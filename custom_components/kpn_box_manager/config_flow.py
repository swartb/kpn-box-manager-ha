from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD

from .const import CONF_HOST, CONF_USERNAME, DEFAULT_HOST, DEFAULT_USERNAME, DOMAIN


class KPNBoxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            from .vendor.kpnboxapi import KPNBoxAPI

            def test_login():
                with KPNBoxAPI(host=user_input[CONF_HOST], timeout=15) as api:
                    return api.login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])

            try:
                if await self.hass.async_add_executor_job(test_login):
                    await self.async_set_unique_id(user_input[CONF_HOST])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=f"KPN Box ({user_input[CONF_HOST]})", data=user_input)
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
