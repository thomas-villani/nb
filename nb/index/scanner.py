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

# Flag to enable/disable vector search indexing
# Set to False to skip vector indexing (useful if embeddings not available)
ENABLE_VECTOR_INDEXING = True


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


def index_note(
    path: Path,
    notes_root: Path | None = None,
    index_vectors: bool = True,
) -> None:
    """Index a single note file.

    Parses the note and its todos, storing them in the database.

    Args:
        path: Path to the note file.
        notes_root: Override notes root directory.
        index_vectors: Whether to also index to localvectordb for search.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    note = get_note(path, notes_root)
    if not note:
        return

    # Read the full content for storage and vector indexing
    if path.is_absolute():
        full_path = path
    else:
        full_path = notes_root / path

    try:
        content = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        content = ""

    db = get_db()

    # Upsert note (now includes content column)
    db.execute(
        """
        INSERT OR REPLACE INTO notes (path, title, date, notebook, content_hash, content, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(note.path),
            note.title,
            note.date.isoformat() if note.date else None,
            note.notebook,
            note.content_hash,
            content,
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

    # Index to localvectordb for search
    if index_vectors and ENABLE_VECTOR_INDEXING and content:
        try:
            from nb.index.search import get_search

            search = get_search()
            search.index_note(note, content)
        except Exception:
            # Don't fail indexing if vector search fails
            # (e.g., embedding service not available)
            pass

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


def index_all_notes(
    notes_root: Path | None = None,
    force: bool = False,
    index_vectors: bool = True,
) -> int:
    """Index all notes in the notes root.

    Args:
        notes_root: Override notes root directory
        force: If True, reindex all files even if unchanged
        index_vectors: Whether to also index to localvectordb for search

    Returns:
        Number of files indexed.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    note_files = scan_notes(notes_root)
    count = 0

    for path in note_files:
        if force or needs_reindex(path, notes_root):
            index_note(path, notes_root, index_vectors=index_vectors)
            count += 1

    return count


def rebuild_search_index(notes_root: Path | None = None) -> int:
    """Rebuild the localvectordb search index from scratch.

    Reads all notes from the database and indexes them to localvectordb.
    Useful when the vector index is corrupted or needs to be regenerated.

    Args:
        notes_root: Override notes root directory

    Returns:
        Number of notes indexed.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if not ENABLE_VECTOR_INDEXING:
        return 0

    from nb.index.search import get_search

    db = get_db()
    search = get_search()

    # Get all notes from database
    rows = db.fetchall("SELECT path, title, date, notebook, content FROM notes")
    count = 0

    for row in rows:
        if not row["content"]:
            continue

        # Build a simple note-like object for indexing
        from nb.models import Note

        note = Note(
            path=Path(row["path"]),
            title=row["title"] or "",
            date=None,  # Will be parsed from string if needed
            tags=[],  # We'd need to query tags separately
            links=[],
            attachments=[],
            notebook=row["notebook"] or "",
            content_hash="",
        )

        # Get tags for this note
        tag_rows = db.fetchall(
            "SELECT tag FROM note_tags WHERE note_path = ?",
            (row["path"],),
        )
        note.tags = [r["tag"] for r in tag_rows]

        # Parse date if present
        if row["date"]:
            from datetime import date as date_type

            try:
                note.date = date_type.fromisoformat(row["date"])
            except ValueError:
                pass

        try:
            search.index_note(note, row["content"])
            count += 1
        except Exception:
            # Continue on errors
            pass

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


def scan_linked_files() -> int:
    """Scan all linked external todo files and index their todos.

    Returns the number of todos indexed.
    """
    from nb.core.links import list_linked_files

    linked_files = list_linked_files()
    total_todos = 0

    for linked in linked_files:
        if not linked.path.exists():
            continue

        # Delete existing todos for this linked file
        delete_todos_for_source(linked.path)

        # Extract and index todos
        todos = extract_todos(
            linked.path,
            source_type="linked",
            notes_root=get_config().notes_root,
            external=True,
            alias=linked.alias,
        )

        for todo in todos:
            upsert_todo(todo)
            total_todos += 1

    return total_todos


def index_linked_file(path: Path, alias: str | None = None) -> int:
    """Index todos from a single linked external file.

    Args:
        path: Path to the linked file.
        alias: Optional alias for the file.

    Returns:
        Number of todos indexed.
    """
    if not path.exists():
        return 0

    # Delete existing todos for this file
    delete_todos_for_source(path)

    # Extract and index todos
    todos = extract_todos(
        path,
        source_type="linked",
        notes_root=get_config().notes_root,
        external=True,
        alias=alias,
    )

    for todo in todos:
        upsert_todo(todo)

    return len(todos)


def remove_deleted_notes(notes_root: Path | None = None) -> int:
    """Remove notes from the database that no longer exist on disk.

    Also removes them from the localvectordb search index.

    Returns the number of notes removed.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()
    # Only check internal notes (external=0 or NULL)
    rows = db.fetchall(
        "SELECT path, external FROM notes WHERE external IS NULL OR external = 0"
    )

    removed = 0
    removed_paths = []

    for row in rows:
        full_path = notes_root / row["path"]
        if not full_path.exists():
            db.execute("DELETE FROM notes WHERE path = ?", (row["path"],))
            removed_paths.append(row["path"])
            removed += 1

    if removed:
        db.commit()

        # Remove from localvectordb search index
        if ENABLE_VECTOR_INDEXING:
            try:
                from nb.index.search import get_search

                search = get_search()
                for path in removed_paths:
                    search.delete_note(path)
            except Exception:
                # Don't fail if vector search cleanup fails
                pass

    return removed


# =============================================================================
# Linked Note Indexing
# =============================================================================


def index_linked_note(
    path: Path,
    notebook: str,
    alias: str,
    notes_root: Path | None = None,
    index_vectors: bool = True,
) -> None:
    """Index a single linked (external) note file.

    Args:
        path: Absolute path to the note file.
        notebook: Virtual notebook name for the note.
        alias: Alias of the linked note source.
        notes_root: Override notes root directory.
        index_vectors: Whether to index for vector search.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    note = get_note(path, notes_root)
    if not note:
        return

    # Override notebook for linked notes
    note.notebook = notebook

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        content = ""

    db = get_db()

    # Use absolute path as the unique identifier for external notes
    note_path = str(path)

    # Upsert note with external flag
    db.execute(
        """
        INSERT OR REPLACE INTO notes
        (path, title, date, notebook, content_hash, content, external, source_alias, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            note_path,
            note.title,
            note.date.isoformat() if note.date else None,
            notebook,
            note.content_hash,
            content,
            1,  # external = True
            alias,
            datetime.now().isoformat(),
        ),
    )

    # Update tags
    db.execute("DELETE FROM note_tags WHERE note_path = ?", (note_path,))
    if note.tags:
        db.executemany(
            "INSERT INTO note_tags (note_path, tag) VALUES (?, ?)",
            [(note_path, tag) for tag in note.tags],
        )

    # Update links
    db.execute("DELETE FROM note_links WHERE source_path = ?", (note_path,))
    if note.links:
        db.executemany(
            "INSERT INTO note_links (source_path, target_path, display_text) VALUES (?, ?, ?)",
            [(note_path, link, link) for link in note.links],
        )

    db.commit()

    # Index to localvectordb
    if index_vectors and ENABLE_VECTOR_INDEXING and content:
        try:
            from nb.index.search import get_search

            # Update path for search to include notebook context
            note.path = Path(note_path)
            search = get_search()
            search.index_note(note, content)
        except Exception:
            pass

    # Also index todos from this file
    delete_todos_for_source(path)
    todos = extract_todos(path, source_type="linked", notes_root=notes_root)
    for todo in todos:
        upsert_todo(todo)


def scan_linked_notes() -> int:
    """Scan all linked external note files/directories and index them.

    Returns the number of notes indexed.
    """
    from nb.core.links import list_linked_notes, scan_linked_note_files

    linked_notes = list_linked_notes()
    total_notes = 0

    for linked in linked_notes:
        if not linked.path.exists():
            continue

        # Get all files from this linked source
        files = scan_linked_note_files(linked)
        notebook = linked.notebook or f"@{linked.alias}"

        for file_path in files:
            index_linked_note(
                file_path,
                notebook=notebook,
                alias=linked.alias,
            )
            total_notes += 1

    return total_notes


def index_single_linked_note(alias: str) -> int:
    """Index notes from a single linked note source.

    Args:
        alias: Alias of the linked note.

    Returns:
        Number of notes indexed.
    """
    from nb.core.links import get_linked_note, scan_linked_note_files

    linked = get_linked_note(alias)
    if not linked or not linked.path.exists():
        return 0

    files = scan_linked_note_files(linked)
    notebook = linked.notebook or f"@{linked.alias}"

    for file_path in files:
        index_linked_note(
            file_path,
            notebook=notebook,
            alias=linked.alias,
        )

    return len(files)


def remove_linked_note_from_index(alias: str) -> int:
    """Remove all notes from a linked source from the index.

    Args:
        alias: Alias of the linked note source.

    Returns:
        Number of notes removed.
    """
    db = get_db()

    # Get paths to remove from vector index
    rows = db.fetchall(
        "SELECT path FROM notes WHERE source_alias = ?",
        (alias,),
    )
    paths = [row["path"] for row in rows]

    # Remove from database
    cursor = db.execute(
        "DELETE FROM notes WHERE source_alias = ?",
        (alias,),
    )
    db.commit()

    # Remove from vector index
    if ENABLE_VECTOR_INDEXING and paths:
        try:
            from nb.index.search import get_search

            search = get_search()
            for path in paths:
                search.delete_note(path)
        except Exception:
            pass

    return cursor.rowcount
