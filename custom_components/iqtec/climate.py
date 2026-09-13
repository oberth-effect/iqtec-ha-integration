"""IQTec Climate."""

from __future__ import annotations

import logging
from typing import Any

from piqtec import CalendarType, MissingVariableError, RoomCorrectionMode, RoomMode, RoomState
from piqtec.type_helpers import RequestSet

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    PRESET_AWAY,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .calendar_schedule import display_type
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import MANUFACTURER, IqTecUnitEntity, device_identifiers

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

PRESET_ANTIFREEZE = "Anti-Freeze"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up climate entries."""
    data = config_entry.runtime_data
    coordinator = data.coordinator
    # The calendar coordinator has read every calendar already. A room refers
    # to its calendar by the number in the calendar's address. Every calendar is
    # named, so a room can always report the one it is on, but only the
    # temperature ones are offered to choose from: a blind or on/off schedule
    # drives something else entirely. What the user has typed a calendar as
    # decides, not what data.xml declares; that is what the override is for.
    calendars: dict[int, str] = {}
    temperature: set[int] = set()
    for idx, state in (data.calendars.data or {}).items():
        number = coordinator.hub.calendars[idx].index
        calendars[number] = state.name or idx
        if display_type(config_entry, idx, state) is CalendarType.TEMPERATURE:
            temperature.add(number)
    async_add_entities(
        IqTecClimate(coordinator, idx, calendars, temperature, data.correction_time) for idx in coordinator.hub.rooms
    )


class IqTecClimate(IqTecUnitEntity[RoomState], ClimateEntity):
    """IQtec Climate Entity."""

    _attr_supported_features = ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_precision = 0.1
    _attr_target_temperature_step = 0.1
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: IqTecCoordinator,
        idx: str,
        calendars: dict[int, str],
        temperature_calendars: set[int],
        manual_time: int,
    ) -> None:
        """Initialise IQtec Climate."""
        super().__init__(coordinator, idx)
        self._calendars = {number: f"({number}) {name}" for number, name in calendars.items()}
        self._temperature_calendars = temperature_calendars
        self.manual_time = manual_time
        self._attr_device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            identifiers=device_identifiers(coordinator.config_entry, idx),
            name=self.iqtec_state.name or idx,
        )

    @property
    def iqtec_state(self) -> RoomState:
        """Current room state."""
        return self.coordinator.data.rooms[self.idx]

    @property
    def _room(self):
        return self._hub.rooms[self.idx]

    @property
    def current_temperature(self) -> float | None:
        """Current temperature."""
        return self.iqtec_state.actual_temperature

    @property
    def current_humidity(self) -> int | None:
        """Current humidity."""
        humidity = self.iqtec_state.humidity
        return None if humidity is None else round(humidity)

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
            case RoomMode.OFF:
                return HVACMode.OFF
            case RoomMode.CALENDAR:
                if self.iqtec_state.correction_status == RoomCorrectionMode.MANUAL:
                    return HVACMode.HEAT
                return HVACMode.AUTO
            case _:
                return HVACMode.AUTO

    @property
    def preset_mode(self) -> str | None:
        """Current Preset Mode."""
        match self.iqtec_state.room_mode:
            case RoomMode.ANTIFREEZE:
                return PRESET_ANTIFREEZE
            case RoomMode.HOLIDAY:
                return PRESET_AWAY
            case _:
                return self._calendars.get(self.iqtec_state.calendar_number)

    @property
    def preset_modes(self) -> list[str]:
        """Preset Modes List.

        The temperature calendars, plus the one the room is on if that is not
        one of them, so what the entity reports is always in the list it offers.
        """
        in_use = self.iqtec_state.calendar_number
        return [
            *(
                name
                for number, name in self._calendars.items()
                if number in self._temperature_calendars or number == in_use
            ),
            PRESET_AWAY,
            PRESET_ANTIFREEZE,
        ]

    @property
    def target_temperature(self) -> float | None:
        """Current target temperature."""
        return self.iqtec_state.requested_temperature

    def _write_room(self, values: dict[str, Any]) -> None:
        """Write several room variables in one request.

        The controller applies them in order, and the poll that follows never
        sees the mode changed but the correction not yet, or the other way round.
        """
        request = RequestSet()
        for field_name, value in values.items():
            api = self._room.apis.get(field_name)
            if api is None:
                raise MissingVariableError(f"{self.idx} has no variable {field_name!r}")
            request = request + api.set_request(value)
        self._hub.api_call(request)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        match hvac_mode:
            case HVACMode.OFF:
                await self._async_command(self._room.set_room_mode, RoomMode.OFF)
            case HVACMode.HEAT:
                await self._async_command(
                    self._write_room,
                    {"room_mode": int(RoomMode.CALENDAR), "correction_status": int(RoomCorrectionMode.MANUAL)},
                )
            case HVACMode.AUTO:
                await self._async_command(
                    self._write_room,
                    {"room_mode": int(RoomMode.CALENDAR), "correction_status": int(RoomCorrectionMode.NONE)},
                )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        if preset_mode == PRESET_AWAY:
            await self._async_command(self._room.set_room_mode, RoomMode.HOLIDAY)
        elif preset_mode == PRESET_ANTIFREEZE:
            await self._async_command(self._room.set_room_mode, RoomMode.ANTIFREEZE)
        else:
            calendars = {name: number for number, name in self._calendars.items()}
            if preset_mode not in calendars:
                _LOGGER.warning("Unknown preset %s for %s", preset_mode, self.idx)
                return
            await self._async_command(
                self._write_room, {"room_mode": int(RoomMode.CALENDAR), "calendar_number": calendars[preset_mode]}
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs[ATTR_TEMPERATURE]
        await self._async_command(self._room.set_manual_temperature, temperature, self.manual_time)
