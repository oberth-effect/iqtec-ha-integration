"""Config flow for the IQtec Smart Home integration."""

from __future__ import annotations

import logging
from typing import Any

from piqtec.controller import Controller
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required("cover_use_short_tilt"): bool,
    }
)


# def _sb_section(idx: str):
#     return vol.Schema(
#         {
#             vol.Optional("sunblind_name", default=idx): TextSelector(
#                 config=TextSelectorConfig(read_only=True)
#             ),
#             vol.Optional("cover_class", default=CoverDeviceClass.BLIND): selector(
#                 {"select": {"options": [e.value for e in CoverDeviceClass]}}
#             ),
#         }
#     )


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    try:
        c = await hass.async_add_executor_job(Controller, data[CONF_HOST])
    except ConnectionError as err:
        raise CannotConnect(f"Got {err}") from None

    # Return info that you want to store in the config entry.
    return {"url": data[CONF_HOST], "name": c.name, "sunblinds": c.sunblinds}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IQtec Smart Home."""

    VERSION = 1

    # _info: dict[str, str]
    # _user_data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                identifier = f"iqtec_platrom_{info['url']}"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(identifier)
                self._abort_if_unique_id_configured()
                # self._info = info
                # self._user_data = user_input

                return self.async_create_entry(
                    title=f"{info['name']} ({info['url']})",
                    data=user_input,
                )
                # return await self.async_step_blinds()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    # async def async_step_blinds(
    #     self, user_input: dict[str, Any] | None = None
    # ) -> ConfigFlowResult:
    #     """Sunblinds config."""
    #     errors: dict[str, str] = {}
    #     if user_input is not None:
    #         return self.async_create_entry(
    #             title=f"{self._info['name']} ({self._info['url']})",
    #             data={**self._user_data, "covers": user_input},
    #         )

    #     return self.async_show_form(
    #         step_id="blinds",
    #         data_schema=vol.Schema(
    #             {
    #                 vol.Required("use_short_tilt"): bool,
    #                 **{
    #                     vol.Required(idx): section(_sb_section(idx))
    #                     for idx in self._info["sunblinds"]
    #                 },
    #             },
    #         ),
    #         errors=errors,
    #     )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
