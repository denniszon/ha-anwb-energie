"""Config flow for ANWB Energie."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class AnwbEnergieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow without options: the tariffs are public."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the integration."""
        if user_input is not None:
            return self.async_create_entry(title="ANWB Energie", data={})
        return self.async_show_form(step_id="user")
