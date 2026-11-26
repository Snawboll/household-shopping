"""The open shop as a standard to-do list, for Assist and the stock HA UI (§7.3).

Mapping: needed -> needs_action; got -> completed; missing -> needs_action with
a "❌ Missing" description prefix. When no shop is open the list is empty, and
adding an item (e.g. via Assist) opens a new shop (BR-SHOP-02).
"""

from __future__ import annotations

import re

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ShoppingConfigEntry
from .const import MISSING_LABEL
from .entity import ShoppingEntity
from .model import GOT, MISSING, NEEDED


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShoppingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ShopTodoEntity(entry.runtime_data, entry)])


_QTY_PREFIX = re.compile(r"^×\s*\d+\s*·?\s*")


def _description(item: dict) -> str | None:
    """e.g. "❌ Missing · ×5 · Cavendish" (BR-QTY-05)."""
    parts = []
    if item["state"] == MISSING:
        parts.append(MISSING_LABEL)
    if item.get("qty", 1) > 1:
        parts.append(f"×{item['qty']}")
    if item.get("note"):
        parts.append(item["note"])
    return " · ".join(parts) or None


def _note_from(description: str | None) -> str:
    """Recover the note from an edited description, dropping our own labels."""
    text = (description or "").strip()
    if text.startswith(MISSING_LABEL):
        text = text[len(MISSING_LABEL):].lstrip(" ·").strip()
    return _QTY_PREFIX.sub("", text).strip()


class ShopTodoEntity(ShoppingEntity, TodoListEntity):
    _attr_name = None  # the list's own name, e.g. todo.shopping
    _attr_translation_key = "shop"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry, "shop_list")

    @property
    def todo_items(self) -> list[TodoItem]:
        shop = self.model.shop
        if not shop:
            return []
        return [
            TodoItem(
                uid=i["id"],
                summary=i["name"],
                status=TodoItemStatus.COMPLETED if i["state"] == GOT else TodoItemStatus.NEEDS_ACTION,
                description=_description(i),
            )
            for i in shop["items"]
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        def apply(model) -> None:
            new = model.add_item(item.summary or "", note=_note_from(item.description) or None)
            if item.status == TodoItemStatus.COMPLETED:
                model.set_item_state(new["id"], GOT)

        self.shopping_manager.run(apply)

    async def async_update_todo_item(self, item: TodoItem) -> None:
        def apply(model) -> None:
            current = model.find_item(item.uid)
            model.update_item(
                item.uid,
                name=item.summary or None,
                note=_note_from(item.description) if item.description is not None else None,
            )
            if item.status == TodoItemStatus.COMPLETED:
                model.set_item_state(item.uid, GOT)
            elif item.status == TodoItemStatus.NEEDS_ACTION and current["state"] == GOT:
                # Unticking means "still need it"; missing stays missing.
                model.set_item_state(item.uid, NEEDED)

        self.shopping_manager.run(apply)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self.shopping_manager.run(lambda model: model.remove_items(uids))

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        self.shopping_manager.run(lambda model: model.move_item(uid, previous_uid))
