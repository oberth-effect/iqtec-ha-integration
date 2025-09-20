"""IQtec Covers."""

import logging
from typing import Any

from piqtec.constants import SUNBLIND_COMMANDS, SUNBLIND_EXTENDED, SUNBLIND_TILT_CLOSED
from piqtec.unit.sunblind import SunblindState

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import IqTecEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Cover entries."""
    coordinator = config_entry.runtime_data.coordinator
    short_tilt = config_entry.runtime_data.cover_use_short_tilt
    async_add_entities(
        IqTecCover(coordinator, idx, short_tilt) for idx in coordinator.hub.sunblinds
    )


class IqTecCover(IqTecEntity, CoverEntity):
    """IQtec Cover Entity."""

    iqtec_state: SunblindState

    supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    device_class = CoverDeviceClass.BLIND

    def __init__(
        self, coordinator: IqTecCoordinator, idx: str, short_tilt: bool
    ) -> None:
        """Initialise IQtec Cover."""
        super().__init__(coordinator, idx)
        self._short_tilt = short_tilt
        self.iqtec_state = coordinator.data.sunblinds[self.idx]

        if self.iqtec_state.full_time_time > 0:
            self.supported_features = (
                self.supported_features
                | CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.STOP_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )

        room_id = self.idx.split("_")[0]
        self._attr_device_info = self._default_device_info | DeviceInfo(
            identifiers={(DOMAIN, room_id)},
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.iqtec_state = self.coordinator.data.sunblinds[self.idx]
        _LOGGER.debug("Updating device: %s", self.idx)
        self.async_write_ha_state()

    @property
    def is_closed(self) -> bool:
        """Return if closed."""
        return self.iqtec_state.position == SUNBLIND_EXTENDED

    @property
    def current_cover_position(self) -> int:
        """Return cover position."""
        return int(
            float(SUNBLIND_EXTENDED - self.iqtec_state.position)
            * 100
            / SUNBLIND_EXTENDED
        )

    @property
    def current_cover_tilt_position(self) -> int:
        """Return tilt position."""
        return int(
            float(SUNBLIND_TILT_CLOSED - self.iqtec_state.rotation)
            * 100
            / SUNBLIND_TILT_CLOSED
        )

    @property
    def is_closing(self) -> bool:
        """Return cover closing."""
        return self.iqtec_state.out_dn_1 or self.iqtec_state.out_dn_2

    @property
    def is_opening(self) -> bool:
        """Return cover closing."""
        return self.iqtec_state.out_up_1 or self.iqtec_state.out_up_2

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        self.hass.async_add_executor_job(
            self._hub.sunblinds[self.idx].set_command, SUNBLIND_COMMANDS.UP
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        self.hass.async_add_executor_job(
            self._hub.sunblinds[self.idx].set_command, SUNBLIND_COMMANDS.DOWN
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        self.hass.async_add_executor_job(
            self._hub.sunblinds[self.idx].set_command, SUNBLIND_COMMANDS.STOP
        )

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs[ATTR_POSITION]
        pos = int(float(100 - position) * SUNBLIND_EXTENDED / 100)
        self.hass.async_add_executor_job(
            self._hub.sunblinds[self.idx].set_position, pos
        )

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        """Open the cover tilt."""
        if self._short_tilt:
            self.hass.async_add_executor_job(
                self._hub.sunblinds[self.idx].set_command,
                SUNBLIND_COMMANDS.TILT_OPEN_SHORT,
            )
        else:
            self.hass.async_add_executor_job(
                self._hub.sunblinds[self.idx].set_command, SUNBLIND_COMMANDS.TILT_OPEN
            )

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        """Close the cover tilt."""
        await self.async_set_cover_tilt_position(tilt_position=0)

    async def async_stop_cover_tilt(self, **kwarg: Any) -> None:
        """Stop the cover."""
        await self.async_stop_cover()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Move the cover tilt to a specific position."""
        tilt = kwargs[ATTR_TILT_POSITION]
        rotation = int(float(100 - tilt) * SUNBLIND_TILT_CLOSED / 100)
        self.hass.async_add_executor_job(
            self._hub.sunblinds[self.idx].set_rotation, rotation
        )
