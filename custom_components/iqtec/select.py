"""IQtec Selects."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IqTecConfigEntry
from .entity import IqTecVariableEntity

PARALLEL_UPDATES = 0

_ON_OFF_AUTO = {0: "off", 1: "on", 2: "auto"}


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


class IqTecOnOffAuto(IqTecVariableEntity, SelectEntity):
    """IQtec OnOffAuto Entity."""

    _source = "switches"
    _attr_options = list(_ON_OFF_AUTO.values())

    @property
    def current_option(self) -> str | None:
        """Currently selected option."""
        return _ON_OFF_AUTO.get(self.raw_value)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        value = next(key for key, name in _ON_OFF_AUTO.items() if name == option)
        await self._async_write(value)
