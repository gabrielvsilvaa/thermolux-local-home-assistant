from homeassistant.helpers.update_coordinator import CoordinatorEntity


class ThermoluxEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device
        self._attr_unique_id = f"{coordinator.identity}_{key}"
