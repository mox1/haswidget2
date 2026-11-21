"""Config flow: adding a device by IP address. Needs requirements_test.txt."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swidget.config_flow import CannotConnect, InvalidAuth
from custom_components.swidget.const import DOMAIN

DEVICE = {"title": "erv", "mac": "020000000001"}
USER_INPUT = {"host": "192.0.2.130", "password": ""}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_network():
    # These tests cover the form only; test_erv_setup.py covers setting up an entry
    with patch("custom_components.swidget.async_setup_entry", AsyncMock(return_value=True)), patch(
        "custom_components.swidget.discover_devices", AsyncMock(return_value={})
    ):
        yield


async def _submit(hass, validate):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    with patch("custom_components.swidget.config_flow.validate_input", validate):
        return await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)


async def test_add_by_ip(hass):
    result = await _submit(hass, AsyncMock(return_value=DEVICE))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "erv"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == "02:00:00:00:00:01"


@pytest.mark.parametrize(("error", "reason"), [(CannotConnect, "cannot_connect"), (InvalidAuth, "invalid_auth")])
async def test_add_by_ip_shows_error(hass, error, reason):
    result = await _submit(hass, AsyncMock(side_effect=error))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}


async def test_add_by_ip_refuses_configured_device(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="02:00:00:00:00:01", data={"host": "192.0.2.10", "password": ""})
    entry.add_to_hass(hass)
    result = await _submit(hass, AsyncMock(return_value=DEVICE))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data["host"] == "192.0.2.130"  # the known device moved to the new address
