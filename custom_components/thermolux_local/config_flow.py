"""Set up a Thermolux device by local address."""
import ipaddress

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback

from .placement import ThermoluxPlacement

from .protocol import read_identity, read_mode


def probe(host):
    identity = read_identity(host)
    read_mode(host)
    return identity


class ThermoluxConfigFlow(config_entries.ConfigFlow, domain="thermolux_local"):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ThermoluxPlacement()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                host = str(ipaddress.IPv4Address(user_input[CONF_HOST].strip()))
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            else:
                try:
                    identity = await self.hass.async_add_executor_job(probe, host)
                except OSError:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(identity)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                    name = user_input[CONF_NAME].strip()
                    if name:
                        return self.async_create_entry(title=name, data={CONF_HOST: host})
                    errors[CONF_NAME] = "invalid_name"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default="Thermolux"): str,
                vol.Required(CONF_HOST): str,
            }),
            errors=errors,
        )
