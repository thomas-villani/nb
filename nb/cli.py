"""CLI entry point for nb."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from nb import __version__
from nb.config import get_config, init_config
from nb.core.notebooks import get_notebook_notes, list_notebooks
from nb.core.notes import (
    create_note,
    ensure_daily_note,
    list_daily_notes,
    open_note,
)
from nb.core.todos import add_todo_to_inbox, toggle_todo_in_file
from nb.index.scanner import index_all_notes
from nb.index.todos_repo import (
    get_sorted_todos,
    get_todo_by_id,
    get_todo_children,
    get_todo_stats,
    query_todos,
    update_todo_completion,
)
from nb.utils.dates import get_week_range, parse_fuzzy_date
from nb.utils.editor import open_in_editor

console = Console()


def ensure_setup() -> None:
    """Ensure nb is set up (creates config and directories on first run)."""
    config = get_config()
    if not config.nb_dir.exists():
        init_config(config.notes_root)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="nb")
@click.pass_context
def main(ctx: click.Context) -> None:
    """A plaintext-first note-taking and todo management CLI.

    Run 'nb' without arguments to open today's daily note.
    """
    ensure_setup()
    if ctx.invoked_subcommand is None:
        # Default action: open today's note
        ctx.invoke(today)


@main.command()
def today() -> None:
    """Open today's daily note."""
    dt = date.today()
    path = ensure_daily_note(dt)
    console.print(f"[dim]Opening {path.name}...[/dim]")
    open_note(path)


@main.command()
def yesterday() -> None:
    """Open yesterday's daily note."""
    dt = date.today() - timedelta(days=1)
    path = ensure_daily_note(dt)
    console.print(f"[dim]Opening {path.name}...[/dim]")
    open_note(path)


@main.command("t")
@click.pass_context
def today_alias(ctx: click.Context) -> None:
    """Alias for 'today'."""
    ctx.invoke(today)


@main.command("y")
@click.pass_context
def yesterday_alias(ctx: click.Context) -> None:
    """Alias for 'yesterday'."""
    ctx.invoke(yesterday)


@main.command("open")
@click.argument("date_str")
def open_date(date_str: str) -> None:
    """Open a note for a specific date.

    DATE_STR can be:
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A path to a note file
    """
    config = get_config()

    # First check if it's a path to an existing note
    path = Path(date_str)
    if not path.suffix:
        path = path.with_suffix(".md")

    full_path = config.notes_root / path
    if full_path.exists():
        console.print(f"[dim]Opening {path}...[/dim]")
        open_note(full_path)
        return

    # Try to parse as a date
    parsed = parse_fuzzy_date(date_str)
    if parsed:
        note_path = ensure_daily_note(parsed)
        console.print(f"[dim]Opening {note_path.name}...[/dim]")
        open_note(note_path)
        return

    console.print(f"[red]Could not parse date: {date_str}[/red]")
    raise SystemExit(1)


@main.command("o")
@click.argument("date_str")
@click.pass_context
def open_alias(ctx: click.Context, date_str: str) -> None:
    """Alias for 'open'."""
    ctx.invoke(open_date, date_str=date_str)


@main.command("new")
@click.argument("path")
@click.option("--title", "-t", help="Title for the note")
def new_note(path: str, title: str | None) -> None:
    """Create a new note.

    PATH is the location for the note (e.g., "projects/myproject/ideas").
    The .md extension is added automatically if not present.
    """
    try:
        note_path = Path(path)
        full_path = create_note(note_path, title=title)
        console.print(f"[green]Created:[/green] {note_path}")
        open_note(full_path)
    except FileExistsError:
        console.print(f"[red]Note already exists:[/red] {path}")
        raise SystemExit(1)


@main.command("edit")
@click.argument("path")
def edit_note(path: str) -> None:
    """Open an existing note in the editor.

    PATH is relative to the notes root.
    """
    config = get_config()
    note_path = Path(path)

    if not note_path.suffix:
        note_path = note_path.with_suffix(".md")

    full_path = config.notes_root / note_path

    if not full_path.exists():
        console.print(f"[red]Note not found:[/red] {note_path}")
        raise SystemExit(1)

    open_note(full_path)


@main.command("notebooks")
@click.option("--verbose", "-v", is_flag=True, help="Show note counts")
def notebooks_cmd(verbose: bool) -> None:
    """List all notebooks."""
    nbs = list_notebooks()

    if not nbs:
        console.print("[dim]No notebooks found.[/dim]")
        return

    if verbose:
        table = Table(show_header=True)
        table.add_column("Notebook")
        table.add_column("Notes", justify="right")

        for nb in nbs:
            notes = get_notebook_notes(nb)
            table.add_row(nb, str(len(notes)))

        console.print(table)
    else:
        for nb in nbs:
            console.print(nb)


@main.command("nbs")
@click.pass_context
def notebooks_alias(ctx: click.Context) -> None:
    """Alias for 'notebooks'."""
    ctx.invoke(notebooks_cmd)


@main.command("config")
def config_cmd() -> None:
    """Open the configuration file in the editor."""
    config = get_config()

    # Ensure config exists
    if not config.config_path.exists():
        init_config(config.notes_root)

    console.print(f"[dim]Opening {config.config_path}...[/dim]")
    open_in_editor(config.config_path, editor=config.editor)


@main.command("add")
@click.argument("text")
def add_to_today(text: str) -> None:
    """Append a line to today's note."""
    dt = date.today()
    path = ensure_daily_note(dt)

    # Append the text
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{text}\n")

    console.print(f"[green]Added to {path.name}[/green]")


@main.command("list")
@click.option("--notebook", "-n", help="Filter by notebook")
@click.option("--week", is_flag=True, help="Show this week's daily notes")
@click.option("--month", is_flag=True, help="Show this month's daily notes")
def list_notes_cmd(notebook: str | None, week: bool, month: bool) -> None:
    """List notes."""
    if week or month:
        # List daily notes
        from nb.utils.dates import get_month_range, get_week_range

        if week:
            start, end = get_week_range()
        else:
            start, end = get_month_range()

        notes = list_daily_notes(start=start, end=end)

        if not notes:
            console.print("[dim]No daily notes found.[/dim]")
            return

        for note_path in notes:
            console.print(str(note_path))
    elif notebook:
        notes = get_notebook_notes(notebook)

        if not notes:
            console.print(f"[dim]No notes in {notebook}.[/dim]")
            return

        for note_path in notes:
            console.print(str(note_path))
    else:
        # List all notebooks with counts
        nbs = list_notebooks()
        for nb in nbs:
            notes = get_notebook_notes(nb)
            console.print(f"{nb}: {len(notes)} notes")


# =============================================================================
# Todo Commands
# =============================================================================


@main.group(invoke_without_command=True)
@click.option("--today", "filter_today", is_flag=True, help="Show todos created today")
@click.option(
    "--week", "filter_week", is_flag=True, help="Show todos created this week"
)
@click.option("--overdue", is_flag=True, help="Show only overdue todos")
@click.option("--priority", "-p", type=int, help="Filter by priority (1, 2, or 3)")
@click.option("--tag", "-t", help="Filter by tag")
@click.option("--project", help="Filter by project")
@click.option("--all", "show_all", is_flag=True, help="Include completed todos")
@click.pass_context
def todo(
    ctx: click.Context,
    filter_today: bool,
    filter_week: bool,
    overdue: bool,
    priority: int | None,
    tag: str | None,
    project: str | None,
    show_all: bool,
) -> None:
    """Manage todos.

    Run 'nb todo' without a subcommand to list todos.
    """
    if ctx.invoked_subcommand is None:
        # Default: list todos
        _list_todos(
            filter_today=filter_today,
            filter_week=filter_week,
            overdue=overdue,
            priority=priority,
            tag=tag,
            project=project,
            show_all=show_all,
        )


def _list_todos(
    filter_today: bool = False,
    filter_week: bool = False,
    overdue: bool = False,
    priority: int | None = None,
    tag: str | None = None,
    project: str | None = None,
    show_all: bool = False,
) -> None:
    """List todos with optional filters."""
    # First, ensure todos are indexed
    index_all_notes()

    # Determine completion filter
    completed = None if show_all else False

    if overdue:
        todos = query_todos(
            completed=completed,
            overdue=True,
            priority=priority,
            tag=tag,
            project=project,
        )
    else:
        todos = get_sorted_todos(
            completed=completed, priority=priority, tag=tag, project=project
        )

    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return

    # Group todos for display
    today_date = date.today()
    week_start, week_end = get_week_range()

    groups: dict[str, list] = {
        "OVERDUE": [],
        "DUE TODAY": [],
        "DUE THIS WEEK": [],
        "DUE LATER": [],
        "NO DUE DATE": [],
    }

    for t in todos:
        if t.due_date is None:
            groups["NO DUE DATE"].append(t)
        elif t.due_date < today_date:
            groups["OVERDUE"].append(t)
        elif t.due_date == today_date:
            groups["DUE TODAY"].append(t)
        elif t.due_date <= week_end:
            groups["DUE THIS WEEK"].append(t)
        else:
            groups["DUE LATER"].append(t)

    # Display
    for group_name, group_todos in groups.items():
        if not group_todos:
            continue

        console.print(f"\n[bold]{group_name}[/bold]")

        for t in group_todos:
            _print_todo(t, indent=0)


def _print_todo(t, indent: int = 0) -> None:
    """Print a single todo with formatting."""
    prefix = "  " * indent
    checkbox = "[green]x[/green]" if t.completed else "[dim]o[/dim]"

    # Build content line
    content = t.content

    # Add metadata
    meta_parts = []
    if t.due_date:
        due_str = t.due_date.strftime("%b %d")
        if t.is_overdue:
            meta_parts.append(f"[red]{due_str}[/red]")
        elif t.is_due_today:
            meta_parts.append(f"[yellow]{due_str}[/yellow]")
        else:
            meta_parts.append(f"[dim]{due_str}[/dim]")

    if t.priority:
        meta_parts.append(f"[magenta]!{t.priority.value}[/magenta]")

    if t.tags:
        meta_parts.append(" ".join(f"[cyan]#{tag}[/cyan]" for tag in t.tags[:3]))

    meta_str = "  ".join(meta_parts)

    # Print with short ID
    short_id = t.id[:8]
    if t.completed:
        console.print(
            f"{prefix}{checkbox} [strikethrough]{content}[/strikethrough]  {meta_str}  [dim]{short_id}[/dim]"
        )
    else:
        console.print(
            f"{prefix}{checkbox} {content}  {meta_str}  [dim]{short_id}[/dim]"
        )

    # Print children
    children = get_todo_children(t.id)
    for child in children:
        _print_todo(child, indent=indent + 1)


@todo.command("add")
@click.argument("text")
def todo_add(text: str) -> None:
    """Add a new todo to the inbox.

    TEXT can include metadata like @due(friday), @priority(1), or #tags.
    """
    t = add_todo_to_inbox(text)
    console.print(f"[green]Added:[/green] {t.content}")
    console.print(f"[dim]ID: {t.id[:8]}[/dim]")


@main.command("ta")
@click.argument("text")
@click.pass_context
def todo_add_alias(ctx: click.Context, text: str) -> None:
    """Alias for 'todo add'."""
    t = add_todo_to_inbox(text)
    console.print(f"[green]Added:[/green] {t.content}")
    console.print(f"[dim]ID: {t.id[:8]}[/dim]")


@todo.command("done")
@click.argument("todo_id")
def todo_done(todo_id: str) -> None:
    """Mark a todo as completed.

    TODO_ID can be the full ID or a prefix (e.g., first 8 characters).
    """
    t = _find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    if t.completed:
        console.print("[yellow]Todo is already completed.[/yellow]")
        return

    # Toggle in source file
    if toggle_todo_in_file(t.source.path, t.line_number):
        update_todo_completion(t.id, True)
        console.print(f"[green]Completed:[/green] {t.content}")
    else:
        console.print("[red]Failed to update todo in source file.[/red]")
        raise SystemExit(1)


@todo.command("undone")
@click.argument("todo_id")
def todo_undone(todo_id: str) -> None:
    """Mark a todo as incomplete.

    TODO_ID can be the full ID or a prefix (e.g., first 8 characters).
    """
    t = _find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    if not t.completed:
        console.print("[yellow]Todo is not completed.[/yellow]")
        return

    # Toggle in source file
    if toggle_todo_in_file(t.source.path, t.line_number):
        update_todo_completion(t.id, False)
        console.print(f"[green]Reopened:[/green] {t.content}")
    else:
        console.print("[red]Failed to update todo in source file.[/red]")
        raise SystemExit(1)


@todo.command("show")
@click.argument("todo_id")
def todo_show(todo_id: str) -> None:
    """Show details of a todo."""
    t = _find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    console.print(f"\n[bold]{t.content}[/bold]")
    console.print(f"ID: {t.id}")
    console.print(f"Status: {'Completed' if t.completed else 'Open'}")
    console.print(f"Source: {t.source.path}:{t.line_number}")

    if t.due_date:
        console.print(f"Due: {t.due_date}")
    if t.priority:
        console.print(f"Priority: {t.priority.value}")
    if t.tags:
        console.print(f"Tags: {', '.join(t.tags)}")
    if t.project:
        console.print(f"Project: {t.project}")

    children = get_todo_children(t.id)
    if children:
        console.print("\n[bold]Subtasks:[/bold]")
        for child in children:
            checkbox = "x" if child.completed else "o"
            console.print(f"  {checkbox} {child.content}")


@todo.command("edit")
@click.argument("todo_id")
def todo_edit(todo_id: str) -> None:
    """Open the source file at the todo's line."""
    t = _find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    config = get_config()
    console.print(f"[dim]Opening {t.source.path.name}:{t.line_number}...[/dim]")
    open_in_editor(t.source.path, line=t.line_number, editor=config.editor)


def _find_todo(todo_id: str):
    """Find a todo by ID or ID prefix."""
    # First try exact match
    t = get_todo_by_id(todo_id)
    if t:
        return t

    # Try prefix match
    from nb.index.db import get_db

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
                console.print(f"  {row['id'][:12]}: {t.content[:50]}")
        return None

    return None


# =============================================================================
# Index Command
# =============================================================================


@main.command("index")
@click.option("--force", "-f", is_flag=True, help="Force reindex all files")
def index_cmd(force: bool) -> None:
    """Rebuild the notes and todos index."""
    console.print("[dim]Indexing notes...[/dim]")
    count = index_all_notes(force=force)
    console.print(f"[green]Indexed {count} files.[/green]")

    stats = get_todo_stats()
    console.print(f"Todos: {stats['open']} open, {stats['completed']} completed")
    if stats["overdue"]:
        console.print(f"[red]{stats['overdue']} overdue[/red]")


# =============================================================================
# Aliases
# =============================================================================


@main.command("td")
@click.pass_context
def todo_alias(ctx: click.Context) -> None:
    """Alias for 'todo' (list todos)."""
    index_all_notes()
    todos = get_sorted_todos(completed=False)
    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return
    _list_todos()


if __name__ == "__main__":
    main()
