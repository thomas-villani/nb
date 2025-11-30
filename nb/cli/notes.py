"""Note-related CLI commands."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import click

from nb.cli.utils import console, get_notebook_display_info, print_note
from nb.config import get_config
from nb.core.notes import (
    create_note,
    ensure_daily_note,
    list_daily_notes,
    open_note,
)
from nb.utils.dates import parse_fuzzy_date


def register_note_commands(cli: click.Group) -> None:
    """Register all note-related commands with the CLI."""
    cli.add_command(today)
    cli.add_command(yesterday)
    cli.add_command(today_alias)
    cli.add_command(yesterday_alias)
    cli.add_command(last_note)
    cli.add_command(last_alias)
    cli.add_command(history_cmd)
    cli.add_command(open_date)
    cli.add_command(open_alias)
    cli.add_command(show_note)
    cli.add_command(new_note)
    cli.add_command(edit_note)
    cli.add_command(add_to_today)
    cli.add_command(list_notes_cmd)


@click.command()
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


@click.command()
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


@click.command("t")
@click.option("--notebook", "-n", help="Notebook to create today's note in")
@click.pass_context
def today_alias(ctx: click.Context, notebook: str | None) -> None:
    """Alias for 'today'."""
    ctx.invoke(today, notebook=notebook)


@click.command("y")
@click.pass_context
def yesterday_alias(ctx: click.Context) -> None:
    """Alias for 'yesterday'."""
    ctx.invoke(yesterday)


@click.command("last")
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


@click.command("l")
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


@click.command("history")
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


@click.command("open")
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

    Both notebook and note names support fuzzy matching - if no exact match
    is found, similar options will be suggested interactively.
    """
    from nb.cli.utils import resolve_notebook, resolve_note
    from nb.core.links import get_linked_note_in_notebook
    from nb.core.notebooks import (
        ensure_notebook_note,
        get_notebook_note_path,
        is_notebook_date_based,
    )

    config = get_config()
    show = ctx.obj and ctx.obj.get("show")

    # Resolve notebook with fuzzy matching if specified
    if notebook:
        nb_config = config.get_notebook(notebook)
        if not nb_config:
            resolved = resolve_notebook(notebook)
            if resolved:
                notebook = resolved
            else:
                raise SystemExit(1)

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
                # Try fuzzy matching
                resolved_path = resolve_note(note_ref, notebook=notebook)
                if resolved_path:
                    note_path = resolved_path
                else:
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


@click.command("o")
@click.argument("note_ref")
@click.option("--notebook", "-n", help="Notebook to open the note from")
@click.pass_context
def open_alias(ctx: click.Context, note_ref: str, notebook: str | None) -> None:
    """Alias for 'open'."""
    ctx.invoke(open_date, note_ref=note_ref, notebook=notebook)


@click.command("show")
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


@click.command("new")
@click.argument("path", required=False)
@click.option("--notebook", "-n", help="Notebook to create the note in")
@click.option("--title", "-t", help="Title for the note")
@click.option("--template", "-T", "template_name", help="Template to use for the note")
def new_note(
    path: str | None,
    notebook: str | None,
    title: str | None,
    template_name: str | None,
) -> None:
    """Create a new note.

    PATH is the location for the note. Can be:
    - A full path: "projects/myproject/ideas"
    - Just a name: "ideas" (requires --notebook)
    - Omitted if notebook is date-based (creates today's note)

    The .md extension is added automatically if not present.

    Use --template/-T to apply a template when creating the note.
    Templates are stored in .nb/templates/.

    \b
    Examples:
      nb new -n daily             # Today's note in daily (date-based)
      nb new ideas -n projects    # projects/ideas.md
      nb new projects/roadmap     # projects/roadmap.md
      nb new -n work -T meeting   # New note with meeting template
    """
    from nb.core.notebooks import ensure_notebook_note, is_notebook_date_based
    from nb.core.templates import list_templates, template_exists

    config = get_config()

    # Resolve template: explicit flag > notebook default > none
    resolved_template = None
    if template_name:
        if not template_exists(template_name):
            console.print(f"[red]Template not found:[/red] {template_name}")
            available = list_templates()
            if available:
                console.print(f"[dim]Available: {', '.join(available)}[/dim]")
            raise SystemExit(1)
        resolved_template = template_name
    elif notebook:
        # Check for notebook default template
        nb_config = config.get_notebook(notebook)
        if nb_config and nb_config.template:
            resolved_template = nb_config.template

    # If notebook specified but no path, check if it's date-based
    if notebook and not path:
        if is_notebook_date_based(notebook):
            # Create/open today's note in this date-based notebook
            full_path = ensure_notebook_note(notebook, template=resolved_template)
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
        full_path = create_note(note_path, title=title, template=resolved_template)
        console.print(f"[green]Created:[/green] {note_path}")
        open_note(full_path)
    except FileExistsError:
        console.print(f"[red]Note already exists:[/red] {note_path}")
        raise SystemExit(1)


@click.command("edit")
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


@click.command("add")
@click.argument("text")
def add_to_today(text: str) -> None:
    """Append a line to today's note."""
    dt = date.today()
    path = ensure_daily_note(dt)

    # Append the text
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{text}\n")

    console.print(f"[green]Added to {path.name}[/green]")


@click.command("list")
@click.option("--notebook", "-n", help="Filter by notebook")
@click.option(
    "--all", "-a", "all_notes", is_flag=True, help="List all notes in all notebooks"
)
@click.option("--week", is_flag=True, help="Show this week's notes")
@click.option("--month", is_flag=True, help="Show this month's notes")
def list_notes_cmd(
    notebook: str | None, all_notes: bool, week: bool, month: bool
) -> None:
    """List notes.

    By default, shows the 3 most recent notes from each notebook.
    Use --all to list all notes, or --notebook to filter by a specific notebook.
    Use --week or --month to filter by date (defaults to daily notebook if no --notebook given).
    """
    from nb.core.notebooks import get_notebook_notes_with_linked
    from nb.core.notes import (
        get_all_notes,
        get_latest_notes_per_notebook,
        list_notebook_notes_by_date,
    )

    if week or month:
        # Get date range
        from nb.utils.dates import get_month_range, get_week_range

        if week:
            start, end = get_week_range()
        else:
            start, end = get_month_range()

        if notebook:
            # Filter specific notebook by date
            notes = list_notebook_notes_by_date(notebook, start=start, end=end)
            if not notes:
                console.print(
                    f"[dim]No notes found in {notebook} for this {'week' if week else 'month'}.[/dim]"
                )
                return
        else:
            # Default to daily notes
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
    elif all_notes:
        # List all notes in all notebooks (one line each)
        notes = get_all_notes()

        if not notes:
            console.print("[dim]No notes found.[/dim]")
            return

        current_notebook = None
        for note_path, title, nb_name, tags in notes:
            if nb_name != current_notebook:
                if current_notebook is not None:
                    console.print()  # Blank line between notebooks
                color, icon = get_notebook_display_info(nb_name)
                icon_prefix = f"{icon} " if icon else ""
                console.print(f"[bold {color}]{icon_prefix}{nb_name}[/bold {color}]")
                current_notebook = nb_name
            display = title if title else note_path.stem
            tags_str = " ".join(f"[yellow]#{t}[/yellow]" for t in tags) if tags else ""
            if tags_str:
                console.print(f"  {display} {tags_str} [dim]({note_path})[/dim]")
            else:
                console.print(f"  {display} [dim]({note_path})[/dim]")
    else:
        # Default: List latest 3 notes from each notebook
        notes_by_notebook = get_latest_notes_per_notebook(limit=3)

        if not notes_by_notebook:
            console.print("[dim]No notes found.[/dim]")
            return

        for nb_name in sorted(notes_by_notebook.keys()):
            notes = notes_by_notebook[nb_name]
            color, icon = get_notebook_display_info(nb_name)
            icon_prefix = f"{icon} " if icon else ""
            console.print(f"[bold {color}]{icon_prefix}{nb_name}[/bold {color}]")
            for note_path, title, tags in notes:
                display = title if title else note_path.stem
                tags_str = (
                    " ".join(f"[yellow]#{t}[/yellow]" for t in tags) if tags else ""
                )
                if tags_str:
                    console.print(f"  {display} {tags_str} [dim]({note_path})[/dim]")
                else:
                    console.print(f"  {display} [dim]({note_path})[/dim]")
            console.print()  # Blank line between notebooks
