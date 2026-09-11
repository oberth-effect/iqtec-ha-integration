"""IQtec Covers."""

from __future__ import annotations

from typing import Any

from piqtec import SUNBLIND_EXTENDED, SUNBLIND_TILT_CLOSED, SunblindCommand, SunblindState

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import IqTecUnitEntity

PARALLEL_UPDATES = 0

_TILT_FEATURES = (
    CoverEntityFeature.OPEN_TILT
    | CoverEntityFeature.CLOSE_TILT
    | CoverEntityFeature.STOP_TILT
    | CoverEntityFeature.SET_TILT_POSITION
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up cover entries."""
    coordinator = config_entry.runtime_data.coordinator
    short_tilt = config_entry.runtime_data.cover_use_short_tilt
    async_add_entities(IqTecCover(coordinator, idx, short_tilt) for idx in coordinator.hub.sunblinds)


class IqTecCover(IqTecUnitEntity[SunblindState], CoverEntity):
    """IQtec Cover Entity."""

    _attr_device_class = CoverDeviceClass.BLIND

    def __init__(self, coordinator: IqTecCoordinator, idx: str, short_tilt: bool) -> None:
        """Initialise IQtec Cover."""
        super().__init__(coordinator, idx)
        self._short_tilt = short_tilt

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )
        if self.iqtec_state.full_time_time:
            self._attr_supported_features |= _TILT_FEATURES

        room_id = idx.split("_")[0]
        self._attr_device_info = DeviceInfo(manufacturer="IQtec/Kobra", identifiers={(DOMAIN, room_id)})

    @property
    def iqtec_state(self) -> SunblindState:
        """Current sunblind state."""
        return self.coordinator.data.sunblinds[self.idx]

    @property
    def _sunblind(self):
        return self._hub.sunblinds[self.idx]

    @property
    def is_closed(self) -> bool | None:
        """Return if closed."""
        if self.iqtec_state.position is None:
            return None
        return self.iqtec_state.position == SUNBLIND_EXTENDED

    @property
    def current_cover_position(self) -> int | None:
        """Return cover position, inverted: IQtec counts extension, HA openness."""
        if self.iqtec_state.position is None:
            return None
        return round((SUNBLIND_EXTENDED - self.iqtec_state.position) * 100 / SUNBLIND_EXTENDED)

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return tilt position."""
        if self.iqtec_state.rotation is None:
            return None
        return round((SUNBLIND_TILT_CLOSED - self.iqtec_state.rotation) * 100 / SUNBLIND_TILT_CLOSED)

    @property
    def is_closing(self) -> bool:
        """Return cover closing."""
        return bool(self.iqtec_state.out_dn_1 or self.iqtec_state.out_dn_2)

    @property
    def is_opening(self) -> bool:
        """Return cover opening."""
        return bool(self.iqtec_state.out_up_1 or self.iqtec_state.out_up_2)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._async_command(self._sunblind.set_command, SunblindCommand.UP)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        await self._async_command(self._sunblind.set_command, SunblindCommand.DOWN)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self._async_command(self._sunblind.set_command, SunblindCommand.STOP)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = round((100 - kwargs[ATTR_POSITION]) * SUNBLIND_EXTENDED / 100)
        await self._async_command(self._sunblind.set_position, position)

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        """Open the cover tilt."""
        command = SunblindCommand.TILT_OPEN_SHORT if self._short_tilt else SunblindCommand.TILT_OPEN
        await self._async_command(self._sunblind.set_command, command)

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        """Close the cover tilt."""
        await self.async_set_cover_tilt_position(tilt_position=0)

    async def async_stop_cover_tilt(self, **kwargs: Any) -> None:
        """Stop the cover tilt."""
        await self.async_stop_cover()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Move the cover tilt to a specific position."""
        rotation = round((100 - kwargs[ATTR_TILT_POSITION]) * SUNBLIND_TILT_CLOSED / 100)
        await self._async_command(self._sunblind.set_rotation, rotation)
