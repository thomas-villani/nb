"""Tests for backlog suggestion functionality."""

from __future__ import annotations

from datetime import datetime, time

from nb.core.ai.backlog import (
    BacklogConfig,
    LightDayAnalysis,
    calculate_free_hours,
    detect_light_day,
    get_backlog_suggestions,
    score_backlog_item,
)
from nb.core.ai.planning import AvailabilityBlock, TodoContext
from nb.models import Priority


class TestCalculateFreeHours:
    """Tests for free hours calculation."""

    def test_empty_blocks(self):
        """No blocks means no free time."""
        assert calculate_free_hours([]) == 0.0

    def test_single_block(self):
        """Single 4-hour block."""
        block = AvailabilityBlock(
            start=datetime(2025, 1, 15, 9, 0),
            end=datetime(2025, 1, 15, 13, 0),
        )
        assert calculate_free_hours([block]) == 4.0

    def test_multiple_blocks(self):
        """Multiple blocks sum correctly."""
        blocks = [
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 9, 0),
                end=datetime(2025, 1, 15, 10, 0),
            ),  # 1 hour
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 11, 0),
                end=datetime(2025, 1, 15, 13, 0),
            ),  # 2 hours
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 14, 0),
                end=datetime(2025, 1, 15, 17, 0),
            ),  # 3 hours
        ]
        assert calculate_free_hours(blocks) == 6.0

    def test_fractional_hours(self):
        """Handles non-whole hour durations."""
        block = AvailabilityBlock(
            start=datetime(2025, 1, 15, 9, 0),
            end=datetime(2025, 1, 15, 10, 30),
        )
        assert calculate_free_hours([block]) == 1.5


class TestDetectLightDay:
    """Tests for light day detection."""

    def test_light_day_both_conditions_met(self):
        """Light day when enough free time and few urgent items."""
        blocks = [
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 9, 0),
                end=datetime(2025, 1, 15, 14, 0),
            ),  # 5 hours
        ]
        result = detect_light_day(blocks, overdue_count=1, due_today_count=1)

        assert result.is_light is True
        assert result.free_hours == 5.0
        assert result.urgent_count == 2
        assert "5.0h free" in result.reason

    def test_not_light_insufficient_time(self):
        """Not light day when not enough free time."""
        blocks = [
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 9, 0),
                end=datetime(2025, 1, 15, 11, 0),
            ),  # 2 hours
        ]
        result = detect_light_day(blocks, overdue_count=0, due_today_count=0)

        assert result.is_light is False
        assert "2.0h free" in result.reason
        assert "need 4.0h+" in result.reason

    def test_not_light_too_many_urgent(self):
        """Not light day when too many urgent items."""
        blocks = [
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 9, 0),
                end=datetime(2025, 1, 15, 17, 0),
            ),  # 8 hours
        ]
        result = detect_light_day(blocks, overdue_count=3, due_today_count=2)

        assert result.is_light is False
        assert result.urgent_count == 5
        assert "5 urgent items" in result.reason

    def test_custom_config_thresholds(self):
        """Custom thresholds are respected."""
        blocks = [
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 9, 0),
                end=datetime(2025, 1, 15, 11, 0),
            ),  # 2 hours
        ]
        config = BacklogConfig(min_free_hours=2.0, max_urgent_items=5)
        result = detect_light_day(blocks, overdue_count=3, due_today_count=2, config=config)

        assert result.is_light is True  # Now meets threshold

    def test_no_calendar_no_free_time(self):
        """Empty blocks means no free time detected."""
        result = detect_light_day([], overdue_count=0, due_today_count=0)

        assert result.is_light is False
        assert result.free_hours == 0.0

    def test_boundary_conditions(self):
        """Test exact threshold values."""
        blocks = [
            AvailabilityBlock(
                start=datetime(2025, 1, 15, 9, 0),
                end=datetime(2025, 1, 15, 13, 0),
            ),  # Exactly 4 hours
        ]
        # Exactly 3 urgent items (at threshold)
        result = detect_light_day(blocks, overdue_count=2, due_today_count=1)

        assert result.is_light is True  # Both at threshold = light


class TestScoreBacklogItem:
    """Tests for backlog item scoring."""

    def test_age_only_no_priority(self):
        """Score equals age when no priority."""
        todo = TodoContext(
            id="abc",
            content="Test task",
            due_date=None,
            priority=None,
            tags=[],
            notebook="projects",
            source_note="test.md",
            age_days=10,
            is_overdue=False,
            is_in_progress=False,
        )
        assert score_backlog_item(todo) == 10  # 10 + 0*7

    def test_high_priority_boost(self):
        """HIGH priority adds 21 points."""
        todo = TodoContext(
            id="abc",
            content="Test task",
            due_date=None,
            priority=Priority.HIGH,
            tags=[],
            notebook="projects",
            source_note="test.md",
            age_days=5,
            is_overdue=False,
            is_in_progress=False,
        )
        assert score_backlog_item(todo) == 26  # 5 + 3*7

    def test_medium_priority_boost(self):
        """MEDIUM priority adds 14 points."""
        todo = TodoContext(
            id="abc",
            content="Test task",
            due_date=None,
            priority=Priority.MEDIUM,
            tags=[],
            notebook="projects",
            source_note="test.md",
            age_days=5,
            is_overdue=False,
            is_in_progress=False,
        )
        assert score_backlog_item(todo) == 19  # 5 + 2*7

    def test_low_priority_boost(self):
        """LOW priority adds 7 points."""
        todo = TodoContext(
            id="abc",
            content="Test task",
            due_date=None,
            priority=Priority.LOW,
            tags=[],
            notebook="projects",
            source_note="test.md",
            age_days=5,
            is_overdue=False,
            is_in_progress=False,
        )
        assert score_backlog_item(todo) == 12  # 5 + 1*7

    def test_old_item_beats_priority(self):
        """Very old item can outrank higher priority newer item."""
        old_no_priority = TodoContext(
            id="old",
            content="Old task",
            due_date=None,
            priority=None,
            tags=[],
            notebook="projects",
            source_note="test.md",
            age_days=30,
            is_overdue=False,
            is_in_progress=False,
        )
        new_high_priority = TodoContext(
            id="new",
            content="New urgent task",
            due_date=None,
            priority=Priority.HIGH,
            tags=[],
            notebook="projects",
            source_note="test.md",
            age_days=1,
            is_overdue=False,
            is_in_progress=False,
        )
        # old: 30, new: 1+21=22
        assert score_backlog_item(old_no_priority) > score_backlog_item(new_high_priority)


class TestGetBacklogSuggestions:
    """Tests for backlog suggestion filtering and ranking."""

    def _make_todo(
        self,
        id: str,
        age_days: int,
        priority: Priority | None = None,
        due_date: datetime | None = None,
        is_overdue: bool = False,
        is_in_progress: bool = False,
    ) -> TodoContext:
        """Helper to create TodoContext for testing."""
        return TodoContext(
            id=id,
            content=f"Task {id}",
            due_date=due_date,
            priority=priority,
            tags=[],
            notebook="projects",
            source_note="test.md",
            age_days=age_days,
            is_overdue=is_overdue,
            is_in_progress=is_in_progress,
        )

    def test_excludes_overdue_items(self):
        """Overdue items are not suggested as backlog."""
        overdue = self._make_todo("1", age_days=10, is_overdue=True)
        normal = self._make_todo("2", age_days=5)
        todos = [overdue, normal]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[overdue],
            in_progress_todos=[],
            due_today_todos=[],
        )

        ids = [t.id for t in result]
        assert "1" not in ids
        assert "2" in ids

    def test_excludes_in_progress_items(self):
        """In-progress items are not suggested as backlog."""
        in_progress = self._make_todo("1", age_days=10, is_in_progress=True)
        normal = self._make_todo("2", age_days=5)
        todos = [in_progress, normal]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[],
            in_progress_todos=[in_progress],
            due_today_todos=[],
        )

        ids = [t.id for t in result]
        assert "1" not in ids
        assert "2" in ids

    def test_excludes_due_today_items(self):
        """Items due today are not suggested as backlog."""
        due_today = self._make_todo("1", age_days=10, due_date=datetime(2025, 1, 15))
        normal = self._make_todo("2", age_days=5)
        todos = [due_today, normal]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[],
            in_progress_todos=[],
            due_today_todos=[due_today],
        )

        ids = [t.id for t in result]
        assert "1" not in ids
        assert "2" in ids

    def test_excludes_items_with_due_dates(self):
        """Items with any due date are excluded (they're already scheduled)."""
        with_due = self._make_todo("1", age_days=10, due_date=datetime(2025, 1, 20))
        without_due = self._make_todo("2", age_days=5)
        todos = [with_due, without_due]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[],
            in_progress_todos=[],
            due_today_todos=[],
        )

        ids = [t.id for t in result]
        assert "1" not in ids
        assert "2" in ids

    def test_limits_to_max_suggestions(self):
        """Result is limited to max_suggestions."""
        todos = [self._make_todo(str(i), age_days=i) for i in range(10)]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[],
            in_progress_todos=[],
            due_today_todos=[],
        )

        assert len(result) == 5  # Default max

    def test_custom_max_suggestions(self):
        """Custom max_suggestions is respected."""
        todos = [self._make_todo(str(i), age_days=i) for i in range(10)]
        config = BacklogConfig(max_suggestions=3)

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[],
            in_progress_todos=[],
            due_today_todos=[],
            config=config,
        )

        assert len(result) == 3

    def test_sorted_by_score_descending(self):
        """Results sorted by score (highest first)."""
        old_no_priority = self._make_todo("old", age_days=20)
        new_high_priority = self._make_todo("new", age_days=1, priority=Priority.HIGH)
        medium_age_medium_priority = self._make_todo("mid", age_days=10, priority=Priority.MEDIUM)
        todos = [new_high_priority, old_no_priority, medium_age_medium_priority]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[],
            in_progress_todos=[],
            due_today_todos=[],
        )

        # Scores: new=22, old=20, mid=24
        assert result[0].id == "mid"  # 24
        assert result[1].id == "new"  # 22
        assert result[2].id == "old"  # 20

    def test_empty_when_no_eligible_items(self):
        """Returns empty list when all items are excluded."""
        overdue = self._make_todo("1", age_days=10, is_overdue=True)
        in_progress = self._make_todo("2", age_days=5, is_in_progress=True)
        todos = [overdue, in_progress]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[overdue],
            in_progress_todos=[in_progress],
            due_today_todos=[],
        )

        assert result == []

    def test_handles_none_due_today(self):
        """Works when due_today_todos is None."""
        todo = self._make_todo("1", age_days=10)
        todos = [todo]

        result = get_backlog_suggestions(
            todos=todos,
            overdue_todos=[],
            in_progress_todos=[],
            due_today_todos=None,
        )

        assert len(result) == 1


class TestBacklogConfig:
    """Tests for BacklogConfig dataclass."""

    def test_default_values(self):
        """Default configuration values."""
        config = BacklogConfig()

        assert config.min_free_hours == 4.0
        assert config.max_urgent_items == 3
        assert config.max_suggestions == 5

    def test_default_priority_weights(self):
        """Default priority weights are set."""
        config = BacklogConfig()

        assert config.priority_weights[Priority.HIGH] == 3
        assert config.priority_weights[Priority.MEDIUM] == 2
        assert config.priority_weights[Priority.LOW] == 1
        assert config.priority_weights[None] == 0

    def test_custom_priority_weights(self):
        """Custom priority weights are respected."""
        custom_weights = {
            Priority.HIGH: 10,
            Priority.MEDIUM: 5,
            Priority.LOW: 2,
            None: 0,
        }
        config = BacklogConfig(priority_weights=custom_weights)

        assert config.priority_weights[Priority.HIGH] == 10


class TestLightDayAnalysis:
    """Tests for LightDayAnalysis dataclass."""

    def test_dataclass_creation(self):
        """Can create LightDayAnalysis."""
        analysis = LightDayAnalysis(
            is_light=True,
            free_hours=5.5,
            urgent_count=2,
            reason="~5.5h free with only 2 urgent items",
        )

        assert analysis.is_light is True
        assert analysis.free_hours == 5.5
        assert analysis.urgent_count == 2
        assert "5.5h" in analysis.reason
