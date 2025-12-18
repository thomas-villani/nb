"""Tests for AI planning functionality."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from nb.core.ai.planning import (
    PlanningContext,
    PlanResult,
    PlanScope,
    PlanWarning,
    TodoContext,
    _compute_availability_blocks,
    _extract_warnings,
    build_planning_prompt,
    create_planning_session,
    format_plan_markdown,
)
from nb.models import Priority, Todo, TodoSource, TodoStatus


class TestTodoContext:
    """Tests for TodoContext creation."""

    def test_from_todo_basic(self):
        """Test basic TodoContext creation from Todo."""
        todo = Todo(
            id="abc12345",
            content="Test task",
            raw_content="- [ ] Test task",
            status=TodoStatus.PENDING,
            source=TodoSource(type="note", path=Path("projects/test.md")),
            line_number=1,
            created_date=date(2025, 1, 10),
            tags=["work"],
            notebook="projects",
        )

        ctx = TodoContext.from_todo(todo, today=date(2025, 1, 15))

        assert ctx.id == "abc12345"
        assert ctx.content == "Test task"
        assert ctx.age_days == 5
        assert ctx.is_overdue is False
        assert ctx.is_in_progress is False

    def test_from_todo_overdue(self):
        """Test TodoContext marks overdue items."""
        todo = Todo(
            id="abc12345",
            content="Overdue task",
            raw_content="- [ ] Overdue task @due(2025-01-10)",
            status=TodoStatus.PENDING,
            source=TodoSource(type="note", path=Path("projects/test.md")),
            line_number=1,
            created_date=date(2025, 1, 5),
            due_date=datetime(2025, 1, 10),
            tags=[],
            notebook="projects",
        )

        ctx = TodoContext.from_todo(todo, today=date(2025, 1, 15))

        assert ctx.is_overdue is True

    def test_from_todo_in_progress(self):
        """Test TodoContext marks in-progress items."""
        todo = Todo(
            id="abc12345",
            content="In progress task",
            raw_content="- [^] In progress task",
            status=TodoStatus.IN_PROGRESS,
            source=TodoSource(type="note", path=Path("projects/test.md")),
            line_number=1,
            created_date=date(2025, 1, 10),
            tags=[],
            notebook="projects",
        )

        ctx = TodoContext.from_todo(todo, today=date(2025, 1, 15))

        assert ctx.is_in_progress is True


class TestAvailabilityBlocks:
    """Tests for availability block computation."""

    def test_compute_availability_no_events(self):
        """Full day available when no events."""
        from datetime import time

        events = []
        blocks = _compute_availability_blocks(
            events,
            start_date=date(2025, 1, 15),
            horizon="day",
            work_start=time(9, 0),
            work_end=time(17, 0),
        )

        assert len(blocks) == 1
        assert blocks[0].duration_minutes == 8 * 60  # 8 hours

    def test_compute_availability_with_meeting(self):
        """Availability blocks around meetings."""
        from datetime import time

        from nb.core.calendar import CalendarEvent

        events = [
            CalendarEvent(
                subject="Meeting",
                start=datetime(2025, 1, 15, 10, 0),
                end=datetime(2025, 1, 15, 11, 0),
            )
        ]

        blocks = _compute_availability_blocks(
            events,
            start_date=date(2025, 1, 15),
            horizon="day",
            work_start=time(9, 0),
            work_end=time(17, 0),
        )

        # Should have 2 blocks: 9-10 and 11-17
        assert len(blocks) == 2
        assert blocks[0].duration_minutes == 60  # 9-10
        assert blocks[1].duration_minutes == 360  # 11-17 (6 hours)

    def test_compute_availability_week_horizon(self):
        """Availability computed for full week."""
        from datetime import time

        events = []
        blocks = _compute_availability_blocks(
            events,
            start_date=date(2025, 1, 13),  # Monday
            horizon="week",
            work_start=time(9, 0),
            work_end=time(17, 0),
        )

        # Should have 7 blocks (one per day)
        assert len(blocks) == 7
        total_minutes = sum(b.duration_minutes for b in blocks)
        assert total_minutes == 7 * 8 * 60  # 7 days * 8 hours


class TestBuildPlanningPrompt:
    """Tests for planning prompt construction."""

    def test_build_prompt_includes_todos(self):
        """Verify todos are formatted in prompt."""
        context = PlanningContext(
            todos=[
                TodoContext(
                    id="abc",
                    content="Test task",
                    due_date=None,
                    priority=Priority.HIGH,
                    tags=["work"],
                    notebook="projects",
                    source_note="projects/test.md",
                    age_days=3,
                    is_overdue=False,
                    is_in_progress=False,
                )
            ],
            overdue_todos=[],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        prompt = build_planning_prompt(context)

        assert "Test task" in prompt
        assert "[P1]" in prompt  # Priority
        assert "#work" in prompt  # Tag
        assert "[projects]" in prompt  # Notebook

    def test_build_prompt_highlights_overdue(self):
        """Verify overdue items are highlighted."""
        overdue_todo = TodoContext(
            id="abc",
            content="Overdue task",
            due_date=datetime(2025, 1, 10),
            priority=None,
            tags=[],
            notebook="projects",
            source_note="projects/test.md",
            age_days=10,
            is_overdue=True,
            is_in_progress=False,
        )

        context = PlanningContext(
            todos=[overdue_todo],
            overdue_todos=[overdue_todo],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        prompt = build_planning_prompt(context)

        assert "OVERDUE ITEMS" in prompt
        assert "Overdue task" in prompt

    def test_build_prompt_includes_calendar(self):
        """Verify calendar events are in prompt."""
        from nb.core.calendar import CalendarEvent

        context = PlanningContext(
            todos=[],
            overdue_todos=[],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[
                CalendarEvent(
                    subject="Team Sync",
                    start=datetime(2025, 1, 15, 10, 0),
                    end=datetime(2025, 1, 15, 11, 0),
                )
            ],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        prompt = build_planning_prompt(context)

        assert "CALENDAR" in prompt
        assert "Team Sync" in prompt

    def test_build_prompt_custom_instructions(self):
        """Verify custom prompt is appended."""
        context = PlanningContext(
            todos=[],
            overdue_todos=[],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        prompt = build_planning_prompt(
            context, custom_prompt="Focus on urgent items only"
        )

        assert "ADDITIONAL INSTRUCTIONS" in prompt
        assert "Focus on urgent items only" in prompt


class TestExtractWarnings:
    """Tests for warning extraction."""

    def test_extract_overdue_warnings(self):
        """Test overdue items generate warnings."""
        context = PlanningContext(
            todos=[],
            overdue_todos=[
                TodoContext(
                    id="abc",
                    content="Overdue task",
                    due_date=datetime(2025, 1, 10),
                    priority=None,
                    tags=[],
                    notebook="projects",
                    source_note="test.md",
                    age_days=10,
                    is_overdue=True,
                    is_in_progress=False,
                )
            ],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        warnings = _extract_warnings(context)

        assert len(warnings) == 1
        assert warnings[0].type == "overdue"
        assert "Overdue task" in warnings[0].message

    def test_extract_stale_warnings(self):
        """Test stale items generate warnings."""
        context = PlanningContext(
            todos=[
                TodoContext(
                    id="abc",
                    content="Stale task",
                    due_date=None,
                    priority=None,
                    tags=[],
                    notebook="projects",
                    source_note="test.md",
                    age_days=20,  # More than 14 days
                    is_overdue=False,
                    is_in_progress=False,
                )
            ],
            overdue_todos=[],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        warnings = _extract_warnings(context)

        assert len(warnings) == 1
        assert warnings[0].type == "stale"
        assert "20 days" in warnings[0].message


class TestFormatPlanMarkdown:
    """Tests for plan markdown formatting."""

    def test_format_basic_plan(self):
        """Test basic plan formatting."""
        plan = PlanResult(
            horizon="week",
            raw_response="## Monday\n- Task 1\n- Task 2\n\n## Tuesday\n- Task 3",
            warnings=[],
        )

        markdown = format_plan_markdown(plan)

        assert "## Plan" in markdown
        assert "## Monday" in markdown
        assert "Task 1" in markdown

    def test_format_plan_with_warnings(self):
        """Test plan formatting includes warnings."""
        plan = PlanResult(
            horizon="week",
            raw_response="Focus on urgent items.",
            warnings=[
                PlanWarning(type="overdue", message="Task X is overdue"),
            ],
        )

        markdown = format_plan_markdown(plan, include_warnings=True)

        assert "### Warnings" in markdown
        assert "overdue" in markdown
        assert "Task X is overdue" in markdown

    def test_format_plan_custom_title(self):
        """Test custom section title."""
        plan = PlanResult(
            horizon="day",
            raw_response="Today's plan",
            warnings=[],
        )

        markdown = format_plan_markdown(plan, section_title="## Daily Plan")

        assert "## Daily Plan" in markdown


class TestPlanningSession:
    """Tests for interactive planning session."""

    def test_create_session(self):
        """Test session creation."""
        context = PlanningContext(
            todos=[],
            overdue_todos=[],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        session = create_planning_session(context)

        assert session.context == context
        assert session.messages == []
        assert session.current_plan is None
        assert session.system_prompt is not None

    def test_create_session_custom_prompt(self):
        """Test session creation with custom system prompt."""
        context = PlanningContext(
            todos=[],
            overdue_todos=[],
            in_progress_todos=[],
            recent_notes=[],
            calendar_events=[],
            availability_blocks=[],
            horizon="week",
            today=date(2025, 1, 15),
            scope=PlanScope(),
        )

        custom_prompt = "You are a focused productivity assistant."
        session = create_planning_session(context, system_prompt=custom_prompt)

        assert session.system_prompt == custom_prompt
