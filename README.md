# Household Shopping

Shopping for a household that treats its groceries as **stock**. Each shop gets its own list. You build it by going through your stock (grouped by where things live at home), shop it aisle by aisle, mark anything the shop didn't have as **missing**, and get a summary at the end. It all runs locally in Home Assistant.

The rules this is built against are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

> **Status:** 0.2.0. The backend (data, actions, entities) is done and tested. The dashboard card, which is the main phone UI with one-tap ✓ got / ✗ missing buttons, is next. Until it's ready, use the actions below or the standard to-do list.

## Install

**HACS:** HACS → ⋮ → Custom repositories → add `https://github.com/Snawboll/household-shopping` as type *Integration* → download → restart HA.

**Manual:** copy `custom_components/household_shopping` into `/config/custom_components/` → restart HA.

Then go to Settings → Devices & services → Add integration → **Household Shopping** and name it, for example "Shopping". It requires HA 2026.11 or newer.

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

**Shop:** `new_shop(store?, items?)` · `start_shopping(store?)` · `finish_shop` (returns the summary) · `cancel_shop` · `add_item(name, note?, aisle?)` · `update_item` · `set_item_state(item, needed|got|missing)` · `remove_item` · `toggle_stock(name, on)` · `get_history(limit)`

**Catalogue:** `add_stock_item(name, location?, aisle?, note?, icon?)` · `add_occasional_item` · `update_catalogue_item` · `promote_to_stock` · `demote_to_occasional` · `remove_catalogue_item` · `import_catalogue(items)` (bulk, all or nothing) · `get_catalogue` (returns everything) · `set_item_image(name, image_url | image_data, source, attribution?)` · `clear_item_image`

**Groups:** `add_group` · `update_group` · `remove_group` · `order_groups` (the type is `location` or `aisle`)

**Events:** `household_shopping_shop_finished` (with the full summary) and `household_shopping_item_missing`.

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
```
