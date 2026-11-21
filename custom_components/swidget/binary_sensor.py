from __future__ import annotations

from dataclasses import dataclass

from .swidgetclient.device import SwidgetDevice

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwidgetDataUpdateCoordinator
from .entity import CoordinatedSwidgetEntity


@dataclass(frozen=True, kw_only=True)
class SwidgetBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Swidget binary sensor. key builds the unique_id; emeter_attr is the realtime_values key."""

    emeter_attr: str


SWIDGET_BINARY_SENSORS: tuple[SwidgetBinarySensorEntityDescription, ...] = (
    SwidgetBinarySensorEntityDescription(
        key="Motion",
        name="Motion",
        device_class=BinarySensorDeviceClass.MOTION,
        emeter_attr="occupied",
    ),
    # Panasonic ERV
    SwidgetBinarySensorEntityDescription(
        key="filter_replace",
        name="Filter needs replacement",
        device_class=BinarySensorDeviceClass.PROBLEM,
        emeter_attr="filter_replace",
    ),
    SwidgetBinarySensorEntityDescription(
        key="filter_clean",
        name="Filter needs cleaning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        emeter_attr="filter_clean",
    ),
    SwidgetBinarySensorEntityDescription(
        key="error",
        name="Error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        emeter_attr="error",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator: SwidgetDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    device = coordinator.device
    async_add_entities(
        SwidgetBinarySensor(device, coordinator, description)
        for description in SWIDGET_BINARY_SENSORS
        if description.emeter_attr in device.realtime_values
    )


class SwidgetBinarySensor(CoordinatedSwidgetEntity, BinarySensorEntity):
    """Representation of a Swidget binary sensor"""

    entity_description: SwidgetBinarySensorEntityDescription

    def __init__(
        self,
        device: SwidgetDevice,
        coordinator: SwidgetDataUpdateCoordinator,
        description: SwidgetBinarySensorEntityDescription,
    ) -> None:
        super().__init__(device, coordinator)
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{self._unique_id_prefix}_{description.key}"

    @property
    def is_on(self) -> bool:
        # Only True counts, as before: a device that sends a string must not read as "on"
        return self.device.realtime_values.get(self.entity_description.emeter_attr) is True
