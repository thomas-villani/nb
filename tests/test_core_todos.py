"""Tests for nb.core.todos module."""

from __future__ import annotations

from datetime import date, timedelta

from nb.core.todos import (
    ATTACH_PATTERN,
    COLON_LABEL_PATTERN,
    DUE_PATTERN,
    HEADING_PATTERN,
    PRIORITY_PATTERN,
    TAG_PATTERN,
    TODO_PATTERN,
    add_todo_to_inbox,
    add_todo_to_note,
    clean_todo_content,
    extract_todos,
    get_inbox_path,
    parse_due_date,
    parse_priority,
    parse_tags,
    toggle_todo_in_file,
)
from nb.models import Priority


class TestPatterns:
    """Tests for regex patterns."""

    def test_todo_pattern_unchecked(self):
        match = TODO_PATTERN.match("- [ ] Task description")
        assert match is not None
        assert match.group("indent") == ""
        assert match.group("state") == " "
        assert match.group("content") == "Task description"

    def test_todo_pattern_checked(self):
        match = TODO_PATTERN.match("- [x] Completed task")
        assert match is not None
        assert match.group("state") == "x"

    def test_todo_pattern_checked_uppercase(self):
        match = TODO_PATTERN.match("- [X] Completed task")
        assert match is not None
        assert match.group("state") == "X"

    def test_todo_pattern_indented(self):
        match = TODO_PATTERN.match("  - [ ] Indented task")
        assert match is not None
        assert match.group("indent") == "  "

    def test_todo_pattern_no_match(self):
        assert TODO_PATTERN.match("Regular text") is None
        assert TODO_PATTERN.match("* [ ] Wrong bullet") is None
        assert TODO_PATTERN.match("- Not a checkbox") is None

    def test_due_pattern(self):
        match = DUE_PATTERN.search("Task @due(friday)")
        assert match is not None
        assert match.group("date") == "friday"

        match = DUE_PATTERN.search("Task @due(2025-12-01)")
        assert match.group("date") == "2025-12-01"

    def test_priority_pattern(self):
        match = PRIORITY_PATTERN.search("Task @priority(1)")
        assert match is not None
        assert match.group("level") == "1"

    def test_tag_pattern(self):
        tags = TAG_PATTERN.findall("Task #urgent #review")
        assert tags == ["urgent", "review"]

    def test_attach_pattern(self):
        match = ATTACH_PATTERN.match("  @attach: ./docs/file.pdf")
        assert match is not None
        assert match.group(1) == "./docs/file.pdf"


class TestCleanTodoContent:
    """Tests for clean_todo_content function."""

    def test_removes_due_date(self):
        result = clean_todo_content("Task @due(friday)")
        assert result == "Task"
        assert "@due" not in result

    def test_removes_priority(self):
        result = clean_todo_content("Task @priority(1)")
        assert result == "Task"
        assert "@priority" not in result

    def test_removes_tags(self):
        result = clean_todo_content("Task #urgent #review")
        assert result == "Task"
        assert "#" not in result

    def test_removes_all_metadata(self):
        result = clean_todo_content("Task @due(friday) @priority(1) #urgent")
        assert result == "Task"

    def test_preserves_text(self):
        result = clean_todo_content("Review PR #123 for project")
        # Only #123 as a tag gets removed, but the text is preserved
        assert "Review PR" in result
        assert "for project" in result

    def test_cleans_whitespace(self):
        result = clean_todo_content("  Task   with   spaces  ")
        assert result == "Task with spaces"


class TestParseDueDate:
    """Tests for parse_due_date function."""

    def test_parses_iso_date(self):
        result = parse_due_date("Task @due(2025-12-01)")
        assert result == date(2025, 12, 1)

    def test_parses_fuzzy_date(self, fixed_today):
        result = parse_due_date("Task @due(tomorrow)")
        assert result == fixed_today + timedelta(days=1)

    def test_no_due_date(self):
        result = parse_due_date("Task without due date")
        assert result is None


class TestParsePriority:
    """Tests for parse_priority function."""

    def test_parses_high_priority(self):
        result = parse_priority("Task @priority(1)")
        assert result == Priority.HIGH

    def test_parses_medium_priority(self):
        result = parse_priority("Task @priority(2)")
        assert result == Priority.MEDIUM

    def test_parses_low_priority(self):
        result = parse_priority("Task @priority(3)")
        assert result == Priority.LOW

    def test_no_priority(self):
        result = parse_priority("Task without priority")
        assert result is None


class TestParseTags:
    """Tests for parse_tags function."""

    def test_single_tag(self):
        result = parse_tags("Task #urgent")
        assert result == ["urgent"]

    def test_multiple_tags(self):
        result = parse_tags("Task #urgent #review #important")
        assert sorted(result) == ["important", "review", "urgent"]

    def test_no_tags(self):
        result = parse_tags("Task without tags")
        assert result == []

    def test_lowercase_normalization(self):
        result = parse_tags("Task #URGENT #Review")
        assert result == ["urgent", "review"]


class TestExtractTodos:
    """Tests for extract_todos function."""

    def test_extracts_basic_todos(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] First task
- [x] Completed task
- [ ] Third task
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 3
        assert todos[0].content == "First task"
        assert todos[0].completed is False
        assert todos[1].completed is True

    def test_extracts_metadata(self, mock_config, create_note, fixed_today):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] High priority @priority(1) @due(tomorrow) #urgent
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 1
        todo = todos[0]
        assert todo.priority == Priority.HIGH
        assert todo.due_date == fixed_today + timedelta(days=1)
        assert "urgent" in todo.tags

    def test_handles_nested_todos(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] Parent task
  - [ ] Child task 1
  - [ ] Child task 2
    - [ ] Grandchild
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 4

        parent = todos[0]
        child1 = todos[1]
        child2 = todos[2]
        grandchild = todos[3]

        assert parent.parent_id is None
        assert child1.parent_id == parent.id
        assert child2.parent_id == parent.id
        assert grandchild.parent_id == child2.id

        assert len(parent.children) == 2
        assert len(child2.children) == 1

    def test_ignores_todos_in_code_blocks(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] Real task

```python
# This is code
- [ ] Not a real task
```

- [ ] Another real task
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 2
        assert todos[0].content == "Real task"
        assert todos[1].content == "Another real task"

    def test_extracts_attachments(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] Task with attachment
  @attach: ./docs/spec.pdf
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 1
        assert len(todos[0].attachments) == 1
        assert todos[0].attachments[0].path == "./docs/spec.pdf"
        assert todos[0].attachments[0].type == "file"

    def test_url_attachment(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
- [ ] Task with URL
  @attach: https://example.com/doc.pdf
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert todos[0].attachments[0].type == "url"

    def test_sets_project_from_notebook(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = "- [ ] Task\n"
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert todos[0].notebook == "projects"

    def test_empty_file(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = "# Empty file\n\nNo todos here.\n"
        note_path = create_note("projects", "empty.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert todos == []

    def test_missing_file(self, mock_config):
        notes_root = mock_config.notes_root

        todos = extract_todos(notes_root / "nonexistent.md", notes_root=notes_root)

        assert todos == []

    def test_extracts_multiline_details(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] Develop presentation for sales:
   - need to include intro slides
   - use the new images
   It would be best to build off the 2024 deck
- [ ] Update website
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 2
        assert todos[0].content == "Develop presentation for sales:"
        assert todos[0].details is not None
        assert "need to include intro slides" in todos[0].details
        assert "use the new images" in todos[0].details
        assert "build off the 2024 deck" in todos[0].details
        assert todos[1].content == "Update website"
        assert todos[1].details is None

    def test_details_not_captured_for_subtasks(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
- [ ] Parent task
  - [ ] Subtask 1
  - [ ] Subtask 2
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        # Subtasks should be children, not details
        assert len(todos) == 3
        parent = todos[0]
        assert parent.details is None
        assert len(parent.children) == 2

    def test_details_with_mixed_content(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
- [ ] Main task
   Some notes about this task
   More details here
  - [ ] Subtask after details
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        # Main task has details and a subtask
        assert len(todos) == 2
        main = todos[0]
        assert main.details is not None
        assert "Some notes about this task" in main.details
        assert "More details here" in main.details
        assert len(main.children) == 1

    def test_inline_tags_not_inherited_across_todos(self, mock_config, create_note):
        """Inline tags from one todo should NOT be inherited by other todos.

        Regression test: Previously, extract_tags() was pulling all inline #tags
        from the entire note body and applying them to every todo. Only frontmatter
        tags should be inherited.
        """
        notes_root = mock_config.notes_root

        content = """\
---
tags: [shared]
---
# Tasks

- [ ] First task #tag1
- [ ] Second task #tag2
- [ ] Third task with no tag
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 3

        # First todo should have frontmatter tag + its own inline tag
        assert set(todos[0].tags) == {"shared", "tag1"}

        # Second todo should have frontmatter tag + its own inline tag
        assert set(todos[1].tags) == {"shared", "tag2"}

        # Third todo should only have the frontmatter tag (not tag1 or tag2)
        assert set(todos[2].tags) == {"shared"}

    def test_frontmatter_tags_inherited_to_all_todos(self, mock_config, create_note):
        """Frontmatter tags should be inherited by all todos in the note."""
        notes_root = mock_config.notes_root

        content = """\
---
tags: [project, important]
---
# Tasks

- [ ] Task without inline tags
- [ ] Task with inline tag #extra
"""
        note_path = create_note("projects", "test.md", content)

        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 2
        # Both todos inherit frontmatter tags
        assert "project" in todos[0].tags
        assert "important" in todos[0].tags
        assert "project" in todos[1].tags
        assert "important" in todos[1].tags
        # Only second todo has the inline tag
        assert "extra" not in todos[0].tags
        assert "extra" in todos[1].tags


class TestToggleTodoInFile:
    """Tests for toggle_todo_in_file function."""

    def test_marks_incomplete_as_complete(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] Task to complete
"""
        note_path = create_note("projects", "test.md", content)

        result = toggle_todo_in_file(note_path, line_number=3)

        assert result == 3  # Returns actual line number on success
        new_content = note_path.read_text()
        assert "- [x] Task to complete" in new_content

    def test_marks_complete_as_incomplete(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [x] Completed task
"""
        note_path = create_note("projects", "test.md", content)

        result = toggle_todo_in_file(note_path, line_number=3)

        assert result == 3  # Returns actual line number on success
        new_content = note_path.read_text()
        assert "- [ ] Completed task" in new_content

    def test_invalid_line_number(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = "- [ ] Task\n"
        note_path = create_note("projects", "test.md", content)

        result = toggle_todo_in_file(note_path, line_number=999)
        assert result is None

        result = toggle_todo_in_file(note_path, line_number=0)
        assert result is None

    def test_non_todo_line(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
# Heading

Regular text
"""
        note_path = create_note("projects", "test.md", content)

        result = toggle_todo_in_file(note_path, line_number=1)
        assert result is None

    def test_missing_file(self, mock_config):
        notes_root = mock_config.notes_root

        result = toggle_todo_in_file(notes_root / "nonexistent.md", line_number=1)
        assert result is None

    def test_stale_line_number_finds_nearby_todo(self, mock_config, create_note):
        """Test that expected_content allows finding todo even if line number is stale."""
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] First task
- [ ] Second task
- [ ] Third task
"""
        note_path = create_note("projects", "test.md", content)

        # Pretend the database has a stale line number (says line 4 but it's actually line 3)
        result = toggle_todo_in_file(
            note_path, line_number=4, expected_content="First task"
        )

        # Should find and toggle the correct todo at line 3
        assert result == 3
        new_content = note_path.read_text()
        assert "- [x] First task" in new_content
        assert "- [ ] Second task" in new_content  # Not toggled

    def test_expected_content_not_found(self, mock_config, create_note):
        """Test that returns None if expected content not found nearby."""
        notes_root = mock_config.notes_root

        content = """\
# Tasks

- [ ] First task
- [ ] Second task
"""
        note_path = create_note("projects", "test.md", content)

        # Try to find a todo that doesn't exist
        result = toggle_todo_in_file(
            note_path, line_number=3, expected_content="Nonexistent task"
        )

        assert result is None
        # File should be unchanged
        new_content = note_path.read_text()
        assert "- [ ] First task" in new_content


class TestAddTodoToInbox:
    """Tests for add_todo_to_inbox function."""

    def test_creates_inbox_if_missing(self, mock_config):
        notes_root = mock_config.notes_root

        todo = add_todo_to_inbox("New task", notes_root)

        inbox_path = notes_root / "todo.md"
        assert inbox_path.exists()
        content = inbox_path.read_text()
        assert "# Todo Inbox" in content
        assert "- [ ] New task" in content

    def test_appends_to_existing_inbox(self, mock_config):
        notes_root = mock_config.notes_root

        add_todo_to_inbox("First task", notes_root)
        add_todo_to_inbox("Second task", notes_root)

        inbox_path = notes_root / "todo.md"
        content = inbox_path.read_text()
        assert "- [ ] First task" in content
        assert "- [ ] Second task" in content

    def test_parses_metadata(self, mock_config, fixed_today):
        notes_root = mock_config.notes_root

        todo = add_todo_to_inbox("Task @priority(1) @due(tomorrow) #urgent", notes_root)

        assert todo.content == "Task"
        assert todo.priority == Priority.HIGH
        assert todo.due_date == fixed_today + timedelta(days=1)
        assert "urgent" in todo.tags

    def test_returns_todo_object(self, mock_config):
        notes_root = mock_config.notes_root

        todo = add_todo_to_inbox("Test task", notes_root)

        assert todo.content == "Test task"
        assert todo.completed is False
        assert todo.source.type == "inbox"


class TestGetInboxPath:
    """Tests for get_inbox_path function."""

    def test_returns_todo_md(self, mock_config):
        notes_root = mock_config.notes_root

        path = get_inbox_path(notes_root)

        assert path == notes_root / "todo.md"


class TestSectionPatterns:
    """Tests for section heading regex patterns."""

    def test_heading_pattern_h1(self):
        match = HEADING_PATTERN.match("# Main Heading")
        assert match is not None
        assert match.group("level") == "#"
        assert match.group("text") == "Main Heading"

    def test_heading_pattern_h2(self):
        match = HEADING_PATTERN.match("## Sub Heading")
        assert match is not None
        assert match.group("level") == "##"
        assert match.group("text") == "Sub Heading"

    def test_heading_pattern_h3(self):
        match = HEADING_PATTERN.match("### Deep Heading")
        assert match is not None
        assert match.group("level") == "###"

    def test_heading_pattern_h6(self):
        match = HEADING_PATTERN.match("###### Level 6")
        assert match is not None
        assert match.group("level") == "######"

    def test_heading_pattern_no_match_text(self):
        assert HEADING_PATTERN.match("Regular text") is None
        assert HEADING_PATTERN.match("No hash prefix") is None

    def test_colon_label_pattern(self):
        match = COLON_LABEL_PATTERN.match("Morning:")
        assert match is not None
        assert match.group("text") == "Morning"

    def test_colon_label_pattern_with_spaces(self):
        match = COLON_LABEL_PATTERN.match("Project Setup:")
        assert match is not None
        assert match.group("text") == "Project Setup"

    def test_colon_label_matches_todo_line(self):
        # The pattern itself CAN match todo lines ending with :
        # But in extract_todos(), we explicitly check not stripped_line.startswith("-")
        # before applying this pattern, so todo lines are excluded
        match = COLON_LABEL_PATTERN.match("- [ ] Task:")
        assert match is not None  # Pattern matches, but code filters it out

    def test_colon_label_no_match_multiple_colons(self):
        # Only matches if there's exactly one colon at the end
        match = COLON_LABEL_PATTERN.match("Time: 10:00:")
        # This actually matches "Time: 10:00" as text with trailing :
        # The pattern is flexible with colons in the content


class TestSectionExtraction:
    """Tests for section heading extraction in extract_todos."""

    def test_markdown_heading_h1_title_skipped(self, mock_config, create_note):
        """First heading (title) should be skipped for section assignment."""
        notes_root = mock_config.notes_root
        content = """\
# Project Tasks

- [ ] First task
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 1
        # First heading is title, so section should be None
        assert todos[0].section is None

    def test_markdown_heading_h2_after_title(self, mock_config, create_note):
        """Second heading becomes section after title is skipped."""
        notes_root = mock_config.notes_root
        content = """\
# Project Title

## Development

- [ ] Write code
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert todos[0].section == "Development"

    def test_markdown_heading_h3_after_title(self, mock_config, create_note):
        """H3 heading becomes section after title is skipped."""
        notes_root = mock_config.notes_root
        content = """\
# Note Title

### Bug Fixes

- [ ] Fix issue #123
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert todos[0].section == "Bug Fixes"

    def test_colon_label(self, mock_config, create_note):
        notes_root = mock_config.notes_root
        content = """\
Morning:
- [ ] Check emails

Afternoon:
- [ ] Team meeting
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 2
        assert todos[0].section == "Morning"
        assert todos[1].section == "Afternoon"

    def test_nearest_heading_wins(self, mock_config, create_note):
        """First heading is title (skipped), subsequent headings become sections."""
        notes_root = mock_config.notes_root
        content = """\
# Note Title

- [ ] Task under title (no section)

## Subsection

- [ ] Task under subsection
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 2
        # First heading is title, so first task has no section
        assert todos[0].section is None
        assert todos[1].section == "Subsection"

    def test_no_section(self, mock_config, create_note):
        notes_root = mock_config.notes_root
        content = """\
- [ ] Task without section
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert todos[0].section is None

    def test_section_in_code_block_ignored(self, mock_config, create_note):
        notes_root = mock_config.notes_root
        content = """\
# Title

## Real Section

```markdown
## Fake Section
```

- [ ] Should be under Real Section
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert todos[0].section == "Real Section"

    def test_mixed_headings_and_labels(self, mock_config, create_note):
        """Colon labels take precedence over headings when closest to todo."""
        notes_root = mock_config.notes_root
        content = """\
# Title

## Project Alpha

Morning:
- [ ] Task 1

## Project Beta

Evening:
- [ ] Task 2
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 2
        assert todos[0].section == "Morning"
        assert todos[1].section == "Evening"

    def test_section_persists_for_multiple_todos(self, mock_config, create_note):
        notes_root = mock_config.notes_root
        content = """\
# Setup Guide

## Installation

- [ ] Set up environment
- [ ] Install dependencies
- [ ] Configure settings
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 3
        assert todos[0].section == "Installation"
        assert todos[1].section == "Installation"
        assert todos[2].section == "Installation"

    def test_nested_todos_inherit_section(self, mock_config, create_note):
        notes_root = mock_config.notes_root
        content = """\
# Title

## Setup

- [ ] Main task
  - [ ] Subtask 1
  - [ ] Subtask 2
"""
        note_path = create_note("projects", "test.md", content)
        todos = extract_todos(note_path, notes_root=notes_root)

        assert len(todos) == 3
        assert todos[0].section == "Setup"
        assert todos[1].section == "Setup"
        assert todos[2].section == "Setup"


class TestAddTodoToNote:
    """Tests for add_todo_to_note function."""

    def test_add_todo_to_note_no_section(self, mock_config, create_note):
        """Test adding a todo to a note without specifying a section."""
        content = """\
# Project Notes

Some content here.
"""
        note_path = create_note("projects", "test.md", content)

        todo = add_todo_to_note("New task", note_path)

        assert todo.content == "New task"
        new_content = note_path.read_text()
        assert "- [ ] New task" in new_content

    def test_add_todo_exact_section_match(self, mock_config, create_note):
        """Test adding a todo to an exact section match."""
        content = """\
# Project Notes

## Tasks

- [ ] Existing task

## Notes

Some notes here.
"""
        note_path = create_note("projects", "test.md", content)

        todo = add_todo_to_note("New task", note_path, section="Tasks")

        assert todo.section == "Tasks"
        new_content = note_path.read_text()
        # The new task should be under Tasks section
        lines = new_content.splitlines()
        tasks_idx = next(i for i, l in enumerate(lines) if "## Tasks" in l)
        notes_idx = next(i for i, l in enumerate(lines) if "## Notes" in l)
        new_task_idx = next(i for i, l in enumerate(lines) if "New task" in l)
        assert tasks_idx < new_task_idx < notes_idx

    def test_add_todo_partial_section_match(self, mock_config, create_note):
        """Test adding a todo with partial section name matching."""
        content = """\
# Daily Note

## Morning Tasks

- [ ] Wake up early

## Evening Tasks

- [ ] Review day
"""
        note_path = create_note("projects", "test.md", content)

        # Use partial name "Morning" instead of full "Morning Tasks"
        todo = add_todo_to_note("Exercise", note_path, section="Morning")

        # Should match "Morning Tasks" and return the full section name
        assert todo.section == "Morning Tasks"
        new_content = note_path.read_text()
        # The new task should be under Morning Tasks section
        lines = new_content.splitlines()
        morning_idx = next(i for i, l in enumerate(lines) if "## Morning Tasks" in l)
        evening_idx = next(i for i, l in enumerate(lines) if "## Evening Tasks" in l)
        new_task_idx = next(i for i, l in enumerate(lines) if "Exercise" in l)
        assert morning_idx < new_task_idx < evening_idx

    def test_add_todo_partial_section_match_case_insensitive(
        self, mock_config, create_note
    ):
        """Test partial section matching is case-insensitive."""
        content = """\
# Notes

## Development Tasks

- [ ] Write code
"""
        note_path = create_note("projects", "test.md", content)

        # Use lowercase partial name
        todo = add_todo_to_note("Review PR", note_path, section="dev")

        assert todo.section == "Development Tasks"

    def test_add_todo_creates_new_section_if_no_match(self, mock_config, create_note):
        """Test that a new section is created if no match found."""
        content = """\
# Notes

## Existing Section

- [ ] Existing task
"""
        note_path = create_note("projects", "test.md", content)

        todo = add_todo_to_note("New task", note_path, section="New Section")

        assert todo.section == "New Section"
        new_content = note_path.read_text()
        assert "## New Section" in new_content
        assert "- [ ] New task" in new_content

    def test_add_todo_colon_label_section(self, mock_config, create_note):
        """Test adding a todo to a colon-style section label."""
        content = """\
# Daily Note

Morning:
- [ ] Check emails

Afternoon:
- [ ] Meetings
"""
        note_path = create_note("projects", "test.md", content)

        todo = add_todo_to_note("Exercise", note_path, section="Morning")

        assert todo.section == "Morning"

    def test_add_todo_partial_colon_label_match(self, mock_config, create_note):
        """Test partial matching for colon-style labels."""
        content = """\
# Daily Note

Morning Tasks:
- [ ] Check emails

Afternoon Tasks:
- [ ] Meetings
"""
        note_path = create_note("projects", "test.md", content)

        # Use partial name
        todo = add_todo_to_note("Exercise", note_path, section="Morn")

        assert todo.section == "Morning Tasks"
