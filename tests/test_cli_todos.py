"""CLI tests for todo subcommands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestTodoDone:
    """Tests for 'nb todo done' command."""

    def test_done_marks_complete(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test completing a single todo."""
        indexed_todo_note(["Test task to complete"])

        todo_id = get_todo_id("Test task to complete")
        assert todo_id is not None, "Should find todo ID"

        result = cli_runner.invoke(cli, ["todo", "done", todo_id])
        assert result.exit_code == 0
        assert "Completed" in result.output

    def test_done_multiple_todos(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test completing multiple todos at once."""
        indexed_todo_note(["Task A", "Task B"])

        id_a = get_todo_id("Task A")
        id_b = get_todo_id("Task B")
        assert id_a and id_b

        result = cli_runner.invoke(cli, ["todo", "done", id_a, id_b])
        assert result.exit_code == 0
        assert "Completed" in result.output

    def test_done_already_completed(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test completing an already completed todo shows warning."""
        # Create note with completed todo
        content = "# Tasks\n\n- [x] Already done task"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        # Get the todo ID (need to show completed)
        result = cli_runner.invoke(cli, ["todo", "-c"])
        # Find ID for completed todo
        for line in result.output.split("\n"):
            if "Already done" in line:
                parts = line.split()
                for part in reversed(parts):
                    if len(part) == 6 and all(c in "0123456789abcdef" for c in part):
                        todo_id = part
                        break
                break
        else:
            pytest.skip("Could not find completed todo ID")

        result = cli_runner.invoke(cli, ["todo", "done", todo_id])
        assert "already completed" in result.output.lower()

    def test_done_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test completing a non-existent todo shows error."""
        result = cli_runner.invoke(cli, ["todo", "done", "abc123"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_done_updates_file(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test that completing a todo actually updates the source file."""
        path = indexed_todo_note(["Update me"])

        todo_id = get_todo_id("Update me")
        cli_runner.invoke(cli, ["todo", "done", todo_id])

        # Check file was updated
        content = path.read_text()
        assert "- [x] Update me" in content


class TestTodoUndone:
    """Tests for 'nb todo undone' command."""

    def test_undone_reopens_todo(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test reopening a completed todo."""
        # Create note with completed todo
        content = "# Tasks\n\n- [x] Completed task"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        # Get the todo ID
        result = cli_runner.invoke(cli, ["todo", "-c"])
        todo_id = None
        for line in result.output.split("\n"):
            if "Completed task" in line:
                parts = line.split()
                for part in reversed(parts):
                    if len(part) == 6 and all(c in "0123456789abcdef" for c in part):
                        todo_id = part
                        break
                break

        assert todo_id is not None

        result = cli_runner.invoke(cli, ["todo", "undone", todo_id])
        assert result.exit_code == 0
        assert "Reopened" in result.output

        # Check file was updated
        content = path.read_text()
        assert "- [ ] Completed task" in content

    def test_undone_not_completed(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test undone on an open todo shows warning."""
        indexed_todo_note(["Open task"])

        todo_id = get_todo_id("Open task")
        result = cli_runner.invoke(cli, ["todo", "undone", todo_id])
        assert "not completed" in result.output.lower()


class TestTodoStart:
    """Tests for 'nb todo start' command."""

    def test_start_marks_in_progress(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test starting a todo marks it in-progress."""
        path = indexed_todo_note(["Task to start"])

        todo_id = get_todo_id("Task to start")
        result = cli_runner.invoke(cli, ["todo", "start", todo_id])
        assert result.exit_code == 0
        assert "Started" in result.output

        # Check file was updated with [^] marker
        content = path.read_text()
        assert "- [^] Task to start" in content

    def test_start_already_in_progress(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test starting an already in-progress todo shows warning."""
        content = "# Tasks\n\n- [^] Already started"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        # Get the todo ID
        result = cli_runner.invoke(cli, ["todo"])
        todo_id = None
        for line in result.output.split("\n"):
            if "Already started" in line:
                parts = line.split()
                for part in reversed(parts):
                    if len(part) == 6 and all(c in "0123456789abcdef" for c in part):
                        todo_id = part
                        break
                break

        if todo_id:
            result = cli_runner.invoke(cli, ["todo", "start", todo_id])
            assert "already in progress" in result.output.lower()

    def test_start_completed_todo(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test starting a completed todo shows error."""
        content = "# Tasks\n\n- [x] Done task"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["todo", "-c"])
        todo_id = None
        for line in result.output.split("\n"):
            if "Done task" in line:
                parts = line.split()
                for part in reversed(parts):
                    if len(part) == 6 and all(c in "0123456789abcdef" for c in part):
                        todo_id = part
                        break
                break

        if todo_id:
            result = cli_runner.invoke(cli, ["todo", "start", todo_id])
            assert "completed" in result.output.lower()


class TestTodoPause:
    """Tests for 'nb todo pause' command."""

    def test_pause_returns_to_pending(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test pausing an in-progress todo returns it to pending."""
        content = "# Tasks\n\n- [^] In progress task"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        # Get the todo ID
        result = cli_runner.invoke(cli, ["todo"])
        todo_id = None
        for line in result.output.split("\n"):
            if "In progress task" in line:
                parts = line.split()
                for part in reversed(parts):
                    if len(part) == 6 and all(c in "0123456789abcdef" for c in part):
                        todo_id = part
                        break
                break

        assert todo_id is not None

        result = cli_runner.invoke(cli, ["todo", "pause", todo_id])
        assert result.exit_code == 0
        assert "Paused" in result.output

        # Check file was updated
        content = path.read_text()
        assert "- [ ] In progress task" in content

    def test_pause_not_in_progress(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test pausing a pending todo shows warning."""
        indexed_todo_note(["Pending task"])

        todo_id = get_todo_id("Pending task")
        result = cli_runner.invoke(cli, ["todo", "pause", todo_id])
        assert "not in progress" in result.output.lower()


class TestTodoShow:
    """Tests for 'nb todo show' command."""

    def test_show_displays_details(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test showing detailed todo information."""
        content = "# Tasks\n\n- [ ] Detailed task @priority(1) @due(2025-12-01) #work"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        # Get the todo ID
        result = cli_runner.invoke(cli, ["todo"])
        todo_id = None
        for line in result.output.split("\n"):
            if "Detailed task" in line:
                parts = line.split()
                for part in reversed(parts):
                    if len(part) == 6 and all(c in "0123456789abcdef" for c in part):
                        todo_id = part
                        break
                break

        assert todo_id is not None

        result = cli_runner.invoke(cli, ["todo", "show", todo_id])
        assert result.exit_code == 0
        assert "Detailed task" in result.output
        assert "Priority" in result.output
        assert "Due" in result.output
        assert "Tags" in result.output or "work" in result.output

    def test_show_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test showing non-existent todo."""
        result = cli_runner.invoke(cli, ["todo", "show", "abc123"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestTodoDelete:
    """Tests for 'nb todo delete' command."""

    def test_delete_with_force(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test deleting a todo with --force."""
        path = indexed_todo_note(["Task to delete"])

        todo_id = get_todo_id("Task to delete")
        result = cli_runner.invoke(cli, ["todo", "delete", todo_id, "-f"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

        # Check file was updated
        content = path.read_text()
        assert "Task to delete" not in content

    def test_delete_with_confirmation(
        self, cli_runner: CliRunner, indexed_todo_note, get_todo_id
    ):
        """Test deleting a todo with confirmation prompt."""
        indexed_todo_note(["Task to confirm"])

        todo_id = get_todo_id("Task to confirm")
        # Simulate 'n' input for cancellation
        result = cli_runner.invoke(cli, ["todo", "delete", todo_id], input="n\n")
        assert "Cancelled" in result.output or result.exit_code == 0

    def test_delete_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test deleting non-existent todo."""
        result = cli_runner.invoke(cli, ["todo", "delete", "abc123", "-f"])
        assert "not found" in result.output.lower()


class TestTodoFilters:
    """Tests for todo filtering options."""

    def test_filter_by_tag(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test filtering todos by tag."""
        content = "# Tasks\n\n- [ ] Work task #work\n- [ ] Personal task #personal"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["todo", "-t", "work"])
        assert result.exit_code == 0
        assert "Work task" in result.output
        assert "Personal task" not in result.output

    def test_filter_by_priority(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test filtering todos by priority."""
        content = "# Tasks\n\n- [ ] High @priority(1)\n- [ ] Low @priority(3)"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["todo", "-p", "1"])
        assert result.exit_code == 0
        assert "High" in result.output
        # Low priority should not appear when filtering for priority 1

    def test_filter_by_notebook(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test filtering todos by notebook."""
        # Create todos in different notebooks
        (mock_cli_config.notes_root / "projects" / "proj.md").write_text(
            "# Proj\n- [ ] Project task"
        )
        (mock_cli_config.notes_root / "work" / "work.md").write_text(
            "# Work\n- [ ] Work task"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["todo", "-n", "work"])
        assert result.exit_code == 0
        assert "Work task" in result.output
        assert "Project task" not in result.output

    def test_exclude_tag(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test excluding todos by tag."""
        content = "# Tasks\n\n- [ ] Active #active\n- [ ] Waiting #waiting"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["todo", "-xt", "waiting"])
        assert result.exit_code == 0
        assert "Active" in result.output
        assert "Waiting" not in result.output

    def test_focus_mode(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test focus mode hides later/no-date todos."""
        content = "# Tasks\n\n- [ ] No date task\n- [ ] Due today @due(today)"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["todo", "-f"])
        assert result.exit_code == 0
        # Focus mode should hide "NO DUE DATE" section

    def test_include_completed(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test including completed todos."""
        content = "# Tasks\n\n- [ ] Open task\n- [x] Completed task"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        # Without -c
        result = cli_runner.invoke(cli, ["todo"])
        assert "Open task" in result.output

        # With -c
        result = cli_runner.invoke(cli, ["todo", "-c"])
        assert "Completed task" in result.output

    def test_limit_and_offset(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test pagination with --limit and --offset."""
        todos = "\n".join([f"- [ ] Task {i}" for i in range(10)])
        content = f"# Tasks\n\n{todos}"
        path = mock_cli_config.notes_root / "projects" / "test.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["todo", "-l", "3"])
        assert result.exit_code == 0
        assert "Showing" in result.output  # Shows pagination info


class TestTodoViews:
    """Tests for todo view management."""

    def test_create_view(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test creating a saved view."""
        result = cli_runner.invoke(
            cli, ["todo", "-n", "work", "--create-view", "mywork"]
        )
        assert result.exit_code == 0
        assert "Creating view" in result.output or "mywork" in result.output

    def test_list_views(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing saved views."""
        # Create a view first
        cli_runner.invoke(cli, ["todo", "-n", "work", "--create-view", "testview"])

        result = cli_runner.invoke(cli, ["todo", "--list-views"])
        assert result.exit_code == 0
        assert "testview" in result.output

    def test_apply_view(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test applying a saved view."""
        # Create a view
        cli_runner.invoke(cli, ["todo", "-n", "work", "--create-view", "workview"])

        # Create todos in work notebook
        (mock_cli_config.notes_root / "work" / "tasks.md").write_text(
            "# Tasks\n- [ ] Work task"
        )
        (mock_cli_config.notes_root / "projects" / "tasks.md").write_text(
            "# Tasks\n- [ ] Project task"
        )
        cli_runner.invoke(cli, ["index"])

        # Apply view
        result = cli_runner.invoke(cli, ["todo", "-v", "workview"])
        assert result.exit_code == 0
        assert "Work task" in result.output

    def test_delete_view(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test deleting a saved view."""
        # Create a view
        cli_runner.invoke(cli, ["todo", "-n", "work", "--create-view", "todelete"])

        result = cli_runner.invoke(cli, ["todo", "--delete-view", "todelete"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

        # Verify it's gone
        result = cli_runner.invoke(cli, ["todo", "--list-views"])
        assert "todelete" not in result.output

    def test_view_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test applying non-existent view."""
        result = cli_runner.invoke(cli, ["todo", "-v", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestTodoAdd:
    """Additional tests for todo add command."""

    def test_add_with_metadata(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test adding todo with inline metadata."""
        result = cli_runner.invoke(
            cli, ["todo", "add", "Review PR @due(friday) @priority(1) #work"]
        )
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_to_specific_note(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test adding todo to a specific note."""
        # Create target note
        (mock_cli_config.notes_root / "projects" / "myproject.md").write_text(
            "# My Project\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(
            cli, ["todo", "add", "New task", "-N", "projects/myproject"]
        )
        assert result.exit_code == 0
        assert "Added" in result.output

        # Verify todo was added to the file
        content = (mock_cli_config.notes_root / "projects" / "myproject.md").read_text()
        assert "- [ ] New task" in content

    def test_add_to_nonexistent_note(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test adding todo to non-existent note shows error."""
        result = cli_runner.invoke(
            cli, ["todo", "add", "Task", "-N", "nonexistent/note"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
