"""Tests for the calendar entity and the set_calendar service."""

from datetime import datetime, timedelta
from unittest.mock import ANY

from piqtec import CalendarLevel, CalendarState, IQtecConnectionError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iqtec.const import (
    CONF_CORRECTION_TIMEOUT,
    CONF_COVER_USE_SHORT_TILT,
    CONF_DISPLAY_TYPES,
    DOMAIN,
    SERVICE_SET_CALENDAR,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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


async def test_set_calendar_gives_a_blank_calendar_its_days(hass: HomeAssistant, mock_controller, calendars) -> None:
    """A calendar the controller reads back empty has no days to inherit from, yet can be written."""
    calendars["_CALENDAR_00"] = CalendarState(name="Blank", temperatures=[14.0, 17.0, 20.0, 27.0, 25.0, 22.0])
    await setup_entry(hass)
    assert hass.states.get(ENTITY).attributes["days"] == []

    days = [{"transitions": [[0, 1], [80, 2]]} for _ in range(8)]
    await hass.services.async_call(DOMAIN, SERVICE_SET_CALENDAR, {"calendar_id": ENTITY, "days": days}, blocking=True)

    written = mock_controller.write_calendar.call_args.args[1]
    assert len(written.days) == 8
    assert not any(day.as_monday for day in written.days)


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


async def test_display_type_defaults_to_the_controller(hass: HomeAssistant, mock_controller) -> None:
    """Without an override, a calendar is shown as the controller types it."""
    await setup_entry(hass)

    attributes = hass.states.get(ENTITY).attributes
    assert attributes["calendar_type"] == "TEMPERATURE"
    assert attributes["display_type"] == "TEMPERATURE"
    assert attributes["levels"] == 3
    assert attributes["level_names"] == ["Nobody", "Night", "Day"]


async def test_display_type_override_changes_levels_and_names(hass: HomeAssistant, mock_controller) -> None:
    """A mistyped calendar can be shown as the on/off schedule it really is."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        options={CONF_DISPLAY_TYPES: {"_CALENDAR_00": "ON_OFF"}},
        unique_id="iqtec_platform_iqtec.home",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    attributes = hass.states.get(ENTITY).attributes
    # What the controller says is kept; what it is shown as is the override.
    assert attributes["calendar_type"] == "TEMPERATURE"
    assert attributes["display_type"] == "ON_OFF"
    assert attributes["levels"] == 2
    assert attributes["level_names"] == ["Off", "Off", "On"]

    # The calendar entity follows the override too.
    calendar = hass.states.get(CALENDAR_ENTITY)
    assert calendar.attributes["message"] in ("On", "Off")


async def test_unknown_display_type_falls_back(hass: HomeAssistant, mock_controller) -> None:
    """A stale or misspelt override does not break the entity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        options={CONF_DISPLAY_TYPES: {"_CALENDAR_00": "NONSENSE"}},
        unique_id="iqtec_platform_iqtec.home",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY).attributes["display_type"] == "TEMPERATURE"


async def test_options_flow_offers_every_calendar(hass: HomeAssistant, mock_controller) -> None:
    """The options flow lists one display type per calendar and stores it."""
    entry = await setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert "calendar_0" in result["data_schema"].schema

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"calendar_0": "on_off"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DISPLAY_TYPES] == {"_CALENDAR_00": "ON_OFF"}
    # Changing the options reloads the entry, so entities pick the change up.
    assert hass.states.get(ENTITY).attributes["display_type"] == "ON_OFF"
