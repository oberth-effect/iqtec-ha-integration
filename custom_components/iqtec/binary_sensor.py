"""IQtec Binary Sensor."""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
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
        for idx, a in d.sensor_apis.items():
            if a.typ in {"OnOff", "bool"}:
                sensors.append(IqTecBinarySensor(coordinator, idx, d_idx))
    async_add_entities(sensors)


class IqTecBinarySensor(IqTecEntity, BinarySensorEntity):
    """IQtec Binary Sensor Entity."""

    def __init__(self, coordinator: IqTecCoordinator, idx: str, device: str) -> None:
        """Initialise IQtec Temp sensor."""
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
        val = self.coordinator.data.devices[self._device_idx].sensors[self.idx]
        if "!" not in val:
            self._attr_is_on = bool(int(val))
        _LOGGER.debug("Updating device: %s", self.idx)
        self.async_write_ha_state()
