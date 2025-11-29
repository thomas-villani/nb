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
