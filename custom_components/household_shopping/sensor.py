"""Trip sensor: whether a shop is underway, plus the last trip's summary."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShoppingConfigEntry
from .entity import ShoppingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShoppingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([TripSensor(entry.runtime_data, entry)])


class TripSensor(ShoppingEntity, SensorEntity):
    """idle / shopping, with trip details as attributes."""

    _attr_name = "Trip"
    _attr_icon = "mdi:cart-arrow-right"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "shopping"]

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry, "trip")

    @property
    def native_value(self) -> str:
        return "shopping" if self._manager.active_trip else "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        trip = self._manager.active_trip or {}
        history = self._manager.history
        return {
            "store": trip.get("store"),
            "started": trip.get("started"),
            "bought_so_far": self._manager.bought_this_trip(),
            "unavailable_now": [i["summary"] for i in self._manager.unavailable_items],
            "last_trip": history[-1] if history else None,
            "trips_recorded": len(history),
        }
