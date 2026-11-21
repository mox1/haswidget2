"""The Swidget integration."""
from __future__ import annotations

from datetime import timedelta
from typing import Any
import logging
import re

from .swidgetclient.device import SwidgetDevice
from .swidgetclient.exceptions import SwidgetAuthError, SwidgetException, SwidgetUnsupportedDevice
from .swidgetclient.discovery import SwidgetDiscoveredDevice, discover_devices, discover_single

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry

from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_MAC,
    EVENT_HOMEASSISTANT_STOP,
)

from homeassistant.core import Event, callback, HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import SwidgetDataUpdateCoordinator
from .entity import unique_id_prefix

_LOGGER = logging.getLogger(__name__)
DISCOVERY_INTERVAL = timedelta(minutes=15)
# Before 0.0.4, unique_ids started with the device repr, which holds the IP:
# "<pana_switch model HK_PICO_1 at 192.0.2.15>_controlled_outlet"
LEGACY_UNIQUE_ID = re.compile(r"^<.* at (?P<host>[^ >]+)(?: - update\(\) needed)?>_(?P<key>.+)$")


@callback
def async_trigger_discovery(
    hass: HomeAssistant,
    discovered_devices: dict[str, SwidgetDevice],
) -> None:
    """Trigger config flows for discovered devices."""
    for mac, device in discovered_devices.items():
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
                data={
                    CONF_NAME: device.friendly_name,
                    CONF_HOST: device.host,
                    CONF_MAC: device.mac,
                },
            )
        )

async def async_discover_devices(hass: HomeAssistant) -> dict[str, SwidgetDevice]:
    """Force discover Swidget devices using """
    # broadcast_addresses = await network.async_get_ipv4_broadcast_addresses(hass)
    # tasks = [Discover.discover(target=str(address)) for address in broadcast_addresses]
    discovered_devices: dict[str, SwidgetDiscoveredDevice] = await discover_devices()
    # for device in discovered_devices:
    #     discovered_devices[dr.format_mac(device.mac)] = device
    _LOGGER.debug("Forced Swidget Discovery found: %s", discovered_devices)
    return discovered_devices

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Swidget component."""
    hass.data[DOMAIN] = {}

    async def _async_discovery(*_: Any) -> None:
        try:
            discovered = await async_discover_devices(hass)
        except OSError as err:
            # Discovery is optional (devices can be added by address); do not fail setup over it
            _LOGGER.debug("Swidget SSDP discovery failed: %s", err)
            return
        if discovered:
            async_trigger_discovery(hass, discovered)

    # After startup, so the 5 s SSDP search never delays Home Assistant starting
    async_at_started(hass, _async_discovery)
    async_track_time_interval(hass, _async_discovery, DISCOVERY_INTERVAL, cancel_on_shutdown=True)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Swidget from a config entry."""
    try:
        _LOGGER.debug("Setting up Swidget at %s", entry.data['host'])
        device: SwidgetDevice = await discover_single(entry.data['host'],
                                                      entry.data['password'],
                                                      False)
    except (SwidgetAuthError, SwidgetUnsupportedDevice) as ex:
        # Retrying cannot help: the key or the device itself must change
        raise ConfigEntryError(f"{ex}. Use Reconfigure to change the address or access key.") from ex
    except SwidgetException as ex:
        # Home Assistant logs this once and retries with backoff (e.g. after a power outage)
        raise ConfigEntryNotReady(str(ex)) from ex

    if entry.unique_id is None:
        # Entries added by address before 0.0.6 have no unique_id, so discovery could not match them
        unique_id = dr.format_mac(device.mac_address)
        if hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id) is None:
            hass.config_entries.async_update_entry(entry, unique_id=unique_id)

    await async_migrate_unique_ids(hass, entry, device)
    hass.data[DOMAIN][entry.entry_id] = SwidgetDataUpdateCoordinator(hass, entry, device)
    # hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # A background task of the entry, so HA cancels it on unload and on shutdown
    entry.async_create_background_task(
        hass, device._websocket.listen(), f"swidget websocket {entry.data['host']}"
    )

    async def _async_close_on_stop(_event: Event) -> None:
        # HA does not unload entries when it stops; an open session logs "Unclosed client session"
        await device.close()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_close_on_stop))
    return True


async def async_migrate_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, device: SwidgetDevice
) -> None:
    """Move entities from IP-based to MAC-based unique_ids, keeping their entity_ids.

    Only entities of the current host move. Leftovers from an older IP stay as they are.
    """
    ent_reg = er.async_get(hass)
    prefix = unique_id_prefix(device)

    @callback
    def _migrate(entity_entry: er.RegistryEntry) -> dict[str, Any] | None:
        match = LEGACY_UNIQUE_ID.match(entity_entry.unique_id)
        if match is None or match["host"] != device.ip_address:
            return None
        new_unique_id = f"{prefix}_{match['key']}"
        if existing := ent_reg.async_get_entity_id(entity_entry.domain, DOMAIN, new_unique_id):
            _LOGGER.warning(
                "Swidget %s: not migrating %s, %s already has unique_id %s",
                device.ip_address, entity_entry.entity_id, existing, new_unique_id,
            )
            return None
        _LOGGER.info(
            "Swidget %s: %s now has unique_id %s",
            device.ip_address, entity_entry.entity_id, new_unique_id,
        )
        return {"new_unique_id": new_unique_id}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
    #     hass.data[DOMAIN].pop(entry.entry_id)
    # return unload_ok
    hass_data: dict[str, Any] = hass.data[DOMAIN]
    coordinator: SwidgetDataUpdateCoordinator = hass_data[entry.entry_id]
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator.remove_device_listener()
        await coordinator.device.close()
        hass_data.pop(entry.entry_id)
    return unload_ok
