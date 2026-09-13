"""Tests for setting up and tearing down the IQtec integration."""

from unittest.mock import patch

from piqtec import IQtecConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iqtec.const import CONF_CORRECTION_TIMEOUT, CONF_COVER_USE_SHORT_TILT, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

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
    entry = _entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "climate", DOMAIN, f"{DOMAIN}-R1", config_entry=entry, suggested_object_id="old_room"
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(old.entity_id).unique_id == f"{entry.entry_id}-R1"


async def test_device_identifiers_are_migrated(hass: HomeAssistant, mock_controller) -> None:
    """A device registered under the controller's bare room name is moved to the entry."""
    entry = _entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    old = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "R1")}, name="Old")
    stats = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)})

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(old.id).identifiers == {(DOMAIN, f"{entry.entry_id}-R1")}
    # Already scoped identifiers are left as they are.
    assert registry.async_get(stats.id).identifiers == {(DOMAIN, entry.entry_id)}
    # The room and its cover land on the migrated device rather than on a new one.
    entities = er.async_get(hass)
    assert entities.async_get("climate.obyvak").device_id == old.id
    assert entities.async_get("cover.okno").device_id == old.id


async def test_two_controllers_keep_their_devices_apart(hass: HomeAssistant, mock_controller) -> None:
    """Both controllers call their first room R1, yet each entry gets a device of its own."""
    home = _entry()
    cottage = MockConfigEntry(
        domain=DOMAIN, data={**ENTRY_DATA, CONF_HOST: "iqtec.cottage"}, unique_id="iqtec_platform_iqtec.cottage"
    )
    for entry in (home, cottage):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    devices = [registry.async_get_device(identifiers={(DOMAIN, f"{entry.entry_id}-R1")}) for entry in (home, cottage)]
    assert all(devices)
    assert devices[0].id != devices[1].id
    assert devices[0].config_entries == {home.entry_id}
    assert devices[1].config_entries == {cottage.entry_id}
    assert registry.async_get_device(identifiers={(DOMAIN, "R1")}) is None
