"""Tests for the commands the climate and cover entities send to the controller."""

from piqtec import IQtecConnectionError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iqtec.const import CONF_CORRECTION_TIMEOUT, CONF_COVER_USE_SHORT_TILT, DOMAIN
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    HVACMode,
)
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN, SERVICE_OPEN_COVER
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

# Addresses of the fake controller in conftest.py.
ROOM_MODE_ADDRESS = "1/3/3"
CORRECTION_STATUS_ADDRESS = "1/3/4"
CALENDAR_NUMBER_ADDRESS = "1/3/5"

ENTRY_DATA = {
    CONF_HOST: "iqtec.home",
    CONF_COVER_USE_SHORT_TILT: False,
    CONF_CORRECTION_TIMEOUT: 24,
}

CLIMATE = "climate.obyvak"
CALENDAR_PRESET = "(0) GeneralProfile"


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="iqtec_platform_iqtec.home")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def writes_since(mock_controller, count: int) -> list[list[tuple[str, str]]]:
    """The setters of every request made since the controller had ``count`` requests."""
    return [
        [(setter.path, setter.value) for setter in request.setters]
        for request in mock_controller.requests[count:]
        if request.setters
    ]


async def test_calendars_are_offered_as_presets_without_another_read(hass: HomeAssistant, mock_controller) -> None:
    """The presets come from the calendars already read; nothing else is asked of the controller."""
    await setup_entry(hass)

    presets = hass.states.get(CLIMATE).attributes["preset_modes"]
    assert CALENDAR_PRESET in presets
    assert hass.states.get(CLIMATE).attributes["preset_mode"] == CALENDAR_PRESET


@pytest.mark.parametrize(
    ("hvac_mode", "correction"),
    [(HVACMode.HEAT, "3"), (HVACMode.AUTO, "0")],
)
async def test_mode_and_correction_are_written_together(
    hass: HomeAssistant, mock_controller, hvac_mode: HVACMode, correction: str
) -> None:
    """One request carries both variables, so no poll can see one changed without the other."""
    await setup_entry(hass)
    before = len(mock_controller.requests)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: hvac_mode}, blocking=True
    )
    await hass.async_block_till_done()

    assert writes_since(mock_controller, before) == [
        [(ROOM_MODE_ADDRESS, "0"), (CORRECTION_STATUS_ADDRESS, correction)]
    ]
    assert hass.states.get(CLIMATE).state == hvac_mode


async def test_a_calendar_preset_is_one_request(hass: HomeAssistant, mock_controller) -> None:
    """Choosing a calendar writes the mode and the calendar number in one go."""
    await setup_entry(hass)
    before = len(mock_controller.requests)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: CALENDAR_PRESET},
        blocking=True,
    )

    assert writes_since(mock_controller, before) == [[(ROOM_MODE_ADDRESS, "0"), (CALENDAR_NUMBER_ADDRESS, "0")]]


async def test_off_is_a_single_write(hass: HomeAssistant, mock_controller) -> None:
    """Switching off only touches the room mode."""
    await setup_entry(hass)
    before = len(mock_controller.requests)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF}, blocking=True
    )

    assert writes_since(mock_controller, before) == [[(ROOM_MODE_ADDRESS, "3")]]
    assert hass.states.get(CLIMATE).state == HVACMode.OFF


async def test_a_controller_failure_is_reported_as_such(hass: HomeAssistant, mock_controller) -> None:
    """An unreachable controller surfaces as a Home Assistant error carrying piqtec's message."""
    await setup_entry(hass)
    mock_controller.fail_with = IQtecConnectionError("Cannot reach iqtec.home: timed out")

    with pytest.raises(HomeAssistantError, match="timed out") as raised:
        await hass.services.async_call(COVER_DOMAIN, SERVICE_OPEN_COVER, {ATTR_ENTITY_ID: "cover.okno"}, blocking=True)
    # The controller, not the caller, is at fault.
    assert not isinstance(raised.value, ServiceValidationError)

    with pytest.raises(HomeAssistantError, match="timed out"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT},
            blocking=True,
        )
