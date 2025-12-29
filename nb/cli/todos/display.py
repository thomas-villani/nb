"""Todo list display function."""

from __future__ import annotations

from datetime import date, timedelta

from nb.cli.utils import console, copy_to_clipboard
from nb.index.todos_repo import get_sorted_todos, query_todos
from nb.utils.dates import get_week_range

from .formatters import _calculate_column_widths, _print_todo, format_todo_as_checkbox


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
    copy: bool = False,
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
    # Default sort order: due-date -> created-date -> priority -> file/section -> line #
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
        else:  # default: due-date -> created-date -> priority -> file/section -> line #
            due = todo.due_date_only if todo.due_date else date.max
            created = todo.created_date or date.min
            prio = todo.priority.value if todo.priority else 999
            source = str(todo.source.path) if todo.source else ""
            return (due, created, prio, source, todo.line_number)

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

    # Copy to clipboard if requested
    if copy:
        lines = []
        for group_name, group_todos in groups.items():
            if not group_todos:
                continue
            lines.append(f"## {group_name}")
            for t in group_todos:
                lines.append(format_todo_as_checkbox(t))
            lines.append("")  # Blank line between groups

        clipboard_text = "\n".join(lines).strip()
        if copy_to_clipboard(clipboard_text):
            console.print(
                f"\n[dim]Copied {len(all_visible_todos)} todos to clipboard.[/dim]"
            )
