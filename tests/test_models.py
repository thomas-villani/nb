"""Tests for nb.models module."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from nb.models import Attachment, Note, Priority, Todo, TodoSource, TodoStatus


class TestPriority:
    """Tests for Priority enum."""

    def test_values(self):
        assert Priority.HIGH.value == 1
        assert Priority.MEDIUM.value == 2
        assert Priority.LOW.value == 3

    def test_from_int_valid(self):
        assert Priority.from_int(1) == Priority.HIGH
        assert Priority.from_int(2) == Priority.MEDIUM
        assert Priority.from_int(3) == Priority.LOW

    def test_from_int_invalid(self):
        assert Priority.from_int(0) is None
        assert Priority.from_int(4) is None
        assert Priority.from_int(-1) is None

    def test_ordering(self):
        # Lower value = higher priority
        assert Priority.HIGH.value < Priority.MEDIUM.value
        assert Priority.MEDIUM.value < Priority.LOW.value


class TestAttachment:
    """Tests for Attachment dataclass."""

    def test_file_attachment(self):
        attachment = Attachment(
            id="abc123",
            type="file",
            path="/path/to/file.pdf",
            title="Design Doc",
            added_date=date(2025, 11, 26),
            copied=True,
        )

        assert attachment.id == "abc123"
        assert attachment.type == "file"
        assert attachment.path == "/path/to/file.pdf"
        assert attachment.title == "Design Doc"
        assert attachment.added_date == date(2025, 11, 26)
        assert attachment.copied is True

    def test_url_attachment(self):
        attachment = Attachment(id="def456", type="url", path="https://example.com/doc")

        assert attachment.type == "url"
        assert attachment.title is None
        assert attachment.added_date is None
        assert attachment.copied is False

    def test_conversation_attachment(self):
        attachment = Attachment(
            id="ghi789", type="conversation", path="snippet content here"
        )

        assert attachment.type == "conversation"


class TestNote:
    """Tests for Note dataclass."""

    def test_basic_note(self):
        note = Note(
            id="abc12345",
            path=Path("daily/2025-11-26.md"),
            title="Daily Note",
            date=date(2025, 11, 26),
            tags=["meeting", "review"],
            links=["projects/roadmap"],
            notebook="daily",
            content_hash="abcd1234",
        )

        assert note.id == "abc12345"
        assert note.path == Path("daily/2025-11-26.md")
        assert note.title == "Daily Note"
        assert note.date == date(2025, 11, 26)
        assert note.tags == ["meeting", "review"]
        assert note.links == ["projects/roadmap"]
        assert note.notebook == "daily"
        assert note.content_hash == "abcd1234"

    def test_default_values(self):
        note = Note(id="def12345", path=Path("note.md"), title="Simple Note", date=None)

        assert note.id == "def12345"
        assert note.tags == []
        assert note.links == []
        assert note.attachments == []
        assert note.notebook == ""
        assert note.content_hash == ""

    def test_with_attachments(self):
        attachment = Attachment(id="a1", type="file", path="doc.pdf")
        note = Note(
            id="ghi12345",
            path=Path("note.md"),
            title="Note with Attachments",
            date=date(2025, 11, 26),
            attachments=[attachment],
        )

        assert len(note.attachments) == 1
        assert note.attachments[0].id == "a1"


class TestTodoSource:
    """Tests for TodoSource dataclass."""

    def test_note_source(self):
        source = TodoSource(type="note", path=Path("daily/2025-11-26.md"))

        assert source.type == "note"
        assert source.path == Path("daily/2025-11-26.md")
        assert source.external is False
        assert source.alias is None

    def test_inbox_source(self):
        source = TodoSource(type="inbox", path=Path("todo.md"))

        assert source.type == "inbox"

    def test_linked_external_source(self):
        source = TodoSource(
            type="linked",
            path=Path("/external/project/TODO.md"),
            external=True,
            alias="project",
        )

        assert source.type == "linked"
        assert source.external is True
        assert source.alias == "project"


class TestTodo:
    """Tests for Todo dataclass."""

    def test_basic_todo(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Review the PR",
            raw_content="- [ ] Review the PR @due(friday)",
            status=TodoStatus.PENDING,
            source=source,
            line_number=10,
            created_date=date(2025, 11, 26),
        )

        assert todo.id == "abc123"
        assert todo.content == "Review the PR"
        assert todo.raw_content == "- [ ] Review the PR @due(friday)"
        assert todo.completed is False
        assert todo.line_number == 10

    def test_completed_todo(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Done task",
            raw_content="- [x] Done task",
            status=TodoStatus.COMPLETED,
            source=source,
            line_number=5,
            created_date=date(2025, 11, 26),
        )

        assert todo.completed is True

    def test_is_overdue_past_date(self, fixed_today: date):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Overdue task",
            raw_content="- [ ] Overdue task",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            due_date=fixed_today - timedelta(days=1),  # Yesterday
        )

        assert todo.is_overdue is True

    def test_is_overdue_future_date(self, fixed_today: date):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Future task",
            raw_content="- [ ] Future task",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            due_date=fixed_today + timedelta(days=1),  # Tomorrow
        )

        assert todo.is_overdue is False

    def test_is_overdue_no_due_date(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="No due date",
            raw_content="- [ ] No due date",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            due_date=None,
        )

        assert todo.is_overdue is False

    def test_is_due_today(self, fixed_today: date):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Today's task",
            raw_content="- [ ] Today's task",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            due_date=fixed_today,
        )

        assert todo.is_due_today is True

    def test_is_due_today_no_due_date(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="No due date",
            raw_content="- [ ] No due date",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            due_date=None,
        )

        assert todo.is_due_today is False

    def test_priority_sort_key_high(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="High priority",
            raw_content="- [ ] High priority",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            priority=Priority.HIGH,
        )

        assert todo.priority_sort_key == 1

    def test_priority_sort_key_medium(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Medium priority",
            raw_content="- [ ] Medium priority",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            priority=Priority.MEDIUM,
        )

        assert todo.priority_sort_key == 2

    def test_priority_sort_key_none(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="No priority",
            raw_content="- [ ] No priority",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            priority=None,
        )

        assert todo.priority_sort_key == 999

    def test_todo_with_children(self):
        source = TodoSource(type="note", path=Path("note.md"))
        parent = Todo(
            id="parent",
            content="Parent task",
            raw_content="- [ ] Parent task",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
        )
        child1 = Todo(
            id="child1",
            content="Child 1",
            raw_content="  - [ ] Child 1",
            status=TodoStatus.PENDING,
            source=source,
            line_number=2,
            created_date=date(2025, 11, 20),
            parent_id="parent",
        )
        child2 = Todo(
            id="child2",
            content="Child 2",
            raw_content="  - [x] Child 2",
            status=TodoStatus.COMPLETED,
            source=source,
            line_number=3,
            created_date=date(2025, 11, 20),
            parent_id="parent",
        )

        parent.children = [child1, child2]

        assert len(parent.children) == 2
        assert parent.children[0].parent_id == "parent"
        assert parent.children[1].completed is True

    def test_todo_with_tags(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Tagged task",
            raw_content="- [ ] Tagged task #urgent #review",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            tags=["urgent", "review"],
        )

        assert "urgent" in todo.tags
        assert "review" in todo.tags

    def test_todo_with_project(self):
        source = TodoSource(type="note", path=Path("note.md"))
        todo = Todo(
            id="abc123",
            content="Project task",
            raw_content="- [ ] Project task",
            status=TodoStatus.PENDING,
            source=source,
            line_number=1,
            created_date=date(2025, 11, 20),
            notebook="nb-cli",
        )

        assert todo.notebook == "nb-cli"
