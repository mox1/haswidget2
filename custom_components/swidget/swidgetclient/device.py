import json
import logging
import time

from aiohttp import ClientError, ClientSession, ClientTimeout, TCPConnector
from enum import auto, Enum
from typing import Any, Dict, List

from .exceptions import SwidgetAuthError, SwidgetException
from .websocket import SwidgetWebsocket

_LOGGER = logging.getLogger(__name__)
# Without it aiohttp waits up to 5 minutes for a device that accepts the connection but never answers
HTTP_TIMEOUT = ClientTimeout(total=10)


class DeviceType(Enum):
    """Device type enum."""

    Dimmer = "dimmer"
    Outlet = "outlet"
    Switch = "switch"
    TimerSwitch = "pana_switch"
    RelaySwitch = "relay_switch"
    Unknown = -1


class SwidgetDevice:
    def __init__(self, host, secret_key, ssl=False, use_websockets=True):
        self.ip_address = host
        self.ssl = ssl
        self.secret_key = secret_key
        self.use_websockets = use_websockets
        self._friendly_name = "Unknown Swidget Device"
        headers = {"x-secret-key": self.secret_key}
        connector = TCPConnector(force_close=True)
        self._session = ClientSession(headers=headers, connector=connector)
        self._last_update = None
        self.device_config = {}
        self._update_listeners = []
        self._websocket = None
        if self.use_websockets:
            self._websocket = SwidgetWebsocket(
                host=self.ip_address,
                secret_key=self.secret_key,
                callback=self.message_callback,
                session=self._session,
                connection_callback=self.connection_callback)

    @property
    def connected(self) -> bool:
        """Return True when the device can be reached for updates."""
        return self._websocket is None or self._websocket.connected

    def add_update_listener(self, listener):
        """Call listener() after every state or connection change; returns a remover."""
        self._update_listeners.append(listener)
        return lambda: self._update_listeners.remove(listener)

    def _notify_listeners(self):
        for listener in list(self._update_listeners):
            listener()

    async def close(self):
        """Stop the websocket and close the HTTP session."""
        if self._websocket is not None:
            await self._websocket.close()
        await self._session.close()

    async def message_callback(self, message):
        """Entrypoint for a websocket callback"""
        request_id = message.get("request_id")
        if request_id == "summary":
            await self.process_summary(message)
        elif request_id in ("state", "DYNAMIC_UPDATE", "command"):
            await self.process_state(message)
        else:
            _LOGGER.debug("Swidget %s: ignoring message: %s", self.ip_address, message)
            return
        self._notify_listeners()

    async def connection_callback(self, connected):
        """Re-read the device after every (re)connect; updates sent while offline were missed."""
        if connected:
            try:
                await self.get_state()
            except Exception as error:  # pylint: disable=broad-except
                _LOGGER.warning("Swidget %s: could not refresh state after connecting: %s",
                                self.ip_address, type(error).__name__)
        self._notify_listeners()

    async def _request(self, method: str, path: str, data: str | None = None, parse_json: bool = True) -> Any:
        """Send one HTTP request; raise SwidgetException (SwidgetAuthError for a bad key) on any failure."""
        try:
            async with self._session.request(
                method, f"https://{self.ip_address}{path}", data=data, ssl=self.ssl, timeout=HTTP_TIMEOUT
            ) as response:
                if response.status in (401, 403):
                    raise SwidgetAuthError(f"Swidget {self.ip_address} rejected the access key (HTTP {response.status})")
                if response.status != 200:
                    raise SwidgetException(f"Swidget {self.ip_address}: {method} {path} failed with HTTP {response.status}")
                return await response.json(content_type=None) if parse_json else None
        except (ClientError, TimeoutError, ValueError) as error:
            # str(), never repr(): an aiohttp repr can include the request headers, which carry the key
            raise SwidgetException(
                f"Swidget {self.ip_address}: {method} {path} failed: {type(error).__name__}: {error}"
            ) from error

    async def get_summary(self):
        """Get a summary of the device over HTTP"""
        await self.process_summary(await self._request("GET", "/api/v1/summary"))

    async def process_summary(self, summary):
        """ Process the data around the summary of the device"""
        self.model = summary["model"]
        self.mac_address = summary["mac"]
        self.version = summary["version"]
        self.assemblies = {
            "host": SwidgetAssembly(summary["host"]),
            "insert": SwidgetAssembly(summary["insert"]),
        }
        self.device_type = self.assemblies['host'].type
        self.insert_type = self.assemblies['insert'].type
        self.id = self.assemblies['host'].id
        self._last_update = int(time.time())

    async def get_state(self):
        """ Get the state of the device over HTTP"""
        await self.process_state(await self._request("GET", "/api/v1/state"))

    async def process_state(self, state):
        """ Process any information about the state of the device or insert"""
        _LOGGER.debug("Swidget %s: processing state: %s", self.ip_address, state)
        # State is not always in the state (during callback)
        try:
            self.rssi = state["connection"]["rssi"]
        except:
            pass
        """
        2022-06-28 14:53:13 ERROR (MainThread) [custom_components.swidget.swidgetclient.device] Self.assemblies: {'host': <custom_components.swidget.swidgetclient.device.SwidgetAssembly object at 0xffff862b6280>, 'insert': <custom_components.swidget.swidgetclient.device.SwidgetAssembly object at 0xffff8f0b5520>}
        Processing state: {'request_id': 'command', 'insert': {'components': {'usb': {'toggle': {}, 'state': 'on'}}}}

        """
        for assembly in self.assemblies:
            for id, component in self.assemblies[assembly].components.items():
                try:
                    component.functions.update(state[assembly]["components"][id])
                except (KeyError, TypeError):
                    pass
        self._last_update = int(time.time())

    async def get_friendly_name(self):
        try:
            name = (await self._request("GET", "/api/v1/name"))["name"]
        except (SwidgetException, KeyError, TypeError):
            name = f"Swidget {self.device_type} w/{self.insert_type} insert"
        await self.process_friendly_name(name)

    async def process_friendly_name(self, name):
        self._friendly_name = name

    async def update(self):
        if self._last_update is None:
            _LOGGER.debug("Performing the initial update to obtain sysinfo")
        await self.get_summary()
        await self.get_state()
        await self.get_friendly_name()

    async def send_config(self, payload: dict):
        data = json.dumps({"type":"config","request_id":"abcd", "payload": payload})
        await self._websocket.send_str(data)

    async def get_device_config(self):
        """Read the device config (the settings on the device's own web page)."""
        self.device_config = await self._request("GET", "/api/v1/device_config")

    async def update_device_config(self, config: dict):
        """Merge settings into the device config, as its web page does (e.g. {"led": {"lightSuppress": False}})."""
        await self._request("POST", "/api/v1/device_config", json.dumps(config))

    async def set_indicator_light(self, show_host_state: bool | None = None, brightness: int | None = None):
        """Set the indicator light: whether it shows the host's on/off state, and its brightness (0-100)."""
        led = {}
        if show_host_state is not None:
            led["lightSuppress"] = not show_host_state
        if brightness is not None:
            led["brightness"] = brightness
        if led:
            await self.update_device_config({"led": led})

    async def send_command(
        self, assembly: str, component: str, function: str, command: dict
    ):
        """Send a command to the Swidget device either using a HTTP call or the existing websocket"""
        data = {assembly: {"components": {component: {function: command}}}}

        if self.use_websockets:
            data = json.dumps({"type": "command",
                               "request_id": "command",
                               "payload": data
                               })
            await self._websocket.send_str(data)
        else:
            state = await self._request("POST", "/api/v1/command", json.dumps(data))
            function_value = state[assembly]["components"][component][function]
            self.assemblies[assembly].components[component].functions[function] = function_value  # fmt: skip

    async def blink(self):
        """Make the device LED blink

        :raises SwidgetException: Raise the exception if there we are unable to connect to the Swidget device
        """
        await self._request("GET", "/blink?x-user-key=dqMMBX9deuwtkkp784ewTjqo76IYfThV", parse_json=False)

    @property
    def hw_info(self) -> Dict:
        """
        Return hardware information.

        This returns just a selection of attributes that are related to hardware.
        """
        return {
            "version": self.version,
            "mac_address": self.mac_address,
            "type": self.device_type,
            "id": self.id,
            "model": self.model,
            "insert_type": self.insert_type,
            "features": self.features,
            "rssi": self.rssi
        }

    def get_child_consumption(self, plug_id=0):
        """Get the power consumption of a plug in watts."""
        if plug_id == "all":
            return_dict = {}
            for id, properties in self.assemblies['host'].components.items():
                try:
                    return_dict[f"power_{id}"] = properties.functions['power']['current']
                except KeyError: # Hits this when there is no power metering
                    return None
            return return_dict
        return self.assemblies['host'].components[str(plug_id)].functions['power']['current']

    @property
    def realtime_values(self):
        """Get a dict of realtime value attributes from the insert and host

        :return: A dictionary of insert sensor values and power consumption values
        :rtype: dict
        """
        return_dict = {}
        for feature in self.features:
            return_dict.update(self.get_function_values(feature))
        return_dict.update({'rssi': self.rssi})
        power_values = self.get_child_consumption("all")
        if power_values:
            return_dict.update(power_values)
        return return_dict

    @property
    def features(self) -> List[str]:
        """Return a set of features that the device supports."""
        try:
            return list(self.assemblies['insert'].components.keys())
        except KeyError:
            _LOGGER.debug("Device does not have feature information")
            return set()

    def get_function_values(self, function: str):
        """Return the values of an insert function."""
        return_values = dict()
        for function, data in self.assemblies['insert'].components[function].functions.items():
            if function == "occupied":
                return_values[function] = data['state']
            elif function == "toggle":
                pass
            else:
                return_values[function] = data['now']
        return return_values

    def get_sensor_value(self, function, sensor):
        """Return the value of a sensor given a function and sensor"""
        if sensor == "occupied":
            return self.assemblies['insert'].components[function].functions['occupied']['state']
        else:
            return self.assemblies['insert'].components[function].functions[sensor]['now']

    @property
    def is_outlet(self) -> bool:
        """Return True if the device is an outlet."""
        return self.device_type == "outlet" or self.device_type == "outlet_20a"

    @property
    def is_switch(self) -> bool:
        """Return True if the device is a switch"""
        return self.device_type == "switch" or self.device_type == "pana_switch" or self.device_type == "relay_switch"
    @property
    def is_pana_switch(self) -> bool:
        """Return True if the device is a pana_switch"""
        return self.device_type == "pana_switch"

    @property
    def is_erv(self) -> bool:
        """Return True if the device is a Panasonic ERV (e.g. pesna_IB150)"""
        return self.device_type.startswith("pesna_")

    @property
    def is_dimmer(self) -> bool:
        """Return True if the device is a dimmer"""
        return self.device_type == "dimmer"

    @property  # type: ignore
    def friendly_name(self) -> str:
        """Return a friendly description of the device"""
        return self._friendly_name

    def __repr__(self):
        if self._last_update is None:
            return f"<{self.device_type} at {self.ip_address} - update() needed>"
        return f"<{self.device_type} model {self.model} at {self.ip_address}>"

class SwidgetAssembly:
    def __init__(self, summary: dict):
        self.type = summary["type"]
        self.components = {
            c["id"]: SwidgetComponent(c["functions"]) for c in summary["components"]
        }
        self.id = summary.get("id")
        self.error = summary.get("error")


class SwidgetComponent:
    def __init__(self, functions):
        self.functions = {f: None for f in functions}
