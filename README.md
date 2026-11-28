# Household Shopping

Shopping for a household that treats its groceries as **stock**. Each shop gets its own list. You build it by going through your stock (grouped by where things live at home), shop it aisle by aisle, mark anything the shop didn't have as **missing**, and get a summary at the end. It all runs locally in Home Assistant.

The rules this is built against are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

> **Status:** 0.6.0. Adds quick shops and assigning a shop to someone, with a push notification.

## Install

**HACS:** HACS → ⋮ → Custom repositories → add `https://github.com/Snawboll/household-shopping` as type *Integration* → download → restart HA.

**Manual:** copy `custom_components/household_shopping` into `/config/custom_components/` → restart HA.

Then go to Settings → Devices & services → Add integration → **Household Shopping** and name it, for example "Shopping". It requires HA 2026.11 or newer.

## The card

The card is bundled with the integration and registers itself as a dashboard resource, so you don't need to install it separately. After an update, refresh the browser or app once. Add it to a dashboard: **Edit dashboard → Add card → search "Household Shopping"**. In YAML that's:

```yaml
type: custom:household-shopping-card
# entity: todo.shopping   # optional; only needed if you have more than one list
```

- **No shop:** a *New shop* button and the last shop's missing list.
- **Planning:** tick what's run out from your stock (a −/＋ stepper appears to set how many), grouped by where it lives at home. Occasional items are in a collapsed section at the bottom. Type anything else into the add box, which suggests catalogue names. Set the store (optional), then tap *Start shopping*.
- **Shopping:** the list is grouped by aisle. Tap **✓** for got and **✗** for missing; tap again to undo. Quantities over 1 show as a **×5** badge. **Tap (or long-press)** an item for more: still needed, edit note, change aisle (remembered for next time), save to stock, photo, remove. *📋 Stock* adds things from the catalogue mid-shop. *Finish shop* shows the summary; **✕** discards the shop without saving it.
- **⚡ Quick shop:** a few things, any time, even while a main shop is open. It skips the stock check, new items aren't added to your catalogue, and you can give it to someone. Chips above the add box switch between open shops.
- **👤 Assign / 🔔 remind:** give any shop to a person. Their phone gets a notification listing what's needed, which opens the dashboard when tapped. Phones are found automatically from each person's Companion app (watches are skipped).
- **History:** every finished shop, newest first. Tap one to see what was missing, not got and got, or to **Shop again** with the same items.
- **Catalogue:** search, edit items (name, stock/occasional, location, aisle, note, icon), take or choose a **photo**, *Paste list* to bulk-add, and *Groups* to rename and reorder home locations and aisles.

Tip: a dashboard view in **panel** or **sections** layout gives the card the full phone screen.

## Concepts

| | |
|---|---|
| **Stock** | Things you always keep at home. Each one has a **home location** (Fridge, Pantry…) and an **aisle** (Dairy & Eggs, Frozen…). |
| **Occasional** | Things you buy sometimes. These are remembered automatically whenever you add something new to a shop. They can be promoted to stock. |
| **Shop** | One trip, with its own list: `planning` → `shopping` → finished. Only one shop is open at a time. |
| **Item state** | `needed`, `got` or `missing`. |

Home locations and aisles come with sensible defaults, and you can rename and reorder them all. Each item gets an automatic emoji icon. You can attach a photo to any catalogue item.

## Entities (for a list named "Shopping")

| Entity | Purpose |
|---|---|
| `todo.shopping` | The open shop as a normal to-do list. It works with Assist ("add milk to shopping"), which opens a shop if none is open. Missing items show as "❌ Missing". |
| `sensor.shopping_shop` | `none` / `planning` / `shopping`, with attributes for the store, counts, `missing_items` and the last shop's missing items. |

## Actions

All of these target `todo.shopping`.

**Shop:** `new_shop(store?, items?)` (items: names or `{name, qty, note}`) · `start_shopping(store?)` · `finish_shop` (returns the summary) · `new_quick_shop(store?, assignee?, items?)` · `assign_shop(shop_id, assignee)` · `remind_shop(shop_id)` · `cancel_shop` (planning or shopping) · `repeat_shop(shop_id)` · `add_item(name, note?, aisle?, qty?)` · `update_item` · `set_item_state(item, needed|got|missing)` · `remove_item` · `toggle_stock(name, on)` · `get_history(limit)`

**Catalogue:** `add_stock_item(name, location?, aisle?, note?, icon?)` · `add_occasional_item` · `update_catalogue_item` · `promote_to_stock` · `demote_to_occasional` · `remove_catalogue_item` · `import_catalogue(items)` (bulk, all or nothing) · `get_catalogue` (returns everything) · `set_item_image(name, image_url | image_data, source, attribution?)` · `clear_item_image`

**Groups:** `add_group` · `update_group` · `remove_group` · `order_groups` (the type is `location` or `aisle`)

Shop actions take an optional `shop_id`; without it they act on the main shop, which is also the one `todo.shopping` shows.

**Events:** `household_shopping_shop_finished` (with the full summary), `household_shopping_item_missing` and `household_shopping_shop_assigned`.

## Example: send the missing list to everyone's phone

```yaml
automation:
  - alias: Shop finished - tell the house what was missing
    triggers:
      - trigger: event
        event_type: household_shopping_shop_finished
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.missing | count > 0 }}"
    actions:
      - action: notify.notify
        data:
          title: "Missing from {{ trigger.event.data.store or 'the shop' }}"
          message: "{{ trigger.event.data.missing | map(attribute='name') | join(', ') }}"
```

## Receipts → catalogue (with an AI assistant)

The integration doesn't read receipts itself. An assistant connected to your HA, such as Claude through the HA MCP server, can do it. It reads a receipt photo or an eReceipt PDF, matches the lines against `get_catalogue`, shows you a table to approve, then calls `import_catalogue` and optionally `set_item_image`. See BR-RCPT in the requirements.

## Privacy & network

No cloud services and no background network calls. The only network request the integration ever makes is when `set_item_image` is given an `image_url`. Photos are stored in `/config/household_shopping_images/` (which is included in backups) and are deleted when you delete the item or remove the integration.

## Development

```bash
pip install -r requirements_test.txt   # Python 3.14 for current HA
pytest -q
# Card end-to-end test (real HA + Chromium), also writes screenshots:
npm install --no-save playwright && HS_SCREENSHOTS=shots pytest -q tests/test_card_e2e.py
```
