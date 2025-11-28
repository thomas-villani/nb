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
from nb.core.todos import add_todo_to_daily_note, add_todo_to_inbox, toggle_todo_in_file
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


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="nb")
@click.option(
    "-s", "--show", is_flag=True, help="Print note to console instead of opening editor"
)
@click.pass_context
def main(ctx: click.Context, show: bool) -> None:
    """A plaintext-first note-taking and todo management CLI.

    Run 'nb' without arguments to open today's daily note.
    Use -s to print the note to console instead.
    """
    ensure_setup()
    ctx.ensure_object(dict)
    ctx.obj["show"] = show
    if ctx.invoked_subcommand is None:
        # Default action: open today's note
        ctx.invoke(today)


@main.command()
@click.option("--notebook", "-n", help="Notebook to create today's note in")
@click.pass_context
def today(ctx: click.Context, notebook: str | None) -> None:
    """Open today's note.

    By default opens today's daily note. Use -n to specify a different notebook.

    \b
    Examples:
      nb today           # Today's note in 'daily'
      nb today -n work   # Today's note in 'work' notebook
    """
    from nb.core.notebooks import is_notebook_date_based, ensure_notebook_note

    dt = date.today()

    if notebook:
        # Create today's note in specified notebook
        if is_notebook_date_based(notebook):
            # Use date-based structure
            path = ensure_notebook_note(notebook, dt=dt)
        else:
            # Use today's date as filename
            path = ensure_notebook_note(notebook, name=dt.isoformat())
    else:
        # Default: daily notebook
        path = ensure_daily_note(dt)

    if ctx.obj and ctx.obj.get("show"):
        print_note(path)
    else:
        config = get_config()
        try:
            rel_path = path.relative_to(config.notes_root)
        except ValueError:
            rel_path = path
        console.print(f"[dim]Opening {rel_path}...[/dim]")
        open_note(path)


@main.command()
@click.pass_context
def yesterday(ctx: click.Context) -> None:
    """Open yesterday's daily note."""
    dt = date.today() - timedelta(days=1)
    path = ensure_daily_note(dt)

    if ctx.obj and ctx.obj.get("show"):
        print_note(path)
    else:
        console.print(f"[dim]Opening {path.name}...[/dim]")
        open_note(path)


@main.command("t")
@click.option("--notebook", "-n", help="Notebook to create today's note in")
@click.pass_context
def today_alias(ctx: click.Context, notebook: str | None) -> None:
    """Alias for 'today'."""
    ctx.invoke(today, notebook=notebook)


@main.command("y")
@click.pass_context
def yesterday_alias(ctx: click.Context) -> None:
    """Alias for 'yesterday'."""
    ctx.invoke(yesterday)


@main.command("open")
@click.argument("date_str")
@click.pass_context
def open_date(ctx: click.Context, date_str: str) -> None:
    """Open a note for a specific date.

    DATE_STR can be:
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A path to a note file
    """
    config = get_config()
    show = ctx.obj and ctx.obj.get("show")

    # First check if it's a path to an existing note
    path = Path(date_str)
    if not path.suffix:
        path = path.with_suffix(".md")

    full_path = config.notes_root / path
    if full_path.exists():
        if show:
            print_note(full_path)
        else:
            console.print(f"[dim]Opening {path}...[/dim]")
            open_note(full_path)
        return

    # Try to parse as a date
    parsed = parse_fuzzy_date(date_str)
    if parsed:
        note_path = ensure_daily_note(parsed)
        if show:
            print_note(note_path)
        else:
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
@click.argument("path", required=False)
@click.option("--notebook", "-n", help="Notebook to create the note in")
@click.option("--title", "-t", help="Title for the note")
def new_note(path: str | None, notebook: str | None, title: str | None) -> None:
    """Create a new note.

    PATH is the location for the note. Can be:
    - A full path: "projects/myproject/ideas"
    - Just a name: "ideas" (requires --notebook)
    - Omitted if notebook is date-based (creates today's note)

    The .md extension is added automatically if not present.

    \b
    Examples:
      nb new -n daily           # Today's note in daily (date-based)
      nb new ideas -n projects  # projects/ideas.md
      nb new projects/roadmap   # projects/roadmap.md
    """
    from nb.core.notebooks import is_notebook_date_based, ensure_notebook_note

    config = get_config()

    # If notebook specified but no path, check if it's date-based
    if notebook and not path:
        if is_notebook_date_based(notebook):
            # Create/open today's note in this date-based notebook
            full_path = ensure_notebook_note(notebook)
            console.print(
                f"[green]Opening:[/green] {full_path.relative_to(config.notes_root)}"
            )
            open_note(full_path)
            return
        else:
            console.print(f"[yellow]Notebook '{notebook}' is not date-based.[/yellow]")
            console.print(f"Please provide a note name: nb new <name> -n {notebook}")
            raise SystemExit(1)

    # If no path and no notebook, show help
    if not path:
        console.print("[yellow]Usage: nb new <name> --notebook <notebook>[/yellow]")
        console.print("       nb new -n <date-based-notebook>  # Creates today's note")
        console.print("\nAvailable notebooks:")
        for nb in config.notebooks:
            date_hint = " (date-based)" if nb.date_based else ""
            console.print(f"  - {nb.name}{date_hint}")
        raise SystemExit(1)

    note_path = Path(path)

    # If notebook specified and path doesn't include a notebook, prepend it
    if notebook:
        # Check if notebook exists
        notebook_names = [nb.name for nb in config.notebooks]
        if notebook not in notebook_names:
            console.print(
                f"[yellow]Warning: '{notebook}' is not a configured notebook.[/yellow]"
            )
            console.print(f"Available notebooks: {', '.join(notebook_names)}")
            # Still allow it - might be intentional

        # If path doesn't already start with the notebook, prepend it
        if not str(note_path).startswith(notebook):
            note_path = Path(notebook) / note_path

    # If path doesn't include a notebook dir and none specified, check if it matches a notebook
    elif len(note_path.parts) == 1:
        # Single name - could be a notebook name or a note name
        notebook_names = [nb.name for nb in config.notebooks]

        # If it's a notebook name, probably a mistake
        if path in notebook_names:
            console.print(
                f"[yellow]'{path}' is a notebook name. Did you mean:[/yellow]"
            )
            console.print(f"  nb {path}      # Open today's note in {path}")
            console.print(f"  nb new <name> -n {path}  # Create a note in {path}")
            raise SystemExit(1)

        # Otherwise, ask which notebook
        console.print(f"[yellow]No notebook specified for '{path}'.[/yellow]")
        console.print("Use --notebook/-n to specify, or provide full path:")
        for nb in config.notebooks:
            console.print(f"  nb new {path} -n {nb.name}")
        raise SystemExit(1)

    try:
        full_path = create_note(note_path, title=title)
        console.print(f"[green]Created:[/green] {note_path}")
        open_note(full_path)
    except FileExistsError:
        console.print(f"[red]Note already exists:[/red] {note_path}")
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


@main.group("notebooks", invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Show note counts")
@click.pass_context
def notebooks_cmd(ctx: click.Context, verbose: bool) -> None:
    """Manage notebooks.

    Run without a subcommand to list all notebooks.
    """
    if ctx.invoked_subcommand is None:
        _list_notebooks(verbose)


def _list_notebooks(verbose: bool = False) -> None:
    """List all notebooks."""
    config = get_config()
    nbs = config.notebooks

    if not nbs:
        console.print("[dim]No notebooks found.[/dim]")
        return

    if verbose:
        table = Table(show_header=True)
        table.add_column("Notebook")
        table.add_column("Type")
        table.add_column("Notes", justify="right")
        table.add_column("Path")

        for nb in nbs:
            nb_path = config.get_notebook_path(nb.name)
            if nb_path and nb_path.exists():
                notes = get_notebook_notes(nb.name)
                note_count = str(len(notes))
            else:
                note_count = "[dim]-[/dim]"

            nb_type_parts = []
            if nb.date_based:
                nb_type_parts.append("date")
            if nb.todo_exclude:
                nb_type_parts.append("excl")
            if nb.is_external:
                nb_type_parts.append("ext")
            nb_type = ", ".join(nb_type_parts) if nb_type_parts else "-"

            path_display = str(nb.path) if nb.is_external else f"~/{nb.name}"
            table.add_row(nb.name, nb_type, note_count, path_display)

        console.print(table)
    else:
        for nb in nbs:
            suffix = ""
            if nb.is_external:
                suffix = f" [dim](external: {nb.path})[/dim]"
            elif nb.date_based:
                suffix = " [dim](date-based)[/dim]"
            console.print(f"{nb.name}{suffix}")


@notebooks_cmd.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show details")
def notebooks_list(verbose: bool) -> None:
    """List all notebooks."""
    _list_notebooks(verbose)


@notebooks_cmd.command("create")
@click.argument("name")
@click.option("--from", "from_path", help="External path to use as notebook")
@click.option("--date-based", "-d", is_flag=True, help="Use date-based organization")
@click.option(
    "--todo-exclude", "-x", is_flag=True, help="Exclude from nb todo by default"
)
def notebooks_create(
    name: str,
    from_path: str | None,
    date_based: bool,
    todo_exclude: bool,
) -> None:
    """Create a new notebook.

    Examples:
        nb notebooks create ideas
        nb notebooks create work-log --date-based
        nb notebooks create obsidian --from ~/Documents/Obsidian/vault
        nb notebooks create personal --todo-exclude
    """
    from nb.config import add_notebook, expand_path

    # Validate external path if provided
    ext_path = None
    if from_path:
        ext_path = expand_path(from_path)
        if not ext_path.exists():
            console.print(f"[red]Path does not exist:[/red] {ext_path}")
            raise SystemExit(1)
        if not ext_path.is_dir():
            console.print(f"[red]Path is not a directory:[/red] {ext_path}")
            raise SystemExit(1)

    try:
        nb = add_notebook(
            name=name,
            date_based=date_based,
            todo_exclude=todo_exclude,
            path=ext_path,
        )

        if nb.is_external:
            console.print(
                f"[green]Created external notebook:[/green] {name} -> {ext_path}"
            )
        else:
            config = get_config()
            console.print(f"[green]Created notebook:[/green] {name}")
            console.print(f"[dim]Location: {config.notes_root / name}[/dim]")

        if date_based:
            console.print(
                "[dim]Using date-based organization (YYYY/Week/YYYY-MM-DD.md)[/dim]"
            )
        if todo_exclude:
            console.print("[dim]Excluded from nb todo by default[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@notebooks_cmd.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def notebooks_remove(name: str, yes: bool) -> None:
    """Remove a notebook from configuration.

    Note: This only removes the notebook from nb's configuration.
    The actual files are NOT deleted.
    """
    from nb.config import remove_notebook

    config = get_config()
    nb = config.get_notebook(name)

    if nb is None:
        console.print(f"[red]Notebook not found:[/red] {name}")
        raise SystemExit(1)

    if not yes:
        if nb.is_external:
            console.print(f"Remove external notebook '{name}' from configuration?")
            console.print(f"[dim]Path: {nb.path}[/dim]")
        else:
            console.print(f"Remove notebook '{name}' from configuration?")
            console.print("[dim]Files will NOT be deleted.[/dim]")

        if not click.confirm("Continue?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    if remove_notebook(name):
        console.print(f"[green]Removed notebook:[/green] {name}")
    else:
        console.print(f"[red]Failed to remove notebook:[/red] {name}")


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
@click.option("--notebook", "-n", help="Filter by notebook (overrides exclusions)")
@click.option("--all", "show_all", is_flag=True, help="Include completed todos")
@click.option("-i", "--interactive", is_flag=True, help="Open interactive todo viewer")
@click.pass_context
def todo(
    ctx: click.Context,
    filter_today: bool,
    filter_week: bool,
    overdue: bool,
    priority: int | None,
    tag: str | None,
    notebook: str | None,
    show_all: bool,
    interactive: bool,
) -> None:
    """Manage todos.

    Run 'nb todo' without a subcommand to list todos.
    Use -i for interactive mode with keyboard navigation.

    Notebooks with todo_exclude: true in config are hidden by default.
    Use -n <notebook> to view a specific notebook (including excluded ones).
    """
    if ctx.invoked_subcommand is None:
        # Ensure todos are indexed (skip vector indexing for speed)
        index_all_notes(index_vectors=False)

        # Get excluded notebooks from config (unless a specific notebook is requested)
        config = get_config()
        exclude_notebooks = None if notebook else config.excluded_notebooks() or None

        if interactive:
            # Launch interactive viewer
            from nb.tui.todos import run_interactive_todos

            run_interactive_todos(
                show_completed=show_all,
                tag=tag,
                notebook=notebook,
                exclude_notebooks=exclude_notebooks,
            )
        else:
            # Default: list todos
            _list_todos(
                filter_today=filter_today,
                filter_week=filter_week,
                overdue=overdue,
                priority=priority,
                tag=tag,
                notebook=notebook,
                exclude_notebooks=exclude_notebooks,
                show_all=show_all,
            )


def _list_todos(
    filter_today: bool = False,
    filter_week: bool = False,
    overdue: bool = False,
    priority: int | None = None,
    tag: str | None = None,
    notebook: str | None = None,
    exclude_notebooks: list[str] | None = None,
    show_all: bool = False,
) -> None:
    """List todos with optional filters."""
    # Determine completion filter
    completed = None if show_all else False

    if overdue:
        todos = query_todos(
            completed=completed,
            overdue=True,
            priority=priority,
            tag=tag,
            notebook=notebook,
            exclude_notebooks=exclude_notebooks,
        )
    else:
        todos = get_sorted_todos(
            completed=completed,
            priority=priority,
            tag=tag,
            notebook=notebook,
            exclude_notebooks=exclude_notebooks,
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


def _format_todo_source(t) -> str:
    """Format the source of a todo for display."""
    if not t.source:
        return ""

    if t.source.alias:
        # Linked file - show @alias
        return f"@{t.source.alias}"
    elif t.source.type == "inbox":
        return "inbox"
    else:
        # Regular note - show notebook/filename
        config = get_config()
        try:
            rel_path = t.source.path.relative_to(config.notes_root)
            if len(rel_path.parts) > 1:
                return f"{rel_path.parts[0]}/{rel_path.stem}"
            else:
                return rel_path.stem
        except ValueError:
            return t.source.path.stem


def _print_todo(t, indent: int = 0) -> None:
    """Print a single todo with formatting."""
    prefix = "  " * indent
    checkbox = "[green]x[/green]" if t.completed else "[dim]o[/dim]"

    # Build content line
    content = t.content

    # Add metadata
    meta_parts = []

    # Add source info
    source_str = _format_todo_source(t)
    if source_str:
        meta_parts.append(f"[blue]{source_str}[/blue]")

    # Add created date
    if t.created_date:
        created_str = t.created_date.strftime("%m/%d")
        meta_parts.append(f"[dim]+{created_str}[/dim]")

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

    # Print with short ID (6 chars is plenty for personal use)
    short_id = t.id[:6]
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
@click.option(
    "--today",
    "add_today",
    is_flag=True,
    help="Add to today's daily note instead of inbox",
)
def todo_add(text: str, add_today: bool) -> None:
    """Add a new todo to the inbox (or today's note with --today).

    TEXT can include metadata like @due(friday), @priority(1), or #tags.

    Examples:
        nb todo add "Review PR @due(friday) #work"
        nb todo add --today "Call dentist @priority(1)"
    """
    if add_today:
        t = add_todo_to_daily_note(text)
        console.print(f"[green]Added to today's note:[/green] {t.content}")
    else:
        t = add_todo_to_inbox(text)
        console.print(f"[green]Added to inbox:[/green] {t.content}")
    console.print(f"[dim]ID: {t.id[:6]}[/dim]")


@main.command("ta")
@click.argument("text")
@click.option("--today", "add_today", is_flag=True, help="Add to today's daily note")
def todo_add_alias(text: str, add_today: bool) -> None:
    """Alias for 'todo add'."""
    if add_today:
        t = add_todo_to_daily_note(text)
        console.print(f"[green]Added to today's note:[/green] {t.content}")
    else:
        t = add_todo_to_inbox(text)
        console.print(f"[green]Added to inbox:[/green] {t.content}")
    console.print(f"[dim]ID: {t.id[:6]}[/dim]")


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
    try:
        if toggle_todo_in_file(t.source.path, t.line_number):
            update_todo_completion(t.id, True)
            console.print(f"[green]Completed:[/green] {t.content}")
        else:
            console.print("[red]Failed to update todo in source file.[/red]")
            raise SystemExit(1)
    except PermissionError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Use 'nb link' to enable sync for this file.[/dim]")
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
    try:
        if toggle_todo_in_file(t.source.path, t.line_number):
            update_todo_completion(t.id, False)
            console.print(f"[green]Reopened:[/green] {t.content}")
        else:
            console.print("[red]Failed to update todo in source file.[/red]")
            raise SystemExit(1)
    except PermissionError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Use 'nb link' to enable sync for this file.[/dim]")
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
                console.print(f"  {row['id'][:6]}: {t.content[:50]}")
        return None

    return None


# =============================================================================
# Search Commands
# =============================================================================


@main.command("search")
@click.argument("query")
@click.option(
    "-s", "--semantic", is_flag=True, help="Use pure semantic search (no keyword)"
)
@click.option(
    "-k", "--keyword", is_flag=True, help="Use pure keyword search (no semantic)"
)
@click.option("-t", "--tag", help="Filter by tag")
@click.option("--notebook", "-n", help="Filter by notebook")
@click.option(
    "--when",
    "when_filter",
    help="Filter by date range (e.g., 'last 3 months', 'this week')",
)
@click.option("--since", "since_date", help="Show notes from this date onwards")
@click.option("--until", "until_date", help="Show notes up to this date")
@click.option(
    "--recent", is_flag=True, help="Boost recent results (30% recency weight)"
)
@click.option("--limit", default=20, help="Max results")
def search_cmd(
    query: str,
    semantic: bool,
    keyword: bool,
    tag: str | None,
    notebook: str | None,
    when_filter: str | None,
    since_date: str | None,
    until_date: str | None,
    recent: bool,
    limit: int,
) -> None:
    """Search notes by keyword, semantic similarity, or both (hybrid).

    By default uses hybrid search (70% semantic, 30% keyword).
    Use --semantic for pure semantic search, --keyword for pure keyword search.

    Date filtering:
        --when "last 3 months"    Fuzzy date range
        --when "this week"        Current week
        --since friday            From a date onwards
        --until "nov 20"          Up to a date

    Examples:
        nb search "machine learning"
        nb search -s "project ideas" --recent
        nb search "TODO" --when "last 2 weeks"
        nb search "meeting notes" --since "last monday"
    """
    from nb.index.search import get_search
    from nb.utils.dates import parse_date_range, parse_fuzzy_date

    # Determine search type
    if semantic and keyword:
        console.print("[red]Cannot use both --semantic and --keyword[/red]")
        raise SystemExit(1)
    elif semantic:
        search_type = "vector"
    elif keyword:
        search_type = "keyword"
    else:
        search_type = "hybrid"

    # Build filters
    filters = {}
    if tag:
        filters["tags"] = {"$contains": tag}
    if notebook:
        filters["notebook"] = notebook

    # Handle date filtering
    date_start = None
    date_end = None

    if when_filter:
        start, end = parse_date_range(when_filter)
        if start:
            date_start = start.isoformat()
        if end:
            date_end = end.isoformat()
        if not start and not end:
            console.print(f"[yellow]Could not parse date range: {when_filter}[/yellow]")

    if since_date:
        parsed = parse_fuzzy_date(since_date)
        if parsed:
            date_start = parsed.isoformat()
        else:
            console.print(f"[yellow]Could not parse date: {since_date}[/yellow]")

    if until_date:
        parsed = parse_fuzzy_date(until_date)
        if parsed:
            date_end = parsed.isoformat()
        else:
            console.print(f"[yellow]Could not parse date: {until_date}[/yellow]")

    # Determine recency boost
    recency_boost = 0.3 if recent else 0.0

    try:
        search = get_search()
        results = search.search(
            query,
            search_type=search_type,
            k=limit,
            filters=filters if filters else None,
            date_start=date_start,
            date_end=date_end,
            recency_boost=recency_boost,
        )
    except Exception as e:
        console.print(f"[red]Search failed:[/red] {e}")
        console.print(
            "[dim]Make sure the index is built and embeddings are available.[/dim]"
        )
        raise SystemExit(1)

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    # Show filter info
    filter_info = []
    if date_start or date_end:
        if date_start and date_end:
            filter_info.append(f"dates: {date_start} to {date_end}")
        elif date_start:
            filter_info.append(f"since: {date_start}")
        else:
            filter_info.append(f"until: {date_end}")
    if recent:
        filter_info.append("recency boosted")

    if filter_info:
        console.print(f"[dim]Filters: {', '.join(filter_info)}[/dim]")

    console.print(f"\n[bold]Found {len(results)} results:[/bold]\n")

    for r in results:
        # Display path and title
        title = r.title or Path(r.path).stem
        console.print(f"[bold cyan]{r.path}[/bold cyan]")
        console.print(f"  [bold]{title}[/bold]")

        # Display score and metadata
        meta_parts = [f"score: {r.score:.3f}"]
        if r.notebook:
            meta_parts.append(f"notebook: {r.notebook}")
        if r.date:
            meta_parts.append(f"date: {r.date}")
        console.print(f"  [dim]{' | '.join(meta_parts)}[/dim]")

        # Display snippet
        if r.snippet:
            snippet = r.snippet.replace("\n", " ").strip()
            if len(snippet) > 150:
                snippet = snippet[:150] + "..."
            console.print(f"  [dim]{snippet}[/dim]")

        console.print()


@main.command("s")
@click.argument("query")
@click.pass_context
def search_alias(ctx: click.Context, query: str) -> None:
    """Alias for 'search' (hybrid search)."""
    ctx.invoke(search_cmd, query=query)


@main.command("ss")
@click.argument("query")
@click.pass_context
def semantic_search_alias(ctx: click.Context, query: str) -> None:
    """Alias for 'search --semantic'."""
    ctx.invoke(search_cmd, query=query, semantic=True)


@main.command("grep")
@click.argument("pattern")
@click.option("-C", "--context", "context_lines", default=2, help="Context lines")
@click.option(
    "-i", "--ignore-case/--case-sensitive", default=True, help="Case sensitivity"
)
def grep_cmd(pattern: str, context_lines: int, ignore_case: bool) -> None:
    """Search notes with regex pattern matching.

    Unlike 'search', this performs raw regex matching on the files.
    Useful for finding exact strings, code snippets, or patterns.

    Examples:
        nb grep "TODO.*urgent"
        nb grep "def\\s+\\w+" -C 5
        nb grep "API_KEY" --case-sensitive
    """
    from nb.index.search import grep_notes

    config = get_config()

    try:
        results = grep_notes(
            pattern,
            config.notes_root,
            context_lines=context_lines,
            case_sensitive=not ignore_case,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if not results:
        console.print("[dim]No matches found.[/dim]")
        return

    console.print(f"\n[bold]Found {len(results)} matches:[/bold]\n")

    current_file = None
    for r in results:
        # Print file header when it changes
        if r.path != current_file:
            if current_file is not None:
                console.print()  # Blank line between files
            console.print(f"[bold cyan]{r.path}[/bold cyan]")
            current_file = r.path

        # Print context before
        for i, line in enumerate(r.context_before):
            line_num = r.line_number - len(r.context_before) + i
            console.print(f"[dim]{line_num:4d}:[/dim] {line}")

        # Print matching line (highlighted)
        console.print(
            f"[yellow]{r.line_number:4d}:[/yellow] [bold]{r.line_content}[/bold]"
        )

        # Print context after
        for i, line in enumerate(r.context_after):
            line_num = r.line_number + 1 + i
            console.print(f"[dim]{line_num:4d}:[/dim] {line}")

        console.print()


# =============================================================================
# Index Command
# =============================================================================


@main.command("index")
@click.option("--force", "-f", is_flag=True, help="Force reindex all files")
@click.option("--rebuild", is_flag=True, help="Drop and recreate the database")
@click.option("--embeddings", "-e", is_flag=True, help="Rebuild search embeddings")
def index_cmd(force: bool, rebuild: bool, embeddings: bool) -> None:
    """Rebuild the notes and todos index.

    Incrementally indexes new and modified files. Use --force to reindex
    all files, or --rebuild to drop and recreate the database entirely.

    \b
    Examples:
      nb index               # Index new/changed files
      nb index --force       # Reindex all files
      nb index --rebuild     # Drop database and reindex (fixes schema issues)
      nb index --embeddings  # Rebuild semantic search vectors
    """
    if rebuild:
        console.print("[yellow]Rebuilding database from scratch...[/yellow]")
        from nb.index.db import get_db, rebuild_db

        db = get_db()
        rebuild_db(db)
        console.print("[green]Database rebuilt.[/green]")
        force = True  # Force reindex after rebuild

    console.print("[dim]Indexing notes...[/dim]")
    count = index_all_notes(force=force)
    console.print(f"[green]Indexed {count} files.[/green]")

    if embeddings:
        console.print("[dim]Rebuilding search index...[/dim]")
        from nb.index.scanner import rebuild_search_index

        search_count = rebuild_search_index()
        console.print(f"[green]Indexed {search_count} notes for search.[/green]")

    stats = get_todo_stats()
    console.print(f"Todos: {stats['open']} open, {stats['completed']} completed")
    if stats["overdue"]:
        console.print(f"[red]{stats['overdue']} overdue[/red]")


# =============================================================================
# Stream Command
# =============================================================================


@main.command("stream")
@click.argument("notebook", required=False)
@click.option(
    "--when", "-w", help="Date range: 'last week', 'this week', 'last 3 days'"
)
@click.option("--since", help="Start from this date")
@click.option("--until", help="End at this date")
@click.option("--reverse", "-r", is_flag=True, help="Show oldest first")
def stream_notes(
    notebook: str | None,
    when: str | None,
    since: str | None,
    until: str | None,
    reverse: bool,
) -> None:
    """Browse notes interactively in a streaming view.

    Navigate through notes with keyboard controls:

    \b
    j/k or arrows  - Scroll within note
    n/N or p       - Next/previous note
    g/G            - First/last note (or top/bottom of current)
    d/u            - Half-page down/up
    e              - Edit current note
    q              - Quit

    Examples:

    \b
      nb stream                      # Stream all notes
      nb stream daily                # Stream daily notes
      nb stream -w "last week"       # Last week's notes
      nb stream -w "this week"       # This week's notes
      nb stream daily -w "last 2 weeks"  # Daily notes from last 2 weeks
    """
    from nb.index.db import get_db
    from nb.models import Note
    from nb.tui.stream import run_note_stream
    from nb.utils.dates import parse_fuzzy_date, parse_date_range
    from datetime import date as date_type

    config = get_config()
    db = get_db()

    # Build query
    query = "SELECT path, title, date, notebook FROM notes WHERE 1=1"
    params: list = []

    # Filter by notebook
    if notebook:
        query += " AND notebook = ?"
        params.append(notebook)

    # Filter by date range
    # --when takes precedence and uses parse_date_range for week support
    if when:
        start, end = parse_date_range(when)
        if start:
            query += " AND date >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND date <= ?"
            params.append(end.isoformat())
    else:
        if since:
            since_date = parse_fuzzy_date(since)
            if since_date:
                query += " AND date >= ?"
                params.append(since_date.isoformat())

        if until:
            until_date = parse_fuzzy_date(until)
            if until_date:
                query += " AND date <= ?"
                params.append(until_date.isoformat())

    # Order by date
    if reverse:
        query += " ORDER BY date ASC"
    else:
        query += " ORDER BY date DESC"

    rows = db.fetchall(query, tuple(params))

    if not rows:
        console.print("[yellow]No notes found.[/yellow]")
        return

    # Convert to Note objects
    notes = []
    for row in rows:
        note_date = None
        if row["date"]:
            try:
                note_date = date_type.fromisoformat(row["date"])
            except ValueError:
                pass

        notes.append(
            Note(
                path=Path(row["path"]),
                title=row["title"] or "",
                date=note_date,
                tags=[],
                links=[],
                attachments=[],
                notebook=row["notebook"] or "",
                content_hash="",
            )
        )

    console.print(f"[dim]Loading {len(notes)} notes...[/dim]")
    run_note_stream(notes, config.notes_root)


# =============================================================================
# Link Commands
# =============================================================================


@main.group()
def link() -> None:
    """Manage linked external files.

    Link external markdown files or directories to index them
    alongside your notes. Both todos and note content are indexed.
    """
    pass


@link.command("list")
def link_list() -> None:
    """List all linked external files."""
    from nb.core.links import list_linked_files, list_linked_notes

    linked_todos = list_linked_files()
    linked_notes = list_linked_notes()

    if not linked_todos and not linked_notes:
        console.print("[dim]No linked files.[/dim]")
        console.print("[dim]Use 'nb link add <path>' to add one.[/dim]")
        return

    table = Table(show_header=True, title="Linked Files")
    table.add_column("Alias")
    table.add_column("Path")
    table.add_column("Type")
    table.add_column("Sync")
    table.add_column("Exists")

    for lf in linked_todos:
        exists = "[green]yes[/green]" if lf.path.exists() else "[red]no[/red]"
        sync = "[green]yes[/green]" if lf.sync else "[dim]no[/dim]"
        table.add_row(lf.alias, str(lf.path), "todos", sync, exists)

    for ln in linked_notes:
        exists = "[green]yes[/green]" if ln.path.exists() else "[red]no[/red]"
        path_type = "notes"
        if ln.path.is_dir():
            path_type = "notes (dir)" if not ln.recursive else "notes (recursive)"
        table.add_row(ln.alias, str(ln.path), path_type, "-", exists)

    console.print(table)


@link.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--alias", "-a", help="Short name for the file (defaults to filename)")
@click.option(
    "--sync/--no-sync", default=True, help="Sync todo completions back to source"
)
@click.option(
    "--notebook", "-n", help="Virtual notebook name for notes (defaults to @alias)"
)
@click.option(
    "--no-recursive", is_flag=True, help="Don't scan subdirectories (for directories)"
)
@click.option("--todos-only", is_flag=True, help="Only index todos (not note content)")
@click.option("--notes-only", is_flag=True, help="Only index note content (not todos)")
def link_add(
    path: str,
    alias: str | None,
    sync: bool,
    notebook: str | None,
    no_recursive: bool,
    todos_only: bool,
    notes_only: bool,
) -> None:
    """Link an external file or directory.

    By default, both todos and note content are indexed from linked files.
    Use --todos-only or --notes-only to limit what gets indexed.

    With --sync (default), completing a todo will update the source file.

    Examples:
        nb link add ~/work/TODO.md              # Index todos and notes
        nb link add ~/docs/wiki --notes-only    # Only index as notes
        nb link add ~/project/tasks.md --todos-only --no-sync
    """
    from nb.core.links import add_linked_file, add_linked_note
    from nb.index.scanner import index_linked_file, index_single_linked_note

    p = Path(path)
    todo_count = 0
    note_count = 0

    try:
        # Index todos unless notes-only
        if not notes_only:
            linked_todo = add_linked_file(
                p,
                alias=alias,
                sync=sync,
                save_to_config=False,
            )
            todo_count = index_linked_file(linked_todo.path, alias=linked_todo.alias)
            console.print(f"[green]Linked for todos:[/green] {linked_todo.alias}")
            console.print(f"[dim]Found {todo_count} todos.[/dim]")

        # Index notes unless todos-only
        if not todos_only:
            # Use different alias if both are being added
            note_alias = (
                f"{alias or p.stem}-notes"
                if not notes_only and not todos_only
                else alias
            )
            linked_note = add_linked_note(
                p,
                alias=note_alias,
                notebook=notebook,
                recursive=not no_recursive,
                save_to_config=False,
            )
            note_count = index_single_linked_note(linked_note.alias)
            console.print(f"[green]Linked for notes:[/green] {linked_note.alias}")
            console.print(
                f"[dim]Indexed {note_count} notes in @{linked_note.notebook}.[/dim]"
            )

    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    except ValueError as e:
        # Alias already exists - that's OK for unified linking
        if "already in use" in str(e) and not notes_only and not todos_only:
            console.print(f"[dim]Note: {e}[/dim]")
        else:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1)


@link.command("remove")
@click.argument("alias")
def link_remove(alias: str) -> None:
    """Stop tracking a linked external file.

    This does not delete the file, just removes it from tracking.
    Works for both todo and note links.
    """
    from nb.core.links import (
        get_linked_file,
        get_linked_note,
        remove_linked_file,
        remove_linked_note,
    )
    from nb.index.scanner import remove_linked_note_from_index
    from nb.index.todos_repo import delete_todos_for_source

    removed = False

    # Try to remove as todo link
    linked_todo = get_linked_file(alias)
    if linked_todo:
        delete_todos_for_source(linked_todo.path)
        remove_linked_file(alias)
        console.print(f"[green]Removed todo link:[/green] {alias}")
        removed = True

    # Try to remove as note link
    linked_note = get_linked_note(alias)
    if linked_note:
        remove_linked_note_from_index(alias)
        remove_linked_note(alias)
        console.print(f"[green]Removed note link:[/green] {alias}")
        removed = True

    if not removed:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("sync")
@click.argument("alias", required=False)
def link_sync(alias: str | None) -> None:
    """Re-scan linked files and update index.

    If ALIAS is provided, only that file is scanned.
    Otherwise, all linked files (todos and notes) are scanned.
    """
    from nb.core.links import (
        get_linked_file,
        get_linked_note,
        list_linked_files,
        list_linked_notes,
    )
    from nb.index.scanner import (
        index_linked_file,
        index_single_linked_note,
        scan_linked_files,
        scan_linked_notes,
    )

    if alias:
        synced = False

        # Try as todo link
        linked_todo = get_linked_file(alias)
        if linked_todo:
            if not linked_todo.path.exists():
                console.print(f"[red]File does not exist: {linked_todo.path}[/red]")
                raise SystemExit(1)
            todo_count = index_linked_file(linked_todo.path, alias=linked_todo.alias)
            console.print(f"[green]Synced todos:[/green] {todo_count}")
            synced = True

        # Try as note link
        linked_note = get_linked_note(alias)
        if linked_note:
            if not linked_note.path.exists():
                console.print(f"[red]Path does not exist: {linked_note.path}[/red]")
                raise SystemExit(1)
            note_count = index_single_linked_note(alias)
            console.print(f"[green]Synced notes:[/green] {note_count}")
            synced = True

        if not synced:
            console.print(f"[red]Linked file not found: {alias}[/red]")
            raise SystemExit(1)
    else:
        todo_total = scan_linked_files()
        note_total = scan_linked_notes()
        todo_count = len(list_linked_files())
        note_count = len(list_linked_notes())
        console.print(
            f"[green]Synced:[/green] {todo_count} todo sources ({todo_total} todos), {note_count} note sources ({note_total} notes)"
        )


@link.command("enable-sync")
@click.argument("alias")
def link_enable_sync(alias: str) -> None:
    """Enable syncing completions back to a linked file."""
    from nb.core.links import update_linked_file_sync

    if update_linked_file_sync(alias, True):
        console.print(f"[green]Enabled sync for:[/green] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("disable-sync")
@click.argument("alias")
def link_disable_sync(alias: str) -> None:
    """Disable syncing completions back to a linked file.

    Todos will still be tracked, but completing them won't modify the source.
    """
    from nb.core.links import update_linked_file_sync

    if update_linked_file_sync(alias, False):
        console.print(f"[yellow]Disabled sync for:[/yellow] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


# =============================================================================
# Attach Commands
# =============================================================================


@main.group()
def attach() -> None:
    """Manage file attachments.

    Attach files or URLs to notes and todos. Files can be linked
    (referenced in place) or copied to the attachments directory.
    """
    pass


@attach.command("file")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--to", "target", help="Note path or todo ID to attach to")
@click.option("--title", "-t", help="Display title for the attachment")
@click.option("--copy", "-c", is_flag=True, help="Copy file to attachments directory")
def attach_file(
    file_path: str, target: str | None, title: str | None, copy: bool
) -> None:
    """Attach a file to a note or todo.

    By default attaches to today's daily note. Use --to to specify a target.

    Examples:
        nb attach file ./document.pdf
        nb attach file ~/image.png --to daily/2025-11-27.md
        nb attach file report.pdf --to abc12345 --copy
    """
    from nb.core.attachments import attach_to_note, attach_to_todo

    config = get_config()

    # Determine target
    if target is None:
        # Default to today's note
        note_path = ensure_daily_note(date.today())
    elif len(target) >= 8 and "/" not in target and "\\" not in target:
        # Looks like a todo ID - try to find it
        t = _find_todo(target)
        if t:
            try:
                attachment = attach_to_todo(
                    t.source.path,
                    t.line_number,
                    file_path,
                    title=title,
                    copy=copy,
                )
                console.print(f"[green]Attached:[/green] {attachment.path}")
                console.print(f"[dim]To todo: {t.content[:50]}...[/dim]")
                return
            except FileNotFoundError as e:
                console.print(f"[red]{e}[/red]")
                raise SystemExit(1)
        # Fall through to try as note path
        note_path = config.notes_root / target
    else:
        note_path = config.notes_root / target

    if not note_path.suffix:
        note_path = note_path.with_suffix(".md")

    if not note_path.exists():
        console.print(f"[red]Note not found: {target}[/red]")
        raise SystemExit(1)

    try:
        attachment = attach_to_note(note_path, file_path, title=title, copy=copy)
        console.print(f"[green]Attached:[/green] {attachment.path}")
        console.print(f"[dim]To: {note_path.name}[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


@attach.command("url")
@click.argument("url")
@click.option("--to", "target", help="Note path or todo ID to attach to")
@click.option("--title", "-t", help="Display title for the URL")
def attach_url(url: str, target: str | None, title: str | None) -> None:
    """Attach a URL to a note or todo.

    By default attaches to today's daily note. Use --to to specify a target.

    Examples:
        nb attach url https://example.com/doc
        nb attach url https://github.com/repo --to projects/myproject.md
    """
    from nb.core.attachments import attach_to_note, attach_to_todo

    config = get_config()

    # Determine target (same logic as attach_file)
    if target is None:
        note_path = ensure_daily_note(date.today())
    elif len(target) >= 8 and "/" not in target and "\\" not in target:
        t = _find_todo(target)
        if t:
            try:
                attachment = attach_to_todo(
                    t.source.path,
                    t.line_number,
                    url,
                    title=title,
                    copy=False,
                )
                console.print(f"[green]Attached:[/green] {attachment.path}")
                console.print(f"[dim]To todo: {t.content[:50]}...[/dim]")
                return
            except Exception as e:
                console.print(f"[red]{e}[/red]")
                raise SystemExit(1)
        note_path = config.notes_root / target
    else:
        note_path = config.notes_root / target

    if not note_path.suffix:
        note_path = note_path.with_suffix(".md")

    if not note_path.exists():
        console.print(f"[red]Note not found: {target}[/red]")
        raise SystemExit(1)

    try:
        attachment = attach_to_note(note_path, url, title=title, copy=False)
        console.print(f"[green]Attached:[/green] {attachment.path}")
        console.print(f"[dim]To: {note_path.name}[/dim]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


@attach.command("list")
@click.argument("target", required=False)
def attach_list(target: str | None) -> None:
    """List attachments in a note.

    Shows all @attach lines in the specified note (or today's note by default).

    Examples:
        nb attach list
        nb attach list daily/2025-11-27.md
    """
    from nb.core.attachments import list_attachments_in_file, resolve_attachment_path
    from nb.models import Attachment

    config = get_config()

    if target is None:
        note_path = ensure_daily_note(date.today())
    else:
        note_path = config.notes_root / target
        if not note_path.suffix:
            note_path = note_path.with_suffix(".md")

    if not note_path.exists():
        console.print(f"[red]Note not found: {target}[/red]")
        raise SystemExit(1)

    attachments = list_attachments_in_file(note_path)

    if not attachments:
        console.print("[dim]No attachments found.[/dim]")
        return

    console.print(f"\n[bold]Attachments in {note_path.name}:[/bold]\n")

    for line_num, path in attachments:
        # Check if file exists
        from nb.core.attachments import is_url

        if is_url(path):
            status = "[cyan]url[/cyan]"
        else:
            # Create a temp attachment to resolve path
            temp = Attachment(id="", type="file", path=path)
            resolved = resolve_attachment_path(temp)
            if resolved:
                status = "[green]ok[/green]"
            else:
                status = "[red]missing[/red]"

        console.print(f"  {line_num:4d}: {path}  {status}")


@attach.command("open")
@click.argument("target")
@click.option("--line", "-l", type=int, help="Line number of the attachment")
def attach_open(target: str, line: int | None) -> None:
    """Open an attachment with the system default handler.

    TARGET can be a note path. Use --line to specify which attachment.

    Examples:
        nb attach open daily/2025-11-27.md --line 15
    """
    from nb.core.attachments import list_attachments_in_file, open_attachment
    from nb.models import Attachment

    config = get_config()
    note_path = config.notes_root / target
    if not note_path.suffix:
        note_path = note_path.with_suffix(".md")

    if not note_path.exists():
        console.print(f"[red]Note not found: {target}[/red]")
        raise SystemExit(1)

    attachments = list_attachments_in_file(note_path)

    if not attachments:
        console.print("[dim]No attachments in this note.[/dim]")
        return

    if line is None:
        if len(attachments) == 1:
            line = attachments[0][0]
        else:
            console.print(
                "[yellow]Multiple attachments found. Use --line to specify:[/yellow]"
            )
            for ln, path in attachments:
                console.print(f"  {ln:4d}: {path}")
            return

    # Find attachment at line
    found = None
    for ln, path in attachments:
        if ln == line:
            found = path
            break

    if found is None:
        console.print(f"[red]No attachment at line {line}[/red]")
        raise SystemExit(1)

    # Determine type and open
    from nb.core.attachments import is_url

    attachment = Attachment(
        id="",
        type="url" if is_url(found) else "file",
        path=found,
    )

    if open_attachment(attachment):
        console.print(f"[green]Opened:[/green] {found}")
    else:
        console.print(f"[red]Failed to open:[/red] {found}")
        raise SystemExit(1)


# =============================================================================
# Aliases
# =============================================================================


@main.command("td")
@click.pass_context
def todo_alias(ctx: click.Context) -> None:
    """Alias for 'todo' (list todos)."""
    index_all_notes(index_vectors=False)
    todos = get_sorted_todos(completed=False)
    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return
    _list_todos()


if __name__ == "__main__":
    main()
