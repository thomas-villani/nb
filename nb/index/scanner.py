"""Filesystem scanning and indexing for nb."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from nb.config import get_config
from nb.core.notes import get_note
from nb.core.todos import extract_todos
from nb.index.db import get_db
from nb.index.todos_repo import delete_todos_for_source, upsert_todo
from nb.utils.hashing import make_note_hash


def scan_notes(notes_root: Path | None = None) -> list[Path]:
    """Find all markdown files in the notes root.

    Excludes hidden directories and .nb directory.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if not notes_root.exists():
        return []

    notes = []
    for md_file in notes_root.rglob("*.md"):
        # Skip hidden directories and .nb
        if any(part.startswith(".") for part in md_file.relative_to(notes_root).parts):
            continue
        notes.append(md_file)

    return sorted(notes)


def get_file_hash(path: Path) -> str:
    """Compute content hash for a file."""
    content = path.read_text(encoding="utf-8")
    return make_note_hash(content)


def needs_reindex(path: Path, notes_root: Path | None = None) -> bool:
    """Check if a file needs to be reindexed.

    Returns True if:
    - File is not in the database
    - File's content hash has changed
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    try:
        relative = path.relative_to(notes_root)
    except ValueError:
        relative = path

    db = get_db()
    row = db.fetchone(
        "SELECT content_hash FROM notes WHERE path = ?",
        (str(relative),),
    )

    if not row:
        return True

    current_hash = get_file_hash(path)
    return row["content_hash"] != current_hash


def index_note(path: Path, notes_root: Path | None = None) -> None:
    """Index a single note file.

    Parses the note and its todos, storing them in the database.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    note = get_note(path, notes_root)
    if not note:
        return

    db = get_db()

    # Upsert note
    db.execute(
        """
        INSERT OR REPLACE INTO notes (path, title, date, notebook, content_hash, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(note.path),
            note.title,
            note.date.isoformat() if note.date else None,
            note.notebook,
            note.content_hash,
            datetime.now().isoformat(),
        ),
    )

    # Update tags
    db.execute("DELETE FROM note_tags WHERE note_path = ?", (str(note.path),))
    if note.tags:
        db.executemany(
            "INSERT INTO note_tags (note_path, tag) VALUES (?, ?)",
            [(str(note.path), tag) for tag in note.tags],
        )

    # Update links
    db.execute("DELETE FROM note_links WHERE source_path = ?", (str(note.path),))
    if note.links:
        db.executemany(
            "INSERT INTO note_links (source_path, target_path, display_text) VALUES (?, ?, ?)",
            [(str(note.path), link, link) for link in note.links],
        )

    db.commit()

    # Index todos
    if path.is_absolute():
        full_path = path
    else:
        full_path = notes_root / path

    # Determine source type
    if full_path.name == "todo.md":
        source_type = "inbox"
    else:
        source_type = "note"

    # Delete existing todos for this file
    delete_todos_for_source(full_path)

    # Extract and index new todos
    todos = extract_todos(full_path, source_type=source_type, notes_root=notes_root)
    for todo in todos:
        upsert_todo(todo)


def index_all_notes(notes_root: Path | None = None, force: bool = False) -> int:
    """Index all notes in the notes root.

    Args:
        notes_root: Override notes root directory
        force: If True, reindex all files even if unchanged

    Returns:
        Number of files indexed.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    note_files = scan_notes(notes_root)
    count = 0

    for path in note_files:
        if force or needs_reindex(path, notes_root):
            index_note(path, notes_root)
            count += 1

    return count


def index_todos_from_file(path: Path, notes_root: Path | None = None) -> int:
    """Index todos from a single file.

    Returns the number of todos indexed.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if not path.is_absolute():
        path = notes_root / path

    # Determine source type
    if path.name == "todo.md":
        source_type = "inbox"
    else:
        source_type = "note"

    # Delete existing todos for this file
    delete_todos_for_source(path)

    # Extract and index new todos
    todos = extract_todos(path, source_type=source_type, notes_root=notes_root)
    for todo in todos:
        upsert_todo(todo)

    return len(todos)


def remove_deleted_notes(notes_root: Path | None = None) -> int:
    """Remove notes from the database that no longer exist on disk.

    Returns the number of notes removed.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()
    rows = db.fetchall("SELECT path FROM notes")

    removed = 0
    for row in rows:
        full_path = notes_root / row["path"]
        if not full_path.exists():
            db.execute("DELETE FROM notes WHERE path = ?", (row["path"],))
            # Todos are deleted via CASCADE
            removed += 1

    if removed:
        db.commit()

    return removed
