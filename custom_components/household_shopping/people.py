"""People who can be assigned a shop, and push notifications to them (BR-ASSIGN).

A person's phones are found from their linked device trackers: each tracker
created by the Companion app (platform mobile_app) belongs to a device whose
notify action is notify.mobile_app_<device name>. Watches are skipped: they
mirror the phone's notifications, so notifying them too would double up.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify

from .model import NEEDED, QUICK, ShoppingError

MAX_LISTED = 6


@callback
def notify_targets(hass: HomeAssistant, person_id: str) -> list[str]:
    """notify.* action names (without the domain) for a person's phones."""
    state = hass.states.get(person_id)
    if state is None:
        return []
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    targets: list[str] = []
    for tracker in state.attributes.get("device_trackers", []):
        entry = ent_reg.async_get(tracker)
        if entry is None or entry.platform != "mobile_app":
            continue
        device = dev_reg.async_get(entry.device_id) if entry.device_id else None
        names = [n for n in (device and (device.name_by_user, device.name)) or () if n]
        label = " ".join([*names, (device and device.model) or ""]).lower()
        if "watch" in label:
            continue
        for name in [*names, tracker.split(".", 1)[1]]:
            service = f"mobile_app_{slugify(name)}"
            if hass.services.has_service("notify", service) and service not in targets:
                targets.append(service)
                break
    return targets


@callback
def people(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Everyone a shop can be assigned to, for the card's picker."""
    out = []
    for state in sorted(hass.states.async_all("person"), key=lambda s: s.name.casefold()):
        out.append(
            {
                "entity_id": state.entity_id,
                "name": state.name,
                "user_id": state.attributes.get("user_id"),
                "can_notify": bool(notify_targets(hass, state.entity_id)),
            }
        )
    return out


@callback
def check_person(hass: HomeAssistant, person_id: str | None) -> None:
    if person_id and (not person_id.startswith("person.") or hass.states.get(person_id) is None):
        raise ShoppingError(f"'{person_id}' isn't a person in Home Assistant")


@callback
def person_for_user(hass: HomeAssistant, user_id: str | None) -> str | None:
    if not user_id:
        return None
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == user_id:
            return state.entity_id
    return None


async def async_notify_assignee(
    hass: HomeAssistant,
    shop: dict[str, Any],
    *,
    by_user_id: str | None = None,
    open_path: str | None = None,
    reminder: bool = False,
) -> bool:
    """BR-ASSIGN-02/03: push the shop to its assignee's phone(s).

    Returns True if a notification was sent. Nobody is notified about a shop
    they assigned to themselves.
    """
    assignee = shop.get("assignee")
    if not assignee:
        return False
    sender = person_for_user(hass, by_user_id)
    if sender == assignee and not reminder:
        return False
    targets = notify_targets(hass, assignee)
    if not targets:
        return False

    needed = [i for i in shop["items"] if i["state"] == NEEDED]
    names = [f"{i['name']} ×{i['qty']}" if i.get("qty", 1) > 1 else i["name"] for i in needed]
    listed = ", ".join(names[:MAX_LISTED])
    if len(names) > MAX_LISTED:
        listed += f" +{len(names) - MAX_LISTED} more"
    kind = "quick shop" if shop.get("kind") == QUICK else "shop"
    who = hass.states.get(sender).name if sender and hass.states.get(sender) else None
    where = f" at {shop['store']}" if shop.get("store") else ""
    if reminder:
        title = f"🛒 Reminder: {kind}{where}"
    elif who:
        title = f"🛒 {who} asked you to do a {kind}{where}"
    else:
        title = f"🛒 You've been given a {kind}{where}"
    data: dict[str, Any] = {
        "tag": f"household_shopping_{shop['id']}",  # replaces, rather than stacks
        "group": "household_shopping",
    }
    if open_path and open_path.startswith("/"):
        data["clickAction"] = open_path  # Android
        data["url"] = open_path  # iOS
    for target in targets:
        await hass.services.async_call(
            "notify",
            target,
            {"title": title, "message": listed or "Nothing on it yet.", "data": data},
            blocking=False,
        )
    return True
