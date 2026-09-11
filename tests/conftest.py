"""Fixtures for the IQtec integration tests."""

from unittest.mock import MagicMock, patch

from piqtec import RoomState, State, SunblindState
from piqtec.unit.device import DeviceState
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration in every test."""
    return


@pytest.fixture
def state() -> State:
    """A small but representative controller state."""
    return State(
        rooms={"R1": RoomState(name="Obyvak", actual_temperature=21.0, heating_enabled=True)},
        sunblinds={"R1_SUNBLIND_1": SunblindState(name="Okno", position=0, rotation=0, full_time_time=100)},
        devices={"PUMP": DeviceState(sensors={"PUMP.Out": True}, switches={})},
    )


@pytest.fixture
def mock_controller(state: State):
    """Patch the piqtec Controller everywhere the integration constructs one."""
    controller = MagicMock()
    controller.name = "IQtec Controller"
    controller.update.return_value = state
    controller.get_calendar_names.return_value = [("_CALENDAR_00", "GeneralProfile")]
    controller.rooms = {"R1": MagicMock()}
    controller.sunblinds = {"R1_SUNBLIND_1": MagicMock()}
    controller.devices = {"PUMP": MagicMock(sensor_apis={}, switch_apis={})}
    controller.__enter__.return_value = controller
    controller.__exit__.return_value = False

    with (
        patch("custom_components.iqtec.Controller", return_value=controller),
        patch("custom_components.iqtec.config_flow.Controller", return_value=controller),
    ):
        yield controller
