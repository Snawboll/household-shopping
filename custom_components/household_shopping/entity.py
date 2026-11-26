"""Shared entity base for Household Shopping."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import ShoppingManager


class ShoppingEntity(Entity):
    """Base entity tied to one shopping list."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: ShoppingManager, entry: ConfigEntry, key: str) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=manager.name,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.async_add_listener(self.async_write_ha_state))
