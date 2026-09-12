"""Fixtures for the IQtec integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from piqtec import CalendarState, State, SystemState
from piqtec.api.generic import DriverAPI
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


# A tiny data.xml: the system, one room, one sunblind and a pump, each in a
# structure of its own so that structure reads can be told apart by address.
APIS: dict[str, DriverAPI] = {
    api.name: api
    for api in (
        _driver("SYSTEM.SET_HEAT", "OnOff", 1, 0, access="U"),
        _driver("SYSTEM.OutTempearture", "Temperature", 1, 1),
        _driver("R1._RoomName", "string16", 3, 0),
        _driver("R1.ActualTemperature", "Temperature", 3, 1),
        _driver("R1.HeatingEnabled", "bool", 3, 2),
        _driver("R1.RoomMode", "RoomMode", 3, 3, access="U"),
        _driver("R1.CorrectionStatus", "CorrectionStatus", 3, 4, access="U"),
        _driver("R1_SUNBLIND_1.Name", "string16", 4, 0),
        _driver("R1_SUNBLIND_1.Position", "word", 4, 1),
        _driver("R1_SUNBLIND_1.Rotation", "word", 4, 2),
        _driver("R1_SUNBLIND_1.FullTimeTime", "word", 4, 3),
        _driver("R1_SUNBLIND_1.COMMAND", "SUNBLIND_COMMAND", 4, 4, access="U"),
        _driver("PUMP.Out", "bool", 7, 0),
        _driver("PUMP.Speed", "byte", 7, 1, access="U"),
    )
}

VALUES: dict[str, str] = {
    "1/1/0": "0",
    "1/1/1": "12.5",
    "1/3/0": "Obyvak",
    "1/3/1": "21.0",
    "1/3/2": "1",
    "1/3/3": "0",
    "1/3/4": "0",
    "1/4/0": "Okno",
    "1/4/1": "0",
    "1/4/2": "0",
    "1/4/3": "100",
    "1/4/4": "3",
    "1/7/0": "1",
    "1/7/1": "3",
}

SYSTEM_ADDRESS = "1/1/"
ROOM_ADDRESS = "1/3/"
SUNBLIND_ADDRESS = "1/4/"
PUMP_ADDRESS = "1/7/"
SET_HEAT_ADDRESS = "1/1/0"
PUMP_OUT_ADDRESS = "1/7/0"


class FakeController:
    """Behaves like piqtec.Controller over an in-memory variable table.

    The units are the real piqtec classes, so requests and parsing are genuine
    and only the HTTP layer is replaced. Every request set is kept for tests to
    inspect, and ``fail_with`` makes reads raise.
    """

    name = "IQtec Controller"

    def __init__(self, calendars: dict[str, CalendarState]) -> None:
        self.values = dict(VALUES)
        self.requests: list[RequestSet] = []
        self.fail_with: Exception | None = None
        self._calendars = calendars
        self._session = requests.Session()

        self.rooms = {"R1": Room(self, "R1", APIS)}
        self.sunblinds = {"R1_SUNBLIND_1": Sunblind(self, "R1_SUNBLIND_1", APIS)}
        self.devices = {"PUMP": Device(self, "PUMP", APIS), "SYSTEM": Device(self, "SYSTEM", APIS)}
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

    def api_call(self, request_set: RequestSet) -> ResponseSet:
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
        if self.fail_with is not None:
            raise self.fail_with
        return self._calendars

    def get_calendar_names(self) -> list[tuple[str, str | None]]:
        return [(idx, state.name) for idx, state in self.read_calendars().items()]


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
    with (
        patch("custom_components.iqtec.Controller", return_value=controller),
        patch("custom_components.iqtec.config_flow.Controller", return_value=controller),
    ):
        yield controller
