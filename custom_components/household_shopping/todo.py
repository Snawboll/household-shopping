"""To-do entities: the shopping list and the staples (standard) list."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShoppingConfigEntry
from .const import (
    ATTR_CLEAR_BOUGHT,
    ATTR_ITEM,
    ATTR_LIMIT,
    ATTR_STORE,
    SERVICE_ADD_STAPLES,
    SERVICE_ADD_TO_STAPLES,
    SERVICE_CLEAR_UNAVAILABLE,
    SERVICE_FINISH_SHOP,
    SERVICE_GET_HISTORY,
    SERVICE_MARK_UNAVAILABLE,
    SERVICE_START_SHOP,
    STATUS_NEEDS_ACTION,
)
from .entity import ShoppingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShoppingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = entry.runtime_data
    async_add_entities(
        [ShoppingListEntity(manager, entry), StaplesListEntity(manager, entry)]
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_ADD_STAPLES, {}, "async_service_add_staples",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        SERVICE_ADD_TO_STAPLES,
        {vol.Required(ATTR_ITEM): cv.string},
        "async_service_add_to_staples",
    )
    platform.async_register_entity_service(
        SERVICE_START_SHOP,
        {vol.Optional(ATTR_STORE): cv.string},
        "async_service_start_shop",
    )
    platform.async_register_entity_service(
        SERVICE_FINISH_SHOP,
        {
            vol.Optional(ATTR_STORE): cv.string,
            vol.Optional(ATTR_CLEAR_BOUGHT, default=True): cv.boolean,
        },
        "async_service_finish_shop",
        supports_response=SupportsResponse.OPTIONAL,
    )
    platform.async_register_entity_service(
        SERVICE_MARK_UNAVAILABLE,
        {vol.Required(ATTR_ITEM): cv.string, vol.Optional(ATTR_STORE): cv.string},
        "async_service_mark_unavailable",
    )
    platform.async_register_entity_service(
        SERVICE_CLEAR_UNAVAILABLE,
        {vol.Optional(ATTR_ITEM): cv.string},
        "async_service_clear_unavailable",
    )
    platform.async_register_entity_service(
        SERVICE_GET_HISTORY,
        {vol.Optional(ATTR_LIMIT, default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=100))},
        "async_service_get_history",
        supports_response=SupportsResponse.ONLY,
    )


class _ServiceMixin(ShoppingEntity, TodoListEntity):
    """Services work when targeting either the list or the staples entity."""

    async def async_service_add_staples(self) -> ServiceResponse:
        return {"added": self._manager.add_staples()}

    async def async_service_add_to_staples(self, item: str) -> None:
        self._manager.add_staple(item)

    async def async_service_start_shop(self, store: str | None = None) -> None:
        self._manager.start_trip(store)

    async def async_service_finish_shop(
        self, clear_bought: bool = True, store: str | None = None
    ) -> ServiceResponse:
        return self._manager.finish_trip(store=store, clear_bought=clear_bought)

    async def async_service_mark_unavailable(self, item: str, store: str | None = None) -> None:
        self._manager.mark_unavailable(item, store)

    async def async_service_clear_unavailable(self, item: str | None = None) -> None:
        if item and self._manager.find_item(item) is None:
            raise ServiceValidationError(f"'{item}' isn't on the {self._manager.name} list")
        self._manager.clear_unavailable(item)

    async def async_service_get_history(self, limit: int = 10) -> ServiceResponse:
        return {"trips": list(reversed(self._manager.history[-limit:]))}


class ShoppingListEntity(_ServiceMixin):
    """The shared shopping list."""

    _attr_name = None  # use the list's name, e.g. todo.shopping
    _attr_icon = "mdi:cart-outline"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry, "list")

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=i["uid"],
                summary=i["summary"],
                status=TodoItemStatus(i["status"]),
                description=self._manager.display_description(i),
            )
            for i in self._manager.items
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"unavailable": [i["summary"] for i in self._manager.unavailable_items]}

    async def async_create_todo_item(self, item: TodoItem) -> None:
        self._manager.add_item(
            item.summary or "",
            description=item.description,
            status=item.status.value if item.status else STATUS_NEEDS_ACTION,
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        self._manager.update_item(
            item.uid,
            item.summary,
            item.status.value if item.status else None,
            item.description,
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self._manager.delete_items("items", uids)

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        self._manager.move_item("items", uid, previous_uid)


class StaplesListEntity(_ServiceMixin):
    """The standard list. Ticking a staple adds it to the shopping list."""

    _attr_name = "Staples"
    _attr_icon = "mdi:format-list-checks"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
    )

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry, "staples")

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(uid=s["uid"], summary=s["summary"], status=TodoItemStatus.NEEDS_ACTION)
            for s in self._manager.staples
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        self._manager.add_staple(item.summary or "")

    async def async_update_todo_item(self, item: TodoItem) -> None:
        self._manager.update_staple(
            item.uid, item.summary, item.status.value if item.status else None
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self._manager.delete_items("staples", uids)

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        self._manager.move_item("staples", uid, previous_uid)
