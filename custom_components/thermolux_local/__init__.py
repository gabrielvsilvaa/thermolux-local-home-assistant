"""Thermolux Local config entries."""
import asyncio
from datetime import timedelta
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.const import CONF_HOST, Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import logging

from .protocol import read_mode, set_mode

DOMAIN = "thermolux_local"
PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.BUTTON, Platform.SWITCH]
LOGGER = logging.getLogger(__name__)


class ThermoluxCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, config_entry=entry, name=entry.title, update_interval=timedelta(seconds=30))
        self.host = entry.data[CONF_HOST]
        self.identity = entry.unique_id
        self.device = DeviceInfo(
            identifiers={(DOMAIN, self.identity)},
            manufacturer="Thermolux",
            model="Easy-IV",
            name=entry.title,
        )
        self.io_lock = asyncio.Lock()
        self.agenda = None

    async def _async_update_data(self):
        async with self.io_lock:
            try:
                return await self.hass.async_add_executor_job(read_mode, self.host)
            except OSError as err:
                raise UpdateFailed(str(err)) from err

    async def command(self, mode):
        async with self.io_lock:
            try:
                await self.hass.async_add_executor_job(set_mode, self.host, mode)
            except OSError as err:
                raise HomeAssistantError(str(err)) from err
        await self.async_request_refresh()


async def async_setup(hass, config):
    resource_path = "/thermolux_local/card.js"
    resource_url = resource_path + "?v=0.3.0"
    await hass.http.async_register_static_paths([
        StaticPathConfig(resource_path, str(Path(__file__).with_name("thermolux-local-card.js")), False)
    ])
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace and lovelace.resource_mode == MODE_STORAGE:
        resources = lovelace.resources
        await resources.async_get_info()
        existing = next((
            item for item in resources.async_items()
            if item.get("id") == "thermolux_local_card"
            or item.get("url", "").split("?")[0] == resource_path
        ), None)
        if existing is None:
            await resources.async_create_item({"url": resource_url, "res_type": "module"})
        elif existing["url"] != resource_url:
            await resources.async_update_item(existing["id"], {"url": resource_url})
    return True


async def async_setup_entry(hass, entry):
    from . import dashboard

    dashboard.register(hass)
    coordinator = ThermoluxCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.agenda = await dashboard.Agenda.load(coordinator, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.agenda.remember_entity(dashboard.mode_entity(hass, coordinator.identity))
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
