"""IQTec Climate."""

import logging
from typing import Any

from piqtec.constants import ROOM_CORR_MODES, ROOM_MODES
from piqtec.unit.room import RoomState

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    PRESET_AWAY,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import IqTecEntity

_LOGGER = logging.getLogger(__name__)


PRESET_ANTIFREEZE = "Anti-Freeze"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Cover entries."""
    coordinator = config_entry.runtime_data.coordinator
    raw_cals = await hass.async_add_executor_job(coordinator.hub.get_calendar_names)
    calendars = {
        int(idx.removeprefix("_CALENDAR_")): calname for idx, calname in raw_cals
    }
    async_add_entities(
        IqTecClimate(coordinator, idx, calendars) for idx in coordinator.hub.rooms
    )


class IqTecClimate(IqTecEntity, ClimateEntity):
    """IQtec Climate Entity."""

    iqtec_state: RoomState
    _calendars: dict[int, str]

    supported_features = (
        ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TARGET_TEMPERATURE
    )

    hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.AUTO,
    ]

    precision = 0.1

    target_temperature_step = 0.1

    temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self, coordinator: IqTecCoordinator, idx: str, calendars: dict[int, str]
    ) -> None:
        """Initialise IQtec Climate."""
        super().__init__(coordinator, idx)
        self.iqtec_state = coordinator.data.rooms[self.idx]

        self._attr_device_info = self._default_device_info | DeviceInfo(
            identifiers={(DOMAIN, idx)}, name=self.iqtec_state.name
        )
        self._calendars = {idx: f"({idx}) {n}" for idx, n in calendars.items()}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.iqtec_state = self.coordinator.data.rooms[self.idx]
        _LOGGER.debug("Updating device: %s", self.idx)
        self.async_write_ha_state()

    # @property
    # def supported_features(self) -> ClimateEntityFeature:
    #     """Supported features."""
    #     return self._base_feautres

    @property
    def current_temperature(self) -> float:
        """Current temperature."""
        return self.iqtec_state.actual_temperature

    @property
    def hvac_action(self) -> HVACAction:
        """Current Climate Action."""
        if self.iqtec_state.heating_enabled:
            return HVACAction.HEATING if self.iqtec_state.heating else HVACAction.IDLE
        return HVACAction.OFF

    @property
    def hvac_mode(self) -> HVACMode:
        """Current Climate Mode."""
        if not self.iqtec_state.heating_enabled:
            return HVACMode.OFF

        match self.iqtec_state.room_mode:
            case ROOM_MODES.OFF:
                return HVACMode.OFF
            case ROOM_MODES.CALENDAR:
                if self.iqtec_state.correction_status == ROOM_CORR_MODES.MANUAL:
                    return HVACMode.HEAT
                return HVACMode.AUTO
            case _:
                return HVACMode.AUTO

    @property
    def preset_mode(self) -> str:
        """Current Preset Mode."""
        match self.iqtec_state.room_mode:
            case ROOM_MODES.ANTIFREEZE:
                return PRESET_ANTIFREEZE
            case ROOM_MODES.HOLIDAY:
                return PRESET_AWAY
            case _:
                return self._calendars.get(
                    self.iqtec_state.calendar_number,
                )

    @property
    def preset_modes(self) -> list[str]:
        """Preset Modes List."""
        return [
            *self._calendars.values(),
            PRESET_AWAY,
            PRESET_ANTIFREEZE,
            PRESET_NONE,
        ]

    @property
    def target_temperature(self) -> float | None:
        """Current target temperature."""
        if type(self.iqtec_state.requested_temperature) is float:
            return self.iqtec_state.requested_temperature
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        match hvac_mode:
            case HVACMode.OFF:
                self.hass.async_add_executor_job(
                    self._hub.rooms[self.idx].set_room_mode, ROOM_MODES.OFF
                )
            case HVACMode.HEAT:
                self.hass.async_add_executor_job(
                    self._hub.rooms[self.idx].set_room_mode, ROOM_MODES.CALENDAR
                )
                self.hass.async_add_executor_job(
                    self._hub.rooms[self.idx].set_correction_mode,
                    ROOM_CORR_MODES.MANUAL,
                )
            case HVACMode.AUTO:
                self.hass.async_add_executor_job(
                    self._hub.rooms[self.idx].set_room_mode, ROOM_MODES.CALENDAR
                )
                self.hass.async_add_executor_job(
                    self._hub.rooms[self.idx].set_correction_mode,
                    ROOM_CORR_MODES.NONE,
                )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        cal_inv = {v: k for k, v in self._calendars.items()}
        if preset_mode == PRESET_AWAY:
            self.hass.async_add_executor_job(
                self._hub.rooms[self.idx].set_room_mode, ROOM_MODES.HOLIDAY
            )
        elif preset_mode == PRESET_ANTIFREEZE:
            self.hass.async_add_executor_job(
                self._hub.rooms[self.idx].set_room_mode, ROOM_MODES.ANTIFREEZE
            )
        elif preset_mode == PRESET_NONE:
            pass
        else:
            self.hass.async_add_executor_job(
                self._hub.rooms[self.idx].set_room_mode, ROOM_MODES.CALENDAR
            )
            self.hass.async_add_executor_job(
                self._hub.rooms[self.idx].set_calendar, cal_inv[preset_mode]
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs[ATTR_TEMPERATURE]
        self.hass.async_add_executor_job(
            self._hub.rooms[self.idx].set_correction_mode,
            ROOM_CORR_MODES.MANUAL,
        )
        self.hass.async_add_executor_job(
            self._hub.rooms[self.idx].set_correction_temperature,
            temp,
        )
