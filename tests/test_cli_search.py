"""CLI tests for search-related commands."""

from __future__ import annotations

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config


class TestSearchCommand:
    """Tests for 'nb search' command."""

    def test_search_keyword_mode(self, cli_runner: CliRunner, indexed_note):
        """Test keyword-only search."""
        indexed_note(
            "projects", "search-test.md", "# Search Test\n\nKeyword match here."
        )

        result = cli_runner.invoke(cli, ["search", "--keyword", "Keyword"])
        assert result.exit_code == 0
        # Should find the match

    def test_search_with_tag_filter(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test search filtered by tag."""
        content = """---
tags:
  - python
---
# Python Tutorial

Python programming guide.
"""
        path = mock_cli_config.notes_root / "projects" / "python.md"
        path.write_text(content)
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(
            cli, ["search", "--keyword", "programming", "-t", "python"]
        )
        assert result.exit_code == 0

    def test_search_with_notebook_filter(self, cli_runner: CliRunner, indexed_note):
        """Test search filtered by notebook."""
        indexed_note("projects", "proj.md", "# Project Notes\n\nImportant content.")
        indexed_note("work", "work.md", "# Work Notes\n\nDifferent important content.")

        result = cli_runner.invoke(
            cli, ["search", "--keyword", "Important", "-n", "projects"]
        )
        assert result.exit_code == 0

    def test_search_no_results(self, cli_runner: CliRunner, indexed_note):
        """Test search with no matches."""
        indexed_note("projects", "test.md", "# Test\n\nSome content.")

        result = cli_runner.invoke(cli, ["search", "--keyword", "xyznonexistent123"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_with_limit(self, cli_runner: CliRunner, indexed_note):
        """Test search with result limit."""
        for i in range(5):
            indexed_note(
                "projects", f"note{i}.md", f"# Note {i}\n\nSearchable content."
            )

        result = cli_runner.invoke(
            cli, ["search", "--keyword", "Searchable", "--limit", "2"]
        )
        assert result.exit_code == 0

    def test_search_mutually_exclusive_modes(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test that --semantic and --keyword are mutually exclusive."""
        result = cli_runner.invoke(cli, ["search", "--semantic", "--keyword", "test"])
        assert result.exit_code == 1
        assert "Cannot use both" in result.output


class TestGrepCommand:
    """Tests for 'nb grep' command."""

    def test_grep_pattern(self, cli_runner: CliRunner, indexed_note):
        """Test basic grep with pattern."""
        indexed_note("projects", "code.md", "# Code\n\ndef hello_world():\n    pass")

        result = cli_runner.invoke(cli, ["grep", "hello_world"])
        assert result.exit_code == 0
        assert "hello_world" in result.output

    def test_grep_regex_pattern(self, cli_runner: CliRunner, indexed_note):
        """Test grep with regex pattern."""
        indexed_note(
            "projects",
            "funcs.md",
            "# Functions\n\ndef foo():\n    pass\ndef bar():\n    pass",
        )

        result = cli_runner.invoke(cli, ["grep", "def \\w+\\(\\):"])
        assert result.exit_code == 0

    def test_grep_case_sensitive(self, cli_runner: CliRunner, indexed_note):
        """Test grep with case sensitivity."""
        indexed_note(
            "projects", "case.md", "# Case Test\n\nTODO: Fix this\ntodo: also this"
        )

        # Case insensitive (default)
        result = cli_runner.invoke(cli, ["grep", "todo"])
        assert result.exit_code == 0
        assert "TODO" in result.output

        # Case sensitive
        result = cli_runner.invoke(cli, ["grep", "TODO", "--case-sensitive"])
        assert result.exit_code == 0

    def test_grep_with_context(self, cli_runner: CliRunner, indexed_note):
        """Test grep with context lines."""
        indexed_note(
            "projects",
            "context.md",
            "# Context\n\nLine 1\nLine 2\nMATCH HERE\nLine 4\nLine 5",
        )

        result = cli_runner.invoke(cli, ["grep", "MATCH", "-C", "2"])
        assert result.exit_code == 0
        # Should include surrounding lines

    def test_grep_with_notebook_filter(self, cli_runner: CliRunner, indexed_note):
        """Test grep filtered by notebook."""
        indexed_note("projects", "a.md", "# A\n\nFindme here")
        indexed_note("work", "b.md", "# B\n\nFindme also here")

        result = cli_runner.invoke(cli, ["grep", "Findme", "-n", "projects"])
        assert result.exit_code == 0
        # Should only show projects match

    def test_grep_no_matches(self, cli_runner: CliRunner, indexed_note):
        """Test grep with no matches."""
        indexed_note("projects", "empty.md", "# Empty\n\nNo matches here")

        result = cli_runner.invoke(cli, ["grep", "xyznonexistent"])
        assert result.exit_code == 0
        assert "No matches" in result.output

    def test_grep_invalid_regex(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test grep with invalid regex pattern."""
        result = cli_runner.invoke(cli, ["grep", "[invalid(regex"])
        assert result.exit_code == 1


class TestIndexCommand:
    """Tests for 'nb index' command."""

    def test_index_basic(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test basic indexing."""
        # Create a note
        (mock_cli_config.notes_root / "projects" / "test.md").write_text("# Test\n")

        result = cli_runner.invoke(cli, ["index"])
        assert result.exit_code == 0
        assert "Indexed" in result.output or "No files" in result.output

    def test_index_force(self, cli_runner: CliRunner, indexed_note):
        """Test force reindexing."""
        indexed_note("projects", "force.md", "# Force\n")

        result = cli_runner.invoke(cli, ["index", "--force"])
        assert result.exit_code == 0
        assert "Indexed" in result.output

    def test_index_notebook_specific(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test indexing specific notebook."""
        (mock_cli_config.notes_root / "projects" / "p.md").write_text("# P\n")
        (mock_cli_config.notes_root / "work" / "w.md").write_text("# W\n")

        result = cli_runner.invoke(cli, ["index", "-n", "projects"])
        assert result.exit_code == 0

    def test_index_rebuild(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test database rebuild."""
        (mock_cli_config.notes_root / "projects" / "rebuild.md").write_text(
            "# Rebuild\n"
        )
        cli_runner.invoke(cli, ["index"])  # Initial index

        result = cli_runner.invoke(cli, ["index", "--rebuild"])
        assert result.exit_code == 0
        assert "rebuilt" in result.output.lower()

    def test_index_rebuild_with_notebook_error(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test that --rebuild and --notebook are incompatible."""
        result = cli_runner.invoke(cli, ["index", "--rebuild", "-n", "projects"])
        assert result.exit_code == 1
        assert "Cannot use" in result.output

    def test_index_shows_stats(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test that index shows todo stats."""
        (mock_cli_config.notes_root / "projects" / "todos.md").write_text(
            "# Todos\n- [ ] Open task\n- [x] Done task"
        )

        result = cli_runner.invoke(cli, ["index", "--force"])
        assert result.exit_code == 0
        assert "Todos:" in result.output or "todo" in result.output.lower()
