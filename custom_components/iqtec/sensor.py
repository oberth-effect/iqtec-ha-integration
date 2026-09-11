"""IQtec Sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .calendar_schedule import IqTecCalendarSensor
from .coordinator import IqTecConfigEntry
from .entity import IqTecVariableEntity

PARALLEL_UPDATES = 0

_NUMERIC_TYPES = {"byte", "float", "short", "word", "long", "Percentage", "AD_DA"}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entries."""
    coordinator = config_entry.runtime_data.coordinator

    sensors: list[SensorEntity] = []
    sensors.extend(IqTecCalendarSensor(config_entry.runtime_data.calendars, idx) for idx in coordinator.hub.calendars)
    for device_idx, device in coordinator.hub.devices.items():
        for idx, api in device.sensor_apis.items():
            if api.typ in {"Temperature", "Humidity"}:
                sensors.append(IqTecTemperatureSensor(coordinator, idx, device_idx))
            elif api.typ in _NUMERIC_TYPES:
                sensors.append(IqTecNumericSensor(coordinator, idx, device_idx))
    async_add_entities(sensors)


class IqTecSensor(IqTecVariableEntity, SensorEntity):
    """IQtec Sensor Entity."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Current value."""
        return self.raw_value


class IqTecTemperatureSensor(IqTecSensor):
    """IQtec Temperature Entity."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1


class IqTecNumericSensor(IqTecSensor):
    """IQtec Numeric Entity."""

    _attr_suggested_display_precision = 0
