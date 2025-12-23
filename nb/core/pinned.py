"""Pinned notes management for quick access."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from nb.index.db import get_db
from nb.utils.hashing import normalize_path


def pin_note(path: Path, notebook: str | None = None) -> None:
    """Pin a note for quick access.

    Args:
        path: Absolute or relative path to the note file
        notebook: Optional notebook context for the pin

    If the note is already pinned, this updates the pinned_at timestamp.
    """
    db = get_db()
    normalized = normalize_path(path)
    # Use empty string for NULL notebook (schema uses NOT NULL DEFAULT '')
    notebook_key = notebook or ""

    db.execute(
        """INSERT OR REPLACE INTO pinned_notes
           (note_path, notebook, pinned_at) VALUES (?, ?, ?)""",
        (normalized, notebook_key, datetime.now().isoformat()),
    )
    db.commit()


def unpin_note(path: Path) -> bool:
    """Unpin a note.

    Args:
        path: Path to the note to unpin

    Returns:
        True if note was pinned and is now unpinned, False if note wasn't pinned.
    """
    db = get_db()
    normalized = normalize_path(path)
    result = db.execute(
        "DELETE FROM pinned_notes WHERE note_path = ?",
        (normalized,),
    )
    db.commit()
    return result.rowcount > 0


def is_pinned(path: Path) -> bool:
    """Check if a note is pinned.

    Args:
        path: Path to the note to check

    Returns:
        True if the note is pinned.
    """
    db = get_db()
    normalized = normalize_path(path)
    row = db.fetchone(
        "SELECT 1 FROM pinned_notes WHERE note_path = ?",
        (normalized,),
    )
    return row is not None


def list_pinned_notes(
    notebook: str | None = None,
) -> list[tuple[Path, str, datetime]]:
    """List all pinned notes, optionally filtered by notebook.

    Args:
        notebook: Optional notebook filter

    Returns:
        List of (path, notebook, pinned_at) tuples, most recently pinned first.
    """
    from nb.config import get_config

    config = get_config()
    db = get_db()

    if notebook:
        rows = db.fetchall(
            """SELECT note_path, notebook, pinned_at FROM pinned_notes
               WHERE notebook = ? ORDER BY pinned_at DESC""",
            (notebook,),
        )
    else:
        rows = db.fetchall(
            "SELECT note_path, notebook, pinned_at FROM pinned_notes ORDER BY pinned_at DESC"
        )

    result = []
    for row in rows:
        path = Path(row["note_path"])
        if not path.is_absolute():
            path = config.notes_root / path
        pinned_at = datetime.fromisoformat(row["pinned_at"])
        result.append((path, row["notebook"], pinned_at))

    return result


def get_pinned_note_paths(notebook: str | None = None) -> set[str]:
    """Get set of normalized paths for all pinned notes.

    Useful for quickly checking if notes in a list are pinned.

    Args:
        notebook: Optional notebook filter

    Returns:
        Set of normalized path strings.
    """
    db = get_db()

    if notebook:
        rows = db.fetchall(
            "SELECT note_path FROM pinned_notes WHERE notebook = ?",
            (notebook,),
        )
    else:
        rows = db.fetchall("SELECT note_path FROM pinned_notes")

    return {row["note_path"] for row in rows}
