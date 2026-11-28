"""End-to-end tests through Home Assistant: config flow, entities, actions, websocket."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from homeassistant import config_entries
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.household_shopping.const import DOMAIN

TODO = "todo.shopping"
SENSOR = "sensor.shopping_shop"


async def call(hass, service, response=False, **data):
    return await hass.services.async_call(
        DOMAIN, service, {"entity_id": TODO, **data}, blocking=True, return_response=response
    )


def snapshot(result):
    return result[TODO]


async def test_config_flow(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Groceries"})
    assert result["type"] == "create_entry" and result["title"] == "Groceries"


async def test_entities_created(hass, entry):
    assert hass.states.get(TODO).state == "0"
    assert hass.states.get(SENSOR).state == "none"


async def test_full_shop_flow(hass, entry):  # §1.1 end to end
    finished = async_capture_events(hass, f"{DOMAIN}_shop_finished")
    missing = async_capture_events(hass, f"{DOMAIN}_item_missing")

    await call(hass, "import_catalogue", items=[
        {"name": "Full cream milk", "kind": "stock", "location": "Fridge", "aisle": "Dairy & Eggs", "note": "Dairy Farmers 3L"},
        {"name": "Broccoli", "kind": "stock", "location": "Fridge", "aisle": "Fruit & Veg"},
        {"name": "Sunscreen", "aisle": "Health & Beauty"},
    ])
    await call(hass, "new_shop", store="Woolworths Woden")
    await call(hass, "toggle_stock", name="full cream milk", on=True)
    await call(hass, "toggle_stock", name="Broccoli", on=True)
    await call(hass, "add_item", name="Birthday candles", aisle="Household")
    assert hass.states.get(SENSOR).state == "planning"
    assert hass.states.get(TODO).state == "3"

    data = snapshot(await call(hass, "get_catalogue", response=True))
    assert [g["name"] for g in data["shop"]["by_aisle"]] == ["Fruit & Veg", "Dairy & Eggs", "Household"]
    candles = next(c for c in data["catalogue"] if c["name"] == "Birthday candles")
    assert candles["kind"] == "occasional"  # BR-OCC-02

    await call(hass, "start_shopping")
    await call(hass, "set_item_state", item="Full cream milk", state="got")
    await call(hass, "set_item_state", item="Broccoli", state="missing")
    assert hass.states.get(SENSOR).attributes["missing_items"] == ["Broccoli"]

    summary = snapshot(await call(hass, "finish_shop", response=True))
    assert [i["name"] for i in summary["missing"]] == ["Broccoli"]
    assert [i["name"] for i in summary["not_got"]] == ["Birthday candles"]
    await hass.async_block_till_done()
    assert len(finished) == 1 and len(missing) == 1
    assert finished[0].data["list"] == "Shopping"
    assert hass.states.get(SENSOR).state == "none"
    assert hass.states.get(SENSOR).attributes["last_shop_missing"] == ["Broccoli"]

    history = snapshot(await call(hass, "get_history", response=True, limit=5))
    assert len(history["shops"]) == 1


async def test_rule_errors_are_validation_errors(hass, entry):
    with pytest.raises(ServiceValidationError, match="no shop open"):
        await call(hass, "finish_shop")
    with pytest.raises(ServiceValidationError, match="Unknown aisle"):
        await call(hass, "add_stock_item", name="X", aisle="Aisle 99")


async def test_todo_entity_and_assist_path(hass, entry):  # §7.3, BR-SHOP-02
    await hass.services.async_call("todo", "add_item", {"entity_id": TODO, "item": "Milk"}, blocking=True)
    assert hass.states.get(SENSOR).state == "planning"
    await call(hass, "set_item_state", item="Milk", state="missing")
    items = await hass.services.async_call("todo", "get_items", {"entity_id": TODO}, blocking=True, return_response=True)
    item = items[TODO]["items"][0]
    assert item["status"] == "needs_action" and item["description"].startswith("❌ Missing")
    await hass.services.async_call(
        "todo", "update_item", {"entity_id": TODO, "item": "Milk", "status": "completed"}, blocking=True
    )
    data = snapshot(await call(hass, "get_catalogue", response=True))
    assert data["shop"]["items"][0]["state"] == "got"
    await hass.services.async_call("todo", "remove_item", {"entity_id": TODO, "item": "Milk"}, blocking=True)
    assert hass.states.get(TODO).state == "0"


async def test_persists_across_reload(hass, entry):  # BR-ITEM-09, NFR-02
    await call(hass, "add_stock_item", name="Rice", location="Pantry", aisle="Pantry")
    await call(hass, "add_item", name="Rice")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    data = snapshot(await call(hass, "get_catalogue", response=True))
    assert data["shop"]["items"][0]["name"] == "Rice"


async def test_image_upload_serve_and_cleanup(hass, entry, hass_client):  # BR-IMG-03/04/05/06
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1000), "red").save(buf, "PNG")
    await call(hass, "add_stock_item", name="Yoghurt")
    await call(hass, "set_item_image", name="Yoghurt", image_data=base64.b64encode(buf.getvalue()).decode(), source="own")
    data = snapshot(await call(hass, "get_catalogue", response=True))
    image = data["catalogue"][0]["image"]
    assert image["source"] == "own"

    client = await hass_client()
    resp = await client.get(image["url"])
    assert resp.status == 200
    img = Image.open(io.BytesIO(await resp.read()))
    assert max(img.size) == 512  # BR-IMG-04

    with pytest.raises(ServiceValidationError, match="own photo"):
        await call(hass, "set_item_image", name="Yoghurt", image_data=base64.b64encode(buf.getvalue()).decode(), source="openfoodfacts")

    await call(hass, "remove_catalogue_item", name="Yoghurt")
    assert (await client.get(image["url"])).status == 404
    assert (await client.get("/api/household_shopping/image/../../secrets.jpg")).status == 404


async def test_websocket_subscribe(hass, entry, hass_ws_client):
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    assert (await ws.receive_json())["success"]
    first = await ws.receive_json()
    assert first["event"]["shop"] is None and first["event"]["name"] == "Shopping"
    await call(hass, "add_item", name="Bread")
    update = await ws.receive_json()
    assert update["event"]["shop"]["items"][0]["name"] == "Bread"


async def test_remove_entry_deletes_data(hass, entry):  # NFR-08
    await call(hass, "add_item", name="Bread")
    await hass.async_block_till_done()
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_load() is None


async def test_quantities_end_to_end(hass, entry):  # BR-QTY-*
    await call(hass, "add_stock_item", name="Bananas", location="Fruit bowl", aisle="Fruit & Veg", qty=5)
    await call(hass, "new_shop", items=["Bread", {"name": "Milk", "qty": 2, "note": "3L"}])
    await call(hass, "toggle_stock", name="Bananas", on=True)
    await call(hass, "update_item", item="Bread", qty=3)
    items = (await hass.services.async_call(
        "todo", "get_items", {"entity_id": TODO}, blocking=True, return_response=True
    ))[TODO]["items"]
    by_name = {i["summary"]: i for i in items}
    assert by_name["Milk"]["description"] == "×2 · 3L"
    assert by_name["Bananas"]["description"].startswith("×5")
    assert by_name["Bread"]["description"] == "×3"
    # Editing the note in HA's own to-do UI keeps the quantity.
    await hass.services.async_call(
        "todo", "update_item", {"entity_id": TODO, "item": "Milk", "description": "×2 · Dairy Farmers"}, blocking=True
    )
    shop = snapshot(await call(hass, "get_catalogue", response=True))["shop"]
    milk = next(i for i in shop["items"] if i["name"] == "Milk")
    assert milk["qty"] == 2 and milk["note"] == "Dairy Farmers"
    with pytest.raises(Exception):
        await call(hass, "update_item", item="Milk", qty=0)


async def test_card_registered_as_dashboard_resource(hass, entry):  # §7.1
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.setup import async_setup_component

    from custom_components.household_shopping.frontend import (
        CARD_URL,
        async_register_card_resource,
        async_remove_card_resource,
    )

    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_get_info()
    # A stale entry (as added by hand) plus a duplicate.
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=0.3.0"})
    await resources.async_create_item({"res_type": "module", "url": CARD_URL})
    assert await async_register_card_resource(hass, f"{CARD_URL}?v=9.9.9")
    ours = [r for r in resources.async_items() if r["url"].startswith(CARD_URL)]
    assert [r["url"] for r in ours] == [f"{CARD_URL}?v=9.9.9"]
    await async_remove_card_resource(hass)
    assert not [r for r in resources.async_items() if r["url"].startswith(CARD_URL)]


async def test_history_websocket_and_repeat(hass, entry, hass_ws_client):  # BR-HIST-04/05
    await call(hass, "new_shop", store="Aldi", items=[{"name": "Pasta", "qty": 3}])
    await call(hass, "start_shopping")
    await call(hass, "finish_shop")
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": f"{DOMAIN}/history", "entity_id": TODO, "limit": 5})
    msg = await ws.receive_json()
    assert msg["success"] and msg["result"]["total"] == 1
    past = msg["result"]["shops"][0]
    assert past["store"] == "Aldi" and past["not_got"][0]["qty"] == 3
    result = snapshot(await call(hass, "repeat_shop", response=True, shop_id=past["id"]))
    assert result["shop_id"]
    shop = snapshot(await call(hass, "get_catalogue", response=True))["shop"]
    assert [(i["name"], i["qty"]) for i in shop["items"]] == [("Pasta", 3)]
    # Cancel mid-shop (BR-SHOP-09) leaves history unchanged.
    await call(hass, "start_shopping")
    await call(hass, "cancel_shop")
    assert hass.states.get(SENSOR).state == "none"
    await ws.send_json({"id": 2, "type": f"{DOMAIN}/history", "entity_id": TODO})
    assert (await ws.receive_json())["result"]["total"] == 1


async def _phones(hass):
    """Mirror the owner's setup: Elijah has a phone + watch, Kelsie a phone."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

    app = MockConfigEntry(domain="mobile_app")
    app.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    trackers = {}
    for key, name, model in (
        ("fold", "Elijah Fold", "SM-F956B"),
        ("watch", "Galaxy Watch7 (976L)", "Galaxy Watch7"),
        ("kel", "SM-S711B", "SM-S711B"),
    ):
        device = dev_reg.async_get_or_create(
            config_entry_id=app.entry_id, identifiers={("mobile_app", key)}, name=name, model=model
        )
        trackers[key] = ent_reg.async_get_or_create(
            "device_tracker", "mobile_app", key, device_id=device.id, suggested_object_id=key
        ).entity_id
    eli = await hass.auth.async_create_user("Elijah", group_ids=["system-admin"])
    kel = await hass.auth.async_create_user("Kelsie", group_ids=["system-admin"])
    hass.states.async_set("person.elijah", "home", {"device_trackers": [trackers["watch"], trackers["fold"]], "user_id": eli.id, "friendly_name": "Elijah"})
    hass.states.async_set("person.kelsie", "home", {"device_trackers": [trackers["kel"]], "user_id": kel.id, "friendly_name": "Kelsie"})
    return {
        "eli_user": eli.id,
        "fold": async_mock_service(hass, "notify", "mobile_app_elijah_fold"),
        "watch": async_mock_service(hass, "notify", "mobile_app_galaxy_watch7_976l"),
        "kel": async_mock_service(hass, "notify", "mobile_app_sm_s711b"),
    }


async def test_quick_shop_assign_and_notify(hass, entry):  # BR-QUICK-*, BR-ASSIGN-*
    from homeassistant.core import Context

    from custom_components.household_shopping.people import notify_targets, people

    calls = await _phones(hass)
    assert notify_targets(hass, "person.elijah") == ["mobile_app_elijah_fold"]  # watch skipped
    assert notify_targets(hass, "person.kelsie") == ["mobile_app_sm_s711b"]
    assert [p["name"] for p in people(hass)] == ["Elijah", "Kelsie"]

    eli = Context(user_id=calls["eli_user"])
    result = await hass.services.async_call(
        DOMAIN, "new_quick_shop",
        {"entity_id": TODO, "assignee": "person.kelsie", "store": "Aldi",
         "items": ["Milk", {"name": "Bananas", "qty": 6}], "open_path": "/household-shopping/shop"},
        blocking=True, return_response=True, context=eli,
    )
    shop_id = result[TODO]["shop_id"]
    assert result[TODO]["notified"] is True
    await hass.async_block_till_done()
    assert len(calls["kel"]) == 1 and not calls["fold"] and not calls["watch"]
    note = calls["kel"][0].data
    assert note["title"] == "🛒 Elijah asked you to do a quick shop at Aldi"
    assert note["message"] == "Milk, Bananas ×6"
    assert note["data"]["clickAction"] == "/household-shopping/shop"

    # Main shop is untouched; the to-do list still shows only the main shop.
    assert hass.states.get(SENSOR).attributes["quick_shops"][0]["needed"] == 2
    assert hass.states.get(TODO).state == "0"

    # Assigning to yourself sends nothing; reassigning notifies the new person.
    r = await hass.services.async_call(DOMAIN, "assign_shop", {"entity_id": TODO, "shop_id": shop_id, "assignee": "person.elijah"}, blocking=True, return_response=True, context=eli)
    assert r[TODO]["notified"] is False
    r = await hass.services.async_call(DOMAIN, "assign_shop", {"entity_id": TODO, "shop_id": shop_id, "assignee": "person.kelsie"}, blocking=True, return_response=True, context=eli)
    await hass.async_block_till_done()
    assert r[TODO]["notified"] is True and len(calls["kel"]) == 2
    await hass.services.async_call(DOMAIN, "remind_shop", {"entity_id": TODO, "shop_id": shop_id}, blocking=True, return_response=True, context=eli)
    await hass.async_block_till_done()
    assert calls["kel"][-1].data["title"].startswith("🛒 Reminder")

    with pytest.raises(ServiceValidationError, match="isn't a person"):
        await call(hass, "assign_shop", shop_id=shop_id, assignee="light.kitchen")

    await call(hass, "set_item_state", item="Milk", state="got", shop_id=shop_id)
    summary = snapshot(await call(hass, "finish_shop", response=True, shop_id=shop_id))
    assert summary["kind"] == "quick" and summary["assignee"] == "person.kelsie"
    assert hass.states.get(SENSOR).attributes["quick_shops"] == []


async def test_snapshot_has_shops_and_people(hass, entry, hass_ws_client):  # BR-QUICK-04
    await _phones(hass)
    await call(hass, "new_shop")
    await call(hass, "new_quick_shop", assignee="person.kelsie")
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    await ws.receive_json()
    event = (await ws.receive_json())["event"]
    assert [s["kind"] for s in event["shops"]] == ["main", "quick"]
    assert {p["entity_id"]: p["can_notify"] for p in event["people"]} == {"person.elijah": True, "person.kelsie": True}


async def test_cash_out_through_services_and_todo(hass, entry):  # BR-CASH-01/04/05
    await call(hass, "add_cash_out", amount=200, note="for the cleaner")
    assert hass.states.get(SENSOR).attributes["cash_out"] == 200
    items = await hass.services.async_call("todo", "get_items", {"entity_id": TODO}, blocking=True, return_response=True)
    item = items[TODO]["items"][0]
    assert item["summary"] == "Cash out" and item["description"] == "$200 · for the cleaner"
    # Editing the note in the standard to-do list keeps the amount.
    await hass.services.async_call(
        "todo", "update_item", {"entity_id": TODO, "item": "Cash out", "description": "$200 · cleaner"}, blocking=True
    )
    await call(hass, "update_item", item="Cash out", amount=250)
    data = snapshot(await call(hass, "get_catalogue", response=True))
    cash = data["shop"]["items"][0]
    assert cash["amount"] == 250 and cash["note"] == "cleaner"
    with pytest.raises(ServiceValidationError):
        await call(hass, "update_item", item="Cash out", qty=3)
    await call(hass, "start_shopping")
    await call(hass, "set_item_state", item="Cash out", state="got")
    summary = await call(hass, "finish_shop", response=True)
    assert summary[TODO]["cash_out"] == {"amount": 250, "state": "got", "note": "cleaner"}
