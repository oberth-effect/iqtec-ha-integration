"""Base classes for IQtec entities."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IqTecCoordinator

_DEVICE_INFO = DeviceInfo(manufacturer="IQtec/Kobra")


class IqTecEntity(CoordinatorEntity[IqTecCoordinator]):
    """Anything backed by the IQtec coordinator."""

    def __init__(self, coordinator: IqTecCoordinator, idx: str) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.idx = idx
        self._hub = coordinator.hub
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-{idx}"

    async def _async_command(self, func, *args: Any) -> None:
        """Run a blocking controller command, then refresh."""
        await self.hass.async_add_executor_job(self.coordinator.monitor.exclusive, func, *args)
        await self.coordinator.async_request_refresh()


class IqTecUnitEntity[S](IqTecEntity):
    """An entity backed by one of the modelled units (room, sunblind)."""

    async def async_added_to_hass(self) -> None:
        """Ask the coordinator to keep reading this unit."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_track_unit(self.idx))

    @property
    def iqtec_state(self) -> S:
        """Current state of the backing unit."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """Name reported by the controller, falling back to the unit id."""
        return getattr(self.iqtec_state, "name", None) or self.idx

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Returns raw iqtec state attributes."""
        return asdict(self.iqtec_state)


class IqTecVariableEntity(IqTecEntity):
    """A single controller variable discovered generically from data.xml."""

    # These are numerous and mostly duplicated across the setup, so they stay out
    # of the way until a user asks for them.
    _attr_entity_registry_enabled_default = False
    _attr_entity_registry_visible_default = False

    #: "sensors" for read-only variables, "switches" for writable ones.
    _source = "sensors"

    def __init__(self, coordinator: IqTecCoordinator, idx: str, device: str) -> None:
        """Initialise a raw variable entity."""
        super().__init__(coordinator, idx)
        self._device_idx = device
        self._attr_name = idx
        self._attr_device_info = _DEVICE_INFO | DeviceInfo(identifiers={(DOMAIN, device)}, name=f"_{device}")

    async def async_added_to_hass(self) -> None:
        """Ask the coordinator to keep reading this variable."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_track_variable(self._device_idx, self.idx))

    @property
    def raw_value(self) -> Any:
        """Decoded value, or None when the controller cannot supply it."""
        device = self.coordinator.data.devices.get(self._device_idx)
        if device is None:
            return None
        return getattr(device, self._source).get(self.idx)

    @property
    def available(self) -> bool:
        """Whether the controller is currently supplying this variable."""
        return super().available and self.raw_value is not None

    async def _async_write(self, value: Any) -> None:
        await self._async_command(self._hub.devices[self._device_idx].set_value, self.idx, value)
