"""CLI tests for link commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestLinkList:
    """Tests for 'nb link list' command."""

    def test_link_list_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing links when none exist."""
        result = cli_runner.invoke(cli, ["link", "list"])
        assert result.exit_code == 0
        assert "No linked" in result.output

    def test_link_list_shows_links(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test listing links shows added links."""
        # Create an external file
        ext_file = tmp_path / "external.md"
        ext_file.write_text("# External Note\n- [ ] External todo\n")

        cli_runner.invoke(cli, ["link", "add", str(ext_file), "-a", "ext"])

        result = cli_runner.invoke(cli, ["link", "list"])
        assert result.exit_code == 0
        assert "ext" in result.output


class TestLinkAdd:
    """Tests for 'nb link add' command."""

    def test_link_add_file(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test linking an external file."""
        ext_file = tmp_path / "todo.md"
        ext_file.write_text("# TODO\n- [ ] Important task\n")

        result = cli_runner.invoke(cli, ["link", "add", str(ext_file)])
        assert result.exit_code == 0
        assert "Linked" in result.output

    def test_link_add_with_alias(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test linking with custom alias."""
        ext_file = tmp_path / "notes.md"
        ext_file.write_text("# Notes\n")

        result = cli_runner.invoke(cli, ["link", "add", str(ext_file), "-a", "mynotes"])
        assert result.exit_code == 0
        assert "mynotes" in result.output

    def test_link_add_directory(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test linking a directory."""
        ext_dir = tmp_path / "docs"
        ext_dir.mkdir()
        (ext_dir / "readme.md").write_text("# Readme\n")
        (ext_dir / "guide.md").write_text("# Guide\n")

        result = cli_runner.invoke(cli, ["link", "add", str(ext_dir)])
        assert result.exit_code == 0
        assert "Indexed" in result.output

    def test_link_add_with_todo_exclude(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test linking with todo exclusion."""
        ext_file = tmp_path / "excluded.md"
        ext_file.write_text("# Excluded\n- [ ] Hidden todo\n")

        result = cli_runner.invoke(
            cli, ["link", "add", str(ext_file), "--todo-exclude"]
        )
        assert result.exit_code == 0
        assert "excluded" in result.output.lower() or "Linked" in result.output

    def test_link_add_file_not_exists(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test linking non-existent file."""
        result = cli_runner.invoke(cli, ["link", "add", "/nonexistent/file.md"])
        assert result.exit_code != 0


class TestLinkRemove:
    """Tests for 'nb link remove' command."""

    def test_link_remove(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test removing a link."""
        ext_file = tmp_path / "remove.md"
        ext_file.write_text("# Remove Me\n")
        cli_runner.invoke(cli, ["link", "add", str(ext_file), "-a", "toremove"])

        result = cli_runner.invoke(cli, ["link", "remove", "toremove"])
        assert result.exit_code == 0
        assert "Removed" in result.output

        # Verify it's gone
        result = cli_runner.invoke(cli, ["link", "list"])
        assert "toremove" not in result.output

    def test_link_remove_not_found(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing non-existent link."""
        result = cli_runner.invoke(cli, ["link", "remove", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestLinkSync:
    """Tests for 'nb link sync' command."""

    def test_link_sync_all(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test syncing all links."""
        ext_file = tmp_path / "sync.md"
        ext_file.write_text("# Sync\n- [ ] Task\n")
        cli_runner.invoke(cli, ["link", "add", str(ext_file), "-a", "sync"])

        result = cli_runner.invoke(cli, ["link", "sync"])
        assert result.exit_code == 0
        assert "Synced" in result.output

    def test_link_sync_specific(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test syncing a specific link."""
        ext_file = tmp_path / "specific.md"
        ext_file.write_text("# Specific\n- [ ] Task\n")
        cli_runner.invoke(cli, ["link", "add", str(ext_file), "-a", "spec"])

        result = cli_runner.invoke(cli, ["link", "sync", "spec"])
        assert result.exit_code == 0
        assert "Synced" in result.output

    def test_link_sync_not_found(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test syncing non-existent link."""
        result = cli_runner.invoke(cli, ["link", "sync", "nonexistent"])
        assert result.exit_code == 1


class TestLinkSyncToggle:
    """Tests for link sync enable/disable commands."""

    def test_enable_sync(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test enabling sync for a link."""
        ext_file = tmp_path / "toggle.md"
        ext_file.write_text("# Toggle\n")
        cli_runner.invoke(
            cli, ["link", "add", str(ext_file), "-a", "toggle", "--no-sync"]
        )

        result = cli_runner.invoke(cli, ["link", "enable-sync", "toggle"])
        assert result.exit_code == 0
        assert "Enabled" in result.output

    def test_disable_sync(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test disabling sync for a link."""
        ext_file = tmp_path / "disable.md"
        ext_file.write_text("# Disable\n")
        cli_runner.invoke(cli, ["link", "add", str(ext_file), "-a", "dis"])

        result = cli_runner.invoke(cli, ["link", "disable-sync", "dis"])
        assert result.exit_code == 0
        assert "Disabled" in result.output


class TestLinkTodoToggle:
    """Tests for link todo include/exclude commands."""

    def test_exclude_todos(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test excluding todos from a link."""
        ext_file = tmp_path / "exclude.md"
        ext_file.write_text("# Exclude\n- [ ] Task\n")
        cli_runner.invoke(cli, ["link", "add", str(ext_file), "-a", "excl"])

        result = cli_runner.invoke(cli, ["link", "exclude-todos", "excl"])
        assert result.exit_code == 0
        assert "Excluded" in result.output

    def test_include_todos(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test including todos from a link."""
        ext_file = tmp_path / "include.md"
        ext_file.write_text("# Include\n- [ ] Task\n")
        cli_runner.invoke(
            cli, ["link", "add", str(ext_file), "-a", "incl", "--todo-exclude"]
        )

        result = cli_runner.invoke(cli, ["link", "include-todos", "incl"])
        assert result.exit_code == 0
        assert "Included" in result.output
