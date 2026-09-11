"""Tests for the calendar entity and the set_calendar service."""

from datetime import datetime, timedelta
from unittest.mock import ANY

from piqtec import CalendarLevel, IQtecConnectionError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iqtec.const import (
    CONF_CORRECTION_TIMEOUT,
    CONF_COVER_USE_SHORT_TILT,
    DOMAIN,
    SERVICE_SET_CALENDAR,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

ENTRY_DATA = {
    CONF_HOST: "iqtec.home",
    CONF_COVER_USE_SHORT_TILT: False,
    CONF_CORRECTION_TIMEOUT: 24,
}

ENTITY = "sensor.calendar_0"


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="iqtec_platform_iqtec.home")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_calendar_entity_exposes_the_schedule(hass: HomeAssistant, mock_controller) -> None:
    """The name is the state and the transitions ride in attributes."""
    await setup_entry(hass)

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == "GeneralProfile"
    assert state.attributes["calendar_type"] == "TEMPERATURE"
    assert state.attributes["levels"] == 3
    assert state.attributes["temperatures"] == [14.0, 17.0, 20.0, 27.0, 25.0, 22.0]

    days = state.attributes["days"]
    assert len(days) == 8
    # Parked edges are not transitions.
    assert days[0]["transitions"] == [[0, 1], [72, 2], [119, 1], [182, 2], [240, 1]]


async def test_set_calendar_writes_transitions(hass: HomeAssistant, mock_controller) -> None:
    """An edited schedule reaches the controller as a full calendar."""
    await setup_entry(hass)

    days = [{"transitions": [[0, 1], [80, 2], [250, 0]], "as_monday": False} for _ in range(8)]
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_CALENDAR,
        {"calendar_id": ENTITY, "name": "Weekdays", "days": days},
        blocking=True,
    )

    mock_controller.write_calendar.assert_called_once_with("_CALENDAR_00", ANY)
    written = mock_controller.write_calendar.call_args.args[1]
    assert written.name == "Weekdays"
    assert [[e.time, e.level] for e in written.days[0].transitions] == [[0, 1], [80, 2], [250, 0]]
    # The grid the controller wants is always full.
    assert all(len(day.edges) == 8 for day in written.days)


async def test_set_calendar_keeps_untouched_fields(hass: HomeAssistant, mock_controller) -> None:
    """Omitted fields keep their current value."""
    await setup_entry(hass)

    await hass.services.async_call(
        DOMAIN, SERVICE_SET_CALENDAR, {"calendar_id": ENTITY, "name": "Renamed"}, blocking=True
    )

    written = mock_controller.write_calendar.call_args.args[1]
    assert written.name == "Renamed"
    assert written.temperatures == [14.0, 17.0, 20.0, 27.0, 25.0, 22.0]


async def test_set_calendar_updates_setpoints(hass: HomeAssistant, mock_controller) -> None:
    """Setpoints can be written on their own."""
    await setup_entry(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_CALENDAR,
        {"calendar_id": ENTITY, "temperatures": [15, 18, 21, 27, 25, 22]},
        blocking=True,
    )

    written = mock_controller.write_calendar.call_args.args[1]
    assert written.temperatures == [15.0, 18.0, 21.0, 27.0, 25.0, 22.0]


async def test_set_calendar_rejects_a_schedule_the_controller_would_refuse(
    hass: HomeAssistant, mock_controller
) -> None:
    """A day that does not start at midnight is refused before any write."""
    await setup_entry(hass)

    days = [{"transitions": [[10, 1], [80, 2]]} for _ in range(8)]
    with pytest.raises(ServiceValidationError, match="midnight"):
        await hass.services.async_call(
            DOMAIN, SERVICE_SET_CALENDAR, {"calendar_id": ENTITY, "days": days}, blocking=True
        )

    mock_controller.write_calendar.assert_not_called()


async def test_set_calendar_rejects_an_unknown_entity(hass: HomeAssistant, mock_controller) -> None:
    """Only IQtec calendars can be targeted."""
    await setup_entry(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_SET_CALENDAR, {"calendar_id": "sensor.somebody_elses"}, blocking=True
        )


async def test_set_calendar_surfaces_a_controller_failure(hass: HomeAssistant, mock_controller) -> None:
    """A write that cannot reach the controller raises, rather than passing silently."""
    await setup_entry(hass)
    mock_controller.write_calendar.side_effect = IQtecConnectionError("boom")

    with pytest.raises(HomeAssistantError, match="Could not save"):
        await hass.services.async_call(
            DOMAIN, SERVICE_SET_CALENDAR, {"calendar_id": ENTITY, "name": "Nope"}, blocking=True
        )


async def test_level_names_are_published(hass: HomeAssistant, mock_controller) -> None:
    """The card labels its lanes from the entity."""
    await setup_entry(hass)

    names = hass.states.get(ENTITY).attributes["level_names"]
    assert names == [level.name.title() for level in CalendarLevel]


CALENDAR_ENTITY = "calendar.generalprofile"


async def test_schedule_calendar_lists_periods(hass: HomeAssistant, mock_controller) -> None:
    """The weekly schedule is projected onto dated events."""
    await setup_entry(hass)

    start = dt_util.start_of_local_day(datetime(2026, 9, 14))  # a Monday
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {"entity_id": CALENDAR_ENTITY, "start_date_time": start, "end_date_time": start + timedelta(days=1)},
        blocking=True,
        return_response=True,
    )
    listed = events[CALENDAR_ENTITY]["events"]
    assert listed, "a day must produce events"
    # Contiguous: the controller is always at some level.
    assert all(a["end"] == b["start"] for a, b in zip(listed, listed[1:], strict=False))
    assert "Day" in listed[1]["summary"]
    assert "20.0" in listed[1]["summary"], "temperature calendars name their setpoint"


async def test_schedule_calendar_has_a_current_event(hass: HomeAssistant, mock_controller) -> None:
    """The entity always has a period in force, so its state stays on."""
    await setup_entry(hass)

    state = hass.states.get(CALENDAR_ENTITY)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["message"]


async def test_schedule_calendar_is_read_only(hass: HomeAssistant, mock_controller) -> None:
    """Creating events is not offered; editing goes through set_calendar."""
    await setup_entry(hass)

    state = hass.states.get(CALENDAR_ENTITY)
    assert not state.attributes.get("supported_features")
