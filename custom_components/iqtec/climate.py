"""IQTec Climate."""

from __future__ import annotations

import logging
from typing import Any

from piqtec import RoomCorrectionMode, RoomMode, RoomState

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

from .const import DOMAIN
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import IqTecUnitEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

PRESET_ANTIFREEZE = "Anti-Freeze"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up climate entries."""
    coordinator = config_entry.runtime_data.coordinator
    raw_calendars = await hass.async_add_executor_job(coordinator.monitor.exclusive, coordinator.hub.get_calendar_names)
    calendars = {int(idx.removeprefix("_CALENDAR_")): name or idx for idx, name in raw_calendars}
    async_add_entities(
        IqTecClimate(coordinator, idx, calendars, config_entry.runtime_data.correction_time)
        for idx in coordinator.hub.rooms
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
        manual_time: int,
    ) -> None:
        """Initialise IQtec Climate."""
        super().__init__(coordinator, idx)
        self._calendars = {number: f"({number}) {name}" for number, name in calendars.items()}
        self.manual_time = manual_time
        self._attr_device_info = DeviceInfo(
            manufacturer="IQtec/Kobra",
            identifiers={(DOMAIN, idx)},
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
        """Preset Modes List."""
        return [*self._calendars.values(), PRESET_AWAY, PRESET_ANTIFREEZE]

    @property
    def target_temperature(self) -> float | None:
        """Current target temperature."""
        return self.iqtec_state.requested_temperature

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        match hvac_mode:
            case HVACMode.OFF:
                await self._async_command(self._room.set_room_mode, RoomMode.OFF)
            case HVACMode.HEAT:
                await self._async_command(self._room.set_room_mode, RoomMode.CALENDAR)
                await self._async_command(self._room.set_correction_mode, RoomCorrectionMode.MANUAL)
            case HVACMode.AUTO:
                await self._async_command(self._room.set_room_mode, RoomMode.CALENDAR)
                await self._async_command(self._room.set_correction_mode, RoomCorrectionMode.NONE)

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
            await self._async_command(self._room.set_room_mode, RoomMode.CALENDAR)
            await self._async_command(self._room.set_calendar, calendars[preset_mode])

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs[ATTR_TEMPERATURE]
        await self._async_command(self._room.set_manual_temperature, temperature, self.manual_time)
