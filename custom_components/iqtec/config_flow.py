"""Config flow for the IQtec Smart Home integration."""

from __future__ import annotations

import logging
from typing import Any

from piqtec import Controller, IQtecError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_CORRECTION_TIMEOUT, CONF_COVER_USE_SHORT_TILT, DEFAULT_CORRECTION_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COVER_USE_SHORT_TILT, default=False): bool,
        vol.Optional(CONF_CORRECTION_TIMEOUT, default=DEFAULT_CORRECTION_TIMEOUT): int,
    }
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
