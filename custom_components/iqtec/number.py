"""IQtec Numbers."""

from __future__ import annotations

import sys

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode, UnitOfTemperature
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
    """Set up number entries."""
    coordinator = config_entry.runtime_data.coordinator

    numbers: list[IqTecNumber] = []
    for device_idx, device in coordinator.hub.devices.items():
        for idx, api in device.switch_apis.items():
            if api.typ in {"Temperature", "Humidity"}:
                numbers.append(IqTecTemperatureNumber(coordinator, idx, device_idx))
            elif api.typ == "byte":
                numbers.append(IqTecByteNumber(coordinator, idx, device_idx))
            elif api.typ in {"float", "short", "word", "long"}:
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


class IqTecByteNumber(IqTecNumber):
    """IQtec Byte Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1


class IqTecFloatNumber(IqTecNumber):
    """IQtec Float Entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -sys.float_info.max
    _attr_native_max_value = sys.float_info.max
    _attr_native_step = 0.001
