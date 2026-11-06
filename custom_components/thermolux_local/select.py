from homeassistant.components.select import SelectEntity

from .entity import ThermoluxEntity
from .protocol import TEMPERATURES

OPTIONS = {"Degelo": "degelo", **TEMPERATURES}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ModeSelect(entry.runtime_data, "selecionar_modo")])


class ModeSelect(ThermoluxEntity, SelectEntity):
    _attr_name = "Selecionar modo"
    _attr_icon = "mdi:radiator"
    _attr_options = list(OPTIONS)

    @property
    def current_option(self):
        return next((label for label, mode in OPTIONS.items() if mode == self.coordinator.data), None)

    async def async_select_option(self, option):
        await self.coordinator.command(OPTIONS[option])
