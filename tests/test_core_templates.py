"""Tests for template functionality."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nb import config as config_module
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.core import notebooks as notebooks_module
from nb.core import templates as templates_module
from nb.models import Priority, Todo, TodoSource, TodoStatus


class TestTemplateOperations:
    """Tests for template CRUD operations."""

    def test_list_templates_empty(self, temp_notes_root: Path) -> None:
        """Empty templates directory returns empty list."""
        from nb.core.templates import list_templates

        assert list_templates(temp_notes_root) == []

    def test_create_and_list_template(self, temp_notes_root: Path) -> None:
        """Create a template and verify it's listed."""
        from nb.core.templates import create_template, list_templates

        create_template("meeting", "# Meeting Notes\n", temp_notes_root)

        templates = list_templates(temp_notes_root)
        assert "meeting" in templates

    def test_create_template_creates_directory(self, temp_notes_root: Path) -> None:
        """Templates directory is created automatically."""
        from nb.core.templates import create_template, get_templates_dir

        templates_dir = get_templates_dir(temp_notes_root)
        assert not templates_dir.exists()

        create_template("test", "content", temp_notes_root)

        assert templates_dir.exists()
        assert templates_dir.is_dir()

    def test_create_duplicate_template_fails(self, temp_notes_root: Path) -> None:
        """Creating duplicate template raises FileExistsError."""
        from nb.core.templates import create_template

        create_template("test", "content", temp_notes_root)

        with pytest.raises(FileExistsError):
            create_template("test", "other content", temp_notes_root)

    def test_read_template(self, temp_notes_root: Path) -> None:
        """Read template content."""
        from nb.core.templates import create_template, read_template

        content = "# Test Template\n\n{{ date }}"
        create_template("test", content, temp_notes_root)

        assert read_template("test", temp_notes_root) == content

    def test_read_nonexistent_template(self, temp_notes_root: Path) -> None:
        """Reading nonexistent template returns None."""
        from nb.core.templates import read_template

        assert read_template("nonexistent", temp_notes_root) is None

    def test_template_exists(self, temp_notes_root: Path) -> None:
        """Check if template exists."""
        from nb.core.templates import create_template, template_exists

        assert not template_exists("test", temp_notes_root)

        create_template("test", "content", temp_notes_root)

        assert template_exists("test", temp_notes_root)

    def test_remove_template(self, temp_notes_root: Path) -> None:
        """Remove an existing template."""
        from nb.core.templates import create_template, remove_template, template_exists

        create_template("test", "content", temp_notes_root)
        assert template_exists("test", temp_notes_root)

        assert remove_template("test", temp_notes_root) is True
        assert not template_exists("test", temp_notes_root)

    def test_remove_nonexistent_template(self, temp_notes_root: Path) -> None:
        """Removing nonexistent template returns False."""
        from nb.core.templates import remove_template

        assert remove_template("nonexistent", temp_notes_root) is False

    def test_get_template_path(self, temp_notes_root: Path) -> None:
        """Get template path."""
        from nb.core.templates import get_template_path

        path = get_template_path("meeting", temp_notes_root)
        assert path == temp_notes_root / ".nb" / "templates" / "meeting.md"


class TestTemplateRendering:
    """Tests for template variable rendering."""

    def test_render_date_variable(self) -> None:
        """Render {{ date }} variable."""
        from nb.core.templates import render_template

        content = "Date: {{ date }}"
        result = render_template(content, dt=date(2025, 11, 29))

        assert result == "Date: 2025-11-29"

    def test_render_title_variable(self) -> None:
        """Render {{ title }} variable."""
        from nb.core.templates import render_template

        content = "# {{ title }}"
        result = render_template(content, title="My Note")

        assert result == "# My Note"

    def test_render_notebook_variable(self) -> None:
        """Render {{ notebook }} variable."""
        from nb.core.templates import render_template

        content = "Notebook: {{ notebook }}"
        result = render_template(content, notebook="projects")

        assert result == "Notebook: projects"

    def test_render_datetime_variable(self) -> None:
        """Render {{ datetime }} variable."""
        from nb.core.templates import render_template

        content = "Created: {{ datetime }}"
        result = render_template(content)

        # Should contain a datetime-like string (YYYY-MM-DDTHH:MM)
        assert "Created: " in result
        assert "T" in result.split("Created: ")[1]

    def test_render_multiple_variables(self) -> None:
        """Render multiple variables in same template."""
        from nb.core.templates import render_template

        content = "---\ndate: {{ date }}\n---\n\n# {{ title }}\n\nIn {{ notebook }}"
        result = render_template(
            content,
            title="Test Note",
            notebook="work",
            dt=date(2025, 11, 29),
        )

        assert "date: 2025-11-29" in result
        assert "# Test Note" in result
        assert "In work" in result

    def test_render_empty_variable(self) -> None:
        """Empty variables render as empty strings."""
        from nb.core.templates import render_template

        content = "Title: {{ title }}"
        result = render_template(content)  # No title provided

        assert result == "Title: "

    def test_render_default_date(self) -> None:
        """Date defaults to today if not provided."""
        from nb.core.templates import render_template

        content = "Date: {{ date }}"
        result = render_template(content)

        # Should contain today's date
        assert "Date: " in result
        assert date.today().isoformat() in result


class TestNoteCreationWithTemplate:
    """Tests for creating notes with templates."""

    def test_create_note_with_template(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Create note using a template."""
        from nb.core.notes import create_note
        from nb.core.templates import create_template

        # Create a template
        create_template(
            "test",
            "---\ndate: {{ date }}\n---\n\n# {{ title }}\n\nCustom template content!\n",
            temp_notes_root,
        )

        # Create note with template
        note_path = create_note(
            Path("projects/test-note"),
            title="My Test",
            template="test",
            notes_root=temp_notes_root,
        )

        content = note_path.read_text()
        assert "# My Test" in content
        assert "Custom template content!" in content

    def test_create_note_without_template(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Create note without template uses default."""
        from nb.core.notes import create_note

        note_path = create_note(
            Path("projects/test-note"),
            title="Default Note",
            notes_root=temp_notes_root,
        )

        content = note_path.read_text()
        assert "# Default Note" in content

    def test_create_note_with_missing_template_falls_back(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Create note with missing template falls back to default."""
        from nb.core.notes import create_note

        note_path = create_note(
            Path("projects/test-note"),
            title="Fallback Note",
            template="nonexistent",  # Template doesn't exist
            notes_root=temp_notes_root,
        )

        # Should still create note with default template
        content = note_path.read_text()
        assert "# Fallback Note" in content


class TestNotebookDefaultTemplate:
    """Tests for notebook default templates."""

    def test_notebook_with_default_template(
        self, temp_notes_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Notebook with default template uses it for new notes."""
        from nb.core.notebooks import ensure_notebook_note
        from nb.core.templates import create_template

        # Create template
        create_template(
            "daily-custom",
            "---\ndate: {{ date }}\n---\n\n# {{ title }}\n\nCustom daily template!\n",
            temp_notes_root,
        )

        # Create config with template
        cfg = Config(
            notes_root=temp_notes_root,
            editor="nano",
            notebooks=[
                NotebookConfig(name="daily", date_based=True, template="daily-custom"),
            ],
            embeddings=EmbeddingsConfig(),
        )
        # Patch get_config in all modules that import it at module level
        monkeypatch.setattr(config_module, "get_config", lambda: cfg)
        monkeypatch.setattr(notebooks_module, "get_config", lambda: cfg)
        monkeypatch.setattr(templates_module, "get_config", lambda: cfg)

        # Create daily directory
        (temp_notes_root / "daily").mkdir(exist_ok=True)

        # Create note - should use template
        note_path = ensure_notebook_note("daily", dt=date(2025, 11, 29))

        content = note_path.read_text()
        assert "Custom daily template!" in content

    def test_explicit_template_overrides_notebook_default(
        self, temp_notes_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit template parameter overrides notebook default."""
        from nb.core.notebooks import ensure_notebook_note
        from nb.core.templates import create_template

        # Create two templates
        create_template("default-tmpl", "Default template content", temp_notes_root)
        create_template("override-tmpl", "Override template content", temp_notes_root)

        # Config with default template
        cfg = Config(
            notes_root=temp_notes_root,
            editor="nano",
            notebooks=[
                NotebookConfig(name="daily", date_based=True, template="default-tmpl"),
            ],
            embeddings=EmbeddingsConfig(),
        )
        # Patch get_config in all modules that import it at module level
        monkeypatch.setattr(config_module, "get_config", lambda: cfg)
        monkeypatch.setattr(notebooks_module, "get_config", lambda: cfg)
        monkeypatch.setattr(templates_module, "get_config", lambda: cfg)

        (temp_notes_root / "daily").mkdir(exist_ok=True)

        # Create note with explicit template
        note_path = ensure_notebook_note(
            "daily", dt=date(2025, 11, 29), template="override-tmpl"
        )

        content = note_path.read_text()
        assert "Override template content" in content
        assert "Default template content" not in content

    def test_notebook_without_default_template_uses_builtin(
        self, temp_notes_root: Path, mock_config: Config
    ) -> None:
        """Notebook without default template uses built-in."""
        from nb.core.notebooks import ensure_notebook_note

        (temp_notes_root / "daily").mkdir(exist_ok=True)

        note_path = ensure_notebook_note("daily", dt=date(2025, 11, 29))

        content = note_path.read_text()
        # Built-in template format
        assert "date: 2025-11-29" in content
        assert "# Saturday, November 29, 2025" in content


class TestFormatTodosForTemplate:
    """Tests for todo formatting in templates."""

    def _make_todo(
        self,
        id: str,
        content: str,
        status: TodoStatus = TodoStatus.PENDING,
        priority: Priority | None = None,
    ) -> Todo:
        """Create a test todo."""
        return Todo(
            id=id,
            content=content,
            raw_content=f"- [ ] {content}",
            status=status,
            source=TodoSource(type="note", path=Path("test.md")),
            line_number=1,
            created_date=date.today(),
            priority=priority,
        )

    def test_empty_todos(self) -> None:
        """Empty todo list shows placeholder."""
        from nb.core.templates import format_todos_for_template

        result = format_todos_for_template([])
        assert result == "_No todos_"

    def test_single_todo(self) -> None:
        """Single todo formats correctly."""
        from nb.core.templates import format_todos_for_template

        todos = [self._make_todo("abc12345", "Fix the bug")]
        result = format_todos_for_template(todos)

        assert result == "- Fix the bug [todo:abc123]"

    def test_multiple_todos(self) -> None:
        """Multiple todos format as list."""
        from nb.core.templates import format_todos_for_template

        todos = [
            self._make_todo("abc12345", "First task"),
            self._make_todo("def67890", "Second task"),
        ]
        result = format_todos_for_template(todos)

        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "- First task [todo:abc123]"
        assert lines[1] == "- Second task [todo:def678]"

    def test_todo_id_truncation(self) -> None:
        """Todo IDs are truncated to 6 chars."""
        from nb.core.templates import format_todos_for_template

        todos = [self._make_todo("abcdef123456789", "Task")]
        result = format_todos_for_template(todos)

        assert "[todo:abcdef]" in result
        assert "123456789" not in result


class TestFormatCalendarForTemplate:
    """Tests for calendar event formatting in templates."""

    def _make_event(
        self,
        subject: str,
        start: datetime,
        end: datetime,
        is_all_day: bool = False,
    ) -> MagicMock:
        """Create a mock calendar event."""
        event = MagicMock()
        event.subject = subject
        event.start = start
        event.end = end
        event.is_all_day = is_all_day
        return event

    def test_empty_events(self) -> None:
        """Empty event list shows placeholder."""
        from nb.core.templates import format_calendar_for_template

        result = format_calendar_for_template([])
        assert result == "_No meetings_"

    def test_single_timed_event(self) -> None:
        """Single timed event formats correctly."""
        from nb.core.templates import format_calendar_for_template

        events = [
            self._make_event(
                "Team Standup",
                datetime(2025, 12, 23, 9, 0),
                datetime(2025, 12, 23, 9, 30),
            )
        ]
        result = format_calendar_for_template(events)

        assert result == "- 9:00 AM - 9:30 AM: Team Standup"

    def test_all_day_event(self) -> None:
        """All-day event formats correctly."""
        from nb.core.templates import format_calendar_for_template

        events = [
            self._make_event(
                "Company Holiday",
                datetime(2025, 12, 25, 0, 0),
                datetime(2025, 12, 25, 23, 59),
                is_all_day=True,
            )
        ]
        result = format_calendar_for_template(events)

        assert result == "- (All day) Company Holiday"

    def test_multiple_events(self) -> None:
        """Multiple events format as list."""
        from nb.core.templates import format_calendar_for_template

        events = [
            self._make_event(
                "Morning Standup",
                datetime(2025, 12, 23, 9, 0),
                datetime(2025, 12, 23, 9, 30),
            ),
            self._make_event(
                "Lunch",
                datetime(2025, 12, 23, 12, 0),
                datetime(2025, 12, 23, 13, 0),
            ),
        ]
        result = format_calendar_for_template(events)

        lines = result.split("\n")
        assert len(lines) == 2
        assert "Morning Standup" in lines[0]
        assert "Lunch" in lines[1]

    def test_pm_time_formatting(self) -> None:
        """PM times format correctly."""
        from nb.core.templates import format_calendar_for_template

        events = [
            self._make_event(
                "Afternoon Meeting",
                datetime(2025, 12, 23, 14, 30),
                datetime(2025, 12, 23, 15, 0),
            )
        ]
        result = format_calendar_for_template(events)

        assert "2:30 PM - 3:00 PM" in result


class TestDynamicTemplateVariables:
    """Tests for dynamic template variables (todos and calendar)."""

    def test_todos_overdue_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """{{ todos_overdue }} renders overdue todos."""
        from nb.core import templates

        # Mock the query function
        def mock_query_todos(**kwargs):
            if kwargs.get("overdue"):
                return [
                    Todo(
                        id="over1234",
                        content="Overdue task",
                        raw_content="- [ ] Overdue task",
                        status=TodoStatus.PENDING,
                        source=TodoSource(type="note", path=Path("test.md")),
                        line_number=1,
                        created_date=date.today(),
                    )
                ]
            return []

        # Patch at the source module (where it gets imported from)
        monkeypatch.setattr("nb.index.todos_repo.query_todos", mock_query_todos)

        content = "## Overdue\n{{ todos_overdue }}"
        result = templates.render_template(content)

        assert "- Overdue task [todo:over12]" in result

    def test_todos_due_today_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """{{ todos_due_today }} renders todos due today."""
        from nb.core import templates

        def mock_query_todos(**kwargs):
            if kwargs.get("due_start") and kwargs.get("due_end"):
                return [
                    Todo(
                        id="today123",
                        content="Due today task",
                        raw_content="- [ ] Due today task",
                        status=TodoStatus.PENDING,
                        source=TodoSource(type="note", path=Path("test.md")),
                        line_number=1,
                        created_date=date.today(),
                    )
                ]
            return []

        import nb.index.todos_repo

        monkeypatch.setattr(nb.index.todos_repo, "query_todos", mock_query_todos)

        content = "## Today\n{{ todos_due_today }}"
        result = templates.render_template(content)

        assert "- Due today task [todo:today1]" in result

    def test_todos_high_priority_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """{{ todos_high_priority }} renders priority 1 todos."""
        from nb.core import templates

        def mock_query_todos(**kwargs):
            if kwargs.get("priority") == 1:
                return [
                    Todo(
                        id="high1234",
                        content="High priority task",
                        raw_content="- [ ] High priority task",
                        status=TodoStatus.PENDING,
                        source=TodoSource(type="note", path=Path("test.md")),
                        line_number=1,
                        created_date=date.today(),
                        priority=Priority.HIGH,
                    )
                ]
            return []

        import nb.index.todos_repo

        monkeypatch.setattr(nb.index.todos_repo, "query_todos", mock_query_todos)

        content = "## Priority\n{{ todos_high_priority }}"
        result = templates.render_template(content)

        assert "- High priority task [todo:high12]" in result

    def test_calendar_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """{{ calendar }} renders today's events."""
        from nb.core import templates

        mock_event = MagicMock()
        mock_event.subject = "Team Meeting"
        mock_event.start = datetime(2025, 12, 23, 10, 0)
        mock_event.end = datetime(2025, 12, 23, 11, 0)
        mock_event.is_all_day = False

        mock_client = MagicMock()
        mock_client.get_events.return_value = [mock_event]

        # Patch at the source module
        monkeypatch.setattr("nb.core.calendar.get_calendar_client", lambda: mock_client)

        content = "## Meetings\n{{ calendar }}"
        result = templates.render_template(content)

        assert "- 10:00 AM - 11:00 AM: Team Meeting" in result

    def test_dynamic_variable_lazy_evaluation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dynamic variables only query when present in template."""
        call_count = {"todos": 0, "calendar": 0}

        def mock_query_todos(**kwargs):
            call_count["todos"] += 1
            return []

        def mock_get_calendar_client():
            call_count["calendar"] += 1
            client = MagicMock()
            client.get_events.return_value = []
            return client

        # Patch at source modules
        monkeypatch.setattr("nb.index.todos_repo.query_todos", mock_query_todos)
        monkeypatch.setattr(
            "nb.core.calendar.get_calendar_client", mock_get_calendar_client
        )

        from nb.core import templates

        # Template without dynamic variables
        content = "# {{ title }}\nDate: {{ date }}"
        templates.render_template(content, title="Test")

        assert call_count["todos"] == 0
        assert call_count["calendar"] == 0

    def test_empty_todos_shows_placeholder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty todo results show placeholder text."""
        monkeypatch.setattr("nb.index.todos_repo.query_todos", lambda **kwargs: [])

        from nb.core import templates

        content = "{{ todos_overdue }}"
        result = templates.render_template(content)

        assert result == "_No todos_"

    def test_empty_calendar_shows_placeholder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty calendar results show placeholder text."""
        mock_client = MagicMock()
        mock_client.get_events.return_value = []

        # Patch at source module
        monkeypatch.setattr("nb.core.calendar.get_calendar_client", lambda: mock_client)

        from nb.core import templates

        content = "{{ calendar }}"
        result = templates.render_template(content)

        assert result == "_No meetings_"
