"""DataUpdate Coordinator for IQtec platform."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging

from piqtec.controller import Controller

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class IQTecData:
    """Runtime dataclass."""

    coordinator: DataUpdateCoordinator
    cover_use_short_tilt: bool
    # cover_config: dict[str, Any]


type IqTecConfigEntry = ConfigEntry[IQTecData]


class IqTecCoordinator(DataUpdateCoordinator):
    """IQtec coordinator."""

    hub: Controller
    hass: HomeAssistant

    def __init__(
        self, hass: HomeAssistant, config_entry: IqTecConfigEntry, hub: Controller
    ) -> None:
        """Initialize IQtec coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            config_entry=config_entry,
            update_interval=timedelta(seconds=2),
            always_update=True,
        )
        self.hub = hub
        self.hass = hass

    async def _async_setup(self):
        """Set up the coordinator.

        Test the connection to the IQtec controller
        """
        try:
            async with asyncio.timeout(10):
                await self.hass.async_add_executor_job(self.hub.update_status)
        except ConnectionError as e:
            raise ConfigEntryAuthFailed(
                f"Failed to connect to the Controller: {e}"
            ) from None

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        Fetch the status data from IQtec
        """
        try:
            async with asyncio.timeout(10):
                return await self.hass.async_add_executor_job(self.hub.update_status)
        except ConnectionError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from None
