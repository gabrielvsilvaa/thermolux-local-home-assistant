"""Add a device's card to an editable Home Assistant dashboard."""
from copy import deepcopy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.lovelace.const import ConfigNotFound, LOVELACE_DATA, MODE_STORAGE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

CARD_TYPE = "custom:thermolux-local-card"


def contains_card(node, entity):
    if isinstance(node, dict):
        if node.get("type") == CARD_TYPE and node.get("entity") == entity:
            return True
        return any(contains_card(value, entity) for value in node.values())
    return isinstance(node, list) and any(contains_card(value, entity) for value in node)


def add_card(view, entity, identity=None):
    if contains_card(view, entity):
        return False
    card = {"type": CARD_TYPE, "entity": entity}
    if identity:
        card["device_identity"] = identity
    if view.get("type") == "sections" or "sections" in view:
        sections = view.setdefault("sections", [])
        section = next((item for item in sections if item.get("type") == "grid"), None)
        if section is None:
            section = {"type": "grid", "cards": []}
            sections.append(section)
        card["grid_options"] = {"columns": "full"}
        section.setdefault("cards", []).append(card)
    else:
        view.setdefault("cards", []).append(card)
    return True


class ThermoluxPlacement(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        options = []
        destinations = {}
        errors = {}
        data = self.hass.data.get(LOVELACE_DATA)
        for path, dashboard in (data.dashboards.items() if data else ()):
            if dashboard.mode != MODE_STORAGE:
                continue
            try:
                config = await dashboard.async_load(False)
            except ConfigNotFound:
                continue
            title = (dashboard.config or {}).get("title", path or "Visão geral")
            for index, view in enumerate(config.get("views", [])):
                if view.get("type") == "panel" or view.get("panel") or view.get("strategy"):
                    continue
                key = f"{path or ''}:{index}"
                label = f"{title} · {view.get('title', f'Aba {index + 1}')}"
                options.append({"value": key, "label": label})
                destinations[key] = (dashboard, index, view.get("path"), view.get("title"))
        if not options:
            return self.async_abort(reason="no_dashboard")
        if user_input is not None:
            destination = destinations.get(user_input["destination"])
            if destination is None:
                errors["base"] = "dashboard_changed"
            else:
                registry = er.async_get(self.hass)
                entity = registry.async_get_entity_id(
                    "sensor", "thermolux_local", f"{self.config_entry.unique_id}_modo"
                )
                if entity is None:
                    return self.async_abort(reason="missing_sensor")
                dashboard, index, path, title = destination
                try:
                    config = deepcopy(await dashboard.async_load(False))
                    views = config.get("views", [])
                    if index >= len(views) or (views[index].get("path"), views[index].get("title")) != (path, title):
                        errors["base"] = "dashboard_changed"
                    elif not add_card(views[index], entity, self.config_entry.unique_id):
                        return self.async_abort(reason="card_present")
                    else:
                        await dashboard.async_save(config)
                        return self.async_create_entry(title="", data=dict(self.config_entry.options))
                except (HomeAssistantError, OSError):
                    errors["base"] = "save_failed"
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("destination"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
            }),
            errors=errors,
        )
