"""Fixtures for the IQtec integration tests."""

from __future__ import annotations

from contextlib import contextmanager
import threading
import time
from unittest.mock import MagicMock, patch

from piqtec import CalendarState, State, SystemState
from piqtec.api.generic import DriverAPI
from piqtec.controller import base_url
from piqtec.type_helpers import RequestSet, Response, ResponseSet
from piqtec.unit.calendar import CalendarDay, CalendarEdge
from piqtec.unit.device import Device
from piqtec.unit.room import Room
from piqtec.unit.sunblind import Sunblind
import pytest
import requests

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration in every test."""
    return


def _driver(name: str, typ: str, structure_id: int, offset: int, access: str = "u") -> DriverAPI:
    return DriverAPI(
        name=name, access=access, param=False, typ=typ, structure_id=structure_id, offset=offset, mask=None
    )


# A tiny data.xml: the system, one room, one sunblind, a pump and a weather
# probe, each in a structure of its own so that structure reads can be told
# apart by address. SET_HEAT is a byte, as on the real controller, although it
# only ever holds 0 or 1.
APIS: dict[str, DriverAPI] = {
    api.name: api
    for api in (
        _driver("SYSTEM.SET_HEAT", "byte", 1, 0, access="U"),
        _driver("SYSTEM.OutTempearture", "Temperature", 1, 1),
        _driver("SYSTEM.Summer", "OnOff", 1, 2, access="U"),
        _driver("R1._RoomName", "string16", 3, 0),
        _driver("R1.ActualTemperature", "Temperature", 3, 1),
        _driver("R1.HeatingEnabled", "bool", 3, 2),
        _driver("R1.RoomMode", "RoomMode", 3, 3, access="U"),
        _driver("R1.CorrectionStatus", "CorrectionStatus", 3, 4, access="U"),
        _driver("R1.CalendarNumber", "CalendarIndex", 3, 5, access="U"),
        _driver("R1_SUNBLIND_1.Name", "string16", 4, 0),
        _driver("R1_SUNBLIND_1.Position", "word", 4, 1),
        _driver("R1_SUNBLIND_1.Rotation", "word", 4, 2),
        _driver("R1_SUNBLIND_1.FullTimeTime", "word", 4, 3),
        _driver("R1_SUNBLIND_1.COMMAND", "SUNBLIND_COMMAND", 4, 4, access="U"),
        _driver("R1_SUNBLIND_1.OutUP_1", "bool", 4, 5),
        _driver("R1_SUNBLIND_1.OutDN_1", "bool", 4, 6),
        _driver("PUMP.Out", "bool", 7, 0),
        _driver("PUMP.Speed", "byte", 7, 1, access="U"),
        _driver("METEO.Humidity", "Humidity", 8, 0),
        _driver("METEO.Level", "word", 8, 1, access="U"),
    )
}

VALUES: dict[str, str] = {
    "1/1/0": "0",
    "1/1/1": "12.5",
    "1/1/2": "0",
    "1/3/0": "Obyvak",
    "1/3/1": "21.0",
    "1/3/2": "1",
    "1/3/3": "0",
    "1/3/4": "0",
    "1/3/5": "0",
    "1/4/0": "Okno",
    "1/4/1": "0",
    "1/4/2": "0",
    "1/4/3": "100",
    "1/4/4": "3",
    "1/4/5": "0",
    "1/4/6": "0",
    "1/7/0": "1",
    "1/7/1": "3",
    "1/8/0": "45.0",
    "1/8/1": "120",
}

SYSTEM_ADDRESS = "1/1/"
ROOM_ADDRESS = "1/3/"
SUNBLIND_ADDRESS = "1/4/"
PUMP_ADDRESS = "1/7/"
METEO_ADDRESS = "1/8/"
SET_HEAT_ADDRESS = "1/1/0"
PUMP_OUT_ADDRESS = "1/7/0"
METEO_LEVEL_ADDRESS = "1/8/1"


class FakeController:
    """Behaves like piqtec.Controller over an in-memory variable table.

    The units are the real piqtec classes, so requests and parsing are genuine
    and only the HTTP layer is replaced. Every request set is kept for tests to
    inspect, and ``fail_with`` makes reads raise.
    """

    name = "IQtec Controller"

    def __init__(self, calendars: dict[str, CalendarState]) -> None:
        self.host = "iqtec.home"
        self.values = dict(VALUES)
        self.requests: list[RequestSet] = []
        self.fail_with: Exception | None = None
        self._calendars = calendars
        self._session = requests.Session()
        # Concurrency bookkeeping: how many callers are talking to the
        # controller right now, and the most there ever were at once.
        self.slow_by = 0.0
        self.calls = 0
        self.max_concurrent = 0
        self._active = 0
        self._active_lock = threading.Lock()

        self.rooms = {"R1": Room(self, "R1", APIS)}
        self.sunblinds = {"R1_SUNBLIND_1": Sunblind(self, "R1_SUNBLIND_1", APIS)}
        self.devices = {
            "METEO": Device(self, "METEO", APIS),
            "PUMP": Device(self, "PUMP", APIS),
            "SYSTEM": Device(self, "SYSTEM", APIS),
        }
        self.calendars = {"_CALENDAR_00": MagicMock(index=0)}

        self.write_calendar = MagicMock()
        self.close = MagicMock()

    def __enter__(self) -> FakeController:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    @property
    def last_paths(self) -> list[str]:
        """Addresses asked for by the most recent request set."""
        return [getter.path for getter in self.requests[-1].getters]

    @contextmanager
    def _talking(self):
        with self._active_lock:
            self._active += 1
            self.calls += 1
            self.max_concurrent = max(self.max_concurrent, self._active)
        try:
            if self.slow_by:
                time.sleep(self.slow_by)
            yield
        finally:
            with self._active_lock:
                self._active -= 1

    def api_call(self, request_set: RequestSet) -> ResponseSet:
        with self._talking():
            return self._api_call(request_set)

    def _api_call(self, request_set: RequestSet) -> ResponseSet:
        self.requests.append(request_set)
        if self.fail_with is not None:
            raise self.fail_with
        responses: ResponseSet = {}
        for getter in request_set.getters:
            if getter.path.endswith("/"):
                for path, value in self.values.items():
                    if path.startswith(getter.path):
                        responses[path] = Response(path=path, value=value)
            elif getter.path in self.values:
                responses[getter.path] = Response(path=getter.path, value=self.values[getter.path])
        for setter in request_set.setters:
            self.values[setter.path] = setter.value
            responses[setter.path] = Response(path=setter.path, value=setter.value)
        return responses

    def update(self) -> State:
        units = [*self.rooms.values(), *self.sunblinds.values(), *self.devices.values()]
        responses = self.api_call(sum((unit.get_request for unit in units), RequestSet()))
        return State(
            system=SystemState(),
            rooms={idx: room.parse_state(responses) for idx, room in self.rooms.items()},
            sunblinds={idx: sunblind.parse_state(responses) for idx, sunblind in self.sunblinds.items()},
            devices={idx: device.parse_state(responses) for idx, device in self.devices.items()},
        )

    def read_calendars(self) -> dict[str, CalendarState]:
        with self._talking():
            if self.fail_with is not None:
                raise self.fail_with
            return self._calendars


@pytest.fixture
def calendars() -> dict[str, CalendarState]:
    """One real-shaped calendar, parked edges included."""
    edges = [[0, 1], [72, 2], [96, 2], [119, 1], [143, 1], [182, 2], [240, 1], [288, 1]]
    return {
        "_CALENDAR_00": CalendarState(
            name="GeneralProfile",
            temperatures=[14.0, 17.0, 20.0, 27.0, 25.0, 22.0],
            days=[CalendarDay(as_monday=d > 0, edges=[CalendarEdge(t, lv) for t, lv in edges]) for d in range(8)],
            color=0xFFFFFF,
        )
    }


@pytest.fixture
def mock_controller(calendars: dict[str, CalendarState]):
    """Patch the piqtec Controller everywhere the integration constructs one."""
    controller = FakeController(calendars)

    def connect(host: str, *args, **kwargs) -> FakeController:
        # Like piqtec, accept a scheme and a trailing slash but report the bare host.
        controller.host = base_url("http", host).partition("://")[2]
        return controller

    with (
        patch("custom_components.iqtec.Controller", side_effect=connect),
        patch("custom_components.iqtec.config_flow.Controller", side_effect=connect),
    ):
        yield controller
