"""IQtec Selects."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ON_OFF_AUTO
from .coordinator import IqTecConfigEntry
from .entity import IqTecOnOffAutoVariable

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entries."""
    coordinator = config_entry.runtime_data.coordinator

    async_add_entities(
        IqTecOnOffAuto(coordinator, idx, device_idx)
        for device_idx, device in coordinator.hub.devices.items()
        for idx, api in device.switch_apis.items()
        if api.typ == "OnOffAuto"
    )


class IqTecOnOffAuto(IqTecOnOffAutoVariable, SelectEntity):
    """A writable On/Off/Auto variable."""

    _source = "switches"

    @property
    def current_option(self) -> str | None:
        """Currently selected option."""
        return self.position

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        await self._async_write(ON_OFF_AUTO[option])
