"""Linked external file management for nb.

Handles both linked todo files and linked note files/directories.
"""

from __future__ import annotations

from pathlib import Path

from nb.config import LinkedNoteConfig, LinkedTodoConfig
from nb.index.db import get_db

# =============================================================================
# Linked Todo Files
# =============================================================================


def list_linked_files() -> list[LinkedTodoConfig]:
    """Get all linked external todo files from the database."""
    db = get_db()
    rows = db.fetchall("SELECT alias, path, sync FROM linked_files")

    return [
        LinkedTodoConfig(
            path=Path(row["path"]),
            alias=row["alias"],
            sync=bool(row["sync"]),
        )
        for row in rows
    ]


def get_linked_file(alias: str) -> LinkedTodoConfig | None:
    """Get a linked file by alias.

    Args:
        alias: The alias of the linked file.

    Returns:
        The linked file config, or None if not found.

    """
    db = get_db()
    row = db.fetchone(
        "SELECT alias, path, sync FROM linked_files WHERE alias = ?",
        (alias,),
    )

    if row:
        return LinkedTodoConfig(
            path=Path(row["path"]),
            alias=row["alias"],
            sync=bool(row["sync"]),
        )

    return None


def add_linked_file(
    path: Path,
    alias: str | None = None,
    sync: bool = True,
) -> LinkedTodoConfig:
    """Add a new linked external todo file.

    Args:
        path: Path to the external todo file.
        alias: Short name for the file (defaults to filename stem).
        sync: Whether to sync completions back to the source file.

    Returns:
        The created LinkedTodoConfig.

    Raises:
        FileNotFoundError: If the path doesn't exist.
        ValueError: If the alias is already in use.

    """
    # Resolve and validate path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Generate alias if not provided
    if alias is None:
        alias = path.stem

    # Check for existing alias
    existing = get_linked_file(alias)
    if existing:
        raise ValueError(f"Alias '{alias}' is already in use for: {existing.path}")

    linked = LinkedTodoConfig(path=path, alias=alias, sync=sync)

    # Save to database
    db = get_db()
    db.execute(
        """
        INSERT OR REPLACE INTO linked_files (alias, path, sync)
        VALUES (?, ?, ?)
        """,
        (alias, str(path), int(sync)),
    )
    db.commit()

    return linked


def remove_linked_file(alias: str) -> bool:
    """Remove a linked external todo file.

    Args:
        alias: The alias of the file to remove.

    Returns:
        True if the file was removed, False if not found.

    """
    db = get_db()
    cursor = db.execute(
        "DELETE FROM linked_files WHERE alias = ?",
        (alias,),
    )
    db.commit()

    return cursor.rowcount > 0


def update_linked_file_sync(alias: str, sync: bool) -> bool:
    """Update the sync setting for a linked file.

    Args:
        alias: The alias of the file to update.
        sync: New sync setting.

    Returns:
        True if updated, False if not found.

    """
    db = get_db()
    cursor = db.execute(
        "UPDATE linked_files SET sync = ? WHERE alias = ?",
        (int(sync), alias),
    )
    db.commit()

    return cursor.rowcount > 0


def get_linked_file_by_path(path: Path) -> LinkedTodoConfig | None:
    """Get a linked file by its path.

    Args:
        path: The path of the linked file.

    Returns:
        The linked file config, or None if not found.

    """
    path = path.resolve()
    db = get_db()
    row = db.fetchone(
        "SELECT alias, path, sync FROM linked_files WHERE path = ?",
        (str(path),),
    )

    if row:
        return LinkedTodoConfig(
            path=Path(row["path"]),
            alias=row["alias"],
            sync=bool(row["sync"]),
        )

    return None


# =============================================================================
# Linked Note Files/Directories
# =============================================================================


def list_linked_notes() -> list[LinkedNoteConfig]:
    """Get all linked external note files/directories from the database."""
    db = get_db()
    rows = db.fetchall(
        "SELECT alias, path, notebook, recursive, todo_exclude, sync FROM linked_notes"
    )

    return [
        LinkedNoteConfig(
            path=Path(row["path"]),
            alias=row["alias"],
            notebook=row["notebook"],
            recursive=bool(row["recursive"]),
            todo_exclude=bool(row["todo_exclude"]) if row["todo_exclude"] else False,
            sync=bool(row["sync"]) if row["sync"] is not None else True,
        )
        for row in rows
    ]


def get_linked_note(alias: str, notebook: str | None = None) -> LinkedNoteConfig | None:
    """Get a linked note by alias.

    Args:
        alias: The alias of the linked note.
        notebook: Optional notebook to scope the lookup (if None, returns first match).

    Returns:
        The linked note config, or None if not found.

    """
    db = get_db()
    if notebook is not None:
        notebook_key = notebook or ""
        row = db.fetchone(
            "SELECT alias, path, notebook, recursive, todo_exclude, sync FROM linked_notes WHERE alias = ? AND notebook = ?",
            (alias, notebook_key),
        )
    else:
        row = db.fetchone(
            "SELECT alias, path, notebook, recursive, todo_exclude, sync FROM linked_notes WHERE alias = ?",
            (alias,),
        )

    if row:
        return LinkedNoteConfig(
            path=Path(row["path"]),
            alias=row["alias"],
            notebook=row["notebook"],
            recursive=bool(row["recursive"]),
            todo_exclude=bool(row["todo_exclude"]) if row["todo_exclude"] else False,
            sync=bool(row["sync"]) if row["sync"] is not None else True,
        )

    return None


def get_linked_notes_by_alias(alias: str) -> list[LinkedNoteConfig]:
    """Get all linked notes with a given alias (across all notebooks).

    Args:
        alias: The alias name to look up.

    Returns:
        List of LinkedNoteConfig for all matching aliases.
    """
    db = get_db()
    rows = db.fetchall(
        "SELECT alias, path, notebook, recursive, todo_exclude, sync FROM linked_notes WHERE alias = ?",
        (alias,),
    )

    return [
        LinkedNoteConfig(
            path=Path(row["path"]),
            alias=row["alias"],
            notebook=row["notebook"],
            recursive=bool(row["recursive"]),
            todo_exclude=bool(row["todo_exclude"]) if row["todo_exclude"] else False,
            sync=bool(row["sync"]) if row["sync"] is not None else True,
        )
        for row in rows
    ]


def add_linked_note(
    path: Path,
    alias: str | None = None,
    notebook: str | None = None,
    recursive: bool = True,
    todo_exclude: bool = False,
    sync: bool = True,
) -> LinkedNoteConfig:
    """Add a new linked external note file or directory.

    Args:
        path: Path to the external note file or directory.
        alias: Short name for the link (defaults to filename/dirname).
        notebook: Virtual notebook name (defaults to @alias). Aliases are unique per-notebook.
        recursive: For directories, whether to scan recursively.
        todo_exclude: Exclude todos from nb todo by default.
        sync: Sync todo completions back to source file.

    Returns:
        The created LinkedNoteConfig.

    Raises:
        FileNotFoundError: If the path doesn't exist.
        ValueError: If the alias is already in use in this notebook.

    """
    # Resolve and validate path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    # Generate alias if not provided
    if alias is None:
        alias = path.stem if path.is_file() else path.name

    # Default notebook to alias with @ prefix
    if notebook is None:
        notebook = f"@{alias}"

    # Check for existing alias in this notebook (use empty string for NULL)
    notebook_key = notebook or ""
    existing = get_linked_note(alias, notebook=notebook_key)
    if existing:
        raise ValueError(
            f"Alias '{alias}' is already in use in notebook '{notebook_key}' for: {existing.path}"
        )

    linked = LinkedNoteConfig(
        path=path,
        alias=alias,
        notebook=notebook,
        recursive=recursive,
        todo_exclude=todo_exclude,
        sync=sync,
    )

    # Save to database
    db = get_db()
    db.execute(
        """
        INSERT OR REPLACE INTO linked_notes (alias, path, notebook, recursive, todo_exclude, sync)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (alias, str(path), notebook, int(recursive), int(todo_exclude), int(sync)),
    )
    db.commit()

    return linked


def remove_linked_note(alias: str, notebook: str | None = None) -> bool:
    """Remove a linked external note file/directory.

    Args:
        alias: The alias of the link to remove.
        notebook: Optional notebook to scope the removal (if None, removes all with this alias).

    Returns:
        True if the link was removed, False if not found.

    """
    db = get_db()
    if notebook is not None:
        notebook_key = notebook or ""
        cursor = db.execute(
            "DELETE FROM linked_notes WHERE alias = ? AND notebook = ?",
            (alias, notebook_key),
        )
    else:
        cursor = db.execute(
            "DELETE FROM linked_notes WHERE alias = ?",
            (alias,),
        )
    db.commit()

    return cursor.rowcount > 0


def update_linked_note_sync(
    alias: str, sync: bool, notebook: str | None = None
) -> bool:
    """Update the sync setting for a linked note.

    Args:
        alias: The alias of the link to update.
        sync: New sync setting.
        notebook: Notebook to scope the update (if None, updates all with this alias).

    Returns:
        True if updated, False if not found.

    """
    db = get_db()
    if notebook is not None:
        notebook_key = notebook or ""
        cursor = db.execute(
            "UPDATE linked_notes SET sync = ? WHERE alias = ? AND notebook = ?",
            (int(sync), alias, notebook_key),
        )
    else:
        cursor = db.execute(
            "UPDATE linked_notes SET sync = ? WHERE alias = ?",
            (int(sync), alias),
        )
    db.commit()

    return cursor.rowcount > 0


def update_linked_note_todo_exclude(
    alias: str, todo_exclude: bool, notebook: str | None = None
) -> bool:
    """Update the todo_exclude setting for a linked note.

    Args:
        alias: The alias of the link to update.
        todo_exclude: New todo_exclude setting.
        notebook: Notebook to scope the update (if None, updates all with this alias).

    Returns:
        True if updated, False if not found.

    """
    db = get_db()
    if notebook is not None:
        notebook_key = notebook or ""
        cursor = db.execute(
            "UPDATE linked_notes SET todo_exclude = ? WHERE alias = ? AND notebook = ?",
            (int(todo_exclude), alias, notebook_key),
        )
    else:
        cursor = db.execute(
            "UPDATE linked_notes SET todo_exclude = ? WHERE alias = ?",
            (int(todo_exclude), alias),
        )
    db.commit()

    return cursor.rowcount > 0


def get_linked_note_by_path(path: Path) -> LinkedNoteConfig | None:
    """Get a linked note by its path.

    Args:
        path: The path of the linked note.

    Returns:
        The linked note config, or None if not found.

    """
    path = path.resolve()
    db = get_db()
    row = db.fetchone(
        "SELECT alias, path, notebook, recursive, todo_exclude, sync FROM linked_notes WHERE path = ?",
        (str(path),),
    )

    if row:
        return LinkedNoteConfig(
            path=Path(row["path"]),
            alias=row["alias"],
            notebook=row["notebook"],
            recursive=bool(row["recursive"]),
            todo_exclude=bool(row["todo_exclude"]) if row["todo_exclude"] else False,
            sync=bool(row["sync"]) if row["sync"] is not None else True,
        )

    return None


def get_linked_note_by_notebook(notebook: str) -> LinkedNoteConfig | None:
    """Get a linked note by its notebook name.

    Args:
        notebook: The notebook name of the linked note.

    Returns:
        The linked note config, or None if not found.

    """
    for ln in list_linked_notes():
        ln_notebook = ln.notebook or f"@{ln.alias}"
        if ln_notebook == notebook:
            return ln
    return None


def find_linked_note_for_path(file_path: Path) -> LinkedNoteConfig | None:
    """Find the linked note config that contains the given file path.

    This checks if the file is a linked note itself (single file link) or
    is within a linked note directory.

    Args:
        file_path: Path to the file to check.

    Returns:
        The LinkedNoteConfig if found, or None if the file is not a linked note.

    """
    file_path = file_path.resolve()

    for ln in list_linked_notes():
        ln_path = ln.path.resolve()

        if ln_path.is_file():
            # Single file link - check exact match
            if file_path == ln_path:
                return ln
        else:
            # Directory link - check if file is within the directory
            try:
                file_path.relative_to(ln_path)
                return ln
            except ValueError:
                # Not within this directory
                continue

    return None


def get_linked_note_in_notebook(notebook: str, alias: str) -> LinkedNoteConfig | None:
    """Get a linked note by notebook and alias.

    Args:
        notebook: The notebook name of the linked note.
        alias: The alias of the linked note.

    Returns:
        The linked note config, or None if not found.

    """
    for ln in list_linked_notes():
        ln_notebook = ln.notebook or f"@{ln.alias}"
        if ln_notebook == notebook and ln.alias == alias:
            return ln
    return None


def scan_linked_note_files(linked: LinkedNoteConfig) -> list[Path]:
    """Get all markdown files from a linked note path.

    Args:
        linked: The linked note configuration.

    Returns:
        List of markdown file paths.

    """
    if not linked.path.exists():
        return []

    if linked.path.is_file():
        # Single file
        if linked.path.suffix.lower() == ".md":
            return [linked.path]
        return []

    # Directory - scan for markdown files
    if linked.recursive:
        files = list(linked.path.rglob("*.md"))
    else:
        files = list(linked.path.glob("*.md"))

    # Exclude hidden files and directories
    files = [
        f
        for f in files
        if not any(part.startswith(".") for part in f.relative_to(linked.path).parts)
    ]

    return sorted(files)
