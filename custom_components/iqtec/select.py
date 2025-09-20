"""IQtec Selects."""

import logging

from homeassistant.components.select import SelectEntity
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
    """Setup Select entries."""
    coordinator = config_entry.runtime_data.coordinator

    switches = []
    for d_idx, d in coordinator.hub.devices.items():
        for idx, a in d.switch_apis.items():
            if a.typ == "OnOffAuto":
                switches.append(IqTecOnOffAuto(coordinator, idx, d_idx))
    async_add_entities(switches)


class IqTecOnOffAuto(IqTecEntity, SelectEntity):
    """IQtec OnOffAuto Entity."""

    options = ["auto", "on", "off"]

    def __init__(self, coordinator: IqTecCoordinator, idx: str, device: str) -> None:
        """Initialise IQtec OnOffAuto.."""
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
        match val:
            case "0":
                self._attr_current_option = "off"
            case "1":
                self._attr_current_option = "on"
            case "2":
                self._attr_current_option = "auto"
        _LOGGER.debug("Updating device: %s", self.idx)
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Turn the entity on."""
        r = (
            self._hub.devices[self._device_idx]
            .switch_apis[self.idx]
            .set_request(option)
        )
        self.hass.async_add_executor_job(self._hub.api_call, r)
