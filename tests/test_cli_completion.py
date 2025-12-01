"""Tests for shell completion functionality."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from nb import config as config_module
from nb.cli import cli
from nb.cli.completion import (
    _get_powershell_source,
    complete_notebook,
    complete_tag,
    complete_view,
)
from nb.config import Config, EmbeddingsConfig, NotebookConfig, TodoViewConfig
from nb.index import scanner as scanner_module
from nb.index.db import reset_db


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def completion_config(tmp_path: Path):
    """Set up config with notebooks, tags, and views for completion tests."""
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()

    cfg = Config(
        notes_root=notes_root,
        editor="echo",
        notebooks=[
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
            NotebookConfig(name="work", date_based=False),
            NotebookConfig(name="personal", date_based=False),
        ],
        todo_views=[
            TodoViewConfig(name="work-focus", filters={"notebooks": ["work"]}),
            TodoViewConfig(name="high-priority", filters={"priority": 1}),
        ],
        embeddings=EmbeddingsConfig(),
        date_format="%Y-%m-%d",
        time_format="%H:%M",
    )

    # Create notebook directories
    for nb in cfg.notebooks:
        if not nb.is_external:
            (notes_root / nb.name).mkdir(exist_ok=True)

    # Disable vector indexing for tests
    scanner_module.ENABLE_VECTOR_INDEXING = False

    yield cfg

    # Cleanup
    config_module.reset_config()
    reset_db()


@pytest.fixture
def mock_completion_config(completion_config: Config, monkeypatch: pytest.MonkeyPatch):
    """Mock get_config() to return completion_config."""
    monkeypatch.setattr(config_module, "_config", completion_config)
    return completion_config


class TestCompletionCommand:
    """Tests for the completion command."""

    def test_completion_powershell_default(self, cli_runner: CliRunner):
        """Test PowerShell completion script generation (default)."""
        result = cli_runner.invoke(cli, ["completion"])
        assert result.exit_code == 0
        # Should include nb completion
        assert "Register-ArgumentCompleter -Native -CommandName nb" in result.output
        # Should include nbt completion
        assert "Register-ArgumentCompleter -Native -CommandName nbt" in result.output
        # Should have proper type mapping
        assert "switch ($type)" in result.output
        assert '"ProviderContainer"' in result.output
        assert '"ProviderItem"' in result.output
        assert '"ParameterValue"' in result.output

    def test_completion_powershell_explicit(self, cli_runner: CliRunner):
        """Test PowerShell completion with explicit shell option."""
        result = cli_runner.invoke(cli, ["completion", "-s", "powershell"])
        assert result.exit_code == 0
        assert "Register-ArgumentCompleter" in result.output

    def test_completion_bash(self, cli_runner: CliRunner):
        """Test Bash completion script generation."""
        result = cli_runner.invoke(cli, ["completion", "-s", "bash"])
        assert result.exit_code == 0
        assert "_nb_completion()" in result.output
        assert "COMP_WORDS" in result.output
        assert "_NB_COMPLETE=bash_complete" in result.output

    def test_completion_zsh(self, cli_runner: CliRunner):
        """Test Zsh completion script generation."""
        result = cli_runner.invoke(cli, ["completion", "-s", "zsh"])
        assert result.exit_code == 0
        assert "#compdef nb" in result.output
        assert "_nb_completion()" in result.output
        assert "_NB_COMPLETE=zsh_complete" in result.output

    def test_completion_fish(self, cli_runner: CliRunner):
        """Test Fish completion script generation."""
        result = cli_runner.invoke(cli, ["completion", "-s", "fish"])
        assert result.exit_code == 0
        assert "function _nb_completion" in result.output
        assert "_NB_COMPLETE=fish_complete" in result.output


class TestPowerShellSource:
    """Tests for the PowerShell completion script generator."""

    def test_includes_nb_completion(self):
        """Test that nb completion is included."""
        script = _get_powershell_source()
        assert "Register-ArgumentCompleter -Native -CommandName nb" in script

    def test_includes_nbt_completion(self):
        """Test that nbt completion is included by default."""
        script = _get_powershell_source()
        assert "Register-ArgumentCompleter -Native -CommandName nbt" in script

    def test_nbt_can_be_excluded(self):
        """Test that nbt completion can be excluded."""
        script = _get_powershell_source(include_nbt=False)
        assert "Register-ArgumentCompleter -Native -CommandName nb" in script
        assert "Register-ArgumentCompleter -Native -CommandName nbt" not in script

    def test_nbt_transforms_args(self):
        """Test that nbt completion transforms args to nb todo."""
        script = _get_powershell_source()
        # The nbt script should transform nbt -> nb todo
        assert '$nbtArgs -replace "^nbt", "nb todo"' in script

    def test_proper_type_mapping(self):
        """Test that completion result types are properly mapped."""
        script = _get_powershell_source()
        assert '"dir"  { "ProviderContainer" }' in script
        assert '"file" { "ProviderItem" }' in script
        assert 'default { "ParameterValue" }' in script


class TestNotebookCompleter:
    """Tests for the notebook completer function."""

    def test_complete_notebook_returns_all(self, mock_completion_config):
        """Test that complete_notebook returns all notebooks when no prefix."""
        completions = complete_notebook(None, None, "")
        names = [c.value for c in completions]
        assert "daily" in names
        assert "projects" in names
        assert "work" in names
        assert "personal" in names

    def test_complete_notebook_filters_by_prefix(self, mock_completion_config):
        """Test that complete_notebook filters by prefix."""
        completions = complete_notebook(None, None, "p")
        names = [c.value for c in completions]
        assert "projects" in names
        assert "personal" in names
        assert "daily" not in names
        assert "work" not in names

    def test_complete_notebook_has_help_text(self, mock_completion_config):
        """Test that completions have help text."""
        completions = complete_notebook(None, None, "")
        for c in completions:
            assert c.help == "notebook"


class TestViewCompleter:
    """Tests for the view completer function."""

    def test_complete_view_returns_all(self, mock_completion_config):
        """Test that complete_view returns all views when no prefix."""
        completions = complete_view(None, None, "")
        names = [c.value for c in completions]
        assert "work-focus" in names
        assert "high-priority" in names

    def test_complete_view_filters_by_prefix(self, mock_completion_config):
        """Test that complete_view filters by prefix."""
        completions = complete_view(None, None, "work")
        names = [c.value for c in completions]
        assert "work-focus" in names
        assert "high-priority" not in names

    def test_complete_view_has_help_text(self, mock_completion_config):
        """Test that completions have help text."""
        completions = complete_view(None, None, "")
        for c in completions:
            assert c.help == "saved view"


class TestTagCompleter:
    """Tests for the tag completer function."""

    def test_complete_tag_empty_db(self, mock_completion_config):
        """Test that complete_tag returns empty list when no tags exist."""
        # With no indexed todos, there should be no tags
        completions = complete_tag(None, None, "")
        assert completions == []

    def test_complete_tag_handles_errors(self, monkeypatch):
        """Test that complete_tag gracefully handles errors."""

        # Mock get_tag_stats to raise an exception
        def mock_get_tag_stats(*args, **kwargs):
            raise Exception("DB error")

        # Patch the module where it's imported inside the function
        monkeypatch.setattr(
            "nb.index.todos_repo.get_tag_stats",
            mock_get_tag_stats,
        )
        # Should return empty list on error, not raise
        completions = complete_tag(None, None, "")
        assert completions == []
