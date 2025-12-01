"""Note operations for nb."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from nb.config import get_config
from nb.models import Note
from nb.utils.editor import open_in_editor
from nb.utils.hashing import make_note_hash, normalize_path
from nb.utils.markdown import (
    create_daily_note_template,
    create_note_template,
    extract_date,
    extract_tags,
    extract_title,
    extract_wiki_links,
    parse_note_file,
)


def get_daily_note_path(dt: date, notes_root: Path | None = None) -> Path:
    """Get the path for a daily note.

    Daily notes are stored as: daily/YYYY/Nov25-Dec01/YYYY-MM-DD.md
    (organized by work week, Monday-Sunday)
    """
    from nb.utils.dates import get_week_folder_name

    if notes_root is None:
        notes_root = get_config().notes_root

    week_folder = get_week_folder_name(dt)
    return notes_root / "daily" / str(dt.year) / week_folder / f"{dt.isoformat()}.md"


def ensure_daily_note(dt: date, notes_root: Path | None = None) -> Path:
    """Ensure a daily note exists, creating it if necessary.

    Returns the path to the note.
    """
    path = get_daily_note_path(dt, notes_root)

    if not path.exists():
        # Create directory structure
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write template
        content = create_daily_note_template(dt)
        path.write_text(content, encoding="utf-8")

    return path


def create_note(
    path: Path,
    title: str | None = None,
    dt: date | None = None,
    tags: list[str] | None = None,
    template: str | None = None,
    notes_root: Path | None = None,
) -> Path:
    """Create a new note at the specified path.

    Args:
        path: Relative path within notes_root (e.g., "projects/myproject/ideas.md")
        title: Optional title for the note
        dt: Date for the note (defaults to today)
        tags: Optional list of tags
        template: Optional template name to use
        notes_root: Override notes root directory

    Returns:
        Absolute path to the created note.

    Raises:
        FileExistsError: If the note already exists.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    # Ensure .md extension
    if not path.suffix:
        path = path.with_suffix(".md")

    full_path = notes_root / path

    if full_path.exists():
        raise FileExistsError(f"Note already exists: {path}")

    # Create directory structure
    full_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate content - use template if specified
    if template:
        from nb.core.templates import read_template, render_template

        template_content = read_template(template, notes_root)
        if template_content:
            # Determine notebook from path
            notebook = path.parts[0] if len(path.parts) > 1 else None
            content = render_template(
                template_content,
                title=title,
                notebook=notebook,
                dt=dt,
            )
        else:
            # Template not found, fall back to default
            content = create_note_template(title=title, dt=dt, tags=tags)
    else:
        content = create_note_template(title=title, dt=dt, tags=tags)

    # Write file
    full_path.write_text(content, encoding="utf-8")

    return full_path


def get_last_modified_note(
    notebook: str | None = None,
    notes_root: Path | None = None,
) -> Path | None:
    """Get the most recently modified note.

    Args:
        notebook: Filter by notebook name
        notes_root: Override notes root directory

    Returns:
        Path to the last modified note, or None if no notes found.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()

    if notebook:
        row = db.fetchone(
            "SELECT path FROM notes WHERE notebook = ? AND mtime IS NOT NULL ORDER BY mtime DESC LIMIT 1",
            (notebook,),
        )
    else:
        row = db.fetchone(
            "SELECT path FROM notes WHERE mtime IS NOT NULL ORDER BY mtime DESC LIMIT 1"
        )

    if row:
        return notes_root / row["path"]
    return None


def get_latest_notes_per_notebook(
    limit: int = 3,
    notes_root: Path | None = None,
) -> dict[str, list[tuple[Path, str | None, list[str]]]]:
    """Get the latest N notes from each notebook.

    Args:
        limit: Maximum number of notes to return per notebook
        notes_root: Override notes root directory

    Returns:
        Dict mapping notebook name to list of (path, title, tags) tuples,
        ordered by modification time descending.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()

    # Get all notebooks with notes
    notebooks = db.fetchall(
        "SELECT DISTINCT notebook FROM notes WHERE notebook IS NOT NULL AND notebook != ''"
    )

    result: dict[str, list[tuple[Path, str | None, list[str]]]] = {}

    for nb_row in notebooks:
        notebook = nb_row["notebook"]
        rows = db.fetchall(
            """SELECT path, title FROM notes
               WHERE notebook = ? AND mtime IS NOT NULL
               ORDER BY mtime DESC LIMIT ?""",
            (notebook, limit),
        )
        if rows:
            notes_with_tags = []
            for row in rows:
                # Get tags for this note
                tag_rows = db.fetchall(
                    "SELECT tag FROM note_tags WHERE note_path = ?",
                    (row["path"],),
                )
                tags = [t["tag"] for t in tag_rows]
                notes_with_tags.append((notes_root / row["path"], row["title"], tags))
            result[notebook] = notes_with_tags

    return result


def get_all_notes(
    notes_root: Path | None = None,
) -> list[tuple[Path, str | None, str, list[str]]]:
    """Get all notes from all notebooks.

    Args:
        notes_root: Override notes root directory

    Returns:
        List of (path, title, notebook, tags) tuples, ordered by notebook then mtime descending.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()

    rows = db.fetchall(
        """SELECT path, title, notebook FROM notes
           WHERE notebook IS NOT NULL AND notebook != ''
           ORDER BY notebook, mtime DESC"""
    )

    result = []
    for row in rows:
        # Get tags for this note
        tag_rows = db.fetchall(
            "SELECT tag FROM note_tags WHERE note_path = ?",
            (row["path"],),
        )
        tags = [t["tag"] for t in tag_rows]
        result.append((notes_root / row["path"], row["title"], row["notebook"], tags))

    return result


def get_notebook_notes_with_metadata(
    notebook: str, notes_root: Path | None = None
) -> list[tuple[Path, str | None, list[str], bool, str | None]]:
    """Get notes from a specific notebook with title, tags, and linked status.

    Args:
        notebook: Name of the notebook (can include @ prefix for linked notebooks)
        notes_root: Override notes root directory

    Returns:
        List of (path, title, tags, is_linked, alias) tuples, ordered by mtime descending.

    """
    from nb.core.links import list_linked_notes
    from nb.index.db import get_db

    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    db = get_db()

    # Query notes for this notebook with metadata
    rows = db.fetchall(
        """SELECT path, title, external FROM notes
           WHERE notebook = ?
           ORDER BY mtime DESC""",
        (notebook,),
    )

    # Build a map of paths to aliases for linked notes
    path_to_alias: dict[str, str] = {}
    for ln in list_linked_notes():
        ln_notebook = ln.notebook or f"@{ln.alias}"
        if ln_notebook == notebook:
            if ln.path.is_file():
                path_to_alias[str(ln.path.resolve())] = ln.alias
            else:
                path_to_alias[f"dir:{ln.path.resolve()}"] = ln.alias

    result = []
    for row in rows:
        note_path_str = row["path"]
        note_path = Path(note_path_str)
        is_external = bool(row["external"])

        # Resolve to absolute path
        if not note_path.is_absolute():
            abs_path = notes_root / note_path
        else:
            abs_path = note_path

        # Get tags for this note
        tag_rows = db.fetchall(
            "SELECT tag FROM note_tags WHERE note_path = ?",
            (note_path_str,),
        )
        tags = [t["tag"] for t in tag_rows]

        # Find alias for linked notes
        alias = None
        if is_external:
            resolved = str(abs_path.resolve())
            if resolved in path_to_alias:
                alias = path_to_alias[resolved]
            else:
                # Check if under a linked directory
                for key, val in path_to_alias.items():
                    if key.startswith("dir:"):
                        dir_path = key[4:]
                        if resolved.startswith(dir_path):
                            alias = val
                            break

        result.append((abs_path, row["title"], tags, is_external, alias))

    return result


@dataclass
class NoteDetails:
    """Extended details for a note."""

    todo_count: int = 0
    mtime: float | None = None
    note_date: str | None = None
    todo_exclude: bool = False


def get_note_details_batch(
    paths: list[Path], notes_root: Path | None = None
) -> dict[Path, NoteDetails]:
    """Get extended details for multiple notes.

    Args:
        paths: List of note paths (absolute)
        notes_root: Override notes root directory

    Returns:
        Dict mapping path to NoteDetails. Paths not in database are omitted.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()
    result: dict[Path, NoteDetails] = {}

    if not paths:
        return result

    # Convert to relative paths for database lookup
    rel_paths = []
    path_map: dict[str, Path] = {}  # rel_path -> abs_path
    for p in paths:
        try:
            rel = p.relative_to(notes_root)
            rel_str = str(rel)
            rel_paths.append(rel_str)
            path_map[rel_str] = p
        except ValueError:
            continue

    if not rel_paths:
        return result

    # Query note details
    placeholders = ",".join("?" * len(rel_paths))
    note_rows = db.fetchall(
        f"""SELECT path, mtime, date, todo_exclude
            FROM notes WHERE path IN ({placeholders})""",
        tuple(rel_paths),
    )

    # Query todo counts
    todo_counts = db.fetchall(
        f"""SELECT source_path, COUNT(*) as count
            FROM todos
            WHERE source_path IN ({placeholders}) AND completed = 0
            GROUP BY source_path""",
        tuple(rel_paths),
    )

    # Build todo count map
    todo_count_map = {row["source_path"]: row["count"] for row in todo_counts}

    # Build result
    for row in note_rows:
        rel_path = row["path"]
        if rel_path in path_map:
            abs_path = path_map[rel_path]
            result[abs_path] = NoteDetails(
                todo_count=todo_count_map.get(rel_path, 0),
                mtime=row["mtime"],
                note_date=row["date"],
                todo_exclude=bool(row["todo_exclude"]),
            )

    return result


def update_note_mtime(path: Path, notes_root: Path | None = None) -> None:
    """Update a note's mtime in the database from the filesystem.

    Args:
        path: Path to the note (absolute or relative to notes_root)
        notes_root: Override notes root directory

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    # Get relative path for database lookup
    if path.is_absolute():
        try:
            relative_path = path.relative_to(notes_root)
        except ValueError:
            relative_path = path
    else:
        relative_path = path
        path = notes_root / path

    # Get current filesystem mtime
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return

    db = get_db()
    db.execute(
        "UPDATE notes SET mtime = ? WHERE path = ?",
        (mtime, normalize_path(relative_path)),
    )
    db.commit()


def get_last_viewed_note(
    notebook: str | None = None,
    notes_root: Path | None = None,
) -> Path | None:
    """Get the most recently viewed note.

    Args:
        notebook: Filter by notebook name
        notes_root: Override notes root directory

    Returns:
        Path to the last viewed note, or None if no views recorded.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()

    if notebook:
        row = db.fetchone(
            """
            SELECT nv.note_path FROM note_views nv
            JOIN notes n ON nv.note_path = n.path
            WHERE n.notebook = ?
            ORDER BY nv.viewed_at DESC LIMIT 1
            """,
            (notebook,),
        )
    else:
        row = db.fetchone(
            "SELECT note_path FROM note_views ORDER BY viewed_at DESC LIMIT 1"
        )

    if row:
        return notes_root / row["note_path"]
    return None


def get_recently_viewed_notes(
    limit: int = 20,
    notebook: str | None = None,
    notes_root: Path | None = None,
) -> list[tuple[Path, datetime]]:
    """Get recently viewed notes with timestamps.

    Args:
        limit: Maximum number of entries to return
        notebook: Filter by notebook name
        notes_root: Override notes root directory

    Returns:
        List of (path, viewed_at) tuples, most recent first.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()

    if notebook:
        rows = db.fetchall(
            """
            SELECT nv.note_path, nv.viewed_at FROM note_views nv
            JOIN notes n ON nv.note_path = n.path
            WHERE n.notebook = ?
            ORDER BY nv.viewed_at DESC LIMIT ?
            """,
            (notebook, limit),
        )
    else:
        rows = db.fetchall(
            "SELECT note_path, viewed_at FROM note_views ORDER BY viewed_at DESC LIMIT ?",
            (limit,),
        )

    result = []
    for row in rows:
        path = notes_root / row["note_path"]
        viewed_at = datetime.fromisoformat(row["viewed_at"])
        result.append((path, viewed_at))

    return result


def get_recently_modified_notes(
    limit: int = 20,
    notebook: str | None = None,
    notes_root: Path | None = None,
) -> list[tuple[Path, datetime]]:
    """Get recently modified notes with timestamps.

    Args:
        limit: Maximum number of entries to return
        notebook: Filter by notebook name
        notes_root: Override notes root directory

    Returns:
        List of (path, mtime) tuples, most recent first.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()

    if notebook:
        rows = db.fetchall(
            """
            SELECT path, mtime FROM notes
            WHERE notebook = ? AND mtime IS NOT NULL
            ORDER BY mtime DESC LIMIT ?
            """,
            (notebook, limit),
        )
    else:
        rows = db.fetchall(
            "SELECT path, mtime FROM notes WHERE mtime IS NOT NULL ORDER BY mtime DESC LIMIT ?",
            (limit,),
        )

    result = []
    for row in rows:
        path = notes_root / row["path"]
        # mtime is stored as Unix timestamp (REAL)
        mtime = datetime.fromtimestamp(row["mtime"])
        result.append((path, mtime))

    return result


def record_note_view(path: Path, notes_root: Path | None = None) -> None:
    """Record that a note was viewed.

    Args:
        path: Path to the note (absolute or relative to notes_root)
        notes_root: Override notes root directory

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    # Get relative path for storage
    if path.is_absolute():
        try:
            relative_path = path.relative_to(notes_root)
        except ValueError:
            # Path is outside notes_root, use absolute
            relative_path = path
    else:
        relative_path = path

    db = get_db()
    db.execute(
        "INSERT INTO note_views (note_path, viewed_at) VALUES (?, ?)",
        (str(relative_path), datetime.now().isoformat()),
    )
    db.commit()


def open_note(path: Path, line: int | None = None) -> None:
    """Open a note in the configured editor.

    After the editor closes, updates the database mtime if the file was modified.

    Args:
        path: Path to the note (absolute or relative to notes_root)
        line: Optional line number to open at

    """
    config = get_config()

    # Resolve path
    if not path.is_absolute():
        path = config.notes_root / path

    if not path.exists():
        raise FileNotFoundError(f"Note not found: {path}")

    # Record the view
    record_note_view(path, config.notes_root)

    # Capture mtime before editing
    try:
        mtime_before = path.stat().st_mtime
    except OSError:
        mtime_before = None

    open_in_editor(path, line=line, editor=config.editor)

    # Re-index the note if file was modified
    try:
        mtime_after = path.stat().st_mtime
        if mtime_before is None or mtime_after != mtime_before:
            update_note_mtime(path, config.notes_root)
            # Re-index the note to pick up any todo changes
            print("Syncing nb...", end="", file=sys.stderr, flush=True)
            _reindex_note_after_edit(path, config.notes_root)
            print(" done", file=sys.stderr)
    except OSError:
        pass


def _reindex_note_after_edit(path: Path, notes_root: Path) -> None:
    """Re-index a note after it has been edited.

    For internal notes, this extracts and updates todos.
    For linked notes, this does a full re-index (note metadata + todos).

    Args:
        path: Absolute path to the note
        notes_root: Notes root directory

    """
    from nb.core.todos import extract_todos
    from nb.index.todos_repo import delete_todos_for_source, upsert_todos_batch

    # Check if this is a linked note (external file)
    try:
        rel_path = path.relative_to(notes_root)
        is_external = False
    except ValueError:
        is_external = True

    if is_external:
        # For linked notes, do a full re-index to update note metadata + todos
        from nb.core.links import list_linked_notes
        from nb.index.scanner import index_linked_note

        for ln in list_linked_notes():
            if ln.path.is_file() and ln.path.resolve() == path.resolve():
                notebook = ln.notebook or f"@{ln.alias}"
                index_linked_note(
                    path,
                    notebook=notebook,
                    alias=ln.alias,
                    notes_root=notes_root,
                    todo_exclude=ln.todo_exclude,
                )
                return
            elif ln.path.is_dir():
                try:
                    path.relative_to(ln.path)
                    notebook = ln.notebook or f"@{ln.alias}"
                    index_linked_note(
                        path,
                        notebook=notebook,
                        alias=ln.alias,
                        notes_root=notes_root,
                        todo_exclude=ln.todo_exclude,
                    )
                    return
                except ValueError:
                    continue
        # Not a linked note, nothing to do
        return

    # Internal note - determine source type and re-extract todos
    from nb.config import get_config as get_cfg

    cfg = get_cfg()
    if rel_path.name == cfg.todo.inbox_file and len(rel_path.parts) == 1:
        source_type = "inbox"
    else:
        source_type = "note"

    # Delete existing todos and re-extract
    delete_todos_for_source(path)
    todos = extract_todos(
        path,
        source_type=source_type,
        external=False,
        alias=None,
        notes_root=notes_root,
        notebook=None,
    )
    # Batch insert for performance (single commit instead of one per todo)
    upsert_todos_batch(todos)


def get_note(path: Path, notes_root: Path | None = None) -> Note | None:
    """Parse a note file into a Note model.

    Args:
        path: Path to the note (absolute or relative to notes_root)
        notes_root: Override notes root directory

    Returns:
        Note model, or None if file doesn't exist.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    # Resolve path
    if not path.is_absolute():
        full_path = notes_root / path
        relative_path = path
    else:
        full_path = path
        try:
            relative_path = path.relative_to(notes_root)
        except ValueError:
            # Path is outside notes_root
            relative_path = path

    if not full_path.exists():
        return None

    # Parse the file
    content = full_path.read_text(encoding="utf-8")
    meta, body = parse_note_file(full_path)

    # Extract metadata
    title = extract_title(meta, body, full_path)
    note_date = extract_date(meta, full_path)
    tags = extract_tags(meta, body)
    links = [link_path for link_path, _ in extract_wiki_links(body)]
    notebook = get_notebook_for_path(relative_path)
    content_hash = make_note_hash(content)

    return Note(
        path=relative_path,
        title=title,
        date=note_date,
        tags=tags,
        links=links,
        attachments=[],  # TODO: extract attachments
        notebook=notebook,
        content_hash=content_hash,
    )


def get_notebook_for_path(path: Path) -> str:
    """Determine the notebook from a note's path.

    The notebook is the first directory component of the path.
    For example:
    - "daily/2025/11/2025-11-26.md" -> "daily"
    - "projects/myapp/notes.md" -> "projects"
    - "standalone.md" -> "" (no notebook)
    """
    parts = path.parts
    if len(parts) > 1:
        return parts[0]
    return ""


def list_notes(
    notebook: str | None = None, notes_root: Path | None = None
) -> list[Path]:
    """List all notes, optionally filtered by notebook.

    Args:
        notebook: Optional notebook name to filter by
        notes_root: Override notes root directory

    Returns:
        List of relative paths to notes.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if notebook:
        search_path = notes_root / notebook
    else:
        search_path = notes_root

    if not search_path.exists():
        return []

    # Find all markdown files
    notes = []
    for md_file in search_path.rglob("*.md"):
        # Skip hidden directories and .nb
        if any(part.startswith(".") for part in md_file.parts):
            continue
        try:
            relative = md_file.relative_to(notes_root)
            notes.append(relative)
        except ValueError:
            pass

    return sorted(notes)


def list_daily_notes(
    start: date | None = None,
    end: date | None = None,
    notes_root: Path | None = None,
) -> list[Path]:
    """List daily notes within a date range.

    Args:
        start: Start date (inclusive)
        end: End date (inclusive)
        notes_root: Override notes root directory

    Returns:
        List of relative paths to daily notes, sorted by date descending.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    daily_path = notes_root / "daily"
    if not daily_path.exists():
        return []

    from nb.utils.dates import parse_date_from_filename

    notes = []
    for md_file in daily_path.rglob("*.md"):
        note_date = parse_date_from_filename(md_file.name)
        if note_date is None:
            continue

        # Apply date filters
        if start and note_date < start:
            continue
        if end and note_date > end:
            continue

        try:
            relative = md_file.relative_to(notes_root)
            notes.append((note_date, relative))
        except ValueError:
            pass

    # Sort by date descending
    notes.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in notes]


def list_notebook_notes_by_date(
    notebook: str,
    start: date | None = None,
    end: date | None = None,
    notes_root: Path | None = None,
) -> list[Path]:
    """List notes from a notebook within a date range.

    Uses the note's date (from frontmatter or filename) to filter.

    Args:
        notebook: Notebook name to filter
        start: Start date (inclusive)
        end: End date (inclusive)
        notes_root: Override notes root directory

    Returns:
        List of paths to notes, sorted by date descending.

    """
    from nb.index.db import get_db

    if notes_root is None:
        notes_root = get_config().notes_root

    db = get_db()

    # Build query with optional date filters
    query = "SELECT path, date FROM notes WHERE notebook = ?"
    params: list[str] = [notebook]

    if start:
        query += " AND date >= ?"
        params.append(start.isoformat())
    if end:
        query += " AND date <= ?"
        params.append(end.isoformat())

    query += " ORDER BY date DESC"

    rows = db.fetchall(query, tuple(params))

    return [notes_root / row["path"] for row in rows if row["path"]]


def delete_note(path: Path, notes_root: Path | None = None) -> bool:
    """Delete a note from the filesystem and database.

    Deletes:
    - The note file from the filesystem
    - The note record from the database (cascades to note_tags, note_links, note_views)
    - All todos from this source file

    Does NOT:
    - Clean up empty parent directories
    - Delete external/linked notes (raises ValueError)

    Args:
        path: Absolute path to the note
        notes_root: Override notes root directory

    Returns:
        True if successfully deleted.

    Raises:
        FileNotFoundError: If the note doesn't exist.
        ValueError: If the note is an external/linked note.

    """
    from nb.index.db import get_db
    from nb.index.todos_repo import delete_todos_for_source
    from nb.utils.hashing import normalize_path

    if notes_root is None:
        notes_root = get_config().notes_root

    # Resolve path
    if not path.is_absolute():
        path = notes_root / path

    if not path.exists():
        raise FileNotFoundError(f"Note not found: {path}")

    # Check if this is an external/linked note (outside notes_root)
    try:
        relative_path = path.relative_to(notes_root)
    except ValueError:
        raise ValueError(
            f"Cannot delete linked notes. Use 'nb unlink' instead: {path}"
        ) from None

    # Also check if it's a linked note in the database
    db = get_db()
    note_row = db.fetchone(
        "SELECT external FROM notes WHERE path = ?",
        (normalize_path(relative_path),),
    )
    if note_row and note_row["external"]:
        raise ValueError("Cannot delete linked notes. Use 'nb unlink' instead.")

    # Delete todos from this source file
    delete_todos_for_source(path)

    # Delete from notes table (cascades to note_tags, note_links, note_views)
    db.execute(
        "DELETE FROM notes WHERE path = ?",
        (normalize_path(relative_path),),
    )
    db.commit()

    # Delete the file from filesystem
    path.unlink()

    return True
