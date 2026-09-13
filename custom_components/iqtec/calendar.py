"""IQtec schedules projected onto Home Assistant calendars.

This is a read-only view of what a calendar is *programmed* to do, so it can be
used as an automation trigger and read with `calendar.get_events`. It is not what
the heating is necessarily doing: holiday mode, a room switched off and a manual
correction all override the calendar without changing it.

Home Assistant's create/delete-event API takes arbitrary dated events, which
cannot be mapped back onto a weekly grid of at most seven transitions, so editing
stays with the calendar card.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from piqtec import CalendarPeriod, CalendarState, CalendarType

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .calendar_schedule import display_type, level_names
from .coordinator import IqTecCalendarCoordinator, IqTecConfigEntry
from .entity import MANUFACTURER, IqTecEntity, device_identifiers

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a calendar per IQtec schedule."""
    coordinator = config_entry.runtime_data.calendars
    async_add_entities(IqTecScheduleCalendar(coordinator, idx) for idx in coordinator.hub.calendars)


class IqTecScheduleCalendar(IqTecEntity, CalendarEntity):
    """One IQtec schedule, as a calendar of level periods."""

    coordinator: IqTecCalendarCoordinator

    _attr_icon = "mdi:calendar-sync"

    def __init__(self, coordinator: IqTecCalendarCoordinator, idx: str) -> None:
        """Initialise a schedule calendar."""
        super().__init__(coordinator, idx)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-{idx}-schedule"
        state = (coordinator.data or {}).get(idx)
        index = coordinator.hub.calendars[idx].index
        self._attr_name = (state.name if state else None) or f"Calendar {index}"
        self._attr_device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            identifiers=device_identifiers(coordinator.config_entry, "calendars"),
            name="IQtec Calendars",
        )

    @property
    def iqtec_state(self) -> CalendarState | None:
        """Current schedule, or None if it has not been read."""
        return (self.coordinator.data or {}).get(self.idx)

    @property
    def available(self) -> bool:
        """Whether the schedule has been read."""
        return super().available and self.iqtec_state is not None

    @property
    def _shown_as(self):
        state = self.iqtec_state
        return None if state is None else display_type(self.coordinator.config_entry, self.idx, state)

    def _label(self, level: int) -> str:
        shown_as = self._shown_as
        return str(level) if shown_as is None else level_names(shown_as)[level]

    def _as_event(self, period: CalendarPeriod) -> CalendarEvent:
        state = self.iqtec_state
        summary = self._label(period.level)
        if state is not None and self._shown_as is CalendarType.TEMPERATURE:
            heating = state.temperature_for(period.level)
            cooling = state.temperature_for(period.level, cooling=True)
            if heating is not None:
                summary = f"{summary} · {heating} °C"
            description = None if cooling is None else f"Heating {heating} °C, cooling {cooling} °C"
        else:
            description = None
        return CalendarEvent(start=period.start, end=period.end, summary=summary, description=description)

    @property
    def event(self) -> CalendarEvent | None:
        """The period in force right now."""
        state = self.iqtec_state
        if state is None:
            return None
        now = dt_util.now()
        periods = state.periods(now, now + timedelta(days=1))
        return self._as_event(periods[0]) if periods else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Every period between two dates."""
        state = self.iqtec_state
        if state is None:
            return []
        return [self._as_event(period) for period in state.periods(start_date, end_date)]
