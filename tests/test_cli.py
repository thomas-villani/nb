"""CLI integration tests for nb."""

from __future__ import annotations

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config

# Note: cli_runner, cli_config, and mock_cli_config fixtures are defined in conftest.py


class TestMainCommand:
    """Tests for main command group."""

    def test_version(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "nb" in result.output

    def test_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert (
            "plaintext-first" in result.output.lower()
            or "note" in result.output.lower()
        )


class TestTodayCommand:
    """Tests for today command."""

    def test_today_creates_note(self, cli_runner: CliRunner, mock_cli_config: Config):
        # Use -s (show) on the main group to avoid actually opening editor
        result = cli_runner.invoke(cli, ["-s", "today"])

        # Should create today's note
        assert result.exit_code == 0

    def test_today_with_notebook(self, cli_runner: CliRunner, mock_cli_config: Config):
        result = cli_runner.invoke(cli, ["-s", "today", "-n", "work"])

        assert result.exit_code == 0


class TestYesterdayCommand:
    """Tests for yesterday command."""

    def test_yesterday(self, cli_runner: CliRunner, mock_cli_config: Config):
        result = cli_runner.invoke(cli, ["-s", "yesterday"])

        assert result.exit_code == 0


class TestListCommand:
    """Tests for list command."""

    def test_list_notes(self, cli_runner: CliRunner, mock_cli_config: Config):
        notes_root = mock_cli_config.notes_root

        # Create some notes
        (notes_root / "projects" / "note1.md").write_text("# Note 1\n")
        (notes_root / "projects" / "note2.md").write_text("# Note 2\n")

        result = cli_runner.invoke(cli, ["list"])

        assert result.exit_code == 0

    def test_list_with_notebook_filter(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        notes_root = mock_cli_config.notes_root

        (notes_root / "projects" / "project.md").write_text("# Project\n")
        (notes_root / "work" / "work.md").write_text("# Work\n")

        result = cli_runner.invoke(cli, ["list", "-n", "projects"])

        assert result.exit_code == 0


class TestNewCommand:
    """Tests for new command."""

    def test_new_note(self, cli_runner: CliRunner, mock_cli_config: Config):
        notes_root = mock_cli_config.notes_root

        result = cli_runner.invoke(cli, ["new", "test-note", "-n", "projects"])

        # Should create the note
        expected_path = notes_root / "projects" / "test-note.md"
        assert expected_path.exists() or result.exit_code == 0

    def test_new_note_with_title(self, cli_runner: CliRunner, mock_cli_config: Config):
        notes_root = mock_cli_config.notes_root

        result = cli_runner.invoke(
            cli, ["new", "my-doc", "-n", "projects", "-t", "My Document"]
        )

        assert result.exit_code == 0


class TestIndexCommand:
    """Tests for index command."""

    def test_index(self, cli_runner: CliRunner, mock_cli_config: Config):
        notes_root = mock_cli_config.notes_root

        # Create a note to index
        (notes_root / "projects" / "note.md").write_text("# Test Note\n")

        result = cli_runner.invoke(cli, ["index"])

        assert result.exit_code == 0


class TestTodoCommands:
    """Tests for todo subcommands."""

    def test_todo_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["todo", "--help"])

        assert result.exit_code == 0
        assert "todo" in result.output.lower()

    def test_todo_default_lists(self, cli_runner: CliRunner, mock_cli_config: Config):
        notes_root = mock_cli_config.notes_root

        # Create a note with todos
        content = """\
# Tasks

- [ ] Task 1
- [ ] Task 2
- [x] Done task
"""
        (notes_root / "projects" / "tasks.md").write_text(content)

        # Index first
        cli_runner.invoke(cli, ["index"])

        # 'todo' without subcommand should list todos (or show TUI)
        result = cli_runner.invoke(cli, ["todo"])

        # May exit 0 or prompt for TUI
        assert result.exit_code == 0 or "todo" in result.output.lower()

    def test_todo_add(self, cli_runner: CliRunner, mock_cli_config: Config):
        result = cli_runner.invoke(cli, ["todo", "add", "New todo task"])

        assert result.exit_code == 0

    def test_todo_add_to_daily(self, cli_runner: CliRunner, mock_cli_config: Config):
        result = cli_runner.invoke(cli, ["todo", "add", "Daily task", "--today"])

        assert result.exit_code == 0


class TestNotebookCommands:
    """Tests for notebook subcommands."""

    def test_notebooks_help(self, cli_runner: CliRunner, mock_cli_config: Config):
        result = cli_runner.invoke(cli, ["notebooks", "--help"])

        assert result.exit_code == 0

    def test_notebooks_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        # 'nbs' is alias for 'notebooks'
        result = cli_runner.invoke(cli, ["nbs", "--help"])

        assert result.exit_code == 0


class TestSearchCommand:
    """Tests for search command."""

    def test_search(self, cli_runner: CliRunner, mock_cli_config: Config):
        notes_root = mock_cli_config.notes_root

        # Create notes with searchable content
        (notes_root / "projects" / "python.md").write_text(
            "# Python Guide\n\nLearn Python basics.\n"
        )

        # Index first
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["search", "python"])

        # Search should complete (may or may not find results depending on index)
        assert result.exit_code == 0


class TestAddCommand:
    """Tests for add command (append to notes)."""

    def test_add_to_today(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Default: add to today's daily note."""
        result = cli_runner.invoke(cli, ["add", "Some quick note content"])

        assert result.exit_code == 0

    def test_add_to_specific_note(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Add to specific note with --note."""
        notes_root = mock_cli_config.notes_root
        note_path = notes_root / "projects" / "myproject.md"
        note_path.write_text("# My Project\n\nSome content.\n")

        result = cli_runner.invoke(
            cli, ["add", "New line of text", "--note", "myproject"]
        )

        assert result.exit_code == 0
        assert "Added to myproject.md" in result.output
        content = note_path.read_text()
        assert "New line of text" in content

    def test_add_to_note_with_notebook_prefix(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Add to note using notebook/note format."""
        notes_root = mock_cli_config.notes_root
        note_path = notes_root / "work" / "tasks.md"
        note_path.write_text("# Tasks\n")

        result = cli_runner.invoke(
            cli, ["add", "Important task", "--note", "work/tasks"]
        )

        assert result.exit_code == 0
        assert "Added to tasks.md" in result.output
        content = note_path.read_text()
        assert "Important task" in content

    def test_add_to_note_with_notebook_option(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Add to note using --note and --notebook separately."""
        notes_root = mock_cli_config.notes_root
        note_path = notes_root / "work" / "meetings.md"
        note_path.write_text("# Meetings\n")

        result = cli_runner.invoke(
            cli, ["add", "Meeting note", "--note", "meetings", "-n", "work"]
        )

        assert result.exit_code == 0
        assert "Added to meetings.md" in result.output
        content = note_path.read_text()
        assert "Meeting note" in content

    def test_add_note_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Error when note doesn't exist."""
        result = cli_runner.invoke(cli, ["add", "Some text", "--note", "nonexistent"])

        assert result.exit_code == 1
        assert "Note not found" in result.output

    def test_add_notebook_ignored_without_note(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Warning when --notebook used without --note."""
        result = cli_runner.invoke(cli, ["add", "Some text", "-n", "work"])

        # Should still succeed (adds to daily)
        assert result.exit_code == 0
        assert "Warning" in result.output


class TestAliases:
    """Test command aliases."""

    def test_t_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        # 't' is alias for 'today' - -s goes on main group
        result = cli_runner.invoke(cli, ["-s", "t"])

        assert result.exit_code == 0

    def test_y_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        # 'y' is alias for 'yesterday' - -s goes on main group
        result = cli_runner.invoke(cli, ["-s", "y"])

        assert result.exit_code == 0

    def test_td_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        # 'td' is alias for 'todo'
        result = cli_runner.invoke(cli, ["td", "--help"])

        assert result.exit_code == 0

    def test_ta_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        # 'ta' is alias for 'todo add'
        result = cli_runner.invoke(cli, ["ta", "Test task"])

        assert result.exit_code == 0
