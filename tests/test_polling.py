"""Tests for what the integration reads from the controller and how it reports on it."""

from datetime import timedelta

from piqtec import IQtecConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.iqtec.const import (
    BURST_AFTER_COMMAND,
    BURST_INTERVAL,
    BURST_WHILE_MOVING,
    CALENDAR_SCAN_INTERVAL,
    CONF_CORRECTION_TIMEOUT,
    CONF_COVER_USE_SHORT_TILT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.iqtec.diagnostics import async_get_config_entry_diagnostics
from homeassistant.components.climate import ATTR_HVAC_MODE, DOMAIN as CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, HVACMode
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN, SERVICE_CLOSE_COVER
from homeassistant.config_entries import RELOAD_AFTER_UPDATE_DELAY
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_SCAN_INTERVAL, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

# Addresses of the fake controller in conftest.py.
SYSTEM_ADDRESS = "1/1/"
ROOM_ADDRESS = "1/3/"
SUNBLIND_ADDRESS = "1/4/"
PUMP_ADDRESS = "1/7/"
METEO_ADDRESS = "1/8/"
SET_HEAT_ADDRESS = "1/1/0"
PUMP_OUT_ADDRESS = "1/7/0"
SUNBLIND_POSITION_ADDRESS = "1/4/1"
SUNBLIND_OUT_DN_ADDRESS = "1/4/6"

CLIMATE = "climate.obyvak"
COVER = "cover.okno"

# Long enough to reach the next poll of a burst, too short to reach a regular one.
BURST_TICK = BURST_INTERVAL + 1
QUICK_POLLS = BURST_AFTER_COMMAND // BURST_INTERVAL

ENTRY_DATA = {
    CONF_HOST: "iqtec.home",
    CONF_COVER_USE_SHORT_TILT: False,
    CONF_CORRECTION_TIMEOUT: 24,
}


async def setup_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, options=options or {}, unique_id="iqtec_platform_iqtec.home"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def poll(hass: HomeAssistant, seconds: int = DEFAULT_SCAN_INTERVAL + 1) -> None:
    """Let the next scheduled poll happen."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    # The refresh runs as a background task of the config entry.
    await hass.async_block_till_done(wait_background_tasks=True)


def stats_entity(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}-stats-{key}")
    assert entity_id, f"no {key} sensor"
    return entity_id


async def test_first_poll_reads_the_whole_controller(hass: HomeAssistant, mock_controller) -> None:
    """Entities are built from a complete picture."""
    await setup_entry(hass)

    first = {getter.path for getter in mock_controller.requests[0].getters}
    assert {SYSTEM_ADDRESS, ROOM_ADDRESS, SUNBLIND_ADDRESS, PUMP_ADDRESS} <= first


async def test_later_polls_read_only_what_enabled_entities_need(hass: HomeAssistant, mock_controller) -> None:
    """Disabled variables cost the controller nothing."""
    await setup_entry(hass)
    await poll(hass)

    paths = mock_controller.last_paths
    # Climate and cover are enabled by default and read as whole structures.
    assert ROOM_ADDRESS in paths
    assert SUNBLIND_ADDRESS in paths
    # SET_HEAT is the one generic variable enabled out of the box, so it is
    # read on its own; the rest of SYSTEM and the other devices stay untouched.
    assert SET_HEAT_ADDRESS in paths
    assert SYSTEM_ADDRESS not in paths
    assert not any(path.startswith(PUMP_ADDRESS) for path in paths)
    assert not any(path.startswith(METEO_ADDRESS) for path in paths)

    # And the reduced poll still feeds the entities.
    assert hass.states.get("climate.obyvak").attributes["current_temperature"] == 21.0
    assert hass.states.get("cover.okno").state == "open"
    assert hass.states.get("switch.system_set_heat").state == "off"


async def test_enabling_an_entity_adds_its_variable_to_the_poll(hass: HomeAssistant, mock_controller) -> None:
    """Turning a variable entity on in the registry makes it part of the poll."""
    entry = await setup_entry(hass)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}-PUMP.Out")
    assert entity_id
    assert registry.async_get(entity_id).disabled
    assert hass.states.get(entity_id) is None

    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.async_block_till_done()
    # Home Assistant reloads the entry a little after an entity is enabled.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=RELOAD_AFTER_UPDATE_DELAY + 1))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id) is not None

    await poll(hass)
    assert PUMP_OUT_ADDRESS in mock_controller.last_paths
    assert hass.states.get(entity_id).state == "on"


async def test_a_device_with_every_variable_enabled_is_read_as_one_structure(
    hass: HomeAssistant, mock_controller
) -> None:
    """Single variables are cheaper until the whole structure is wanted anyway."""
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    coordinator.async_track_variable("PUMP", "PUMP.Out")
    assert PUMP_OUT_ADDRESS in coordinator.plan().paths
    assert PUMP_ADDRESS not in coordinator.plan().paths

    untrack_speed = coordinator.async_track_variable("PUMP", "PUMP.Speed")
    assert PUMP_ADDRESS in coordinator.plan().paths
    assert PUMP_OUT_ADDRESS not in coordinator.plan().paths

    untrack_speed()
    assert PUMP_OUT_ADDRESS in coordinator.plan().paths
    assert PUMP_ADDRESS not in coordinator.plan().paths


async def test_calendar_and_update_polls_do_not_overlap(hass: HomeAssistant, mock_controller) -> None:
    """Both polls fall due in the same tick, yet the controller sees one at a time."""
    entry = await setup_entry(hass)
    mock_controller.slow_by = 0.02
    calls_before = mock_controller.calls

    # Jumping past the calendar interval fires the 15 s poll and the 5 min
    # calendar poll together, each in its own executor thread.
    await poll(hass, seconds=int(CALENDAR_SCAN_INTERVAL.total_seconds()) + 1)

    assert mock_controller.calls >= calls_before + 2, "both polls must have run"
    assert mock_controller.max_concurrent == 1

    duration = hass.states.get(stats_entity(hass, entry, "poll_duration"))
    assert duration.attributes["waits"] >= 0
    assert duration.attributes["waited"] >= 0


async def test_read_failures_are_counted_and_reported(hass: HomeAssistant, mock_controller) -> None:
    """The monitor sensors keep counting while the controller is unreachable."""
    entry = await setup_entry(hass)
    failed = stats_entity(hass, entry, "failed_polls")
    last_error = stats_entity(hass, entry, "last_error")
    assert hass.states.get(failed).state == "0"
    assert hass.states.get(last_error).state == "unknown"

    mock_controller.fail_with = IQtecConnectionError("Cannot reach iqtec.home: timed out")
    await poll(hass)

    assert hass.states.get("climate.obyvak").state == STATE_UNAVAILABLE
    assert hass.states.get(failed).state == "1"
    assert hass.states.get(failed).attributes["consecutive_failures"] == 1
    assert "timed out" in hass.states.get(last_error).state
    assert hass.states.get(last_error).attributes["at"] is not None

    # A second failure in a row changes no entity data, but the counters must still move.
    await poll(hass)
    assert hass.states.get(failed).state == "2"
    assert hass.states.get(failed).attributes["consecutive_failures"] == 2

    mock_controller.fail_with = None
    await poll(hass)
    assert hass.states.get("climate.obyvak").state != STATE_UNAVAILABLE
    assert hass.states.get(failed).state == "2"
    assert hass.states.get(failed).attributes["consecutive_failures"] == 0


async def test_poll_statistics_are_exposed(hass: HomeAssistant, mock_controller) -> None:
    """Duration and request counters exist and are numbers."""
    entry = await setup_entry(hass)
    await poll(hass)

    duration = hass.states.get(stats_entity(hass, entry, "poll_duration"))
    assert float(duration.state) >= 0
    assert duration.attributes["unit_of_measurement"] == "s"
    requests = hass.states.get(stats_entity(hass, entry, "requests"))
    # The fake controller never touches HTTP, so the tally stays at zero, but
    # the poll counter in its attributes shows the polls went through it.
    assert requests.state == "0"
    assert requests.attributes["polls"] >= 2


async def test_scan_interval_option_changes_the_poll_rate(hass: HomeAssistant, mock_controller) -> None:
    """The options flow stores the interval and the reloaded coordinator uses it."""
    entry = await setup_entry(hass)
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60, "calendar_0": "temperature"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 60
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=60)


async def test_scan_interval_option_is_honoured_at_setup(hass: HomeAssistant, mock_controller) -> None:
    """An entry configured with an interval polls at that interval."""
    entry = await setup_entry(hass, options={CONF_SCAN_INTERVAL: 30})
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=30)

    polls_before = len(mock_controller.requests)
    await poll(hass, seconds=16)
    assert len(mock_controller.requests) == polls_before
    await poll(hass, seconds=31)
    assert len(mock_controller.requests) == polls_before + 1


async def test_diagnostics_describe_the_polling(hass: HomeAssistant, mock_controller) -> None:
    """The download names what is polled, redacts the host and carries the counters."""
    entry = await setup_entry(hass)
    await poll(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert diagnostics["controller"]["rooms"] == ["R1"]
    assert diagnostics["polling"]["discovering"] is False
    assert diagnostics["polling"]["scan_interval"] == DEFAULT_SCAN_INTERVAL
    assert diagnostics["polling"]["burst_interval"] == BURST_INTERVAL
    assert diagnostics["polling"]["burst_polls_left"] == 0
    assert diagnostics["polling"]["current_interval"] == DEFAULT_SCAN_INTERVAL
    assert ROOM_ADDRESS in diagnostics["polling"]["addresses"]
    assert diagnostics["polling"]["units"] == ["R1", "R1_SUNBLIND_1"]
    assert diagnostics["stats"]["polls"] >= 2
    assert diagnostics["stats"]["failed_polls"] == 0


async def test_a_command_is_followed_by_a_burst_of_quick_polls(hass: HomeAssistant, mock_controller) -> None:
    """After a command the controller is read every few seconds for a while, then at the usual pace again."""
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    await poll(hass)
    # Nothing is due within a burst tick while nothing has happened.
    idle = len(mock_controller.requests)
    await poll(hass, seconds=BURST_TICK)
    assert len(mock_controller.requests) == idle

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF}, blocking=True
    )
    await hass.async_block_till_done()
    # The command itself and the read that follows it straight away.
    assert len(mock_controller.requests) == idle + 2
    assert coordinator.update_interval == timedelta(seconds=BURST_INTERVAL)

    # Diagnostics keep reporting the configured interval next to the burst.
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["polling"]["scan_interval"] == DEFAULT_SCAN_INTERVAL
    assert diagnostics["polling"]["current_interval"] == BURST_INTERVAL
    assert diagnostics["polling"]["burst_polls_left"] == QUICK_POLLS - 1

    for n in range(1, QUICK_POLLS + 1):
        await poll(hass, seconds=BURST_TICK)
        assert len(mock_controller.requests) == idle + 2 + n, f"quick poll {n} did not happen"

    # The burst is over: nothing within a tick, the regular poll on time.
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)
    await poll(hass, seconds=BURST_TICK)
    assert len(mock_controller.requests) == idle + 2 + QUICK_POLLS
    await poll(hass)
    assert len(mock_controller.requests) == idle + 3 + QUICK_POLLS


async def test_a_failed_poll_ends_the_burst(hass: HomeAssistant, mock_controller) -> None:
    """An unreachable controller is not asked more often for it."""
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator
    await hass.services.async_call(COVER_DOMAIN, SERVICE_CLOSE_COVER, {ATTR_ENTITY_ID: COVER}, blocking=True)
    assert coordinator.update_interval == timedelta(seconds=BURST_INTERVAL)

    mock_controller.fail_with = IQtecConnectionError("Cannot reach iqtec.home: timed out")
    await poll(hass, seconds=BURST_TICK)

    assert hass.states.get(COVER).state == STATE_UNAVAILABLE
    assert coordinator.burst_polls_left == 0
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def test_a_moving_cover_keeps_the_burst_going(hass: HomeAssistant, mock_controller) -> None:
    """The quick polls last as long as the blind moves, and a little beyond."""
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    await hass.services.async_call(COVER_DOMAIN, SERVICE_CLOSE_COVER, {ATTR_ENTITY_ID: COVER}, blocking=True)
    # The motor runs for longer than the command's own burst would cover.
    mock_controller.values[SUNBLIND_OUT_DN_ADDRESS] = "1"
    for step in range(1, QUICK_POLLS + 4):
        mock_controller.values[SUNBLIND_POSITION_ADDRESS] = str(100 * step)
        before = len(mock_controller.requests)
        await poll(hass, seconds=BURST_TICK)
        assert len(mock_controller.requests) == before + 1, f"no quick poll while moving, step {step}"
        assert hass.states.get(COVER).state == "closing"

    # The blind stops: the quick polls run on for a moment, then the regular pace returns.
    mock_controller.values[SUNBLIND_OUT_DN_ADDRESS] = "0"
    mock_controller.values[SUNBLIND_POSITION_ADDRESS] = "1000"
    await poll(hass, seconds=BURST_TICK)
    assert hass.states.get(COVER).state == "closed"
    for _ in range(BURST_WHILE_MOVING // BURST_INTERVAL):
        await poll(hass, seconds=BURST_TICK)
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)
    before = len(mock_controller.requests)
    await poll(hass, seconds=BURST_TICK)
    assert len(mock_controller.requests) == before


async def test_a_cover_without_motor_outputs_is_judged_by_its_position(hass: HomeAssistant, mock_controller) -> None:
    """An installation that hides the outputs still gets quick polls while the position changes."""
    sunblind = mock_controller.sunblinds["R1_SUNBLIND_1"]
    del sunblind.apis["out_up_1"], sunblind.apis["out_dn_1"]
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data.coordinator

    await hass.services.async_call(COVER_DOMAIN, SERVICE_CLOSE_COVER, {ATTR_ENTITY_ID: COVER}, blocking=True)
    for step in range(1, QUICK_POLLS + 4):
        mock_controller.values[SUNBLIND_POSITION_ADDRESS] = str(100 * step)
        before = len(mock_controller.requests)
        await poll(hass, seconds=BURST_TICK)
        assert len(mock_controller.requests) == before + 1, f"no quick poll while moving, step {step}"

    # Without the outputs Home Assistant never sees it closing, only the position on its way.
    assert hass.states.get(COVER).state == "open"
    assert hass.states.get(COVER).attributes["current_position"] == 100 - 10 * (QUICK_POLLS + 3)
    assert coordinator.burst_polls_left == BURST_WHILE_MOVING // BURST_INTERVAL
