"""Shared utilities for Wijjit-based TUI components."""

from __future__ import annotations

from datetime import date, timedelta

from nb.config import get_config
from nb.models import Todo
from nb.utils.dates import get_week_range


def format_todo_source(todo: Todo) -> str:
    """Format the source of a todo for display.

    Args:
        todo: The todo item.

    Returns:
        Formatted source string (e.g., "@alias", "inbox", "notebook/filename").

    """
    if not todo.source:
        return ""

    if todo.source.alias:
        return f"@{todo.source.alias}"
    elif todo.source.type == "inbox":
        return "inbox"
    else:
        config = get_config()
        try:
            rel_path = todo.source.path.relative_to(config.notes_root)
            if len(rel_path.parts) > 1:
                return f"{rel_path.parts[0]}/{rel_path.stem}"
            else:
                return rel_path.stem
        except ValueError:
            return todo.source.path.stem


def format_due_date(todo: Todo) -> tuple[str, str]:
    """Format the due date of a todo with appropriate styling.

    Args:
        todo: The todo item.

    Returns:
        Tuple of (formatted_string, style_name).

    """
    if not todo.due_date:
        return "-", "dim"

    today = date.today()
    _week_start, week_end = get_week_range()
    due = todo.due_date_only

    if due is None:
        return "-", "dim"

    # Format the date string
    if todo.has_due_time:
        due_str = todo.due_date.strftime("%b %d %H:%M")
    else:
        due_str = todo.due_date.strftime("%b %d")

    # Determine style based on urgency
    if due < today:
        return due_str, "red bold"
    elif due == today:
        return due_str, "yellow bold"
    elif due <= week_end:
        return due_str, "cyan"
    else:
        return due_str, "dim"


def format_due_date_review(todo: Todo) -> tuple[str, str]:
    """Format the due date for review view (shows overdue days).

    Args:
        todo: The todo item.

    Returns:
        Tuple of (formatted_string, style_name).

    """
    if not todo.due_date:
        return "", "dim"

    today = date.today()
    _week_start, week_end = get_week_range()
    due = todo.due_date_only

    if due is None:
        return "", "dim"

    overdue_days = (today - due).days

    if overdue_days > 0:
        return f"{overdue_days}d overdue", "red bold"
    elif due == today:
        return "today", "yellow bold"
    elif due <= week_end:
        return todo.due_date.strftime("%a"), "cyan"
    else:
        return todo.due_date.strftime("%b %d"), "dim"


def get_this_friday() -> date:
    """Get the date of this Friday (or next Friday if today is Friday or later).

    Returns:
        Date of this Friday.

    """
    today = date.today()
    days_ahead = 4 - today.weekday()  # 4 = Friday
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def get_next_friday() -> date:
    """Get the date of next week's Friday.

    Returns:
        Date of next Friday.

    """
    return get_this_friday() + timedelta(days=7)


def get_next_monday() -> date:
    """Get the date of next Monday.

    Returns:
        Date of next Monday.

    """
    today = date.today()
    days_ahead = 7 - today.weekday()  # 0 = Monday
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def get_first_of_next_month() -> date:
    """Get the first day of next month.

    Returns:
        First day of next month.

    """
    today = date.today()
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def truncate(text: str, max_length: int) -> str:
    """Truncate text to a maximum length with ellipsis.

    Args:
        text: Text to truncate.
        max_length: Maximum length including ellipsis.

    Returns:
        Truncated text.

    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
