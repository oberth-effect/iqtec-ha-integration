"""Tests for the entities built from generic data.xml variables."""

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.iqtec.const import CONF_CORRECTION_TIMEOUT, CONF_COVER_USE_SHORT_TILT, DOMAIN
from homeassistant.components.number import ATTR_VALUE, DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN, SERVICE_TURN_ON
from homeassistant.config_entries import RELOAD_AFTER_UPDATE_DELAY
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

# Addresses of the fake controller in conftest.py.
SET_HEAT_ADDRESS = "1/1/0"
SUMMER_ADDRESS = "1/1/2"
METEO_LEVEL_ADDRESS = "1/8/1"

ENTRY_DATA = {
    CONF_HOST: "iqtec.home",
    CONF_COVER_USE_SHORT_TILT: False,
    CONF_CORRECTION_TIMEOUT: 24,
}


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="iqtec_platform_iqtec.home")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def enable(hass: HomeAssistant, entry: MockConfigEntry, *wanted: tuple[str, str]) -> list[str]:
    """Enable disabled-by-default variable entities and wait for the reload that follows."""
    registry = er.async_get(hass)
    entity_ids = []
    for domain, idx in wanted:
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}-{idx}")
        assert entity_id, f"no {domain} entity for {idx}"
        assert registry.async_get(entity_id).disabled
        registry.async_update_entity(entity_id, disabled_by=None)
        entity_ids.append(entity_id)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=RELOAD_AFTER_UPDATE_DELAY + 1))
    await hass.async_block_till_done(wait_background_tasks=True)
    return entity_ids


async def test_a_manual_switch_is_a_switch_despite_its_numeric_type(hass: HomeAssistant, mock_controller) -> None:
    """SET_HEAT is a byte in data.xml but only ever 0 or 1, so it is a switch and not a number."""
    entry = await setup_entry(hass)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}-SYSTEM.SET_HEAT") is None
    # Like every other discovered variable it waits to be enabled.
    (switch,) = await enable(hass, entry, ("switch", "SYSTEM.SET_HEAT"))
    assert hass.states.get(switch).state == "off"

    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: switch}, blocking=True)

    assert mock_controller.values[SET_HEAT_ADDRESS] == "1"
    assert hass.states.get(switch).state == "on"


async def test_on_off_variables_are_switches(hass: HomeAssistant, mock_controller) -> None:
    """A writable OnOff variable is a switch by type, disabled until asked for like the rest."""
    entry = await setup_entry(hass)
    (switch,) = await enable(hass, entry, ("switch", "SYSTEM.Summer"))
    assert hass.states.get(switch).state == "off"

    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: switch}, blocking=True)

    assert mock_controller.values[SUMMER_ADDRESS] == "1"
    assert hass.states.get(switch).state == "on"


async def test_humidity_variables_are_humidity_entities(hass: HomeAssistant, mock_controller) -> None:
    """A Humidity variable is a percentage, not a temperature."""
    entry = await setup_entry(hass)
    (sensor,) = await enable(hass, entry, ("sensor", "METEO.Humidity"))

    state = hass.states.get(sensor)
    assert state.state == "45.0"
    assert state.attributes["device_class"] == "humidity"
    assert state.attributes["unit_of_measurement"] == PERCENTAGE


async def test_whole_number_variables_take_whole_numbers_only(hass: HomeAssistant, mock_controller) -> None:
    """A word is a whole number with the bounds of a word; a fraction is the caller's mistake."""
    entry = await setup_entry(hass)
    (number,) = await enable(hass, entry, ("number", "METEO.Level"))

    state = hass.states.get(number)
    assert state.state == "120"
    assert state.attributes["step"] == 1
    assert (state.attributes["min"], state.attributes["max"]) == (0, 65535)

    # Home Assistant hands over a float; it reaches the controller as a whole number.
    await hass.services.async_call(
        NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: number, ATTR_VALUE: 121}, blocking=True
    )
    assert mock_controller.values[METEO_LEVEL_ADDRESS] == "121"

    with pytest.raises(ServiceValidationError, match="whole number"):
        await hass.services.async_call(
            NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: number, ATTR_VALUE: 12.5}, blocking=True
        )
    assert mock_controller.values[METEO_LEVEL_ADDRESS] == "121"
