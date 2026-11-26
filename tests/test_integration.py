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
