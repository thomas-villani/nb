"""Todo-related CLI commands."""

from __future__ import annotations

from datetime import date, timedelta

import click

from nb.cli.utils import console, find_todo, get_notebook_display_info
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
    cli.add_command(todo_add_alias)
    cli.add_command(todo_alias)


@click.group(invoke_without_command=True)
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
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (can be used multiple times)",
)
@click.option(
    "--note",
    multiple=True,
    help="Filter by specific note path (can be used multiple times)",
)
@click.option(
    "--exclude-notebook",
    "-N",
    multiple=True,
    help="Exclude todos from this notebook (can be used multiple times)",
)
@click.option("--view", "-v", help="Apply a saved todo view")
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
    sort_by: str,
    show_all: bool,
    include_completed: bool,
    interactive: bool,
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

    Notebooks with todo_exclude: true in config are hidden by default.
    Notes with todo_exclude: true in frontmatter are also hidden.
    Use -a/--all to include them, or -n <notebook> to view one explicitly.

    Notebook names support fuzzy matching - if no exact match is found,
    similar notebooks will be suggested interactively.
    """
    if ctx.invoked_subcommand is None:
        config = get_config()

        # Handle view management commands first
        if list_views:
            _list_todo_views(config)
            return

        if delete_view:
            _delete_todo_view(config, delete_view)
            return

        # Resolve notebooks with fuzzy matching if they don't exist
        from nb.cli.utils import resolve_notebook

        effective_notebooks: list[str] = []
        for nb_name in notebook:
            if config.get_notebook(nb_name):
                effective_notebooks.append(nb_name)
            else:
                resolved = resolve_notebook(nb_name)
                if resolved:
                    effective_notebooks.append(resolved)
                else:
                    raise SystemExit(1)

        effective_notes = list(note) if note else []
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

        # Get excluded notebooks from config (unless --all or specific notebooks requested)
        all_excluded_notebooks: list[str] | None = None
        if not show_all and not effective_notebooks:
            config_excluded = config.excluded_notebooks() or []
            # Merge config exclusions with CLI exclusions
            all_excluded_notebooks = list(set(config_excluded) | set(exclude_notebook))
            if not all_excluded_notebooks:
                all_excluded_notebooks = None

        # Convert to list or None for query functions
        notebooks_filter = effective_notebooks if effective_notebooks else None
        notes_filter = effective_notes if effective_notes else None
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
            # Don't exclude when --all or specific notebooks requested
            exclude_note_excluded = not show_all and not effective_notebooks

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
                exclude_notebooks=all_excluded_notebooks,
                hide_later=effective_hide_later,
                hide_no_date=effective_hide_no_date,
                sort_by=sort_by,
                include_completed=effective_include_completed,
                exclude_note_excluded=exclude_note_excluded,
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
    exclude_notebooks: list[str] | None = None,
    hide_later: bool = False,
    hide_no_date: bool = False,
    sort_by: str = "source",
    include_completed: bool = False,
    exclude_note_excluded: bool = True,
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

    # Cap source width (notebook/note::section should fit reasonably)
    widths["source"] = min(widths["source"], 35)

    return widths


def _format_todo_source(t, max_section_len: int = 15) -> str:
    """Format the source of a todo for display (plain text, used for sorting).

    Format: notebook/note_title::Section (if section exists)
            notebook/note_title (if no section)

    Args:
        t: Todo object
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
        return f"{base_source}::{section}"
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


def _format_colored_todo_source(t, width: int = 0, max_section_len: int = 15) -> str:
    """Format the source of a todo with colors for display.

    Uses configured notebook colors and icons.

    Args:
        t: Todo object
        width: Minimum width for padding (0 = no padding)
        max_section_len: Maximum length for section name (default 15)

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    # Build colored source string
    colored_parts = []

    if parts["notebook"]:
        color, icon = get_notebook_display_info(parts["notebook"])
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

    # Calculate plain length for padding
    if width > 0:
        plain_len = len(_format_todo_source(t, max_section_len=max_section_len))
        if plain_len < width:
            colored += " " * (width - plain_len)

    return colored


def _print_todo(t, indent: int = 0, widths: dict[str, int] | None = None) -> None:
    """Print a single todo with formatting."""
    prefix = "  " * indent
    # Checkbox indicator: x=completed, ^=in-progress, o=pending
    if t.completed:
        checkbox = "[green]x[/green]"
    elif t.in_progress:
        checkbox = "[yellow]^[/yellow]"
    else:
        checkbox = "[dim]o[/dim]"

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


@click.command("ta")
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
    t = find_todo(todo_id)
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
    t = find_todo(todo_id)
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


@todo.command("start")
@click.argument("todo_id")
def todo_start(todo_id: str) -> None:
    """Mark a todo as in-progress.

    Changes the todo marker from [ ] to [^] in the source file.
    In-progress todos appear in their own section in 'nb todo' output.

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo start abc123
    """
    t = find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    if t.completed:
        console.print(
            "[yellow]Todo is already completed. Use 'nb todo undone' first.[/yellow]"
        )
        return

    if t.in_progress:
        console.print("[yellow]Todo is already in progress.[/yellow]")
        return

    # Set status in source file
    try:
        if set_todo_status_in_file(
            t.source.path, t.line_number, TodoStatus.IN_PROGRESS
        ):
            update_todo_status(t.id, TodoStatus.IN_PROGRESS)
            console.print(f"[yellow]Started:[/yellow] {t.content}")
        else:
            console.print("[red]Failed to update todo in source file.[/red]")
            raise SystemExit(1)
    except PermissionError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Use 'nb link' to enable sync for this file.[/dim]")
        raise SystemExit(1)


@todo.command("pause")
@click.argument("todo_id")
def todo_pause(todo_id: str) -> None:
    """Pause an in-progress todo (return to pending).

    Changes the todo marker from [^] to [ ] in the source file.

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo pause abc123
    """
    t = find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    if t.completed:
        console.print("[yellow]Todo is completed. Use 'nb todo undone' first.[/yellow]")
        return

    if not t.in_progress:
        console.print("[yellow]Todo is not in progress.[/yellow]")
        return

    # Set status in source file
    try:
        if set_todo_status_in_file(t.source.path, t.line_number, TodoStatus.PENDING):
            update_todo_status(t.id, TodoStatus.PENDING)
            console.print(f"[dim]Paused:[/dim] {t.content}")
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


@click.command("td")
@click.pass_context
def todo_alias(ctx: click.Context) -> None:
    """Alias for 'todo' (list todos)."""
    index_all_notes(index_vectors=False)
    todos = get_sorted_todos(completed=False)
    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return
    _list_todos()
