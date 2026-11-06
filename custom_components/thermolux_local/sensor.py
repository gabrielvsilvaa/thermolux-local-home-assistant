from homeassistant.components.sensor import SensorEntity

from .entity import ThermoluxEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ModeSensor(entry.runtime_data, "modo")])


class ModeSensor(ThermoluxEntity, SensorEntity):
    _attr_name = "Modo atual"
    _attr_icon = "mdi:radiator"

    @property
    def native_value(self):
        return self.coordinator.data
