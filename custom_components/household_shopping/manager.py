"""State and persistence for a Household Shopping list."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import uuid

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_ITEM_UNAVAILABLE,
    EVENT_TRIP_FINISHED,
    MAX_HISTORY,
    STATUS_COMPLETED,
    STATUS_NEEDS_ACTION,
    STORAGE_VERSION,
    UNAVAILABLE_KEYWORDS,
)


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def _now() -> str:
    return dt_util.utcnow().isoformat()


class ShoppingManager:
    """Holds the shopping list, staples, active trip and trip history."""

    def __init__(self, hass: HomeAssistant, entry_id: str, name: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.name = name
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.data: dict[str, Any] = {
            "items": [],
            "staples": [],
            "active_trip": None,
            "history": [],
        }
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ storage

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.data.update(stored)

    async def async_save(self) -> None:
        await self._store.async_save(self.data)

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove

    @callback
    def _changed(self) -> None:
        self._store.async_delay_save(lambda: self.data, 1)
        for listener in list(self._listeners):
            listener()

    # --------------------------------------------------------------- accessors

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.data["items"]

    @property
    def staples(self) -> list[dict[str, Any]]:
        return self.data["staples"]

    @property
    def active_trip(self) -> dict[str, Any] | None:
        return self.data["active_trip"]

    @property
    def history(self) -> list[dict[str, Any]]:
        return self.data["history"]

    @property
    def unavailable_items(self) -> list[dict[str, Any]]:
        return [i for i in self.items if i.get("unavailable")]

    def _by_uid(self, key: str, uid: str) -> dict[str, Any] | None:
        return next((i for i in self.data[key] if i["uid"] == uid), None)

    def find_item(self, ref: str) -> dict[str, Any] | None:
        """Find a shopping item by uid or (case-insensitive) name, preferring open items."""
        if item := self._by_uid("items", ref):
            return item
        wanted = _norm(ref)
        matches = [i for i in self.items if _norm(i["summary"]) == wanted]
        open_matches = [i for i in matches if i["status"] == STATUS_NEEDS_ACTION]
        return (open_matches or matches or [None])[0]

    def has_open_item(self, summary: str) -> bool:
        wanted = _norm(summary)
        return any(
            _norm(i["summary"]) == wanted and i["status"] == STATUS_NEEDS_ACTION
            for i in self.items
        )

    # ------------------------------------------------------------ descriptions

    @staticmethod
    def unavailable_label(item: dict[str, Any]) -> str | None:
        info = item.get("unavailable")
        if not info:
            return None
        when = dt_util.parse_datetime(info["at"])
        date = ""
        if when:
            local = dt_util.as_local(when)
            date = f" ({local.day} {local:%b})"
        store = f" at {info['store']}" if info.get("store") else ""
        return f"Unavailable{store}{date}"

    def display_description(self, item: dict[str, Any]) -> str | None:
        label = self.unavailable_label(item)
        note = item.get("note") or ""
        if label and note:
            return f"{label} — {note}"
        return label or note or None

    @callback
    def _apply_description(self, item: dict[str, Any], description: str | None) -> None:
        desc = (description or "").strip()
        if desc == (self.display_description(item) or ""):
            return
        if _norm(desc) in UNAVAILABLE_KEYWORDS:
            self._mark_unavailable(item, None)
            return
        label = self.unavailable_label(item)
        if label and desc.startswith(label):
            # User edited only the note after the label.
            item["note"] = desc[len(label):].lstrip(" —-").strip()
            return
        # Any other edit replaces the note and clears the unavailable flag.
        item["note"] = desc
        item["unavailable"] = None

    # -------------------------------------------------------------- list items

    @callback
    def add_item(
        self,
        summary: str,
        description: str | None = None,
        status: str = STATUS_NEEDS_ACTION,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "uid": uuid.uuid4().hex,
            "summary": summary.strip(),
            "status": STATUS_NEEDS_ACTION,
            "note": "",
            "unavailable": None,
            "completed_at": None,
        }
        self.items.append(item)
        self._apply_description(item, description)
        self._set_status(item, status)
        self._changed()
        return item

    @callback
    def update_item(
        self,
        uid: str,
        summary: str | None,
        status: str | None,
        description: str | None,
    ) -> None:
        item = self._by_uid("items", uid)
        if item is None:
            raise ValueError(f"Unknown item {uid}")
        if summary:
            item["summary"] = summary.strip()
        self._apply_description(item, description)
        if status:
            self._set_status(item, status)
        self._changed()

    @callback
    def _set_status(self, item: dict[str, Any], status: str) -> None:
        if status == item["status"]:
            return
        item["status"] = status
        if status == STATUS_COMPLETED:
            item["completed_at"] = _now()
            item["unavailable"] = None  # found it after all
            if self.active_trip is None:
                self._start_trip(None)
        else:
            item["completed_at"] = None

    @callback
    def _mark_unavailable(self, item: dict[str, Any], store: str | None) -> None:
        if self.active_trip is None:
            self._start_trip(store)
        trip = self.active_trip or {}
        item["unavailable"] = {"at": _now(), "store": store or trip.get("store")}
        item["status"] = STATUS_NEEDS_ACTION
        item["completed_at"] = None
        self.hass.bus.async_fire(
            EVENT_ITEM_UNAVAILABLE,
            {
                "list": self.name,
                "item": item["summary"],
                "store": item["unavailable"]["store"],
            },
        )

    @callback
    def mark_unavailable(self, ref: str, store: str | None = None) -> dict[str, Any]:
        item = self.find_item(ref)
        if item is None:
            item = self.add_item(ref)
        self._mark_unavailable(item, store)
        self._changed()
        return item

    @callback
    def clear_unavailable(self, ref: str | None = None) -> int:
        targets = [self.find_item(ref)] if ref else self.unavailable_items
        count = 0
        for item in targets:
            if item and item.get("unavailable"):
                item["unavailable"] = None
                count += 1
        self._changed()
        return count

    @callback
    def delete_items(self, key: str, uids: list[str]) -> None:
        remove = set(uids)
        self.data[key] = [i for i in self.data[key] if i["uid"] not in remove]
        self._changed()

    @callback
    def move_item(self, key: str, uid: str, previous_uid: str | None) -> None:
        items = self.data[key]
        item = self._by_uid(key, uid)
        if item is None:
            raise ValueError(f"Unknown item {uid}")
        items.remove(item)
        if previous_uid is None:
            items.insert(0, item)
        else:
            prev = self._by_uid(key, previous_uid)
            if prev is None:
                items.append(item)
            else:
                items.insert(items.index(prev) + 1, item)
        self._changed()

    # ------------------------------------------------------------------ staples

    @callback
    def add_staple(self, summary: str) -> dict[str, Any]:
        wanted = _norm(summary)
        if existing := next((s for s in self.staples if _norm(s["summary"]) == wanted), None):
            return existing
        staple = {"uid": uuid.uuid4().hex, "summary": summary.strip()}
        self.staples.append(staple)
        self._changed()
        return staple

    @callback
    def update_staple(self, uid: str, summary: str | None, status: str | None) -> None:
        staple = self._by_uid("staples", uid)
        if staple is None:
            raise ValueError(f"Unknown staple {uid}")
        if summary:
            staple["summary"] = summary.strip()
        if status == STATUS_COMPLETED and not self.has_open_item(staple["summary"]):
            # Ticking a staple adds it to the shopping list; the staple itself stays.
            self.add_item(staple["summary"])
        self._changed()

    @callback
    def add_staples(self) -> list[str]:
        added = []
        for staple in self.staples:
            if not self.has_open_item(staple["summary"]):
                self.add_item(staple["summary"])
                added.append(staple["summary"])
        self._changed()
        return added

    # -------------------------------------------------------------------- trips

    @callback
    def _start_trip(self, store: str | None) -> None:
        self.data["active_trip"] = {"store": store, "started": _now()}

    @callback
    def start_trip(self, store: str | None) -> None:
        if self.active_trip is None:
            self._start_trip(store)
        elif store:
            self.active_trip["store"] = store
        self._changed()

    @callback
    def finish_trip(self, store: str | None = None, clear_bought: bool = True) -> dict[str, Any]:
        trip = self.active_trip or {"store": None, "started": None}
        started = trip["started"]

        def in_trip(ts: str | None) -> bool:
            return ts is not None and (started is None or ts >= started)

        record = {
            "store": store or trip["store"],
            "started": started,
            "finished": _now(),
            "bought": [
                i["summary"]
                for i in self.items
                if i["status"] == STATUS_COMPLETED and in_trip(i["completed_at"])
            ],
            "unavailable": [
                i["summary"]
                for i in self.items
                if i.get("unavailable") and in_trip(i["unavailable"]["at"])
            ],
            "remaining": [
                i["summary"]
                for i in self.items
                if i["status"] == STATUS_NEEDS_ACTION and not i.get("unavailable")
            ],
        }
        self.history.append(record)
        del self.history[:-MAX_HISTORY]
        if clear_bought:
            self.data["items"] = [i for i in self.items if i["status"] != STATUS_COMPLETED]
        self.data["active_trip"] = None
        self.hass.bus.async_fire(EVENT_TRIP_FINISHED, {"list": self.name, **record})
        self._changed()
        return record

    @callback
    def bought_this_trip(self) -> list[str]:
        trip = self.active_trip
        if not trip:
            return []
        return [
            i["summary"]
            for i in self.items
            if i["status"] == STATUS_COMPLETED
            and i["completed_at"]
            and i["completed_at"] >= trip["started"]
        ]
