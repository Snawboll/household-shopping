"""Actions (services). All target a list's shop to-do entity, e.g. todo.shopping (§7.4)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_platform_entity_service

from .const import DOMAIN
from .images import async_set_image_from_data, async_set_image_from_url, remove_image
from .manager import ShoppingManager
from .people import async_notify_assignee, check_person
from .model import (
    AISLES,
    GROUP_TYPES,
    IMAGE_SOURCES,
    ITEM_STATES,
    KINDS,
    LOCATIONS,
    OCCASIONAL,
    STOCK,
    ShoppingError,
    ShoppingModel,
)

_ENTITY_KEYS = {"entity_id", "device_id", "area_id", "floor_id", "label_id"}

Handler = Callable[[ShoppingManager, dict[str, Any]], Any]

opt_str = vol.Any(None, cv.string)
QTY = vol.All(vol.Coerce(int), vol.Range(min=1, max=99))

SHOP_ITEM = vol.Any(
    cv.string,
    vol.Schema(
        {
            vol.Required("name"): cv.string,
            vol.Optional("qty"): QTY,
            vol.Optional("note"): cv.string,
            vol.Optional("aisle"): cv.string,
        }
    ),
)

CATALOGUE_ENTRY = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("kind"): vol.In(KINDS),
        vol.Optional("location"): opt_str,
        vol.Optional("aisle"): opt_str,
        vol.Optional("note"): opt_str,
        vol.Optional("icon"): opt_str,
        vol.Optional("qty"): vol.Any(None, QTY),
    }
)
GROUP_TYPE = vol.In([*GROUP_TYPES, "location", "aisle"])

# Which open shop an action applies to; omitted means the main shop (BR-QUICK-04).
SHOP_ID = {vol.Optional("shop_id"): cv.string}
ASSIGNEE = vol.Any(None, "", cv.entity_id)


def _group_type(value: str) -> str:
    return {"location": LOCATIONS, "aisle": AISLES}.get(value, value)


def _sync(func: Callable[[ShoppingModel, dict[str, Any]], Any]) -> Handler:
    """Wrap a model change so it is saved and broadcast."""

    def handler(manager: ShoppingManager, data: dict[str, Any]) -> Any:
        return manager.run(lambda model: func(model, data))

    return handler


def _new_shop(model: ShoppingModel, d: dict[str, Any]) -> dict[str, Any]:
    shop = model.new_shop(d.get("store"))
    model.add_items(d.get("items", []))
    return {"shop_id": shop["id"], "items": [i["name"] for i in shop["items"]]}


def _assignee(manager: ShoppingManager, d: dict[str, Any]) -> str | None:
    person = d.get("assignee") or None
    check_person(manager.hass, person)
    return person


async def _new_quick_shop(manager: ShoppingManager, d: dict[str, Any]) -> dict[str, Any]:
    """BR-QUICK-01, BR-ASSIGN-02."""
    person = _assignee(manager, d)

    def apply(model: ShoppingModel) -> dict[str, Any]:
        shop = model.new_quick_shop(d.get("store"), person)
        model.add_items(d.get("items", []), shop_id=shop["id"])
        return shop

    shop = manager.run(apply)
    notified = await async_notify_assignee(
        manager.hass, shop, by_user_id=d.get("_user_id"), open_path=d.get("open_path")
    )
    return {"shop_id": shop["id"], "notified": notified}


async def _assign_shop(manager: ShoppingManager, d: dict[str, Any]) -> dict[str, Any]:
    """BR-ASSIGN-01/02: (re)assign a shop and tell the new person."""
    person = _assignee(manager, d)
    shop = manager.run(lambda m: m.assign_shop(d.get("shop_id"), person))
    manager.fire("shop_assigned", {"shop_id": shop["id"], "assignee": person})
    notified = await async_notify_assignee(
        manager.hass, shop, by_user_id=d.get("_user_id"), open_path=d.get("open_path")
    )
    return {"notified": notified}


async def _remind_shop(manager: ShoppingManager, d: dict[str, Any]) -> dict[str, Any]:
    """BR-ASSIGN-03: nudge the assignee again with the current list."""
    shop = manager.run(lambda m: m._require_shop(d.get("shop_id")))
    if not shop.get("assignee"):
        raise ShoppingError("Nobody is assigned to this shop yet")
    notified = await async_notify_assignee(
        manager.hass, shop, by_user_id=d.get("_user_id"), open_path=d.get("open_path"), reminder=True
    )
    if not notified:
        raise ShoppingError("Couldn't find a phone to notify for that person")
    return {"notified": True}


def _import(model: ShoppingModel, d: dict[str, Any]) -> dict[str, Any]:
    entries = [{"kind": d.get("kind", OCCASIONAL), **e} for e in d["items"]]
    return model.import_catalogue(entries)


def _history(model: ShoppingModel, d: dict[str, Any]) -> dict[str, Any]:
    return {"shops": list(reversed(model.data["history"][-d["limit"]:]))}


async def _set_image(manager: ShoppingManager, d: dict[str, Any]) -> None:
    if bool(d.get("image_url")) == bool(d.get("image_data")):
        raise ShoppingError("Give exactly one of image_url or image_data")
    if d.get("image_url"):
        await async_set_image_from_url(manager, d)
    else:
        await async_set_image_from_data(manager, d)


async def _clear_image(manager: ShoppingManager, d: dict[str, Any]) -> None:
    old = manager.run(lambda m: (m.get_catalogue_item(d["name"]).get("image") or {}))
    manager.run(lambda m: m.set_image(d["name"], None))
    if old.get("file"):
        await manager.hass.async_add_executor_job(remove_image, manager.hass, manager.entry_id, old["file"])


async def _remove_catalogue_item(manager: ShoppingManager, d: dict[str, Any]) -> None:
    """BR-IMG-04: deleting a catalogue item deletes its photo."""
    item = manager.run(lambda m: m.remove_catalogue_item(d["name"]))
    if (item.get("image") or {}).get("file"):
        await manager.hass.async_add_executor_job(
            remove_image, manager.hass, manager.entry_id, item["image"]["file"]
        )


# name -> (schema, handler, response)
SERVICES: dict[str, tuple[dict, Handler | Callable[..., Awaitable[Any]], SupportsResponse]] = {
    # ---------------------------------------------------------------- shop
    "new_shop": (
        {vol.Optional("store"): cv.string, vol.Optional("items", default=list): [SHOP_ITEM]},
        _sync(_new_shop),
        SupportsResponse.OPTIONAL,
    ),
    "new_quick_shop": (
        {
            vol.Optional("store"): cv.string,
            vol.Optional("assignee"): ASSIGNEE,
            vol.Optional("items", default=list): [SHOP_ITEM],
            vol.Optional("open_path"): cv.string,
        },
        _new_quick_shop,
        SupportsResponse.OPTIONAL,
    ),
    "assign_shop": (
        {**SHOP_ID, vol.Optional("assignee"): ASSIGNEE, vol.Optional("open_path"): cv.string},
        _assign_shop,
        SupportsResponse.OPTIONAL,
    ),
    "remind_shop": (
        {**SHOP_ID, vol.Optional("open_path"): cv.string},
        _remind_shop,
        SupportsResponse.OPTIONAL,
    ),
    "start_shopping": (
        {vol.Optional("store"): cv.string, **SHOP_ID},
        _sync(lambda m, d: m.start_shopping(d.get("store"), d.get("shop_id")) and None),
        SupportsResponse.NONE,
    ),
    "set_store": (
        {vol.Optional("store", default=""): vol.Any(None, cv.string), **SHOP_ID},
        _sync(lambda m, d: m.set_store(d.get("store"), d.get("shop_id")) and None),
        SupportsResponse.NONE,
    ),
    "finish_shop": (SHOP_ID, _sync(lambda m, d: m.finish_shop(d.get("shop_id"))), SupportsResponse.OPTIONAL),
    "cancel_shop": (SHOP_ID, _sync(lambda m, d: m.cancel_shop(d.get("shop_id"))), SupportsResponse.NONE),
    "repeat_shop": (
        {vol.Required("shop_id"): cv.string},
        _sync(lambda m, d: {"shop_id": m.repeat_shop(d["shop_id"])["id"]}),
        SupportsResponse.OPTIONAL,
    ),
    "add_item": (
        {
            vol.Required("name"): cv.string,
            vol.Optional("note"): cv.string,
            vol.Optional("aisle"): cv.string,
            vol.Optional("qty"): QTY,
            vol.Optional("remember"): cv.boolean,
            **SHOP_ID,
        },
        _sync(
            lambda m, d: m.add_item(
                d["name"],
                note=d.get("note"),
                aisle=d.get("aisle"),
                qty=d.get("qty"),
                remember=d.get("remember"),
                shop_id=d.get("shop_id"),
            )
            and None
        ),
        SupportsResponse.NONE,
    ),
    "update_item": (
        {
            vol.Required("item"): cv.string,
            vol.Optional("name"): cv.string,
            vol.Optional("note"): cv.string,
            vol.Optional("aisle"): cv.string,
            vol.Optional("qty"): QTY,
            **SHOP_ID,
        },
        _sync(
            lambda m, d: m.update_item(
                d["item"],
                name=d.get("name"),
                note=d.get("note"),
                aisle=d.get("aisle"),
                qty=d.get("qty"),
                shop_id=d.get("shop_id"),
            )
            and None
        ),
        SupportsResponse.NONE,
    ),
    "set_item_state": (
        {vol.Required("item"): cv.string, vol.Required("state"): vol.In(ITEM_STATES), **SHOP_ID},
        _sync(lambda m, d: m.set_item_state(d["item"], d["state"], d.get("shop_id")) and None),
        SupportsResponse.NONE,
    ),
    "remove_item": (
        {vol.Required("item"): cv.string, **SHOP_ID},
        _sync(lambda m, d: m.remove_item(d["item"], d.get("shop_id"))),
        SupportsResponse.NONE,
    ),
    "toggle_stock": (
        {vol.Required("name"): cv.string, vol.Required("on"): cv.boolean},
        _sync(lambda m, d: m.toggle_stock(d["name"], d["on"])),
        SupportsResponse.NONE,
    ),
    "get_history": (
        {vol.Optional("limit", default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=100))},
        _sync(_history),
        SupportsResponse.ONLY,
    ),
    # ----------------------------------------------------------- catalogue
    "add_stock_item": (
        {
            vol.Required("name"): cv.string,
            vol.Optional("location"): cv.string,
            vol.Optional("aisle"): cv.string,
            vol.Optional("note"): cv.string,
            vol.Optional("icon"): cv.string,
            vol.Optional("qty"): QTY,
        },
        _sync(
            lambda m, d: m.add_catalogue_item(
                d["name"], STOCK, **{k: d.get(k) for k in ("location", "aisle", "note", "icon", "qty")}
            )
            and None
        ),
        SupportsResponse.NONE,
    ),
    "add_occasional_item": (
        {
            vol.Required("name"): cv.string,
            vol.Optional("aisle"): cv.string,
            vol.Optional("note"): cv.string,
            vol.Optional("icon"): cv.string,
            vol.Optional("qty"): QTY,
        },
        _sync(
            lambda m, d: m.add_catalogue_item(
                d["name"], OCCASIONAL, **{k: d.get(k) for k in ("aisle", "note", "icon", "qty")}
            )
            and None
        ),
        SupportsResponse.NONE,
    ),
    "update_catalogue_item": (
        {
            vol.Required("name"): cv.string,
            vol.Optional("new_name"): cv.string,
            vol.Optional("location"): cv.string,
            vol.Optional("aisle"): cv.string,
            vol.Optional("note"): cv.string,
            vol.Optional("icon"): cv.string,
            vol.Optional("qty"): QTY,
        },
        _sync(
            lambda m, d: m.update_catalogue_item(
                d["name"],
                name=d.get("new_name"),
                **{k: d.get(k) for k in ("location", "aisle", "note", "icon", "qty")},
            )
            and None
        ),
        SupportsResponse.NONE,
    ),
    "promote_to_stock": (
        {vol.Required("name"): cv.string, vol.Optional("location"): cv.string},
        _sync(lambda m, d: m.set_kind(d["name"], STOCK, d.get("location")) and None),
        SupportsResponse.NONE,
    ),
    "demote_to_occasional": (
        {vol.Required("name"): cv.string},
        _sync(lambda m, d: m.set_kind(d["name"], OCCASIONAL) and None),
        SupportsResponse.NONE,
    ),
    "remove_catalogue_item": (
        {vol.Required("name"): cv.string},
        _remove_catalogue_item,
        SupportsResponse.NONE,
    ),
    "import_catalogue": (
        {
            vol.Required("items"): [CATALOGUE_ENTRY],
            vol.Optional("kind", default=OCCASIONAL): vol.In(KINDS),
        },
        _sync(_import),
        SupportsResponse.OPTIONAL,
    ),
    "get_catalogue": ({}, _sync(lambda m, d: m.snapshot()), SupportsResponse.ONLY),
    "set_item_image": (
        {
            vol.Required("name"): cv.string,
            vol.Optional("image_url"): cv.url,
            vol.Optional("image_data"): cv.string,
            vol.Optional("source", default="other"): vol.In(IMAGE_SOURCES),
            vol.Optional("attribution"): cv.string,
            vol.Optional("force", default=False): cv.boolean,
        },
        _set_image,
        SupportsResponse.NONE,
    ),
    "clear_item_image": ({vol.Required("name"): cv.string}, _clear_image, SupportsResponse.NONE),
    # -------------------------------------------------------------- groups
    "add_group": (
        {
            vol.Required("type"): GROUP_TYPE,
            vol.Required("name"): cv.string,
            vol.Optional("icon"): cv.string,
        },
        _sync(lambda m, d: m.add_group(_group_type(d["type"]), d["name"], d.get("icon")) and None),
        SupportsResponse.NONE,
    ),
    "update_group": (
        {
            vol.Required("type"): GROUP_TYPE,
            vol.Required("group"): cv.string,
            vol.Optional("name"): cv.string,
            vol.Optional("icon"): cv.string,
        },
        _sync(
            lambda m, d: m.update_group(
                _group_type(d["type"]), d["group"], d.get("name"), d.get("icon")
            )
        ),
        SupportsResponse.NONE,
    ),
    "remove_group": (
        {vol.Required("type"): GROUP_TYPE, vol.Required("group"): cv.string},
        _sync(lambda m, d: m.remove_group(_group_type(d["type"]), d["group"])),
        SupportsResponse.NONE,
    ),
    "order_groups": (
        {vol.Required("type"): GROUP_TYPE, vol.Required("groups"): [cv.string]},
        _sync(lambda m, d: m.order_groups(_group_type(d["type"]), d["groups"])),
        SupportsResponse.NONE,
    ),
}


def _make_func(handler: Callable[..., Any]) -> Callable[..., Awaitable[ServiceResponse]]:
    async def func(entity: Any, call: Any) -> ServiceResponse:
        data = getattr(call, "data", call)
        data = {k: v for k, v in data.items() if k not in _ENTITY_KEYS}
        context = getattr(entity, "_context", None) or getattr(call, "context", None)
        data["_user_id"] = getattr(context, "user_id", None)  # who asked (BR-ASSIGN-02)
        manager: ShoppingManager | None = getattr(entity, "shopping_manager", None)
        if manager is None:
            raise ShoppingError("Target a Household Shopping list, e.g. todo.shopping")
        try:
            result = handler(manager, data)
            if hasattr(result, "__await__"):
                result = await result
        except ShoppingError as err:
            from homeassistant.exceptions import ServiceValidationError  # noqa: PLC0415

            raise ServiceValidationError(str(err)) from err
        return result if isinstance(result, dict) else None

    return func


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    for name, (schema, handler, response) in SERVICES.items():
        async_register_platform_entity_service(
            hass,
            DOMAIN,
            name,
            entity_domain="todo",
            schema=schema,
            func=_make_func(handler),
            supports_response=response,
        )
