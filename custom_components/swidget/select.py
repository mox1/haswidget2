"""Select for a Panasonic ERV: the ventilation mode."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwidgetDataUpdateCoordinator
from .entity import CoordinatedSwidgetEntity, async_refresh_after
from .swidgetclient.swidgeterv import SwidgetERV

# Option shown in HA -> device mode. Some duct installs block recirculation; the ERV then ignores it.
MODES = {
    "Ventilate": "heatExchange",
    "Supply": "supply",
    "Exhaust": "exhaust",
    "Recirculate": "recirculation",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SwidgetDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if coordinator.device.is_erv:
        async_add_entities([SwidgetErvModeSelect(coordinator.device, coordinator)])


class SwidgetErvModeSelect(CoordinatedSwidgetEntity, SelectEntity):
    """The ERV's ventilation mode."""

    device: SwidgetERV
    _attr_icon = "mdi:hvac"
    _attr_options = list(MODES)

    def __init__(self, device: SwidgetERV, coordinator: SwidgetDataUpdateCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_name = "Mode"
        self._attr_unique_id = f"{self._unique_id_prefix}_mode"

    @property
    def current_option(self) -> str | None:
        mode = self.device.mode
        return next((name for name, value in MODES.items() if value == mode), None)

    @async_refresh_after
    async def async_select_option(self, option: str) -> None:
        await self.device.set_mode(MODES[option])
