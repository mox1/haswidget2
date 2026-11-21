"""Support for Elgato button."""
from __future__ import annotations

import logging

from .swidgetclient.device import SwidgetDevice
from .swidgetclient.exceptions import SwidgetException

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwidgetDataUpdateCoordinator

from .entity import CoordinatedSwidgetEntity, async_refresh_after

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Elgato button based on a config entry."""

    coordinator: SwidgetDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[ButtonEntity] = [SwidgetIdentifyButton(coordinator.device, coordinator)]
    if coordinator.device.is_erv:
        entities.append(SwidgetErvFilterResetButton(coordinator.device, coordinator))
    async_add_entities(entities)


class SwidgetIdentifyButton(CoordinatedSwidgetEntity, ButtonEntity):
    """Defines an Swidget identify button."""

    def __init__(
        self,
        device: SwidgetDevice,
        coordinator: SwidgetDataUpdateCoordinator,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(device, coordinator)
        self.entity_description = ButtonEntityDescription(
            key="Blink",
            name="Blink",
            icon="mdi:flash",
            entity_category=EntityCategory.CONFIG,
        )
        self._attr_name = "Blink"
        self._attr_unique_id = f"{self._unique_id_prefix}_{self.entity_description.key}"

    @async_refresh_after
    async def async_press(self) -> None:
        """Identify the device by making it blink."""
        await self.device.blink()


class SwidgetErvFilterResetButton(CoordinatedSwidgetEntity, ButtonEntity):
    """Reset the ERV's filter run time after filter maintenance."""

    _attr_icon = "mdi:air-filter"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        device: SwidgetDevice,
        coordinator: SwidgetDataUpdateCoordinator,
    ) -> None:
        super().__init__(device, coordinator)
        self._attr_name = "Reset filter"
        self._attr_unique_id = f"{self._unique_id_prefix}_reset_filter"

    @async_refresh_after
    async def async_press(self) -> None:
        await self.device.reset_filter()
