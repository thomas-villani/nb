"""Linked external file management for nb.

Handles both linked todo files and linked note files/directories.
"""

from __future__ import annotations

from pathlib import Path

from nb.config import LinkedNoteConfig, LinkedTodoConfig, get_config, save_config
from nb.index.db import get_db

# =============================================================================
# Linked Todo Files
# =============================================================================


def list_linked_files() -> list[LinkedTodoConfig]:
    """Get all linked external todo files.

    Returns both configured (from config file) and database-stored linked files.
    """
    config = get_config()

    # Start with config file entries
    linked = list(config.linked_todos)

    # Also check database for dynamically added links
    db = get_db()
    rows = db.fetchall("SELECT alias, path, sync FROM linked_files")

    # Add DB entries that aren't in config
    config_aliases = {lt.alias for lt in linked}
    for row in rows:
        if row["alias"] not in config_aliases:
            linked.append(
                LinkedTodoConfig(
                    path=Path(row["path"]),
                    alias=row["alias"],
                    sync=bool(row["sync"]),
                )
            )

    return linked


def get_linked_file(alias: str) -> LinkedTodoConfig | None:
    """Get a linked file by alias.

    Args:
        alias: The alias of the linked file.

    Returns:
        The linked file config, or None if not found.

    """
    config = get_config()

    # Check config first
    for lt in config.linked_todos:
        if lt.alias == alias:
            return lt

    # Check database
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
    save_to_config: bool = False,
) -> LinkedTodoConfig:
    """Add a new linked external todo file.

    Args:
        path: Path to the external todo file.
        alias: Short name for the file (defaults to filename stem).
        sync: Whether to sync completions back to the source file.
        save_to_config: If True, save to config file. Otherwise, save to DB.

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

    if save_to_config:
        # Save to config file
        config = get_config()
        config.linked_todos.append(linked)
        save_config(config)
    else:
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
    config = get_config()

    # Check if in config
    for i, lt in enumerate(config.linked_todos):
        if lt.alias == alias:
            config.linked_todos.pop(i)
            save_config(config)
            return True

    # Check database
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
    config = get_config()

    # Check config first
    for lt in config.linked_todos:
        if lt.alias == alias:
            lt.sync = sync
            save_config(config)
            return True

    # Check database
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
    config = get_config()

    # Check config first
    for lt in config.linked_todos:
        if lt.path.resolve() == path:
            return lt

    # Check database
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
    """Get all linked external note files/directories.

    Returns both configured (from config file) and database-stored linked notes.
    """
    config = get_config()

    # Start with config file entries
    linked = list(config.linked_notes)

    # Also check database for dynamically added links
    db = get_db()
    rows = db.fetchall(
        "SELECT alias, path, notebook, recursive, todo_exclude, sync FROM linked_notes"
    )

    # Add DB entries that aren't in config
    config_aliases = {ln.alias for ln in linked}
    for row in rows:
        if row["alias"] not in config_aliases:
            linked.append(
                LinkedNoteConfig(
                    path=Path(row["path"]),
                    alias=row["alias"],
                    notebook=row["notebook"],
                    recursive=bool(row["recursive"]),
                    todo_exclude=(
                        bool(row["todo_exclude"]) if row["todo_exclude"] else False
                    ),
                    sync=bool(row["sync"]) if row["sync"] is not None else True,
                )
            )

    return linked


def get_linked_note(alias: str) -> LinkedNoteConfig | None:
    """Get a linked note by alias.

    Args:
        alias: The alias of the linked note.

    Returns:
        The linked note config, or None if not found.

    """
    config = get_config()

    # Check config first
    for ln in config.linked_notes:
        if ln.alias == alias:
            return ln

    # Check database
    db = get_db()
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


def add_linked_note(
    path: Path,
    alias: str | None = None,
    notebook: str | None = None,
    recursive: bool = True,
    todo_exclude: bool = False,
    sync: bool = True,
    save_to_config: bool = False,
) -> LinkedNoteConfig:
    """Add a new linked external note file or directory.

    Args:
        path: Path to the external note file or directory.
        alias: Short name for the link (defaults to filename/dirname).
        notebook: Virtual notebook name (defaults to alias).
        recursive: For directories, whether to scan recursively.
        todo_exclude: Exclude todos from nb todo by default.
        sync: Sync todo completions back to source file.
        save_to_config: If True, save to config file. Otherwise, save to DB.

    Returns:
        The created LinkedNoteConfig.

    Raises:
        FileNotFoundError: If the path doesn't exist.
        ValueError: If the alias is already in use.

    """
    # Resolve and validate path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    # Generate alias if not provided
    if alias is None:
        alias = path.stem if path.is_file() else path.name

    # Check for existing alias
    existing = get_linked_note(alias)
    if existing:
        raise ValueError(f"Alias '{alias}' is already in use for: {existing.path}")

    # Default notebook to alias with @ prefix
    if notebook is None:
        notebook = f"@{alias}"

    linked = LinkedNoteConfig(
        path=path,
        alias=alias,
        notebook=notebook,
        recursive=recursive,
        todo_exclude=todo_exclude,
        sync=sync,
    )

    if save_to_config:
        # Save to config file
        config = get_config()
        config.linked_notes.append(linked)
        save_config(config)
    else:
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


def remove_linked_note(alias: str) -> bool:
    """Remove a linked external note file/directory.

    Args:
        alias: The alias of the link to remove.

    Returns:
        True if the link was removed, False if not found.

    """
    config = get_config()

    # Check if in config
    for i, ln in enumerate(config.linked_notes):
        if ln.alias == alias:
            config.linked_notes.pop(i)
            save_config(config)
            return True

    # Check database
    db = get_db()
    cursor = db.execute(
        "DELETE FROM linked_notes WHERE alias = ?",
        (alias,),
    )
    db.commit()

    return cursor.rowcount > 0


def update_linked_note_sync(alias: str, sync: bool) -> bool:
    """Update the sync setting for a linked note.

    Args:
        alias: The alias of the link to update.
        sync: New sync setting.

    Returns:
        True if updated, False if not found.

    """
    config = get_config()

    # Check config first
    for ln in config.linked_notes:
        if ln.alias == alias:
            ln.sync = sync
            save_config(config)
            return True

    # Check database
    db = get_db()
    cursor = db.execute(
        "UPDATE linked_notes SET sync = ? WHERE alias = ?",
        (int(sync), alias),
    )
    db.commit()

    return cursor.rowcount > 0


def update_linked_note_todo_exclude(alias: str, todo_exclude: bool) -> bool:
    """Update the todo_exclude setting for a linked note.

    Args:
        alias: The alias of the link to update.
        todo_exclude: New todo_exclude setting.

    Returns:
        True if updated, False if not found.

    """
    config = get_config()

    # Check config first
    for ln in config.linked_notes:
        if ln.alias == alias:
            ln.todo_exclude = todo_exclude
            save_config(config)
            return True

    # Check database
    db = get_db()
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
    config = get_config()

    # Check config first
    for ln in config.linked_notes:
        if ln.path.resolve() == path:
            return ln

    # Check database
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
