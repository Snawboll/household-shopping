"""Automatic emoji icons for items (BR-IMG-02).

Keywords are matched against whole words in the lower-cased item name, longest
keyword first, so "sweet potato" beats "potato" and "ice cream" beats "cream".
"""

from __future__ import annotations

import re

KEYWORD_ICONS: dict[str, str] = {
    # fruit & veg
    "apple": "🍎", "banana": "🍌", "orange": "🍊", "mandarin": "🍊", "lemon": "🍋",
    "lime": "🍋", "kiwifruit": "🥝", "kiwi": "🥝", "mango": "🥭", "pineapple": "🍍",
    "grape": "🍇", "grapes": "🍇", "strawberry": "🍓", "strawberries": "🍓",
    "blueberry": "🫐", "blueberries": "🫐", "berry": "🍓", "berries": "🍓",
    "pear": "🍐", "peach": "🍑", "cherry": "🍒", "cherries": "🍒", "melon": "🍈",
    "watermelon": "🍉", "avocado": "🥑", "tomato": "🍅", "tomatoes": "🍅",
    "potato": "🥔", "potatoes": "🥔", "sweet potato": "🍠", "pumpkin": "🎃",
    "carrot": "🥕", "carrots": "🥕", "broccoli": "🥦", "cauliflower": "🥦",
    "lettuce": "🥬", "spinach": "🥬", "cabbage": "🥬", "cucumber": "🥒",
    "zucchini": "🥒", "capsicum": "🫑", "chilli": "🌶️", "corn": "🌽",
    "onion": "🧅", "garlic": "🧄", "mushroom": "🍄", "mushrooms": "🍄",
    "ginger": "🫚", "olives": "🫒", "olive": "🫒", "beans": "🫘",
    # bakery
    "bread": "🍞", "loaf": "🍞", "sourdough": "🍞", "baguette": "🥖", "roll": "🥖",
    "rolls": "🥖", "croissant": "🥐", "bagel": "🥯", "wraps": "🫓", "tortilla": "🫓",
    "pizza base": "🍕", "muffin": "🧁",
    # dairy & eggs
    "milk": "🥛", "cheese": "🧀", "parmesan": "🧀", "butter": "🧈", "egg": "🥚",
    "eggs": "🥚", "yoghurt": "🥣", "yogurt": "🥣", "cream": "🥛", "sour cream": "🥛",
    "ice cream": "🍨",
    # meat & seafood
    "beef": "🥩", "mince": "🥩", "steak": "🥩", "lamb": "🥩", "pork": "🥓",
    "bacon": "🥓", "ham": "🍖", "salami": "🍖", "chicken": "🍗", "sausage": "🌭",
    "sausages": "🌭", "fish": "🐟", "salmon": "🐟", "tuna": "🐟", "prawns": "🦐",
    "tofu": "🥡",
    # pantry
    "rice": "🍚", "pasta": "🍝", "spaghetti": "🍝", "noodles": "🍜", "flour": "🌾",
    "sugar": "🧂", "salt": "🧂", "oil": "🫒", "honey": "🍯", "jam": "🍯",
    "peanut butter": "🥜", "nuts": "🥜", "soup": "🥫", "tin": "🥫", "tinned": "🥫",
    "tomato paste": "🥫", "sauce": "🥫", "mayonnaise": "🥫", "vegemite": "🥫",
    "promite": "🥫", "cereal": "🥣", "oats": "🥣", "gnocchi": "🍝", "agnolotti": "🍝",
    "pastizzis": "🥟", "dumplings": "🥟",
    # snacks & drinks
    "chips": "🍟", "crinkle": "🍟", "chocolate": "🍫", "choc": "🍫", "mars": "🍫",
    "kitkat": "🍫", "smarties": "🍫", "lollies": "🍬", "jelly beans": "🍬",
    "party mix": "🍬", "biscuits": "🍪", "cookies": "🍪", "wafers": "🍪",
    "crackers": "🍘", "popcorn": "🍿", "juice": "🧃", "water": "💧", "coffee": "☕",
    "tea": "🍵", "soft drink": "🥤", "cola": "🥤", "lemonade": "🥤", "energy": "⚡",
    "beer": "🍺", "wine": "🍷",
    # frozen
    "frozen": "🧊", "ice": "🧊", "peas": "🫛", "burger": "🍔", "pizza": "🍕",
    # household & personal
    "toilet paper": "🧻", "paper towel": "🧻", "tissues": "🧻", "nappy": "👶",
    "nappies": "👶", "baby": "👶", "romper": "👶", "dishwasher": "🍽️",
    "detergent": "🧴", "laundry": "🧺", "soap": "🧼", "body wash": "🧼",
    "shampoo": "🧴", "conditioner": "🧴", "toothpaste": "🪥", "toothbrush": "🪥",
    "sunscreen": "🧴", "bin bags": "🗑️", "bags": "🛍️", "battery": "🔋",
    "batteries": "🔋", "dog": "🐕", "cat": "🐈", "pet": "🐾",
}

DEFAULT_ICON = "🛒"

_KEYS = sorted(KEYWORD_ICONS, key=len, reverse=True)
_PATTERNS = [(re.compile(rf"\b{re.escape(k)}\b"), KEYWORD_ICONS[k]) for k in _KEYS]


def guess_icon(name: str) -> str | None:
    """Return an emoji for the item name, or None if nothing matches."""
    text = name.lower()
    for pattern, icon in _PATTERNS:
        if pattern.search(text):
            return icon
    return None
