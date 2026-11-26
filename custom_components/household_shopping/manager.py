"""Glue between the pure model and Home Assistant: storage, events, listeners."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_MINOR_VERSION, STORAGE_VERSION
from .model import ShoppingError, ShoppingModel, default_data

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

T = TypeVar("T")


class ShoppingManager:
    """Owns one list's model and persists every change (BR-ITEM-09, NFR-02)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry_id = entry.entry_id
        self.name = entry.title
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry.entry_id}",
            minor_version=STORAGE_MINOR_VERSION,
        )
        self.model = ShoppingModel(now=dt_util.utcnow, fire=self._fire)
        self._listeners: list[Callable[[], None]] = []

    @staticmethod
    async def async_remove_store(hass: HomeAssistant, entry_id: str) -> None:
        await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}").async_remove()

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        data = default_data()
        if stored:
            data.update(stored)
        self.model.data = data

    async def async_save(self) -> None:
        await self._store.async_save(self.model.data)

    @callback
    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        self.hass.bus.async_fire(
            f"{DOMAIN}_{event}", {"list": self.name, "entry_id": self.entry_id, **payload}
        )

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            if update in self._listeners:
                self._listeners.remove(update)

        return remove

    @callback
    def run(self, func: Callable[[ShoppingModel], T]) -> T:
        """Apply one change atomically, then save and notify.

        Runs entirely inside the event loop with no awaits, so two people
        editing at once can't interleave and lose changes (NFR-06).
        """
        try:
            result = func(self.model)
        except ShoppingError as err:
            raise ServiceValidationError(str(err)) from err
        self._store.async_delay_save(lambda: self.model.data, 1)
        for listener in list(self._listeners):
            listener()
        return result
