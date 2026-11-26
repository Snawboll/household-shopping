"""Constants for Household Shopping."""

DOMAIN = "household_shopping"

CONF_NAME = "name"

STORAGE_VERSION = 1
MAX_HISTORY = 100

STATUS_NEEDS_ACTION = "needs_action"
STATUS_COMPLETED = "completed"

# Typing one of these into an item's description marks it unavailable.
UNAVAILABLE_KEYWORDS = {
    "na",
    "n/a",
    "unavailable",
    "out",
    "oos",
    "out of stock",
    "none",
    "sold out",
}

EVENT_TRIP_FINISHED = f"{DOMAIN}_trip_finished"
EVENT_ITEM_UNAVAILABLE = f"{DOMAIN}_item_unavailable"

ATTR_ITEM = "item"
ATTR_STORE = "store"
ATTR_CLEAR_BOUGHT = "clear_bought"
ATTR_LIMIT = "limit"

SERVICE_ADD_STAPLES = "add_staples"
SERVICE_ADD_TO_STAPLES = "add_to_staples"
SERVICE_START_SHOP = "start_shop"
SERVICE_FINISH_SHOP = "finish_shop"
SERVICE_MARK_UNAVAILABLE = "mark_unavailable"
SERVICE_CLEAR_UNAVAILABLE = "clear_unavailable"
SERVICE_GET_HISTORY = "get_history"
