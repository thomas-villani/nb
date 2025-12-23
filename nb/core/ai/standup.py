"""AI-assisted morning standup briefings.

Generates a morning briefing based on yesterday's completed work,
today's calendar, and items needing attention.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from nb.config import get_config
from nb.core.ai.planning import TodoContext
from nb.core.llm import Message, StreamChunk, get_llm_client
from nb.models import TodoStatus

if TYPE_CHECKING:
    pass


@dataclass
class StandupScope:
    """Filtering scope for the standup."""

    notebooks: list[str] | None = None
    tags: list[str] | None = None


@dataclass
class StandupContext:
    """All context needed for generating a standup briefing."""

    yesterday_completed: list[TodoContext]
    calendar_events: list  # list[CalendarEvent]
    overdue_todos: list[TodoContext]
    in_progress_todos: list[TodoContext]
    due_today: list[TodoContext]
    today: date
    scope: StandupScope


@dataclass
class StandupResult:
    """Result of a standup generation."""

    raw_response: str
    yesterday_count: int = 0
    today_count: int = 0
    overdue_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


# Default system prompt for standups
DEFAULT_STANDUP_SYSTEM_PROMPT = """\
You are a productivity assistant helping plan the day ahead.

Generate a concise morning briefing with these sections:

## Yesterday
Brief 1-2 sentence summary of what was accomplished yesterday.
Focus on outcomes, not just activity.

## Today's Schedule
List calendar events and meetings to be aware of.
Note any prep work or conflicts.

## Focus Areas
Top 2-3 priorities for today based on:
- Overdue items (highest priority)
- Items due today
- In-progress work

## Needs Attention
Flag any blockers, overdue items that have been stuck, or
stale tasks that need decisions.

Guidelines:
- Keep it concise and actionable
- Prioritize ruthlessly - not everything needs to be done today
- Be specific about what needs to happen
- If the calendar is full, acknowledge realistic constraints
"""


def gather_standup_context(
    scope: StandupScope | None = None,
    include_calendar: bool = True,
) -> StandupContext:
    """Gather all context needed for a standup briefing.

    Args:
        scope: Filtering scope for notebooks/tags.
        include_calendar: Whether to fetch calendar events.

    Returns:
        StandupContext with yesterday's work and today's agenda.
    """
    from nb.index.todos_repo import query_todos

    if scope is None:
        scope = StandupScope()

    today = date.today()
    yesterday = today - timedelta(days=1)

    # Get yesterday's completed todos
    yesterday_raw = query_todos(
        status=TodoStatus.COMPLETED,
        completed_date_start=yesterday,
        completed_date_end=yesterday,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=False,
    )

    # Get overdue todos
    overdue_raw = query_todos(
        overdue=True,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=scope.notebooks is None,
    )

    # Get in-progress todos
    in_progress_raw = query_todos(
        status=TodoStatus.IN_PROGRESS,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=scope.notebooks is None,
    )

    # Get todos due today
    due_today_raw = query_todos(
        due_start=today,
        due_end=today,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=scope.notebooks is None,
    )

    # Filter out completed from due_today
    due_today_raw = [t for t in due_today_raw if t.status != TodoStatus.COMPLETED]

    # Convert to TodoContext
    yesterday_completed = [TodoContext.from_todo(t, today) for t in yesterday_raw]
    overdue_todos = [TodoContext.from_todo(t, today) for t in overdue_raw]
    in_progress_todos = [TodoContext.from_todo(t, today) for t in in_progress_raw]
    due_today = [TodoContext.from_todo(t, today) for t in due_today_raw]

    # Get calendar events for today
    calendar_events = []
    if include_calendar:
        try:
            from nb.core.calendar import get_today_events

            calendar_events = get_today_events()
        except Exception:
            # Calendar not available, continue without it
            pass

    return StandupContext(
        yesterday_completed=yesterday_completed,
        calendar_events=calendar_events,
        overdue_todos=overdue_todos,
        in_progress_todos=in_progress_todos,
        due_today=due_today,
        today=today,
        scope=scope,
    )


def build_standup_prompt(
    context: StandupContext,
    custom_prompt: str | None = None,
) -> str:
    """Build the LLM prompt for generating a standup briefing.

    Args:
        context: Standup context with todos and calendar.
        custom_prompt: Optional custom instructions to append.

    Returns:
        Formatted prompt string.
    """
    parts = []

    # Header
    parts.append(
        f"Please generate a morning standup briefing for "
        f"{context.today.strftime('%A, %B %d, %Y')}.\n"
    )

    # Yesterday's completed items
    parts.append("## YESTERDAY'S COMPLETED")
    if context.yesterday_completed:
        for todo in context.yesterday_completed:
            notebook_str = f" [{todo.notebook}]" if todo.notebook else ""
            parts.append(f"- [x] {todo.content}{notebook_str}")
    else:
        parts.append("(No items completed yesterday)")
    parts.append("")

    # Today's calendar
    parts.append("## TODAY'S CALENDAR")
    if context.calendar_events:
        for event in context.calendar_events:
            start_str = event.start.strftime("%H:%M")
            end_str = event.end.strftime("%H:%M")
            duration = event.duration_minutes
            location_str = f" @ {event.location}" if event.location else ""
            parts.append(
                f"- {start_str}-{end_str} ({duration}min): {event.subject}{location_str}"
            )
    else:
        parts.append("(No calendar events)")
    parts.append("")

    # Overdue items (highest priority)
    parts.append("## OVERDUE ITEMS (need immediate attention)")
    if context.overdue_todos:
        for todo in context.overdue_todos:
            due_str = todo.due_date.strftime("%Y-%m-%d") if todo.due_date else "no date"
            priority_str = f" [P{todo.priority.value}]" if todo.priority else ""
            age_str = f" ({todo.age_days}d old)" if todo.age_days > 0 else ""
            parts.append(f"- {todo.content}{priority_str} (due: {due_str}){age_str}")
    else:
        parts.append("(No overdue items)")
    parts.append("")

    # In-progress items
    parts.append("## IN PROGRESS")
    if context.in_progress_todos:
        for todo in context.in_progress_todos:
            due_str = ""
            if todo.due_date:
                due_str = f" (due: {todo.due_date.strftime('%Y-%m-%d')})"
            notebook_str = f" [{todo.notebook}]" if todo.notebook else ""
            parts.append(f"- [^] {todo.content}{due_str}{notebook_str}")
    else:
        parts.append("(No items in progress)")
    parts.append("")

    # Due today
    parts.append("## DUE TODAY")
    if context.due_today:
        for todo in context.due_today:
            status_marker = "^" if todo.is_in_progress else " "
            priority_str = f" [P{todo.priority.value}]" if todo.priority else ""
            notebook_str = f" [{todo.notebook}]" if todo.notebook else ""
            parts.append(
                f"- [{status_marker}] {todo.content}{priority_str}{notebook_str}"
            )
    else:
        parts.append("(No items due today)")
    parts.append("")

    # Stats summary
    total_focus = (
        len(context.overdue_todos)
        + len(context.in_progress_todos)
        + len(context.due_today)
    )
    parts.append("## SUMMARY")
    parts.append(f"- Yesterday completed: {len(context.yesterday_completed)}")
    parts.append(f"- Calendar events: {len(context.calendar_events)}")
    parts.append(f"- Items needing focus: {total_focus}")
    parts.append(f"  - Overdue: {len(context.overdue_todos)}")
    parts.append(f"  - In progress: {len(context.in_progress_todos)}")
    parts.append(f"  - Due today: {len(context.due_today)}")
    parts.append("")

    # Custom instructions
    if custom_prompt:
        parts.append("## ADDITIONAL INSTRUCTIONS")
        parts.append(custom_prompt)
        parts.append("")

    return "\n".join(parts)


def generate_standup(
    context: StandupContext,
    use_smart_model: bool = True,
    custom_prompt: str | None = None,
) -> StandupResult:
    """Generate a standup briefing using the LLM.

    Args:
        context: Standup context.
        use_smart_model: Whether to use the smart (more capable) model.
        custom_prompt: Optional custom instructions.

    Returns:
        StandupResult with the generated briefing.
    """
    prompt = build_standup_prompt(context, custom_prompt)

    client = get_llm_client()
    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        system=DEFAULT_STANDUP_SYSTEM_PROMPT,
        use_smart_model=use_smart_model,
    )

    total_today = (
        len(context.overdue_todos)
        + len(context.in_progress_todos)
        + len(context.due_today)
    )

    return StandupResult(
        raw_response=response.content,
        yesterday_count=len(context.yesterday_completed),
        today_count=total_today,
        overdue_count=len(context.overdue_todos),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


def generate_standup_stream(
    context: StandupContext,
    use_smart_model: bool = True,
    custom_prompt: str | None = None,
) -> Iterator[StreamChunk]:
    """Stream the standup generation.

    Args:
        context: Standup context.
        use_smart_model: Whether to use the smart model.
        custom_prompt: Optional custom instructions.

    Yields:
        StreamChunk objects with content.
    """
    prompt = build_standup_prompt(context, custom_prompt)

    client = get_llm_client()
    yield from client.complete_stream(
        messages=[Message(role="user", content=prompt)],
        system=DEFAULT_STANDUP_SYSTEM_PROMPT,
        use_smart_model=use_smart_model,
    )


def format_standup_markdown(
    standup: StandupResult,
    section_title: str = "## Morning Standup",
) -> str:
    """Format a standup as markdown.

    Args:
        standup: The standup result to format.
        section_title: Title for the standup section.

    Returns:
        Markdown-formatted standup.
    """
    parts = [section_title, ""]
    parts.append(standup.raw_response)
    return "\n".join(parts)


def append_standup_to_note(
    standup: StandupResult,
    note_path: Path | None = None,
    section_title: str = "## Morning Standup",
) -> Path:
    """Append the standup to a note.

    Args:
        standup: The standup to append.
        note_path: Path to the note. If None, uses today's daily note.
        section_title: Title for the standup section.

    Returns:
        Path to the note that was modified.
    """
    from nb.core.notes import ensure_daily_note

    config = get_config()

    if note_path is None:
        note_path = ensure_daily_note(date.today())
    elif not note_path.is_absolute():
        note_path = config.notes_root / note_path

    # Ensure parent directory exists
    note_path.parent.mkdir(parents=True, exist_ok=True)

    # Format the standup
    formatted = format_standup_markdown(standup, section_title=section_title)

    # Append to note
    existing_content = ""
    if note_path.exists():
        existing_content = note_path.read_text(encoding="utf-8")

    # Add newlines before appending
    if existing_content and not existing_content.endswith("\n\n"):
        if existing_content.endswith("\n"):
            existing_content += "\n"
        else:
            existing_content += "\n\n"

    note_path.write_text(existing_content + formatted + "\n", encoding="utf-8")

    return note_path
