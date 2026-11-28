"""Shop sensor: none / planning / shopping, plus counts and the last summary (§7.3)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ShoppingConfigEntry
from .entity import ShoppingEntity
from .model import GOT, MISSING, NEEDED


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShoppingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ShopSensor(entry.runtime_data, entry)])


class ShopSensor(ShoppingEntity, SensorEntity):
    _attr_translation_key = "shop"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["none", "planning", "shopping"]

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry, "shop")

    @property
    def native_value(self) -> str:
        shop = self.model.shop
        return shop["state"] if shop else "none"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        shop = self.model.shop or {}
        items = shop.get("items", [])

        def names(state: str) -> list[str]:
            return [i["name"] for i in items if i["state"] == state]

        history = self.model.data["history"]
        last = history[-1] if history else None
        return {
            "store": shop.get("store"),
            "created": shop.get("created"),
            "started": shop.get("started"),
            "needed": len(names(NEEDED)),
            "got": len(names(GOT)),
            "missing_items": names(MISSING),
            # BR-CASH-04: the open shop's cash-out amount, or None.
            "cash_out": next((i["amount"] for i in items if i.get("type") == "cash"), None),
            "last_shop_finished": last and last["finished"],
            "last_shop_missing": last and [i["name"] for i in last["missing"]],
            # BR-QUICK-05: open quick shops, e.g. for "remind me when I'm near Aldi".
            "quick_shops": [
                {
                    "shop_id": q["id"],
                    "store": q["store"],
                    "assignee": q.get("assignee"),
                    "needed": sum(1 for i in q["items"] if i["state"] == NEEDED),
                }
                for q in self.model.quick_shops
            ],
        }
