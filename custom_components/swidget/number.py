"""Numbers for a Panasonic ERV: the settings in its device config."""
from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwidgetDataUpdateCoordinator
from .entity import CoordinatedSwidgetEntity, async_refresh_after
from .swidgetclient.swidgeterv import SwidgetERV


def _airflow(key: str, name: str) -> NumberEntityDescription:
    # Limits come from the device (SwidgetERV.airflow_range): it stores any value, even above its maximum
    return NumberEntityDescription(
        key=key,
        name=name,
        native_step=1,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_FEET_PER_MINUTE,
        device_class=NumberDeviceClass.VOLUME_FLOW_RATE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )


def _humidity(key: str, name: str) -> NumberEntityDescription:
    # The ERV accepts 30-80 % and ignores other values
    return NumberEntityDescription(
        key=key,
        name=name,
        native_min_value=30,
        native_max_value=80,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.HUMIDITY,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )


# Keys are ERV device_config keys
ERV_NUMBERS: tuple[NumberEntityDescription, ...] = (
    _airflow("lowSa", "Low supply airflow"),
    _airflow("lowEa", "Low exhaust airflow"),
    _airflow("highSa", "High supply airflow"),
    _airflow("highEa", "High exhaust airflow"),
    _airflow("boostSa", "Boost supply airflow"),
    _airflow("boostEa", "Boost exhaust airflow"),
    # Setting it also turns "Intermittent runtime auto" off, as on the ERV panel
    NumberEntityDescription(
        key="runtime",
        name="Intermittent runtime",
        native_min_value=1,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    _humidity("humidityControlSetting", "Humidity control setpoint"),
    _humidity("highHumidityThreshold", "High humidity threshold"),
    NumberEntityDescription(
        key="lowTempThreshold",
        name="Low temperature threshold",
        native_min_value=-10,
        native_max_value=20,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SwidgetDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    device = coordinator.device
    if device.is_erv:
        async_add_entities(
            SwidgetErvNumber(device, coordinator, description)
            for description in ERV_NUMBERS
            if description.key in device.settings
        )


class SwidgetErvNumber(CoordinatedSwidgetEntity, NumberEntity):
    """A numeric ERV setting."""

    device: SwidgetERV

    def __init__(
        self,
        device: SwidgetERV,
        coordinator: SwidgetDataUpdateCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        super().__init__(device, coordinator)
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{self._unique_id_prefix}_{description.key}"
        if description.native_unit_of_measurement == UnitOfVolumeFlowRate.CUBIC_FEET_PER_MINUTE:
            self._attr_native_min_value, self._attr_native_max_value = device.airflow_range

    @property
    def native_value(self) -> float:
        return self.device.settings[self.entity_description.key]

    @async_refresh_after
    async def async_set_native_value(self, value: float) -> None:
        await self.device.set_setting(self.entity_description.key, int(value))
