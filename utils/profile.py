"""
utils/profile.py  —  Stretch 4: style profile memory

Saves and loads the user's wardrobe choice + style note to disk so the UI
can prefill them on the next run. This means the user doesn't have to
re-select "Example wardrobe" and re-type "I like y2k and grunge" every time.

This is NOT an agent tool — the planning loop never calls it.
It's a UI helper that app.py calls directly:
  - at startup: load_profile() → prefill the Gradio inputs
  - on "Save my style profile" click: save_profile() → write to disk
"""

import json
import os

# Store the profile next to the other data files.
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_PROFILE_PATH = os.path.join(_DATA_DIR, "style_profile.json")


def load_profile(path: str = DEFAULT_PROFILE_PATH) -> dict | None:
    """
    Load the saved style profile from disk.

    Returns:
        A dict like {"wardrobe_choice": "Example wardrobe", "style_note": "I like y2k"}
        if the file exists and is valid, or None otherwise.

    WHY it returns None instead of raising: on a fresh clone there's no profile
    file yet, and that's totally fine — the UI just shows its default values.
    Returning None lets the caller handle "no profile" without a try/except.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        # FileNotFoundError → first run, no file yet. That's expected.
        # json.JSONDecodeError → file got corrupted somehow. Treat as missing.
        # OSError → permissions issue or similar. Treat as missing.
        return None

    # Extra safety: make sure what we loaded is actually a dict.
    if not isinstance(data, dict):
        return None
    return data


def save_profile(profile: dict, path: str = DEFAULT_PROFILE_PATH) -> None:
    """
    Write the style profile to disk, creating the data/ directory if needed.

    Args:
        profile: {"wardrobe_choice": str, "style_note": str}
                 These are the exact values from the two Gradio UI inputs.
        path:    Where to save (defaults to data/style_profile.json).
                 Tests pass a temp path here so they don't touch the real file.

    WHY exist_ok=True on makedirs: if the data/ folder already exists (it
    always does in normal usage) makedirs would crash without this flag.
    """
    # Create the directory if it somehow doesn't exist yet.
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        # indent=2 makes the JSON human-readable if you open the file manually.
        json.dump(profile, f, indent=2)
