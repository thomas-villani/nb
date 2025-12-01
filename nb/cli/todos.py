"""Todo-related CLI commands."""

from __future__ import annotations

from datetime import date, timedelta

import click

from nb.cli.completion import complete_notebook, complete_tag, complete_view
from nb.cli.utils import (
    console,
    find_todo,
    get_notebook_display_info,
    get_stdin_content,
)
from nb.config import TodoViewConfig, get_config, save_config
from nb.core.todos import (
    add_todo_to_daily_note,
    add_todo_to_inbox,
    set_todo_status_in_file,
    toggle_todo_in_file,
)
from nb.index.scanner import index_all_notes
from nb.index.todos_repo import (
    get_sorted_todos,
    get_todo_children,
    query_todos,
    update_todo_completion,
    update_todo_status,
)
from nb.models import TodoStatus
from nb.utils.dates import get_week_range
from nb.utils.editor import open_in_editor


def register_todo_commands(cli: click.Group) -> None:
    """Register all todo-related commands with the CLI."""
    cli.add_command(todo)


@click.group(invoke_without_command=True)
@click.option("--created-today", is_flag=True, help="Show only todos created today")
@click.option("--created-week", is_flag=True, help="Show only todos created this week")
@click.option("--due-today", is_flag=True, help="Show only todos due today")
@click.option("--due-week", is_flag=True, help="Show only todos due this week")
@click.option("--overdue", is_flag=True, help="Show only overdue todos")
@click.option("--priority", "-p", type=int, help="Filter by priority (1, 2, or 3)")
@click.option("--tag", "-t", help="Filter by tag", shell_complete=complete_tag)
@click.option(
    "--exclude-tag",
    "-T",
    multiple=True,
    help="Exclude todos with this tag (can be used multiple times)",
    shell_complete=complete_tag,
)
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (can be used multiple times)",
    shell_complete=complete_notebook,
)
@click.option(
    "--note",
    multiple=True,
    help="Filter by note path or linked alias (repeatable)",
)
@click.option(
    "--exclude-notebook",
    "-N",
    multiple=True,
    help="Exclude todos from this notebook (can be used multiple times)",
    shell_complete=complete_notebook,
)
@click.option(
    "--view", "-v", help="Apply a saved todo view", shell_complete=complete_view
)
@click.option("--create-view", help="Create a view from current filters")
@click.option("--list-views", is_flag=True, help="List all saved views")
@click.option("--delete-view", help="Delete a saved view")
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
    default=None,
    help="Sort todos within groups (default from config)",
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
@click.option("--limit", "-l", type=int, help="Limit the number of todos displayed")
@click.option("--offset", "-o", type=int, default=0, help="Skip the first N todos")
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
    notebook: tuple[str, ...],
    note: tuple[str, ...],
    exclude_notebook: tuple[str, ...],
    view: str | None,
    create_view: str | None,
    list_views: bool,
    delete_view: str | None,
    hide_later: bool,
    hide_no_date: bool,
    focus: bool,
    sort_by: str | None,
    show_all: bool,
    include_completed: bool,
    interactive: bool,
    limit: int | None,
    offset: int,
) -> None:
    """Manage todos.

    Run 'nb todo' without a subcommand to list todos grouped by status and due date:
    OVERDUE, IN PROGRESS, DUE TODAY, DUE THIS WEEK, DUE NEXT WEEK, DUE LATER, NO DUE DATE.

    Todos can be marked in-progress with 'nb todo start <ID>' which changes
    the marker from [ ] to [^] in the source file.

    \b
    Examples:
      nb todo                 List all open todos
      nb todo -f              Focus mode (hide later/no-date sections)
      nb todo -t work         Show only todos tagged #work
      nb todo -T waiting      Exclude todos tagged #waiting
      nb todo -p 1            Show only high priority todos
      nb todo -n daily        Show todos from 'daily' notebook only
      nb todo -n daily -n work  Filter by multiple notebooks
      nb todo --note myproject  Filter by specific note
      nb todo --note nbtodo     Filter by linked note alias
      nb todo --note a --note b  Filter by multiple notes
      nb todo -a              Include todos from excluded notebooks
      nb todo -c              Include completed todos
      nb todo -s tag          Sort by tag instead of source
      nb todo --due-today     Show only todos due today
      nb todo --created-week  Show only todos created this week

    \b
    Saved Views:
      nb todo -v myview                   Apply a saved view
      nb todo -n work --create-view work  Save current filters as 'work' view
      nb todo --list-views                List all saved views
      nb todo --delete-view work          Delete a saved view

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
      -n, --notebook NAME       Filter by notebook (repeatable for multiple)
      --note PATH               Filter by specific note path (repeatable)
      -N, --exclude-notebook    Exclude todos from this notebook (repeatable)
      -p, --priority N          Filter by priority (1=high, 2=medium, 3=low)

    \b
    Display Filters:
      --hide-later      Hide the "DUE LATER" section
      --hide-no-date    Hide the "NO DUE DATE" section
      -f, --focus       Focus mode: hide both later and no-date sections

    \b
    View Management:
      -v, --view NAME       Apply a saved todo view
      --create-view NAME    Save current filters as a named view
      --list-views          List all saved views
      --delete-view NAME    Delete a saved view

    \b
    Output Options:
      -s, --sort-by     Sort within groups: source (default), tag, priority, created
      -a, --all         Include all sources (even excluded notebooks)
      -c, --include-completed   Include completed todos
      -i, --interactive         Launch interactive TUI viewer
      -l, --limit N     Limit output to N todos
      -o, --offset N    Skip first N todos (use with --limit for pagination)

    Notebooks with todo_exclude: true in config are hidden by default.
    Notes with todo_exclude: true in frontmatter are also hidden.
    Use -a/--all to include them, or -n <notebook> to view one explicitly.

    Notebook names support fuzzy matching - if no exact match is found,
    similar notebooks will be suggested interactively.
    """
    if ctx.invoked_subcommand is None:
        config = get_config()

        # Use config default for sort_by if not specified
        if sort_by is None:
            sort_by = config.todo.default_sort

        # Handle view management commands first
        if list_views:
            _list_todo_views(config)
            return

        if delete_view:
            _delete_todo_view(config, delete_view)
            return

        # Resolve notebooks with fuzzy matching if they don't exist
        from nb.cli.utils import resolve_notebook
        from nb.utils.fuzzy import UserCancelled

        effective_notebooks: list[str] = []
        for nb_name in notebook:
            if config.get_notebook(nb_name):
                effective_notebooks.append(nb_name)
            else:
                try:
                    resolved = resolve_notebook(nb_name)
                except UserCancelled:
                    console.print("[dim]Cancelled.[/dim]")
                    raise SystemExit(1) from None
                if resolved:
                    effective_notebooks.append(resolved)
                else:
                    raise SystemExit(1)

        # Resolve notes with fuzzy matching and linked note alias support
        # Also collects section filters from ::section syntax
        from nb.cli.utils import resolve_note_for_todo_filter

        effective_notes: list[str] = []
        effective_sections: list[str] = []
        for note_ref in note:
            # Parse notebook/note format FIRST, then resolve
            # This ensures "nbcli/nbtodo" resolves alias "nbtodo" in notebook context
            nb_hint = None
            note_part = note_ref

            # Check for notebook/note format (but not if :: comes before /)
            if "/" in note_ref:
                # Handle ::section which might appear after notebook/note
                ref_without_section = (
                    note_ref.split("::")[0] if "::" in note_ref else note_ref
                )
                if "/" in ref_without_section:
                    parts = ref_without_section.split("/", 1)
                    nb_hint = parts[0]
                    # Reconstruct note_part with section if present
                    if "::" in note_ref:
                        note_part = parts[1] + "::" + note_ref.split("::", 1)[1]
                    else:
                        note_part = parts[1]

            try:
                resolved_path, section = resolve_note_for_todo_filter(
                    note_part, notebook=nb_hint
                )
            except UserCancelled:
                console.print("[dim]Cancelled.[/dim]")
                raise SystemExit(1) from None
            if resolved_path:
                effective_notes.append(resolved_path)
            elif section:
                # Section-only filter (e.g., "::Morning")
                pass
            else:
                console.print(f"[yellow]Note not found: {note_ref}[/yellow]")
                raise SystemExit(1)
            if section:
                effective_sections.append(section)

        effective_tag = tag
        effective_priority = priority
        effective_exclude_tags = list(exclude_tag) if exclude_tag else []
        effective_hide_later = hide_later or focus
        effective_hide_no_date = hide_no_date or focus
        effective_include_completed = include_completed

        if view:
            view_config = config.get_todo_view(view)
            if not view_config:
                console.print(f"[red]View not found: {view}[/red]")
                console.print("[dim]Use --list-views to see available views.[/dim]")
                raise SystemExit(1)
            # Merge view filters with CLI filters (CLI takes precedence)
            filters = view_config.filters
            if not effective_notebooks and "notebooks" in filters:
                effective_notebooks = filters["notebooks"]
            if not effective_notes and "notes" in filters:
                effective_notes = filters["notes"]
            if not effective_tag and "tag" in filters:
                effective_tag = filters["tag"]
            if not effective_priority and "priority" in filters:
                effective_priority = filters["priority"]
            if not effective_exclude_tags and "exclude_tags" in filters:
                effective_exclude_tags = filters["exclude_tags"]
            if not hide_later and not focus and filters.get("hide_later"):
                effective_hide_later = True
            if not hide_no_date and not focus and filters.get("hide_no_date"):
                effective_hide_no_date = True
            if not include_completed and filters.get("include_completed"):
                effective_include_completed = True

        # Handle --create-view (save current filters as a view)
        if create_view:
            _create_todo_view(
                config,
                create_view,
                notebooks=effective_notebooks,
                notes=effective_notes,
                tag=effective_tag,
                priority=effective_priority,
                exclude_tags=effective_exclude_tags,
                hide_later=effective_hide_later,
                hide_no_date=effective_hide_no_date,
                include_completed=effective_include_completed,
            )
            return

        # Ensure todos are indexed (skip vector indexing for speed)
        index_all_notes(index_vectors=False)

        # Get excluded notebooks from config (unless --all, specific notebooks, or specific notes requested)
        all_excluded_notebooks: list[str] | None = None
        if not show_all and not effective_notebooks and not effective_notes:
            config_excluded = config.excluded_notebooks() or []
            # Merge config exclusions with CLI exclusions
            all_excluded_notebooks = list(set(config_excluded) | set(exclude_notebook))
            if not all_excluded_notebooks:
                all_excluded_notebooks = None

        # Convert to list or None for query functions
        notebooks_filter = effective_notebooks if effective_notebooks else None
        notes_filter = effective_notes if effective_notes else None
        sections_filter = effective_sections if effective_sections else None
        exclude_tags_filter = effective_exclude_tags if effective_exclude_tags else None

        if interactive:
            # Launch interactive viewer
            from nb.tui.todos import run_interactive_todos

            run_interactive_todos(
                show_completed=effective_include_completed,
                tag=effective_tag,
                notebooks=notebooks_filter,
                exclude_notebooks=all_excluded_notebooks,
            )
        else:
            # Determine if we should exclude notes with todo_exclude
            # Don't exclude when --all, specific notebooks, or specific notes requested
            exclude_note_excluded = (
                not show_all and not effective_notebooks and not notes_filter
            )

            # Default: list todos
            _list_todos(
                created_today=created_today,
                created_week=created_week,
                due_today=due_today,
                due_week=due_week,
                overdue=overdue,
                priority=effective_priority,
                tag=effective_tag,
                exclude_tags=exclude_tags_filter,
                notebooks=notebooks_filter,
                notes=notes_filter,
                sections=sections_filter,
                exclude_notebooks=all_excluded_notebooks,
                hide_later=effective_hide_later,
                hide_no_date=effective_hide_no_date,
                sort_by=sort_by,
                include_completed=effective_include_completed,
                exclude_note_excluded=exclude_note_excluded,
                limit=limit,
                offset=offset,
            )


def _list_todo_views(config) -> None:
    """List all saved todo views."""
    views = config.todo_views
    if not views:
        console.print("[dim]No saved views.[/dim]")
        console.print(
            "[dim]Create one with: nb todo -n notebook --create-view myview[/dim]"
        )
        return

    console.print("[bold]Saved Todo Views[/bold]\n")
    for v in views:
        console.print(f"  [cyan]{v.name}[/cyan]")
        filters = v.filters
        if filters.get("notebooks"):
            console.print(f"    notebooks: {', '.join(filters['notebooks'])}")
        if filters.get("notes"):
            console.print(f"    notes: {', '.join(filters['notes'])}")
        if filters.get("tag"):
            console.print(f"    tag: #{filters['tag']}")
        if filters.get("priority"):
            console.print(f"    priority: !{filters['priority']}")
        if filters.get("exclude_tags"):
            console.print(
                f"    exclude_tags: {', '.join('#' + t for t in filters['exclude_tags'])}"
            )
        if filters.get("hide_later"):
            console.print("    hide_later: true")
        if filters.get("hide_no_date"):
            console.print("    hide_no_date: true")
        if filters.get("include_completed"):
            console.print("    include_completed: true")
        console.print()


def _delete_todo_view(config, view_name: str) -> None:
    """Delete a saved todo view."""
    view = config.get_todo_view(view_name)
    if not view:
        console.print(f"[red]View not found: {view_name}[/red]")
        raise SystemExit(1)

    config.todo_views = [v for v in config.todo_views if v.name != view_name]
    save_config(config)
    console.print(f"[green]Deleted view:[/green] {view_name}")


def _create_todo_view(
    config,
    name: str,
    notebooks: list[str] | None = None,
    notes: list[str] | None = None,
    tag: str | None = None,
    priority: int | None = None,
    exclude_tags: list[str] | None = None,
    hide_later: bool = False,
    hide_no_date: bool = False,
    include_completed: bool = False,
) -> None:
    """Create a new todo view from current filters."""
    # Build filters dict (only include non-empty values)
    filters: dict = {}
    if notebooks:
        filters["notebooks"] = notebooks
    if notes:
        filters["notes"] = notes
    if tag:
        filters["tag"] = tag
    if priority:
        filters["priority"] = priority
    if exclude_tags:
        filters["exclude_tags"] = exclude_tags
    if hide_later:
        filters["hide_later"] = True
    if hide_no_date:
        filters["hide_no_date"] = True
    if include_completed:
        filters["include_completed"] = True

    if not filters:
        console.print(
            "[red]Cannot create empty view. Specify at least one filter.[/red]"
        )
        raise SystemExit(1)

    # Check if view already exists
    existing = config.get_todo_view(name)
    if existing:
        console.print(f"[yellow]Updating existing view:[/yellow] {name}")
        config.todo_views = [v for v in config.todo_views if v.name != name]
    else:
        console.print(f"[green]Creating view:[/green] {name}")

    new_view = TodoViewConfig(name=name, filters=filters)
    config.todo_views.append(new_view)
    save_config(config)

    # Show what was saved
    console.print("[dim]Filters:[/dim]")
    for key, value in filters.items():
        if isinstance(value, list):
            console.print(f"  {key}: {', '.join(str(v) for v in value)}")
        else:
            console.print(f"  {key}: {value}")


def _list_todos(
    created_today: bool = False,
    created_week: bool = False,
    due_today: bool = False,
    due_week: bool = False,
    overdue: bool = False,
    priority: int | None = None,
    tag: str | None = None,
    exclude_tags: list[str] | None = None,
    notebooks: list[str] | None = None,
    notes: list[str] | None = None,
    sections: list[str] | None = None,
    exclude_notebooks: list[str] | None = None,
    hide_later: bool = False,
    hide_no_date: bool = False,
    sort_by: str = "source",
    include_completed: bool = False,
    exclude_note_excluded: bool = True,
    limit: int | None = None,
    offset: int = 0,
) -> None:
    """List todos with optional filters."""
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
            notebooks=notebooks,
            notes=notes,
            sections=sections,
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
            notebooks=notebooks,
            notes=notes,
            sections=sections,
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

    # Apply offset and limit for pagination
    total_count = len(todos)
    if offset > 0:
        todos = todos[offset:]
    if limit is not None:
        todos = todos[:limit]

    if not todos:
        console.print(
            f"[dim]No todos in range (offset {offset}, total {total_count}).[/dim]"
        )
        return

    # Show pagination info if limit/offset is used
    if limit is not None or offset > 0:
        end_idx = min(offset + len(todos), total_count)
        console.print(
            f"[dim]Showing {offset + 1}-{end_idx} of {total_count} todos[/dim]"
        )

    # Calculate next week range
    next_week_end = week_end + timedelta(days=7)

    # Group todos for display
    groups: dict[str, list] = {
        "OVERDUE": [],
        "IN PROGRESS": [],
        "DUE TODAY": [],
        "DUE THIS WEEK": [],
        "DUE NEXT WEEK": [],
        "DUE LATER": [],
        "NO DUE DATE": [],
    }

    for t in todos:
        # In-progress todos get their own group regardless of due date
        if t.in_progress:
            groups["IN PROGRESS"].append(t)
        elif t.due_date is None:
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
    # line_number is used as a tiebreaker to maintain document order for todos from the same source
    def get_sort_key(todo):
        if sort_by == "tag":
            return (
                todo.tags[0].lower() if todo.tags else "zzz",
                todo.content.lower(),
                todo.line_number,
            )
        elif sort_by == "priority":
            # Priority 1 is highest, None is lowest
            prio = todo.priority.value if todo.priority else 999
            return (prio, todo.content.lower(), todo.line_number)
        elif sort_by == "created":
            return (
                todo.created_date or date.min,
                todo.content.lower(),
                todo.line_number,
            )
        else:  # source (default)
            # For source sorting, put line_number before content to maintain document order
            source_str = _format_todo_source(todo)
            return (source_str.lower(), todo.line_number, todo.content.lower())

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

        console.print(f"\n[bold yellow]{group_name}[/bold yellow]")

        for t in group_todos:
            _print_todo(t, indent=0, widths=widths)


def _calculate_column_widths(todos: list) -> dict[str, int | bool]:
    """Calculate column widths for aligned todo output.

    Uses dynamic terminal width with progressive truncation:
    1. First, try full layout with all columns
    2. If too wide, eliminate "created" column
    3. If still too wide, shrink source to notebook only
    4. If still too wide, hide due date column

    Returns dict with column widths and visibility flags:
    - content, source, created, due, priority: int widths
    - show_created, show_due, compact_source: bool flags
    """
    terminal_width = console.width or 120
    # Cap terminal width to prevent excessively long lines
    # (some terminals/environments report width larger than visible area)
    terminal_width = min(terminal_width, 120)
    min_content_width = 25
    max_content_width = 60  # Don't pad content beyond this for readability

    # Calculate full source width based on actual content (min 15, max 30)
    # Account for icons which add ~2 visual chars (emoji + space)
    max_source_full = 15
    max_source_compact = 8  # notebook only
    for t in todos:
        source_str = _format_todo_source(t)
        # Check if notebook has an icon
        parts = _get_todo_source_parts(t)
        _, icon = (
            get_notebook_display_info(parts["notebook"])
            if parts["notebook"]
            else (None, None)
        )
        icon_width = 2 if icon else 0

        # Full source includes icon width
        max_source_full = max(max_source_full, len(source_str) + icon_width)
        # Compact is notebook + icon
        notebook_len = len(parts["notebook"]) if parts["notebook"] else 0
        max_source_compact = max(max_source_compact, notebook_len + icon_width)

    source_width_full = min(max_source_full, 30)
    source_width_compact = min(max_source_compact, 15)

    # Fixed widths
    created_width = 6  # "+MM/DD"
    due_width = 6  # "Mon DD"
    priority_width = 2  # "!N"
    id_width = 6

    # Base spacing: checkbox(1) + space + gaps between columns
    # With all columns: {checkbox} {content}  {source}  {created}  {due}  {priority}  {id}
    # Gaps: 2 after each column except last = 5 gaps * 2 = 10, plus checkbox overhead = 2
    base_spacing = 2 + id_width  # checkbox + id

    def calc_total(source_w: int, show_created: bool, show_due: bool) -> int:
        """Calculate total width needed for given configuration."""
        total = base_spacing + source_w + priority_width
        total += 2  # gap after content
        total += 2  # gap after source
        if show_created:
            total += created_width + 2  # column + gap
        if show_due:
            total += due_width + 2  # column + gap
        total += 2  # gap after priority
        return total

    # Try configurations in order of preference
    # 1. Full layout with all columns
    fixed_total = calc_total(source_width_full, show_created=True, show_due=True)
    content_width = min(terminal_width - fixed_total, max_content_width)
    if content_width >= min_content_width:
        return {
            "content": content_width,
            "source": source_width_full,
            "created": created_width,
            "due": due_width,
            "priority": priority_width,
            "show_created": True,
            "show_due": True,
            "compact_source": False,
        }

    # 2. Remove created column
    fixed_total = calc_total(source_width_full, show_created=False, show_due=True)
    content_width = min(terminal_width - fixed_total, max_content_width)
    if content_width >= min_content_width:
        return {
            "content": content_width,
            "source": source_width_full,
            "created": 0,
            "due": due_width,
            "priority": priority_width,
            "show_created": False,
            "show_due": True,
            "compact_source": False,
        }

    # 3. Remove created and use compact source (notebook only)
    fixed_total = calc_total(source_width_compact, show_created=False, show_due=True)
    content_width = min(terminal_width - fixed_total, max_content_width)
    if content_width >= min_content_width:
        return {
            "content": content_width,
            "source": source_width_compact,
            "created": 0,
            "due": due_width,
            "priority": priority_width,
            "show_created": False,
            "show_due": True,
            "compact_source": True,
        }

    # 4. Remove created, compact source, and hide due date
    fixed_total = calc_total(source_width_compact, show_created=False, show_due=False)
    content_width = min(
        max(terminal_width - fixed_total, min_content_width), max_content_width
    )
    return {
        "content": content_width,
        "source": source_width_compact,
        "created": 0,
        "due": 0,
        "priority": priority_width,
        "show_created": False,
        "show_due": False,
        "compact_source": True,
    }


def _format_todo_source(t, max_width: int = 0, max_section_len: int = 15) -> str:
    """Format the source of a todo for display (plain text, used for sorting).

    Format: notebook/note_title::Section (if section exists)
            notebook/note_title (if no section)

    Args:
        t: Todo object
        max_width: Maximum total width (0 = no limit). If exceeded, truncates with ellipsis.
        max_section_len: Maximum length for section name (default 15)
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
        section = parts["section"]
        if len(section) > max_section_len:
            section = section[: max_section_len - 1] + "…"
        result = f"{base_source}::{section}"
    else:
        result = base_source

    # Truncate if exceeds max_width
    if max_width > 0 and len(result) > max_width:
        result = result[: max_width - 1] + "…"

    return result


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


def _format_colored_todo_source(t, width: int = 0, max_section_len: int = 15) -> str:
    """Format the source of a todo with colors for display.

    Uses configured notebook colors and icons.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)
        max_section_len: Maximum length for section name (default 15)

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    # Check if notebook has an icon - icons take ~2 visual chars (emoji + space)
    color, icon = (
        get_notebook_display_info(parts["notebook"])
        if parts["notebook"]
        else ("white", None)
    )
    icon_width = 2 if icon else 0  # emoji + space

    # Adjust available width for text (reserve space for icon)
    text_width = max(width - icon_width, 10) if width > 0 else 0

    # Build the plain source with adjusted width
    plain_source = _format_todo_source(
        t, max_width=text_width, max_section_len=max_section_len
    )

    # Check if we need truncation
    full_plain = _format_todo_source(t, max_width=0, max_section_len=max_section_len)
    needs_truncation = text_width > 0 and len(full_plain) > text_width

    if needs_truncation:
        # Truncate: color each part that fits in the truncated string
        truncated = plain_source
        icon_prefix = f"{icon} " if icon else ""

        # Build colored version by identifying parts in the truncated string
        colored_parts = []
        remaining = truncated

        # Color notebook part
        if parts["notebook"] and remaining.startswith(parts["notebook"]):
            colored_parts.append(f"[{color}]{icon_prefix}{parts['notebook']}[/{color}]")
            remaining = remaining[len(parts["notebook"]) :]
            icon_prefix = ""  # Only show icon once
        elif parts["notebook"]:
            # Notebook itself was truncated
            colored_parts.append(f"[{color}]{icon_prefix}{remaining}[/{color}]")
            remaining = ""

        # Color "/" separator and note part
        if remaining.startswith("/") and parts["note"]:
            colored_parts.append("/")
            remaining = remaining[1:]
            # Find how much of the note fits
            if "::" in remaining:
                note_part = remaining.split("::")[0]
            else:
                note_part = remaining.rstrip("…")
                if remaining.endswith("…"):
                    note_part = remaining[:-1]  # Remove ellipsis for now
            if remaining.startswith(parts["note"]):
                colored_parts.append(f"[blue]{parts['note']}[/blue]")
                remaining = remaining[len(parts["note"]) :]
            elif note_part:
                colored_parts.append(f"[blue]{note_part}[/blue]")
                remaining = remaining[len(note_part) :]

        # Color "::" separator and section part
        if remaining.startswith("::"):
            colored_parts.append("::")
            remaining = remaining[2:]
            if remaining:
                colored_parts.append(f"[cyan]{remaining}[/cyan]")
                remaining = ""

        # Any remaining uncolored text
        if remaining:
            colored_parts.append(remaining)

        colored = "".join(colored_parts)
    else:
        # Build full colored source string
        colored_parts = []

        if parts["notebook"]:
            icon_prefix = f"{icon} " if icon else ""
            colored_parts.append(f"[{color}]{icon_prefix}{parts['notebook']}[/{color}]")

        if parts["note"]:
            if colored_parts:
                colored_parts.append("/")
            colored_parts.append(f"[blue]{parts['note']}[/blue]")

        if parts["section"]:
            section = parts["section"]
            if len(section) > max_section_len:
                section = section[: max_section_len - 1] + "…"
            colored_parts.append("::")
            colored_parts.append(f"[cyan]{section}[/cyan]")

        colored = "".join(colored_parts)

    # Calculate plain length for padding (text + icon)
    if width > 0:
        visual_len = len(plain_source) + icon_width
        if visual_len < width:
            colored += " " * (width - visual_len)

    return colored


def _format_compact_source(t, max_width: int = 0) -> str:
    """Format the source of a todo in compact mode (notebook only).

    Used when terminal is too narrow for full source display.

    Args:
        t: Todo object
        max_width: Maximum width (0 = no limit)
    """
    parts = _get_todo_source_parts(t)
    notebook = parts["notebook"] if parts["notebook"] else ""

    if max_width > 0 and len(notebook) > max_width:
        notebook = notebook[: max_width - 1] + "…"

    return notebook


def _format_colored_compact_source(t, width: int = 0) -> str:
    """Format compact source (notebook only) with colors.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    if not parts["notebook"]:
        return " " * width if width > 0 else ""

    notebook = parts["notebook"]
    color, icon = get_notebook_display_info(notebook)

    # Icons take ~2 visual chars (emoji + space)
    icon_width = 2 if icon else 0

    # Truncate notebook if needed (reserve space for icon)
    if width > 0:
        text_available = max(width - icon_width, 5)
        if len(notebook) > text_available:
            notebook = notebook[: text_available - 1] + "…"

    icon_prefix = f"{icon} " if icon else ""
    colored = f"[{color}]{icon_prefix}{notebook}[/{color}]"

    # Calculate visual length for padding (text + icon)
    if width > 0:
        visual_len = len(notebook) + icon_width
        if visual_len < width:
            colored += " " * (width - visual_len)

    return colored


def _print_todo(
    t, indent: int = 0, widths: dict[str, int | bool] | None = None
) -> None:
    """Print a single todo with formatting."""
    prefix = "  " * indent
    indent_width = len(prefix)

    # Checkbox indicator: x=completed, ^=in-progress, o=pending
    if t.completed:
        checkbox = "[green]x[/green]"
    elif t.in_progress:
        checkbox = "[yellow]^[/yellow]"
    else:
        checkbox = "[dim]o[/dim]"

    # Get visibility flags from widths
    show_created = widths.get("show_created", True) if widths else True
    show_due = widths.get("show_due", True) if widths else True
    compact_source = widths.get("compact_source", False) if widths else False

    # Build content - truncate if needed for alignment
    # Reduce content width by indent amount to keep columns aligned
    content = t.content
    base_content_width = widths["content"] if widths else len(content)
    content_width = max(base_content_width - indent_width, 10)  # minimum 10 chars
    if len(content) > content_width:
        content_display = content[: content_width - 1] + "…"
    else:
        content_display = content.ljust(content_width)

    # Build source column (colored) - compact mode shows only notebook
    source_width = widths["source"] if widths else 15
    if compact_source:
        source_str = _format_compact_source(t)
        source_part = _format_colored_compact_source(t, source_width)
    else:
        source_str = _format_todo_source(t)
        source_part = (
            _format_colored_todo_source(t, source_width)
            if source_str
            else " " * source_width
        )

    # Build metadata columns with fixed widths
    created_str = ""
    if show_created and t.created_date:
        created_str = f"+{t.created_date.strftime('%m/%d')}"

    due_str = ""
    due_color = "yellow"  # Default to yellow for future due dates
    if show_due and t.due_date:
        due_str = t.due_date.strftime("%b %d")
        # Red if due today or overdue (and not completed)
        if t.due_date <= date.today() and not t.completed:
            due_color = "red"

    priority_str = ""
    if t.priority:
        priority_str = f"!{t.priority.value}"

    # Only show tags when we have full layout (show_created = True)
    # Tags add variable width that would cause wrapping in compact modes
    tags_str = ""
    if t.tags and show_created:
        tags_str = " ".join(f"#{tag}" for tag in t.tags[:3])

    # Build the formatted line with alignment
    short_id = t.id[:6]

    # Format with Rich markup and padding
    if t.completed:
        content_part = f"[strikethrough]{content_display}[/strikethrough]"
    else:
        content_part = content_display

    priority_part = f"[magenta]{priority_str:>2}[/magenta]" if priority_str else "  "
    tags_part = f"  [cyan]{tags_str}[/cyan]" if tags_str else ""

    # Build line based on visible columns
    line_parts = [
        f"{prefix}[dim]{short_id}[/dim] {checkbox} {content_part}  {source_part}"
    ]

    if show_created:
        created_part = f"[dim]{created_str:>6}[/dim]" if created_str else " " * 6
        line_parts.append(f"  {created_part}")

    if show_due:
        due_part = f"[{due_color}]{due_str:>6}[/{due_color}]" if due_str else " " * 6
        line_parts.append(f"  {due_part}")

    line_parts.append(f"  {priority_part}{tags_part}")

    console.print("".join(line_parts))

    # Print children
    children = get_todo_children(t.id)
    for child in children:
        _print_todo(child, indent=indent + 1, widths=widths)


@todo.command("add")
@click.argument("text", required=False)
@click.option(
    "--today",
    "add_today",
    is_flag=True,
    help="Add to today's daily note instead of inbox",
)
@click.option(
    "--note",
    "-N",
    "target_note",
    help="Add to specific note (path or path::section)",
)
def todo_add(text: str | None, add_today: bool, target_note: str | None) -> None:
    """Add a new todo to the inbox (or today's note with --today).

    Accepts todo text as an argument or from stdin (piped input).
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
      nb todo add --note work/project "Document API"
      nb todo add --note work/project::Tasks "New task"

    \b
    Piping examples:
      echo "Review PR" | nb todo add               # Pipe to inbox
      pbpaste | nb todo add --today                # Pipe clipboard to daily note
      echo "Task @due(friday)" | nb todo add       # Pipe with metadata
    """
    # Check stdin first, then use argument
    content = get_stdin_content() or text

    if not content:
        console.print("[red]No todo text provided.[/red]")
        console.print(
            '[dim]Usage: nb todo add "text" or echo "text" | nb todo add[/dim]'
        )
        raise SystemExit(1)
    from nb.core.todos import add_todo_to_note

    if target_note:
        # Parse note::section syntax
        if "::" in target_note:
            note_ref, section = target_note.split("::", 1)
        else:
            note_ref = target_note
            section = None

        # Use resolve_note_ref which handles:
        # - Note aliases (from 'nb alias')
        # - Linked note aliases in notebook context (from 'nb link')
        # - notebook/note format parsing
        # - Date-based notebooks
        # - Fuzzy matching
        from nb.cli.utils import resolve_note_ref
        from nb.utils.fuzzy import UserCancelled

        try:
            resolved_path = resolve_note_ref(note_ref, ensure_exists=True)
        except UserCancelled:
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(1) from None

        if not resolved_path:
            console.print(f"[red]Note not found: {note_ref}[/red]")
            raise SystemExit(1)

        # If section specified, check for ambiguous matches
        if section:
            from rich.prompt import Prompt

            from nb.core.todos import find_matching_sections

            matches = find_matching_sections(resolved_path, section)

            if len(matches) > 1:
                # Multiple matches - prompt user to choose
                console.print(f"[yellow]Multiple sections match '{section}':[/yellow]")
                for i, (_, name) in enumerate(matches, 1):
                    console.print(f"  [cyan]{i}[/cyan]. {name}")
                console.print(
                    f"  [cyan]{len(matches) + 1}[/cyan]. Create new section '{section}'"
                )
                console.print("  [dim]0[/dim]. Cancel")

                choice = Prompt.ask(
                    "Select",
                    choices=[str(i) for i in range(len(matches) + 2)],
                    default="1",
                )

                if choice == "0":
                    console.print("[dim]Cancelled.[/dim]")
                    raise SystemExit(1)
                elif int(choice) == len(matches) + 1:
                    # User wants to create a new section
                    pass  # Keep original section name
                else:
                    # Use the selected section name
                    section = matches[int(choice) - 1][1]

        try:
            t = add_todo_to_note(content, resolved_path, section=section)
            if t.section:
                # Use t.section which has the actual matched section name
                console.print(
                    f"[green]Added to {resolved_path.name}::{t.section}:[/green] {t.content}"
                )
            else:
                console.print(
                    f"[green]Added to {resolved_path.name}:[/green] {t.content}"
                )
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None
    elif add_today:
        t = add_todo_to_daily_note(content)
        console.print(f"[green]Added to today's note:[/green] {t.content}")
    else:
        t = add_todo_to_inbox(content)
        console.print(f"[green]Added to inbox:[/green] {t.content}")
    console.print(f"[dim]ID: {t.id[:6]}[/dim]")


def _complete_todo_with_children(t) -> int:
    """Complete a todo and all its children recursively.

    Returns the count of children that were completed.
    """
    children_completed = 0
    children = get_todo_children(t.id)

    for child in children:
        if child.completed:
            continue

        # Set child to completed in source file (pass content to handle stale line numbers)
        actual_line = set_todo_status_in_file(
            child.source.path,
            child.line_number,
            TodoStatus.COMPLETED,
            expected_content=child.content,
        )
        if actual_line is not None:
            update_todo_completion(child.id, True)
            children_completed += 1

            # Recursively complete grandchildren
            children_completed += _complete_todo_with_children(child)

    return children_completed


@todo.command("done")
@click.argument("todo_id", nargs=-1)
def todo_done(todo_id: tuple[str, ...]) -> None:
    """Mark a todo as completed.

    TODO_ID can be the full ID or just the first few characters.
    The 6-character ID shown in 'nb todo' output is usually sufficient.

    If the todo has child todos (subtasks), they will also be marked as completed.

    \b
    Examples:
      nb todo done abc123
      nb todo done abc123def456...
      nb todo done abc123 def567   # Multiple IDs allowed
    """
    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if t.completed:
            console.print(f"[yellow]Todo {_todo[:6]} is already completed.[/yellow]")
            continue

        # Toggle in source file (pass content to handle stale line numbers)
        try:
            actual_line = toggle_todo_in_file(
                t.source.path, t.line_number, expected_content=t.content
            )
            if actual_line is not None:
                update_todo_completion(t.id, True)
                console.print(f"[green]Completed:[/green] {t.content}")

                # Auto-complete child todos (if enabled in config)
                config = get_config()
                if config.todo.auto_complete_children:
                    children_completed = _complete_todo_with_children(t)
                    if children_completed > 0:
                        console.print(
                            f"[dim]  Also completed {children_completed} subtask(s)[/dim]"
                        )
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("undone")
@click.argument("todo_id", nargs=-1)
def todo_undone(todo_id: tuple[str, ...]) -> None:
    """Mark a todo as incomplete (reopen it).

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo undone abc123
    """
    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if not t.completed:
            console.print(f"[yellow]Todo {_todo[:6]} is not completed.[/yellow]")
            continue

        # Toggle in source file (pass content to handle stale line numbers)
        try:
            actual_line = toggle_todo_in_file(
                t.source.path, t.line_number, expected_content=t.content
            )
            if actual_line is not None:
                update_todo_completion(t.id, False)
                console.print(f"[green]Reopened:[/green] {t.content}")
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("start")
@click.argument("todo_id", nargs=-1)
def todo_start(todo_id: tuple[str, ...]) -> None:
    """Mark a todo as in-progress.

    Changes the todo marker from [ ] to [^] in the source file.
    In-progress todos appear in their own section in 'nb todo' output.

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo start abc123
    """

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if t.completed:
            console.print(
                f"[yellow]Todo {_todo[:6]} is already completed. Use 'nb todo undone' first.[/yellow]"
            )
            continue

        if t.in_progress:
            console.print(f"[yellow]Todo {_todo[:6]} is already in progress.[/yellow]")
            continue

        # Set status in source file (pass content to handle stale line numbers)
        try:
            actual_line = set_todo_status_in_file(
                t.source.path,
                t.line_number,
                TodoStatus.IN_PROGRESS,
                expected_content=t.content,
            )
            if actual_line is not None:
                update_todo_status(t.id, TodoStatus.IN_PROGRESS)
                console.print(f"[yellow]Started:[/yellow] {t.content}")
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("pause")
@click.argument("todo_id", nargs=-1)
def todo_pause(todo_id: tuple[str, ...]) -> None:
    """Pause an in-progress todo (return to pending).

    Changes the todo marker from [^] to [ ] in the source file.

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo pause abc123
    """

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if t.completed:
            console.print(
                f"[yellow]Todo {_todo[:6]} is completed. Use 'nb todo undone' first.[/yellow]"
            )
            continue

        if not t.in_progress:
            console.print(f"[yellow]Todo {_todo[:6]} is not in progress.[/yellow]")
            continue

        # Set status in source file (pass content to handle stale line numbers)
        try:
            actual_line = set_todo_status_in_file(
                t.source.path,
                t.line_number,
                TodoStatus.PENDING,
                expected_content=t.content,
            )
            if actual_line is not None:
                update_todo_status(t.id, TodoStatus.PENDING)
                console.print(f"[dim]Paused:[/dim] {t.content}")
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("due")
@click.argument("todo_id", nargs=-1)
@click.argument("date_expr")
def todo_due(todo_id: tuple[str, ...], date_expr: str) -> None:
    """Set or clear the due date for a todo.

    \b
    DATE_EXPR can be:
    - A date: "2025-12-15", "dec 15", "tomorrow", "friday"
    - "none" or "clear" to remove the due date

    Note: "friday" means the NEXT Friday (future), not the most recent.

    \b
    Examples:
      nb todo due abc123 friday       # Set due to next Friday
      nb todo due abc123 tomorrow
      nb todo due abc123 "dec 25"
      nb todo due abc123 2025-12-15
      nb todo due abc123 none         # Remove due date
      nb todo due abc def friday      # Multiple IDs
    """
    from nb.core.todos import remove_todo_due_date, update_todo_due_date
    from nb.index.todos_repo import update_todo_due_date_db
    from nb.utils.dates import is_clear_date_keyword, parse_fuzzy_date_future

    # Check if we should clear the due date
    is_clear = is_clear_date_keyword(date_expr)

    if not is_clear:
        new_date = parse_fuzzy_date_future(date_expr)
        if not new_date:
            console.print(f"[red]Could not parse date: {date_expr}[/red]")
            console.print(
                "[dim]Try: tomorrow, friday, next monday, dec 15, 2025-12-15, or 'none' to clear[/dim]"
            )
            raise SystemExit(1)
    else:
        new_date = None

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        try:
            if is_clear:
                # Remove due date from file
                actual_line = remove_todo_due_date(
                    t.source.path,
                    t.line_number,
                    expected_content=t.content,
                )
            else:
                # Update due date in file
                assert new_date is not None  # Guaranteed by is_clear check above
                actual_line = update_todo_due_date(
                    t.source.path,
                    t.line_number,
                    new_date,
                    expected_content=t.content,
                )

            if actual_line is not None:
                # Update database
                update_todo_due_date_db(t.id, new_date)

                if is_clear:
                    console.print(f"[green]Cleared due date:[/green] {t.content}")
                else:
                    assert new_date is not None
                    console.print(
                        f"[green]Due {new_date.strftime('%b %d')}:[/green] {t.content}"
                    )
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


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
    t = find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    console.print(f"\n[bold]{t.content}[/bold]")
    console.print(f"ID: {t.id}")
    # Show status
    if t.completed:
        status_str = "Completed"
    elif t.in_progress:
        status_str = "In Progress"
    else:
        status_str = "Pending"
    console.print(f"Status: {status_str}")
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
    t = find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    config = get_config()
    console.print(f"[dim]Opening {t.source.path.name}:{t.line_number}...[/dim]")
    open_in_editor(t.source.path, line=t.line_number, editor=config.editor)


def _delete_todo_with_children(t, force: bool = False) -> int:
    """Delete a todo and all its children recursively.

    Returns the count of children that were deleted.
    """
    from nb.core.todos import delete_todo_from_file
    from nb.index.todos_repo import delete_todo

    children_deleted = 0
    children = get_todo_children(t.id)

    # Delete children first (bottom-up to preserve line numbers)
    for child in reversed(children):
        children_deleted += _delete_todo_with_children(child, force=True)

    # Delete from source file (pass content to handle stale line numbers)
    try:
        actual_line = delete_todo_from_file(
            t.source.path, t.line_number, expected_content=t.content
        )
        if actual_line is not None:
            delete_todo(t.id)
            return children_deleted + 1
    except PermissionError as e:
        console.print(f"[red]{e}[/red]")
        console.print(
            "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
        )

    return children_deleted


@todo.command("delete")
@click.argument("todo_id", nargs=-1)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def todo_delete(todo_id: tuple[str, ...], force: bool) -> None:
    """Delete a todo from the source file and database.

    TODO_ID can be the full ID or just the first few characters.
    The 6-character ID shown in 'nb todo' output is usually sufficient.

    If the todo has child todos (subtasks), they will also be deleted.

    \b
    Examples:
      nb todo delete abc123
      nb todo delete abc123 def456   # Multiple IDs
      nb todo delete abc123 -f       # Skip confirmation
    """
    from rich.prompt import Confirm

    if not todo_id:
        console.print("[yellow]No todo ID provided.[/yellow]")
        raise SystemExit(1)

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            continue

        # Check for children
        children = get_todo_children(t.id)
        children_count = len(children)

        # Show confirmation unless --force
        if not force:
            console.print(f"\n[bold]Delete todo:[/bold] {t.content}")
            console.print(f"[dim]Source: {t.source.path.name}:{t.line_number}[/dim]")
            if children_count > 0:
                console.print(
                    f"[yellow]This will also delete {children_count} subtask(s).[/yellow]"
                )

            if not Confirm.ask("Are you sure?", default=False):
                console.print("[dim]Cancelled.[/dim]")
                continue

        # Delete the todo and its children
        try:
            deleted_count = _delete_todo_with_children(t, force=True)
            if deleted_count > 0:
                if children_count > 0:
                    console.print(
                        f"[green]Deleted:[/green] {t.content} [dim](+{children_count} subtask(s))[/dim]"
                    )
                else:
                    console.print(f"[green]Deleted:[/green] {t.content}")
            else:
                console.print("[red]Failed to delete todo from source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )


@todo.command("review")
@click.option(
    "--weekly", "-w", is_flag=True, help="Include this week + no-due-date items"
)
@click.option(
    "--all",
    "-a",
    "show_all",
    is_flag=True,
    help="Review all incomplete todos",
)
@click.option("--tag", "-t", help="Filter by tag", shell_complete=complete_tag)
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (can be used multiple times)",
    shell_complete=complete_notebook,
)
@click.option(
    "--note",
    multiple=True,
    help="Filter by note path (can be used multiple times)",
)
@click.option(
    "--exclude-notebook",
    "-N",
    multiple=True,
    help="Exclude todos from this notebook (can be used multiple times)",
    shell_complete=complete_notebook,
)
def todo_review(
    weekly: bool,
    show_all: bool,
    tag: str | None,
    notebook: tuple[str, ...],
    note: tuple[str, ...],
    exclude_notebook: tuple[str, ...],
) -> None:
    """Interactively review and triage todos.

    Opens an interactive TUI to quickly process overdue and upcoming todos.
    Use keyboard shortcuts to mark done, reschedule, or delete items.

    \b
    Scopes:
      (default)   Overdue + due today
      --weekly    Overdue + this week + items with no due date
      --all       All incomplete todos

    \b
    Actions (in TUI):
      d  Mark done         t  Reschedule to tomorrow
      f  This Friday       F  Next Friday
      w  Next Monday       n  Next month
      e  Edit in editor    s  Skip (move to next)
      x  Delete            q  Quit review

    \b
    Navigation:
      j/k  Move up/down    [/]  Previous/next page

    \b
    Examples:
      nb todo review              Review overdue + due today
      nb todo review --weekly     Include this week's todos
      nb todo review --all        Review everything incomplete
      nb todo review -t work      Review only #work tagged todos
      nb todo review -n daily     Review only from daily notebook
    """
    from nb.cli.utils import resolve_notebook
    from nb.tui.review import run_review
    from nb.utils.fuzzy import UserCancelled

    config = get_config()

    # Determine scope
    if show_all:
        scope = "all"
    elif weekly:
        scope = "weekly"
    else:
        scope = "daily"

    # Resolve notebooks with fuzzy matching
    effective_notebooks: list[str] = []
    for nb_name in notebook:
        if config.get_notebook(nb_name):
            effective_notebooks.append(nb_name)
        else:
            try:
                resolved = resolve_notebook(nb_name)
            except UserCancelled:
                console.print("[dim]Cancelled.[/dim]")
                raise SystemExit(1) from None
            if resolved:
                effective_notebooks.append(resolved)
            else:
                raise SystemExit(1)

    # Resolve notes
    from nb.cli.utils import resolve_note_for_todo_filter

    effective_notes: list[str] = []
    for note_ref in note:
        try:
            resolved_path, _ = resolve_note_for_todo_filter(note_ref)
        except UserCancelled:
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(1) from None
        if resolved_path:
            effective_notes.append(resolved_path)
        else:
            console.print(f"[yellow]Note not found: {note_ref}[/yellow]")
            raise SystemExit(1)

    # Get excluded notebooks from config if not filtering by specific notebooks
    all_excluded_notebooks: list[str] | None = None
    if not effective_notebooks and not effective_notes:
        config_excluded = config.excluded_notebooks() or []
        all_excluded_notebooks = list(set(config_excluded) | set(exclude_notebook))
        if not all_excluded_notebooks:
            all_excluded_notebooks = None

    # Convert to proper types
    notebooks_filter = effective_notebooks if effective_notebooks else None
    notes_filter = effective_notes if effective_notes else None

    # Run the review TUI
    run_review(
        scope=scope,
        tag=tag,
        notebooks=notebooks_filter,
        notes=notes_filter,
        exclude_notebooks=all_excluded_notebooks,
    )


@todo.command("all-done")
@click.argument("note_ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook to search in",
    shell_complete=complete_notebook,
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def todo_all_done(note_ref: str, notebook: str | None, force: bool) -> None:
    """Mark all todos in a note as completed.

    NOTE_REF can be:
    - A note name: "myproject", "friday"
    - A notebook/note path: "work/myproject", "daily/friday"
    - A note alias (from 'nb alias')

    \b
    Examples:
      nb todo all-done friday                 # Friday's daily note
      nb todo all-done myproject -n work      # work/myproject.md
      nb todo all-done work/myproject         # Same as above
      nb todo all-done myalias                # By alias
      nb todo all-done friday -f              # Skip confirmation
    """
    from rich.prompt import Confirm

    from nb.cli.utils import resolve_note_ref
    from nb.utils.fuzzy import UserCancelled
    from nb.utils.hashing import normalize_path

    # Handle notebook/note format in note_ref
    if "/" in note_ref and not notebook:
        parts = note_ref.split("/", 1)
        notebook = parts[0]
        note_ref = parts[1]

    # Resolve the note
    try:
        note_path = resolve_note_ref(note_ref, notebook=notebook, ensure_exists=True)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if not note_path:
        console.print(f"[red]Note not found: {note_ref}[/red]")
        raise SystemExit(1)

    # Query incomplete todos for this note
    normalized_path = normalize_path(note_path)
    todos = query_todos(
        completed=False,
        notes=[normalized_path],
        parent_only=False,  # Include subtasks
        exclude_note_excluded=False,  # Don't exclude - user explicitly asked
    )

    if not todos:
        console.print(f"[dim]No incomplete todos in {note_path.name}[/dim]")
        return

    # Show confirmation unless --force
    if not force:
        console.print(f"\n[bold]Mark all todos as done in:[/bold] {note_path.name}")
        console.print(f"[dim]Found {len(todos)} incomplete todo(s)[/dim]")

        for t in todos[:5]:
            console.print(
                f"  [dim]o[/dim] {t.content[:50]}{'...' if len(t.content) > 50 else ''}"
            )
        if len(todos) > 5:
            console.print(f"  [dim]... and {len(todos) - 5} more[/dim]")

        if not Confirm.ask("Mark all as completed?", default=True):
            console.print("[dim]Cancelled.[/dim]")
            return

    # Mark each todo as complete
    completed_count = 0
    for t in todos:
        try:
            actual_line = set_todo_status_in_file(
                t.source.path,
                t.line_number,
                TodoStatus.COMPLETED,
                expected_content=t.content,
            )
            if actual_line is not None:
                update_todo_status(t.id, TodoStatus.COMPLETED)
                completed_count += 1
        except PermissionError:
            # Skip linked files without sync, but don't fail entirely
            pass

    console.print(
        f"[green]Completed {completed_count} todo(s)[/green] in {note_path.name}"
    )
