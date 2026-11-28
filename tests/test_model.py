"""Business-rule tests for model.py. Each test names the rule(s) it covers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import pathlib
import sys

import pytest

# Load model.py without importing the HA package __init__.
_PKG = pathlib.Path(__file__).parents[1] / "custom_components" / "household_shopping"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"hs_pure.{name}", _PKG / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if "hs_pure" not in sys.modules:
    import types

    pkg = types.ModuleType("hs_pure")
    pkg.__path__ = [str(_PKG)]
    sys.modules["hs_pure"] = pkg
icons = _load("icons_map")
m = _load("model")


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 27, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def events():
    return []


@pytest.fixture
def model(events):
    return m.ShoppingModel(now=Clock(), fire=lambda e, d: events.append((e, d)))


def stock(model, name, location="Fridge", aisle="Dairy & Eggs", **kw):
    return model.add_catalogue_item(name, m.STOCK, location=location, aisle=aisle, **kw)


# ---------------------------------------------------------------- catalogue

def test_catalogue_names_unique_case_insensitive(model):  # BR-STOCK-01, BR-OCC-01
    stock(model, "Full cream milk")
    with pytest.raises(m.ShoppingError):
        model.add_catalogue_item("  full   CREAM milk ", m.OCCASIONAL)


def test_missing_groups_default_to_other(model):  # BR-STOCK-07
    item = model.add_catalogue_item("Thing", m.STOCK)
    assert item["location"] == m.OTHER_ID and item["aisle"] == m.OTHER_ID


def test_unknown_group_is_rejected(model):  # BR-STOCK-06
    with pytest.raises(m.ShoppingError, match="Unknown aisle"):
        model.add_catalogue_item("Thing", m.STOCK, aisle="Aisle 99")


def test_group_edit_and_delete_moves_items_to_other(model):  # BR-STOCK-06
    model.add_group(m.LOCATIONS, "Garage")
    assert model.groups(m.LOCATIONS)[-1]["id"] == m.OTHER_ID  # Other stays last
    item = stock(model, "Soft drink", location="garage", aisle="Drinks")
    model.add_item("Soft drink")
    model.remove_group(m.AISLES, "Drinks")
    assert item["aisle"] == m.OTHER_ID
    assert model.shop["items"][0]["aisle"] == m.OTHER_ID
    with pytest.raises(m.ShoppingError):
        model.remove_group(m.LOCATIONS, "Other")


def test_group_order(model):  # BR-STOCK-04/05
    model.order_groups(m.AISLES, ["Frozen", "Other", "Bakery"])
    names = [g["name"] for g in model.groups(m.AISLES)]
    assert names[:2] == ["Frozen", "Bakery"] and names[-1] == "Other"


def test_catalogue_edits_do_not_touch_open_shop(model):  # BR-STOCK-02, BR-STOCK-05
    stock(model, "Milk", note="3L")
    item = model.add_item("Milk")
    model.update_catalogue_item("Milk", name="Milk 3L", note="Dairy Farmers")
    assert item["name"] == "Milk" and item["note"] == "3L"


def test_promote_and_demote(model):  # BR-OCC-04
    model.add_catalogue_item("Sunscreen", m.OCCASIONAL, aisle="Health & Beauty")
    model.set_kind("sunscreen", m.STOCK, location="Bathroom")
    entry = model.get_catalogue_item("Sunscreen")
    assert entry["kind"] == m.STOCK and entry["location"] == "bathroom"
    model.set_kind("Sunscreen", m.OCCASIONAL)
    assert entry["kind"] == m.OCCASIONAL


def test_import_upserts_and_is_all_or_nothing(model):  # BR-STOCK-08, BR-RCPT-04
    stock(model, "Milk")
    result = model.import_catalogue([
        {"name": "milk", "note": "Dairy Farmers 3L"},
        {"name": "Broccoli", "kind": "stock", "location": "Fridge", "aisle": "Fruit & Veg"},
    ])
    assert result == {"added": ["Broccoli"], "updated": ["Milk"]}
    assert model.get_catalogue_item("Milk")["note"] == "Dairy Farmers 3L"
    before = len(model.catalogue)
    with pytest.raises(m.ShoppingError, match="nothing changed"):
        model.import_catalogue([{"name": "Bread"}, {"name": "Bad", "aisle": "Nope"}])
    assert len(model.catalogue) == before


def test_icons(model):  # BR-IMG-02
    assert icons.guess_icon("Gold sweet potato") == "🍠"
    assert icons.guess_icon("WW Sour Cream 300ml") == "🥛"
    assert icons.guess_icon("Allen's Jelly Beans") == "🍬"
    assert icons.guess_icon("Bananas") == "🍌" and icons.guess_icon("Mangoes") == "🥭"
    assert icons.guess_icon("Apples") == "🍎" and icons.guess_icon("Pineapple pieces") == "🍍"
    odd = model.add_catalogue_item("Zzz", m.STOCK, aisle="Frozen")
    assert model.icon_for(odd) == "🧊"  # falls back to aisle icon
    model.update_catalogue_item("Zzz", icon="⭐")
    assert model.icon_for(odd) == "⭐"


def test_own_photo_wins(model):  # BR-IMG-05/06
    stock(model, "Yoghurt")
    model.set_image("Yoghurt", {"file": "a.jpg", "source": "own", "attribution": None})
    with pytest.raises(m.ShoppingError, match="own photo"):
        model.set_image("Yoghurt", {"file": "b.jpg", "source": "openfoodfacts", "attribution": "OFF"})
    with pytest.raises(m.ShoppingError):
        model.set_image("Yoghurt", {"file": "c.jpg", "source": "google"})


# --------------------------------------------------------------------- shop

def test_one_open_shop(model):  # BR-SHOP-01
    model.new_shop()
    with pytest.raises(m.ShoppingError):
        model.new_shop()


def test_adding_item_creates_shop(model):  # BR-SHOP-02
    assert model.shop is None
    model.add_item("Milk")
    assert model.shop["state"] == m.PLANNING


def test_new_shop_starts_empty_no_carry_over(model):  # BR-SHOP-08
    model.add_item("Eggs")
    model.start_shopping()
    model.set_item_state("Eggs", m.MISSING)
    model.finish_shop()
    assert model.new_shop()["items"] == []


def test_lifecycle_and_summary(model, events):  # BR-SHOP-03/04/06/07, BR-HIST-03
    stock(model, "Milk")
    model.new_shop(store="Woolworths Woden")
    for n in ("Milk", "Eggs", "Bread"):
        model.add_item(n)
    with pytest.raises(m.ShoppingError, match="Start shopping"):
        model.finish_shop()
    model.start_shopping()
    assert model.shop["state"] == m.SHOPPING and model.shop["started"]
    model.set_item_state("Milk", m.GOT)
    model.set_item_state("Eggs", m.MISSING)
    record = model.finish_shop()
    assert [x["name"] for x in record["missing"]] == ["Eggs"]
    assert [x["name"] for x in record["got"]] == ["Milk"]
    assert [x["name"] for x in record["not_got"]] == ["Bread"]
    assert record["got"][0]["catalogue_id"] == model.get_catalogue_item("Milk")["id"]
    assert record["store"] == "Woolworths Woden"
    assert model.shop is None
    assert [e for e, _ in events] == [m.EVENT_ITEM_MISSING, m.EVENT_SHOP_FINISHED]


def test_cancel_planning_or_shopping_keeps_no_history(model):  # BR-SHOP-09
    model.new_shop()
    model.cancel_shop()
    assert model.shop is None and model.data["history"] == []
    model.add_item("Milk")
    model.start_shopping()
    model.set_item_state("Milk", m.GOT)
    model.cancel_shop()  # allowed mid-shop since v1.3
    assert model.shop is None and model.data["history"] == []
    with pytest.raises(m.ShoppingError):
        model.cancel_shop()


def test_finish_without_shop_errors(model):  # BR-SHOP-07 / §7.4
    with pytest.raises(m.ShoppingError, match="no shop open"):
        model.finish_shop()


def test_history_capped(model):  # BR-HIST-01
    for _ in range(m.MAX_HISTORY + 5):
        model.new_shop()
        model.start_shopping()
        model.finish_shop()
    assert len(model.data["history"]) == m.MAX_HISTORY


# --------------------------------------------------------------- shop items

def test_empty_name_rejected(model):  # BR-ITEM-01
    with pytest.raises(m.ShoppingError):
        model.add_item("   ")


def test_duplicates_allowed(model):  # BR-ITEM-02
    model.add_item("Milk")
    model.add_item("milk")
    assert len(model.shop["items"]) == 2


def test_catalogue_item_copies_aisle_and_note(model):  # BR-ITEM-01
    stock(model, "Tasty cheese", aisle="Deli", note="Bega 500g")
    item = model.add_item("tasty cheese")
    assert item["name"] == "Tasty cheese" and item["aisle"] == "deli"
    assert item["note"] == "Bega 500g"


def test_one_off_remembered_as_occasional(model):  # BR-OCC-02
    item = model.add_item("Birthday candles", aisle="Household")
    entry = model.get_catalogue_item("Birthday candles")
    assert entry["kind"] == m.OCCASIONAL and entry["aisle"] == "household"
    assert item["catalogue_id"] == entry["id"]
    model.update_item(item["id"], aisle="Other")
    assert entry["aisle"] == m.OTHER_ID  # aisle change updates the memory


def test_states_any_to_any_including_planning(model):  # BR-ITEM-04..07
    item = model.add_item("Milk")
    assert item["state"] == m.NEEDED
    model.set_item_state("Milk", m.GOT)  # allowed during planning
    assert item["state_at"]
    model.set_item_state(item["id"], m.MISSING)
    model.set_item_state(item["id"], m.NEEDED)
    assert item["state_at"] is None
    with pytest.raises(m.ShoppingError):
        model.set_item_state(item["id"], "lost")


def test_stock_check_toggle(model):  # BR-ITEM-03, BR-STOCK-04
    stock(model, "Milk")
    stock(model, "Rice", location="Pantry", aisle="Pantry")
    model.toggle_stock("Milk", True)
    model.toggle_stock("Milk", True)  # no duplicate from the toggle
    assert len(model.shop["items"]) == 1
    check = model.stock_check()
    assert [g["name"] for g in check] == ["Fridge", "Pantry"]
    assert check[0]["items"][0]["on_list"] is True
    model.toggle_stock("Milk", False)
    assert model.shop["items"] == []
    # Off doesn't remove an item that's already been dealt with.
    model.toggle_stock("Rice", True)
    model.set_item_state("Rice", m.GOT)
    model.toggle_stock("Rice", False)
    assert len(model.shop["items"]) == 1


def test_shop_grouped_by_aisle_done_last(model):  # BR-ITEM-08
    stock(model, "Milk", aisle="Dairy & Eggs")
    stock(model, "Yoghurt", aisle="Dairy & Eggs")
    stock(model, "Broccoli", aisle="Fruit & Veg")
    for n in ("Milk", "Yoghurt", "Broccoli"):
        model.add_item(n)
    model.set_item_state("Milk", m.GOT)
    groups = model.shop_by_aisle()
    assert [g["name"] for g in groups] == ["Fruit & Veg", "Dairy & Eggs"]
    assert [i["name"] for i in groups[1]["items"]] == ["Yoghurt", "Milk"]


def test_find_prefers_needed(model):
    a = model.add_item("Milk")
    b = model.add_item("Milk")
    model.set_item_state(a["id"], m.GOT)
    assert model.find_item("milk") is b


def test_remove_catalogue_unlinks_shop_items(model):
    stock(model, "Milk")
    item = model.add_item("Milk")
    model.remove_catalogue_item("Milk")
    assert item["catalogue_id"] is None


# ---------------------------------------------------------------- quantities

def test_qty_defaults_and_validation(model):  # BR-QTY-01/02
    item = model.add_item("Milk")
    assert item["qty"] == 1
    stock(model, "Bananas", qty=5)
    assert model.add_item("Bananas")["qty"] == 5  # usual amount
    assert model.add_item("bananas", qty=2)["qty"] == 2  # explicit wins
    for bad in (0, 100, 2.5, "two", True, [2]):
        with pytest.raises(m.ShoppingError):
            model.add_item("Eggs", qty=bad)


def test_qty_change_is_shop_only(model):  # BR-QTY-03
    entry = stock(model, "Milk", qty=2)
    item = model.add_item("Milk")
    model.update_item(item["id"], qty=4)
    assert item["qty"] == 4 and entry["qty"] == 2
    model.update_catalogue_item("Milk", qty=3)
    assert item["qty"] == 4 and entry["qty"] == 3


def test_qty_in_summary(model):  # BR-QTY-04
    model.add_items(["Bread", {"name": "Bananas", "qty": 5}])
    model.start_shopping()
    model.set_item_state("Bananas", m.MISSING)
    record = model.finish_shop()
    assert record["missing"][0]["qty"] == 5 and record["not_got"][0]["qty"] == 1


def test_toggle_stock_uses_usual_qty(model):  # BR-QTY-02, BR-ITEM-03
    stock(model, "Yoghurt", qty=7)
    model.toggle_stock("Yoghurt", True)
    assert model.shop["items"][0]["qty"] == 7


def test_import_sets_qty(model):  # BR-QTY-02
    model.import_catalogue([{"name": "Milk", "kind": "stock", "qty": 2}])
    assert model.get_catalogue_item("Milk")["qty"] == 2


def test_normalise_old_data():  # NFR-02
    old = m.default_data()
    old["catalogue"].append({"id": "a", "name": "Milk", "kind": "stock", "location": "fridge", "aisle": "dairy_eggs", "note": "", "icon": None, "image": None})
    old["shop"] = {"id": "s", "store": None, "state": "planning", "created": "x", "started": None,
                   "items": [{"id": "i", "name": "Milk", "note": "", "aisle": "dairy_eggs", "catalogue_id": "a", "state": "needed", "state_at": None, "added": "x"}]}
    old["history"].append({"missing": [{"name": "Eggs", "catalogue_id": None}], "got": [], "not_got": []})
    data = m.normalise(old)
    assert data["catalogue"][0]["qty"] == 1 and data["shop"]["items"][0]["qty"] == 1
    assert data["history"][0]["missing"][0]["qty"] == 1


# ------------------------------------------------------------------ history

def _finish(model, items, store=None):
    model.new_shop(store)
    model.add_items(items)
    model.start_shopping()
    return model.finish_shop()


def test_history_page_newest_first(model):  # BR-HIST-02/04
    ids = [_finish(model, ["Milk"], store=f"S{i}")["id"] for i in range(5)]
    page = model.history_page(limit=2)
    assert page["total"] == 5 and [s["id"] for s in page["shops"]] == ids[::-1][:2]
    assert [s["id"] for s in model.history_page(limit=2, offset=4)["shops"]] == ids[:1]


def test_repeat_shop(model):  # BR-HIST-05
    stock(model, "Milk")
    model.new_shop("Coles")
    model.add_items([{"name": "Milk", "qty": 2}, "Eggs", "Bread"])
    model.start_shopping()
    model.set_item_state("Milk", m.GOT)
    model.set_item_state("Eggs", m.MISSING)
    record = model.finish_shop()
    model.update_catalogue_item("Milk", name="Full cream milk")  # renamed since
    with pytest.raises(m.ShoppingError):
        model.repeat_shop("nope")
    shop = model.repeat_shop(record["id"])
    assert shop["store"] == "Coles" and shop["state"] == m.PLANNING
    assert [(i["name"], i["qty"], i["state"]) for i in shop["items"]] == [
        ("Full cream milk", 2, m.NEEDED), ("Eggs", 1, m.NEEDED), ("Bread", 1, m.NEEDED)
    ]
    with pytest.raises(m.ShoppingError, match="already open"):
        model.repeat_shop(record["id"])


# ------------------------------------------------------------- quick shops

def test_quick_shop_alongside_main(model):  # BR-QUICK-01/02/04
    stock(model, "Milk", aisle="Dairy & Eggs")
    main = model.new_shop()
    model.add_item("Bread")
    quick = model.new_quick_shop(store="Aldi", assignee="person.kelsie")
    assert quick["state"] == m.SHOPPING and quick["started"] and quick["kind"] == m.QUICK
    assert [s["id"] for s in model.open_shops] == [main["id"], quick["id"]]
    model.add_item("Milk", shop_id=quick["id"])
    model.add_item("Birthday card", shop_id=quick["id"])
    assert len(main["items"]) == 1 and len(quick["items"]) == 2
    # Catalogue items still link; one-offs aren't remembered on a quick shop (BR-QUICK-03).
    assert quick["items"][0]["catalogue_id"] and quick["items"][0]["aisle"] == "dairy_eggs"
    assert model.find_catalogue("Birthday card") is None
    model.add_item("Balloons", shop_id=quick["id"], remember=True)
    assert model.find_catalogue("Balloons")["kind"] == m.OCCASIONAL
    # Items found by id in any open shop; by name within the given shop.
    model.set_item_state(quick["items"][1]["id"], m.GOT)
    model.set_item_state("Milk", m.MISSING, shop_id=quick["id"])
    with pytest.raises(m.ShoppingError):
        model.set_item_state("Milk", m.GOT)  # not on the main shop
    record = model.finish_shop(quick["id"])
    assert record["kind"] == m.QUICK and record["assignee"] == "person.kelsie"
    assert record["store"] == "Aldi" and [i["name"] for i in record["missing"]] == ["Milk"]
    assert model.shop is main and model.quick_shops == []


def test_quick_shop_without_main_and_cancel(model):  # BR-QUICK-01, BR-SHOP-09
    quick = model.new_quick_shop()
    assert model.shop is None
    model.add_item("Milk")  # no shop_id: opens a main shop, doesn't touch the quick one
    assert model.shop is not None and quick["items"] == []
    model.cancel_shop(quick["id"])
    assert model.quick_shops == [] and model.shop is not None
    with pytest.raises(m.ShoppingError, match="isn't open"):
        model.finish_shop(quick["id"])


def test_quick_shop_limit_and_assign(model):  # BR-QUICK-01, BR-ASSIGN-01
    shops = [model.new_quick_shop() for _ in range(m.MAX_QUICK_SHOPS)]
    with pytest.raises(m.ShoppingError):
        model.new_quick_shop()
    model.assign_shop(shops[0]["id"], "person.elijah")
    assert shops[0]["assignee"] == "person.elijah"
    model.assign_shop(shops[0]["id"], None)
    assert shops[0]["assignee"] is None


def test_normalise_adds_quick_shops():  # NFR-02
    old = m.default_data()
    del old["quick_shops"]
    old["shop"] = {"id": "s", "store": None, "state": "planning", "created": "x", "started": None, "items": []}
    data = m.normalise(old)
    assert data["quick_shops"] == [] and data["shop"]["kind"] == m.MAIN and data["shop"]["assignee"] is None


# ---------------------------------------------------------------- cash out


def test_cash_out_is_one_line_with_an_amount(model):  # BR-CASH-01
    model.new_shop()
    cash = model.add_cash_out(200, note="for the cleaner")
    assert cash["type"] == m.CASH and cash["amount"] == 200 and cash["note"] == "for the cleaner"
    assert cash["catalogue_id"] is None and not model.catalogue  # never remembered
    again = model.add_cash_out(150)
    assert again is cash and cash["amount"] == 150
    assert len([i for i in model.shop["items"] if i.get("type") == m.CASH]) == 1
    for bad in (0, 1001, 12.5, "lots", True):
        with pytest.raises(m.ShoppingError):
            model.add_cash_out(bad)
    assert model.add_cash_out("$300")["amount"] == 300


def test_cash_out_cannot_take_quantity_aisle_or_go_on_other_items(model):  # BR-CASH-01
    model.new_shop()
    model.add_item("Milk")
    model.add_cash_out(200)
    with pytest.raises(m.ShoppingError):
        model.update_item("Cash out", qty=2)
    with pytest.raises(m.ShoppingError):
        model.update_item("Cash out", aisle="Dairy & Eggs")
    with pytest.raises(m.ShoppingError):
        model.update_item("Milk", amount=50)
    assert model.update_item("Cash out", amount=250, note="cleaner")["amount"] == 250


def test_cash_out_defaults_to_last_amount(model):  # BR-CASH-02
    model.new_shop()
    assert model.add_cash_out()["amount"] == m.DEFAULT_CASH
    model.update_item("Cash out", amount=200)
    model.cancel_shop()
    model.new_shop()
    assert model.add_cash_out()["amount"] == 200


def test_cash_out_opens_a_shop_and_works_on_quick_shops(model):  # BR-CASH-01, BR-SHOP-02
    assert model.add_cash_out(50)["amount"] == 50
    assert model.shop is not None
    quick = model.new_quick_shop("Aldi")
    model.add_cash_out(80, shop_id=quick["id"])
    assert [i["amount"] for i in quick["items"]] == [80]
    assert [i["amount"] for i in model.shop["items"]] == [50]


def test_cash_out_listed_last_under_checkout(model):  # BR-CASH-03
    stock(model, "Milk")
    model.new_shop()
    model.add_cash_out(200)
    model.add_item("Milk")
    groups = model.shop_by_aisle()
    assert groups[-1]["id"] == m.CHECKOUT_ID and groups[-1]["name"] == "Checkout"
    assert [i["name"] for i in groups[-1]["items"]] == ["Cash out"]
    assert all(i.get("type") != m.CASH for g in groups[:-1] for i in g["items"])
    described = groups[-1]["items"][0]
    assert described["icon"] == m.CASH_ICON and described["aisle_name"] == "Checkout"
    # An aisle the user happens to call "Checkout" doesn't swallow it twice.
    model.add_group(m.AISLES, "Checkout")
    assert sum(len(g["items"]) for g in model.shop_by_aisle()) == 2
    model.set_item_state("Cash out", m.GOT)
    assert model.find_item("Cash out")["state"] == m.GOT


def test_cash_out_recorded_on_finish_and_repeated(model, events):  # BR-CASH-04, BR-CASH-05
    model.new_shop("Woolworths Woden")
    model.add_item("Milk")
    model.add_cash_out(200, note="cleaner")
    model.start_shopping()
    model.set_item_state("Milk", m.GOT)
    model.set_item_state("Cash out", m.GOT)
    record = model.finish_shop()
    assert record["cash_out"] == {"amount": 200, "state": m.GOT, "note": "cleaner"}
    assert [i["name"] for i in record["got"]] == ["Milk"]  # cash isn't a grocery
    assert events[-1][1]["cash_out"]["amount"] == 200
    model.repeat_shop(record["id"])
    cash = model.find_item("Cash out")
    assert cash["amount"] == 200 and cash["note"] == "cleaner" and cash["state"] == m.NEEDED


def test_shop_without_cash_out_records_none(model):  # BR-CASH-04
    model.new_shop()
    model.add_item("Milk")
    model.start_shopping()
    assert model.finish_shop()["cash_out"] is None
