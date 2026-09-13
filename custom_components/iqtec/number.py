"""IQtec Numbers."""

from __future__ import annotations

import sys

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode, UnitOfTemperature
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IqTecConfigEntry
from .entity import IqTecVariableEntity

PARALLEL_UPDATES = 0

# The whole-number types of data.xml and the values each can hold. piqtec
# refuses a fraction written to any of them.
_INTEGER_RANGES: dict[str, tuple[int, int]] = {
    "byte": (0, 2**8 - 1),
    "short": (-(2**15), 2**15 - 1),
    "word": (0, 2**16 - 1),
    "long": (-(2**31), 2**31 - 1),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entries."""
    coordinator = config_entry.runtime_data.coordinator

    numbers: list[IqTecNumber] = []
    for device_idx, device in coordinator.hub.devices.items():
        for idx, api in device.switch_apis.items():
            if api.typ == "Temperature":
                numbers.append(IqTecTemperatureNumber(coordinator, idx, device_idx))
            elif api.typ == "Humidity":
                numbers.append(IqTecHumidityNumber(coordinator, idx, device_idx))
            elif api.typ in _INTEGER_RANGES:
                numbers.append(IqTecIntegerNumber(coordinator, idx, device_idx, api.typ))
            elif api.typ == "float":
                numbers.append(IqTecFloatNumber(coordinator, idx, device_idx))
    async_add_entities(numbers)


class IqTecNumber(IqTecVariableEntity, NumberEntity):
    """IQtec Number Entity."""

    _source = "switches"

    @property
    def native_value(self) -> float | None:
        """Current value."""
        return self.raw_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._async_write(value)


class IqTecTemperatureNumber(IqTecNumber):
    """IQtec Temperature Entity."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.1


class IqTecHumidityNumber(IqTecNumber):
    """IQtec Humidity Entity."""

    _attr_device_class = NumberDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1


class IqTecIntegerNumber(IqTecNumber):
    """IQtec whole-number entity (byte, short, word, long)."""

    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(self, coordinator, idx: str, device: str, typ: str) -> None:
        """Initialise the entity with the bounds of its type."""
        super().__init__(coordinator, idx, device)
        self._attr_native_min_value, self._attr_native_max_value = _INTEGER_RANGES[typ]


class IqTecFloatNumber(IqTecNumber):
    """IQtec Float Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -sys.float_info.max
    _attr_native_max_value = sys.float_info.max
    _attr_native_step = 0.001
