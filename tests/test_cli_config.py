"""CLI tests for config commands."""

from __future__ import annotations

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestConfigGet:
    """Tests for 'nb config get' command."""

    def test_config_get_editor(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test getting editor setting."""
        result = cli_runner.invoke(cli, ["config", "get", "editor"])
        assert result.exit_code == 0
        assert "echo" in result.output  # Test config uses echo

    def test_config_get_date_format(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test getting date format setting."""
        result = cli_runner.invoke(cli, ["config", "get", "date_format"])
        assert result.exit_code == 0
        assert "%Y-%m-%d" in result.output

    def test_config_get_unknown(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test getting unknown setting."""
        result = cli_runner.invoke(cli, ["config", "get", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown" in result.output


class TestConfigSet:
    """Tests for 'nb config set' command."""

    def test_config_set_editor(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test setting editor."""
        result = cli_runner.invoke(cli, ["config", "set", "editor", "vim"])
        assert result.exit_code == 0
        assert "Set" in result.output

    def test_config_set_date_format(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test setting date format."""
        result = cli_runner.invoke(cli, ["config", "set", "date_format", "%d/%m/%Y"])
        assert result.exit_code == 0
        assert "Set" in result.output

    def test_config_set_unknown(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test setting unknown key."""
        result = cli_runner.invoke(cli, ["config", "set", "nonexistent", "value"])
        assert result.exit_code == 1
        assert "Unknown" in result.output


class TestConfigList:
    """Tests for 'nb config list' command."""

    def test_config_list(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing all config settings."""
        result = cli_runner.invoke(cli, ["config", "list"])
        assert result.exit_code == 0
        assert "editor" in result.output
        assert "date_format" in result.output


class TestConfigExcludeInclude:
    """Tests for 'nb config exclude/include' commands."""

    def test_config_exclude_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test excluding a notebook from todos."""
        result = cli_runner.invoke(cli, ["config", "exclude", "projects"])
        assert result.exit_code == 0
        assert "Excluded" in result.output

    def test_config_include_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test including a notebook in todos."""
        # First exclude
        cli_runner.invoke(cli, ["config", "exclude", "work"])

        result = cli_runner.invoke(cli, ["config", "include", "work"])
        assert result.exit_code == 0
        assert "Included" in result.output

    def test_config_exclude_note(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test excluding a specific note from todos."""
        # Create note
        note_path = mock_cli_config.notes_root / "projects" / "exclude.md"
        note_path.write_text("# Exclude\n- [ ] Task\n")

        result = cli_runner.invoke(cli, ["config", "exclude", "projects/exclude"])
        assert result.exit_code == 0
        assert "Excluded" in result.output

        # Check frontmatter was updated
        content = note_path.read_text()
        assert "todo_exclude" in content

    def test_config_exclude_not_found(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test excluding non-existent target."""
        result = cli_runner.invoke(cli, ["config", "exclude", "nonexistent"])
        assert result.exit_code == 1
        assert "Not found" in result.output
