"""IQtec Switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MANUAL_SWITCHES
from .coordinator import IqTecConfigEntry
from .entity import IqTecVariableEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switch entries."""
    coordinator = config_entry.runtime_data.coordinator

    # On/off variables are switches by type; MANUAL_SWITCHES names the ones
    # data.xml types as numbers although they only ever hold 0 or 1.
    async_add_entities(
        IqTecSwitch(coordinator, idx, device_idx)
        for device_idx, device in coordinator.hub.devices.items()
        for idx, api in device.switch_apis.items()
        if api.typ in {"OnOff", "bool"} or idx in MANUAL_SWITCHES
    )


class IqTecSwitch(IqTecVariableEntity, SwitchEntity):
    """IQtec Switch Entity."""

    _source = "switches"
    _attr_device_class = SwitchDeviceClass.SWITCH

    @property
    def is_on(self) -> bool | None:
        """Whether the switch is on."""
        return None if self.raw_value is None else bool(self.raw_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self._async_write(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._async_write(0)
