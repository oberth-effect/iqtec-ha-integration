"""IQtec Numbers."""

import logging
import sys

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import IqTecEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Sensor entries."""
    coordinator = config_entry.runtime_data.coordinator

    sensors = []

    for d_idx, d in coordinator.hub.devices.items():
        for idx, a in d.switch_apis.items():
            if a.typ == "Temperature":
                sensors.append(IqTecTemperatureNumber(coordinator, idx, d_idx))
            if a.typ == "byte":
                sensors.append(IqTecByteNumber(coordinator, idx, d_idx))
            if a.typ in {"float", "short"}:
                sensors.append(IqTecFloatNumber(coordinator, idx, d_idx))
    async_add_entities(sensors)


class _IqTecBaseNumber(IqTecEntity, NumberEntity):
    """IQtec Base Number."""

    def __init__(self, coordinator: IqTecCoordinator, idx: str, device: str) -> None:
        """Initialise IQtec Number."""
        super().__init__(coordinator, idx)
        self._device_idx = device
        self._val_idx = idx.split(".")[1]

        self.entity_registry_visible_default = False

        self._attr_device_info = self._default_device_info | DeviceInfo(
            identifiers={(DOMAIN, device)}, name=f"_{device}"
        )

    @property
    def name(self) -> str:
        """Return the entity name."""
        return self.idx

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Returns raw iqtec state attributes."""
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        val = self.coordinator.data.devices[self._device_idx].switches[self.idx]
        if "!" not in val:
            self._attr_native_value = float(val)
        _LOGGER.debug("Updating device: %s", self.idx)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        r = (
            self._hub.devices[self._device_idx]
            .switch_apis[self.idx]
            .set_request(str(value))
        )
        self.hass.async_add_executor_job(self._hub.api_call, r)


class IqTecTemperatureNumber(_IqTecBaseNumber):
    """IQtec Temperature Entity."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS


class IqTecByteNumber(_IqTecBaseNumber):
    """IQtec Temperature Entity."""

    mode = "box"

    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1


class IqTecFloatNumber(_IqTecBaseNumber):
    """IQtec Temperature Entity."""

    _attr_native_max_value = sys.float_info.max
    _attr_native_min_value = sys.float_info.min
    _attr_native_step = 0.001

    mode = "box"
