"""Note-related CLI commands."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import click

from nb.cli.completion import complete_notebook
from nb.cli.utils import (
    console,
    get_notebook_display_info,
    get_stdin_content,
    open_or_show_note,
    print_note,
    resolve_note_ref,
)
from nb.config import get_config
from nb.core.notes import (
    create_note,
    delete_note,
    ensure_daily_note,
    list_daily_notes,
    open_note,
)
from nb.utils.fuzzy import UserCancelled


def register_note_commands(cli: click.Group) -> None:
    """Register all note-related commands with the CLI."""
    cli.add_command(today)
    cli.add_command(yesterday)
    cli.add_command(last_note)
    cli.add_command(history_cmd)
    cli.add_command(open_date)
    cli.add_command(show_note)
    cli.add_command(new_note)
    cli.add_command(edit_note)
    cli.add_command(add_to_note)
    cli.add_command(list_notes_cmd)
    cli.add_command(alias_note)
    cli.add_command(unalias_note)
    cli.add_command(list_aliases_cmd)
    cli.add_command(delete_note_cmd)
    cli.add_command(where_cmd)


@click.command()
@click.option(
    "--notebook",
    "-n",
    help="Notebook to create today's note in",
    shell_complete=complete_notebook,
)
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
            path = ensure_notebook_note(notebook, dt=dt)
        else:
            path = ensure_notebook_note(notebook, name=dt.isoformat())
    else:
        path = ensure_daily_note(dt)

    show = ctx.obj and ctx.obj.get("show")
    open_or_show_note(path, show=show)


@click.command()
@click.pass_context
def yesterday(ctx: click.Context) -> None:
    """Open yesterday's daily note."""
    dt = date.today() - timedelta(days=1)
    path = ensure_daily_note(dt)

    show = ctx.obj and ctx.obj.get("show")
    open_or_show_note(path, show=show)


@click.command("last")
@click.option(
    "-s", "--show", is_flag=True, help="Print note to console instead of opening editor"
)
@click.option(
    "--notebook", "-n", help="Filter by notebook", shell_complete=complete_notebook
)
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

    open_or_show_note(path, show=show)


@click.command("history")
@click.option("--limit", "-l", default=10, help="Number of entries to show")
@click.option("--offset", "-o", default=0, help="Skip first N entries")
@click.option(
    "--notebook", "-n", help="Filter by notebook", shell_complete=complete_notebook
)
@click.option(
    "--full-path", "-f", is_flag=True, help="Show full paths instead of filenames"
)
@click.option("--group", "-g", is_flag=True, help="Group entries by notebook")
def history_cmd(
    limit: int, offset: int, notebook: str | None, full_path: bool, group: bool
) -> None:
    """Show recently viewed notes.

    Displays a list of notes you've recently opened with timestamps.
    Use --group to organize entries by notebook.

    \b
    Examples:
      nb history             # Show last 10 viewed notes (interleaved)
      nb history -l 50       # Show last 50 viewed notes
      nb history -o 10       # Skip first 10, show next 10
      nb history -n work     # Show recently viewed notes in 'work' notebook
      nb history -f          # Show full paths instead of filenames
      nb history -g          # Group entries by notebook
    """
    from collections import defaultdict

    from nb.core.links import list_linked_notes
    from nb.core.notes import get_recently_viewed_notes

    # Request more views than limit+offset to account for deduplication
    # Use higher multiplier since notes can be viewed many times
    views = get_recently_viewed_notes(limit=(limit + offset) * 10, notebook=notebook)

    if not views:
        console.print("[dim]No view history found.[/dim]")
        return

    config = get_config()

    # Get linked notes from database (not just config)
    linked_notes = list_linked_notes()

    console.print("\n[bold]Recently Viewed Notes[/bold]\n")

    # Deduplicate views by path, keeping most recent timestamp and count
    # Use dict to track: path -> (most_recent_timestamp, view_count)
    seen_paths: dict[Path, tuple[list, int]] = {}
    unique_views: list[tuple[Path, list, int]] = []  # (path, [timestamps], total_count)

    for path, viewed_at in views:
        resolved = path.resolve()
        if resolved in seen_paths:
            # Already seen this file - just increment count
            seen_paths[resolved] = (
                seen_paths[resolved][0],
                seen_paths[resolved][1] + 1,
            )
        else:
            # First time seeing this file
            seen_paths[resolved] = ([viewed_at], 1)
            unique_views.append((path, [viewed_at], 1))

    # Update counts in unique_views and apply offset/limit
    final_views = []
    for i, (path, timestamps, _) in enumerate(unique_views):
        if i < offset:
            continue
        resolved = path.resolve()
        _, count = seen_paths[resolved]
        final_views.append((path, timestamps, count))
        if len(final_views) >= limit:
            break

    # Resolve notebook info for each view
    resolved_views = []
    for path, timestamps, view_count in final_views:
        # Determine notebook - check linked notes first for external paths
        try:
            rel_path = path.relative_to(config.notes_root)
            # Get notebook from path (first directory component)
            if len(rel_path.parts) > 1:
                nb_name = rel_path.parts[0]
            else:
                nb_name = ""  # Root-level notes
            linked_alias = None
        except ValueError:
            # Path is outside notes_root - check if it's a linked note
            rel_path = path
            nb_name = "@external"
            linked_alias = None

            # Check linked notes (from database) to find proper notebook
            for ln in linked_notes:
                if ln.path.is_file() and ln.path.resolve() == path.resolve():
                    nb_name = ln.notebook or f"@{ln.alias}"
                    linked_alias = ln.alias
                    rel_path = Path(ln.alias + path.suffix)
                    break
                elif ln.path.is_dir():
                    try:
                        inner_rel = path.relative_to(ln.path)
                        nb_name = ln.notebook or f"@{ln.alias}"
                        linked_alias = ln.alias
                        rel_path = inner_rel
                        break
                    except ValueError:
                        continue

        resolved_views.append(
            (path, rel_path, timestamps, view_count, linked_alias, nb_name)
        )

    if group:
        # Group by notebook (old behavior)
        views_by_notebook: dict[str, list] = defaultdict(list)
        for (
            path,
            rel_path,
            timestamps,
            view_count,
            linked_alias,
            nb_name,
        ) in resolved_views:
            views_by_notebook[nb_name].append(
                (path, rel_path, timestamps, view_count, linked_alias)
            )

        # Sort notebooks alphabetically (empty string last, @external last)
        sorted_notebooks = sorted(
            views_by_notebook.keys(),
            key=lambda x: (x == "@external", x == "", x.lower()),
        )

        for nb_name in sorted_notebooks:
            nb_views = views_by_notebook[nb_name]

            # Get notebook display info (color and icon)
            if nb_name and nb_name != "@external":
                color, icon = get_notebook_display_info(nb_name)
                icon_prefix = f"{icon} " if icon else ""
                console.print(f"[bold {color}]{icon_prefix}{nb_name}[/bold {color}]")
            elif nb_name == "@external":
                console.print("[bold dim]@external[/bold dim]")
            else:
                console.print("[bold dim](root)[/bold dim]")

            # Sort views by most recent timestamp within each notebook
            nb_views.sort(key=lambda x: x[2][0], reverse=True)

            for _abs_path, rel_path, timestamps, view_count, linked_alias in nb_views:
                # Format the timestamp (use most recent)
                time_str = timestamps[0].strftime(
                    f"{config.date_format} {config.time_format}"
                )

                # Determine display path
                if full_path:
                    display_path = str(rel_path)
                else:
                    display_path = rel_path.name

                # Show count if viewed multiple times
                count_str = ""
                if view_count > 1:
                    count_str = f" [dim](+{view_count - 1})[/dim]"

                # Show linked alias if applicable
                alias_str = ""
                if linked_alias:
                    alias_str = f" [dim](@{linked_alias})[/dim]"

                console.print(
                    f"  [dim]{time_str}[/dim]  {display_path}{alias_str}{count_str}"
                )

            console.print()  # Blank line between notebooks
    else:
        # Interleaved display (new default) - sorted by most recent first
        for (
            _path,
            rel_path,
            timestamps,
            view_count,
            linked_alias,
            nb_name,
        ) in resolved_views:
            # Format the timestamp (use most recent)
            time_str = timestamps[0].strftime(
                f"{config.date_format} {config.time_format}"
            )

            # Determine display path
            if full_path:
                display_path = str(rel_path)
            else:
                display_path = rel_path.name

            # Show count if viewed multiple times
            count_str = ""
            if view_count > 1:
                count_str = f" [dim](+{view_count - 1})[/dim]"

            # Show linked alias if applicable
            alias_str = ""
            if linked_alias:
                alias_str = f" [dim](@{linked_alias})[/dim]"

            # Get notebook display info (color and icon)
            if nb_name and nb_name != "@external":
                color, icon = get_notebook_display_info(nb_name)
                icon_prefix = f"{icon} " if icon else ""
                nb_display = f"[{color}]{icon_prefix}{nb_name}[/{color}]"
            elif nb_name == "@external":
                nb_display = "[dim]@external[/dim]"
            else:
                nb_display = "[dim](root)[/dim]"

            console.print(
                f"[dim]{time_str}[/dim]  {nb_display}  {display_path}{alias_str}{count_str}"
            )


@click.command("open")
@click.argument("note_ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook to open the note from",
    shell_complete=complete_notebook,
)
@click.option(
    "--no-prompt",
    is_flag=True,
    help="Don't prompt to create if note doesn't exist",
)
@click.pass_context
def open_date(
    ctx: click.Context, note_ref: str, notebook: str | None, no_prompt: bool
) -> None:
    """Open a note by date or name.

    \b
    NOTE_REF can be:
    - "last" to open the most recently modified note
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A note name (when used with -n for non-date-based notebooks)
    - A notebook/note path: "work/myproject", "daily/friday"
    - A note alias (created with 'nb alias')
    - A linked note alias (when used with -n for the linked note's notebook)
    - A path to a note file

    If the note doesn't exist, you'll be prompted to create it.
    Use --no-prompt to disable this behavior.

    \b
    Examples:
      nb open last                # Open the last modified note
      nb open last -n work        # Open last modified note in 'work' notebook
      nb open friday              # Open Friday's daily note
      nb open "last monday"       # Open last Monday's note
      nb open myalias             # Open note by alias
      nb open myproject -n ideas  # Open ideas/myproject.md
      nb open friday -n work      # Open Friday in work notebook
      nb open mytodo -n nbcli     # Open linked note 'mytodo' in notebook 'nbcli'

    Both notebook and note names support fuzzy matching - if no exact match
    is found, similar options will be suggested interactively.
    """
    from rich.prompt import Confirm

    from nb.core.notebooks import ensure_notebook_note, is_notebook_date_based
    from nb.core.notes import create_note, get_last_modified_note
    from nb.utils.dates import parse_fuzzy_date

    show = ctx.obj and ctx.obj.get("show")
    config = get_config()

    # Handle "last" as a special case - open the most recently modified note
    if note_ref.lower() == "last":
        path = get_last_modified_note(notebook=notebook)
        if not path:
            console.print("[dim]No notes found.[/dim]")
            if notebook:
                console.print("[dim]Try 'nb index' to ensure notes are indexed.[/dim]")
            raise SystemExit(1)
        open_or_show_note(path, show=show)
        return

    try:
        path = resolve_note_ref(note_ref, notebook=notebook, create_if_date_based=True)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if path:
        open_or_show_note(path, show=show)
        return

    # Note doesn't exist - try to resolve the path without requiring existence
    # Use interactive=False to avoid duplicate "not found" messages from fuzzy matching
    try:
        potential_path = resolve_note_ref(
            note_ref,
            notebook=notebook,
            ensure_exists=False,
            create_if_date_based=False,
            interactive=False,
        )
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if not potential_path:
        console.print(f"[red]Could not resolve note: {note_ref}[/red]")
        raise SystemExit(1)

    # We have a potential path but the file doesn't exist
    if no_prompt:
        console.print(f"[red]Note not found: {note_ref}[/red]")
        raise SystemExit(1)

    # Prompt to create
    display_name = potential_path.name
    if Confirm.ask(f"Note '{display_name}' doesn't exist. Create it?", default=True):
        # Determine how to create the note
        # Parse notebook from resolved path or use provided notebook
        resolved_notebook = notebook
        if not resolved_notebook:
            try:
                rel = potential_path.relative_to(config.notes_root)
                if len(rel.parts) > 1:
                    resolved_notebook = rel.parts[0]
            except ValueError:
                pass

        # Create the note
        if resolved_notebook and is_notebook_date_based(resolved_notebook):
            # Date-based: use ensure_notebook_note
            parsed_date = parse_fuzzy_date(note_ref)
            if parsed_date:
                path = ensure_notebook_note(resolved_notebook, dt=parsed_date)
            else:
                # If date parsing failed, just create a blank note
                path = create_note(potential_path.relative_to(config.notes_root))
        else:
            # Non-date-based: create with standard function
            try:
                rel_path = potential_path.relative_to(config.notes_root)
            except ValueError:
                # External path - can't create
                console.print(
                    f"[red]Cannot create note outside notes root: {potential_path}[/red]"
                )
                raise SystemExit(1) from None
            path = create_note(rel_path)

        if path and path.exists():
            console.print(f"[green]Created:[/green] {display_name}")
            open_or_show_note(path, show=show)
        else:
            console.print("[red]Failed to create note.[/red]")
            raise SystemExit(1)
    else:
        console.print("[dim]Cancelled.[/dim]")


@click.command("show")
@click.argument("note_ref", required=False)
@click.option(
    "--notebook",
    "-n",
    help="Notebook to show the note from",
    shell_complete=complete_notebook,
)
def show_note(note_ref: str | None, notebook: str | None) -> None:
    """Print a note to the console.

    \b
    NOTE_REF can be:
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A note name (when used with -n for non-date-based notebooks)
    - A notebook/note path: "work/myproject", "daily/friday"
    - A note alias (created with 'nb alias')
    - A linked note alias (when used with -n for the linked note's notebook)
    - A path to a note file
    - Omitted to show today's note

    \b
    Examples:
      nb show                     # Show today's daily note
      nb show friday              # Show Friday's daily note
      nb show myalias             # Show note by alias
      nb show -n work             # Show today's note in work notebook
      nb show friday -n work      # Show Friday in work notebook
      nb show myproject -n ideas  # Show ideas/myproject.md
      nb show mytodo -n nbcli     # Show linked note 'mytodo' in notebook 'nbcli'
    """
    # Default to today if no note_ref provided
    if note_ref is None:
        note_ref = "today"

    try:
        path = resolve_note_ref(note_ref, notebook=notebook, create_if_date_based=True)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if not path:
        console.print(f"[red]Could not resolve note: {note_ref}[/red]")
        raise SystemExit(1)

    print_note(path)


@click.command("new")
@click.argument("path", required=False)
@click.option(
    "--notebook",
    "-n",
    help="Notebook to create the note in",
    shell_complete=complete_notebook,
)
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
        console.print(f"[yellow]Note already exists:[/yellow] {note_path}")
        if click.confirm("Open existing note?", default=True):
            open_note(config.notes_root / note_path)
        else:
            raise SystemExit(1) from None


@click.command("edit")
@click.argument("path")
def edit_note(path: str) -> None:
    """Open an existing note in the editor.

    PATH is relative to the notes root.
    """
    from nb.cli.utils import ensure_note_path

    full_path = ensure_note_path(path)

    if not full_path.exists():
        console.print(f"[red]Note not found:[/red] {path}")
        raise SystemExit(1)

    open_note(full_path)


@click.command("add")
@click.argument("text", required=False)
@click.option(
    "--note",
    "-N",
    "target_note",
    help="Add to specific note (path, alias, or notebook/note format)",
)
@click.option(
    "--notebook",
    "-n",
    help="Notebook to search for note (used with --note)",
)
def add_to_note(
    text: str | None, target_note: str | None, notebook: str | None
) -> None:
    """Append content to a note (defaults to today's daily note).

    Accepts text as an argument or from stdin (piped input).

    \b
    Examples:
      nb add "Quick thought"                       # Today's daily note
      nb add "Note text" --note myproject          # Specific note by name
      nb add "Note text" --note work/myproject     # Notebook/note format
      nb add "Note text" --note myproject -n work  # Note in specific notebook
      nb add "Note text" -N proj                   # Using alias

    \b
    Piping examples:
      echo "random thought" | nb add               # Pipe to today's note
      cat notes.txt | nb add                       # Pipe file content
      git diff --stat | nb add --note work/log     # Pipe command output
      pbpaste | nb add                             # Pipe clipboard (macOS)
    """
    # Check stdin first, then use argument
    content = get_stdin_content() or text

    if not content:
        console.print("[red]No content provided.[/red]")
        console.print('[dim]Usage: nb add "text" or echo "text" | nb add[/dim]')
        raise SystemExit(1)

    if target_note:
        resolved_path = resolve_note_ref(target_note, notebook=notebook)
        if not resolved_path:
            console.print(f"[red]Note not found: {target_note}[/red]")
            raise SystemExit(1)

        # Append the content
        with resolved_path.open("a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")

        console.print(f"[green]Added to {resolved_path.name}[/green]")
    else:
        # Default: add to today's daily note
        if notebook:
            console.print(
                "[yellow]Warning: --notebook/-n ignored without --note[/yellow]"
            )

        dt = date.today()
        path = ensure_daily_note(dt)

        # Append the content
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")

        console.print(f"[green]Added to {path.name}[/green]")


@click.command("list")
@click.option(
    "--notebook", "-n", help="Filter by notebook", shell_complete=complete_notebook
)
@click.option(
    "--all", "-a", "all_notes", is_flag=True, help="List all notes in all notebooks"
)
@click.option("--week", is_flag=True, help="Show this week's notes")
@click.option("--month", is_flag=True, help="Show this month's notes")
@click.option("--full", "-f", is_flag=True, help="Show full path to notes")
@click.option(
    "--details", "-d", is_flag=True, help="Show extra details (todo count, mtime, etc.)"
)
@click.option(
    "--section",
    "-S",
    multiple=True,
    help="Filter by path section/subdirectory (repeatable)",
)
@click.option(
    "--exclude-section",
    "-xs",
    multiple=True,
    help="Exclude notes from this section (repeatable)",
)
@click.option(
    "--tree",
    "-t",
    is_flag=True,
    help="Display notes as a tree grouped by subdirectory sections",
)
def list_notes_cmd(
    notebook: str | None,
    all_notes: bool,
    week: bool,
    month: bool,
    full: bool,
    details: bool,
    section: tuple[str, ...],
    exclude_section: tuple[str, ...],
    tree: bool,
) -> None:
    """List notes.

    By default, shows the 3 most recent notes from each notebook.
    Use --all to list all notes, or --notebook to filter by a specific notebook.
    Use --week or --month to filter by date (defaults to daily notebook if no --notebook given).

    With --details/-d, shows extra information:
    - Todo count (incomplete todos in the note)
    - Last modified time
    - Note date (from frontmatter)
    - Excluded status (if note is excluded from nb todo)
    """
    from nb.core.notes import (
        NoteDetails,
        get_all_notes,
        get_latest_notes_per_notebook,
        get_note_details_batch,
        get_notebook_notes_with_metadata,
        list_notebook_notes_by_date,
    )

    def format_details_str(d: NoteDetails | None) -> str:
        """Format note details as a string for display."""
        if d is None:
            return ""

        parts = []

        # Todo count
        if d.todo_count > 0:
            parts.append(
                f"[cyan]{d.todo_count} todo{'s' if d.todo_count != 1 else ''}[/cyan]"
            )

        # Note date
        if d.note_date:
            parts.append(f"[dim]{d.note_date}[/dim]")

        # Mtime (relative)
        if d.mtime:
            from datetime import datetime, timedelta

            now = datetime.now()
            mtime_dt = datetime.fromtimestamp(d.mtime)
            diff = now - mtime_dt

            if diff < timedelta(minutes=1):
                mtime_str = "just now"
            elif diff < timedelta(hours=1):
                mins = int(diff.total_seconds() / 60)
                mtime_str = f"{mins}m ago"
            elif diff < timedelta(days=1):
                hours = int(diff.total_seconds() / 3600)
                mtime_str = f"{hours}h ago"
            elif diff < timedelta(days=7):
                days = diff.days
                mtime_str = f"{days}d ago"
            else:
                mtime_str = mtime_dt.strftime("%b %d")
            parts.append(f"[dim]mod: {mtime_str}[/dim]")

        # Excluded status
        if d.todo_exclude:
            parts.append("[red]excluded[/red]")

        return "  ".join(parts)

    def filter_notes_by_sections(
        note_paths: list,
        include_sections: tuple[str, ...],
        exclude_sections: tuple[str, ...],
    ) -> list:
        """Filter notes by path-based sections."""
        from nb.core.notes import get_sections_for_path

        if not include_sections and not exclude_sections:
            return note_paths

        filtered = []
        for item in note_paths:
            # Handle both plain Path and tuple (path, title, tags, ...)
            if isinstance(item, tuple):
                note_path = item[0]
            else:
                note_path = item

            note_sections = get_sections_for_path(note_path)

            # Check include filter (any match)
            if include_sections:
                if not any(s in note_sections for s in include_sections):
                    continue

            # Check exclude filter (none should match)
            if exclude_sections:
                if any(s in note_sections for s in exclude_sections):
                    continue

            filtered.append(item)
        return filtered

    def render_notes_tree(
        notes: list,
        notebook_name: str,
        full_path: bool,
        details_map: dict,
        format_details_fn,
    ) -> None:
        """Render notes as a tree grouped by subdirectory sections."""
        from rich.tree import Tree

        from nb.core.notes import get_sections_for_path

        config = get_config()

        # Get notebook display info
        color, icon = get_notebook_display_info(notebook_name)
        icon_prefix = f"{icon} " if icon else ""

        # Build tree structure
        root = Tree(f"[bold {color}]{icon_prefix}{notebook_name}[/bold {color}]")
        section_nodes: dict = {}  # Maps section path tuple to tree node

        for item in notes:
            # Handle tuple format (path, title, tags, is_linked, alias)
            if isinstance(item, tuple):
                note_path = item[0]
                title = item[1] if len(item) > 1 else None
                tags = item[2] if len(item) > 2 else []
            else:
                note_path = item
                title = None
                tags = []

            # Convert absolute path to relative path for section extraction
            try:
                rel_path = note_path.relative_to(config.notes_root)
            except ValueError:
                # External/linked note - use the path as-is
                rel_path = note_path

            note_sections = get_sections_for_path(rel_path)

            # Find or create parent node
            parent = root
            for i, sec in enumerate(note_sections):
                section_key = tuple(note_sections[: i + 1])
                if section_key not in section_nodes:
                    section_nodes[section_key] = parent.add(f"[dim]{sec}/[/dim]")
                parent = section_nodes[section_key]

            # Build note display
            display = title if title else note_path.stem
            tags_str = " ".join(f"[yellow]#{t}[/yellow]" for t in tags) if tags else ""
            path_display = f"[dim]({note_path if full_path else note_path.stem})[/dim]"

            note_parts = [display]
            if tags_str:
                note_parts.append(tags_str)
            note_parts.append(path_display)

            # Add details if available
            if details_map and note_path in details_map:
                details_str = format_details_fn(details_map[note_path])
                if details_str:
                    note_parts.append(details_str)

            parent.add(" ".join(note_parts))

        console.print(root)

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
        else:
            # Default to daily notes
            notes = list_daily_notes(start=start, end=end)

        # Apply section filters
        notes = filter_notes_by_sections(notes, section, exclude_section)

        if not notes:
            msg = (
                f"No notes found in {notebook}" if notebook else "No daily notes found"
            )
            if section or exclude_section:
                msg += " matching section filters"
            console.print(f"[dim]{msg}.[/dim]")
            return

        # Get details if requested
        details_map = get_note_details_batch(notes) if details else {}

        for note_path in notes:
            base = str(note_path) if full else note_path.stem
            if details:
                d = details_map.get(note_path)
                details_str = format_details_str(d)
                console.print(f"{base}  {details_str}" if details_str else base)
            else:
                console.print(base)
    elif notebook:
        # Get notes with metadata (title, tags, linked status)
        notes_meta = get_notebook_notes_with_metadata(notebook)

        # Apply section filters
        notes_meta = filter_notes_by_sections(notes_meta, section, exclude_section)

        if not notes_meta:
            msg = f"No notes in {notebook}"
            if section or exclude_section:
                msg += " matching section filters"
            console.print(f"[dim]{msg}.[/dim]")
            return

        # Get extra details if requested
        if details:
            note_paths = [note_path for note_path, _, _, _, _ in notes_meta]
            details_map = get_note_details_batch(note_paths)
        else:
            details_map = {}

        # Use tree display if --tree flag is set
        if tree:
            render_notes_tree(
                notes_meta, notebook, full, details_map, format_details_str
            )
            return

        for note_path, title, tags, is_linked, alias in notes_meta:
            # Build display name (title or stem)
            display = title if title else note_path.stem

            # Build tags string
            tags_str = " ".join(f"[yellow]#{t}[/yellow]" for t in tags) if tags else ""

            # Build base output
            if is_linked:
                if alias:
                    linked_info = f"[cyan]{alias}[/cyan] [dim](linked)[/dim]"
                else:
                    linked_info = "[dim](linked)[/dim]"
                base_parts = [f"  {display}"]
                if tags_str:
                    base_parts.append(tags_str)
                base_parts.append(
                    f"[dim]({note_path if full else note_path.stem})[/dim]"
                )
                base_parts.append(linked_info)
            else:
                base_parts = [f"  {display}"]
                if tags_str:
                    base_parts.append(tags_str)
                base_parts.append(
                    f"[dim]({note_path if full else note_path.stem})[/dim]"
                )

            base = " ".join(base_parts)

            if details:
                d = details_map.get(note_path)
                details_str = format_details_str(d)
                console.print(f"{base}  {details_str}" if details_str else base)
            else:
                console.print(base)
    elif all_notes:
        # List all notes in all notebooks (one line each)
        all_notes_list = get_all_notes()

        # Apply section filters
        all_notes_list = filter_notes_by_sections(
            all_notes_list, section, exclude_section
        )

        if not all_notes_list:
            msg = "No notes found"
            if section or exclude_section:
                msg += " matching section filters"
            console.print(f"[dim]{msg}.[/dim]")
            return

        # Get details if requested
        if details:
            note_paths = [note_path for note_path, _, _, _ in all_notes_list]
            details_map = get_note_details_batch(note_paths)
        else:
            details_map = {}

        current_notebook = None
        for note_path, title, nb_name, tags in all_notes_list:
            if nb_name != current_notebook:
                color, icon = get_notebook_display_info(nb_name)
                icon_prefix = f"{icon} " if icon else ""
                console.print(f"[bold {color}]{icon_prefix}{nb_name}[/bold {color}]")
                current_notebook = nb_name
            display = title if title else note_path.stem
            tags_str = " ".join(f"[yellow]#{t}[/yellow]" for t in tags) if tags else ""

            base_parts = [f"  {display}"]
            if tags_str:
                base_parts.append(tags_str)
            base_parts.append(f"[dim]({note_path if full else note_path.stem})[/dim]")
            base = " ".join(base_parts)

            if details:
                d = details_map.get(note_path)
                details_str = format_details_str(d)
                console.print(f"{base}  {details_str}" if details_str else base)
            else:
                console.print(base)
    else:
        # Default: List latest 3 notes from each notebook
        notes_by_notebook = get_latest_notes_per_notebook(limit=3)

        if not notes_by_notebook:
            console.print("[dim]No notes found.[/dim]")
            return

        # Apply section filters to each notebook's notes
        if section or exclude_section:
            filtered_by_notebook = {}
            for nb_name, nb_notes in notes_by_notebook.items():
                filtered = filter_notes_by_sections(nb_notes, section, exclude_section)
                if filtered:
                    filtered_by_notebook[nb_name] = filtered
            notes_by_notebook = filtered_by_notebook

            if not notes_by_notebook:
                console.print("[dim]No notes found matching section filters.[/dim]")
                return

        # Get details if requested
        if details:
            all_paths: list[Path] = []
            for nb_notes in notes_by_notebook.values():
                all_paths.extend(note_path for note_path, _, _ in nb_notes)
            details_map = get_note_details_batch(all_paths)
        else:
            details_map = {}

        for nb_name in sorted(notes_by_notebook.keys()):
            nb_notes_list = notes_by_notebook[nb_name]
            color, icon = get_notebook_display_info(nb_name)
            icon_prefix = f"{icon} " if icon else ""
            console.print(f"[bold {color}]{icon_prefix}{nb_name}[/bold {color}]")
            for note_path, title, tags in nb_notes_list:
                display = title if title else note_path.stem
                tags_str = (
                    " ".join(f"[yellow]#{t}[/yellow]" for t in tags) if tags else ""
                )

                base_parts = [f"  {display}"]
                if tags_str:
                    base_parts.append(tags_str)
                base_parts.append(
                    f"[dim]({note_path if full else note_path.stem})[/dim]"
                )
                base = " ".join(base_parts)

                if details:
                    d = details_map.get(note_path)
                    details_str = format_details_str(d)
                    console.print(f"{base}  {details_str}" if details_str else base)
                else:
                    console.print(base)


@click.command("alias")
@click.argument("alias_name")
@click.argument("note_ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook containing the note",
    shell_complete=complete_notebook,
)
def alias_note(alias_name: str, note_ref: str, notebook: str | None) -> None:
    """Create an alias for a note.

    ALIAS_NAME is the shorthand name to use (e.g., "readme", "standup").
    NOTE_REF is the note to alias (path, name, or notebook/name).

    \b
    Examples:
      nb alias readme projects/README
      nb alias standup daily/2025-11-29
      nb alias meeting notes/meeting-template -n projects
    """
    from nb.cli.utils import resolve_note
    from nb.core.aliases import add_note_alias

    # Extract notebook from note_ref if specified
    if "/" in note_ref and not notebook:
        parts = note_ref.split("/", 1)
        notebook = parts[0]
        note_name = parts[1]
    else:
        note_name = note_ref

    # Resolve the note
    resolved = resolve_note(note_name, notebook=notebook, interactive=True)
    if not resolved:
        console.print(f"[red]Note not found: {note_ref}[/red]")
        console.print("[dim]Hint: Use 'nb stream' or 'nb search' to find notes.[/dim]")
        raise SystemExit(1)

    try:
        add_note_alias(alias_name, resolved, notebook=notebook)
        console.print(f"[green]Alias created:[/green] {alias_name} -> {resolved.name}")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None


@click.command("unalias")
@click.argument("alias_name")
def unalias_note(alias_name: str) -> None:
    """Remove a note alias.

    \b
    Examples:
      nb unalias readme
    """
    from nb.core.aliases import remove_note_alias

    if remove_note_alias(alias_name):
        console.print(f"[green]Alias removed:[/green] {alias_name}")
    else:
        console.print(f"[yellow]Alias not found: {alias_name}[/yellow]")


@click.command("aliases")
def list_aliases_cmd() -> None:
    """List all note aliases.

    Shows all aliases that have been created for quick note access.
    """
    from nb.core.aliases import list_note_aliases

    aliases = list_note_aliases()
    if not aliases:
        console.print("[dim]No aliases defined.[/dim]")
        console.print("[dim]Create one with: nb alias <name> <note>[/dim]")
        return

    console.print("[bold]Note Aliases[/bold]\n")
    for alias, path, notebook in aliases:
        nb_str = f" [dim]({notebook})[/dim]" if notebook else ""
        console.print(f"  [cyan]{alias}[/cyan] -> {path.name}{nb_str}")


@click.command("delete")
@click.argument("note_ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook containing the note",
    shell_complete=complete_notebook,
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def delete_note_cmd(note_ref: str, notebook: str | None, force: bool) -> None:
    """Delete a note from the filesystem and database.

    NOTE_REF can be a note path, name, alias, or date (for daily notes).
    Use --notebook/-n to specify which notebook the note is in.

    This will also delete all todos from that note.

    Note: Linked notes cannot be deleted. Use 'nb unlink' to remove them.

    \b
    Examples:
      nb delete friday                 # Delete Friday's daily note
      nb delete myproject -n work      # Delete work/myproject.md
      nb delete work/myproject         # Delete using notebook/note format
      nb delete myalias                # Delete note by alias
      nb delete friday -f              # Skip confirmation
    """
    from rich.prompt import Confirm

    from nb.cli.utils import get_display_path

    config = get_config()

    try:
        path = resolve_note_ref(note_ref, notebook=notebook)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if not path:
        console.print(f"[red]Could not resolve note: {note_ref}[/red]")
        raise SystemExit(1)

    # Get display path for user feedback
    display_path = get_display_path(path)

    # Show confirmation unless --force
    if not force:
        console.print(f"\n[bold]Delete note:[/bold] {display_path}")

        if not Confirm.ask("Are you sure?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(0)

    # Delete the note
    try:
        delete_note(path, notes_root=config.notes_root)
        console.print(f"[green]Deleted:[/green] {display_path}")
    except FileNotFoundError:
        console.print(f"[red]Note not found: {display_path}[/red]")
        raise SystemExit(1) from None
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None


@click.command("where")
@click.argument("ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook context for resolving note",
    shell_complete=complete_notebook,
)
def where_cmd(ref: str, notebook: str | None) -> None:
    """Print the full path to a notebook, note, or alias.

    REF can be:
    - A notebook name: prints path to notebook directory
    - A note name/path/date: prints path to note file
    - An alias (from 'nb alias'): prints path to aliased note
    - A linked note alias: prints path to linked file

    When multiple matches exist, all paths are printed (one per line).

    \b
    Examples:
      nb where daily              # Path to daily notebook directory
      nb where friday             # Path to Friday's daily note
      nb where myalias            # Path to aliased note
      nb where myproject -n work  # Path to work/myproject.md
    """
    from nb.core.aliases import get_note_by_alias
    from nb.core.links import get_linked_note, get_linked_note_in_notebook

    config = get_config()
    paths_found: list[Path] = []

    # 1. Check if it's a notebook name
    nb_config = config.get_notebook(ref)
    if nb_config:
        nb_path = config.get_notebook_path(ref)
        if nb_path and nb_path.exists():
            paths_found.append(nb_path)

    # 2. Check note aliases (from nb alias)
    alias_path = get_note_by_alias(ref)
    if alias_path and alias_path.exists() and alias_path not in paths_found:
        paths_found.append(alias_path)

    # 3. Check linked notes
    if notebook:
        linked = get_linked_note_in_notebook(notebook, ref)
        if linked and linked.path.exists() and linked.path not in paths_found:
            paths_found.append(linked.path)
    else:
        linked = get_linked_note(ref)
        if linked and linked.path.exists() and linked.path not in paths_found:
            paths_found.append(linked.path)

    # 4. Try to resolve as a note reference (non-interactive)
    try:
        note_path = resolve_note_ref(
            ref,
            notebook=notebook,
            interactive=False,
        )
        if note_path and note_path.exists() and note_path not in paths_found:
            paths_found.append(note_path)
    except UserCancelled:
        pass

    # Output results
    if not paths_found:
        console.print(f"[red]Not found: {ref}[/red]")
        raise SystemExit(1)

    for p in paths_found:
        # Print absolute path (plain text for piping)
        print(str(p.resolve()))
