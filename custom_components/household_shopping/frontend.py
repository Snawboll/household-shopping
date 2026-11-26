"""Serve the bundled dashboard card and make every dashboard load it (§7.1).

Preferred: keep one entry for the card in the dashboard resources (storage
mode), with the version in its URL so an update makes browsers fetch the new
file. That's how Marketplace cards load, and it doesn't depend on the browser
reloading HA's index page. Fallback (YAML-mode resources): inject the module
with add_extra_js_url.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_URL = "/household_shopping/household-shopping-card.js"
_CARD = Path(__file__).parent / "www" / "household-shopping-card.js"


def _ours(url: str) -> bool:
    return url.split("?", 1)[0] == CARD_URL


async def _async_resource_collection(hass: HomeAssistant):
    """The storage-mode resource collection, or None (YAML mode / no lovelace)."""
    if "lovelace" not in hass.config.components:
        return None
    try:
        from homeassistant.components.lovelace.const import (  # noqa: PLC0415
            LOVELACE_DATA,
            MODE_STORAGE,
        )
    except ImportError:
        return None
    data = hass.data.get(LOVELACE_DATA)
    if data is None or data.resource_mode != MODE_STORAGE:
        return None
    await data.resources.async_get_info()  # loads the collection
    return data.resources


async def async_register_card_resource(hass: HomeAssistant, url: str) -> bool:
    """Ensure exactly one resource entry for the card, at this version."""
    resources = await _async_resource_collection(hass)
    if resources is None:
        return False
    mine = [r for r in resources.async_items() if _ours(r.get("url", ""))]
    if not mine:
        await resources.async_create_item({"res_type": "module", "url": url})
        return True
    first, *duplicates = mine
    if first["url"] != url:
        await resources.async_update_item(first["id"], {"res_type": "module", "url": url})
    for dup in duplicates:
        await resources.async_delete_item(dup["id"])
    return True


async def async_remove_card_resource(hass: HomeAssistant) -> None:
    resources = await _async_resource_collection(hass)
    if resources is None:
        return
    for item in [r for r in resources.async_items() if _ours(r.get("url", ""))]:
        await resources.async_delete_item(item["id"])


async def async_setup_frontend(hass: HomeAssistant) -> None:
    if "http" not in hass.config.components or getattr(hass, "http", None) is None:
        return
    version = (await async_get_integration(hass, DOMAIN)).version
    url = f"{CARD_URL}?v={version}"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(_CARD), False)])
    try:
        if await async_register_card_resource(hass, url):
            return
    except Exception:  # never block setup over a dashboard resource
        _LOGGER.exception("Couldn't register the card as a dashboard resource")
    # The frontend is always loaded in a real install; tests run without it.
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        add_extra_js_url(hass, url)
