# Household Shopping: Requirements & Business Rules

**Status:** v1.0, agreed. Changes from here on are made by editing this file, with a note in the commit.

`MUST`, `SHOULD` and `MAY` are used as in RFC 2119. Rule IDs are referred to in tests and commits.

---

## 1. Purpose & scope

Shopping for one household, built on Home Assistant. It is **local only** and used through the HA Companion app.

### 1.1 The household's process (this is what the product supports)

The household treats its groceries as **stock**. **Every shop has its own list.**

1. **New shop:** create a shop. Its list starts empty. Nothing carries over from the last shop.
2. **Plan:** go through the **stock list**, **grouped by where it's kept at home**, and pick whatever has run out or is low. Add anything else, either from **occasional items** (remembered things that aren't stock) or as something new.
3. **Start shopping:** at the shop the list is **sorted by aisle**. The shopper ticks items off as they go in the trolley, and mark anything the shop doesn't have as **missing**.
4. **Finish:** this gives a **summary of what was missing**. The shop is closed and kept in history.

### 1.2 Goals
1. Building a shop's list from stock is quick, even with a long stock list.
2. Each item can be set to *got* or *missing* with one tap while shopping.
3. Every finished shop produces a summary of what was missing.
4. The list is shared and updates live for everyone in the household.
5. Adding items by voice through Assist keeps working.

### 1.3 Non-goals (v1)
**Tracking stock levels or usage.** Stock is a catalogue of things the household keeps. Whether an item is needed is decided only when building a new shop, and the household never records when something is used. *(Owner decision.)* Also out of scope: prices, supermarket APIs, recipes and barcodes.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Stock item** | Something the household normally keeps at home (milk, rice, dishwasher tablets). It's a permanent catalogue entry, not a thing to buy. |
| **Stock list** | All stock items, in an order the user can change. |
| **Shop** | One shopping occasion with its own list. Its states are `planning` → `shopping` → `finished`. |
| **Shop item** | A line on a shop's list. It is either picked from stock or a one-off. Its states are `needed`, `got` and `missing`. |
| **Occasional item** | A remembered item that isn't stock. It isn't reviewed every shop, but it's quick to add to a shop and can be promoted to stock. |
| **Catalogue** | Stock items plus occasional items. |
| **One-off** | A shop item that isn't in the catalogue (yet). |
| **Home location** | Where a stock item is kept at home, for example Fridge, Pantry or Laundry. Used to group the stock check. |
| **Aisle** | A generic shop section, for example Fruit & Veg, Dairy or Frozen. Used to sort the list while shopping. It isn't tied to any particular store. |
| **Shop summary** | The record of a finished shop. |

---

## 3. Stock

| ID | Rule |
|---|---|
| BR-STOCK-01 | A stock item has a name that is unique (compared case-insensitively, ignoring extra spaces) and MAY have a default note. |
| BR-STOCK-02 | Stock items can be added, renamed, reordered and deleted. Changing stock MUST NOT change shops that already exist. |
| BR-STOCK-03 | A shop item that isn't stock can be saved to stock with one action. |
| BR-STOCK-04 | Every stock item has a **home location**. The stock check is grouped by home location, in the location order the user sets. *(Owner decision.)* |
| BR-STOCK-05 | Every stock item has an **aisle**. The list is sorted by aisle while shopping, in the aisle order the user sets. *(Owner decision.)* |
| BR-STOCK-06 | Home locations and aisles are lists the user can edit (add, rename, reorder and delete). Deleting one moves its items to "Other". They come with defaults (see §3.1). |
| BR-STOCK-07 | A new stock item with no location or aisle goes into "Other" for that grouping. *(Later: guess the aisle from the name with a built-in keyword list.)* |
| BR-STOCK-08 | Stock items can be created and edited **outside a shop**: from the card's settings, one at a time or **in bulk** (paste a list), and through services, so automations and AI assistants connected to HA can do it too. |
| BR-STOCK-09 | Stock carries no quantity, level or "last used" value. *(Owner decision.)* |

### 3.1 Default groupings (editable)
**Home locations:** Fridge, Freezer, Pantry, Fruit bowl, Bathroom, Laundry, Cleaning, Other.

**Aisles** (a generic order loosely based on a typical Australian supermarket walk; the user can reorder them to match their usual store): Fruit & Veg, Bakery, Deli, Meat & Seafood, Dairy & Eggs, Pantry, Breakfast, Snacks & Confectionery, Drinks, International, Frozen, Health & Beauty, Baby, Pet, Cleaning & Laundry, Household, Other.

## 3a. Occasional items

| ID | Rule |
|---|---|
| BR-OCC-01 | An occasional item has a unique name (matched the same way as stock), an aisle, and MAY have a note. A name can't be both stock and occasional. |
| BR-OCC-02 | **Created automatically.** Every one-off added to a shop is remembered as an occasional item, along with its aisle. If the item's aisle is changed later, the remembered aisle is updated too. Cleaning up is done by hand in the catalogue screen, or by asking an AI assistant to review it through `get_catalogue` / `remove_catalogue_item`. *(Owner decision.)* |
| BR-OCC-03 | When planning, occasional items appear in a collapsed "Occasional" section of the stock check, and as suggestions when typing a new item (for example, typing "sun" suggests "Sunscreen"). Picking one adds it to the shop with its aisle. |
| BR-OCC-04 | **Promote to stock:** one action turns an occasional item into a stock item, asking for its home location. **Demote:** a stock item can be moved back to occasional. |
| BR-OCC-05 | Occasional items can be renamed, have their aisle changed, or be deleted. |
| BR-OCC-06 | *(Later)* Suggest a promotion when an occasional item appears in, say, 3 of the last 5 shops: "You buy this most shops. Add to stock?" |

## 4. Shops

| ID | Rule |
|---|---|
| BR-SHOP-01 | **Only one shop can be open (`planning` or `shopping`) at a time.** Finished shops are read-only history. |
| BR-SHOP-02 | A new shop is created by hand (from the card or a service), or automatically when an item is added while no shop is open, for example "add milk to shopping" through Assist. |
| BR-SHOP-03 | `planning` → `shopping` happens by hand ("Start shopping"). This switches the card from the stock picker to the aisle-sorted ✓/✗ view. |
| BR-SHOP-04 | `shopping` → `finished` happens by hand ("Finish"). Nothing starts or finishes a shop automatically, but automations MAY call the services. |
| BR-SHOP-05 | A shop MAY have a store name. It's optional and can be left blank. |
| BR-SHOP-06 | **Finishing** records: store, created, started, finished, **got**, **missing** and **not got** (items still `needed`). |
| BR-SHOP-07 | The summary leads with **what was missing**. It shows on the card and fires `household_shopping_shop_finished`. Phone notifications are left to the user's own automations, and the README includes a sample. |
| BR-SHOP-08 | **No carry-over.** A new shop starts empty. Missing items appear only in the last shop's summary, which stays visible from the card. *(Owner decision.)* |
| BR-SHOP-09 | Cancelling a shop that's still in `planning` deletes it and leaves no history. |

## 5. Shop items

| ID | Rule |
|---|---|
| BR-ITEM-01 | A shop item has a non-empty name (trimmed), MAY have a note, has an **aisle**, and has a state: `needed` (the default), `got` or `missing`. An item picked from stock copies the stock item's aisle. A one-off defaults to "Other" and its aisle can be changed. |
| BR-ITEM-02 | **Duplicates are allowed.** *(Owner decision.)* The stock check shows a stock item as already picked if it is on the shop. |
| BR-ITEM-03 | **Stock check:** each stock item has a toggle. On adds it to the shop, and off removes it, as long as it is still `needed`. |
| BR-ITEM-04 | Items can be added at any time, including while shopping: from stock, from occasional items, or as one-offs. A shop can also be **created with items in one call** (service `new_shop` with `items`). |
| BR-ITEM-05 | While shopping, any item can be set to `got` or `missing` with **one tap** (controls next to the item) or from a **long-press menu**. Either can be undone. *(Owner decision.)* |
| BR-ITEM-06 | `got` and `missing` record the time they were set. Marking an item `missing` fires `household_shopping_item_missing`. |
| BR-ITEM-07 | Items can be set to `got` or `missing` during `planning` too, for example "already grabbed it". |
| BR-ITEM-08 | While shopping, items are **grouped by aisle** in aisle order, in the order added within each aisle. Items that are done drop to the bottom of their aisle. |
| BR-ITEM-09 | Every change reaches all devices within seconds and survives an HA restart. |

## 6. History

| ID | Rule |
|---|---|
| BR-HIST-01 | Keep the most recent 100 finished shops. |
| BR-HIST-02 | `get_history(limit)` returns the newest first. |
| BR-HIST-03 | Shop records keep each item's catalogue ID (when it has one) as well as its name, so BR-OCC-06 and future suggestions can work. |

---

## 7. Interfaces

### 7.1 Why a custom card
HA's to-do entities have only two states (`needs_action` and `completed`), and the built-in to-do card has no long-press or extra per-item controls ([HA developer docs: To-do entity](https://developers.home-assistant.io/docs/core/entity/todo/)). Meeting BR-ITEM-05 needs a custom Lovelace card. The integration bundles the card and registers it, so it needs no separate install.

### 7.2 Card (primary UI)
- **No open shop:** a "New shop" button and the last summary.
- **Planning:** the stock check (toggles, grouped by home location, with collapsible groups, then an "Occasional" group), an add box that suggests catalogue names as you type, the current shop list, and a **Start shopping** button.
- **Shopping:** items are grouped under aisle headings. Each item shows its name and note, with a ✓ got and a ✗ missing control. Long-press opens a menu with Got, Missing, Edit, Change aisle, Delete, and Save to stock or Remember. Items that are done drop to the bottom. There's a **Finish** button.
- **Summary:** shown after Finish.
- **Catalogue / settings:** add or edit stock and occasional items, including a bulk paste; promote and demote between them; edit the home locations and aisles and their order.
- Phone-first: one-handed use, large tap targets, and HA's light and dark themes.

### 7.3 Entities (for Assist and compatibility)
| Entity | Purpose |
|---|---|
| `todo.<name>` | The **current open shop** as a standard to-do list. `got` shows as done, `missing` shows as to-do with the description "Missing". Assist can add items, which creates a shop if none is open. |
| `sensor.<name>_shop` | `none` / `planning` / `shopping`, with attributes for store, counts and the last summary. |

### 7.4 Services
Shops: `new_shop(store?, items?)`, `start_shopping(store?)`, `finish_shop()` (returns the summary), `cancel_shop()`, `add_item(name, aisle?, note?)`, `set_item_state(item, state)`, `get_history(limit)`.

Catalogue: `add_stock_item(name, location?, aisle?, note?)`, `add_occasional_item(name, aisle?, note?)`, `update_catalogue_item(name, new_name?, location?, aisle?, note?)`, `promote_to_stock(name, location?)`, `demote_to_occasional(name)`, `remove_catalogue_item(name)`, `import_catalogue(items, kind)` for bulk loading, and `get_catalogue()` (returns data).

With these services an AI assistant connected to HA (for example Claude through the HA MCP server) can build the stock list and create shops. Invalid calls, such as finishing with no shop open or naming an unknown item, raise a `ServiceValidationError` with a clear message.

### 7.5 Events
`household_shopping_shop_finished`, `household_shopping_item_missing`.

---

## 8. Non-functional requirements
| ID | Requirement |
|---|---|
| NFR-01 | Local only. No network calls. |
| NFR-02 | Data is stored in versioned HA `.storage`, with migrations, and is included in HA backups. |
| NFR-03 | Minimum HA version: set to whatever the owner's instance is running (to be checked before release). |
| NFR-04 | Passes hassfest and HACS validation in CI. |
| NFR-05 | Tests use `pytest-homeassistant-custom-component`, every BR-* rule is covered, and the tests run in CI. |
| NFR-06 | Two people editing at once MUST NOT lose changes. Change handlers never await partway through an update. |
| NFR-07 | Dates use HA's time zone and an Australian format ("27 Nov"). |
| NFR-08 | Removing the integration deletes its data. |

## 9. Later / maybe
Quantities, aisle ordering, "added by", suggestions from history, a "shop started, anything else?" blueprint, and several households or shops at once.
