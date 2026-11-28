"""Business rules for Household Shopping, kept free of Home Assistant imports.

Every public method enforces the rules in docs/REQUIREMENTS.md (rule IDs are
quoted in comments) and raises ShoppingError with a user-readable message when a
request breaks one. The HA layer turns ShoppingError into ServiceValidationError.

All state lives in one JSON-serialisable dict (``self.data``) so persistence is
just "save the dict".
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from typing import Any
import uuid

from .icons_map import DEFAULT_ICON, guess_icon

STOCK = "stock"
OCCASIONAL = "occasional"
KINDS = (STOCK, OCCASIONAL)

PLANNING = "planning"
SHOPPING = "shopping"

NEEDED = "needed"
GOT = "got"
MISSING = "missing"
ITEM_STATES = (NEEDED, GOT, MISSING)

LOCATIONS = "locations"
AISLES = "aisles"
GROUP_TYPES = (LOCATIONS, AISLES)

OTHER_ID = "other"
MAX_HISTORY = 100
MAX_QTY = 99

IMAGE_SOURCES = ("own", "openfoodfacts", "other")

EVENT_SHOP_FINISHED = "shop_finished"
EVENT_ITEM_MISSING = "item_missing"

# §3.1 defaults. Aisle order loosely follows a typical Australian supermarket walk.
DEFAULT_LOCATIONS = [
    ("fridge", "Fridge", "🧊"),
    ("freezer", "Freezer", "❄️"),
    ("pantry", "Pantry", "🥫"),
    ("fruit_bowl", "Fruit bowl", "🍎"),
    ("bathroom", "Bathroom", "🛁"),
    ("laundry", "Laundry", "🧺"),
    ("cleaning", "Cleaning", "🧽"),
    (OTHER_ID, "Other", "📦"),
]
DEFAULT_AISLES = [
    ("fruit_veg", "Fruit & Veg", "🥦"),
    ("bakery", "Bakery", "🍞"),
    ("deli", "Deli", "🧀"),
    ("meat_seafood", "Meat & Seafood", "🥩"),
    ("dairy_eggs", "Dairy & Eggs", "🥛"),
    ("pantry", "Pantry", "🥫"),
    ("breakfast", "Breakfast", "🥣"),
    ("snacks", "Snacks & Confectionery", "🍫"),
    ("drinks", "Drinks", "🧃"),
    ("international", "International", "🌮"),
    ("frozen", "Frozen", "🧊"),
    ("health_beauty", "Health & Beauty", "🧴"),
    ("baby", "Baby", "👶"),
    ("pet", "Pet", "🐾"),
    ("cleaning_laundry", "Cleaning & Laundry", "🧽"),
    ("household", "Household", "🏠"),
    (OTHER_ID, "Other", "🛒"),
]


class ShoppingError(Exception):
    """A request that breaks a business rule. The message is shown to the user."""


def check_qty(qty: Any) -> int:
    """BR-QTY-01: a whole number from 1 to 99."""
    if isinstance(qty, float) and qty.is_integer():
        value = int(qty)
    elif isinstance(qty, str) and qty.strip().isdigit():
        value = int(qty)
    elif isinstance(qty, int) and not isinstance(qty, bool):
        value = qty
    else:
        raise ShoppingError("Quantity must be a whole number")
    if not 1 <= value <= MAX_QTY:
        raise ShoppingError(f"Quantity must be between 1 and {MAX_QTY}")
    return value


def normalise(data: dict[str, Any]) -> dict[str, Any]:
    """Fill fields added in later versions so older stored data keeps working."""
    for entry in data.get("catalogue", []):
        entry.setdefault("qty", 1)
    for item in (data.get("shop") or {}).get("items", []):
        item.setdefault("qty", 1)
    for record in data.get("history", []):
        for key in ("missing", "got", "not_got"):
            for entry in record.get(key, []):
                entry.setdefault("qty", 1)
    return data


def norm(text: str | None) -> str:
    """Name matching: case-insensitive, extra whitespace ignored (BR-STOCK-01)."""
    return " ".join((text or "").casefold().split())


def clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _new_id() -> str:
    return uuid.uuid4().hex


def default_data() -> dict[str, Any]:
    return {
        LOCATIONS: [{"id": i, "name": n, "icon": ic} for i, n, ic in DEFAULT_LOCATIONS],
        AISLES: [{"id": i, "name": n, "icon": ic} for i, n, ic in DEFAULT_AISLES],
        "catalogue": [],
        "shop": None,
        "history": [],
    }


class ShoppingModel:
    """All shopping state and the rules that change it."""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        *,
        now: Callable[[], datetime],
        fire: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.data = data if data is not None else default_data()
        self._now = now
        self._fire = fire or (lambda event, payload: None)

    def _ts(self) -> str:
        return self._now().isoformat()

    # ================================================================ groups
    # BR-STOCK-04..06: home locations and aisles are editable, ordered lists.

    def groups(self, group_type: str) -> list[dict[str, Any]]:
        if group_type not in GROUP_TYPES:
            raise ShoppingError(f"Unknown group type '{group_type}'")
        return self.data[group_type]

    def group_id(self, group_type: str, ref: str | None) -> str:
        """Resolve a group name or id. None/empty means Other (BR-STOCK-07)."""
        if not clean(ref):
            return OTHER_ID
        for group in self.groups(group_type):
            if group["id"] == ref or norm(group["name"]) == norm(ref):
                return group["id"]
        label = "home location" if group_type == LOCATIONS else "aisle"
        names = ", ".join(g["name"] for g in self.groups(group_type))
        raise ShoppingError(f"Unknown {label} '{ref}'. Choose one of: {names}")

    def group(self, group_type: str, group_id: str) -> dict[str, Any]:
        for group in self.groups(group_type):
            if group["id"] == group_id:
                return group
        return self.group(group_type, OTHER_ID)

    def add_group(self, group_type: str, name: str, icon: str | None = None) -> dict[str, Any]:
        name = clean(name)
        if not name:
            raise ShoppingError("A name is required")
        groups = self.groups(group_type)
        if any(norm(g["name"]) == norm(name) for g in groups):
            raise ShoppingError(f"'{name}' already exists")
        group = {"id": _new_id(), "name": name, "icon": icon or "📦"}
        # New groups go before Other, which always stays last.
        groups.insert(len(groups) - 1, group)
        return group

    def update_group(
        self, group_type: str, ref: str, name: str | None = None, icon: str | None = None
    ) -> None:
        group = self.group(group_type, self.group_id(group_type, ref))
        if name is not None:
            name = clean(name)
            if not name:
                raise ShoppingError("A name is required")
            if any(
                norm(g["name"]) == norm(name) and g is not group
                for g in self.groups(group_type)
            ):
                raise ShoppingError(f"'{name}' already exists")
            group["name"] = name
        if icon is not None:
            group["icon"] = icon

    def remove_group(self, group_type: str, ref: str) -> None:
        """Deleting a group moves its items to Other (BR-STOCK-06)."""
        group_id = self.group_id(group_type, ref)
        if group_id == OTHER_ID:
            raise ShoppingError("'Other' can't be deleted")
        field = "location" if group_type == LOCATIONS else "aisle"
        for item in self.data["catalogue"]:
            if item.get(field) == group_id:
                item[field] = OTHER_ID
        if group_type == AISLES and self.shop:
            for item in self.shop["items"]:
                if item["aisle"] == group_id:
                    item["aisle"] = OTHER_ID
        self.data[group_type] = [g for g in self.groups(group_type) if g["id"] != group_id]

    def order_groups(self, group_type: str, refs: list[str]) -> None:
        """Reorder groups. Unlisted groups keep their relative order; Other stays last."""
        groups = self.groups(group_type)
        ids = [self.group_id(group_type, r) for r in refs]
        by_id = {g["id"]: g for g in groups}
        ordered = [by_id[i] for i in dict.fromkeys(ids) if i != OTHER_ID]
        rest = [g for g in groups if g["id"] not in ids and g["id"] != OTHER_ID]
        self.data[group_type] = ordered + rest + [by_id[OTHER_ID]]

    # ============================================================= catalogue

    @property
    def catalogue(self) -> list[dict[str, Any]]:
        return self.data["catalogue"]

    def find_catalogue(self, ref: str | None) -> dict[str, Any] | None:
        if not ref:
            return None
        wanted = norm(ref)
        return next(
            (c for c in self.catalogue if c["id"] == ref or norm(c["name"]) == wanted),
            None,
        )

    def get_catalogue_item(self, ref: str) -> dict[str, Any]:
        item = self.find_catalogue(ref)
        if item is None:
            raise ShoppingError(f"'{ref}' isn't in the catalogue")
        return item

    def icon_for(self, item: dict[str, Any]) -> str:
        """BR-IMG-02: user icon, else keyword guess, else the aisle's icon."""
        return (
            item.get("icon")
            or guess_icon(item["name"])
            or self.group(AISLES, item.get("aisle") or OTHER_ID).get("icon")
            or DEFAULT_ICON
        )

    def add_catalogue_item(
        self,
        name: str,
        kind: str,
        *,
        location: str | None = None,
        aisle: str | None = None,
        note: str | None = None,
        icon: str | None = None,
        qty: int | None = None,
    ) -> dict[str, Any]:
        name = clean(name)
        if not name:
            raise ShoppingError("A name is required")
        if kind not in KINDS:
            raise ShoppingError(f"Kind must be one of {', '.join(KINDS)}")
        # BR-STOCK-01 / BR-OCC-01: one name, one catalogue entry.
        if existing := self.find_catalogue(name):
            raise ShoppingError(f"'{existing['name']}' is already in the catalogue as {existing['kind']}")
        item = {
            "id": _new_id(),
            "name": name,
            "kind": kind,
            # Occasional items aren't reviewed by location, but keep one if given
            # so promotion (BR-OCC-04) can reuse it.
            "location": self.group_id(LOCATIONS, location),
            "aisle": self.group_id(AISLES, aisle),
            "note": clean(note),
            "icon": icon or None,
            "qty": check_qty(qty) if qty is not None else 1,  # BR-QTY-02 usual amount
            "image": None,
            "created": self._ts(),
        }
        self.catalogue.append(item)
        return item

    def update_catalogue_item(
        self,
        ref: str,
        *,
        name: str | None = None,
        location: str | None = None,
        aisle: str | None = None,
        note: str | None = None,
        icon: str | None = None,
        qty: int | None = None,
    ) -> dict[str, Any]:
        """BR-STOCK-02: changing the catalogue never touches the open shop."""
        item = self.get_catalogue_item(ref)
        if name is not None:
            name = clean(name)
            if not name:
                raise ShoppingError("A name is required")
            other = self.find_catalogue(name)
            if other is not None and other is not item:
                raise ShoppingError(f"'{other['name']}' is already in the catalogue")
            item["name"] = name
        if location is not None:
            item["location"] = self.group_id(LOCATIONS, location)
        if aisle is not None:
            item["aisle"] = self.group_id(AISLES, aisle)
        if note is not None:
            item["note"] = clean(note)
        if icon is not None:
            item["icon"] = icon or None
        if qty is not None:
            item["qty"] = check_qty(qty)
        return item

    def set_kind(self, ref: str, kind: str, location: str | None = None) -> dict[str, Any]:
        """BR-OCC-04: promote to stock (optionally with a location) or demote."""
        item = self.get_catalogue_item(ref)
        if kind not in KINDS:
            raise ShoppingError(f"Kind must be one of {', '.join(KINDS)}")
        item["kind"] = kind
        if location is not None:
            item["location"] = self.group_id(LOCATIONS, location)
        return item

    def remove_catalogue_item(self, ref: str) -> dict[str, Any]:
        """Removes the entry. Shop items keep their name but lose the link."""
        item = self.get_catalogue_item(ref)
        self.data["catalogue"] = [c for c in self.catalogue if c is not item]
        if self.shop:
            for shop_item in self.shop["items"]:
                if shop_item.get("catalogue_id") == item["id"]:
                    shop_item["catalogue_id"] = None
        return item

    def move_catalogue_item(self, ref: str, before: str | None) -> None:
        """Reorder within the catalogue; before=None moves to the end."""
        item = self.get_catalogue_item(ref)
        self.catalogue.remove(item)
        if before is None:
            self.catalogue.append(item)
            return
        anchor = self.get_catalogue_item(before)
        self.catalogue.insert(self.catalogue.index(anchor), item)

    def import_catalogue(self, entries: list[dict[str, Any]]) -> dict[str, list[str]]:
        """BR-STOCK-08 / BR-RCPT-04: bulk upsert by name. All-or-nothing."""
        backup = deepcopy(self.data)
        added: list[str] = []
        updated: list[str] = []
        try:
            for entry in entries:
                name = clean(entry.get("name"))
                fields = {k: entry.get(k) for k in ("location", "aisle", "note", "icon", "qty")}
                if existing := self.find_catalogue(name):
                    self.update_catalogue_item(
                        existing["id"], **{k: v for k, v in fields.items() if v is not None}
                    )
                    if entry.get("kind"):
                        self.set_kind(existing["id"], entry["kind"])
                    updated.append(existing["name"])
                else:
                    self.add_catalogue_item(name, entry.get("kind") or OCCASIONAL, **fields)
                    added.append(name)
        except ShoppingError as err:
            self.data.clear()
            self.data.update(backup)
            raise ShoppingError(f"Import cancelled, nothing changed. {err}") from err
        return {"added": added, "updated": updated}

    def set_image(self, ref: str, image: dict[str, Any] | None, *, force: bool = False) -> None:
        """BR-IMG-05/06. image = {file, source, attribution}. Own photos win."""
        item = self.get_catalogue_item(ref)
        if image is not None:
            if image.get("source") not in IMAGE_SOURCES:
                raise ShoppingError(f"Image source must be one of {', '.join(IMAGE_SOURCES)}")
            current = item.get("image")
            if (
                current
                and current.get("source") == "own"
                and image["source"] != "own"
                and not force
            ):
                raise ShoppingError(f"'{item['name']}' already has your own photo")
        item["image"] = image

    # ================================================================== shop

    @property
    def shop(self) -> dict[str, Any] | None:
        return self.data["shop"]

    def _require_shop(self) -> dict[str, Any]:
        if self.shop is None:
            raise ShoppingError("There's no shop open. Start a new shop first")
        return self.shop

    def new_shop(self, store: str | None = None) -> dict[str, Any]:
        """BR-SHOP-01: one open shop at a time. BR-SHOP-08: starts empty."""
        if self.shop is not None:
            raise ShoppingError("A shop is already open. Finish or cancel it first")
        self.data["shop"] = {
            "id": _new_id(),
            "store": clean(store) or None,
            "state": PLANNING,
            "created": self._ts(),
            "started": None,
            "items": [],
        }
        return self.shop

    def start_shopping(self, store: str | None = None) -> dict[str, Any]:
        """BR-SHOP-03: planning -> shopping, by hand."""
        shop = self._require_shop()
        if clean(store):
            shop["store"] = clean(store)
        if shop["state"] == PLANNING:
            shop["state"] = SHOPPING
            shop["started"] = self._ts()
        return shop

    def set_store(self, store: str | None) -> dict[str, Any]:
        """BR-SHOP-05: optional store name; blank clears it."""
        shop = self._require_shop()
        shop["store"] = clean(store) or None
        return shop

    def cancel_shop(self) -> None:
        """BR-SHOP-09: discard the open shop, planning or shopping; no history kept."""
        self._require_shop()
        self.data["shop"] = None

    # -------------------------------------------------------------- history

    def history_page(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """BR-HIST-02/04: finished shops, newest first, a page at a time."""
        newest_first = list(reversed(self.data["history"]))
        return {
            "total": len(newest_first),
            "shops": newest_first[offset : offset + limit],
        }

    def repeat_shop(self, shop_id: str) -> dict[str, Any]:
        """BR-HIST-05: open a new shop with a past shop's items and quantities."""
        record = next((h for h in self.data["history"] if h["id"] == shop_id), None)
        if record is None:
            raise ShoppingError("That shop isn't in the history")
        if self.shop is not None:
            raise ShoppingError("A shop is already open. Finish or cancel it first")
        shop = self.new_shop(record.get("store"))
        for entry in record["got"] + record["missing"] + record["not_got"]:
            # Prefer the catalogue item (it may have been renamed since).
            catalogue = self.find_catalogue(entry.get("catalogue_id"))
            self.add_item(
                catalogue["name"] if catalogue else entry["name"],
                qty=entry.get("qty", 1),
            )
        return shop

    def finish_shop(self) -> dict[str, Any]:
        """BR-SHOP-04/06/07: close the shop and record the summary."""
        shop = self._require_shop()
        if shop["state"] != SHOPPING:
            raise ShoppingError("Shopping hasn't started yet. Start shopping first")

        def entries(state: str) -> list[dict[str, Any]]:
            return [
                # BR-HIST-03, BR-QTY-04
                {"name": i["name"], "qty": i.get("qty", 1), "catalogue_id": i.get("catalogue_id")}
                for i in shop["items"]
                if i["state"] == state
            ]

        record = {
            "id": shop["id"],
            "store": shop["store"],
            "created": shop["created"],
            "started": shop["started"],
            "finished": self._ts(),
            "missing": entries(MISSING),
            "got": entries(GOT),
            "not_got": entries(NEEDED),
        }
        history = self.data["history"]
        history.append(record)
        del history[:-MAX_HISTORY]  # BR-HIST-01
        self.data["shop"] = None
        self._fire(EVENT_SHOP_FINISHED, record)
        return record

    # ------------------------------------------------------------ shop items

    def find_item(self, ref: str) -> dict[str, Any]:
        """Find a shop item by id or name, preferring one that's still needed."""
        shop = self._require_shop()
        for item in shop["items"]:
            if item["id"] == ref:
                return item
        matches = [i for i in shop["items"] if norm(i["name"]) == norm(ref)]
        if not matches:
            raise ShoppingError(f"'{ref}' isn't on the shop list")
        return next((i for i in matches if i["state"] == NEEDED), matches[0])

    def add_item(
        self,
        name: str,
        *,
        note: str | None = None,
        aisle: str | None = None,
        qty: int | None = None,
        remember: bool = True,
    ) -> dict[str, Any]:
        """BR-ITEM-01..04. Creates a shop if none is open (BR-SHOP-02).

        Catalogue items copy their aisle and note. Anything else is a one-off,
        which is remembered as an occasional item (BR-OCC-02).
        """
        name = clean(name)
        if not name:
            raise ShoppingError("A name is required")
        aisle_id = self.group_id(AISLES, aisle) if aisle else None
        qty = check_qty(qty) if qty is not None else None
        if self.shop is None:
            self.new_shop()
        entry = self.find_catalogue(name)
        if entry is None and remember:
            entry = self.add_catalogue_item(name, OCCASIONAL, aisle=aisle_id, note=note)
        item = {
            "id": _new_id(),
            "name": entry["name"] if entry else name,
            "note": clean(note) if note is not None else (entry or {}).get("note", ""),
            "aisle": aisle_id or (entry or {}).get("aisle") or OTHER_ID,
            "catalogue_id": entry["id"] if entry else None,
            # BR-QTY-02: given amount, else the catalogue's usual amount, else 1.
            "qty": qty or (entry or {}).get("qty") or 1,
            "state": NEEDED,
            "state_at": None,
            "added": self._ts(),
        }
        self.shop["items"].append(item)  # BR-ITEM-02: duplicates allowed
        return item

    def add_items(self, entries: list[str | dict[str, Any]]) -> list[dict[str, Any]]:
        """Add several items; each is a name or {name, qty?, note?, aisle?}."""
        out = []
        for entry in entries:
            if isinstance(entry, str):
                if clean(entry):
                    out.append(self.add_item(entry))
                continue
            out.append(
                self.add_item(
                    entry.get("name", ""),
                    note=entry.get("note"),
                    aisle=entry.get("aisle"),
                    qty=entry.get("qty"),
                )
            )
        return out

    def update_item(
        self,
        ref: str,
        *,
        name: str | None = None,
        note: str | None = None,
        aisle: str | None = None,
        qty: int | None = None,
    ) -> dict[str, Any]:
        item = self.find_item(ref)
        if qty is not None:
            item["qty"] = check_qty(qty)  # BR-QTY-03: the shop's amount only
        if name is not None:
            if not clean(name):
                raise ShoppingError("A name is required")
            item["name"] = clean(name)
        if note is not None:
            item["note"] = clean(note)
        if aisle is not None:
            item["aisle"] = self.group_id(AISLES, aisle)
            # BR-OCC-02: changing the aisle on the list updates the remembered aisle.
            if entry := self.find_catalogue(item.get("catalogue_id")):
                entry["aisle"] = item["aisle"]
        return item

    def set_item_state(self, ref: str, state: str) -> dict[str, Any]:
        """BR-ITEM-05/06/07: any state to any state, in planning or shopping."""
        if state not in ITEM_STATES:
            raise ShoppingError(f"State must be one of {', '.join(ITEM_STATES)}")
        item = self.find_item(ref)
        if item["state"] == state:
            return item
        item["state"] = state
        item["state_at"] = None if state == NEEDED else self._ts()
        if state == MISSING:
            self._fire(
                EVENT_ITEM_MISSING,
                {"item": item["name"], "store": self.shop["store"]},
            )
        return item

    def remove_item(self, ref: str) -> None:
        item = self.find_item(ref)
        self.shop["items"].remove(item)

    def remove_items(self, item_ids: list[str]) -> None:
        shop = self._require_shop()
        drop = set(item_ids)
        shop["items"] = [i for i in shop["items"] if i["id"] not in drop]

    def move_item(self, ref: str, after: str | None) -> None:
        """Reorder; after=None moves to the top (matches HA's to-do move API)."""
        shop = self._require_shop()
        item = self.find_item(ref)
        shop["items"].remove(item)
        if after is None:
            shop["items"].insert(0, item)
            return
        anchor = self.find_item(after)
        shop["items"].insert(shop["items"].index(anchor) + 1, item)

    def toggle_stock(self, ref: str, on: bool) -> None:
        """BR-ITEM-03: the stock check toggle."""
        entry = self.get_catalogue_item(ref)
        linked = [i for i in (self.shop or {}).get("items", []) if i.get("catalogue_id") == entry["id"]]
        if on:
            if not linked:
                self.add_item(entry["name"])
            return
        if self.shop:
            # Only items still needed are removed; got/missing ones are history.
            self.shop["items"] = [
                i for i in self.shop["items"] if not (i in linked and i["state"] == NEEDED)
            ]

    # ============================================================== queries

    def stock_check(self) -> list[dict[str, Any]]:
        """Stock grouped by home location, in location order (BR-STOCK-04)."""
        on_list = {
            i.get("catalogue_id") for i in (self.shop or {}).get("items", [])
        }
        out = []
        for group in self.groups(LOCATIONS):
            items = [
                {**self.describe_catalogue_item(c), "on_list": c["id"] in on_list}
                for c in self.catalogue
                if c["kind"] == STOCK and c["location"] == group["id"]
            ]
            if items:
                out.append({**group, "items": items})
        return out

    def shop_by_aisle(self) -> list[dict[str, Any]]:
        """BR-ITEM-08: items grouped by aisle; done items drop to the bottom."""
        shop = self._require_shop()
        out = []
        for group in self.groups(AISLES):
            items = [i for i in shop["items"] if i["aisle"] == group["id"]]
            if items:
                items.sort(key=lambda i: i["state"] != NEEDED)  # stable sort
                out.append({**group, "items": [self.describe_shop_item(i) for i in items]})
        return out

    def describe_catalogue_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            **item,
            "icon": self.icon_for(item),
            "icon_custom": bool(item.get("icon")),
            "location_name": self.group(LOCATIONS, item["location"])["name"],
            "aisle_name": self.group(AISLES, item["aisle"])["name"],
        }

    def describe_shop_item(self, item: dict[str, Any]) -> dict[str, Any]:
        entry = self.find_catalogue(item.get("catalogue_id"))
        return {
            **item,
            "icon": self.icon_for(entry or item),
            "image": (entry or {}).get("image"),
            "kind": (entry or {}).get("kind"),
            "aisle_name": self.group(AISLES, item["aisle"])["name"],
        }

    def snapshot(self) -> dict[str, Any]:
        """Everything a UI needs in one payload."""
        return {
            "locations": self.groups(LOCATIONS),
            "aisles": self.groups(AISLES),
            "catalogue": [self.describe_catalogue_item(c) for c in self.catalogue],
            "stock_check": self.stock_check(),
            "shop": (
                {
                    **self.shop,
                    # Items carry their catalogue details (icon, photo, kind).
                    "items": [self.describe_shop_item(i) for i in self.shop["items"]],
                    "by_aisle": self.shop_by_aisle(),
                }
                if self.shop
                else None
            ),
            "last_shop": self.data["history"][-1] if self.data["history"] else None,
        }
