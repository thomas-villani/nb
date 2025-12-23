"""Todo view and kanban management functions."""

from __future__ import annotations

from datetime import date

from nb.cli.utils import console
from nb.config import TodoViewConfig, save_config
from nb.index.todos_repo import query_todos
from nb.models import TodoStatus


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
