"""Hashing utilities for content identification."""

from __future__ import annotations

import hashlib
from pathlib import Path


def normalize_path(path: Path | str) -> str:
    """Normalize a path to a consistent string format.

    Uses forward slashes for cross-platform consistency.
    This ensures paths are stored/compared identically on Windows and Unix.
    """
    if isinstance(path, Path):
        return path.as_posix()
    return str(path).replace("\\", "/")


def hash_content(content: str, length: int = 8) -> str:
    """Generate a SHA256 hash of content, truncated to specified length.

    Args:
        content: The content to hash.
        length: Number of hex characters to return (default 8).

    This provides a reasonably unique identifier while remaining
    short enough to be human-readable in IDs.

    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:length]


def make_todo_id(source_path: Path, content: str) -> str:
    """Generate a stable ID for a todo item.

    The ID is based on:
    - Source file path (normalized)
    - Todo content (cleaned)

    This means the ID will change if the todo is:
    - Moved to a different file
    - Has its content edited

    Line number is NOT included so that reordering todos
    (e.g., adding a new todo above) doesn't change existing IDs.
    """
    # Normalize path for consistent IDs across platforms
    normalized = normalize_path(source_path)
    combined = f"{normalized}:{content}"
    return hash_content(combined)


def make_note_hash(content: str) -> str:
    """Generate a content hash for a note file.

    Used for change detection during indexing.
    """
    return hash_content(content)


def make_note_id(path: Path) -> str:
    """Generate a stable ID for a note based on its path.

    Unlike todo IDs which include content, note IDs are based only
    on the normalized path. This means the ID remains stable across
    content edits but will change if the file is moved/renamed.

    This is intentional: notes are identified by their location,
    while todos are identified by their content within a file.
    """
    normalized = normalize_path(path)
    return hash_content(normalized)


def make_attachment_id(path: str, parent_type: str, parent_id: str) -> str:
    """Generate a stable ID for an attachment.

    Args:
        path: Path or URL of the attachment
        parent_type: "note" or "todo"
        parent_id: ID of the parent note or todo

    """
    combined = f"{parent_type}:{parent_id}:{path}"
    return hash_content(combined)
