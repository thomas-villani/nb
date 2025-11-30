"""Note alias management for quick access."""

from __future__ import annotations

from pathlib import Path

from nb.index.db import get_db
from nb.utils.hashing import normalize_path


def add_note_alias(alias: str, path: Path, notebook: str | None = None) -> None:
    """Add an alias for a note.

    Args:
        alias: The alias name (e.g., "readme", "standup")
        path: Absolute path to the note file
        notebook: Optional notebook name for context

    Raises:
        ValueError: If alias already exists
    """
    db = get_db()
    normalized = normalize_path(path)

    # Check if alias already exists
    existing = db.fetchone("SELECT path FROM note_aliases WHERE alias = ?", (alias,))
    if existing:
        raise ValueError(
            f"Alias '{alias}' already exists (points to {existing['path']})"
        )

    db.execute(
        "INSERT INTO note_aliases (alias, path, notebook) VALUES (?, ?, ?)",
        (alias, normalized, notebook),
    )
    db.commit()


def remove_note_alias(alias: str) -> bool:
    """Remove a note alias.

    Args:
        alias: The alias to remove

    Returns:
        True if alias was found and removed, False otherwise.
    """
    db = get_db()
    result = db.execute("DELETE FROM note_aliases WHERE alias = ?", (alias,))
    db.commit()
    return result.rowcount > 0


def get_note_by_alias(alias: str) -> Path | None:
    """Resolve an alias to a note path.

    Args:
        alias: The alias to resolve

    Returns:
        Absolute path to the note file, or None if alias not found.
    """
    from nb.config import get_config

    db = get_db()
    row = db.fetchone("SELECT path FROM note_aliases WHERE alias = ?", (alias,))
    if row:
        path = Path(row["path"])
        # Handle relative paths by joining with notes_root
        if not path.is_absolute():
            config = get_config()
            path = config.notes_root / path
        return path
    return None


def list_note_aliases() -> list[tuple[str, Path, str | None]]:
    """List all note aliases.

    Returns:
        List of (alias, absolute_path, notebook) tuples.
    """
    from nb.config import get_config

    config = get_config()
    db = get_db()
    rows = db.fetchall("SELECT alias, path, notebook FROM note_aliases ORDER BY alias")
    result = []
    for row in rows:
        path = Path(row["path"])
        if not path.is_absolute():
            path = config.notes_root / path
        result.append((row["alias"], path, row["notebook"]))
    return result


def update_note_alias(alias: str, path: Path, notebook: str | None = None) -> bool:
    """Update an existing alias to point to a new path.

    Args:
        alias: The alias to update
        path: New path for the alias
        notebook: Optional notebook name

    Returns:
        True if alias was found and updated, False otherwise.
    """
    db = get_db()
    normalized = normalize_path(path)
    result = db.execute(
        "UPDATE note_aliases SET path = ?, notebook = ? WHERE alias = ?",
        (normalized, notebook, alias),
    )
    db.commit()
    return result.rowcount > 0
