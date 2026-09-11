"""DataUpdate Coordinator for IQtec platform."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from piqtec import Controller, IQtecError, State

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class IQTecData:
    """Runtime dataclass."""

    coordinator: IqTecCoordinator
    cover_use_short_tilt: bool
    correction_time: int


type IqTecConfigEntry = ConfigEntry[IQTecData]


class IqTecCoordinator(DataUpdateCoordinator[State]):
    """IQtec coordinator."""

    config_entry: IqTecConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: IqTecConfigEntry, hub: Controller) -> None:
        """Initialize IQtec coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            config_entry=config_entry,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.hub = hub

    async def _async_update_data(self) -> State:
        """Fetch the status data from IQtec."""
        try:
            return await self.hass.async_add_executor_job(self.hub.update)
        except IQtecError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
