import asyncio
import json
import logging
import socket
from typing import Awaitable, Callable, Dict, Optional, Type, cast
from urllib.parse import urlparse

import ssdp

from .device import DeviceType, SwidgetDevice
from .swidgetdimmer import SwidgetDimmer
from .swidgeterv import SwidgetERV
from .swidgetoutlet import SwidgetOutlet
from .swidgetswitch import SwidgetSwitch
from .swidgettimerswitch import SwidgetTimerSwitch
from .exceptions import SwidgetUnsupportedDevice

RESPONSE_SEC = 5
SWIDGET_ST = "urn:swidget:pico:1"
_LOGGER = logging.getLogger(__name__)


class SwidgetDiscoveredDevice:
    def __init__(self, mac: str, host: str, friendly_name: str = "Swidget Discovered Device"):
        self.mac = mac
        self.host = host
        self.friendly_name = friendly_name

    def __repr__(self):
        return f"<{self.friendly_name} at {self.host}>"


class SwidgetProtocol(ssdp.SimpleServiceDiscoveryProtocol):
    """Collect the Swidget devices that answer one SSDP search."""

    def __init__(self):
        self.devices: dict[str, SwidgetDiscoveredDevice] = {}

    def datagram_received(self, data, addr):
        # Any other device can answer; an error here would reach the event loop's error log
        try:
            super().datagram_received(data, addr)
        except Exception:  # pylint: disable=broad-except
            _LOGGER.debug("Ignoring a malformed SSDP reply from %s", addr[0], exc_info=True)

    def response_received(self, response: ssdp.SSDPResponse, addr: tuple):
        "Handle an incoming response."
        headers = {name.upper(): value for name, value in response.headers}
        if headers.get("ST") != SWIDGET_ST:
            return
        _LOGGER.debug("SSDP reply from %s: %s", addr[0], headers.get("SERVER"))
        mac_address = headers["USN"].split("-")[-1]
        ip_address = urlparse(headers["LOCATION"]).hostname
        # SERVER looks like: Swidget/1.0 outlet_20a+control/"Kitchen"
        friendly_name = headers["SERVER"].split("/")[2].strip('"')
        self.devices[mac_address] = SwidgetDiscoveredDevice(mac_address, ip_address, friendly_name)


async def discover_devices() -> dict[str, SwidgetDiscoveredDevice]:
    """Search the network for Swidget devices for RESPONSE_SEC seconds."""
    transport, protocol = await asyncio.get_running_loop().create_datagram_endpoint(
        SwidgetProtocol, family=socket.AF_INET
    )
    try:
        # Send out an M-SEARCH request, requesting Swidget service types.
        search_request = ssdp.SSDPRequest(
            "M-SEARCH",
            headers={
                "HOST": "239.255.255.250:1900",
                "MAN": '"ssdp:discover"',
                "MX": RESPONSE_SEC,
                "ST": SWIDGET_ST,
            },
        )
        search_request.sendto(transport, (SwidgetProtocol.MULTICAST_ADDRESS, 1900))
        await asyncio.sleep(RESPONSE_SEC)
    finally:
        transport.close()
    _LOGGER.debug("Found the following Swidget devices from SSDP discovery: %s", protocol.devices)
    return protocol.devices


async def discover_single(host: str, password: str, ssl: bool) -> SwidgetDevice:
    """Discover a single device by the given IP address.

    :param host: Hostname of device to query
    :rtype: SwidgetDevice
    :return: Object for querying/controlling found device.
    :raises SwidgetException: the device cannot be reached, rejects the key, or is not supported
    """
    swidget_device = SwidgetDevice(host, password, ssl, use_websockets=False)
    try:
        await swidget_device.get_summary()
    finally:
        await swidget_device.close()
    device_type = swidget_device.device_type
    device_class = _get_device_class(device_type)
    dev = device_class(host, password, False)
    try:
        await dev.update()
    except BaseException:
        # Each setup retry would otherwise leak an HTTP session ("Unclosed client session")
        await dev.close()
        raise
    return dev

def _get_device_class(device_type: str) -> Type[SwidgetDevice]:
    """Find SmartDevice subclass for device described by passed data."""
    if device_type == "outlet" or device_type == "outlet_20a":
        return SwidgetOutlet
    elif device_type == "switch":
        return SwidgetSwitch
    elif device_type == "dimmer":
        return SwidgetDimmer
    elif device_type == "pana_switch":
        return SwidgetTimerSwitch
    elif device_type == "relay_switch":
        return SwidgetSwitch
    elif device_type.startswith("pesna_"):
        return SwidgetERV
    raise SwidgetUnsupportedDevice(f"Unsupported Swidget device type: {device_type}")
