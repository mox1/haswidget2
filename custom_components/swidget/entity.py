"""Common code for tplink."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from .swidgetclient.device import SwidgetDevice
from .swidgetclient.exceptions import SwidgetException
from typing_extensions import Concatenate, ParamSpec

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SwidgetDataUpdateCoordinator

_T = TypeVar("_T", bound="CoordinatedSwidgetEntity")
_P = ParamSpec("_P")


def async_refresh_after(
    func: Callable[Concatenate[_T, _P], Awaitable[None]]  # type: ignore[misc]
) -> Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]]:  # type: ignore[misc]
    """Define a wrapper to refresh after."""

    async def _async_wrap(self: _T, *args: _P.args, **kwargs: _P.kwargs) -> None:
        try:
            await func(self, *args, **kwargs)
        except SwidgetException as err:
            # Home Assistant logs this as one line; any other exception logs a full traceback
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh_without_children()

    return _async_wrap


def unique_id_prefix(device: SwidgetDevice) -> str:
    """Return the start of every entity unique_id: the MAC, which survives IP changes."""
    return dr.format_mac(device.mac_address)


class CoordinatedSwidgetEntity(CoordinatorEntity[SwidgetDataUpdateCoordinator]):
    """Common base class for all coordinated tplink entities."""

    def __init__(
        self, device: SwidgetDevice, coordinator: SwidgetDataUpdateCoordinator
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.device: SwidgetDevice = device
        self._attr_name = self.device.mac_address.replace(":", "").upper()
        self._attr_unique_id = self.device.id
        self._unique_id_prefix = unique_id_prefix(device)
        # ERV entities start with the device name ("erv Mode"); older types keep their bare names
        self._attr_has_entity_name = device.is_erv

    @property
    def available(self) -> bool:
        """Return False while the websocket to the device is down."""
        return super().available and self.device.connected

    @property
    def device_info(self) -> DeviceInfo:
        """Return information about the device."""
        return DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, self.device.mac_address)},
            identifiers={(DOMAIN, str(self.device.id))},
            manufacturer="Swidget",
            model=self.device.model,
            name=self.device.friendly_name,
            sw_version=self.device.version,
        )

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self.device.is_on)

    @async_refresh_after
    async def set_indicator_light(self, **kwargs: Any) -> None:
        """Handle the set_indicator_light action, which can target any Swidget switch."""
        await self.device.set_indicator_light(
            show_host_state=kwargs.get("show_host_state"), brightness=kwargs.get("brightness")
        )
