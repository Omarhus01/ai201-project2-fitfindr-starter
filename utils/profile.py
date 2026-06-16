"""
utils/profile.py

Persistence for the Stretch 4 style profile — a single-user, single-file record of
the user's chosen wardrobe and an optional free-text style note, so app.py can
prefill the UI on a fresh run instead of asking the user to re-describe themselves
every session.

Not part of tools.py: this isn't an agent tool the planning loop calls, it's a
persistence helper the UI calls directly.
"""

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_PROFILE_PATH = os.path.join(_DATA_DIR, "style_profile.json")


def load_profile(path: str = DEFAULT_PROFILE_PATH) -> dict | None:
    """
    Load the saved style profile.

    Returns:
        The profile dict ({"wardrobe_choice": str, "style_note": str}), or None if
        the file doesn't exist or contains invalid JSON. Never raises.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict):
        return None
    return data


def save_profile(profile: dict, path: str = DEFAULT_PROFILE_PATH) -> None:
    """
    Save the style profile, creating the containing directory if needed.

    Args:
        profile: {"wardrobe_choice": str, "style_note": str}.
        path:    Destination file path (defaults to the real profile location).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
