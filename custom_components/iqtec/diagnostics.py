"""Diagnostics support for the IQtec Smart Home integration."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import IqTecConfigEntry

TO_REDACT = {CONF_HOST}


def _piqtec_version() -> str | None:
    try:
        return version("piqtec")
    except PackageNotFoundError:
        return None


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: IqTecConfigEntry) -> dict[str, Any]:
    """Describe the controller, what is polled and how the polling is going."""
    data = entry.runtime_data
    coordinator = data.coordinator
    hub = coordinator.hub
    plan = coordinator.plan()
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "piqtec_version": _piqtec_version(),
        "controller": {
            "rooms": sorted(hub.rooms),
            "sunblinds": sorted(hub.sunblinds),
            "calendars": sorted(hub.calendars),
            "devices": {idx: len(device.all_apis) for idx, device in sorted(hub.devices.items())},
        },
        "polling": {
            "scan_interval": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
            "calendar_scan_interval": (
                data.calendars.update_interval.total_seconds() if data.calendars.update_interval else None
            ),
            "discovering": coordinator.discovering,
            "units": plan.units,
            "devices": plan.devices,
            "addresses": plan.paths,
            "last_update_success": coordinator.last_update_success,
            "calendars_last_update_success": data.calendars.last_update_success,
        },
        "stats": data.monitor.stats.as_dict(),
    }
