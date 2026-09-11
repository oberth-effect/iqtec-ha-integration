"""Calendar schedules, exposed as entities and edited through a service.

The controller stores a calendar as a fixed 8x8 grid of edges, but both this
entity and the service speak the transition list instead: the 1 to 7 moments a
day changes level. piqtec packs that back into the grid.
"""

from __future__ import annotations

import logging
from typing import Any

from piqtec import TWO_STATE_CALENDARS, CalendarDay, CalendarEdge, CalendarState, CalendarType, IQtecError
import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    ATTR_AS_MONDAY,
    ATTR_CALENDAR_ID,
    ATTR_DAYS,
    ATTR_TEMPERATURES,
    ATTR_TRANSITIONS,
    CONF_DISPLAY_TYPES,
    DOMAIN,
    SERVICE_SET_CALENDAR,
)
from .coordinator import IqTecCalendarCoordinator, IqTecConfigEntry
from .entity import IqTecEntity

_LOGGER = logging.getLogger(__name__)

#: Calendar types that only ever show two states.
TWO_STATE_TYPES = set(TWO_STATE_CALENDARS)

#: Level names per display type, following the controller's own outputs
#: (OutNobody, OutNight, OutDay) and the OEM application's wording.
LEVEL_NAMES: dict[CalendarType, list[str]] = {
    CalendarType.TEMPERATURE: ["Nobody", "Night", "Day"],
    CalendarType.VALUE: ["Nobody", "Night", "Day"],
    CalendarType.BLIND: ["Down", "Tilted", "Up"],
    CalendarType.ON_OFF: ["Off", "Off", "On"],
    CalendarType.ON_OFF2: ["Off", "Off", "On"],
}


def display_type(entry: IqTecConfigEntry, idx: str, state: CalendarState) -> CalendarType:
    """How a calendar should be shown, honouring the user's override."""
    configured = (entry.options.get(CONF_DISPLAY_TYPES) or {}).get(idx)
    if configured:
        try:
            return CalendarType(configured)
        except ValueError:
            _LOGGER.warning("Unknown display type %r for %s", configured, idx)
    return state.calendar_type


def level_names(shown_as: CalendarType) -> list[str]:
    """Labels for levels 0, 1 and 2 under a display type."""
    return LEVEL_NAMES.get(shown_as, LEVEL_NAMES[CalendarType.TEMPERATURE])


DAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "day_8",
]

_TRANSITION_SCHEMA = vol.All(
    [vol.All([vol.Coerce(int)], vol.Length(min=2, max=2))],
    vol.Length(min=1, max=7),
)

_DAY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TRANSITIONS): _TRANSITION_SCHEMA,
        vol.Optional(ATTR_AS_MONDAY): cv.boolean,
    }
)

SET_CALENDAR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CALENDAR_ID): cv.entity_id,
        vol.Optional("name"): vol.All(cv.string, vol.Length(max=16)),
        vol.Optional(ATTR_TEMPERATURES): vol.All([vol.Coerce(float)], vol.Length(min=6, max=6)),
        vol.Optional(ATTR_DAYS): vol.All([_DAY_SCHEMA], vol.Length(min=8, max=8)),
    }
)


def state_as_attributes(
    idx: str, state: CalendarState, index: int, shown_as: CalendarType | None = None
) -> dict[str, Any]:
    """Render the calendar the way the card reads it and the service accepts it."""
    shown_as = shown_as or state.calendar_type
    return {
        "calendar_key": idx,
        "calendar_index": index,
        # What the controller declares, and what it is shown as; they differ
        # when the user has overridden a mistyped calendar.
        "calendar_type": str(state.calendar_type),
        "display_type": str(shown_as),
        "levels": 2 if shown_as in TWO_STATE_TYPES else 3,
        "level_names": level_names(shown_as),
        ATTR_TEMPERATURES: list(state.temperatures),
        "heating_temperatures": state.heating_temperatures,
        "cooling_temperatures": state.cooling_temperatures,
        "color": None if state.color is None else f"#{state.color & 0xFFFFFF:06X}",
        ATTR_DAYS: [
            {
                "name": DAY_NAMES[number],
                ATTR_AS_MONDAY: day.as_monday,
                ATTR_TRANSITIONS: [[edge.time, edge.level] for edge in day.transitions],
            }
            for number, day in enumerate(state.days)
        ],
    }


class IqTecCalendarSensor(IqTecEntity, SensorEntity):
    """One calendar. Its state is the name; the schedule rides in attributes."""

    coordinator: IqTecCalendarCoordinator

    # The schedule is large and changes rarely; keeping it out of the recorder
    # avoids writing the whole thing on every poll.
    _unrecorded_attributes = frozenset(
        {
            ATTR_DAYS,
            ATTR_TEMPERATURES,
            "heating_temperatures",
            "cooling_temperatures",
            "level_names",
        }
    )

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: IqTecCalendarCoordinator, idx: str) -> None:
        """Initialise a calendar entity."""
        super().__init__(coordinator, idx)
        self._attr_name = f"Calendar {coordinator.hub.calendars[idx].index}"
        self._attr_device_info = DeviceInfo(
            manufacturer="IQtec/Kobra",
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}-calendars")},
            name="IQtec Calendars",
        )

    @property
    def iqtec_state(self) -> CalendarState | None:
        """Current calendar, or None if it has not been read."""
        return (self.coordinator.data or {}).get(self.idx)

    @property
    def available(self) -> bool:
        """Whether the calendar has been read."""
        return super().available and self.iqtec_state is not None

    @property
    def native_value(self) -> str | None:
        """The calendar name."""
        state = self.iqtec_state
        return state.name if state else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The full schedule, as the editor card consumes it."""
        state = self.iqtec_state
        if state is None:
            return {}
        entry = self.coordinator.config_entry
        return state_as_attributes(
            self.idx,
            state,
            self.coordinator.hub.calendars[self.idx].index,
            display_type(entry, self.idx, state),
        )


async def _async_set_calendar(hass: HomeAssistant, call: ServiceCall) -> None:
    """Apply an edited schedule to the controller."""
    entity_id = call.data[ATTR_CALENDAR_ID]
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.platform != DOMAIN:
        raise ServiceValidationError(f"{entity_id} is not an IQtec calendar")

    config_entry: IqTecConfigEntry | None = hass.config_entries.async_get_entry(entry.config_entry_id)
    if config_entry is None or not hasattr(config_entry, "runtime_data"):
        raise ServiceValidationError(f"The integration owning {entity_id} is not loaded")

    coordinator = config_entry.runtime_data.calendars
    idx = (entry.unique_id or "").removeprefix(f"{entry.config_entry_id}-")
    current = (coordinator.data or {}).get(idx)
    if current is None:
        raise ServiceValidationError(f"Calendar {idx} has not been read yet")

    state = CalendarState(
        name=call.data.get("name", current.name),
        temperatures=list(call.data.get(ATTR_TEMPERATURES, current.temperatures)),
        days=current.days,
        color=current.color,
        calendar_type=current.calendar_type,
    )

    if ATTR_DAYS in call.data:
        days = []
        for number, raw in enumerate(call.data[ATTR_DAYS]):
            day = CalendarDay(as_monday=raw.get(ATTR_AS_MONDAY, current.days[number].as_monday))
            try:
                day.set_transitions([CalendarEdge(time, level) for time, level in raw[ATTR_TRANSITIONS]])
            except IQtecError as err:
                raise ServiceValidationError(f"{DAY_NAMES[number]}: {err}") from err
            days.append(day)
        state.days = days

    try:
        await hass.async_add_executor_job(coordinator.hub.write_calendar, idx, state)
    except IQtecError as err:
        raise HomeAssistantError(f"Could not save calendar {idx}: {err}") from err

    await coordinator.async_request_refresh()


def async_register_services(hass: HomeAssistant) -> None:
    """Register the calendar services once per Home Assistant run."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_CALENDAR):
        return

    async def handler(call: ServiceCall) -> None:
        await _async_set_calendar(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_SET_CALENDAR, handler, schema=SET_CALENDAR_SCHEMA)
