"""Persisted popup state (last-used location + toggle).

Remembers the last capture destination and the todo/plain toggle so the popup
reopens where you left off instead of resetting to Today every time. Stored as
a small JSON file under ``notes_root/.nb/``.
"""

from __future__ import annotations

import json

from nb.config import get_config

_STATE_FILE = "quickcapture.json"


def _state_path():
    return get_config().notes_root / ".nb" / _STATE_FILE


def load_state() -> dict:
    """Return the saved popup state, or ``{}`` if none/unreadable."""
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(notebook: str | None, as_todo: bool) -> None:
    """Persist the last-used destination and toggle. Best-effort (never raises)."""
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"notebook": notebook, "as_todo": as_todo}),
            encoding="utf-8",
        )
    except OSError:
        pass
