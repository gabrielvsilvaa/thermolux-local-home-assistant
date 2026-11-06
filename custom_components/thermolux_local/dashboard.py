"""Per-device agenda and authenticated dashboard commands."""
import asyncio
import base64
import binascii
import os
import re
import socket
from pathlib import Path
from shutil import copyfile

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from . import DOMAIN
from .protocol import TEMPERATURES

TIME = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
ACTIONS = {"parado", "degelo", *TEMPERATURES.values()}


def send_image(host, pixels):
    image = bytes.fromhex("10 10 00 f0 00 f0 01 1b") + pixels
    with socket.create_connection((host, 8090), 2) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        pending = bytearray()
        for index, offset in enumerate(range(0, len(image), 250)):
            payload = index.to_bytes(2, "big") + image[offset:offset + 250]
            packet = bytes.fromhex("5a a5 31 01") + len(payload).to_bytes(2, "big") + payload
            packet += bytes([sum(packet) & 255])
            for _ in range(5):
                connection.sendall(packet)
                try:
                    while True:
                        if len(pending) >= 6:
                            length = int.from_bytes(pending[4:6], "big")
                            if pending[:4] != bytes.fromhex("5a a5 31 02") or not 2 <= length <= 32:
                                raise ValueError("Resposta inesperada do toalheiro")
                            if len(pending) >= length + 7:
                                block = int.from_bytes(pending[6:8], "big")
                                del pending[:length + 7]
                                if block == index:
                                    break
                                continue
                        chunk = connection.recv(256)
                        if not chunk:
                            raise EOFError("O toalheiro encerrou a conexão")
                        pending.extend(chunk)
                except socket.timeout:
                    continue
                break
            else:
                raise TimeoutError(f"Toalheiro não confirmou o bloco {index + 1}")


def read_preview(path):
    return base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else None


def upload(host, path, pixels, preview):
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_bytes(preview)
        os.chmod(temporary, 0o600)
        send_image(host, pixels)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def copy_legacy_photo(source, target):
    if source.is_file() and not target.exists():
        copyfile(source, target)
        os.chmod(target, 0o600)


class Agenda:
    def __init__(self, coordinator, entry):
        self.coordinator = coordinator
        self.store = Store(coordinator.hass, 1, f"{DOMAIN}.{coordinator.identity}.agenda")
        self.path = Path(coordinator.hass.config.path(".storage", f"{DOMAIN}.{coordinator.identity}.jpg"))
        self.lock = asyncio.Lock()

    @classmethod
    async def load(cls, coordinator, entry):
        agenda = cls(coordinator, entry)
        agenda.data = await agenda.store.async_load()
        if agenda.data is None:
            previous = Store(coordinator.hass, 1, f"{DOMAIN}.{entry.entry_id}.agenda")
            agenda.data = await previous.async_load() or {"revision": 0, "rows": [], "enabled": False}
            source = Path(coordinator.hass.config.path(".storage", f"{DOMAIN}.{entry.entry_id}.jpg"))
            await coordinator.hass.async_add_executor_job(copy_legacy_photo, source, agenda.path)
            await agenda.store.async_save(agenda.data)
        entry.async_on_unload(async_track_time_change(coordinator.hass, agenda.tick, second=0))
        return agenda

    async def remember_entity(self, entity):
        if not entity:
            return
        async with self.lock:
            aliases = self.data.get("entities", [])
            if entity not in aliases:
                data = {**self.data, "entities": [*aliases, entity]}
                await self.store.async_save(data)
                self.data = data

    async def enable(self, enabled):
        async with self.lock:
            data = {**self.data, "enabled": enabled}
            await self.store.async_save(data)
            self.data = data

    async def tick(self, now):
        if not self.data["enabled"]:
            return
        time = now.strftime("%H:%M")
        rows = self.data["rows"]
        if any(row["end"] == time for row in rows):
            mode = "parado"
        else:
            mode = next((TEMPERATURES[row["temperature"]] for row in rows if row["start"] == time), None)
        if mode:
            await self.coordinator.command(mode)


def register(hass):
    if hass.data.get(DOMAIN + "_websocket"):
        return
    for command in (device, lookup, agenda_save, agenda_enable, upload_command, mode_command):
        websocket_api.async_register_command(hass, command)
    hass.data[DOMAIN + "_websocket"] = True


def runtime(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Use uma conta administradora do HA")
        return None
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        connection.send_error(msg["id"], "not_found", "Thermolux indisponível")
        return None
    return entry.runtime_data


@websocket_api.websocket_command({vol.Required("type"): DOMAIN + "/device", vol.Required("entry_id"): str})
@websocket_api.async_response
async def device(hass, connection, msg):
    if (coordinator := runtime(hass, connection, msg)) is None:
        return
    preview = await hass.async_add_executor_job(read_preview, coordinator.agenda.path)
    connection.send_result(msg["id"], {
        **coordinator.agenda.data,
        "preview": preview,
        "entity": mode_entity(hass, coordinator.identity),
    })


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/agenda_save",
    vol.Required("entry_id"): str,
    vol.Required("revision"): int,
    vol.Required("rows"): vol.All(list, vol.Length(max=30), [{
        vol.Required("start"): vol.Match(TIME),
        vol.Required("end"): vol.Match(TIME),
        vol.Required("temperature"): vol.In(TEMPERATURES),
    }]),
})
@websocket_api.async_response
async def agenda_save(hass, connection, msg):
    if (coordinator := runtime(hass, connection, msg)) is None:
        return
    if any(not TIME.fullmatch(row[key]) for row in msg["rows"] for key in ("start", "end")):
        connection.send_error(msg["id"], "invalid_time", "Use horários no formato HH:MM")
        return
    agenda = coordinator.agenda
    async with agenda.lock:
        if msg["revision"] != agenda.data["revision"]:
            connection.send_error(msg["id"], "conflict", "A agenda mudou. Feche e abra para recarregar.")
            return
        data = {**agenda.data, "revision": msg["revision"] + 1, "rows": msg["rows"]}
        try:
            await agenda.store.async_save(data)
        except OSError as error:
            connection.send_error(msg["id"], "agenda_error", str(error))
            return
        agenda.data = data
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/upload",
    vol.Required("entry_id"): str,
    vol.Required("pixels"): vol.All(str, vol.Length(min=153600, max=153600)),
    vol.Required("preview"): vol.All(str, vol.Length(max=180000)),
})
@websocket_api.async_response
async def upload_command(hass, connection, msg):
    if (coordinator := runtime(hass, connection, msg)) is None:
        return
    try:
        pixels = base64.b64decode(msg["pixels"], validate=True)
        image = base64.b64decode(msg["preview"], validate=True)
        if len(pixels) != 115200 or not image.startswith(b"\xff\xd8\xff") or not image.endswith(b"\xff\xd9"):
            raise ValueError("Imagem inválida")
        async with coordinator.io_lock:
            await hass.async_add_executor_job(upload, coordinator.host, coordinator.agenda.path, pixels, image)
    except (OSError, ValueError, EOFError, binascii.Error) as error:
        connection.send_error(msg["id"], "upload_failed", str(error))
        return
    connection.send_result(msg["id"], {"preview": msg["preview"]})


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/mode",
    vol.Required("entry_id"): str,
    vol.Required("mode"): vol.In(ACTIONS),
})
@websocket_api.async_response
async def mode_command(hass, connection, msg):
    if (coordinator := runtime(hass, connection, msg)) is None:
        return
    from homeassistant.exceptions import HomeAssistantError

    try:
        await coordinator.command(msg["mode"])
    except HomeAssistantError as error:
        connection.send_error(msg["id"], "command_failed", str(error))
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/agenda_enable",
    vol.Required("entry_id"): str,
    vol.Required("enabled"): bool,
})
@websocket_api.async_response
async def agenda_enable(hass, connection, msg):
    if (coordinator := runtime(hass, connection, msg)) is None:
        return
    try:
        await coordinator.agenda.enable(msg["enabled"])
    except OSError as error:
        connection.send_error(msg["id"], "agenda_error", str(error))
        return
    await coordinator.async_request_refresh()
    connection.send_result(msg["id"], coordinator.agenda.data)


def mode_entity(hass, identity):
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{identity}_modo")


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/lookup",
    vol.Required("entity"): str,
    vol.Optional("identity"): str,
})
@websocket_api.async_response
async def lookup(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Use uma conta administradora do HA")
        return
    identity = msg.get("identity")
    entity = msg["entity"]
    candidates = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is None or coordinator.agenda is None:
            continue
        current = mode_entity(hass, coordinator.identity)
        if identity:
            if coordinator.identity == identity:
                candidates.append((0, entry, current))
        elif current == entity:
            candidates.append((0, entry, current))
        elif entity in coordinator.agenda.data.get("entities", []):
            candidates.append((1, entry, current))
    candidates.sort(key=lambda item: item[0])
    if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
        connection.send_error(msg["id"], "not_found", "Selecione o sensor do toalheiro neste card")
        return
    _, entry, current = candidates[0]
    connection.send_result(msg["id"], {"entry_id": entry.entry_id, "entity": current})
