from homeassistant.components.button import ButtonEntity

from .entity import ThermoluxEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OffButton(entry.runtime_data, "desligar")])


class OffButton(ThermoluxEntity, ButtonEntity):
    _attr_name = "Desligar"
    _attr_icon = "mdi:power"

    async def async_press(self):
        await self.coordinator.command("parado")
