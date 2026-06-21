"""Tests for the quick-capture core (routing + hotkey parsing).

The GUI/tray/hotkey-loop are Windows- and display-dependent and are not
exercised here; we test the pure hotkey parser and the capture router, which
hold the logic that matters.
"""

from __future__ import annotations

import pytest

from nb.quickcapture.capture import Location, capture_text, list_locations
from nb.quickcapture.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    parse_hotkey,
)


# --------------------------------------------------------------------------- #
# parse_hotkey
# --------------------------------------------------------------------------- #
class TestParseHotkey:
    def test_ctrl_alt_letter(self) -> None:
        mods, vk = parse_hotkey("ctrl+alt+n")
        assert mods == (MOD_CONTROL | MOD_ALT)
        assert vk == ord("N")

    def test_is_case_insensitive(self) -> None:
        assert parse_hotkey("CTRL+Alt+N") == parse_hotkey("ctrl+alt+n")

    def test_all_modifiers_and_named_key(self) -> None:
        mods, vk = parse_hotkey("ctrl+shift+win+space")
        assert mods == (MOD_CONTROL | MOD_SHIFT | MOD_WIN)
        assert vk == 0x20

    def test_function_key(self) -> None:
        _mods, vk = parse_hotkey("ctrl+f12")
        assert vk == 0x7B  # VK_F12

    def test_modifier_aliases(self) -> None:
        assert parse_hotkey("control+super+n") == (MOD_CONTROL | MOD_WIN, ord("N"))

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_hotkey("   ")

    def test_no_main_key_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_hotkey("ctrl+alt")

    def test_multiple_main_keys_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_hotkey("ctrl+a+b")

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_hotkey("ctrl+nope")


# --------------------------------------------------------------------------- #
# list_locations
# --------------------------------------------------------------------------- #
def test_list_locations_today_first(mock_config) -> None:
    locations = list_locations()
    assert locations[0] == Location(label="Today (daily note)", notebook=None)
    names = [loc.notebook for loc in locations]
    # The built-in daily notebook is folded into the "Today" entry.
    assert "daily" not in names
    assert "projects" in names
    assert "work" in names


# --------------------------------------------------------------------------- #
# capture_text
# --------------------------------------------------------------------------- #
def test_capture_todo_to_daily(mock_config, fixed_today) -> None:
    summary = capture_text("buy milk @due(friday) #errand")

    assert "Added todo" in summary
    daily = mock_config.notes_root / "daily"
    files = list(daily.rglob("*.md"))
    assert files, "expected a daily note to be created"
    content = files[0].read_text(encoding="utf-8")
    assert "- [ ] buy milk @due(friday) #errand" in content


def test_capture_todo_to_notebook(mock_config) -> None:
    from datetime import date

    today = date.today().isoformat()
    summary = capture_text("ship the thing", notebook="projects")

    assert summary == f"Added todo to projects/{today}.md"
    note = mock_config.notes_root / "projects" / f"{today}.md"
    assert note.exists()
    assert "- [ ] ship the thing" in note.read_text(encoding="utf-8")


def test_capture_plain_line_is_timestamped(mock_config, fixed_today) -> None:
    summary = capture_text("just a thought", as_todo=False)

    assert "Logged to" in summary
    files = list((mock_config.notes_root / "daily").rglob("*.md"))
    content = files[0].read_text(encoding="utf-8")
    assert "just a thought" in content
    # Plain captures are not checkboxes.
    assert "- [ ] just a thought" not in content


def test_capture_empty_text_raises(mock_config) -> None:
    with pytest.raises(ValueError):
        capture_text("   ")


# --------------------------------------------------------------------------- #
# autostart (pure command-building only; registry I/O is not exercised)
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# state (last-used location + toggle)
# --------------------------------------------------------------------------- #
def test_state_defaults_to_empty(mock_config) -> None:
    from nb.quickcapture import state

    assert state.load_state() == {}


def test_state_round_trip(mock_config) -> None:
    from nb.quickcapture import state

    state.save_state("projects", False)
    assert state.load_state() == {"notebook": "projects", "as_todo": False}

    # Overwriting replaces the prior value.
    state.save_state(None, True)
    assert state.load_state() == {"notebook": None, "as_todo": True}


def test_state_corrupt_file_is_ignored(mock_config) -> None:
    from nb.quickcapture import state

    state._state_path().write_text("not json", encoding="utf-8")
    assert state.load_state() == {}


def test_autostart_build_command() -> None:
    from nb.quickcapture import autostart

    command = autostart.build_command("ctrl+alt+j")
    assert "-m nb.quickcapture" in command
    assert "--hotkey ctrl+alt+j" in command
    # The launcher path is quoted to survive spaces in the install path.
    assert command.startswith('"')
