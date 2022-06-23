from __future__ import annotations
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST

import voluptuous as vol
import asyncio

from .const import DOMAIN
from .airtouch4 import AirTouch4

import logging
_LOGGER = logging.getLogger(__name__)

# TODO adjust the data schema to the data that you need
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)

class AirTouch4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Airtouch4."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=DATA_SCHEMA
            )

        errors = {}

        airtouch = AirTouch4(user_input[CONF_HOST])
        try:
            await asyncio.wait_for(airtouch.ready(), 5)
        except asyncio.TimeoutError:
            errors["base"] = "cannot_connect"
        except:
            _LOGGER.exception("Unknown error connecting to the Airtouch")
            errors["base"] = "unknown"
        await airtouch.disconnect()

        if errors:
            return self.async_show_form(
                step_id="user", data_schema=DATA_SCHEMA, errors=errors
            )

        return self.async_create_entry(
            title="AirTouch 4 (" + user_input[CONF_HOST] + ")",
            data=user_input
        )
