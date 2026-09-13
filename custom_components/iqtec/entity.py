"""Base classes for IQtec entities."""

from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any

from piqtec import InvalidValueError, IQtecError

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BURST_AFTER_COMMAND, DOMAIN, ON_OFF_AUTO
from .coordinator import IqTecCoordinator

_LOGGER = logging.getLogger(__name__)

MANUFACTURER = "IQtec/Kobra"

_ON_OFF_AUTO_LABELS = {value: label for label, value in ON_OFF_AUTO.items()}


def device_identifiers(entry: ConfigEntry, idx: str) -> set[tuple[str, str]]:
    """Identify one device of a config entry.

    Every installation calls its rooms R1..Rn and has a SYSTEM device, so the
    entry id keeps the devices of two controllers apart.
    """
    return {(DOMAIN, f"{entry.entry_id}-{idx}")}


class IqTecEntity(CoordinatorEntity[IqTecCoordinator]):
    """Anything backed by the IQtec coordinator."""

    def __init__(self, coordinator: IqTecCoordinator, idx: str) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.idx = idx
        self._hub = coordinator.hub
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-{idx}"

    async def _async_command(self, func, *args: Any) -> None:
        """Run a blocking controller command, then poll quickly for a while.

        piqtec reports every failure as an IQtecError. A value it cannot
        transmit is the caller's mistake; anything else is the controller's.
        """
        try:
            await self.hass.async_add_executor_job(self.coordinator.monitor.exclusive, func, *args)
        except InvalidValueError as err:
            raise ServiceValidationError(f"{self.idx}: {err}") from err
        except IQtecError as err:
            raise HomeAssistantError(f"{self.idx}: {err}") from err
        await self.coordinator.async_request_burst(BURST_AFTER_COMMAND)


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
        self._attr_device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            identifiers=device_identifiers(coordinator.config_entry, device),
            name=f"_{device}",
        )

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


class IqTecOnOffAutoVariable(IqTecVariableEntity):
    """A variable with the three positions off, on and auto.

    The labels double as translation keys, so the select and the sensor show
    Off, On and Auto with an icon per position. Any other value reads as
    unknown, stays in the attributes as the controller sent it, and is
    reported in the log once.
    """

    _attr_translation_key = "on_off_auto"
    _attr_options = list(ON_OFF_AUTO)

    def __init__(self, coordinator: IqTecCoordinator, idx: str, device: str) -> None:
        """Initialise the variable with nothing reported yet."""
        super().__init__(coordinator, idx, device)
        self._reported: set[Any] = set()

    @property
    def position(self) -> str | None:
        """The label of the current value, or None when it is none of the three."""
        value = self.raw_value
        if value is None:
            return None
        label = _ON_OFF_AUTO_LABELS.get(value)
        if label is None and value not in self._reported:
            self._reported.add(value)
            _LOGGER.warning("%s reports %r, which is none of off, on or auto", self.idx, value)
        return label

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The value as the controller sends it, telling when it is none of the three."""
        return {"raw_value": self.raw_value}
