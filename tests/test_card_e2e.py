"""Drive the real card in Chromium against a live (test) Home Assistant.

Skipped unless Node and Playwright are available. Screenshots go to
$HS_SCREENSHOTS (default: a temp dir).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from custom_components.household_shopping.const import DOMAIN

ROOT = Path(__file__).parents[1]
CARD = ROOT / "custom_components" / DOMAIN / "www" / "household-shopping-card.js"


def _playwright_available() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


pytestmark = [
    pytest.mark.skipif(not _playwright_available(), reason="needs node + playwright"),
    pytest.mark.enable_socket,
]

SEED = [
    ("Full cream milk", "stock", "Fridge", "Dairy & Eggs", "3L"),
    ("Tasty cheese", "stock", "Fridge", "Dairy & Eggs", "500g block"),
    ("Greek yoghurt", "stock", "Fridge", "Dairy & Eggs", "1kg"),
    ("Broccoli", "stock", "Fridge", "Fruit & Veg", ""),
    ("Carrots", "stock", "Fridge", "Fruit & Veg", "1kg bag"),
    ("Bananas", "stock", "Fruit bowl", "Fruit & Veg", ""),
    ("Apples", "stock", "Fruit bowl", "Fruit & Veg", "1kg punnet"),
    ("Wholemeal bread", "stock", "Pantry", "Bakery", ""),
    ("Rice", "stock", "Pantry", "Pantry", "Jasmine 5kg"),
    ("Pasta", "stock", "Pantry", "Pantry", ""),
    ("Frozen peas", "stock", "Freezer", "Frozen", ""),
    ("Dishwasher tablets", "stock", "Cleaning", "Cleaning & Laundry", ""),
    ("Toilet paper", "stock", "Bathroom", "Household", "24 pack"),
    ("Sunscreen", "occasional", None, "Health & Beauty", "SPF 50+"),
    ("Mangoes", "occasional", None, "Fruit & Veg", ""),
    ("<b>Hacker</b> & co", "occasional", None, None, "<img src=x onerror=alert(1)>"),
]


async def test_card_end_to_end(socket_enabled, hass, entry, aiohttp_client, hass_access_token, tmp_path):

    await hass.services.async_call(
        DOMAIN,
        "import_catalogue",
        {
            "entity_id": "todo.shopping",
            "items": [
                {"name": n, "kind": k, "location": loc, "aisle": a, "note": note}
                for n, k, loc, a, note in SEED
            ],
        },
        blocking=True,
    )
    # A finished shop so the "last shop" panel has something to show.
    for svc, data in (
        ("new_shop", {"items": ["Rice", "Mangoes"]}),
        ("start_shopping", {}),
        ("set_item_state", {"item": "Mangoes", "state": "missing"}),
        ("set_item_state", {"item": "Rice", "state": "got"}),
        ("finish_shop", {}),
    ):
        await hass.services.async_call(DOMAIN, svc, {"entity_id": "todo.shopping", **data}, blocking=True)

    hass.states.async_set("person.kelsie", "home", {"friendly_name": "Kelsie", "device_trackers": []})
    hass.states.async_set("person.elijah", "home", {"friendly_name": "Elijah", "device_trackers": []})
    client = await aiohttp_client(hass.http.app)
    base = str(client.make_url("")).rstrip("/")
    out = Path(os.environ.get("HS_SCREENSHOTS", tmp_path))
    out.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "node", str(ROOT / "tests" / "e2e" / "drive.js"), base, hass_access_token, str(out), str(CARD),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    lines = [ln for ln in stdout.decode().splitlines() if ln.startswith("{")]
    assert lines, stderr.decode()[-2000:]
    result = json.loads(lines[-1])
    assert result["ok"], result.get("error")
    assert result["errors"] == [], result["errors"]

    history = await hass.services.async_call(
        DOMAIN, "get_history", {"entity_id": "todo.shopping"}, blocking=True, return_response=True
    )
    shops = history["todo.shopping"]["shops"]
    quick = shops[0]  # newest: the quick shop
    assert quick["kind"] == "quick" and quick["assignee"] == "person.kelsie" and quick["store"] == "Aldi"
    assert [i["name"] for i in quick["got"]] == ["Birthday card"] and [i["name"] for i in quick["missing"]] == ["Milk"]
    catalogue = await hass.services.async_call(
        DOMAIN, "get_catalogue", {"entity_id": "todo.shopping"}, blocking=True, return_response=True
    )
    names = {c["name"] for c in catalogue["todo.shopping"]["catalogue"]}
    assert "Birthday card" not in names  # BR-QUICK-03
    assert catalogue["todo.shopping"]["shop"]["state"] == "planning"  # main shop untouched
    last = next(s for s in shops if s["store"] == "Woolworths Woden")
    assert last["store"] == "Woolworths Woden"
    assert sorted(i["name"] for i in last["missing"]) == ["Broccoli", "Tasty cheese"]
    assert sorted(i["name"] for i in last["got"]) == ["Bananas", "Full cream milk"]
    assert len(last["not_got"]) == 2  # Birthday candles was removed mid-shop
    qty = {i["name"]: i["qty"] for i in last["got"] + last["missing"]}
    assert qty["Full cream milk"] == 3 and qty["Broccoli"] == 2  # BR-QTY-04
    assert last["cash_out"] == {"amount": 120, "state": "got", "note": ""}  # BR-CASH-03/04
