"""Capture routing for quick-capture.

Resolves the selected location to a note and appends the captured text,
reusing the existing core todo helpers so captured items appear in `nb todo`
immediately (they upsert into the index DB).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from nb.config import get_config


@dataclass(frozen=True)
class Location:
    """A capture destination shown in the popup dropdown.

    ``notebook`` is ``None`` for the special "today's daily note" target;
    otherwise it is the name of a configured notebook.
    """

    label: str
    notebook: str | None


def list_locations() -> list[Location]:
    """Build the ordered list of capture destinations for the popup.

    The first entry is always today's daily note; the rest are the configured
    notebooks (excluding the built-in ``daily`` notebook, which the first entry
    already covers).
    """
    config = get_config()
    locations = [Location(label="Today (daily note)", notebook=None)]
    for name in config.notebook_names():
        if name == "daily":
            continue
        locations.append(Location(label=name, notebook=name))
    return locations


def _resolve_today_note(notebook: str) -> Path:
    """Resolve (creating if needed) today's note within ``notebook``.

    Mirrors the behaviour of the MCP ``remember`` tool and ``nb today``: a
    date-based notebook gets today's dated note; a flat notebook gets a note
    named for today's date.
    """
    from nb.core.notebooks import ensure_notebook_note, is_notebook_date_based

    today = date.today()
    if is_notebook_date_based(notebook):
        return ensure_notebook_note(notebook, dt=today)
    return ensure_notebook_note(notebook, dt=today, name=today.isoformat())


def capture_text(
    text: str, notebook: str | None = None, *, as_todo: bool = True
) -> str:
    """Append ``text`` to the chosen location and return a short summary.

    Args:
        text: The captured line (may include ``@due``/``@priority``/``#tags``).
        notebook: Destination notebook name, or ``None`` for today's daily note.
        as_todo: If ``True`` (default), write a ``- [ ]`` checkbox so it shows
            in ``nb todo``. If ``False``, append a timestamped plain line
            (like ``nb log``).

    Returns:
        A human-readable summary, e.g. ``"Added todo to 2026-06-21.md"``.

    Raises:
        ValueError: If ``text`` is empty after stripping.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to capture: text was empty.")

    if as_todo:
        return _capture_todo(text, notebook)
    return _capture_plain(text, notebook)


def _capture_todo(text: str, notebook: str | None) -> str:
    from nb.core.todos import add_todo_to_daily_note, add_todo_to_note

    if notebook is None:
        todo = add_todo_to_daily_note(text)
        return f"Added todo to {todo.source.path.name}"

    path = _resolve_today_note(notebook)
    todo = add_todo_to_note(text, path)
    return f"Added todo to {notebook}/{path.name}"


def _capture_plain(text: str, notebook: str | None) -> str:
    from nb.core.notes import _reindex_note_after_edit, ensure_daily_note

    config = get_config()
    if notebook is None:
        path = ensure_daily_note(date.today())
        dest = path.name
    else:
        path = _resolve_today_note(notebook)
        dest = f"{notebook}/{path.name}"

    timestamp = datetime.now().strftime(f"{config.date_format} {config.time_format}")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n{timestamp}: {text}\n")

    _reindex_note_after_edit(path, config.notes_root)
    return f"Logged to {dest}"
