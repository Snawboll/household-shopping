# Household Shopping

A shared shopping list for Home Assistant, with a standard (staples) list, shop tracking and "unavailable" items. It's local, with no cloud account, and syncs to everyone through the HA Companion app.

## Install

**HACS (recommended):** HACS → ⋮ → Custom repositories → add `https://github.com/Snawboll/household-shopping` as type *Integration* → download → restart HA.

**Manual:** copy `custom_components/household_shopping` into `/config/custom_components/` (via the Samba or File editor add-on) → restart HA.

Then go to Settings → Devices & services → Add integration → **Household Shopping** and name it (for example "Shopping"). Requires HA 2024.8 or newer.

## What you get (for a list named "Shopping")

| Entity | Purpose |
|---|---|
| `todo.shopping` | The shared list. Appears under To-do lists in the sidebar and works with Assist ("add milk to shopping"). |
| `todo.shopping_staples` | Your standard list. **Ticking a staple adds it to the shopping list**, and the staple stays put. |
| `sensor.shopping_trip` | `idle` / `shopping`. Attributes: store, started, bought_so_far, unavailable_now, last_trip, trips_recorded. |

## Day to day

- **Standard list:** run *Add staples* to load everything onto the list at once, or tick individual staples.
- **Unavailable:** in the app, open an item and type `na` (or `out`, `oos`, `unavailable`) as its description. It becomes "Unavailable at Coles (27 Nov)" and stays on the list for next time. Ticking it later clears the flag, and so does replacing the description.
- **Tracking a shop:** ticking the first item (or marking one unavailable) starts a trip automatically. Run *Finish shop* to record what was bought, what was unavailable and what was left, and to clear the ticked items. History keeps the last 100 trips.

## Services

All of them target `todo.shopping` (or the staples entity, which does the same thing).

`add_staples` · `add_to_staples(item)` · `start_shop(store?)` · `finish_shop(store?, clear_bought=true)` · `mark_unavailable(item, store?)` · `clear_unavailable(item?)` · `get_history(limit=10)` (returns data)

Events: `household_shopping_trip_finished`, `household_shopping_item_unavailable`.

## Example: start and finish by location

```yaml
automation:
  - alias: Shop starts at Coles
    triggers:
      - trigger: zone
        entity_id: person.elijah
        zone: zone.coles
        event: enter
    actions:
      - action: household_shopping.start_shop
        target: { entity_id: todo.shopping }
        data: { store: Coles }
  - alias: Shop ends leaving Coles
    triggers:
      - trigger: zone
        entity_id: person.elijah
        zone: zone.coles
        event: leave
    conditions:
      - condition: state
        entity_id: sensor.shopping_trip
        state: shopping
    actions:
      - action: household_shopping.finish_shop
        target: { entity_id: todo.shopping }
```

## Known limits

- HA's to-do card only has two states (to do / done), so "unavailable" shows in the item's description rather than as a third state.
- Trips start automatically but don't end automatically. Finish them with the service, a dashboard button, or the zone automation above.
