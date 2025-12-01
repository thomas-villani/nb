"""CLI tests for template commands."""

from __future__ import annotations

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestTemplateList:
    """Tests for 'nb template list' command."""

    def test_template_list_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing templates when none exist."""
        result = cli_runner.invoke(cli, ["template", "list"])
        assert result.exit_code == 0
        assert "No templates" in result.output

    def test_template_list_shows_templates(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test listing templates shows existing templates."""
        # Create a template
        template_dir = mock_cli_config.notes_root / ".nb" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "meeting.md").write_text("# Meeting\n\n## Attendees\n")

        result = cli_runner.invoke(cli, ["template", "list"])
        assert result.exit_code == 0
        assert "meeting" in result.output

    def test_template_default_lists(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test that 'nb template' without subcommand lists templates."""
        result = cli_runner.invoke(cli, ["template"])
        assert result.exit_code == 0


class TestTemplateShow:
    """Tests for 'nb template show' command."""

    def test_template_show(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test showing template contents."""
        template_dir = mock_cli_config.notes_root / ".nb" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "standup.md").write_text(
            "# Standup\n\n## Yesterday\n\n## Today\n\n## Blockers\n"
        )

        result = cli_runner.invoke(cli, ["template", "show", "standup"])
        assert result.exit_code == 0
        assert "Standup" in result.output

    def test_template_show_not_found(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test showing non-existent template."""
        result = cli_runner.invoke(cli, ["template", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestTemplateNew:
    """Tests for 'nb template new' command."""

    def test_template_new(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test creating a new template."""
        result = cli_runner.invoke(cli, ["template", "new", "weekly"])
        assert result.exit_code == 0
        assert "Created" in result.output

        # Verify template exists
        template_path = mock_cli_config.notes_root / ".nb" / "templates" / "weekly.md"
        assert template_path.exists()

    def test_template_new_already_exists(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test creating a template that already exists."""
        template_dir = mock_cli_config.notes_root / ".nb" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "existing.md").write_text("# Existing\n")

        result = cli_runner.invoke(cli, ["template", "new", "existing"])
        assert result.exit_code == 1
        assert "already exists" in result.output.lower()


class TestTemplateRemove:
    """Tests for 'nb template remove' command."""

    def test_template_remove_with_yes(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a template with -y flag."""
        template_dir = mock_cli_config.notes_root / ".nb" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        template_path = template_dir / "toremove.md"
        template_path.write_text("# To Remove\n")

        result = cli_runner.invoke(cli, ["template", "remove", "toremove", "-y"])
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert not template_path.exists()

    def test_template_remove_with_confirmation_cancel(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing a template cancelled by user."""
        template_dir = mock_cli_config.notes_root / ".nb" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        template_path = template_dir / "keep.md"
        template_path.write_text("# Keep Me\n")

        result = cli_runner.invoke(cli, ["template", "remove", "keep"], input="n\n")
        assert "Cancelled" in result.output
        assert template_path.exists()

    def test_template_remove_not_found(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test removing non-existent template."""
        result = cli_runner.invoke(cli, ["template", "remove", "nonexistent", "-y"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
