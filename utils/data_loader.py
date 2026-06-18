"""
utils/data_loader.py

Helper functions for reading the two JSON data files the project uses:
  - data/listings.json      → the mock thrift store catalogue
  - data/wardrobe_schema.json → the example + empty wardrobe templates

WHY this file exists: instead of every tool opening and parsing JSON on its
own, we centralise file I/O here. Tools just call load_listings() and get a
plain Python list back — they never touch file paths or JSON parsing.
"""

import json
import os
from typing import Optional

# Build an absolute path to the data/ folder.
# __file__ is the path to THIS file (data_loader.py).
# os.path.dirname(__file__) is the utils/ folder.
# ".." goes one level up to the project root, then into data/.
# This means the code works no matter what directory you run Python from.
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_listings() -> list[dict]:
    """
    Read data/listings.json and return every listing as a list of dicts.

    Each listing dict has these fields:
        id (str)          — unique identifier, e.g. "listing_001"
        title (str)       — human-readable name, e.g. "Faded Band Tee"
        description (str) — longer text description of the item
        category (str)    — one of: tops, bottoms, outerwear, shoes, accessories
        style_tags (list) — e.g. ["vintage", "graphic", "90s"]
        size (str)        — e.g. "M", "US 8", "W30", "One Size"
        condition (str)   — one of: excellent, good, fair
        price (float)     — selling price in USD
        colors (list)     — e.g. ["black", "white"]
        brand (str|None)  — brand name, or None if unlisted
        platform (str)    — where it's listed: depop, thredUp, or poshmark

    Returns a fresh list every time (reads from disk each call).
    """
    path = os.path.join(_DATA_DIR, "listings.json")
    with open(path, "r", encoding="utf-8") as f:
        # json.load() parses the file into Python objects automatically.
        # encoding="utf-8" is important — some listing titles have em dashes
        # (U+2014) which only decode correctly in UTF-8.
        return json.load(f)


def load_wardrobe_schema() -> dict:
    """
    Read data/wardrobe_schema.json and return the full schema dict.

    The JSON file has three top-level keys:
        schema           — field definitions (not used at runtime, just documentation)
        example_wardrobe — a ready-made wardrobe with ~10 real items
        empty_wardrobe   — {"items": []} — starting point for a new user

    Most callers don't need the raw schema; use get_example_wardrobe() or
    get_empty_wardrobe() instead.
    """
    path = os.path.join(_DATA_DIR, "wardrobe_schema.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_example_wardrobe() -> dict:
    """
    Shortcut — returns just the example_wardrobe section.

    The returned dict looks like:
        {"items": [{"name": "Baggy straight-leg jeans", "category": "bottoms", ...}, ...]}

    Use this in the UI when the user selects "Example wardrobe", and in tests
    when you need a wardrobe with real items.
    """
    schema = load_wardrobe_schema()
    # Pull out just the example_wardrobe key — we don't need the rest.
    return schema["example_wardrobe"]


def get_empty_wardrobe() -> dict:
    """
    Shortcut — returns the empty wardrobe template: {"items": []}.

    Use this when the user selects "Empty wardrobe (new user)" in the UI.
    suggest_outfit handles an empty items list by giving general styling advice
    instead of naming specific wardrobe pieces.
    """
    schema = load_wardrobe_schema()
    return schema["empty_wardrobe"]


# --- Quick sanity check ---
# Running this file directly (python utils/data_loader.py) prints a summary
# so you can confirm the data files are readable without running the full app.
if __name__ == "__main__":
    listings = load_listings()
    print(f"Loaded {len(listings)} listings.")
    print(f"First listing: {listings[0]['title']} — ${listings[0]['price']}")

    wardrobe = get_example_wardrobe()
    print(f"\nExample wardrobe has {len(wardrobe['items'])} items.")
    print(f"First item: {wardrobe['items'][0]['name']}")
