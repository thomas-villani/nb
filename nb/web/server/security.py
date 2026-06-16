"""Path-safety helpers for the web viewer.

Moved verbatim from the old ``nb.webserver`` so the traversal protection and the
linked/external read-only guarantees are preserved exactly.
"""

from __future__ import annotations

from pathlib import Path


def _is_allowed_external_path(path: Path) -> bool:
    """Check if an absolute path belongs to a configured linked note or file.

    This prevents arbitrary file read by ensuring absolute paths are only
    allowed if they're part of a linked notes directory or linked todo file.

    Args:
        path: The absolute path to validate.

    Returns:
        True if the path belongs to a linked note/file, False otherwise.
    """
    from nb.core.links import list_linked_files, list_linked_notes

    resolved = path.resolve()

    # Check linked notes (files and directories)
    for linked_note in list_linked_notes():
        if not linked_note.path.exists():
            continue
        linked_resolved = linked_note.path.resolve()
        if linked_note.path.is_file():
            # Single file - must match exactly
            if resolved == linked_resolved:
                return True
        else:
            # Directory - check if path is inside it
            try:
                resolved.relative_to(linked_resolved)
                return True
            except ValueError:
                continue

    # Check linked todo files
    for linked_file in list_linked_files():
        if not linked_file.path.exists():
            continue
        if resolved == linked_file.path.resolve():
            return True

    return False


def _safe_note_path(notes_root: Path, rel: str) -> Path | None:
    """Validate and resolve a note path, ensuring it's an allowed location.

    For internal notes (relative paths), ensures the resolved path doesn't
    escape notes_root via path traversal (e.g., "../../etc/passwd").

    For linked/external notes (absolute paths), validates that the path
    belongs to a configured linked note or file to prevent arbitrary file read.

    Args:
        notes_root: The notes root directory.
        rel: The relative or absolute path string from the request.

    Returns:
        Resolved Path if valid, None if path traversal detected or
        absolute path is not an allowed linked location.
    """
    path = Path(rel)

    # Absolute paths must belong to a configured linked note/file
    if path.is_absolute():
        if _is_allowed_external_path(path):
            return path
        return None  # Reject absolute paths not in linked locations

    # For relative paths, resolve and check containment
    resolved = (notes_root / rel).resolve()
    try:
        resolved.relative_to(notes_root.resolve())
    except ValueError:
        # Path escapes notes_root - path traversal attempt
        return None
    return resolved
