"""IQtec Switch."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, MANUAL_SWITCHES
from .coordinator import IqTecConfigEntry, IqTecCoordinator
from .entity import IqTecEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IqTecConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Switch entries."""
    coordinator = config_entry.runtime_data.coordinator

    switches = []
    for d_idx, d in coordinator.hub.devices.items():
        for idx, a in d.switch_apis.items():
            if a.typ in {"OnOff", "bool"}:
                switches.append(IqTecSwitch(coordinator, idx, d_idx))
    switches.extend(
        IqTecSwitch(coordinator, sw, sw.split(".", maxsplit=1)[0])
        for sw in MANUAL_SWITCHES
    )
    async_add_entities(switches)


class IqTecSwitch(IqTecEntity, SwitchEntity):
    """IQtec Switch Entity."""

    def __init__(self, coordinator: IqTecCoordinator, idx: str, device: str) -> None:
        """Initialise IQtec Switch."""
        super().__init__(coordinator, idx)
        self._device_idx = device
        self._val_idx = idx.split(".")[1]

        self.entity_registry_visible_default = False

        self._attr_device_info = self._default_device_info | DeviceInfo(
            identifiers={(DOMAIN, device)}, name=f"_{device}"
        )

    device_class = SwitchDeviceClass.SWITCH

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
            self._attr_is_on = bool(int(val))
        _LOGGER.debug("Updating device: %s", self.idx)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        r = self._hub.devices[self._device_idx].switch_apis[self.idx].set_request("1")
        self.hass.async_add_executor_job(self._hub.api_call, r)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        r = self._hub.devices[self._device_idx].switch_apis[self.idx].set_request("0")
        self.hass.async_add_executor_job(self._hub.api_call, r)

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the entity."""
        if self.is_off:
            return await self.turn_on()
        return await self.turn_off()
