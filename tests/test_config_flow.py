"""Tests for the IQtec config flow."""

from unittest.mock import patch

from piqtec import IQtecConnectionError

from custom_components.iqtec.const import CONF_CORRECTION_TIMEOUT, CONF_COVER_USE_SHORT_TILT, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

USER_INPUT = {
    CONF_HOST: "iqtec.home",
    CONF_COVER_USE_SHORT_TILT: False,
    CONF_CORRECTION_TIMEOUT: 24,
}


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_controller) -> None:
    """A reachable controller produces a config entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT


async def test_cannot_connect_is_recoverable(hass: HomeAssistant, mock_controller) -> None:
    """A connection error shows an error and lets the user retry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    with patch(
        "custom_components.iqtec.config_flow.Controller",
        side_effect=IQtecConnectionError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_host_is_aborted(hass: HomeAssistant, mock_controller) -> None:
    """The same controller cannot be added twice."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_host_is_stored_as_the_controller_reports_it(hass: HomeAssistant, mock_controller) -> None:
    """A scheme or a trailing slash in the input does not reach the entry, nor make a duplicate."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: "http://iqtec.home/"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "iqtec.home"
    assert result["title"] == "IQtec Controller (iqtec.home)"
    assert result["result"].unique_id == "iqtec_platform_iqtec.home"

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**USER_INPUT, CONF_HOST: "iqtec.home/"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_unexpected_errors_are_reported_not_swallowed(hass: HomeAssistant, mock_controller) -> None:
    """Anything but a connection problem shows the generic error and keeps the form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    with patch("custom_components.iqtec.config_flow.Controller", side_effect=HomeAssistantError("odd")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}
