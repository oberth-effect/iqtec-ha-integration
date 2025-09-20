"""The IQtec Smart Home integration."""

from __future__ import annotations

from piqtec.controller import Controller

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import IqTecConfigEntry, IqTecCoordinator, IQTecData

_PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: IqTecConfigEntry) -> bool:
    """Set up IQtec Smart Home from a config entry."""
    try:
        hub = await hass.async_add_executor_job(Controller, entry.data["host"])
    except ConnectionError as err:
        raise ConfigEntryNotReady(f"Got: {err}") from None

    coordinator = IqTecCoordinator(hass, entry, hub)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = IQTecData(
        coordinator=coordinator, cover_use_short_tilt=entry.data["cover_use_short_tilt"]
    )
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: IqTecConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
