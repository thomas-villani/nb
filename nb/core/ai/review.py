"""AI-assisted daily and weekly reviews.

Generates structured reflection on completed work, items carrying over,
wins, and areas for improvement.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from nb.config import get_config
from nb.core.ai.planning import TodoContext
from nb.core.llm import Message, StreamChunk, get_llm_client
from nb.models import TodoStatus
from nb.utils.dates import get_week_range


@dataclass
class ReviewScope:
    """Filtering scope for the review."""

    notebooks: list[str] | None = None
    tags: list[str] | None = None


@dataclass
class ReviewContext:
    """All context needed for generating a review."""

    completed_todos: list[TodoContext]
    pending_todos: list[TodoContext]  # Carrying over
    overdue_todos: list[TodoContext]
    horizon: Literal["day", "week"]
    period_start: date
    period_end: date
    today: date
    scope: ReviewScope


@dataclass
class ReviewResult:
    """Result of a review generation."""

    horizon: Literal["day", "week"]
    raw_response: str
    completed_count: int = 0
    pending_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


# Default system prompt for reviews
DEFAULT_REVIEW_SYSTEM_PROMPT = """\
You are a productivity coach helping with end-of-{horizon} reviews.

Generate a structured review with these sections:

## Completed
Summarize what got done. Group by project/notebook if there are multiple.
Be specific about accomplishments.

## Carrying Over
List pending items that are moving forward. For each, briefly note why it's
still open (blocked, deprioritized, in progress) if context is available.

## Wins
Highlight notable achievements, milestones reached, or progress made.
Even small wins count.

{improvements_section}

Guidelines:
- Keep the tone reflective and constructive
- Be specific about accomplishments (not just "worked on X" but "completed X feature")
- For carrying over items, prioritize by importance
- Be honest about what didn't get done and why
- Keep it concise but meaningful
"""

IMPROVEMENTS_SECTION = """\
## Improvements
Suggest 1-2 process improvements based on patterns observed:
- Tasks that took longer than expected
- Items that keep carrying over
- Themes in what's working or not
"""


def gather_review_context(
    scope: ReviewScope | None = None,
    horizon: Literal["day", "week"] = "day",
) -> ReviewContext:
    """Gather all context needed for a review.

    Args:
        scope: Filtering scope for notebooks/tags.
        horizon: Review horizon ("day" or "week").

    Returns:
        ReviewContext with completed and pending todos.
    """
    from nb.index.todos_repo import query_todos

    if scope is None:
        scope = ReviewScope()

    today = date.today()

    # Determine the review period
    if horizon == "day":
        period_start = today
        period_end = today
    else:
        # Week review: use the current week
        period_start, period_end = get_week_range(today)

    # Get completed todos in the period
    completed_raw = query_todos(
        status=TodoStatus.COMPLETED,
        completed_date_start=period_start,
        completed_date_end=period_end,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=False,
    )

    # Get pending todos (items that existed before period start and are still open)
    # These are "carrying over" items
    pending_raw = query_todos(
        status=TodoStatus.PENDING,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=scope.notebooks is None,
    )

    # Also include in-progress items
    in_progress_raw = query_todos(
        status=TodoStatus.IN_PROGRESS,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=scope.notebooks is None,
    )

    # Combine pending and in-progress for "carrying over"
    carrying_over_raw = pending_raw + in_progress_raw

    # Get overdue todos
    overdue_raw = query_todos(
        overdue=True,
        notebooks=scope.notebooks,
        tag=scope.tags[0] if scope.tags else None,
        parent_only=True,
        exclude_note_excluded=scope.notebooks is None,
    )

    # Convert to TodoContext
    completed_todos = [TodoContext.from_todo(t, today) for t in completed_raw]
    pending_todos = [TodoContext.from_todo(t, today) for t in carrying_over_raw]
    overdue_todos = [TodoContext.from_todo(t, today) for t in overdue_raw]

    return ReviewContext(
        completed_todos=completed_todos,
        pending_todos=pending_todos,
        overdue_todos=overdue_todos,
        horizon=horizon,
        period_start=period_start,
        period_end=period_end,
        today=today,
        scope=scope,
    )


def build_review_prompt(
    context: ReviewContext,
    custom_prompt: str | None = None,
) -> str:
    """Build the LLM prompt for generating a review.

    Args:
        context: Review context with todos.
        custom_prompt: Optional custom instructions to append.

    Returns:
        Formatted prompt string.
    """
    parts = []

    # Header
    if context.horizon == "day":
        period_str = f"today ({context.today.strftime('%A, %B %d, %Y')})"
    else:
        period_str = (
            f"this week ({context.period_start.strftime('%B %d')} - "
            f"{context.period_end.strftime('%B %d, %Y')})"
        )

    parts.append(f"Please generate a review for {period_str}.\n")

    # Completed items
    parts.append("## COMPLETED ITEMS")
    if context.completed_todos:
        # Group by notebook
        by_notebook: dict[str, list[TodoContext]] = {}
        for todo in context.completed_todos:
            nb = todo.notebook or "other"
            if nb not in by_notebook:
                by_notebook[nb] = []
            by_notebook[nb].append(todo)

        for notebook, todos in sorted(by_notebook.items()):
            parts.append(f"\n### {notebook}")
            for todo in todos:
                tags_str = f" #{' #'.join(todo.tags)}" if todo.tags else ""
                parts.append(f"- [x] {todo.content}{tags_str}")
    else:
        parts.append("(No items completed)")
    parts.append("")

    # Carrying over items
    parts.append("## CARRYING OVER (still pending)")
    if context.pending_todos:
        for todo in context.pending_todos[:20]:  # Limit to top 20
            status_marker = "^" if todo.is_in_progress else " "
            priority_str = f" [P{todo.priority.value}]" if todo.priority else ""
            due_str = ""
            if todo.due_date:
                due_str = f" (due: {todo.due_date.strftime('%Y-%m-%d')})"
            overdue_str = " [OVERDUE]" if todo.is_overdue else ""
            age_str = f" ({todo.age_days}d old)" if todo.age_days > 3 else ""

            parts.append(
                f"- [{status_marker}] {todo.content}{priority_str}{due_str}"
                f"{overdue_str}{age_str}"
            )
    else:
        parts.append("(No pending items)")
    parts.append("")

    # Stats summary
    parts.append("## SUMMARY STATS")
    parts.append(f"- Completed: {len(context.completed_todos)}")
    parts.append(f"- Carrying over: {len(context.pending_todos)}")
    parts.append(f"- Overdue: {len(context.overdue_todos)}")
    parts.append("")

    # Custom instructions
    if custom_prompt:
        parts.append("## ADDITIONAL INSTRUCTIONS")
        parts.append(custom_prompt)
        parts.append("")

    return "\n".join(parts)


def _get_system_prompt(horizon: Literal["day", "week"]) -> str:
    """Get the system prompt for the given horizon."""
    improvements = IMPROVEMENTS_SECTION if horizon == "week" else ""
    return DEFAULT_REVIEW_SYSTEM_PROMPT.format(
        horizon=horizon,
        improvements_section=improvements,
    )


def generate_review(
    context: ReviewContext,
    use_smart_model: bool = True,
    custom_prompt: str | None = None,
) -> ReviewResult:
    """Generate a review using the LLM.

    Args:
        context: Review context.
        use_smart_model: Whether to use the smart (more capable) model.
        custom_prompt: Optional custom instructions.

    Returns:
        ReviewResult with the generated review.
    """
    system = _get_system_prompt(context.horizon)
    prompt = build_review_prompt(context, custom_prompt)

    client = get_llm_client()
    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )

    return ReviewResult(
        horizon=context.horizon,
        raw_response=response.content,
        completed_count=len(context.completed_todos),
        pending_count=len(context.pending_todos),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


def generate_review_stream(
    context: ReviewContext,
    use_smart_model: bool = True,
    custom_prompt: str | None = None,
) -> Iterator[StreamChunk]:
    """Stream the review generation.

    Args:
        context: Review context.
        use_smart_model: Whether to use the smart model.
        custom_prompt: Optional custom instructions.

    Yields:
        StreamChunk objects with content.
    """
    system = _get_system_prompt(context.horizon)
    prompt = build_review_prompt(context, custom_prompt)

    client = get_llm_client()
    yield from client.complete_stream(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )


def format_review_markdown(
    review: ReviewResult,
    section_title: str = "## Daily Review",
) -> str:
    """Format a review as markdown.

    Args:
        review: The review result to format.
        section_title: Title for the review section.

    Returns:
        Markdown-formatted review.
    """
    parts = [section_title, ""]
    parts.append(review.raw_response)
    return "\n".join(parts)


def append_review_to_note(
    review: ReviewResult,
    note_path: Path | None = None,
    section_title: str | None = None,
) -> Path:
    """Append the review to a note.

    Args:
        review: The review to append.
        note_path: Path to the note. If None, uses today's daily note.
        section_title: Title for the review section.

    Returns:
        Path to the note that was modified.
    """
    from nb.core.notes import ensure_daily_note

    config = get_config()

    if section_title is None:
        section_title = (
            "## Daily Review" if review.horizon == "day" else "## Weekly Review"
        )

    if note_path is None:
        note_path = ensure_daily_note(date.today())
    elif not note_path.is_absolute():
        note_path = config.notes_root / note_path

    # Ensure parent directory exists
    note_path.parent.mkdir(parents=True, exist_ok=True)

    # Format the review
    formatted = format_review_markdown(review, section_title=section_title)

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
