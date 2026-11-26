"""Household Shopping: shops built from household stock, with missing-item tracking."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .frontend import async_remove_card_resource, async_setup_frontend
from .images import async_remove_entry_images, async_setup_images
from .manager import ShoppingManager
from .services import async_setup_services
from .websocket import async_setup_websocket

PLATFORMS = [Platform.TODO, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type ShoppingConfigEntry = ConfigEntry[ShoppingManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    async_setup_websocket(hass)
    async_setup_images(hass)
    await async_setup_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ShoppingConfigEntry) -> bool:
    manager = ShoppingManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ShoppingConfigEntry) -> bool:
    await entry.runtime_data.async_save()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """NFR-08: removing the integration deletes its data and photos."""
    await ShoppingManager.async_remove_store(hass, entry.entry_id)
    await async_remove_entry_images(hass, entry.entry_id)
    others = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
    if not others:
        await async_remove_card_resource(hass)
