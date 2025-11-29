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


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="nb")
@click.option(
    "-s", "--show", is_flag=True, help="Print note to console instead of opening editor"
)
@click.option("--notebook", "-n", help="Notebook for default today action")
@click.pass_context
def cli(ctx: click.Context, show: bool, notebook: str | None) -> None:
    """A plaintext-first note-taking and todo management CLI.

    Run 'nb' without arguments to open today's daily note.
    Use -s to print the note to console instead.
    Use -n to specify a notebook for the default action.
    """
    ensure_setup()
    ctx.ensure_object(dict)
    ctx.obj["show"] = show
    if ctx.invoked_subcommand is None:
        # Default action: open today's note
        ctx.invoke(today, notebook=notebook)


@cli.command()
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
    from nb.core.notebooks import ensure_notebook_note, is_notebook_date_based

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


@cli.command()
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


@cli.command("t")
@click.option("--notebook", "-n", help="Notebook to create today's note in")
@click.pass_context
def today_alias(ctx: click.Context, notebook: str | None) -> None:
    """Alias for 'today'."""
    ctx.invoke(today, notebook=notebook)


@cli.command("y")
@click.pass_context
def yesterday_alias(ctx: click.Context) -> None:
    """Alias for 'yesterday'."""
    ctx.invoke(yesterday)


@cli.command("last")
@click.option(
    "-s", "--show", is_flag=True, help="Print note to console instead of opening editor"
)
@click.option("--notebook", "-n", help="Filter by notebook")
@click.option("--viewed", is_flag=True, help="Use last viewed instead of last modified")
def last_note(show: bool, notebook: str | None, viewed: bool) -> None:
    """Open the most recently modified (or viewed) note.

    By default opens the last modified note. Use --viewed to open
    the last viewed note instead.

    \b
    Examples:
      nb last                # Open last modified note
      nb last -s             # Show last modified note (print to console)
      nb last -n work        # Last modified note in 'work' notebook
      nb last --viewed       # Last viewed note
      nb last --viewed -n daily  # Last viewed note in 'daily' notebook
    """
    from nb.core.notes import get_last_modified_note, get_last_viewed_note

    # Get the appropriate note
    if viewed:
        path = get_last_viewed_note(notebook=notebook)
        if not path:
            console.print("[dim]No viewed notes found.[/dim]")
            if notebook:
                console.print("[dim]Try without -n to search all notebooks.[/dim]")
            raise SystemExit(1)
    else:
        path = get_last_modified_note(notebook=notebook)
        if not path:
            console.print("[dim]No notes found.[/dim]")
            if notebook:
                console.print("[dim]Try 'nb index' to ensure notes are indexed.[/dim]")
            raise SystemExit(1)

    config = get_config()
    try:
        rel_path = path.relative_to(config.notes_root)
    except ValueError:
        rel_path = path

    if show:
        print_note(path)
    else:
        console.print(f"[dim]Opening {rel_path}...[/dim]")
        open_note(path)


@cli.command("l")
@click.option(
    "-s", "--show", is_flag=True, help="Print note to console instead of opening editor"
)
@click.option("--notebook", "-n", help="Filter by notebook")
@click.option("--viewed", is_flag=True, help="Use last viewed instead of last modified")
def last_alias(show: bool, notebook: str | None, viewed: bool) -> None:
    """Alias for 'last'."""
    from nb.core.notes import get_last_modified_note, get_last_viewed_note

    if viewed:
        path = get_last_viewed_note(notebook=notebook)
        if not path:
            console.print("[dim]No viewed notes found.[/dim]")
            raise SystemExit(1)
    else:
        path = get_last_modified_note(notebook=notebook)
        if not path:
            console.print("[dim]No notes found.[/dim]")
            raise SystemExit(1)

    config = get_config()
    try:
        rel_path = path.relative_to(config.notes_root)
    except ValueError:
        rel_path = path

    if show:
        print_note(path)
    else:
        console.print(f"[dim]Opening {rel_path}...[/dim]")
        open_note(path)


@cli.command("history")
@click.option("--limit", "-l", default=20, help="Number of entries to show")
@click.option("--notebook", "-n", help="Filter by notebook")
def history_cmd(limit: int, notebook: str | None) -> None:
    """Show recently viewed notes.

    Displays a list of notes you've recently opened, with timestamps.

    \b
    Examples:
      nb history             # Show last 20 viewed notes
      nb history -l 50       # Show last 50 viewed notes
      nb history -n work     # Show recently viewed notes in 'work' notebook
    """
    from nb.core.notes import get_recently_viewed_notes

    views = get_recently_viewed_notes(limit=limit, notebook=notebook)

    if not views:
        console.print("[dim]No view history found.[/dim]")
        return

    config = get_config()

    console.print("\n[bold]Recently Viewed Notes[/bold]\n")

    for path, viewed_at in views:
        try:
            rel_path = path.relative_to(config.notes_root)
        except ValueError:
            rel_path = path

        # Format the timestamp
        time_str = viewed_at.strftime("%Y-%m-%d %H:%M")
        console.print(f"  [dim]{time_str}[/dim]  {rel_path}")


@cli.command("open")
@click.argument("note_ref")
@click.option("--notebook", "-n", help="Notebook to open the note from")
@click.pass_context
def open_date(ctx: click.Context, note_ref: str, notebook: str | None) -> None:
    """Open a note by date or name.

    NOTE_REF can be:
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A note name (when used with -n for non-date-based notebooks)
    - A linked note alias (when used with -n for the linked note's notebook)
    - A path to a note file

    \b
    Examples:
      nb open friday              # Open Friday's daily note
      nb open "last monday"       # Open last Monday's note
      nb open myproject -n ideas  # Open ideas/myproject.md
      nb open friday -n work      # Open Friday in work notebook
      nb open mytodo -n nbcli     # Open linked note 'mytodo' in notebook 'nbcli'
    """
    from nb.core.links import get_linked_note_in_notebook
    from nb.core.notebooks import (
        ensure_notebook_note,
        get_notebook_note_path,
        is_notebook_date_based,
    )

    config = get_config()
    show = ctx.obj and ctx.obj.get("show")

    # If notebook is specified, handle it
    if notebook:
        # Check if note_ref matches a linked note alias in this notebook
        linked = get_linked_note_in_notebook(notebook, note_ref)
        if linked:
            # Found linked note by alias - open the linked file
            if show:
                print_note(linked.path)
            else:
                ln_notebook = linked.notebook or f"@{linked.alias}"
                console.print(f"[dim]Opening {ln_notebook}/{linked.alias}...[/dim]")
                open_note(linked.path)
            return

        # Check if it's a date-based notebook
        if is_notebook_date_based(notebook):
            # Try to parse as a date
            parsed = parse_fuzzy_date(note_ref)
            if parsed:
                note_path = ensure_notebook_note(notebook, dt=parsed)
                if show:
                    print_note(note_path)
                else:
                    try:
                        rel_path = note_path.relative_to(config.notes_root)
                    except ValueError:
                        rel_path = note_path
                    console.print(f"[dim]Opening {rel_path}...[/dim]")
                    open_note(note_path)
                return
            else:
                console.print(f"[red]Could not parse date: {note_ref}[/red]")
                raise SystemExit(1)
        else:
            # Non-date-based notebook: treat note_ref as a name
            try:
                note_path = get_notebook_note_path(notebook, name=note_ref)
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
                raise SystemExit(1)

            if not note_path.exists():
                console.print(f"[red]Note not found: {notebook}/{note_ref}[/red]")
                raise SystemExit(1)

            if show:
                print_note(note_path)
            else:
                try:
                    rel_path = note_path.relative_to(config.notes_root)
                except ValueError:
                    rel_path = note_path
                console.print(f"[dim]Opening {rel_path}...[/dim]")
                open_note(note_path)
            return

    # No notebook specified - use original behavior

    # First check if it's a path to an existing note
    path = Path(note_ref)
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
    parsed = parse_fuzzy_date(note_ref)
    if parsed:
        note_path = ensure_daily_note(parsed)
        if show:
            print_note(note_path)
        else:
            console.print(f"[dim]Opening {note_path.name}...[/dim]")
            open_note(note_path)
        return

    console.print(f"[red]Could not parse date: {note_ref}[/red]")
    raise SystemExit(1)


@cli.command("o")
@click.argument("note_ref")
@click.option("--notebook", "-n", help="Notebook to open the note from")
@click.pass_context
def open_alias(ctx: click.Context, note_ref: str, notebook: str | None) -> None:
    """Alias for 'open'."""
    ctx.invoke(open_date, note_ref=note_ref, notebook=notebook)


@cli.command("show")
@click.argument("note_ref", required=False)
@click.option("--notebook", "-n", help="Notebook to show the note from")
def show_note(note_ref: str | None, notebook: str | None) -> None:
    """Print a note to the console.

    NOTE_REF can be:
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A note name (when used with -n for non-date-based notebooks)
    - A linked note alias (when used with -n for the linked note's notebook)
    - A path to a note file
    - Omitted to show today's note

    \b
    Examples:
      nb show                     # Show today's daily note
      nb show friday              # Show Friday's daily note
      nb show -n work             # Show today's note in work notebook
      nb show friday -n work      # Show Friday in work notebook
      nb show myproject -n ideas  # Show ideas/myproject.md
      nb show mytodo -n nbcli     # Show linked note 'mytodo' in notebook 'nbcli'
    """
    from nb.core.links import get_linked_note_in_notebook
    from nb.core.notebooks import (
        ensure_notebook_note,
        get_notebook_note_path,
        is_notebook_date_based,
    )

    config = get_config()

    # If no note_ref provided, default to today
    if note_ref is None:
        note_ref = "today"

    # Handle "today" specially
    if note_ref.lower() == "today":
        dt = date.today()
        if notebook:
            if is_notebook_date_based(notebook):
                note_path = ensure_notebook_note(notebook, dt=dt)
            else:
                # For non-date-based, use today's date as name
                note_path = ensure_notebook_note(notebook, name=dt.isoformat())
        else:
            note_path = ensure_daily_note(dt)
        print_note(note_path)
        return

    # If notebook is specified, handle it
    if notebook:
        # Check if note_ref matches a linked note alias in this notebook
        linked = get_linked_note_in_notebook(notebook, note_ref)
        if linked:
            # Found linked note by alias - show the linked file
            print_note(linked.path)
            return

        if is_notebook_date_based(notebook):
            # Try to parse as a date
            parsed = parse_fuzzy_date(note_ref)
            if parsed:
                note_path = ensure_notebook_note(notebook, dt=parsed)
                print_note(note_path)
                return
            else:
                console.print(f"[red]Could not parse date: {note_ref}[/red]")
                raise SystemExit(1)
        else:
            # Non-date-based notebook: treat note_ref as a name
            try:
                note_path = get_notebook_note_path(notebook, name=note_ref)
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
                raise SystemExit(1)

            if not note_path.exists():
                console.print(f"[red]Note not found: {notebook}/{note_ref}[/red]")
                raise SystemExit(1)

            print_note(note_path)
            return

    # No notebook specified - check if it's a path or parse as date

    # First check if it's a path to an existing note
    path = Path(note_ref)
    if not path.suffix:
        path = path.with_suffix(".md")

    full_path = config.notes_root / path
    if full_path.exists():
        print_note(full_path)
        return

    # Try to parse as a date
    parsed = parse_fuzzy_date(note_ref)
    if parsed:
        note_path = ensure_daily_note(parsed)
        print_note(note_path)
        return

    console.print(f"[red]Could not parse date: {note_ref}[/red]")
    raise SystemExit(1)


@cli.command("new")
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
    from nb.core.notebooks import ensure_notebook_note, is_notebook_date_based

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


@cli.command("edit")
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


@cli.group("notebooks", invoke_without_command=True)
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


@cli.command("nbs")
@click.pass_context
def notebooks_alias(ctx: click.Context) -> None:
    """Alias for 'notebooks'."""
    ctx.invoke(notebooks_cmd)


@cli.group("config", invoke_without_command=True)
@click.pass_context
def config_cmd(ctx: click.Context) -> None:
    """Manage configuration settings.

    When called without a subcommand, opens the config file in the editor.

    \b
    Subcommands:
      get <key>           Get a configuration value
      set <key> <value>   Set a configuration value
      list                List all configurable settings

    \b
    Examples:
      nb config              # Open config file in editor
      nb config get editor   # Show current editor setting
      nb config set editor code  # Set editor to 'code'
      nb config list         # Show all configurable settings
    """
    if ctx.invoked_subcommand is None:
        # Default: open config file in editor
        config = get_config()

        # Ensure config exists
        if not config.config_path.exists():
            init_config(config.notes_root)

        console.print(f"[dim]Opening {config.config_path}...[/dim]")
        open_in_editor(config.config_path, editor=config.editor)


@config_cmd.command("get")
@click.argument("key")
def config_get(key: str) -> None:
    """Get a configuration value.

    \b
    Available keys:
      editor                Text editor command
      date_format           Date display format
      time_format           Time display format
      embeddings.provider   Embeddings provider
      embeddings.model      Embeddings model
      embeddings.base_url   Custom API endpoint
      embeddings.api_key    API key
    """
    from nb.config import get_config_value

    value = get_config_value(key)
    if value is None:
        console.print(f"[red]Unknown setting:[/red] {key}")
        console.print("[dim]Use 'nb config list' to see available settings.[/dim]")
        raise SystemExit(1)

    console.print(f"{key} = {value}")


@config_cmd.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    \b
    Available keys:
      editor                Text editor command
      date_format           Date display format
      time_format           Time display format
      embeddings.provider   Embeddings provider
      embeddings.model      Embeddings model
      embeddings.base_url   Custom API endpoint
      embeddings.api_key    API key
    """
    from nb.config import set_config_value

    if set_config_value(key, value):
        console.print(f"[green]Set[/green] {key} = {value}")
    else:
        console.print(f"[red]Unknown setting:[/red] {key}")
        console.print("[dim]Use 'nb config list' to see available settings.[/dim]")
        raise SystemExit(1)


@config_cmd.command("list")
def config_list() -> None:
    """List all configurable settings."""
    from nb.config import list_config_settings

    settings = list_config_settings()

    console.print("\n[bold]Configurable Settings[/bold]\n")
    for key, (description, value) in settings.items():
        value_str = str(value) if value is not None else "[dim]<not set>[/dim]"
        console.print(f"  [cyan]{key}[/cyan]")
        console.print(f"    {description}")
        console.print(f"    Current: {value_str}")
        console.print()


@cli.command("add")
@click.argument("text")
def add_to_today(text: str) -> None:
    """Append a line to today's note."""
    dt = date.today()
    path = ensure_daily_note(dt)

    # Append the text
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{text}\n")

    console.print(f"[green]Added to {path.name}[/green]")


@cli.command("list")
@click.option("--notebook", "-n", help="Filter by notebook")
@click.option("--week", is_flag=True, help="Show this week's daily notes")
@click.option("--month", is_flag=True, help="Show this month's daily notes")
def list_notes_cmd(notebook: str | None, week: bool, month: bool) -> None:
    """List notes."""
    from nb.core.notebooks import get_notebook_notes_with_linked

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
        notes = get_notebook_notes_with_linked(notebook)

        if not notes:
            console.print(f"[dim]No notes in {notebook}.[/dim]")
            return

        for note_path, is_linked, alias in notes:
            if is_linked:
                if alias:
                    console.print(f"[cyan]{alias}[/cyan] [dim]({note_path})[/dim]")
                else:
                    console.print(f"[cyan]{note_path}[/cyan] [dim](linked)[/dim]")
            else:
                console.print(str(note_path))
    else:
        # List all notebooks with counts (including linked notebooks)
        from nb.core.links import list_linked_notes

        nbs = list_notebooks()
        for nb in nbs:
            notes = get_notebook_notes(nb)
            console.print(f"{nb}: {len(notes)} notes")

        # Also list linked note notebooks
        linked_notes = list_linked_notes()
        linked_notebooks: dict[str, int] = {}
        for ln in linked_notes:
            notebook_name = ln.notebook or f"@{ln.alias}"
            from nb.core.links import scan_linked_note_files

            files = scan_linked_note_files(ln)
            linked_notebooks[notebook_name] = len(files)

        for nb_name, count in sorted(linked_notebooks.items()):
            console.print(f"[cyan]{nb_name}[/cyan]: {count} notes [dim](linked)[/dim]")


# =============================================================================
# Todo Commands
# =============================================================================


@cli.group(invoke_without_command=True)
@click.option("--created-today", is_flag=True, help="Show only todos created today")
@click.option("--created-week", is_flag=True, help="Show only todos created this week")
@click.option("--due-today", is_flag=True, help="Show only todos due today")
@click.option("--due-week", is_flag=True, help="Show only todos due this week")
@click.option("--overdue", is_flag=True, help="Show only overdue todos")
@click.option("--priority", "-p", type=int, help="Filter by priority (1, 2, or 3)")
@click.option("--tag", "-t", help="Filter by tag")
@click.option(
    "--exclude-tag",
    "-T",
    multiple=True,
    help="Exclude todos with this tag (can be used multiple times)",
)
@click.option("--notebook", "-n", help="Filter by notebook (overrides exclusions)")
@click.option(
    "--exclude-notebook",
    "-N",
    multiple=True,
    help="Exclude todos from this notebook (can be used multiple times)",
)
@click.option("--hide-later", is_flag=True, help="Hide todos due later than next week")
@click.option("--hide-no-date", is_flag=True, help="Hide todos with no due date")
@click.option(
    "--focus",
    "-f",
    is_flag=True,
    help="Focus mode: show only overdue, today, this week, and next week",
)
@click.option(
    "--sort-by",
    "-s",
    type=click.Choice(["source", "tag", "priority", "created"]),
    default="source",
    help="Sort todos within groups",
)
@click.option(
    "--all",
    "-a",
    "show_all",
    is_flag=True,
    help="Include todos from all sources (even excluded notebooks)",
)
@click.option("--include-completed", "-c", is_flag=True, help="Include completed todos")
@click.option("-i", "--interactive", is_flag=True, help="Open interactive todo viewer")
@click.pass_context
def todo(
    ctx: click.Context,
    created_today: bool,
    created_week: bool,
    due_today: bool,
    due_week: bool,
    overdue: bool,
    priority: int | None,
    tag: str | None,
    exclude_tag: tuple[str, ...],
    notebook: str | None,
    exclude_notebook: tuple[str, ...],
    hide_later: bool,
    hide_no_date: bool,
    focus: bool,
    sort_by: str,
    show_all: bool,
    include_completed: bool,
    interactive: bool,
) -> None:
    """Manage todos.

    Run 'nb todo' without a subcommand to list todos grouped by due date:
    OVERDUE, DUE TODAY, DUE THIS WEEK, DUE NEXT WEEK, DUE LATER, NO DUE DATE.

    \b
    Examples:
      nb todo                 List all open todos
      nb todo -f              Focus mode (hide later/no-date sections)
      nb todo -t work         Show only todos tagged #work
      nb todo -T waiting      Exclude todos tagged #waiting
      nb todo -p 1            Show only high priority todos
      nb todo -n daily        Show todos from 'daily' notebook only
      nb todo -a              Include todos from excluded notebooks
      nb todo -c              Include completed todos
      nb todo -s tag          Sort by tag instead of source
      nb todo --due-today     Show only todos due today
      nb todo --created-week  Show only todos created this week

    \b
    Date Filters:
      --created-today   Show todos created today
      --created-week    Show todos created this week
      --due-today       Show todos due today
      --due-week        Show todos due this week
      --overdue         Show only overdue todos

    \b
    Source Filters:
      -t, --tag TAG             Include only todos with this tag
      -T, --exclude-tag TAG     Exclude todos with this tag (repeatable)
      -n, --notebook NAME       Show only todos from this notebook
      -N, --exclude-notebook    Exclude todos from this notebook (repeatable)
      -p, --priority N          Filter by priority (1=high, 2=medium, 3=low)

    \b
    Display Filters:
      --hide-later      Hide the "DUE LATER" section
      --hide-no-date    Hide the "NO DUE DATE" section
      -f, --focus       Focus mode: hide both later and no-date sections

    \b
    Output Options:
      -s, --sort-by     Sort within groups: source (default), tag, priority, created
      -a, --all         Include all sources (even excluded notebooks)
      -c, --include-completed   Include completed todos
      -i, --interactive         Launch interactive TUI viewer

    Notebooks with todo_exclude: true in config are hidden by default.
    Notes with todo_exclude: true in frontmatter are also hidden.
    Use -a/--all to include them, or -n <notebook> to view one explicitly.
    """
    if ctx.invoked_subcommand is None:
        # Ensure todos are indexed (skip vector indexing for speed)
        index_all_notes(index_vectors=False)

        # Get excluded notebooks from config (unless --all or specific notebook is requested)
        config = get_config()
        all_excluded_notebooks: list[str] | None = None
        if not show_all and not notebook:
            config_excluded = config.excluded_notebooks() or []
            # Merge config exclusions with CLI exclusions
            all_excluded_notebooks = list(set(config_excluded) | set(exclude_notebook))
            if not all_excluded_notebooks:
                all_excluded_notebooks = None

        # Convert exclude_tag tuple to list (or None)
        exclude_tags = list(exclude_tag) if exclude_tag else None

        # Handle --focus flag (enables both --hide-later and --hide-no-date)
        effective_hide_later = hide_later or focus
        effective_hide_no_date = hide_no_date or focus

        if interactive:
            # Launch interactive viewer
            from nb.tui.todos import run_interactive_todos

            run_interactive_todos(
                show_completed=include_completed,
                tag=tag,
                notebook=notebook,
                exclude_notebooks=all_excluded_notebooks,
            )
        else:
            # Determine if we should exclude notes with todo_exclude
            # Don't exclude when --all or specific notebook is requested
            exclude_note_excluded = not show_all and not notebook

            # Default: list todos
            _list_todos(
                created_today=created_today,
                created_week=created_week,
                due_today=due_today,
                due_week=due_week,
                overdue=overdue,
                priority=priority,
                tag=tag,
                exclude_tags=exclude_tags,
                notebook=notebook,
                exclude_notebooks=all_excluded_notebooks,
                hide_later=effective_hide_later,
                hide_no_date=effective_hide_no_date,
                sort_by=sort_by,
                include_completed=include_completed,
                exclude_note_excluded=exclude_note_excluded,
            )


def _list_todos(
    created_today: bool = False,
    created_week: bool = False,
    due_today: bool = False,
    due_week: bool = False,
    overdue: bool = False,
    priority: int | None = None,
    tag: str | None = None,
    exclude_tags: list[str] | None = None,
    notebook: str | None = None,
    exclude_notebooks: list[str] | None = None,
    hide_later: bool = False,
    hide_no_date: bool = False,
    sort_by: str = "source",
    include_completed: bool = False,
    exclude_note_excluded: bool = True,
) -> None:
    """List todos with optional filters."""
    from datetime import timedelta

    # Determine completion filter
    completed = None if include_completed else False

    # Calculate date ranges for filters
    today_date = date.today()
    week_start, week_end = get_week_range()

    # Build query parameters based on filters
    due_start: date | None = None
    due_end: date | None = None
    created_start: date | None = None
    created_end: date | None = None

    if created_today:
        created_start = today_date
        created_end = today_date
    elif created_week:
        created_start = week_start
        created_end = week_end

    if due_today:
        due_start = today_date
        due_end = today_date
    elif due_week:
        due_start = week_start
        due_end = week_end

    if overdue:
        todos = query_todos(
            completed=completed,
            overdue=True,
            priority=priority,
            tag=tag,
            exclude_tags=exclude_tags,
            notebook=notebook,
            exclude_notebooks=exclude_notebooks,
            created_start=created_start,
            created_end=created_end,
            exclude_note_excluded=exclude_note_excluded,
        )
    else:
        todos = get_sorted_todos(
            completed=completed,
            priority=priority,
            tag=tag,
            exclude_tags=exclude_tags,
            notebook=notebook,
            exclude_notebooks=exclude_notebooks,
            due_start=due_start,
            due_end=due_end,
            created_start=created_start,
            created_end=created_end,
            exclude_note_excluded=exclude_note_excluded,
        )

    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return

    # Calculate next week range
    # next_week_start = week_end + timedelta(days=1)
    next_week_end = week_end + timedelta(days=7)

    # Group todos for display
    groups: dict[str, list] = {
        "OVERDUE": [],
        "DUE TODAY": [],
        "DUE THIS WEEK": [],
        "DUE NEXT WEEK": [],
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
        elif t.due_date <= next_week_end:
            groups["DUE NEXT WEEK"].append(t)
        else:
            groups["DUE LATER"].append(t)

    # Apply hide filters
    if hide_later:
        groups["DUE LATER"] = []
    if hide_no_date:
        groups["NO DUE DATE"] = []

    # Sort todos within each group
    def get_sort_key(todo):
        if sort_by == "tag":
            return (todo.tags[0].lower() if todo.tags else "zzz", todo.content.lower())
        elif sort_by == "priority":
            # Priority 1 is highest, None is lowest
            prio = todo.priority.value if todo.priority else 999
            return (prio, todo.content.lower())
        elif sort_by == "created":
            return (todo.created_date or date.min, todo.content.lower())
        else:  # source (default)
            source_str = _format_todo_source(todo)
            return (source_str.lower(), todo.content.lower())

    for group_todos in groups.values():
        group_todos.sort(key=get_sort_key)

    # Collect all visible todos for column width calculation
    all_visible_todos = []
    for group_todos in groups.values():
        all_visible_todos.extend(group_todos)

    if not all_visible_todos:
        console.print("[dim]No todos found.[/dim]")
        return

    # Calculate column widths for alignment
    widths = _calculate_column_widths(all_visible_todos)

    # Display
    for group_name, group_todos in groups.items():
        if not group_todos:
            continue

        console.print(f"\n[bold]{group_name}[/bold]")

        for t in group_todos:
            _print_todo(t, indent=0, widths=widths)


def _calculate_column_widths(todos: list) -> dict[str, int]:
    """Calculate column widths for aligned todo output."""
    widths = {
        "content": 0,
        "source": 0,
        "created": 5,  # Fixed: "+MM/DD"
        "due": 6,  # Fixed: "Mon DD"
        "priority": 2,  # Fixed: "!N"
    }

    for t in todos:
        widths["content"] = max(widths["content"], len(t.content))
        source_str = _format_todo_source(t)
        widths["source"] = max(widths["source"], len(source_str))

    # Cap content width to avoid very long lines
    widths["content"] = min(widths["content"], 60)

    return widths


def _format_todo_source(t) -> str:
    """Format the source of a todo for display (plain text, used for sorting).

    Format: notebook/note_title::Section (if section exists)
            notebook/note_title (if no section)
    """
    parts = _get_todo_source_parts(t)
    if not parts["notebook"] and not parts["note"]:
        return ""

    base_source = ""
    if parts["notebook"] and parts["note"]:
        base_source = f"{parts['notebook']}/{parts['note']}"
    elif parts["notebook"]:
        base_source = parts["notebook"]
    elif parts["note"]:
        base_source = parts["note"]

    if parts["section"]:
        return f"{base_source}::{parts['section']}"
    return base_source


def _get_todo_source_parts(t) -> dict[str, str]:
    """Extract source parts (notebook, note, section) from a todo.

    Returns a dict with keys: notebook, note, section (all may be empty strings).
    """
    result = {"notebook": "", "note": "", "section": t.section or ""}

    if not t.source:
        return result

    if t.source.alias:
        # Linked file - show notebook/alias (look up from linked notes)
        from nb.core.links import get_linked_note

        linked = get_linked_note(t.source.alias)
        if linked:
            result["notebook"] = linked.notebook or f"@{linked.alias}"
            # For single files, just show alias
            # For directories, show filename
            if linked.path.is_file():
                result["note"] = linked.alias
            else:
                # Show relative_path_stem
                try:
                    rel = t.source.path.relative_to(linked.path)
                    result["note"] = rel.stem
                except ValueError:
                    result["note"] = t.source.path.stem
        else:
            result["notebook"] = f"@{t.source.alias}"
    elif t.source.type == "inbox":
        result["notebook"] = "inbox"
    else:
        # Regular note - show notebook/filename
        config = get_config()
        try:
            rel_path = t.source.path.relative_to(config.notes_root)
            if len(rel_path.parts) > 1:
                result["notebook"] = rel_path.parts[0]
                result["note"] = rel_path.stem
            else:
                result["note"] = rel_path.stem
        except ValueError:
            result["note"] = t.source.path.stem

    return result


def _format_colored_todo_source(t, width: int = 0) -> str:
    """Format the source of a todo with colors for display.

    Colors: notebook=magenta, note=blue, section=cyan

    Args:
        t: Todo object
        width: Minimum width for padding (0 = no padding)

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    # Build colored source string
    colored_parts = []

    if parts["notebook"]:
        colored_parts.append(f"[magenta]{parts['notebook']}[/magenta]")

    if parts["note"]:
        if colored_parts:
            colored_parts.append("/")
        colored_parts.append(f"[blue]{parts['note']}[/blue]")

    if parts["section"]:
        colored_parts.append("::")
        colored_parts.append(f"[cyan]{parts['section']}[/cyan]")

    colored = "".join(colored_parts)

    # Calculate plain length for padding
    if width > 0:
        plain_len = len(_format_todo_source(t))
        if plain_len < width:
            colored += " " * (width - plain_len)

    return colored


def _print_todo(t, indent: int = 0, widths: dict[str, int] | None = None) -> None:
    """Print a single todo with formatting."""
    prefix = "  " * indent
    checkbox = "[green]x[/green]" if t.completed else "[dim]o[/dim]"

    # Build content - truncate if needed for alignment
    content = t.content
    content_width = widths["content"] if widths else len(content)
    if len(content) > content_width:
        content_display = content[: content_width - 1] + "…"
    else:
        content_display = content.ljust(content_width)

    # Build source column (colored)
    source_str = _format_todo_source(t)
    source_width = widths["source"] if widths else len(source_str)

    # Build metadata columns with fixed widths
    created_str = ""
    if t.created_date:
        created_str = f"+{t.created_date.strftime('%m/%d')}"

    due_str = ""
    due_color = "red"
    if t.due_date:
        due_str = t.due_date.strftime("%b %d")

    priority_str = ""
    if t.priority:
        priority_str = f"!{t.priority.value}"

    tags_str = ""
    if t.tags:
        tags_str = " ".join(f"#{tag}" for tag in t.tags[:3])

    # Build the formatted line with alignment
    short_id = t.id[:6]

    # Format with Rich markup and padding
    if t.completed:
        content_part = f"[strikethrough]{content_display}[/strikethrough]"
    else:
        content_part = content_display

    source_part = (
        _format_colored_todo_source(t, source_width)
        if source_str
        else " " * source_width
    )
    created_part = f"[dim]{created_str:>6}[/dim]" if created_str else " " * 6
    due_part = f"[{due_color}]{due_str:>6}[/{due_color}]" if due_str else " " * 6
    priority_part = f"[magenta]{priority_str:>2}[/magenta]" if priority_str else "  "
    tags_part = f"  [cyan]{tags_str}[/cyan]" if tags_str else ""

    console.print(
        f"{prefix}{checkbox} {content_part}  {source_part}  {created_part}  {due_part}  {priority_part}  [dim]{short_id}[/dim]{tags_part}"
    )

    # Print children
    children = get_todo_children(t.id)
    for child in children:
        _print_todo(child, indent=indent + 1, widths=widths)


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

    TEXT can include inline metadata:

    \b
      @due(DATE)      Set due date (today, tomorrow, friday, 2024-12-25)
      @priority(N)    Set priority (1=high, 2=medium, 3=low)
      #tag            Add tags

    \b
    Examples:
      nb todo add "Review PR"
      nb todo add "Review PR @due(friday) #work"
      nb todo add "Urgent task @priority(1) @due(today)"
      nb todo add --today "Call dentist"
    """
    if add_today:
        t = add_todo_to_daily_note(text)
        console.print(f"[green]Added to today's note:[/green] {t.content}")
    else:
        t = add_todo_to_inbox(text)
        console.print(f"[green]Added to inbox:[/green] {t.content}")
    console.print(f"[dim]ID: {t.id[:6]}[/dim]")


@cli.command("ta")
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

    TODO_ID can be the full ID or just the first few characters.
    The 6-character ID shown in 'nb todo' output is usually sufficient.

    \b
    Examples:
      nb todo done abc123
      nb todo done abc123def456...
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
    """Mark a todo as incomplete (reopen it).

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo undone abc123
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
    """Show detailed information about a todo.

    Displays the todo's content, status, source file, due date,
    priority, tags, project, and any subtasks.

    \b
    Examples:
      nb todo show abc123
    """
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
    if t.notebook:
        console.print(f"Notebook: {t.notebook}")

    if t.details:
        console.print("\n[bold]Details:[/bold]")
        console.print(f"[dim]{t.details}[/dim]")

    children = get_todo_children(t.id)
    if children:
        console.print("\n[bold]Subtasks:[/bold]")
        for child in children:
            checkbox = "x" if child.completed else "o"
            console.print(f"  {checkbox} {child.content}")


@todo.command("edit")
@click.argument("todo_id")
def todo_edit(todo_id: str) -> None:
    """Open the source file at the todo's line in your editor.

    Opens the markdown file containing the todo, jumping directly
    to the line where the todo is defined.

    \b
    Examples:
      nb todo edit abc123
    """
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


@cli.command("search")
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


@cli.command("s")
@click.argument("query")
@click.pass_context
def search_alias(ctx: click.Context, query: str) -> None:
    """Alias for 'search' (hybrid search)."""
    ctx.invoke(search_cmd, query=query)


@cli.command("ss")
@click.argument("query")
@click.pass_context
def semantic_search_alias(ctx: click.Context, query: str) -> None:
    """Alias for 'search --semantic'."""
    ctx.invoke(search_cmd, query=query, semantic=True)


@cli.command("grep")
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


@cli.command("index")
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


@cli.command("stream")
@click.option("--notebook", "-n", help="Filter by notebook")
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
    j/k or ↑/↓     - Scroll within note
    ←/→ or PgUp/Dn - Previous/next note
    n/N or p       - Next/previous note
    g/G            - First/last note (or top/bottom of current)
    d/u            - Half-page down/up
    e              - Edit current note
    q              - Quit

    Examples:
    \b
      nb stream                      # Stream all notes
      nb stream -n daily             # Stream daily notes
      nb stream -w "last week"       # Last week's notes
      nb stream -w "this week"       # This week's notes
      nb stream -n daily -w "last 2 weeks"  # Daily notes from last 2 weeks

    """
    from datetime import date as date_type

    from nb.index.db import get_db
    from nb.models import Note
    from nb.tui.stream import run_note_stream
    from nb.utils.dates import parse_date_range, parse_fuzzy_date

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


@cli.group()
def link() -> None:
    """Manage linked external files.

    Link external markdown files or directories to index them
    alongside your notes. Both todos and note content are indexed.
    """
    pass


@link.command("list")
def link_list() -> None:
    """List all linked external files.

    Shows alias, notebook, path, sync status, and todo exclusion status.
    """
    from nb.core.links import list_linked_notes

    linked_notes = list_linked_notes()

    if not linked_notes:
        console.print("[dim]No linked files.[/dim]")
        console.print("[dim]Use 'nb link add <path>' to add one.[/dim]")
        return

    table = Table(show_header=True, title="Linked Notes")
    table.add_column("Alias")
    table.add_column("Notebook")
    table.add_column("Path")
    table.add_column("Sync")
    table.add_column("Todo Excl")
    table.add_column("Exists")

    for ln in linked_notes:
        exists = "[green]yes[/green]" if ln.path.exists() else "[red]no[/red]"
        sync = "[green]yes[/green]" if ln.sync else "[dim]no[/dim]"
        todo_excl = "[yellow]yes[/yellow]" if ln.todo_exclude else "[dim]no[/dim]"
        notebook = ln.notebook or f"@{ln.alias}"
        path_str = str(ln.path)
        if ln.path.is_dir():
            path_str += "/" if ln.recursive else " (flat)"
        table.add_row(ln.alias, notebook, path_str, sync, todo_excl, exists)

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
@click.option(
    "--todo-exclude",
    is_flag=True,
    help="Exclude todos from 'nb todo' unless explicitly requested",
)
def link_add(
    path: str,
    alias: str | None,
    sync: bool,
    notebook: str | None,
    no_recursive: bool,
    todo_exclude: bool,
) -> None:
    """Link an external file or directory.

    Linked notes are indexed like regular notes - both note content and todos
    are collected. Linked notes appear in 'nb list -n <notebook>' with the
    specified notebook name (defaults to @alias).

    With --sync (default), completing a todo will update the source file.
    With --todo-exclude, todos won't appear in 'nb todo' unless you filter
    by the notebook explicitly with -n.

    Examples:
        nb link add ~/work/TODO.md              # Link with todos visible
        nb link add ~/docs/wiki                 # Link a directory of notes
        nb link add ~/project/tasks.md --todo-exclude  # Hide from nb todo
        nb link add ~/docs --no-sync            # Don't sync completions back

    """
    from nb.core.links import add_linked_note
    from nb.index.scanner import index_single_linked_note

    p = Path(path)

    try:
        linked = add_linked_note(
            p,
            alias=alias,
            notebook=notebook,
            recursive=not no_recursive,
            todo_exclude=todo_exclude,
            sync=sync,
            save_to_config=False,
        )
        note_count = index_single_linked_note(linked.alias)

        console.print(f"[green]Linked:[/green] {linked.alias}")
        console.print(f"[dim]Notebook: {linked.notebook}[/dim]")
        console.print(f"[dim]Indexed {note_count} notes.[/dim]")
        if todo_exclude:
            console.print("[dim]Todos excluded from 'nb todo' by default.[/dim]")
        if not sync:
            console.print("[dim]Sync disabled - completions won't update source.[/dim]")

    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


@link.command("remove")
@click.argument("alias")
def link_remove(alias: str) -> None:
    """Stop tracking a linked external file.

    This does not delete the file, just removes it from tracking.
    """
    from nb.core.links import get_linked_note, remove_linked_note
    from nb.index.scanner import remove_linked_note_from_index

    linked_note = get_linked_note(alias)
    if linked_note:
        remove_linked_note_from_index(alias)
        remove_linked_note(alias)
        console.print(f"[green]Removed link:[/green] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("sync")
@click.argument("alias", required=False)
def link_sync(alias: str | None) -> None:
    """Re-scan linked files and update index.

    If ALIAS is provided, only that linked note is scanned.
    Otherwise, all linked notes are scanned.
    """
    from nb.core.links import get_linked_note, list_linked_notes
    from nb.index.scanner import index_single_linked_note, scan_linked_notes

    if alias:
        linked_note = get_linked_note(alias)
        if linked_note:
            if not linked_note.path.exists():
                console.print(f"[red]Path does not exist: {linked_note.path}[/red]")
                raise SystemExit(1)
            note_count = index_single_linked_note(alias)
            console.print(f"[green]Synced:[/green] {note_count} notes")
        else:
            console.print(f"[red]Linked file not found: {alias}[/red]")
            raise SystemExit(1)
    else:
        note_total = scan_linked_notes()
        link_count = len(list_linked_notes())
        console.print(f"[green]Synced:[/green] {link_count} links ({note_total} notes)")


@link.command("enable-sync")
@click.argument("alias")
def link_enable_sync(alias: str) -> None:
    """Enable syncing completions back to a linked file."""
    from nb.core.links import update_linked_note_sync

    if update_linked_note_sync(alias, True):
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
    from nb.core.links import update_linked_note_sync

    if update_linked_note_sync(alias, False):
        console.print(f"[yellow]Disabled sync for:[/yellow] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("exclude-todos")
@click.argument("alias")
def link_exclude_todos(alias: str) -> None:
    """Exclude todos from this linked note from 'nb todo'.

    Todos will still be indexed, but won't appear in 'nb todo' unless
    you explicitly filter by this notebook with -n.
    """
    from nb.core.links import update_linked_note_todo_exclude

    if update_linked_note_todo_exclude(alias, True):
        console.print(f"[yellow]Excluded todos for:[/yellow] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("include-todos")
@click.argument("alias")
def link_include_todos(alias: str) -> None:
    """Include todos from this linked note in 'nb todo'."""
    from nb.core.links import update_linked_note_todo_exclude

    if update_linked_note_todo_exclude(alias, False):
        console.print(f"[green]Included todos for:[/green] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


# =============================================================================
# Attach Commands
# =============================================================================


@cli.group()
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


@cli.command("td")
@click.pass_context
def todo_alias(ctx: click.Context) -> None:
    """Alias for 'todo' (list todos)."""
    index_all_notes(index_vectors=False)
    todos = get_sorted_todos(completed=False)
    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return
    _list_todos()


# =============================================================================
# Shell Completion
# =============================================================================


def _get_powershell_source() -> str:
    """Generate PowerShell completion script for nb."""
    return """\
Register-ArgumentCompleter -Native -CommandName nb -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $env:_NB_COMPLETE = "powershell_complete"
    $env:_NB_COMPLETE_ARGS = $commandAst.ToString()
    $env:_NB_COMPLETE_WORD = $wordToComplete
    nb | ForEach-Object {
        $type, $value, $help = $_ -split "`t", 3
        [System.Management.Automation.CompletionResult]::new(
            $value,
            $value,
            $(if ($type -eq "dir") { "ParameterValue" } elseif ($type -eq "file") { "ParameterValue" } else { "ParameterValue" }),
            $(if ($help) { $help } else { $value })
        )
    }
    Remove-Item Env:_NB_COMPLETE
    Remove-Item Env:_NB_COMPLETE_ARGS
    Remove-Item Env:_NB_COMPLETE_WORD
}
"""


def _handle_powershell_completion() -> bool:
    """Handle PowerShell completion if requested via env var. Returns True if handled."""
    import os
    import shlex

    complete_var = os.environ.get("_NB_COMPLETE")
    if complete_var != "powershell_complete":
        return False

    args_str = os.environ.get("_NB_COMPLETE_ARGS", "")
    word = os.environ.get("_NB_COMPLETE_WORD", "")

    # Parse the command line
    try:
        # Remove the 'nb' command name
        parts = shlex.split(args_str)
        if parts and parts[0] == "nb":
            parts = parts[1:]
    except ValueError:
        parts = []

    # Use click's completion mechanism
    from click.shell_completion import ShellComplete

    comp = ShellComplete(cli, {}, "nb", "_NB_COMPLETE")
    completions = comp.get_completions(parts, word)

    for item in completions:
        # Output format: type\tvalue\thelp
        help_text = item.help or ""
        click.echo(f"{item.type}\t{item.value}\t{help_text}")

    return True


@cli.command("completion")
@click.option(
    "--shell",
    "-s",
    type=click.Choice(["powershell", "bash", "zsh", "fish"]),
    default="powershell",
    help="Shell to generate completion for",
)
def completion_cmd(shell: str) -> None:
    """Generate shell completion script.

    \b
    For PowerShell, add this to your $PROFILE:
        nb completion | Out-String | Invoke-Expression

    \b
    Or save to a file and source it:
        nb completion > ~/.nb-completion.ps1
        . ~/.nb-completion.ps1

    \b
    For Bash, add to ~/.bashrc:
        eval "$(nb completion -s bash)"

    \b
    For Zsh, add to ~/.zshrc:
        eval "$(nb completion -s zsh)"

    \b
    For Fish, add to ~/.config/fish/completions/nb.fish:
        nb completion -s fish > ~/.config/fish/completions/nb.fish
    """
    import click.shell_completion as shell_completion

    if shell == "powershell":
        click.echo(_get_powershell_source())
    else:
        shell_map = {
            "bash": shell_completion.BashComplete,
            "zsh": shell_completion.ZshComplete,
            "fish": shell_completion.FishComplete,
        }
        cls = shell_map[shell]
        comp = cls(cli, {}, "nb", "_NB_COMPLETE")
        click.echo(comp.source())


def main() -> None:
    """Entry point for the CLI."""
    if not _handle_powershell_completion():
        cli()


if __name__ == "__main__":
    main()
