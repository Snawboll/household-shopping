"""Config flow for Household Shopping."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.util import slugify

from .const import CONF_NAME, DOMAIN


class HouseholdShoppingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a shopping list."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            await self.async_set_unique_id(slugify(name))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data={CONF_NAME: name})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default="Shopping"): str}),
        )
