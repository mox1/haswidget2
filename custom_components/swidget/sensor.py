from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from .swidgetclient.device import SwidgetDevice

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPower,
    UnitOfTemperature,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfVolumeFlowRate,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
)
from .coordinator import SwidgetDataUpdateCoordinator
from .entity import CoordinatedSwidgetEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SwidgetSensorEntityDescription(SensorEntityDescription):
    """Describes A Swidget sensor entity."""

    emeter_attr: str | None = None
    precision: int | None = None

SWIDGET_SENSORS: tuple[SwidgetSensorEntityDescription, ...] = (
    SwidgetSensorEntityDescription(
        key="Power 0",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Plug 0 Current Consumption",
        emeter_attr="power_0",
        precision=1,
    ),
    SwidgetSensorEntityDescription(
        key="Power 1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Plug 1 Current Consumption",
        emeter_attr="power_1",
        precision=1,
    ),
    SwidgetSensorEntityDescription(
        key="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Temperature",
        emeter_attr="temperature",
        precision=1,
    ),
    SwidgetSensorEntityDescription(
        key="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Humidity",
        emeter_attr="humidity",
        precision=0,
    ),
    SwidgetSensorEntityDescription(
        key="Pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Air Pressure",
        emeter_attr="bp",
        precision=0,
    ),
    SwidgetSensorEntityDescription(
        key="Air Quality",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        name="Air Quality",
        emeter_attr="iaq",
        precision=0,
    ),
    SwidgetSensorEntityDescription(
        key="Carbon dioxide",
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        name="Carbon dioxide",
        emeter_attr="eco2",
        precision=1,
    ),
    SwidgetSensorEntityDescription(
        key="Volatile Organic Compounds",
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        # VOLATILE_ORGANIC_COMPOUNDS takes µg/m³; the ppm class is _PARTS
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
        state_class=SensorStateClass.MEASUREMENT,
        name="Volatile Organic Compounds",
        emeter_attr="tvoc",
        precision=1,
    ),
    # Panasonic ERV
    SwidgetSensorEntityDescription(
        key="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Power",
        emeter_attr="power",
        precision=1,
    ),
    SwidgetSensorEntityDescription(
        key="Supply airflow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_FEET_PER_MINUTE,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply airflow",
        emeter_attr="supply_cfm",
        precision=0,
    ),
    SwidgetSensorEntityDescription(
        key="Exhaust airflow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_FEET_PER_MINUTE,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust airflow",
        emeter_attr="exhaust_cfm",
        precision=0,
    ),
    SwidgetSensorEntityDescription(
        key="Indoor temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Indoor temperature",
        emeter_attr="indoors_temperature",
        precision=1,
    ),
    SwidgetSensorEntityDescription(
        key="Indoor humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Indoor humidity",
        emeter_attr="indoors_humidity",
        precision=0,
    ),
    SwidgetSensorEntityDescription(
        key="Outdoor temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outdoor temperature",
        emeter_attr="outdoors_temperature",
        precision=1,
    ),
    SwidgetSensorEntityDescription(
        key="Outdoor humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outdoor humidity",
        emeter_attr="outdoors_humidity",
        precision=0,
    ),
    # normal, defrost, boost, humidity, auto, int, limit, balancing or unknown
    SwidgetSensorEntityDescription(
        key="Status",
        icon="mdi:information-outline",
        name="Status",
        emeter_attr="status",
    ),
    SwidgetSensorEntityDescription(
        key="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category = EntityCategory.DIAGNOSTIC,
        # It changes with almost every update, so it fills the recorder database; opt in
        entity_registry_enabled_default=False,
        name="Signal Strength",
        emeter_attr="rssi",
    ),
)

def async_emeter_from_device(
    device: SwidgetDevice, description: SwidgetSensorEntityDescription
) -> float | None:
    """Map a sensor key to the device attribute."""
    if attr := description.emeter_attr:
        if (val := device.realtime_values.get(attr, None)) is None:
            return None
        if attr == "occupied":
            if val is True:
                return "is_motion"
            return "is_no_motion"
        if description.precision is None:
            return val
        return round(cast(float, val), description.precision)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator: SwidgetDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[SwidgetSensor] = []
    parent = coordinator.device

    def _async_sensors_for_device(device: SwidgetDevice) -> list[SwidgetSensor]:
        return [
            SwidgetSensor(device, coordinator, description)
            for description in SWIDGET_SENSORS
            # Key, not value: an ERV reading can be empty at startup (e.g. no airflow while off)
            if description.emeter_attr in device.realtime_values
        ]

    entities.extend(_async_sensors_for_device(parent))

    async_add_entities(entities)


class SwidgetSensor(CoordinatedSwidgetEntity, SensorEntity):
    """Representation of a Swidget sensor"""

    entity_description: SwidgetSensorEntityDescription

    def __init__(
        self,
        device: SwidgetDevice,
        coordinator: SwidgetDataUpdateCoordinator,
        description: SwidgetSensorEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(device, coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{self._unique_id_prefix}_{self.entity_description.key}"
        )

    @property
    def name(self) -> str:
        """Return the name of the Smart Plug.

        Overridden to include the description.
        """
        return f"{self.entity_description.name}"

    @property
    def native_value(self) -> float | None:
        """Return the sensors state."""
        return async_emeter_from_device(self.device, self.entity_description)
