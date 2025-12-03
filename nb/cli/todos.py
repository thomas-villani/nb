"""Todo-related CLI commands."""

from __future__ import annotations

import sys
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
@click.option("--today", "-T", is_flag=True, help="Show only todos due today")
@click.option("--week", "-W", is_flag=True, help="Show only todos due this week")
@click.option("--overdue", is_flag=True, help="Show only overdue todos")
@click.option("--priority", "-p", type=int, help="Filter by priority (1, 2, or 3)")
@click.option("--tag", "-t", help="Filter by tag", shell_complete=complete_tag)
@click.option(
    "--exclude-tag",
    "-xt",
    multiple=True,
    help="Exclude todos with this tag (repeatable)",
    shell_complete=complete_tag,
)
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (repeatable)",
    shell_complete=complete_notebook,
)
@click.option(
    "--note",
    multiple=True,
    help="Filter by note path or linked alias (repeatable)",
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
    help="Exclude todos from this section (repeatable)",
)
@click.option(
    "--exclude-notebook",
    "-N",
    multiple=True,
    help="Exclude todos from this notebook (repeatable)",
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
    help="Focus mode: hide later/no-date; hide next week if this week has items",
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
@click.option(
    "--expand",
    "-x",
    is_flag=True,
    help="Expanded view: show more content (up to 80 chars), hide source/due as needed",
)
@click.option(
    "--kanban",
    "-k",
    is_flag=True,
    help="Display todos in kanban board columns",
)
@click.option(
    "--board",
    "-b",
    default="default",
    help="Kanban board name to use (default: 'default')",
)
@click.pass_context
def todo(
    ctx: click.Context,
    created_today: bool,
    created_week: bool,
    today: bool,
    week: bool,
    overdue: bool,
    priority: int | None,
    tag: str | None,
    exclude_tag: tuple[str, ...],
    notebook: tuple[str, ...],
    note: tuple[str, ...],
    section: tuple[str, ...],
    exclude_section: tuple[str, ...],
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
    expand: bool,
    kanban: bool,
    board: str,
) -> None:
    """Manage todos.

    Run 'nb todo' without a subcommand to list todos grouped by status and due date:
    OVERDUE, IN PROGRESS, DUE TODAY, DUE TOMORROW, DUE THIS WEEK, DUE NEXT WEEK, DUE LATER, NO DUE DATE.

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
      -f, --focus       Focus mode: hide later/no-date and next week (if this week has items)

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
                resolved_path, note_section = resolve_note_for_todo_filter(
                    note_part, notebook=nb_hint
                )
            except UserCancelled:
                console.print("[dim]Cancelled.[/dim]")
                raise SystemExit(1) from None
            if resolved_path:
                effective_notes.append(resolved_path)
            elif note_section:
                # Section-only filter (e.g., "::Morning")
                pass
            else:
                console.print(f"[yellow]Note not found: {note_ref}[/yellow]")
                raise SystemExit(1)
            if note_section:
                effective_sections.append(note_section)

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

        if kanban:
            # Display kanban board view
            _display_kanban(
                notebooks=notebooks_filter,
                exclude_notebooks=all_excluded_notebooks,
                board_name=board,
            )
        elif interactive:
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
                due_today=today,
                due_week=week,
                overdue=overdue,
                priority=effective_priority,
                tag=effective_tag,
                exclude_tags=exclude_tags_filter,
                notebooks=notebooks_filter,
                notes=notes_filter,
                sections=sections_filter,
                exclude_notebooks=all_excluded_notebooks,
                path_sections=list(section) if section else None,
                exclude_path_sections=(
                    list(exclude_section) if exclude_section else None
                ),
                hide_later=effective_hide_later,
                hide_no_date=effective_hide_no_date,
                focus=focus,
                sort_by=sort_by,
                include_completed=effective_include_completed,
                exclude_note_excluded=exclude_note_excluded,
                limit=limit,
                offset=offset,
                expand=expand,
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


def _display_kanban(
    notebooks: list[str] | None = None,
    exclude_notebooks: list[str] | None = None,
    board_name: str = "default",
) -> None:
    """Display todos in a kanban board layout using Rich."""

    from rich.columns import Columns
    from rich.panel import Panel

    from nb.config import DEFAULT_KANBAN_COLUMNS, KanbanBoardConfig, get_config

    config = get_config()
    today = date.today()

    # Get board configuration
    board = config.get_kanban_board(board_name)
    if not board:
        # Use default board if not found or if no boards configured
        if board_name != "default":
            console.print(
                f"[yellow]Board '{board_name}' not found, using default.[/yellow]"
            )
        board = KanbanBoardConfig(name="default", columns=DEFAULT_KANBAN_COLUMNS)

    # Calculate responsive column width based on terminal size
    term_width = console.width or 120
    term_height = console.height or 40
    num_columns = len(board.columns)
    # Account for gaps between columns (2 chars each) and some padding
    available_width = term_width - (num_columns - 1) * 2 - 4
    # Calculate per-column width, with min 30 and max 60
    column_width = max(30, min(60, available_width // num_columns))
    # Content width is column width minus panel borders/padding (4 chars)
    max_content_len = column_width - 6
    # Calculate max items per column based on terminal height
    # Each item is ~1 line, plus header (3 lines) and footer
    max_items = max(8, min(25, term_height - 8))

    # Query todos for each column and build panels
    column_panels = []
    for col in board.columns:
        todos = _query_todos_for_kanban_column(
            col.filters, notebooks, exclude_notebooks, today
        )

        # Build column content
        lines = []
        for t in todos[:max_items]:  # Limit items per column based on terminal height
            # Priority indicator
            priority_str = f"[red]!{t.priority.value}[/red] " if t.priority else ""

            # Content (truncated based on available width)
            content = priority_str + t.content

            if len(content) > max_content_len:
                content = content[: max_content_len - 3] + "..."
            lines.append(content)

        if len(todos) > max_items:
            lines.append(f"[dim]+{len(todos) - max_items} more[/dim]")

        content_str = "\n".join(lines) if lines else "[dim]No items[/dim]"
        panel = Panel(
            content_str,
            title=f"[bold {col.color}]{col.name}[/bold {col.color}] ({len(todos)})",
            border_style=col.color,
            width=column_width,
        )
        column_panels.append(panel)

    # Print board header
    console.print(f"\n[bold]Kanban Board[/bold]: {board.name}\n")

    # Print columns
    console.print(Columns(column_panels, equal=True, expand=True))
    console.print()


def _query_todos_for_kanban_column(
    filters: dict,
    notebooks: list[str] | None,
    exclude_notebooks: list[str] | None,
    today: date,
) -> list:
    """Query todos matching kanban column filters."""
    from datetime import timedelta

    # Map filter keys to query_todos parameters
    kwargs: dict = {
        "notebooks": notebooks,
        "exclude_notebooks": exclude_notebooks,
        "parent_only": True,
        "exclude_note_excluded": True,
    }

    # Handle status filter
    status_val = filters.get("status")
    if status_val:
        kwargs["status"] = TodoStatus(status_val)
    else:
        # Default to non-completed
        kwargs["completed"] = False

    # Handle due date filters
    if filters.get("due_today"):
        kwargs["due_start"] = today
        kwargs["due_end"] = today

    if filters.get("due_this_week"):
        kwargs["due_start"] = today
        kwargs["due_end"] = today + timedelta(days=7)

    if filters.get("overdue"):
        kwargs["overdue"] = True

    # Handle priority filter
    if filters.get("priority"):
        kwargs["priority"] = filters["priority"]

    # Handle tags filter
    if filters.get("tags") and len(filters["tags"]) > 0:
        kwargs["tag"] = filters["tags"][0]

    # Query todos
    todos = query_todos(**kwargs)

    # Post-filter for no_due_date (can't easily do this in SQL query)
    if filters.get("no_due_date"):
        todos = [t for t in todos if t.due_date is None]

    return todos


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
    path_sections: list[str] | None = None,
    exclude_path_sections: list[str] | None = None,
    hide_later: bool = False,
    hide_no_date: bool = False,
    focus: bool = False,
    sort_by: str = "source",
    include_completed: bool = False,
    exclude_note_excluded: bool = True,
    limit: int | None = None,
    offset: int = 0,
    expand: bool = False,
) -> None:
    """List todos with optional filters."""
    # Determine completion filter
    completed = None if include_completed else False

    # Calculate date ranges for filters
    today_date = date.today()
    tomorrow_date = today_date + timedelta(days=1)
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
            path_sections=path_sections,
            exclude_path_sections=exclude_path_sections,
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
            path_sections=path_sections,
            exclude_path_sections=exclude_path_sections,
        )

    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return

    # Calculate next week range
    next_week_end = week_end + timedelta(days=7)

    # Group todos for display
    groups: dict[str, list] = {
        "OVERDUE": [],
        "IN PROGRESS": [],
        "DUE TODAY": [],
        "DUE TOMORROW": [],
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
        else:
            # Use due_date_only for date comparisons (due_date may be datetime)
            due = t.due_date_only
            assert due is not None  # guaranteed since t.due_date is not None
            if due < today_date:
                groups["OVERDUE"].append(t)
            elif due == today_date:
                groups["DUE TODAY"].append(t)
            elif due == tomorrow_date:
                groups["DUE TOMORROW"].append(t)
            elif due <= week_end:
                groups["DUE THIS WEEK"].append(t)
            elif due <= next_week_end:
                groups["DUE NEXT WEEK"].append(t)
            else:
                groups["DUE LATER"].append(t)

    # Apply hide filters
    if hide_later:
        groups["DUE LATER"] = []
    if hide_no_date:
        groups["NO DUE DATE"] = []

    # In focus mode, hide "DUE NEXT WEEK" if there are items in earlier groups
    if focus:
        earlier_groups = [
            "OVERDUE",
            "IN PROGRESS",
            "DUE TODAY",
            "DUE TOMORROW",
            "DUE THIS WEEK",
        ]
        has_earlier_items = any(groups[g] for g in earlier_groups)
        if has_earlier_items:
            groups["DUE NEXT WEEK"] = []

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
        else:  # default: sort by due date, then line_number to preserve document order
            due = todo.due_date_only if todo.due_date else date.max
            return (due, todo.line_number, todo.content.lower())

    for group_todos in groups.values():
        group_todos.sort(key=get_sort_key)

    # Apply offset and limit AFTER grouping and sorting
    # This ensures the user sees the first N todos in display order
    if limit is not None or offset > 0:
        # Flatten groups in display order
        group_order = [
            "OVERDUE",
            "IN PROGRESS",
            "DUE TODAY",
            "DUE TOMORROW",
            "DUE THIS WEEK",
            "DUE NEXT WEEK",
            "DUE LATER",
            "NO DUE DATE",
        ]
        all_todos_ordered = []
        for group_name in group_order:
            all_todos_ordered.extend(groups[group_name])

        total_count = len(all_todos_ordered)

        # Apply offset and limit
        if offset > 0:
            all_todos_ordered = all_todos_ordered[offset:]
        if limit is not None:
            all_todos_ordered = all_todos_ordered[:limit]

        if not all_todos_ordered:
            console.print(
                f"[dim]No todos in range (offset {offset}, total {total_count}).[/dim]"
            )
            return

        # Show pagination info
        end_idx = min(offset + len(all_todos_ordered), total_count)
        console.print(
            f"[dim]Showing {offset + 1}-{end_idx} of {total_count} todos[/dim]"
        )

        # Rebuild groups from the sliced list
        groups = {name: [] for name in group_order}
        for t in all_todos_ordered:
            if t.in_progress:
                groups["IN PROGRESS"].append(t)
            elif t.due_date is None:
                groups["NO DUE DATE"].append(t)
            else:
                due = t.due_date_only
                if due < today_date:
                    groups["OVERDUE"].append(t)
                elif due == today_date:
                    groups["DUE TODAY"].append(t)
                elif due == tomorrow_date:
                    groups["DUE TOMORROW"].append(t)
                elif due <= week_end:
                    groups["DUE THIS WEEK"].append(t)
                elif due <= next_week_end:
                    groups["DUE NEXT WEEK"].append(t)
                else:
                    groups["DUE LATER"].append(t)

    # Collect all visible todos for column width calculation
    all_visible_todos = []
    for group_todos in groups.values():
        all_visible_todos.extend(group_todos)

    if not all_visible_todos:
        console.print("[dim]No todos found.[/dim]")
        return

    # Calculate column widths for alignment
    # Hide notebook in source column when filtering to a single notebook
    hide_notebook = notebooks is not None and len(notebooks) == 1
    widths = _calculate_column_widths(
        all_visible_todos, hide_notebook=hide_notebook, expand=expand
    )

    # Display
    for group_name, group_todos in groups.items():
        if not group_todos:
            continue

        console.print(f"\n[bold yellow]{group_name}[/bold yellow]")

        for t in group_todos:
            _print_todo(t, indent=0, widths=widths)


def _calculate_column_widths(
    todos: list, hide_notebook: bool = False, expand: bool = False
) -> dict[str, int | bool]:
    """Calculate column widths for aligned todo output.

    Uses dynamic terminal width with progressive truncation:
    1. Full layout with all columns + tags (wide terminals, >130)
    2. No created/tags, no-section source (medium terminals, 90-130)
    3. No created/tags, compact source - notebook only (narrower)
    4. Minimal - hide due date column (very narrow)

    When expand=True, prioritizes content width (up to 80 chars) and hides
    source/due columns as needed to fit.

    Args:
        todos: List of todos to calculate widths for
        hide_notebook: If True, source column shows only note (not notebook/note)
        expand: If True, maximize content width and hide source/due as needed

    Returns dict with column widths and visibility flags:
    - content, source, created, due, priority: int widths
    - show_created, show_due, compact_source, nosection_source, hide_notebook: bool flags
    """
    terminal_width = console.width or 120
    # Cap terminal width to prevent excessively long lines
    # (some terminals/environments report width larger than visible area)
    terminal_width = min(terminal_width, 150)
    min_content_width = 25
    max_content_width = 60  # Don't pad content beyond this for readability

    # Calculate full source width based on actual content (min 15, max 30)
    # Account for icons which add ~2 visual chars (emoji + space)
    # When hide_notebook=True, don't include notebook or icon in width calculation
    max_source_full = 15
    max_source_nosection = 12  # notebook/note without section
    max_source_compact = 8  # notebook only
    for t in todos:
        parts = _get_todo_source_parts(t)
        _, icon = (
            get_notebook_display_info(parts["notebook"])
            if parts["notebook"]
            else (None, None)
        )
        # No icon when hiding notebook
        icon_width = 0 if hide_notebook else (2 if icon else 0)

        if hide_notebook:
            # Source is just note::section or note
            note = parts["note"] or ""
            section = parts["section"] or ""
            if section:
                source_str = f"{note}::{section}"
            else:
                source_str = note
            nosection_str = note
        else:
            source_str = _format_todo_source(t)
            nosection_str = _format_nosection_source(t)

        # Full source includes icon width
        max_source_full = max(max_source_full, len(source_str) + icon_width)
        # No-section source (notebook/note or just note)
        max_source_nosection = max(
            max_source_nosection, len(nosection_str) + icon_width
        )
        # Compact is notebook + icon (or just note when hiding)
        if hide_notebook:
            note_len = len(parts["note"]) if parts["note"] else 0
            max_source_compact = max(max_source_compact, note_len)
        else:
            notebook_len = len(parts["notebook"]) if parts["notebook"] else 0
            max_source_compact = max(max_source_compact, notebook_len + icon_width)

    source_width_full = min(max_source_full, 30)
    source_width_nosection = min(max_source_nosection, 25)
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

    def calc_total_no_source(show_due: bool) -> int:
        """Calculate total width needed without source column."""
        total = base_spacing + priority_width
        total += 2  # gap after content
        if show_due:
            total += due_width + 2  # column + gap
        total += 2  # gap after priority
        return total

    # Expanded view mode: maximize content width, show only id + source + content
    # Hide created, due, and priority to give maximum room for todo text
    if expand:
        # Base spacing: id(6) + checkbox(1) + space + gap after content + gap after source
        expand_base = id_width + 2 + 2 + 2  # 12 chars overhead

        # Try with full source
        fixed_total = expand_base + source_width_full
        content_width = terminal_width - fixed_total
        if content_width >= min_content_width:
            return {
                "content": content_width,
                "source": source_width_full,
                "created": 0,
                "due": 0,
                "priority": 0,
                "show_created": False,
                "show_due": False,
                "show_priority": False,
                "compact_source": False,
                "nosection_source": False,
                "hide_notebook": hide_notebook,
                "hide_source": False,
            }

        # Try with compact source
        fixed_total = expand_base + source_width_compact
        content_width = terminal_width - fixed_total
        if content_width >= min_content_width:
            return {
                "content": content_width,
                "source": source_width_compact,
                "created": 0,
                "due": 0,
                "priority": 0,
                "show_created": False,
                "show_due": False,
                "show_priority": False,
                "compact_source": True,
                "nosection_source": False,
                "hide_notebook": hide_notebook,
                "hide_source": False,
            }

        # Fallback: hide source too, maximize content
        fixed_total = id_width + 2 + 2  # id + checkbox + gap
        content_width = max(terminal_width - fixed_total, min_content_width)
        return {
            "content": content_width,
            "source": 0,
            "created": 0,
            "due": 0,
            "priority": 0,
            "show_created": False,
            "show_due": False,
            "show_priority": False,
            "compact_source": False,
            "nosection_source": False,
            "hide_notebook": hide_notebook,
            "hide_source": True,
        }

    # Try configurations in order of preference
    # Use explicit width thresholds for better control over medium-width terminals
    #
    # Tags add variable width (only shown in full layout with show_created=True)
    # so we need extra buffer for step 1 to avoid wrapping

    # 1. Full layout with all columns (wide terminals, typically > 130)
    # Requires extra room for tags (estimate ~20 chars for up to 3 tags)
    fixed_total = calc_total(source_width_full, show_created=True, show_due=True)
    tags_buffer = 20  # Space for tags which aren't in calc_total
    content_width = min(terminal_width - fixed_total - tags_buffer, max_content_width)
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
            "nosection_source": False,
            "hide_notebook": hide_notebook,
            "hide_source": False,
        }

    # 2. Remove created/tags and use no-section source (medium terminals, 90-130)
    # Tags are not shown when show_created=False, so no buffer needed
    fixed_total = calc_total(source_width_nosection, show_created=False, show_due=True)
    content_width = min(terminal_width - fixed_total, max_content_width)
    if content_width >= min_content_width:
        return {
            "content": content_width,
            "source": source_width_nosection,
            "created": 0,
            "due": due_width,
            "priority": priority_width,
            "show_created": False,
            "show_due": True,
            "compact_source": False,
            "nosection_source": True,
            "hide_notebook": hide_notebook,
            "hide_source": False,
        }

    # 3. Remove created and use compact source (notebook only, narrower terminals)
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
            "nosection_source": False,
            "hide_notebook": hide_notebook,
            "hide_source": False,
        }

    # 4. Remove created, compact source, and hide due date (very narrow)
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
        "nosection_source": False,
        "hide_notebook": hide_notebook,
        "hide_source": False,
    }


def _format_todo_source(
    t, max_width: int = 0, max_section_len: int = 15, hide_notebook: bool = False
) -> str:
    """Format the source of a todo for display (plain text, used for sorting).

    Format: notebook/note_title::Section (if section exists)
            notebook/note_title (if no section)
            note_title::Section (if hide_notebook and section exists)
            note_title (if hide_notebook and no section)

    Args:
        t: Todo object
        max_width: Maximum total width (0 = no limit). If exceeded, truncates with ellipsis.
        max_section_len: Maximum length for section name (default 15)
        hide_notebook: If True, omit notebook from output (show only note)
    """
    parts = _get_todo_source_parts(t)
    if not parts["notebook"] and not parts["note"]:
        return ""

    base_source = ""
    if hide_notebook:
        # Only show note, not notebook
        base_source = parts["note"] or ""
    elif parts["notebook"] and parts["note"]:
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


def _format_colored_todo_source(
    t, width: int = 0, max_section_len: int = 15, hide_notebook: bool = False
) -> str:
    """Format the source of a todo with colors for display.

    Uses configured notebook colors and icons.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)
        max_section_len: Maximum length for section name (default 15)
        hide_notebook: If True, omit notebook and icon from output

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    # Check if notebook has an icon - icons take ~2 visual chars (emoji + space)
    # No icon when hiding notebook
    if hide_notebook:
        color, icon = "white", None
    else:
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
        t,
        max_width=text_width,
        max_section_len=max_section_len,
        hide_notebook=hide_notebook,
    )

    # Check if we need truncation
    full_plain = _format_todo_source(
        t, max_width=0, max_section_len=max_section_len, hide_notebook=hide_notebook
    )
    needs_truncation = text_width > 0 and len(full_plain) > text_width

    if needs_truncation:
        # Truncate: color each part that fits in the truncated string
        truncated = plain_source
        icon_prefix = f"{icon} " if icon else ""

        # Build colored version by identifying parts in the truncated string
        colored_parts = []
        remaining = truncated

        # Color notebook part (skip if hiding notebook)
        if (
            not hide_notebook
            and parts["notebook"]
            and remaining.startswith(parts["notebook"])
        ):
            colored_parts.append(f"[{color}]{icon_prefix}{parts['notebook']}[/{color}]")
            remaining = remaining[len(parts["notebook"]) :]
            icon_prefix = ""  # Only show icon once
        elif not hide_notebook and parts["notebook"]:
            # Notebook itself was truncated
            colored_parts.append(f"[{color}]{icon_prefix}{remaining}[/{color}]")
            remaining = ""

        # Color "/" separator and note part (skip "/" if hiding notebook)
        if not hide_notebook and remaining.startswith("/") and parts["note"]:
            colored_parts.append("/")
            remaining = remaining[1:]

        # Color note part
        if parts["note"] and remaining:
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

        if not hide_notebook and parts["notebook"]:
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


def _format_nosection_source(t, max_width: int = 0, hide_notebook: bool = False) -> str:
    """Format the source of a todo without section (notebook/note only).

    Used for medium-width terminals where full source with section is too wide,
    but compact (notebook only) loses too much context.

    Args:
        t: Todo object
        max_width: Maximum width (0 = no limit)
        hide_notebook: If True, show only note name
    """
    parts = _get_todo_source_parts(t)
    if not parts["notebook"] and not parts["note"]:
        return ""

    if hide_notebook:
        result = parts["note"] or ""
    elif parts["notebook"] and parts["note"]:
        result = f"{parts['notebook']}/{parts['note']}"
    elif parts["notebook"]:
        result = parts["notebook"]
    else:
        result = parts["note"]

    if max_width > 0 and len(result) > max_width:
        result = result[: max_width - 1] + "…"

    return result


def _format_colored_nosection_source(
    t, width: int = 0, hide_notebook: bool = False
) -> str:
    """Format source without section (notebook/note) with colors.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)
        hide_notebook: If True, omit notebook and icon from output

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    if not parts["notebook"] and not parts["note"]:
        return " " * width if width > 0 else ""

    notebook = parts["notebook"] if not hide_notebook else None
    note = parts["note"]

    if hide_notebook:
        color, icon = "white", None
    else:
        color, icon = (
            get_notebook_display_info(notebook) if notebook else ("white", None)
        )

    # Icons take ~2 visual chars (emoji + space)
    icon_width = 2 if icon else 0

    # Build plain source for width calculation
    if hide_notebook:
        plain_source = note or ""
    elif notebook and note:
        plain_source = f"{notebook}/{note}"
    elif notebook:
        plain_source = notebook
    else:
        plain_source = note

    # Adjust available width for text (reserve space for icon)
    text_width = max(width - icon_width, 10) if width > 0 else 0

    # Truncate if needed
    if text_width > 0 and len(plain_source) > text_width:
        # Try to keep at least some of both parts
        truncated = plain_source[: text_width - 1] + "…"
    else:
        truncated = plain_source

    # Build colored version
    colored_parts = []
    remaining = truncated

    if not hide_notebook and notebook and remaining.startswith(notebook):
        icon_prefix = f"{icon} " if icon else ""
        colored_parts.append(f"[{color}]{icon_prefix}{notebook}[/{color}]")
        remaining = remaining[len(notebook) :]
    elif not hide_notebook and notebook:
        # Notebook was truncated
        icon_prefix = f"{icon} " if icon else ""
        colored_parts.append(f"[{color}]{icon_prefix}{remaining}[/{color}]")
        remaining = ""

    if not hide_notebook and remaining.startswith("/") and note:
        colored_parts.append("/")
        remaining = remaining[1:]

    # Color note part
    if remaining:
        if remaining.endswith("…"):
            colored_parts.append(f"[blue]{remaining}[/blue]")
        else:
            colored_parts.append(f"[blue]{remaining}[/blue]")
        remaining = ""

    if remaining:
        colored_parts.append(remaining)

    colored = "".join(colored_parts)

    # Calculate visual length for padding (text + icon)
    if width > 0:
        visual_len = len(truncated) + icon_width
        if visual_len < width:
            colored += " " * (width - visual_len)

    return colored


def _format_compact_source(t, max_width: int = 0, hide_notebook: bool = False) -> str:
    """Format the source of a todo in compact mode (notebook only, or note if hiding).

    Used when terminal is too narrow for full source display.

    Args:
        t: Todo object
        max_width: Maximum width (0 = no limit)
        hide_notebook: If True, show note instead of notebook
    """
    parts = _get_todo_source_parts(t)
    if hide_notebook:
        result = parts["note"] if parts["note"] else ""
    else:
        result = parts["notebook"] if parts["notebook"] else ""

    if max_width > 0 and len(result) > max_width:
        result = result[: max_width - 1] + "…"

    return result


def _format_colored_compact_source(
    t, width: int = 0, hide_notebook: bool = False
) -> str:
    """Format compact source (notebook only, or note if hiding) with colors.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)
        hide_notebook: If True, show note instead of notebook

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    if hide_notebook:
        # Show note instead of notebook
        if not parts["note"]:
            return " " * width if width > 0 else ""
        text = parts["note"]
        # No icon when hiding notebook
        icon_width = 0
        # Truncate if needed
        if width > 0 and len(text) > width:
            text = text[: width - 1] + "…"
        colored = f"[blue]{text}[/blue]"
        if width > 0 and len(text) < width:
            colored += " " * (width - len(text))
        return colored

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
    show_created = bool(widths.get("show_created", True)) if widths else True
    show_due = bool(widths.get("show_due", True)) if widths else True
    show_priority = bool(widths.get("show_priority", True)) if widths else True
    compact_source = bool(widths.get("compact_source", False)) if widths else False
    nosection_source = bool(widths.get("nosection_source", False)) if widths else False
    hide_notebook = bool(widths.get("hide_notebook", False)) if widths else False
    hide_source = bool(widths.get("hide_source", False)) if widths else False

    # Build content - truncate if needed for alignment
    # Reduce content width by indent amount to keep columns aligned
    content = t.content
    base_content_width = widths["content"] if widths else len(content)
    content_width = max(base_content_width - indent_width, 10)  # minimum 10 chars
    if len(content) > content_width:
        content_display = content[: content_width - 1] + "…"
    else:
        content_display = content.ljust(content_width)

    # Build source column (colored) - different modes for different widths
    source_width = widths["source"] if widths else 15
    if compact_source:
        source_str = _format_compact_source(t, hide_notebook=hide_notebook)
        source_part = _format_colored_compact_source(
            t, source_width, hide_notebook=hide_notebook
        )
    elif nosection_source:
        source_str = _format_nosection_source(t, hide_notebook=hide_notebook)
        source_part = (
            _format_colored_nosection_source(
                t, source_width, hide_notebook=hide_notebook
            )
            if source_str
            else " " * source_width
        )
    else:
        source_str = _format_todo_source(t, hide_notebook=hide_notebook)
        source_part = (
            _format_colored_todo_source(t, source_width, hide_notebook=hide_notebook)
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
        # Show time if not midnight, otherwise just date
        if t.has_due_time:
            due_str = t.due_date.strftime("%b %d %H:%M")
        else:
            due_str = t.due_date.strftime("%b %d")
        # Red if due today or overdue (and not completed)
        due = t.due_date_only
        if due and due <= date.today() and not t.completed:
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
    # ID stays left-aligned, indent comes after ID before checkbox
    if hide_source:
        line_parts = [f"[dim]{short_id}[/dim] {prefix}{checkbox} {content_part}"]
    else:
        line_parts = [
            f"[dim]{short_id}[/dim] {prefix}{checkbox} {content_part}  {source_part}"
        ]

    if show_created:
        created_part = f"[dim]{created_str:>6}[/dim]" if created_str else " " * 6
        line_parts.append(f"  {created_part}")

    if show_due:
        due_part = f"[{due_color}]{due_str:>6}[/{due_color}]" if due_str else " " * 6
        line_parts.append(f"  {due_part}")

    if show_priority:
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
    "-t",
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
    - A date with time: "2025-12-15 14:30", "tomorrow 2pm", "friday 9am"
    - "none" or "clear" to remove the due date

    Note: "friday" means the NEXT Friday (future), not the most recent.

    \b
    Examples:
      nb todo due abc123 friday         # Set due to next Friday
      nb todo due abc123 tomorrow
      nb todo due abc123 "dec 25"
      nb todo due abc123 2025-12-15
      nb todo due abc123 "friday 2pm"   # With time
      nb todo due abc123 "tomorrow 9am"
      nb todo due abc123 none           # Remove due date
      nb todo due abc def friday        # Multiple IDs
    """
    from nb.core.todos import remove_todo_due_date, update_todo_due_date
    from nb.index.todos_repo import update_todo_due_date_db
    from nb.utils.dates import (
        format_datetime,
        is_clear_date_keyword,
        parse_fuzzy_datetime_future,
    )

    # Check if we should clear the due date
    is_clear = is_clear_date_keyword(date_expr)

    if not is_clear:
        new_date = parse_fuzzy_datetime_future(date_expr)
        if not new_date:
            console.print(f"[red]Could not parse date: {date_expr}[/red]")
            console.print(
                "[dim]Try: tomorrow, friday 2pm, next monday 9am, dec 15, 2025-12-15 14:30, or 'none' to clear[/dim]"
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
                    # Format with time if not midnight
                    date_display = format_datetime(new_date)
                    console.print(f"[green]Due {date_display}:[/green] {t.content}")
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
    path = t.source.path

    # Capture mtime before edit
    try:
        mtime_before = path.stat().st_mtime
    except OSError:
        mtime_before = None

    console.print(f"[dim]Opening {path.name}:{t.line_number}...[/dim]")
    open_in_editor(path, line=t.line_number, editor=config.editor)

    # Sync if file was modified
    try:
        mtime_after = path.stat().st_mtime
        if mtime_before is None or mtime_after != mtime_before:
            from nb.core.notes import _reindex_note_after_edit, update_note_mtime

            print("Syncing nb...", end="", file=sys.stderr, flush=True)
            update_note_mtime(path, config.notes_root)
            _reindex_note_after_edit(path, config.notes_root)
            print(" done", file=sys.stderr)
    except OSError:
        pass


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
    help="Filter by notebook (repeatable)",
    shell_complete=complete_notebook,
)
@click.option(
    "--note",
    multiple=True,
    help="Filter by note path (repeatable)",
)
@click.option(
    "--exclude-notebook",
    "-N",
    multiple=True,
    help="Exclude todos from this notebook (repeatable)",
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
@click.option(
    "--in-progress",
    "-i",
    "in_progress_only",
    is_flag=True,
    help="Only mark in-progress todos as completed (not pending)",
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def todo_all_done(
    note_ref: str, notebook: str | None, in_progress_only: bool, force: bool
) -> None:
    """Mark all todos in a note as completed.

    NOTE_REF can be:
    - A note name: "myproject", "friday"
    - A notebook/note path: "work/myproject", "daily/friday"
    - A note alias (from 'nb alias')

    Use --in-progress to only mark in-progress todos as completed,
    leaving pending todos unchanged.

    \b
    Examples:
      nb todo all-done friday                 # Friday's daily note
      nb todo all-done myproject -n work      # work/myproject.md
      nb todo all-done work/myproject         # Same as above
      nb todo all-done myalias                # By alias
      nb todo all-done friday -f              # Skip confirmation
      nb todo all-done friday --in-progress   # Only complete in-progress todos
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
    if in_progress_only:
        # Only get IN_PROGRESS todos (not PENDING)
        todos = query_todos(
            status=TodoStatus.IN_PROGRESS,
            notes=[normalized_path],
            parent_only=False,  # Include subtasks
            exclude_note_excluded=False,  # Don't exclude - user explicitly asked
        )
    else:
        # Get all incomplete todos (PENDING + IN_PROGRESS)
        todos = query_todos(
            completed=False,
            notes=[normalized_path],
            parent_only=False,  # Include subtasks
            exclude_note_excluded=False,  # Don't exclude - user explicitly asked
        )

    if not todos:
        if in_progress_only:
            console.print(f"[dim]No in-progress todos in {note_path.name}[/dim]")
        else:
            console.print(f"[dim]No incomplete todos in {note_path.name}[/dim]")
        return

    # Show confirmation unless --force
    if not force:
        if in_progress_only:
            console.print(
                f"\n[bold]Mark in-progress todos as done in:[/bold] {note_path.name}"
            )
            console.print(f"[dim]Found {len(todos)} in-progress todo(s)[/dim]")
        else:
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


@todo.command("completed")
@click.option("--today", "-T", is_flag=True, help="Show todos completed today")
@click.option("--yesterday", "-Y", is_flag=True, help="Show todos completed today")
@click.option("--week", "-W", is_flag=True, help="Show todos completed this week")
@click.option("--days", "-d", type=int, help="Show todos completed in last N days")
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (repeatable)",
    shell_complete=complete_notebook,
)
@click.option("--tag", "-t", help="Filter by tag", shell_complete=complete_tag)
@click.option("--limit", "-l", type=int, default=50, help="Maximum number of todos")
def todo_completed(
    today: bool,
    yesterday: bool,
    week: bool,
    days: int | None,
    notebook: tuple[str, ...],
    tag: str | None,
    limit: int,
) -> None:
    """Show recently completed todos.

    View todos that were marked as completed within a specified time period.
    By default, shows todos completed in the last 7 days.

    \b
    Examples:
      nb todo completed                Show completed in last 7 days
      nb todo completed --today        Show completed today
      nb todo completed --week         Show completed this week
      nb todo completed -d 30          Show completed in last 30 days
      nb todo completed -n work        Show completed from work notebook
      nb todo completed -t project     Show completed todos tagged #project
    """
    from nb.index.scanner import index_all_notes

    # Ensure todos are indexed
    index_all_notes(index_vectors=False)

    config = get_config()

    # Resolve notebooks with fuzzy matching
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

    # Determine date range
    today_date = date.today()
    if today and yesterday:
        start_date = today_date - timedelta(days=1)
        end_date = today_date
        period_label = "yesterday and today"
    elif today:
        start_date = end_date = today_date
        period_label = "today"
    elif yesterday:
        start_date = end_date = today_date - timedelta(days=1)
        period_label = "today"
    elif week:
        week_start, week_end = get_week_range()
        start_date = week_start
        end_date = week_end
        period_label = "this week"
    elif days:
        start_date = today_date - timedelta(days=days)
        end_date = today_date
        period_label = f"last {days} days"
    else:
        # Default: last 7 days
        start_date = today_date - timedelta(days=7)
        end_date = today_date
        period_label = "last 7 days"

    # Query completed todos
    todos = query_todos(
        status=TodoStatus.COMPLETED,
        completed_date_start=start_date,
        completed_date_end=end_date,
        notebooks=effective_notebooks if effective_notebooks else None,
        tag=tag,
        parent_only=True,
        exclude_note_excluded=False,  # Show all completed todos
    )

    if not todos:
        console.print(f"[dim]No completed todos {period_label}.[/dim]")
        return

    # Sort by completion date (newest first), with fallback to created_date
    def completion_sort_key(t):
        # Get completion date from database - query_todos doesn't load it directly
        # so we'll use created_date as a proxy for sorting within groups
        return t.created_date or date.min

    # Group by completion date
    # Since Todo model doesn't expose completed_date, we'll query it separately
    from nb.index.db import get_db

    db = get_db()
    todo_dates = {}
    for t in todos:
        row = db.fetchone("SELECT completed_date FROM todos WHERE id = ?", (t.id,))
        if row and row["completed_date"]:
            todo_dates[t.id] = date.fromisoformat(row["completed_date"])
        else:
            todo_dates[t.id] = t.created_date or today_date

    # Group todos by completion date
    by_date: dict[date, list] = {}
    for t in todos:
        d = todo_dates.get(t.id, today_date)
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(t)

    # Display header
    console.print(f"\n[bold]Completed Todos[/bold] ({period_label})\n")

    # Display grouped by date (newest first)
    displayed = 0
    for d in sorted(by_date.keys(), reverse=True):
        if displayed >= limit:
            break

        # Format date header
        if d == today_date:
            date_label = "Today"
        elif d == today_date - timedelta(days=1):
            date_label = "Yesterday"
        else:
            date_label = d.strftime("%A, %B %d")

        console.print(f"[bold cyan]{date_label}[/bold cyan]")

        for t in by_date[d]:
            if displayed >= limit:
                break

            # Get notebook display info
            nb_color, _ = get_notebook_display_info(t.notebook or "")

            # Truncate content if needed
            content = t.content
            max_content = 60
            if len(content) > max_content:
                content = content[: max_content - 3] + "..."

            # Format the todo line
            nb_display = f"[{nb_color}]{t.notebook}[/{nb_color}]" if t.notebook else ""
            console.print(f"  [green][x][/green] {content} [dim]{nb_display}[/dim]")
            displayed += 1

        console.print()  # Blank line between dates

    # Summary
    total = len(todos)
    if displayed < total:
        console.print(f"[dim]Showing {displayed} of {total} completed todos[/dim]")
    else:
        console.print(f"[dim]{total} todo(s) completed {period_label}[/dim]")
