"""Websocket API for the card: a live snapshot of one list (§7.2)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


def _manager(hass: HomeAssistant, entry_id: str | None):
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if entry_id is None or e.entry_id == entry_id
    ]
    return entries[0].runtime_data if entries else None


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/lists"}
)
@callback
def ws_lists(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_result(
        msg["id"],
        [
            {"entry_id": e.entry_id, "name": e.title}
            for e in hass.config_entries.async_loaded_entries(DOMAIN)
        ],
    )


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/subscribe", vol.Optional("entry_id"): str}
)
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    manager = _manager(hass, msg.get("entry_id"))
    if manager is None:
        connection.send_error(msg["id"], "not_found", "No Household Shopping list found")
        return

    @callback
    def send() -> None:
        connection.send_message(
            websocket_api.event_message(
                msg["id"],
                {"entry_id": manager.entry_id, "name": manager.name, **manager.model.snapshot()},
            )
        )

    connection.subscriptions[msg["id"]] = manager.async_add_listener(send)
    connection.send_result(msg["id"])
    send()


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_lists)
    websocket_api.async_register_command(hass, ws_subscribe)
