"""Backlog suggestion logic for planning and standup commands.

Provides light day detection and backlog item scoring to help
surface non-dated items when schedules allow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from nb.models import Priority

if TYPE_CHECKING:
    from nb.core.ai.planning import AvailabilityBlock, TodoContext


@dataclass
class BacklogConfig:
    """Configuration for backlog suggestions."""

    # Light day thresholds
    min_free_hours: float = 4.0  # Minimum free hours to consider light
    max_urgent_items: int = 3  # Maximum overdue + due_today items

    # Backlog limits
    max_suggestions: int = 5  # Maximum backlog items to suggest

    # Scoring weights (score = age_days + priority_weight * 7)
    priority_weights: dict[Priority | None, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.priority_weights:
            self.priority_weights = {
                Priority.HIGH: 3,
                Priority.MEDIUM: 2,
                Priority.LOW: 1,
                None: 0,
            }


@dataclass
class LightDayAnalysis:
    """Result of light day detection."""

    is_light: bool
    free_hours: float
    urgent_count: int
    reason: str  # Human-readable explanation


def calculate_free_hours(availability_blocks: list[AvailabilityBlock]) -> float:
    """Calculate total free hours from availability blocks.

    Args:
        availability_blocks: List of AvailabilityBlock from planning context.

    Returns:
        Total free hours as a float.
    """
    if not availability_blocks:
        return 0.0

    total_minutes = sum(block.duration_minutes for block in availability_blocks)
    return total_minutes / 60.0


def detect_light_day(
    availability_blocks: list[AvailabilityBlock],
    overdue_count: int,
    due_today_count: int,
    config: BacklogConfig | None = None,
) -> LightDayAnalysis:
    """Determine if today qualifies as a 'light day' suitable for backlog work.

    A light day is defined by the combination of:
    - Sufficient free time (calendar availability)
    - Low urgent item count (few overdue/due-today items)

    Args:
        availability_blocks: Free time blocks from calendar analysis.
        overdue_count: Number of overdue items.
        due_today_count: Number of items due today.
        config: Optional configuration overrides.

    Returns:
        LightDayAnalysis with detection result and reasoning.
    """
    if config is None:
        config = BacklogConfig()

    free_hours = calculate_free_hours(availability_blocks)
    urgent_count = overdue_count + due_today_count

    has_free_time = free_hours >= config.min_free_hours
    has_low_urgency = urgent_count <= config.max_urgent_items

    is_light = has_free_time and has_low_urgency

    # Build human-readable reason
    if is_light:
        reason = f"~{free_hours:.1f}h free with only {urgent_count} urgent item{'s' if urgent_count != 1 else ''}"
    elif not has_free_time:
        reason = f"Only {free_hours:.1f}h free (need {config.min_free_hours}h+)"
    else:
        reason = f"{urgent_count} urgent items (max {config.max_urgent_items})"

    return LightDayAnalysis(
        is_light=is_light,
        free_hours=free_hours,
        urgent_count=urgent_count,
        reason=reason,
    )


def score_backlog_item(
    todo: TodoContext,
    config: BacklogConfig | None = None,
) -> float:
    """Calculate priority score for a backlog item.

    Score = age_days + (priority_weight * 7)
    Higher score = suggested first (older and higher priority items surface first)

    Args:
        todo: The todo item to score.
        config: Optional configuration overrides.

    Returns:
        Numeric score (higher = more important to surface).
    """
    if config is None:
        config = BacklogConfig()

    priority_weight = config.priority_weights.get(todo.priority, 0)
    return todo.age_days + (priority_weight * 7)


def get_backlog_suggestions(
    todos: list[TodoContext],
    overdue_todos: list[TodoContext],
    in_progress_todos: list[TodoContext],
    due_today_todos: list[TodoContext] | None = None,
    config: BacklogConfig | None = None,
) -> list[TodoContext]:
    """Filter and rank todos to find backlog suggestions.

    Backlog items are defined as:
    - Not overdue
    - Not in progress
    - Not due today (if due_today_todos provided)
    - Has no due date OR due date is in the future (not within urgent window)

    Args:
        todos: All incomplete todos.
        overdue_todos: Items that are overdue (to exclude).
        in_progress_todos: Items in progress (to exclude).
        due_today_todos: Items due today (to exclude), optional.
        config: Optional configuration overrides.

    Returns:
        List of TodoContext items, sorted by score (highest first), limited to max_suggestions.
    """
    if config is None:
        config = BacklogConfig()

    # Build exclusion sets
    exclude_ids = {t.id for t in overdue_todos}
    exclude_ids.update(t.id for t in in_progress_todos)
    if due_today_todos:
        exclude_ids.update(t.id for t in due_today_todos)

    # Filter to backlog items (no due date or future due date, not excluded)
    backlog = []
    for todo in todos:
        if todo.id in exclude_ids:
            continue
        if todo.is_overdue:
            continue
        # Exclude items with a due date in the near future (within a week)
        # These are already being tracked - we want truly non-urgent items
        if todo.due_date is not None:
            continue
        backlog.append(todo)

    # Score and sort (highest score first)
    scored = [(score_backlog_item(todo, config), todo) for todo in backlog]
    scored.sort(key=lambda x: -x[0])  # Descending by score

    # Return top N
    return [todo for _, todo in scored[: config.max_suggestions]]
