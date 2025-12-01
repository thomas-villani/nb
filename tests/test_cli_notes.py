"""CLI tests for note commands."""

from __future__ import annotations


from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestOpenCommand:
    """Tests for 'nb open' command."""

    def test_open_by_date(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test opening a note by date reference."""
        # Create a note for "today"
        result = cli_runner.invoke(cli, ["-s", "open", "today"])
        assert result.exit_code == 0

    def test_open_by_name(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test opening a note by name in a notebook."""
        # Create a note
        note_path = mock_cli_config.notes_root / "projects" / "myproject.md"
        note_path.write_text("# My Project\n")

        result = cli_runner.invoke(cli, ["-s", "open", "myproject", "-n", "projects"])
        assert result.exit_code == 0

    def test_open_with_notebook_prefix(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test opening a note using notebook/note format."""
        # Create a note
        note_path = mock_cli_config.notes_root / "work" / "tasks.md"
        note_path.write_text("# Tasks\n")

        result = cli_runner.invoke(cli, ["-s", "open", "work/tasks"])
        assert result.exit_code == 0

    def test_open_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test opening non-existent note shows error."""
        result = cli_runner.invoke(cli, ["open", "nonexistent", "-n", "projects"])
        assert result.exit_code == 1
        assert "not" in result.output.lower() or "Could not" in result.output


class TestShowCommand:
    """Tests for 'nb show' command."""

    def test_show_today(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test showing today's note (default)."""
        # Create today's note first
        cli_runner.invoke(cli, ["-s", "today"])

        result = cli_runner.invoke(cli, ["show"])
        assert result.exit_code == 0

    def test_show_specific_note(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test showing a specific note."""
        note_path = mock_cli_config.notes_root / "projects" / "readme.md"
        note_path.write_text("# README\n\nThis is the readme content.\n")

        result = cli_runner.invoke(cli, ["show", "readme", "-n", "projects"])
        assert result.exit_code == 0
        assert "README" in result.output or "readme" in result.output

    def test_show_by_date(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test showing a note by date reference."""
        result = cli_runner.invoke(cli, ["show", "today"])
        assert result.exit_code == 0

    def test_show_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test showing non-existent note shows error."""
        result = cli_runner.invoke(cli, ["show", "nonexistent", "-n", "projects"])
        assert result.exit_code == 1


class TestEditCommand:
    """Tests for 'nb edit' command."""

    def test_edit_existing_note(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test editing an existing note."""
        note_path = mock_cli_config.notes_root / "projects" / "edit-me.md"
        note_path.write_text("# Edit Me\n")

        result = cli_runner.invoke(cli, ["edit", "projects/edit-me.md"])
        # Uses echo as editor, so should succeed
        assert result.exit_code == 0

    def test_edit_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test editing non-existent note shows error."""
        result = cli_runner.invoke(cli, ["edit", "projects/nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestLastCommand:
    """Tests for 'nb last' command."""

    def test_last_modified(self, cli_runner: CliRunner, indexed_note):
        """Test opening last modified note."""
        # Create and index a note
        indexed_note("projects", "recent.md", "# Recent Note\n")

        result = cli_runner.invoke(cli, ["last", "-s"])
        assert result.exit_code == 0

    def test_last_with_notebook_filter(self, cli_runner: CliRunner, indexed_note):
        """Test last modified note filtered by notebook."""
        indexed_note("projects", "proj.md", "# Project\n")
        indexed_note("work", "work.md", "# Work\n")

        result = cli_runner.invoke(cli, ["last", "-s", "-n", "work"])
        assert result.exit_code == 0

    def test_last_no_notes(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test last when no notes exist."""
        result = cli_runner.invoke(cli, ["last"])
        assert result.exit_code == 1
        assert "No" in result.output


class TestHistoryCommand:
    """Tests for 'nb history' command."""

    def test_history_basic(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test basic history output."""
        # Open some notes to create history
        cli_runner.invoke(cli, ["-s", "today"])

        result = cli_runner.invoke(cli, ["history"])
        # May have no history if views aren't tracked, but should not error
        assert result.exit_code == 0

    def test_history_with_limit(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test history with --limit."""
        result = cli_runner.invoke(cli, ["history", "-l", "5"])
        assert result.exit_code == 0

    def test_history_with_group(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test history with --group."""
        result = cli_runner.invoke(cli, ["history", "-g"])
        assert result.exit_code == 0


class TestAliasCommands:
    """Tests for alias-related commands."""

    def test_alias_create(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test creating a note alias."""
        # Create a note to alias
        note_path = mock_cli_config.notes_root / "projects" / "important.md"
        note_path.write_text("# Important\n")

        result = cli_runner.invoke(cli, ["alias", "imp", "projects/important"])
        assert result.exit_code == 0
        assert "Alias created" in result.output

    def test_alias_list(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing aliases."""
        # Create a note and alias
        note_path = mock_cli_config.notes_root / "projects" / "readme.md"
        note_path.write_text("# Readme\n")
        cli_runner.invoke(cli, ["alias", "rdme", "projects/readme"])

        result = cli_runner.invoke(cli, ["aliases"])
        assert result.exit_code == 0
        assert "rdme" in result.output

    def test_aliases_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing aliases when none exist."""
        result = cli_runner.invoke(cli, ["aliases"])
        assert result.exit_code == 0
        assert "No aliases" in result.output

    def test_unalias(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test removing an alias."""
        # Create a note and alias
        note_path = mock_cli_config.notes_root / "projects" / "temp.md"
        note_path.write_text("# Temp\n")
        cli_runner.invoke(cli, ["alias", "tmp", "projects/temp"])

        result = cli_runner.invoke(cli, ["unalias", "tmp"])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    def test_unalias_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test removing non-existent alias."""
        result = cli_runner.invoke(cli, ["unalias", "nonexistent"])
        assert "not found" in result.output.lower()

    def test_open_by_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test opening a note by its alias."""
        # Create and alias a note
        note_path = mock_cli_config.notes_root / "projects" / "aliased.md"
        note_path.write_text("# Aliased Note\n")
        cli_runner.invoke(cli, ["alias", "ali", "projects/aliased"])

        result = cli_runner.invoke(cli, ["-s", "open", "ali"])
        assert result.exit_code == 0


class TestDeleteCommand:
    """Tests for 'nb delete' command."""

    def test_delete_with_force(self, cli_runner: CliRunner, indexed_note):
        """Test deleting a note with --force."""
        path = indexed_note("projects", "to-delete.md", "# Delete Me\n")
        assert path.exists()

        result = cli_runner.invoke(cli, ["delete", "projects/to-delete", "-f"])
        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert not path.exists()

    def test_delete_with_confirmation_cancel(self, cli_runner: CliRunner, indexed_note):
        """Test deleting a note cancelled by user."""
        path = indexed_note("projects", "keep-me.md", "# Keep Me\n")

        result = cli_runner.invoke(cli, ["delete", "projects/keep-me"], input="n\n")
        assert "Cancelled" in result.output
        assert path.exists()

    def test_delete_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test deleting non-existent note."""
        result = cli_runner.invoke(cli, ["delete", "nonexistent", "-n", "projects"])
        assert result.exit_code == 1

    def test_delete_removes_from_index(self, cli_runner: CliRunner, indexed_note):
        """Test that deleting a note removes it from the index."""
        path = indexed_note("projects", "indexed.md", "# Indexed\n- [ ] Todo")

        # Verify todo exists
        result = cli_runner.invoke(cli, ["todo"])
        assert "Todo" in result.output

        # Delete the note
        cli_runner.invoke(cli, ["delete", "projects/indexed", "-f"])

        # Re-index and verify todo is gone
        cli_runner.invoke(cli, ["index"])
        result = cli_runner.invoke(cli, ["todo"])
        assert "Todo" not in result.output or "No todos" in result.output


class TestListCommand:
    """Additional tests for 'nb list' command."""

    def test_list_all(self, cli_runner: CliRunner, indexed_note):
        """Test listing all notes."""
        indexed_note("projects", "proj1.md", "# Project 1\n")
        indexed_note("work", "work1.md", "# Work 1\n")

        result = cli_runner.invoke(cli, ["list", "-a"])
        assert result.exit_code == 0

    def test_list_week(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing this week's notes."""
        result = cli_runner.invoke(cli, ["list", "--week"])
        assert result.exit_code == 0

    def test_list_month(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing this month's notes."""
        result = cli_runner.invoke(cli, ["list", "--month"])
        assert result.exit_code == 0

    def test_list_full_path(self, cli_runner: CliRunner, indexed_note):
        """Test listing with full paths."""
        indexed_note("projects", "fullpath.md", "# Full Path\n")

        result = cli_runner.invoke(cli, ["list", "-n", "projects", "-f"])
        assert result.exit_code == 0


class TestNewCommand:
    """Additional tests for 'nb new' command."""

    def test_new_with_template(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test creating note with template."""
        # Create a template
        template_dir = mock_cli_config.notes_root / ".nb" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "meeting.md").write_text(
            "# Meeting Notes\n\n## Attendees\n\n## Topics\n"
        )

        result = cli_runner.invoke(
            cli, ["new", "standup", "-n", "projects", "-T", "meeting"]
        )
        assert result.exit_code == 0

        # Verify template was applied
        note_path = mock_cli_config.notes_root / "projects" / "standup.md"
        content = note_path.read_text()
        assert "Attendees" in content

    def test_new_template_not_found(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating note with non-existent template."""
        result = cli_runner.invoke(
            cli, ["new", "test", "-n", "projects", "-T", "nonexistent"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_new_already_exists(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test creating note that already exists."""
        note_path = mock_cli_config.notes_root / "projects" / "exists.md"
        note_path.write_text("# Exists\n")

        result = cli_runner.invoke(cli, ["new", "exists", "-n", "projects"])
        assert result.exit_code == 1
        assert "already exists" in result.output.lower()
