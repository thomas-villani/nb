"""Hashing utilities for content identification."""

from __future__ import annotations

import hashlib
from pathlib import Path


def hash_content(content: str, length: int = 8) -> str:
    """Generate a SHA256 hash of content, truncated to specified length.

    Args:
        content: The content to hash.
        length: Number of hex characters to return (default 8).

    This provides a reasonably unique identifier while remaining
    short enough to be human-readable in IDs.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:length]


def make_todo_id(source_path: Path, content: str, line_number: int) -> str:
    """Generate a stable ID for a todo item.

    The ID is based on:
    - Source file path
    - Todo content (cleaned)
    - Line number

    This means the ID will change if the todo is:
    - Moved to a different file
    - Has its content edited
    - Moved to a different line

    This is intentional - when a todo changes significantly,
    it should be treated as a new todo.
    """
    combined = f"{source_path}:{line_number}:{content}"
    return hash_content(combined)


def make_note_hash(content: str) -> str:
    """Generate a content hash for a note file.

    Used for change detection during indexing.
    """
    return hash_content(content)


def make_attachment_id(path: str, parent_type: str, parent_id: str) -> str:
    """Generate a stable ID for an attachment.

    Args:
        path: Path or URL of the attachment
        parent_type: "note" or "todo"
        parent_id: ID of the parent note or todo
    """
    combined = f"{parent_type}:{parent_id}:{path}"
    return hash_content(combined)
