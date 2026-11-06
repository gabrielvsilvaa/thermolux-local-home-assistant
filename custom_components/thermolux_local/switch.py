from homeassistant.components.switch import SwitchEntity

from .entity import ThermoluxEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AgendaSwitch(entry.runtime_data, "agenda")])


class AgendaSwitch(ThermoluxEntity, SwitchEntity):
    _attr_name = "Agenda"
    _attr_icon = "mdi:calendar-clock-outline"

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return self.coordinator.agenda.data["enabled"]

    async def async_turn_on(self, **kwargs):
        await self.coordinator.agenda.enable(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self.coordinator.agenda.enable(False)
        self.async_write_ha_state()
