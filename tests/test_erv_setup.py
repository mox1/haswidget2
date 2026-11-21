"""Set up the integration with a mocked ERV and drive its entities. Needs requirements_test.txt."""
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swidget.const import DOMAIN
from custom_components.swidget.swidgetclient.swidgeterv import SwidgetERV

from .test_swidgeterv import STATE, SUMMARY

# device_config of the same FV-15ESC1, host component "0"
SETTINGS = {"log_rate": 300000, "toggle": {"lock": "unlocked"}, "model": 12, "highEa": 90, "highSa": 100,
            "balancing": 1, "offset": 0, "defaultTimer": 0, "lowSa": 60, "lowEa": 50, "boostSa": 150,
            "boostEa": 150, "autoRuntime": 1, "supplyLimitLowTemp": 0, "supplyLimitHighHum": 0,
            "intermittentMode": 0, "humidityControl": 0, "outsideHumidityCSensing": 0,
            "humidityControlSetting": 49, "highHumidityThreshold": 50, "lowTempThreshold": 15, "runtime": 30}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def expected_lingering_timers() -> bool:
    # The discovery interval and the coordinator's refresh debouncer can still be scheduled at teardown
    return True


@pytest.fixture
async def erv():
    """An ERV with real state, whose network calls are mocks."""
    device = SwidgetERV("192.0.2.1", "", False)
    await device.process_summary(SUMMARY)
    await device.process_state(STATE)
    await device.process_friendly_name("erv")
    device.device_config = {"host": {"components": {"0": dict(SETTINGS)}}}
    device._websocket.state = "connected"
    device._websocket.listen = AsyncMock()
    device.send_command = AsyncMock()
    device.update_device_config = AsyncMock()
    device.get_device_config = AsyncMock()
    with patch("custom_components.swidget.discover_single", AsyncMock(return_value=device)), patch(
        "custom_components.swidget.discover_devices", AsyncMock(return_value={})
    ):
        yield device


async def test_erv_entities(hass, erv):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.1", "password": ""})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    fan = hass.states.get("fan.erv_ventilation")
    assert fan.state == "on"
    assert fan.attributes["preset_modes"] == ["Low", "High", "Boost"]
    assert fan.attributes["preset_mode"] == "High"
    assert hass.states.get("select.erv_mode").state == "Ventilate"
    assert hass.states.get("sensor.erv_power").state == "58.3"
    assert hass.states.get("sensor.erv_status").state == "normal"
    assert hass.states.get("sensor.erv_outdoor_humidity").state == "unknown"  # the ERV sent 254
    assert hass.states.get("binary_sensor.erv_filter_needs_cleaning").state == "on"
    assert hass.states.get("binary_sensor.erv_error").state == "off"
    assert float(hass.states.get("number.erv_high_supply_airflow").state) == 100
    assert hass.states.get("number.erv_high_supply_airflow").attributes["max"] == 150
    assert hass.states.get("switch.erv_intermittent_runtime_auto").state == "on"
    assert hass.states.get("button.erv_reset_filter") is not None

    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": "fan.erv_ventilation", "preset_mode": "Boost"}, blocking=True
    )
    erv.send_command.assert_awaited_with(assembly="host", component="0", function="boost", command={"mode": "on"})

    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.erv_mode", "option": "Supply"}, blocking=True
    )
    erv.send_command.assert_awaited_with(assembly="host", component="0", function="mode", command="supply")

    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.erv_low_supply_airflow", "value": 70}, blocking=True
    )
    erv.update_device_config.assert_awaited_with({"host": {"components": {"0": {"lowSa": 70}}}})

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.erv_humidity_control"}, blocking=True
    )
    erv.update_device_config.assert_awaited_with({"host": {"components": {"0": {"humidityControl": 1}}}})

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
