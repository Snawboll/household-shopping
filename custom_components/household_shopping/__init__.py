"""Household Shopping: a shared shopping list with staples, shop tracking and unavailable items."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .manager import ShoppingManager

PLATFORMS = [Platform.TODO, Platform.SENSOR]

type ShoppingConfigEntry = ConfigEntry[ShoppingManager]


async def async_setup_entry(hass: HomeAssistant, entry: ShoppingConfigEntry) -> bool:
    manager = ShoppingManager(hass, entry.entry_id, entry.title)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ShoppingConfigEntry) -> bool:
    await entry.runtime_data.async_save()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
