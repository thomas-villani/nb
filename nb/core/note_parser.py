"""Pure note parsing functions - no database dependencies.

This module extracts the parsing logic from notes.py to break the circular
dependency between nb.core.notes and nb.index.scanner.

Functions in this module:
- get_note(): Parse a note file into a Note model
- get_notebook_for_path(): Determine the notebook from a note's path
- get_sections_for_path(): Extract subdirectory sections from a note's path

These are pure parsing functions with no database or index layer dependencies.
"""

from __future__ import annotations

from pathlib import Path

from nb.config import get_config
from nb.models import Note
from nb.utils.hashing import make_note_hash
from nb.utils.markdown import (
    extract_date,
    extract_tags,
    extract_title,
    extract_wiki_links,
    parse_note_file,
)


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
        attachments=[],  # Lazy-loaded via get_attachments_for_parent() when needed
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


def get_sections_for_path(path: Path) -> list[str]:
    """Extract subdirectory sections from a note's path.

    Returns all intermediate directory names between the notebook
    and the filename. These represent the hierarchical "sections"
    within a notebook.

    Examples:
        - "projects/myapp/docs/api.md" -> ["myapp", "docs"]
        - "daily/2025/Nov25-Dec01/2025-11-27.md" -> ["2025", "Nov25-Dec01"]
        - "projects/readme.md" -> []
        - "standalone.md" -> []
    """
    parts = path.parts
    if len(parts) <= 2:
        return []  # No subdirectories (just notebook/filename or just filename)
    # Skip first (notebook) and last (filename)
    return list(parts[1:-1])
