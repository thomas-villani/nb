"""Shared utilities for CLI commands."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from nb.config import get_config, init_config

console = Console(highlight=False)


def print_note(path: Path) -> None:
    """Print a note's content to console with markdown formatting."""
    from rich.markdown import Markdown

    if not path.exists():
        console.print(f"[red]Note not found: {path}[/red]")
        raise SystemExit(1)

    content = path.read_text(encoding="utf-8")

    # Print header with path info
    console.print(f"[dim]─── {path.name} ───[/dim]\n")

    # Render markdown
    md = Markdown(content)
    console.print(md)
    console.print()


def ensure_setup() -> None:
    """Ensure nb is set up (creates config and directories on first run)."""
    config = get_config()
    if not config.nb_dir.exists():
        init_config(config.notes_root)


def find_todo(todo_id: str):
    """Find a todo by ID or ID prefix."""
    from nb.index.db import get_db
    from nb.index.todos_repo import get_todo_by_id

    # First try exact match
    t = get_todo_by_id(todo_id)
    if t:
        return t

    # Try prefix match
    db = get_db()
    rows = db.fetchall(
        "SELECT id FROM todos WHERE id LIKE ?",
        (f"{todo_id}%",),
    )

    if len(rows) == 1:
        return get_todo_by_id(rows[0]["id"])
    elif len(rows) > 1:
        console.print(
            f"[yellow]Multiple todos match '{todo_id}'. Be more specific.[/yellow]"
        )
        for row in rows[:5]:
            t = get_todo_by_id(row["id"])
            if t:
                console.print(f"  {row['id'][:6]}: {t.content[:50]}")
        return None

    return None


def get_notebook_display_info(notebook_name: str) -> tuple[str, str | None]:
    """Get display color and icon for a notebook.

    Args:
        notebook_name: Name of the notebook

    Returns:
        Tuple of (color, icon). Color defaults to "magenta", icon may be None.
    """
    config = get_config()
    nb_config = config.get_notebook(notebook_name)
    if nb_config:
        color = nb_config.color or "magenta"
        icon = nb_config.icon
    else:
        color = "magenta"
        icon = None
    return color, icon


def resolve_notebook(name: str, interactive: bool = True) -> str | None:
    """Resolve a notebook name, with fuzzy matching if no exact match.

    Args:
        name: The notebook name to resolve.
        interactive: If True, prompt user to select from fuzzy matches.

    Returns:
        Resolved notebook name, or None if not found/cancelled.

    """
    from nb.utils.fuzzy import resolve_with_fuzzy

    config = get_config()

    # Get all notebook names
    notebook_names = [nb.name for nb in config.notebooks]

    return resolve_with_fuzzy(
        name,
        notebook_names,
        item_type="notebook",
        interactive=interactive,
    )


def resolve_note_for_todo_filter(
    note_ref: str,
    notebook: str | None = None,
) -> str | None:
    """Resolve a note reference for todo filtering.

    This handles:
    - Linked note aliases (e.g., "nbtodo" resolves to the linked file path)
    - Linked todo aliases (e.g., "mytodos" for linked todo files)
    - Regular notes (e.g., "notebook/note-name" or just "note-name")

    Args:
        note_ref: The note reference (name, path, or linked alias).
        notebook: Optional notebook to narrow search.

    Returns:
        A path string suitable for use in query_todos notes filter,
        or None if not found.

    """
    from nb.core.links import (
        get_linked_file,
        get_linked_note,
        get_linked_note_in_notebook,
    )
    from nb.utils.hashing import normalize_path

    config = get_config()

    # Strip @ prefix if present
    check_ref = note_ref[1:] if note_ref.startswith("@") else note_ref

    # If notebook specified, check for linked note in that notebook first
    if notebook:
        linked = get_linked_note_in_notebook(notebook, check_ref)
        if linked:
            return normalize_path(linked.path)

    # Check if it matches a linked note alias (from config or DB)
    linked_note = get_linked_note(check_ref)
    if linked_note:
        return normalize_path(linked_note.path)

    # Also check linked todo files (from config or DB)
    linked_file = get_linked_file(check_ref)
    if linked_file:
        return normalize_path(linked_file.path)

    # Try to resolve as a regular note (only if no @ prefix)
    if not note_ref.startswith("@"):
        resolved_path = resolve_note(note_ref, notebook=notebook, interactive=True)
        if resolved_path:
            # Return the path relative to notes_root for LIKE matching
            try:
                rel_path = resolved_path.relative_to(config.notes_root)
                return normalize_path(rel_path)
            except ValueError:
                # External path, return full normalized path
                return normalize_path(resolved_path)

    return None


def resolve_note(
    note_ref: str,
    notebook: str | None = None,
    interactive: bool = True,
) -> Path | None:
    """Resolve a note reference, with fuzzy matching if no exact match.

    Args:
        note_ref: The note reference (name or path) to resolve.
        notebook: Optional notebook to search within.
        interactive: If True, prompt user to select from fuzzy matches.

    Returns:
        Resolved note Path, or None if not found/cancelled.

    """
    from nb.core.notebooks import get_notebook_notes_with_linked
    from nb.core.notes import list_notes
    from nb.utils.fuzzy import resolve_with_fuzzy

    config = get_config()

    # Get candidate notes
    # get_notebook_notes_with_linked returns tuples (path, is_linked, alias)
    # list_notes returns just paths
    note_paths: list[Path] = []
    if notebook:
        notes_with_linked = get_notebook_notes_with_linked(notebook)
        note_paths = [path for path, _, _ in notes_with_linked]
    else:
        note_paths = list_notes(notes_root=config.notes_root)

    if not note_paths:
        return None

    # Build a mapping from display names to paths
    # Use stem (filename without extension) as the display name
    name_to_path: dict[str, Path] = {}
    for note_path in note_paths:
        # Use the stem as the primary lookup key
        stem = note_path.stem
        if stem not in name_to_path:
            name_to_path[stem] = note_path

        # Also add notebook/stem for disambiguation
        try:
            rel = note_path.relative_to(config.notes_root)
            if len(rel.parts) > 1:
                full_ref = f"{rel.parts[0]}/{stem}"
                if full_ref not in name_to_path:
                    name_to_path[full_ref] = note_path
        except ValueError:
            pass

    # Try exact match first (case-insensitive)
    note_ref_lower = note_ref.lower()
    for name, path in name_to_path.items():
        if name.lower() == note_ref_lower:
            return path

    # Try fuzzy matching
    resolved_name = resolve_with_fuzzy(
        note_ref,
        list(name_to_path.keys()),
        item_type="note",
        interactive=interactive,
    )

    if resolved_name:
        return name_to_path.get(resolved_name)

    return None
