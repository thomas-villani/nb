"""CLI tests for misc commands (tags, stats, attachments)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestTagsCommand:
    """Tests for 'nb tags' command."""

    def test_tags_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test tags when no tags exist."""
        result = cli_runner.invoke(cli, ["tags"])
        assert result.exit_code == 0
        assert "No tags" in result.output

    def test_tags_shows_tags(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test tags command shows existing tags."""
        (mock_cli_config.notes_root / "projects" / "tagged.md").write_text(
            "# Tagged\n- [ ] Task 1 #work\n- [ ] Task 2 #work #urgent\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["tags"])
        assert result.exit_code == 0
        assert "work" in result.output

    def test_tags_sort_alpha(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test tags sorted alphabetically."""
        (mock_cli_config.notes_root / "projects" / "multi.md").write_text(
            "# Multi\n- [ ] A #zebra\n- [ ] B #alpha\n- [ ] C #middle\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["tags", "--sort", "alpha"])
        assert result.exit_code == 0

    def test_tags_with_sources(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test tags with --sources shows note info."""
        (mock_cli_config.notes_root / "projects" / "src.md").write_text(
            "# Source\n- [ ] Task #tracked\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["tags", "-s"])
        assert result.exit_code == 0
        assert "tracked" in result.output

    def test_tags_with_limit(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test tags with --limit."""
        (mock_cli_config.notes_root / "projects" / "many.md").write_text(
            "# Many\n" + "\n".join([f"- [ ] Task {i} #tag{i}" for i in range(10)])
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["tags", "-l", "3"])
        assert result.exit_code == 0

    def test_tags_filter_by_notebook(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test tags filtered by notebook."""
        (mock_cli_config.notes_root / "projects" / "p.md").write_text(
            "# P\n- [ ] Task #project\n"
        )
        (mock_cli_config.notes_root / "work" / "w.md").write_text(
            "# W\n- [ ] Task #worktag\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["tags", "-n", "projects"])
        assert result.exit_code == 0


class TestStatsCommand:
    """Tests for 'nb stats' command."""

    def test_stats_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test stats with no todos."""
        result = cli_runner.invoke(cli, ["stats"])
        assert result.exit_code == 0

    def test_stats_basic(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test basic stats output."""
        (mock_cli_config.notes_root / "projects" / "tasks.md").write_text(
            "# Tasks\n- [ ] Open 1\n- [ ] Open 2\n- [x] Done 1\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "Todos" in result.output or "total" in result.output.lower()

    def test_stats_compact(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test compact stats view."""
        (mock_cli_config.notes_root / "projects" / "tasks.md").write_text(
            "# Tasks\n- [ ] Task\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["stats", "-c"])
        assert result.exit_code == 0

    def test_stats_by_notebook(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test stats broken down by notebook."""
        (mock_cli_config.notes_root / "projects" / "tasks.md").write_text(
            "# Tasks\n- [ ] Project task\n"
        )
        (mock_cli_config.notes_root / "work" / "tasks.md").write_text(
            "# Tasks\n- [ ] Work task\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["stats", "--by-notebook"])
        assert result.exit_code == 0

    def test_stats_by_priority(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test stats broken down by priority."""
        (mock_cli_config.notes_root / "projects" / "pri.md").write_text(
            "# Priority\n- [ ] High @priority(1)\n- [ ] Low @priority(3)\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["stats", "--by-priority"])
        assert result.exit_code == 0

    def test_stats_by_tag(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test stats with tag breakdown."""
        (mock_cli_config.notes_root / "projects" / "tagged.md").write_text(
            "# Tagged\n- [ ] Task 1 #work\n- [ ] Task 2 #personal\n"
        )
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["stats", "--by-tag"])
        assert result.exit_code == 0


class TestAttachCommand:
    """Tests for 'nb attach' commands."""

    def test_attach_list_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test listing attachments when none exist."""
        # Create today's note
        cli_runner.invoke(cli, ["-s", "today"])

        result = cli_runner.invoke(cli, ["attach", "list"])
        assert result.exit_code == 0
        assert "No attachments" in result.output

    def test_attach_file(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test attaching a file."""
        # Create today's note first
        cli_runner.invoke(cli, ["-s", "today"])

        # Create a file to attach
        attach_file = tmp_path / "document.pdf"
        attach_file.write_bytes(b"PDF content")

        result = cli_runner.invoke(cli, ["attach", "file", str(attach_file)])
        assert result.exit_code == 0
        assert "Attached" in result.output

    def test_attach_url(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test attaching a URL."""
        # Create today's note first
        cli_runner.invoke(cli, ["-s", "today"])

        result = cli_runner.invoke(cli, ["attach", "url", "https://example.com/doc"])
        assert result.exit_code == 0
        assert "Attached" in result.output

    def test_attach_to_specific_note(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test attaching to a specific note."""
        # Create target note
        note_path = mock_cli_config.notes_root / "projects" / "target.md"
        note_path.write_text("# Target\n")

        # Create a file to attach
        attach_file = tmp_path / "file.txt"
        attach_file.write_text("content")

        result = cli_runner.invoke(
            cli, ["attach", "file", str(attach_file), "--to", "projects/target"]
        )
        assert result.exit_code == 0
        assert "Attached" in result.output

    def test_attach_with_copy(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test attaching with --copy to copy file."""
        cli_runner.invoke(cli, ["-s", "today"])

        attach_file = tmp_path / "tocopy.txt"
        attach_file.write_text("copy me")

        result = cli_runner.invoke(cli, ["attach", "file", str(attach_file), "-c"])
        assert result.exit_code == 0
        assert "Attached" in result.output

    def test_attach_with_title(
        self, cli_runner: CliRunner, mock_cli_config: Config, tmp_path: Path
    ):
        """Test attaching with custom title."""
        cli_runner.invoke(cli, ["-s", "today"])

        attach_file = tmp_path / "untitled.txt"
        attach_file.write_text("content")

        result = cli_runner.invoke(
            cli, ["attach", "file", str(attach_file), "-t", "My Document"]
        )
        assert result.exit_code == 0
        assert "Attached" in result.output

    def test_attach_file_not_exists(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test attaching non-existent file."""
        result = cli_runner.invoke(cli, ["attach", "file", "/nonexistent/file.pdf"])
        assert result.exit_code != 0
