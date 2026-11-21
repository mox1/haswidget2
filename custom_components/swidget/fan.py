"""Fan for a Panasonic ERV: on/off and the speeds Low, High and Boost."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwidgetDataUpdateCoordinator
from .entity import CoordinatedSwidgetEntity, async_refresh_after
from .swidgetclient.swidgeterv import SwidgetERV

# Preset name shown in HA -> speed in SwidgetERV
SPEEDS = {"Low": "low", "High": "high", "Boost": "boost"}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SwidgetDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if coordinator.device.is_erv:
        async_add_entities([SwidgetErvFan(coordinator.device, coordinator)])


class SwidgetErvFan(CoordinatedSwidgetEntity, FanEntity):
    """The ERV's ventilation."""

    device: SwidgetERV
    _attr_supported_features = (
        FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = list(SPEEDS)

    def __init__(self, device: SwidgetERV, coordinator: SwidgetDataUpdateCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_name = "Ventilation"
        self._attr_unique_id = f"{self._unique_id_prefix}_ventilation"

    @property
    def is_on(self) -> bool:
        return self.device.is_on

    @property
    def preset_mode(self) -> str | None:
        speed = self.device.speed
        return next((name for name, value in SPEEDS.items() if value == speed), speed)

    @async_refresh_after
    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        await self.device.turn_on()
        if preset_mode is not None:
            await self.device.set_speed(SPEEDS[preset_mode])

    @async_refresh_after
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.device.turn_off()

    @async_refresh_after
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.device.set_speed(SPEEDS[preset_mode])
