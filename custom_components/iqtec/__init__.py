"""The IQtec Smart Home integration."""

from __future__ import annotations

import logging

from piqtec import Controller, IQtecError
import requests

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .calendar_schedule import async_register_services
from .const import CONF_CORRECTION_TIMEOUT, CONF_COVER_USE_SHORT_TILT, DEFAULT_CORRECTION_TIMEOUT, DOMAIN
from .coordinator import IqTecCalendarCoordinator, IqTecConfigEntry, IqTecCoordinator, IQTecData
from .monitor import RequestMonitor

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def _async_migrate_unique_ids(hass: HomeAssistant, entry: IqTecConfigEntry) -> None:
    """Scope unique ids to the config entry so two controllers can coexist."""
    prefix = f"{DOMAIN}-"

    def migrate(registry_entry: er.RegistryEntry) -> dict[str, str] | None:
        if not registry_entry.unique_id.startswith(prefix):
            return None
        return {"new_unique_id": f"{entry.entry_id}-{registry_entry.unique_id.removeprefix(prefix)}"}

    await er.async_migrate_entries(hass, entry.entry_id, migrate)


@callback
def _async_migrate_device_identifiers(hass: HomeAssistant, entry: IqTecConfigEntry) -> None:
    """Scope device identifiers to the config entry, as the unique ids are.

    Rooms, covers and generic devices used to be identified by their controller
    name alone, which every installation shares. Those of this entry get the
    entry id prepended; a device already scoped to an entry, this one or
    another, is left alone.
    """
    registry = dr.async_get(hass)
    entry_ids = {other.entry_id for other in hass.config_entries.async_entries(DOMAIN)}
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        identifiers = {
            (domain, value if domain != DOMAIN or value.partition("-")[0] in entry_ids else f"{entry.entry_id}-{value}")
            for domain, value in device.identifiers
        }
        if identifiers != device.identifiers:
            registry.async_update_device(device.id, new_identifiers=identifiers)


def _monitor_traffic(hub: Controller) -> RequestMonitor:
    """Count the requests piqtec makes on the HTTP session of the hub.

    The session is an implementation detail of piqtec, so its absence is not an
    error: the integration keeps working, only the per-request counters stay at
    zero.
    """
    monitor = RequestMonitor()
    session = getattr(hub, "_session", None)
    if isinstance(session, requests.Session):
        monitor.install(session)
    else:
        _LOGGER.warning("This piqtec version does not expose its HTTP session; request counters stay at zero")
    return monitor


async def async_setup_entry(hass: HomeAssistant, entry: IqTecConfigEntry) -> bool:
    """Set up IQtec Smart Home from a config entry."""
    try:
        hub = await hass.async_add_executor_job(Controller, entry.data[CONF_HOST])
    except IQtecError as err:
        raise ConfigEntryNotReady(f"Cannot connect to the IQtec controller: {err}") from err
    monitor = _monitor_traffic(hub)

    await _async_migrate_unique_ids(hass, entry)
    _async_migrate_device_identifiers(hass, entry)

    coordinator = IqTecCoordinator(hass, entry, hub, monitor)
    await coordinator.async_config_entry_first_refresh()

    calendars = IqTecCalendarCoordinator(hass, entry, hub, monitor)
    await calendars.async_config_entry_first_refresh()

    entry.runtime_data = IQTecData(
        coordinator=coordinator,
        calendars=calendars,
        monitor=monitor,
        cover_use_short_tilt=entry.data.get(CONF_COVER_USE_SHORT_TILT, False),
        correction_time=entry.data.get(CONF_CORRECTION_TIMEOUT, DEFAULT_CORRECTION_TIMEOUT),
    )
    async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    # Every enabled entity has registered what it needs by now.
    coordinator.async_finish_discovery()

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: IqTecConfigEntry) -> None:
    """Rebuild the entities after the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: IqTecConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unloaded:
        await hass.async_add_executor_job(entry.runtime_data.coordinator.hub.close)
    return unloaded
