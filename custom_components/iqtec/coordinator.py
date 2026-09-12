"""DataUpdate Coordinator for IQtec platform."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
import logging

from piqtec import CalendarState, Controller, IQtecError, State
from piqtec.type_helpers import RequestSet

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CALENDAR_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .monitor import PollRecord, RequestMonitor

_LOGGER = logging.getLogger(__name__)


@dataclass
class IQTecData:
    """Runtime dataclass."""

    coordinator: IqTecCoordinator
    calendars: IqTecCalendarCoordinator
    monitor: RequestMonitor
    cover_use_short_tilt: bool
    correction_time: int


type IqTecConfigEntry = ConfigEntry[IQTecData]


@dataclass
class PollPlan:
    """What one poll reads, decided in the event loop and executed in a thread."""

    request: RequestSet = field(default_factory=RequestSet)
    units: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    previous: State | None = None

    @property
    def paths(self) -> list[str]:
        """The controller addresses this poll asks for."""
        return [getter.path for getter in self.request.getters]


class IqTecCoordinator(DataUpdateCoordinator[State]):
    """IQtec coordinator.

    Until the platforms have finished setting up, every unit is read so entities
    can be built from real data. From then on only what an enabled entity has
    asked for is read: rooms and covers as whole structures, generic variables
    one by one, and nothing at all for the many variables that stay disabled.
    """

    config_entry: IqTecConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: IqTecConfigEntry, hub: Controller, monitor: RequestMonitor
    ) -> None:
        """Initialize IQtec coordinator."""
        seconds = config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            config_entry=config_entry,
            update_interval=timedelta(seconds=seconds),
        )
        self.hub = hub
        self.monitor = monitor
        self._discovering = True
        self._units: set[str] = set()
        self._variables: defaultdict[str, set[str]] = defaultdict(set)
        self._stats_listeners: list[CALLBACK_TYPE] = []

    # -- what to read ------------------------------------------------------

    @property
    def discovering(self) -> bool:
        """Whether polls still read the whole controller."""
        return self._discovering

    @callback
    def async_track_unit(self, idx: str) -> CALLBACK_TYPE:
        """Keep a room or sunblind in the poll while an entity needs it."""
        self._units.add(idx)

        @callback
        def untrack() -> None:
            self._units.discard(idx)

        return untrack

    @callback
    def async_track_variable(self, device_idx: str, name: str) -> CALLBACK_TYPE:
        """Keep one generic variable in the poll while an entity needs it."""
        self._variables[device_idx].add(name)

        @callback
        def untrack() -> None:
            names = self._variables.get(device_idx)
            if names is not None:
                names.discard(name)
                if not names:
                    del self._variables[device_idx]

        return untrack

    @callback
    def async_finish_discovery(self) -> None:
        """Switch from reading everything to reading what is tracked."""
        self._discovering = False
        plan = self.plan()
        _LOGGER.info(
            "Polling %d rooms and covers and %d variables of %d devices in %d addresses every %s",
            len(plan.units),
            sum(len(names) for names in self._variables.values()),
            len(plan.devices),
            len(plan.paths),
            self.update_interval,
        )

    @callback
    def plan(self) -> PollPlan:
        """Assemble the next poll from what entities have registered."""
        plan = PollPlan(previous=self.data)
        for idx in sorted(self._units):
            unit = self.hub.rooms.get(idx) or self.hub.sunblinds.get(idx)
            if unit is None:
                continue
            plan.request = plan.request + unit.get_request
            plan.units.append(idx)
        for device_idx, names in sorted(self._variables.items()):
            device = self.hub.devices.get(device_idx)
            if device is None:
                continue
            apis = device.all_apis
            wanted = [apis[name] for name in sorted(names) if name in apis]
            if not wanted:
                continue
            # A structure read returns the whole structure, so ask for the
            # variables one by one unless every one of them is wanted anyway.
            if len(wanted) == len(apis):
                plan.request = plan.request + device.get_request
            else:
                for api in wanted:
                    plan.request = plan.request + api.get_request()
            plan.devices.append(device_idx)
        return plan

    # -- reading -----------------------------------------------------------

    def _read(self, plan: PollPlan) -> State:
        """Fetch the planned addresses and fold them into the last known state."""
        responses = self.hub.api_call(plan.request) if plan.request else {}
        previous = plan.previous or State()
        rooms, sunblinds, devices = dict(previous.rooms), dict(previous.sunblinds), dict(previous.devices)
        for idx in plan.units:
            if (room := self.hub.rooms.get(idx)) is not None:
                rooms[idx] = room.parse_state(responses)
            elif (sunblind := self.hub.sunblinds.get(idx)) is not None:
                sunblinds[idx] = sunblind.parse_state(responses)
        for idx in plan.devices:
            devices[idx] = self.hub.devices[idx].parse_state(responses)
        return State(system=previous.system, rooms=rooms, sunblinds=sunblinds, devices=devices)

    async def _async_update_data(self) -> State:
        """Fetch the status data from IQtec."""
        record = PollRecord()
        error: BaseException | None = None
        try:
            if self._discovering:
                return await self.hass.async_add_executor_job(self.monitor.run, record, self.hub.update)
            plan = self.plan()
            return await self.hass.async_add_executor_job(self.monitor.run, record, self._read, plan)
        except IQtecError as err:
            error = err
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            error = err
            raise
        finally:
            self.monitor.stats.last_poll = record
            self.monitor.poll_finished(error)
            self._async_notify_stats()

    # -- statistics --------------------------------------------------------

    @callback
    def async_add_stats_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Be told after every poll, failed ones included."""
        self._stats_listeners.append(listener)

        @callback
        def remove() -> None:
            self._stats_listeners.remove(listener)

        return remove

    @callback
    def _async_notify_stats(self) -> None:
        for listener in list(self._stats_listeners):
            listener()


class IqTecCalendarCoordinator(DataUpdateCoordinator[dict[str, CalendarState]]):
    """Calendars, polled slowly because only an editor changes them."""

    config_entry: IqTecConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: IqTecConfigEntry, hub: Controller, monitor: RequestMonitor
    ) -> None:
        """Initialize the calendar coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} calendars ({config_entry.unique_id})",
            config_entry=config_entry,
            update_interval=CALENDAR_SCAN_INTERVAL,
        )
        self.hub = hub
        self.monitor = monitor

    async def _async_update_data(self) -> dict[str, CalendarState]:
        """Fetch every calendar from the controller."""
        record = PollRecord()
        error: BaseException | None = None
        try:
            return await self.hass.async_add_executor_job(self.monitor.run, record, self.hub.read_calendars)
        except IQtecError as err:
            error = err
            raise UpdateFailed(f"Error reading calendars: {err}") from err
        except Exception as err:
            error = err
            raise
        finally:
            self.monitor.poll_finished(error)
