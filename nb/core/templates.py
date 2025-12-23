"""Template operations for nb."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from nb.config import get_config

if TYPE_CHECKING:
    from nb.core.calendar import CalendarEvent
    from nb.models import Todo


def get_templates_dir(notes_root: Path | None = None) -> Path:
    """Get the templates directory (.nb/templates).

    Args:
        notes_root: Override notes root directory

    Returns:
        Path to the templates directory.

    """
    if notes_root is None:
        notes_root = get_config().notes_root
    return notes_root / ".nb" / "templates"


def ensure_templates_dir(notes_root: Path | None = None) -> Path:
    """Ensure templates directory exists.

    Args:
        notes_root: Override notes root directory

    Returns:
        Path to the templates directory.

    """
    templates_dir = get_templates_dir(notes_root)
    templates_dir.mkdir(parents=True, exist_ok=True)
    return templates_dir


def list_templates(notes_root: Path | None = None) -> list[str]:
    """List available template names (without .md extension).

    Args:
        notes_root: Override notes root directory

    Returns:
        Sorted list of template names.

    """
    templates_dir = get_templates_dir(notes_root)
    if not templates_dir.exists():
        return []
    return sorted([p.stem for p in templates_dir.glob("*.md")])


def get_template_path(name: str, notes_root: Path | None = None) -> Path:
    """Get full path to a template file.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        Full path to the template file.

    """
    templates_dir = get_templates_dir(notes_root)
    return templates_dir / f"{name}.md"


def template_exists(name: str, notes_root: Path | None = None) -> bool:
    """Check if a template exists.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        True if the template exists.

    """
    return get_template_path(name, notes_root).exists()


def read_template(name: str, notes_root: Path | None = None) -> str | None:
    """Read template content.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        Template content, or None if not found.

    """
    path = get_template_path(name, notes_root)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def create_template(
    name: str,
    content: str,
    notes_root: Path | None = None,
) -> Path:
    """Create a new template file.

    Args:
        name: Template name (without .md extension)
        content: Template content
        notes_root: Override notes root directory

    Returns:
        Path to the created template file.

    Raises:
        FileExistsError: If the template already exists.

    """
    ensure_templates_dir(notes_root)
    path = get_template_path(name, notes_root)
    if path.exists():
        raise FileExistsError(f"Template already exists: {name}")
    path.write_text(content, encoding="utf-8")
    return path


def remove_template(name: str, notes_root: Path | None = None) -> bool:
    """Remove a template.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        True if removed, False if not found.

    """
    path = get_template_path(name, notes_root)
    if path.exists():
        path.unlink()
        return True
    return False


def format_todos_for_template(todos: list[Todo]) -> str:
    """Format todos as a markdown list for template insertion.

    Args:
        todos: List of Todo objects to format.

    Returns:
        Markdown formatted string with todo references.
        Format: "- todo text here [todo:abc123]"
    """
    if not todos:
        return "_No todos_"

    lines = []
    for todo in todos:
        # Use first 6 chars of ID for brevity (matches CLI display)
        short_id = todo.id[:6]
        lines.append(f"- {todo.content} [todo:{short_id}]")

    return "\n".join(lines)


def format_calendar_for_template(events: list[CalendarEvent]) -> str:
    """Format calendar events as a markdown list for template insertion.

    Args:
        events: List of CalendarEvent objects to format.

    Returns:
        Markdown formatted string with event times and subjects.
        Format: "- 9:00 AM - 10:00 AM: Meeting subject"
    """
    if not events:
        return "_No meetings_"

    lines = []
    for event in events:
        if event.is_all_day:
            lines.append(f"- (All day) {event.subject}")
        else:
            start_time = event.start.strftime("%I:%M %p").lstrip("0")
            end_time = event.end.strftime("%I:%M %p").lstrip("0")
            lines.append(f"- {start_time} - {end_time}: {event.subject}")

    return "\n".join(lines)


def render_template(
    content: str,
    title: str | None = None,
    notebook: str | None = None,
    dt: date | None = None,
) -> str:
    """Render template variables.

    Supported variables:
    - {{ date }} - ISO date (YYYY-MM-DD)
    - {{ datetime }} - ISO datetime
    - {{ notebook }} - Notebook name
    - {{ title }} - Note title
    - {{ todos_overdue }} - Overdue todos (dynamic, requires DB)
    - {{ todos_due_today }} - Todos due today (dynamic, requires DB)
    - {{ todos_due_this_week }} - Todos due this week (dynamic, requires DB)
    - {{ todos_high_priority }} - High priority todos (dynamic, requires DB)
    - {{ calendar }} - Today's calendar events (dynamic, requires Outlook)

    Args:
        content: Template content with variables
        title: Note title (for {{ title }})
        notebook: Notebook name (for {{ notebook }})
        dt: Date for the note (for {{ date }}, defaults to today)

    Returns:
        Rendered template with variables replaced.

    """
    if dt is None:
        dt = date.today()

    now = datetime.now()

    # Static replacements (no external dependencies)
    replacements = {
        "{{ date }}": dt.isoformat(),
        "{{ datetime }}": now.isoformat(timespec="minutes"),
        "{{ notebook }}": notebook or "",
        "{{ title }}": title or "",
    }

    result = content
    for var, value in replacements.items():
        result = result.replace(var, value)

    # Dynamic replacements - only query if variable is present (lazy evaluation)
    dynamic_vars = {
        "{{ todos_overdue }}": _get_todos_overdue,
        "{{ todos_due_today }}": lambda: _get_todos_due_today(dt),
        "{{ todos_due_this_week }}": lambda: _get_todos_due_this_week(dt),
        "{{ todos_high_priority }}": _get_todos_high_priority,
        "{{ calendar }}": lambda: _get_calendar_events(dt),
    }

    for var, getter in dynamic_vars.items():
        if var in result:
            result = result.replace(var, getter())

    return result


def _get_todos_overdue() -> str:
    """Get formatted overdue todos."""
    from nb.index.todos_repo import query_todos

    todos = query_todos(overdue=True, completed=False)
    return format_todos_for_template(todos)


def _get_todos_due_today(dt: date) -> str:
    """Get formatted todos due today."""
    from nb.index.todos_repo import query_todos

    todos = query_todos(due_start=dt, due_end=dt, completed=False)
    return format_todos_for_template(todos)


def _get_todos_due_this_week(dt: date) -> str:
    """Get formatted todos due this week."""
    from nb.index.todos_repo import query_todos

    week_end = dt + timedelta(days=7)
    todos = query_todos(due_start=dt, due_end=week_end, completed=False)
    return format_todos_for_template(todos)


def _get_todos_high_priority() -> str:
    """Get formatted high priority todos."""
    from nb.index.todos_repo import query_todos

    todos = query_todos(priority=1, completed=False)
    return format_todos_for_template(todos)


def _get_calendar_events(dt: date) -> str:
    """Get formatted calendar events for the given date."""
    from nb.core.calendar import get_calendar_client

    client = get_calendar_client()
    events = client.get_events(dt, dt)
    return format_calendar_for_template(events)


# Default template content for new templates
DEFAULT_TEMPLATE_CONTENT = """\
---
date: {{ date }}
---

# {{ title }}

"""
