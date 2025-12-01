"""CLI tests for notebook commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestNotebooksList:
    """Tests for 'nb notebooks' list command."""

    def test_notebooks_list(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing all notebooks."""
        result = cli_runner.invoke(cli, ["notebooks"])
        assert result.exit_code == 0
        assert "daily" in result.output
        assert "projects" in result.output
        assert "work" in result.output

    def test_notebooks_list_verbose(
        self, cli_runner: CliRunner, mock_cli_config: Config, indexed_note
    ):
        """Test verbose notebook listing with counts."""
        indexed_note("projects", "note1.md", "# Note 1\n")
        indexed_note("projects", "note2.md", "# Note 2\n")

        result = cli_runner.invoke(cli, ["notebooks", "-v"])
        assert result.exit_code == 0
        assert "Notebook" in result.output

    def test_notebooks_alias(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test 'nbs' alias."""
        result = cli_runner.invoke(cli, ["nbs"])
        assert result.exit_code == 0
        assert "daily" in result.output


class TestNotebooksCreate:
    """Tests for 'nb notebooks create' command."""

    def test_create_notebook(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test creating a new notebook."""
        result = cli_runner.invoke(cli, ["notebooks", "create", "ideas"])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "ideas" in result.output

        # Verify directory was created
        assert (mock_cli_config.notes_root / "ideas").exists()

    def test_create_date_based_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating a date-based notebook."""
        result = cli_runner.invoke(
            cli, ["notebooks", "create", "journal", "--date-based"]
        )
        assert result.exit_code == 0
        assert "date-based" in result.output.lower()

    def test_create_todo_exclude_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating a notebook excluded from todos."""
        result = cli_runner.invoke(
            cli, ["notebooks", "create", "archive", "--todo-exclude"]
        )
        assert result.exit_code == 0
        assert "Excluded" in result.output or "archive" in result.output

    def test_create_external_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test creating a notebook from external path."""
        external_path = tmp_path / "external_notes"
        external_path.mkdir()
        (external_path / "readme.md").write_text("# External\n")

        result = cli_runner.invoke(
            cli, ["notebooks", "create", "external", "--from", str(external_path)]
        )
        assert result.exit_code == 0
        assert "external" in result.output.lower()

    def test_create_external_path_not_exists(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating notebook from non-existent path."""
        result = cli_runner.invoke(
            cli, ["notebooks", "create", "bad", "--from", "/nonexistent/path"]
        )
        assert result.exit_code == 1
        assert "not exist" in result.output.lower()

    def test_create_duplicate_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating a notebook that already exists."""
        result = cli_runner.invoke(cli, ["notebooks", "create", "projects"])
        assert result.exit_code == 1
        assert "already exists" in result.output.lower()


class TestNotebooksRemove:
    """Tests for 'nb notebooks remove' command."""

    def test_remove_notebook_with_yes(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a notebook with -y flag."""
        # Create a notebook first
        cli_runner.invoke(cli, ["notebooks", "create", "removeme"])

        result = cli_runner.invoke(cli, ["notebooks", "remove", "removeme", "-y"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_notebook_with_confirmation(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a notebook with confirmation."""
        cli_runner.invoke(cli, ["notebooks", "create", "confirm"])

        # Cancel removal
        result = cli_runner.invoke(cli, ["notebooks", "remove", "confirm"], input="n\n")
        assert "Cancelled" in result.output

    def test_remove_nonexistent_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a notebook that doesn't exist."""
        result = cli_runner.invoke(cli, ["notebooks", "remove", "nonexistent", "-y"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_remove_preserves_files(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test that removing a notebook preserves the files."""
        cli_runner.invoke(cli, ["notebooks", "create", "preserve"])
        note_path = mock_cli_config.notes_root / "preserve" / "note.md"
        note_path.write_text("# Preserved Note\n")

        cli_runner.invoke(cli, ["notebooks", "remove", "preserve", "-y"])

        # Files should still exist
        assert note_path.exists()
