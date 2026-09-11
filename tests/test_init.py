"""Tests for setting up and tearing down the IQtec integration."""

from unittest.mock import patch

from piqtec import IQtecConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iqtec.const import CONF_CORRECTION_TIMEOUT, CONF_COVER_USE_SHORT_TILT, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

ENTRY_DATA = {
    CONF_HOST: "iqtec.home",
    CONF_COVER_USE_SHORT_TILT: False,
    CONF_CORRECTION_TIMEOUT: 24,
}


def _entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="iqtec_platform_iqtec.home")


async def test_setup_and_unload(hass: HomeAssistant, mock_controller) -> None:
    """The entry loads, creates entities and unloads cleanly."""
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("climate.obyvak") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    mock_controller.close.assert_called_once()


async def test_setup_retries_when_unreachable(hass: HomeAssistant) -> None:
    """A controller that cannot be reached leaves the entry retrying."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch("custom_components.iqtec.Controller", side_effect=IQtecConnectionError("boom")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unique_ids_are_migrated(hass: HomeAssistant, mock_controller) -> None:
    """Entities registered under the old global unique id are moved."""
    from homeassistant.helpers import entity_registry as er

    entry = _entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "climate", DOMAIN, f"{DOMAIN}-R1", config_entry=entry, suggested_object_id="old_room"
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(old.entity_id).unique_id == f"{entry.entry_id}-R1"
