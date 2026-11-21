"""Config flow for Swidget integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from .swidgetclient.discovery import SwidgetDiscoveredDevice, _get_device_class
from . import async_discover_devices
from .swidgetclient.device import SwidgetDevice
from .swidgetclient.exceptions import SwidgetAuthError, SwidgetUnsupportedDevice
import voluptuous as vol
from homeassistant.helpers.typing import DiscoveryInfoType


from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST, default=""): str,
        vol.Optional("password", default=""): str,
    }
)

# An empty password keeps the current one
STEP_RECONFIGURE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional("password"): str,
    }
)

# Devices with authentication turned off accept an empty access key
STEP_DISCOVERY_CONFIRM_SCHEMA = vol.Schema({vol.Optional("password", default=""): str})


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Connect to the device and return its title and MAC.

    :raises InvalidAuth: the device rejected the access key
    :raises UnsupportedDevice: the integration cannot set up this device type
    :raises CannotConnect: any other failure
    """
    d = SwidgetDevice(data[CONF_HOST], data["password"], False, use_websockets=False)
    try:
        await d.update()
        _get_device_class(d.device_type)
    except SwidgetAuthError as ex:
        raise InvalidAuth from ex
    except SwidgetUnsupportedDevice as ex:
        raise UnsupportedDevice(str(ex)) from ex
    except Exception as ex:
        _LOGGER.debug("Cannot set up Swidget at %s", data[CONF_HOST], exc_info=True)
        raise CannotConnect from ex
    finally:
        await d.close()
    return {"title": f"{d.friendly_name}", "mac": d.mac_address}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swidget."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, SwidgetDiscoveredDevice] = {}
        self._discovered_device: SwidgetDiscoveredDevice | None = None

    async def _async_create_validated_entry(
        self, data: dict[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        """Create the entry if the device answers; otherwise fill errors and return None."""
        try:
            info = await validate_input(self.hass, data)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except UnsupportedDevice as ex:
            _LOGGER.warning("%s", ex)
            errors["base"] = "unsupported_device"
        else:
            # The MAC is the unique_id, so the same device cannot be added twice
            await self.async_set_unique_id(dr.format_mac(info["mac"]), raise_on_progress=False)
            self._abort_if_unique_id_configured(updates=data)
            return self.async_create_entry(title=info["title"], data=data)
        return None

    async def async_step_dhcp(self, discovery_info) -> ConfigFlowResult:
        """Handle discovery via dhcp."""
        _LOGGER.debug("Swidget device found via DHCP: %s", discovery_info)
        return await self._async_handle_discovery(
            discovery_info.ip, discovery_info.macaddress
        )

    async def async_step_ssdp(self, discovery_info) -> ConfigFlowResult:
        """Handle discovery via SSDP."""
        _LOGGER.debug("Swidget device found via SSDP: %s", discovery_info)
        discovered_ip = urlparse(discovery_info.ssdp_location or "").hostname
        discovered_mac = (discovery_info.ssdp_usn or "").split("-")[-1]
        if not discovered_ip or not discovered_mac:
            return self.async_abort(reason="no_devices_found")
        return await self._async_handle_discovery(discovered_ip, discovered_mac)

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        return await self._async_handle_discovery(
            discovery_info[CONF_HOST], discovery_info[CONF_MAC]
        )

    async def _async_handle_discovery(self, host: str, mac: str) -> ConfigFlowResult:
        """Handle any discovery."""
        await self.async_set_unique_id(dr.format_mac(mac))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._async_abort_entries_match({CONF_HOST: host})
        self.context[CONF_HOST] = host
        for progress in self._async_in_progress():
            if progress.get("context", {}).get(CONF_HOST) == host:
                return self.async_abort(reason="already_in_progress")

        self._discovered_device = SwidgetDiscoveredDevice(mac, host)
        await self.async_set_unique_id(
            dr.format_mac(mac), raise_on_progress=True
        )
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovered_device is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_HOST: self._discovered_device.host, "password": user_input.get("password", "")}
            if result := await self._async_create_validated_entry(data, errors):
                return result

        placeholders = {
            "name": self._discovered_device.friendly_name,
            "host": self._discovered_device.host,
        }
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=STEP_DISCOVERY_CONFIRM_SCHEMA,
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_HOST]:
                return await self.async_step_pick_device()
            if result := await self._async_create_validated_entry(user_input, errors):
                return result

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host or access key, keeping the entities."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_HOST: user_input[CONF_HOST],
                "password": user_input.get("password") or entry.data["password"],
            }
            try:
                info = await validate_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except UnsupportedDevice:
                errors["base"] = "unsupported_device"
            else:
                if entry.unique_id and dr.format_mac(info["mac"]) != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_DATA_SCHEMA, {CONF_HOST: entry.data[CONF_HOST]}
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the step to pick discovered device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device = self._discovered_devices[user_input[CONF_DEVICE]]
            data = {CONF_HOST: device.host, "password": user_input.get("password", "")}
            if result := await self._async_create_validated_entry(data, errors):
                return result
        else:
            self._discovered_devices = await async_discover_devices(self.hass)

        configured_devices = {
            entry.unique_id for entry in self._async_current_entries()
        }
        devices_name = {
            mac: f"{device.friendly_name} ({device.host})"
            for mac, device in self._discovered_devices.items()
            if dr.format_mac(mac) not in configured_devices
        }
        # Check if there is at least one device
        if not devices_name:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE): vol.In(devices_name),
                                    vol.Optional("password", default=""): str}),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class UnsupportedDevice(HomeAssistantError):
    """Error to indicate the device type is not supported."""
