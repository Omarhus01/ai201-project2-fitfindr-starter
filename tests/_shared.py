"""
Shared constants and helpers for the FitFindr test suite. Not a test module itself
(no test_ prefix, so pytest won't collect it) — imported by the split test files.
"""

import tools

FIT_CARD_EMPTY_GUARD = "No outfit to caption yet — generate a styling idea first."
FIT_CARD_FALLBACK = (
    "Couldn't write a caption for this one right now — "
    "but it's a great find worth showing off."
)

FALLBACK_2 = (
    "Couldn't generate a full styling idea for this one — "
    "but it's a versatile piece worth grabbing."
)

OUTFIT = "Wear it with baggy jeans and chunky sneakers for an easy y2k look."

# A minimal valid listing dict for the Tool 2/3 tests (no network — _chat is patched).
SAMPLE_ITEM = {
    "id": "lst_x", "title": "Vintage Band Tee", "description": "soft faded cotton",
    "category": "tops", "style_tags": ["vintage", "graphic tee"], "size": "M",
    "condition": "good", "price": 19.0, "colors": ["grey"], "brand": None,
    "platform": "depop",
}

ONE_A = (
    "I couldn't read that request — try naming an item, a size, or a price, "
    "e.g. 'vintage denim jacket size M under $40.'"
)
SERVICE_ERROR = (
    "FitFindr is having trouble reaching its service right now — "
    "please try again in a moment."
)
ONE_B = (
    "FitFindr only helps find and style secondhand clothing. Tell me what you're "
    "after — for example, 'vintage denim jacket, size M, under $40' — and I'll dig "
    "something up."
)


def _scope(in_scope=True, description="vintage graphic tee", size=None, max_price=30.0):
    """Fake _parse_query() return value for run_agent loop tests."""
    return {
        "description": description, "size": size,
        "max_price": max_price, "in_scope": in_scope,
    }


def _session(**overrides):
    """A full default session dict, for stubbing run_agent in handle_query tests."""
    base = {
        "query": "", "parsed": {}, "search_results": [], "selected_item": None,
        "wardrobe": {}, "outfit_suggestion": None, "fit_card": None, "error": None,
        "loosened": None, "price_check": None,
    }
    base.update(overrides)
    return base


def _real_item(title_substring):
    """Look up a real listing by a substring of its title (compare_price tests)."""
    for listing in tools.load_listings():
        if title_substring in listing["title"]:
            return listing
    raise AssertionError(f"no listing found containing {title_substring!r}")
