"""
Tests for utils/profile.py (Stretch 4 persistence). Every test uses tmp_path —
none of these read or write the real data/style_profile.json.
"""

from utils.profile import load_profile, save_profile


def test_profile_save_then_load_round_trips(tmp_path):
    path = tmp_path / "style_profile.json"
    profile = {"wardrobe_choice": "Example wardrobe", "style_note": "I like y2k and grunge"}
    save_profile(profile, path=str(path))
    assert load_profile(path=str(path)) == profile


def test_profile_missing_file_returns_none(tmp_path):
    path = tmp_path / "does_not_exist.json"
    assert load_profile(path=str(path)) is None


def test_profile_corrupt_file_returns_none_no_exception(tmp_path):
    path = tmp_path / "style_profile.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_profile(path=str(path)) is None
