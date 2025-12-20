"""AI-assisted planning for weekly and daily task organization.

Uses LLM to generate actionable plans based on todos, recent notes,
and calendar availability.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from nb.config import get_config
from nb.core.llm import Message, StreamChunk, get_llm_client
from nb.models import Priority, Todo, TodoStatus


@dataclass
class TodoContext:
    """Todo item with additional context for planning."""

    id: str
    content: str
    due_date: datetime | None
    priority: Priority | None
    tags: list[str]
    notebook: str | None
    source_note: str
    age_days: int
    is_overdue: bool
    is_in_progress: bool
    section: str | None = None
    raw_content: str | None = None

    @classmethod
    def from_todo(cls, todo: Todo, today: date | None = None) -> TodoContext:
        """Create TodoContext from a Todo model."""
        if today is None:
            today = date.today()

        # Calculate age in days
        age_days = 0
        if todo.created_date:
            age_days = (today - todo.created_date).days

        # Check if overdue
        is_overdue = False
        if todo.due_date and not todo.completed:
            is_overdue = todo.due_date_only < today if todo.due_date_only else False

        return cls(
            id=todo.id,
            content=todo.content,
            due_date=todo.due_date,
            priority=todo.priority,
            tags=todo.tags,
            notebook=todo.notebook,
            source_note=str(todo.source.path) if todo.source else "",
            age_days=age_days,
            is_overdue=is_overdue,
            is_in_progress=todo.status == TodoStatus.IN_PROGRESS,
            section=todo.section,
            raw_content=todo.raw_content,
        )


@dataclass
class NoteContext:
    """Recent note context for planning."""

    path: str
    title: str | None
    date: date | None
    summary: str
    tags: list[str]
    notebook: str


@dataclass
class AvailabilityBlock:
    """A block of available time."""

    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> int:
        """Get duration in minutes."""
        delta = self.end - self.start
        return int(delta.total_seconds() / 60)


@dataclass
class PlanScope:
    """Filtering scope for the plan."""

    notebooks: list[str] | None = None
    tags: list[str] | None = None
    exclude_notebooks: list[str] | None = None


@dataclass
class PlanningContext:
    """All context needed for planning."""

    todos: list[TodoContext]
    overdue_todos: list[TodoContext]
    in_progress_todos: list[TodoContext]
    recent_notes: list[NoteContext]
    calendar_events: list  # list[CalendarEvent] - imported dynamically
    availability_blocks: list[AvailabilityBlock]
    horizon: Literal["day", "week"]
    today: date
    scope: PlanScope


@dataclass
class DayPlan:
    """Plan for a single day."""

    date: date
    focus_items: list[str]
    scheduled_tasks: list[tuple[str, str]]  # (time_slot, task)
    reasoning: str


@dataclass
class PlanWarning:
    """Warning about potential issues."""

    type: str  # overdue, no_next_action, stale_project, conflict
    message: str
    related_todo_id: str | None = None


@dataclass
class PlanResult:
    """Complete planning result."""

    horizon: Literal["day", "week"]
    raw_response: str
    warnings: list[PlanWarning] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ChatMessage:
    """A message in the planning chat."""

    role: Literal["user", "assistant", "system"]
    content: str


@dataclass
class PlanningSession:
    """Interactive planning session state."""

    context: PlanningContext
    messages: list[ChatMessage] = field(default_factory=list)
    current_plan: str | None = None
    system_prompt: str | None = None


# Default system prompt for planning
DEFAULT_PLANNING_SYSTEM_PROMPT = """\
You are a productivity assistant helping plan work based on todos and calendar.

Guidelines:
- Prioritize overdue items and high-priority tasks
- Consider calendar availability when scheduling
- Group related tasks when possible
- Flag items that have been pending too long (more than 7 days without progress)
- Be realistic about time estimates
- Consider context switching costs
- For weekly plans, spread work across days to avoid overload
- For daily plans, focus on what can realistically be accomplished today

Output format:
- Start with today's focus items (2-3 most important tasks)
- Then provide a day-by-day breakdown with brief reasoning
- End with warnings about potential issues (overdue items, conflicts, stale tasks)
- Keep the plan actionable and concise
- Reference todo ID hashes when referencing them
"""


def gather_planning_context(
    scope: PlanScope | None = None,
    horizon: Literal["day", "week"] = "week",
    days_back: int = 7,
    include_calendar: bool = True,
) -> PlanningContext:
    """Gather all context needed for planning.

    Args:
        scope: Filtering scope for notebooks/tags.
        horizon: Planning horizon ("day" or "week").
        days_back: Number of days of notes to include for context.
        include_calendar: Whether to fetch calendar events.

    Returns:
        PlanningContext with todos, notes, and calendar data.
    """
    from nb.core.notes import list_daily_notes
    from nb.index.todos_repo import get_sorted_todos

    if scope is None:
        scope = PlanScope()

    today = date.today()

    # Fetch incomplete todos
    # Only exclude todo_excluded notes when no specific notebook is requested
    # (matches nb todo behavior where -n work shows all todos from that notebook)
    todos_raw = get_sorted_todos(
        completed=False,
        notebooks=scope.notebooks,
        exclude_notebooks=scope.exclude_notebooks,
        tag=scope.tags[0] if scope.tags else None,
        exclude_note_excluded=scope.notebooks is None,
    )

    # Convert to TodoContext
    todos = [TodoContext.from_todo(t, today) for t in todos_raw]

    # Separate overdue and in-progress
    overdue_todos = [t for t in todos if t.is_overdue]
    in_progress_todos = [t for t in todos if t.is_in_progress]

    # Get recent daily notes for context
    recent_notes: list[NoteContext] = []
    config = get_config()

    start_date = today - timedelta(days=days_back)
    daily_note_paths = list_daily_notes(start=start_date, end=today)

    for note_path in daily_note_paths[:10]:  # Limit to 10 notes
        full_path = config.notes_root / note_path
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")
                # Extract first 300 chars as summary
                summary = content[:300].strip()
                if len(content) > 300:
                    summary += "..."

                # Try to extract date from filename
                note_date = None
                try:
                    date_str = note_path.stem  # e.g., "2025-01-15"
                    note_date = date.fromisoformat(date_str)
                except ValueError:
                    pass

                recent_notes.append(
                    NoteContext(
                        path=str(note_path),
                        title=note_path.stem,
                        date=note_date,
                        summary=summary,
                        tags=[],
                        notebook="daily",
                    )
                )
            except OSError:
                continue

    # Get calendar events
    calendar_events = []
    availability_blocks: list[AvailabilityBlock] = []

    if include_calendar:
        try:
            from nb.core.calendar import get_today_events, get_week_events

            if horizon == "day":
                calendar_events = get_today_events()
            else:
                calendar_events = get_week_events()

            # Compute availability blocks
            availability_blocks = _compute_availability_blocks(
                calendar_events, today, horizon
            )
        except Exception:
            # Calendar not available, continue without it
            pass

    return PlanningContext(
        todos=todos,
        overdue_todos=overdue_todos,
        in_progress_todos=in_progress_todos,
        recent_notes=recent_notes,
        calendar_events=calendar_events,
        availability_blocks=availability_blocks,
        horizon=horizon,
        today=today,
        scope=scope,
    )


def _compute_availability_blocks(
    events: list,
    start_date: date,
    horizon: Literal["day", "week"],
    work_start: time = time(9, 0),
    work_end: time = time(17, 0),
) -> list[AvailabilityBlock]:
    """Compute free time blocks around calendar events.

    Args:
        events: List of CalendarEvent objects.
        start_date: Starting date.
        horizon: Planning horizon.
        work_start: Start of work day.
        work_end: End of work day.

    Returns:
        List of AvailabilityBlock objects representing free time.
    """
    blocks = []
    num_days = 1 if horizon == "day" else 7

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        day_start = datetime.combine(current_date, work_start)
        day_end = datetime.combine(current_date, work_end)

        # Get events for this day
        day_events = [
            e for e in events if hasattr(e, "start") and e.start.date() == current_date
        ]

        # Sort by start time
        day_events.sort(key=lambda e: e.start)

        # Find gaps between events
        current_time = day_start

        for event in day_events:
            event_start = event.start
            event_end = event.end

            # Skip all-day events or events outside work hours
            if hasattr(event, "is_all_day") and event.is_all_day:
                continue
            if event_start >= day_end or event_end <= day_start:
                continue

            # Clamp to work hours
            event_start = max(event_start, day_start)
            event_end = min(event_end, day_end)

            # Add availability block before this event
            if event_start > current_time:
                blocks.append(AvailabilityBlock(start=current_time, end=event_start))

            current_time = max(current_time, event_end)

        # Add remaining time after last event
        if current_time < day_end:
            blocks.append(AvailabilityBlock(start=current_time, end=day_end))

    return blocks


def build_planning_prompt(
    context: PlanningContext,
    custom_prompt: str | None = None,
) -> str:
    """Build the LLM prompt for planning.

    Args:
        context: Planning context with todos, notes, calendar.
        custom_prompt: Optional custom instructions to append.

    Returns:
        Formatted prompt string.
    """
    parts = []

    # Header
    horizon_str = "today" if context.horizon == "day" else "the upcoming week"
    parts.append(
        f"Please help me plan {horizon_str}. Today is {context.today.strftime('%A, %B %d, %Y')}.\n"
    )

    # Overdue items (highlighted)
    if context.overdue_todos:
        parts.append("## OVERDUE ITEMS (need immediate attention)")
        for todo in context.overdue_todos:
            due_str = todo.due_date.strftime("%Y-%m-%d") if todo.due_date else "no date"
            priority_str = f" [P{todo.priority.value}]" if todo.priority else ""
            parts.append(
                f"- {todo.content}{priority_str} (due: {due_str}, {todo.age_days} days old)"
            )
        parts.append("")

    # In-progress items
    if context.in_progress_todos:
        parts.append("## IN PROGRESS")
        for todo in context.in_progress_todos:
            due_str = (
                f" (due: {todo.due_date.strftime('%Y-%m-%d')})" if todo.due_date else ""
            )
            parts.append(f"- {todo.content}{due_str}")
        parts.append("")

    # All open todos
    parts.append("## OPEN TODOS")
    if context.todos:
        for todo in context.todos:
            if todo.is_overdue or todo.is_in_progress:
                continue  # Already listed above

            tags_str = f" #{' #'.join(todo.tags)}" if todo.tags else ""
            priority_str = f" [P{todo.priority.value}]" if todo.priority else ""
            due_str = ""
            if todo.due_date:
                due_str = f" (due: {todo.due_date.strftime('%Y-%m-%d')})"
            notebook_str = f" [{todo.notebook}]" if todo.notebook else ""
            age_str = f" ({todo.age_days}d old)" if todo.age_days > 3 else ""

            parts.append(
                f"- {todo.content}{priority_str}{due_str}{notebook_str}{tags_str}{age_str}"
            )
    else:
        parts.append("(No open todos)")
    parts.append("")

    # Calendar events
    if context.calendar_events:
        parts.append("## CALENDAR")
        for event in context.calendar_events:
            start_str = event.start.strftime("%a %H:%M")
            end_str = event.end.strftime("%H:%M")
            duration = event.duration_minutes
            parts.append(f"- {start_str}-{end_str} ({duration}min): {event.subject}")
        parts.append("")

    # Availability summary
    if context.availability_blocks:
        total_available = sum(b.duration_minutes for b in context.availability_blocks)
        parts.append(f"## AVAILABILITY: ~{total_available // 60} hours of free time")
        parts.append("")

    # Recent context from notes (brief)
    if context.recent_notes:
        parts.append("## RECENT CONTEXT (from daily notes)")
        for note in context.recent_notes[:3]:  # Just top 3
            date_str = note.date.strftime("%Y-%m-%d") if note.date else "unknown"
            # Truncate summary
            summary = (
                note.summary[:150] + "..." if len(note.summary) > 150 else note.summary
            )
            summary = summary.replace("\n", " ")
            parts.append(f"- {date_str}: {summary}")
        parts.append("")

    # Custom instructions
    if custom_prompt:
        parts.append("## ADDITIONAL INSTRUCTIONS")
        parts.append(custom_prompt)
        parts.append("")

    return "\n".join(parts)


def generate_plan(
    context: PlanningContext,
    use_smart_model: bool = True,
    custom_prompt: str | None = None,
    system_prompt: str | None = None,
) -> PlanResult:
    """Generate a plan using the LLM.

    Args:
        context: Planning context.
        use_smart_model: Whether to use the smart (more capable) model.
        custom_prompt: Optional custom instructions.
        system_prompt: Optional custom system prompt.

    Returns:
        PlanResult with the generated plan.
    """
    system = system_prompt or DEFAULT_PLANNING_SYSTEM_PROMPT
    prompt = build_planning_prompt(context, custom_prompt)

    client = get_llm_client()
    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )

    # Extract warnings from context
    warnings = _extract_warnings(context)

    return PlanResult(
        horizon=context.horizon,
        raw_response=response.content,
        warnings=warnings,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


def generate_plan_stream(
    context: PlanningContext,
    use_smart_model: bool = True,
    custom_prompt: str | None = None,
    system_prompt: str | None = None,
) -> Iterator[StreamChunk]:
    """Stream the plan generation.

    Args:
        context: Planning context.
        use_smart_model: Whether to use the smart model.
        custom_prompt: Optional custom instructions.
        system_prompt: Optional custom system prompt.

    Yields:
        StreamChunk objects with content.
    """
    system = system_prompt or DEFAULT_PLANNING_SYSTEM_PROMPT
    prompt = build_planning_prompt(context, custom_prompt)

    client = get_llm_client()
    yield from client.complete_stream(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )


def _extract_warnings(context: PlanningContext) -> list[PlanWarning]:
    """Extract warnings from planning context."""
    warnings = []

    # Overdue items
    for todo in context.overdue_todos:
        warnings.append(
            PlanWarning(
                type="overdue",
                message=f"Overdue: {todo.content}",
                related_todo_id=todo.id,
            )
        )

    # Stale items (more than 14 days old without progress)
    for todo in context.todos:
        if todo.age_days > 14 and not todo.is_in_progress:
            warnings.append(
                PlanWarning(
                    type="stale",
                    message=f"Stale ({todo.age_days} days): {todo.content}",
                    related_todo_id=todo.id,
                )
            )

    return warnings


def format_plan_markdown(
    plan: PlanResult,
    include_warnings: bool = True,
    section_title: str = "## Plan",
) -> str:
    """Format a plan as markdown.

    Args:
        plan: The plan result to format.
        include_warnings: Whether to include warnings section.
        section_title: Title for the plan section.

    Returns:
        Markdown-formatted plan.
    """
    parts = [section_title, ""]
    parts.append(plan.raw_response)

    if include_warnings and plan.warnings:
        parts.append("")
        parts.append("### Warnings")
        for warning in plan.warnings:
            parts.append(f"- **{warning.type}**: {warning.message}")

    return "\n".join(parts)


def append_plan_to_note(
    plan: PlanResult,
    note_path: Path | None = None,
    section_title: str = "## Weekly Plan",
) -> Path:
    """Append the plan to a note.

    Args:
        plan: The plan to append.
        note_path: Path to the note. If None, uses today's daily note.
        section_title: Title for the plan section.

    Returns:
        Path to the note that was modified.
    """
    from nb.core.notes import ensure_daily_note

    config = get_config()

    if note_path is None:
        note_path = ensure_daily_note(date.today())
    elif not note_path.is_absolute():
        note_path = config.notes_root / note_path

    # Format the plan
    formatted = format_plan_markdown(plan, section_title=section_title)

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


# Interactive session functions


def create_planning_session(
    context: PlanningContext,
    system_prompt: str | None = None,
) -> PlanningSession:
    """Create a new interactive planning session.

    Args:
        context: Planning context to use.
        system_prompt: Optional custom system prompt.

    Returns:
        New PlanningSession instance.
    """
    return PlanningSession(
        context=context,
        messages=[],
        current_plan=None,
        system_prompt=system_prompt or DEFAULT_PLANNING_SYSTEM_PROMPT,
    )


def continue_planning_session(
    session: PlanningSession,
    user_input: str,
    use_smart_model: bool = True,
) -> tuple[str, PlanResult | None]:
    """Continue the planning conversation.

    Args:
        session: The planning session to continue.
        user_input: User's input message.
        use_smart_model: Whether to use the smart model.

    Returns:
        Tuple of (response text, updated PlanResult if plan was generated).
    """
    # Add user message
    session.messages.append(ChatMessage(role="user", content=user_input))

    # Build messages for LLM
    llm_messages = []

    # If this is the first message, include the planning context
    if len(session.messages) == 1:
        initial_prompt = build_planning_prompt(session.context)
        # Combine initial context with user message
        combined_content = f"{initial_prompt}\n\nUser request: {user_input}"
        llm_messages.append(Message(role="user", content=combined_content))
    else:
        # Include conversation history
        for msg in session.messages:
            llm_messages.append(Message(role=msg.role, content=msg.content))

    # Get LLM response
    client = get_llm_client()
    response = client.complete(
        messages=llm_messages,
        system=session.system_prompt,
        use_smart_model=use_smart_model,
    )

    # Add assistant response
    session.messages.append(ChatMessage(role="assistant", content=response.content))
    session.current_plan = response.content

    # Create plan result
    warnings = _extract_warnings(session.context)
    plan_result = PlanResult(
        horizon=session.context.horizon,
        raw_response=response.content,
        warnings=warnings,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )

    return response.content, plan_result


def continue_planning_session_stream(
    session: PlanningSession,
    user_input: str,
    use_smart_model: bool = True,
) -> Iterator[tuple[str, PlanResult | None]]:
    """Stream the continuation response.

    Args:
        session: The planning session to continue.
        user_input: User's input message.
        use_smart_model: Whether to use the smart model.

    Yields:
        Tuple of (chunk content, PlanResult on final chunk).
    """
    # Add user message
    session.messages.append(ChatMessage(role="user", content=user_input))

    # Build messages for LLM
    llm_messages = []

    # If this is the first message, include the planning context
    if len(session.messages) == 1:
        initial_prompt = build_planning_prompt(session.context)
        combined_content = f"{initial_prompt}\n\nUser request: {user_input}"
        llm_messages.append(Message(role="user", content=combined_content))
    else:
        for msg in session.messages:
            llm_messages.append(Message(role=msg.role, content=msg.content))

    # Stream LLM response
    client = get_llm_client()
    full_response = ""
    final_tokens = (0, 0)

    for chunk in client.complete_stream(
        messages=llm_messages,
        system=session.system_prompt,
        use_smart_model=use_smart_model,
    ):
        full_response += chunk.content
        if chunk.is_final:
            final_tokens = (chunk.input_tokens or 0, chunk.output_tokens or 0)
            # Add assistant response to history
            session.messages.append(
                ChatMessage(role="assistant", content=full_response)
            )
            session.current_plan = full_response

            # Create final plan result
            warnings = _extract_warnings(session.context)
            plan_result = PlanResult(
                horizon=session.context.horizon,
                raw_response=full_response,
                warnings=warnings,
                input_tokens=final_tokens[0],
                output_tokens=final_tokens[1],
            )
            yield chunk.content, plan_result
        else:
            yield chunk.content, None
