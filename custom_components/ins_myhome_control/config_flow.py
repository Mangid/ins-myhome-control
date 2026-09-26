from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_ROOM_TEMP, CONF_ROOM_HUMIDITY, CONF_WALL_CORNER_TEMP,
    CONF_WALL_CENTER_TEMP, CONF_GRID_POWER,
    DEFAULT_ROOM_TEMP, DEFAULT_ROOM_HUMIDITY, DEFAULT_WALL_CORNER_TEMP,
    DEFAULT_WALL_CENTER_TEMP, DEFAULT_GRID_POWER,
)

class INSMyHomeControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="INS MyHome Control", data=user_input)

        entity = selector.EntitySelector(selector.EntitySelectorConfig())
        schema = vol.Schema({
            vol.Required(CONF_ROOM_TEMP, default=DEFAULT_ROOM_TEMP): entity,
            vol.Required(CONF_ROOM_HUMIDITY, default=DEFAULT_ROOM_HUMIDITY): entity,
            vol.Required(CONF_WALL_CORNER_TEMP, default=DEFAULT_WALL_CORNER_TEMP): entity,
            vol.Required(CONF_WALL_CENTER_TEMP, default=DEFAULT_WALL_CENTER_TEMP): entity,
            vol.Required(CONF_GRID_POWER, default=DEFAULT_GRID_POWER): entity,
        })
        return self.async_show_form(step_id="user", data_schema=schema)
