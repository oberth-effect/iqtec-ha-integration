"""IQtec Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    UnitOfTemperature,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .calendar_schedule import IqTecCalendarSensor
from .const import DOMAIN
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import MANUFACTURER, IqTecOnOffAutoVariable, IqTecVariableEntity
from .monitor import RequestStats

PARALLEL_UPDATES = 0

_NUMERIC_TYPES = {"byte", "float", "short", "word", "long", "Percentage", "AD_DA"}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entries."""
    coordinator = config_entry.runtime_data.coordinator

    sensors: list[SensorEntity] = [IqTecStatsSensor(coordinator, description) for description in STATS_SENSORS]
    sensors.extend(IqTecCalendarSensor(config_entry.runtime_data.calendars, idx) for idx in coordinator.hub.calendars)
    for device_idx, device in coordinator.hub.devices.items():
        for idx, api in device.sensor_apis.items():
            if api.typ == "Temperature":
                sensors.append(IqTecTemperatureSensor(coordinator, idx, device_idx))
            elif api.typ == "Humidity":
                sensors.append(IqTecHumiditySensor(coordinator, idx, device_idx))
            elif api.typ == "OnOffAuto":
                sensors.append(IqTecOnOffAutoSensor(coordinator, idx, device_idx))
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


class IqTecHumiditySensor(IqTecSensor):
    """IQtec Humidity Entity."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0


class IqTecNumericSensor(IqTecSensor):
    """IQtec Numeric Entity."""

    _attr_suggested_display_precision = 0


class IqTecOnOffAutoSensor(IqTecOnOffAutoVariable, SensorEntity):
    """A read-only On/Off/Auto variable, with the same three states as the select."""

    _attr_device_class = SensorDeviceClass.ENUM

    @property
    def native_value(self) -> str | None:
        """Current position."""
        return self.position


@dataclass(frozen=True, kw_only=True)
class IqTecStatsDescription(SensorEntityDescription):
    """One counter kept by the request monitor."""

    value_fn: Callable[[RequestStats], StateType]
    attributes_fn: Callable[[RequestStats], dict[str, Any]] = lambda stats: {}


STATS_SENSORS: tuple[IqTecStatsDescription, ...] = (
    IqTecStatsDescription(
        key="poll_requests",
        name="Poll requests",
        icon="mdi:swap-vertical",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda stats: stats.last_poll.requests,
        attributes_fn=lambda stats: {
            "bytes_received": stats.last_poll.bytes_received,
            "request_errors": stats.last_poll.errors,
        },
    ),
    IqTecStatsDescription(
        key="poll_duration",
        name="Poll duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda stats: round(stats.last_poll.duration, 3),
        attributes_fn=lambda stats: {"waited": round(stats.last_poll.waited, 3), "waits": stats.waits},
    ),
    IqTecStatsDescription(
        key="requests",
        name="Requests",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda stats: stats.requests,
        attributes_fn=lambda stats: {"bytes_received": stats.bytes_received, "polls": stats.polls},
    ),
    IqTecStatsDescription(
        key="request_errors",
        name="Request errors",
        icon="mdi:lan-disconnect",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda stats: stats.errors,
        attributes_fn=lambda stats: {"timeouts": stats.timeouts, "connection_errors": stats.connection_errors},
    ),
    IqTecStatsDescription(
        key="failed_polls",
        name="Failed polls",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda stats: stats.failed_polls,
        attributes_fn=lambda stats: {
            "consecutive_failures": stats.consecutive_failures,
            "last_success_at": stats.last_success_at,
        },
    ),
    IqTecStatsDescription(
        key="last_error",
        name="Last error",
        icon="mdi:message-alert-outline",
        value_fn=lambda stats: None if stats.last_error is None else stats.last_error[:255],
        attributes_fn=lambda stats: {"at": stats.last_error_at},
    ),
)


class IqTecStatsSensor(SensorEntity):
    """How the integration is treating the controller: requests, timing, failures.

    Deliberately not a coordinator entity: it has to stay available, and keep
    updating, while the controller itself cannot be reached.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    entity_description: IqTecStatsDescription

    def __init__(self, coordinator: IqTecCoordinator, description: IqTecStatsDescription) -> None:
        """Initialise a monitor sensor."""
        self.entity_description = description
        self._coordinator = coordinator
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}-stats-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            name=entry.title,
            configuration_url=f"http://{coordinator.hub.host}",
        )

    async def async_added_to_hass(self) -> None:
        """Refresh after every poll, whether or not it succeeded."""
        await super().async_added_to_hass()
        self.async_on_remove(self._coordinator.async_add_stats_listener(self._async_poll_finished))

    @callback
    def _async_poll_finished(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> StateType:
        """The counter this sensor shows."""
        return self.entity_description.value_fn(self._coordinator.monitor.stats)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Related counters that do not deserve a sensor of their own."""
        return self.entity_description.attributes_fn(self._coordinator.monitor.stats)
