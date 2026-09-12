"""Config flow for the IQtec Smart Home integration."""

from __future__ import annotations

import logging
from typing import Any

from piqtec import CalendarType, Controller, IQtecError
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CORRECTION_TIMEOUT,
    CONF_COVER_USE_SHORT_TILT,
    CONF_DISPLAY_TYPES,
    DEFAULT_CORRECTION_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COVER_USE_SHORT_TILT, default=False): bool,
        vol.Optional(CONF_CORRECTION_TIMEOUT, default=DEFAULT_CORRECTION_TIMEOUT): int,
    }
)

SCAN_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_SCAN_INTERVAL,
        max=MAX_SCAN_INTERVAL,
        step=1,
        unit_of_measurement="s",
        mode=NumberSelectorMode.BOX,
    )
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    def _connect() -> str:
        with Controller(data[CONF_HOST]) as controller:
            return controller.name

    try:
        name = await hass.async_add_executor_job(_connect)
    except IQtecError as err:
        raise CannotConnect(f"Got {err}") from err

    return {"url": data[CONF_HOST], "name": name}


class IQTecConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IQtec Smart Home."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Offer the polling interval and the per-calendar display overrides."""
        return IQTecOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(f"iqtec_platform_{user_input[CONF_HOST]}")
            self._abort_if_unique_id_configured()
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"{info['name']} ({info['url']})",
                    data=user_input,
                )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class IQTecOptionsFlow(OptionsFlow):
    """Let the user tune the polling and say how each calendar should be shown.

    The scan interval trades responsiveness for load on the controller, which
    is an embedded device with a small HTTP server.

    data.xml types several calendars TEMPERATURE that really drive something
    on/off, and the OEM application guesses from the calendar's name. Rather
    than matching names, ask once and remember.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the scan interval and one display type per calendar."""
        data = getattr(self.config_entry, "runtime_data", None)
        calendars = (data.calendars.data if data else None) or {}
        hub_calendars = data.calendars.hub.calendars if data else {}
        # Field keys read as "Calendar 3" and map back to the controller's id.
        keys = {f"calendar_{hub_calendars[idx].index}": idx for idx in calendars}

        if user_input is not None:
            # The form speaks lowercase; the option keeps the CalendarType value.
            chosen = {keys[key]: value.upper() for key, value in user_input.items() if key in keys}
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_DISPLAY_TYPES: chosen,
                }
            )

        current = self.config_entry.options.get(CONF_DISPLAY_TYPES) or {}
        # Selector options double as translation keys, which must be lowercase.
        selector = SelectSelector(
            SelectSelectorConfig(
                options=[t.value.lower() for t in CalendarType],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="display_type",
            )
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): SCAN_INTERVAL_SELECTOR,
                **{
                    vol.Required(key, default=(current.get(idx) or str(calendars[idx].calendar_type)).lower()): selector
                    for key, idx in keys.items()
                },
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={"names": ", ".join(f"{k} = {calendars[i].name}" for k, i in keys.items())},
        )
