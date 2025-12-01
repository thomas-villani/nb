"""Note-related CLI commands."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import click

from nb.cli.utils import (
    console,
    get_notebook_display_info,
    open_or_show_note,
    print_note,
    resolve_note_ref,
)
from nb.config import get_config
from nb.core.notes import (
    create_note,
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
@click.option("--notebook", "-n", help="Filter by notebook")
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

            for abs_path, rel_path, timestamps, view_count, linked_alias in nb_views:
                # Format the timestamp (use most recent)
                time_str = timestamps[0].strftime("%Y-%m-%d %H:%M")

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
            path,
            rel_path,
            timestamps,
            view_count,
            linked_alias,
            nb_name,
        ) in resolved_views:
            # Format the timestamp (use most recent)
            time_str = timestamps[0].strftime("%Y-%m-%d %H:%M")

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
@click.option("--notebook", "-n", help="Notebook to open the note from")
@click.pass_context
def open_date(ctx: click.Context, note_ref: str, notebook: str | None) -> None:
    """Open a note by date or name.

    NOTE_REF can be:
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A note name (when used with -n for non-date-based notebooks)
    - A note alias (created with 'nb alias')
    - A linked note alias (when used with -n for the linked note's notebook)
    - A path to a note file

    \b
    Examples:
      nb open friday              # Open Friday's daily note
      nb open "last monday"       # Open last Monday's note
      nb open myalias             # Open note by alias
      nb open myproject -n ideas  # Open ideas/myproject.md
      nb open friday -n work      # Open Friday in work notebook
      nb open mytodo -n nbcli     # Open linked note 'mytodo' in notebook 'nbcli'

    Both notebook and note names support fuzzy matching - if no exact match
    is found, similar options will be suggested interactively.
    """
    show = ctx.obj and ctx.obj.get("show")

    try:
        path = resolve_note_ref(note_ref, notebook=notebook, create_if_date_based=True)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1)

    if not path:
        console.print(f"[red]Could not resolve note: {note_ref}[/red]")
        raise SystemExit(1)

    open_or_show_note(path, show=show)


@click.command("show")
@click.argument("note_ref", required=False)
@click.option("--notebook", "-n", help="Notebook to show the note from")
def show_note(note_ref: str | None, notebook: str | None) -> None:
    """Print a note to the console.

    NOTE_REF can be:
    - A date like "2025-11-26" or "nov 26"
    - A relative date like "friday" or "last monday"
    - A note name (when used with -n for non-date-based notebooks)
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
        raise SystemExit(1)

    if not path:
        console.print(f"[red]Could not resolve note: {note_ref}[/red]")
        raise SystemExit(1)

    print_note(path)


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
    from nb.cli.utils import ensure_note_path

    full_path = ensure_note_path(path)

    if not full_path.exists():
        console.print(f"[red]Note not found:[/red] {path}")
        raise SystemExit(1)

    open_note(full_path)


@click.command("add")
@click.argument("text")
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
def add_to_note(text: str, target_note: str | None, notebook: str | None) -> None:
    """Append a line to a note (defaults to today's daily note).

    \b
    Examples:
      nb add "Quick thought"                       # Today's daily note
      nb add "Note text" --note myproject          # Specific note by name
      nb add "Note text" --note work/myproject     # Notebook/note format
      nb add "Note text" --note myproject -n work  # Note in specific notebook
      nb add "Note text" -N proj                   # Using alias
    """
    if target_note:
        resolved_path = resolve_note_ref(target_note, notebook=notebook)
        if not resolved_path:
            console.print(f"[red]Note not found: {target_note}[/red]")
            raise SystemExit(1)

        # Append the text
        with open(resolved_path, "a", encoding="utf-8") as f:
            f.write(f"\n{text}\n")

        console.print(f"[green]Added to {resolved_path.name}[/green]")
    else:
        # Default: add to today's daily note
        if notebook:
            console.print(
                "[yellow]Warning: --notebook/-n ignored without --note[/yellow]"
            )

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
@click.option("--full", "-f", is_flag=True, help="Show full path to notes")
def list_notes_cmd(
    notebook: str | None, all_notes: bool, week: bool, month: bool, full: bool
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
            console.print(str(note_path) if full else note_path.stem)
    elif notebook:
        notes = get_notebook_notes_with_linked(notebook)

        if not notes:
            console.print(f"[dim]No notes in {notebook}.[/dim]")
            return

        for note_path, is_linked, alias in notes:
            if is_linked:
                if alias:
                    console.print(
                        f"[cyan]{alias}[/cyan] [dim]({note_path if full else note_path.stem})[/dim]"
                    )
                else:
                    console.print(
                        f"[cyan]{note_path if full else note_path.stem}[/cyan] [dim](linked)[/dim]"
                    )
            else:
                console.print(str(note_path) if full else note_path.stem)
    elif all_notes:
        # List all notes in all notebooks (one line each)
        notes = get_all_notes()

        if not notes:
            console.print("[dim]No notes found.[/dim]")
            return

        current_notebook = None
        for note_path, title, nb_name, tags in notes:
            if nb_name != current_notebook:
                color, icon = get_notebook_display_info(nb_name)
                icon_prefix = f"{icon} " if icon else ""
                console.print(f"[bold {color}]{icon_prefix}{nb_name}[/bold {color}]")
                current_notebook = nb_name
            display = title if title else note_path.stem
            tags_str = " ".join(f"[yellow]#{t}[/yellow]" for t in tags) if tags else ""
            if tags_str:
                console.print(
                    f"  {display} {tags_str} [dim]({note_path if full else note_path.stem})[/dim]"
                )
            else:
                console.print(
                    f"  {display} [dim]({note_path if full else note_path.stem})[/dim]"
                )
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
                    console.print(
                        f"  {display} {tags_str} [dim]({note_path if full else note_path.stem})[/dim]"
                    )
                else:
                    console.print(
                        f"  {display} [dim]({note_path if full else note_path.stem})[/dim]"
                    )


@click.command("alias")
@click.argument("alias_name")
@click.argument("note_ref")
@click.option("--notebook", "-n", help="Notebook containing the note")
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
        raise SystemExit(1)


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
