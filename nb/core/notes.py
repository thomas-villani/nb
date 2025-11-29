"""Note operations for nb."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from nb.config import get_config
from nb.models import Note
from nb.utils.editor import open_in_editor
from nb.utils.hashing import make_note_hash
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
    notes_root: Path | None = None,
) -> Path:
    """Create a new note at the specified path.

    Args:
        path: Relative path within notes_root (e.g., "projects/myproject/ideas.md")
        title: Optional title for the note
        dt: Date for the note (defaults to today)
        tags: Optional list of tags
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

    # Generate content
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
        (mtime, str(relative_path)),
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

    # Update mtime in database if file was modified
    try:
        mtime_after = path.stat().st_mtime
        if mtime_before is None or mtime_after != mtime_before:
            update_note_mtime(path, config.notes_root)
    except OSError:
        pass


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
