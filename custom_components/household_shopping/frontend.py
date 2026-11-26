"""Serve the bundled dashboard card and load it on every dashboard (§7.1)."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

CARD_URL = "/household_shopping/household-shopping-card.js"
_CARD = Path(__file__).parent / "www" / "household-shopping-card.js"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    if "http" not in hass.config.components or getattr(hass, "http", None) is None:
        return
    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(_CARD), False)])
    # The frontend is always loaded in a real install; tests run without it.
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        add_extra_js_url(hass, f"{CARD_URL}?v={version}")
