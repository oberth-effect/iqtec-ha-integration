"""IQtec Binary Sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IqTecConfigEntry
from .entity import IqTecVariableEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensor entries."""
    coordinator = config_entry.runtime_data.coordinator

    async_add_entities(
        IqTecBinarySensor(coordinator, idx, device_idx)
        for device_idx, device in coordinator.hub.devices.items()
        for idx, api in device.sensor_apis.items()
        if api.typ in {"OnOff", "bool"}
    )


class IqTecBinarySensor(IqTecVariableEntity, BinarySensorEntity):
    """IQtec Binary Sensor Entity."""

    @property
    def is_on(self) -> bool | None:
        """Whether the variable is set."""
        return None if self.raw_value is None else bool(self.raw_value)
