"""Base class for Iqtec Entities."""

from dataclasses import asdict
import logging

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IqTecCoordinator

_LOGGER = logging.getLogger(__name__)


class IqTecEntity(CoordinatorEntity):
    """IqTec Base class."""

    # _attr_has_entity_name = True

    _default_device_info = DeviceInfo(manufacturer="IQtec/Kobra")

    def __init__(
        self,
        coordinator: IqTecCoordinator,
        idx: str,
    ) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.idx = idx
        self._hub = coordinator.hub
        self._attr_unique_id = f"{DOMAIN}-{self.idx}"

    @property
    def name(self) -> str:
        """Return the entity name."""
        return self.iqtec_state.name

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Returns raw iqtec state attributes."""
        return asdict(self.iqtec_state)
