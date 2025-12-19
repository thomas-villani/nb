"""Shared fixtures for nb tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from nb import config as config_module
from nb.cli import cli
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.index import scanner as scanner_module
from nb.index.db import reset_db
from nb.index.search import reset_search


@pytest.fixture
def temp_notes_root(tmp_path: Path) -> Path:
    """Create a temporary notes root directory with .nb folder."""
    notes_root = tmp_path / "notes"
    notes_root.mkdir(parents=True)
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()
    return notes_root


@pytest.fixture
def temp_config(temp_notes_root: Path) -> Generator[Config]:
    """Create a temporary configuration for testing."""
    cfg = Config(
        notes_root=temp_notes_root,
        editor="nano",
        notebooks=[
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
            NotebookConfig(name="work", date_based=False),
        ],
        embeddings=EmbeddingsConfig(),
        date_format="%Y-%m-%d",
        time_format="%H:%M",
    )

    # Create notebook directories
    for nb in cfg.notebooks:
        if not nb.is_external:
            (temp_notes_root / nb.name).mkdir(exist_ok=True)

    yield cfg

    # Reset global singletons after test to avoid interference
    reset_search()  # Must reset before config to avoid stale references
    config_module.reset_config()
    reset_db()


@pytest.fixture
def mock_config(temp_config: Config, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Mock get_config() to return temp_config.

    This patches the get_config function itself (not just _config variable)
    so that even if reset_config() is called during the test, subsequent
    calls to get_config() will still return the temp config.
    """
    # Reset any cached singletons before test
    config_module.reset_config()
    reset_db()
    # Patch get_config to always return temp_config
    monkeypatch.setattr(config_module, "get_config", lambda: temp_config)
    return temp_config


@pytest.fixture
def sample_note_content() -> str:
    """Sample markdown note with frontmatter."""
    return """\
---
date: 2025-11-26
tags:
  - meeting
  - project
---

# Team Standup

Discussed project timeline with [[projects/roadmap|the roadmap]].

## Action Items

- [ ] Review PR #123 @due(tomorrow)
- [x] Update documentation #docs
- [ ] Fix bug @priority(1) @due(friday)

See also [[daily/2025-11-25|yesterday's notes]].

#followup #urgent
"""


@pytest.fixture
def sample_todo_content() -> str:
    """Sample markdown file with todos."""
    return """\
# Project Tasks

- [ ] High priority task @priority(1) @due(2025-12-01)
- [x] Completed task #done
- [ ] Medium priority @priority(2)
  - [ ] Sub-task 1
  - [ ] Sub-task 2 @due(friday)
- [ ] Low priority @priority(3) #backlog
- [ ] Task with attachment @attach: ./docs/spec.pdf
"""


@pytest.fixture
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> date:
    """Fix date.today() to a known value for deterministic tests."""
    fixed = date(2025, 11, 28)  # A Friday

    class MockDate(date):
        @classmethod
        def today(cls) -> date:
            return fixed

    monkeypatch.setattr("nb.utils.dates.date", MockDate)
    monkeypatch.setattr("nb.models.date", MockDate)
    return fixed


@pytest.fixture
def create_note(temp_notes_root: Path):
    """Factory fixture to create note files."""

    def _create_note(
        notebook: str,
        filename: str,
        content: str,
        *,
        week_folder: str | None = None,
        year: int | None = None,
    ) -> Path:
        if week_folder:
            # Date-based structure: YYYY/WeekFolder/filename
            note_dir = temp_notes_root / notebook / str(year or 2025) / week_folder
        else:
            # Flat structure: notebook/filename
            note_dir = temp_notes_root / notebook

        note_dir.mkdir(parents=True, exist_ok=True)
        note_path = note_dir / filename
        note_path.write_text(content, encoding="utf-8")
        return note_path

    return _create_note


# =============================================================================
# CLI Test Fixtures
# =============================================================================


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI runner for testing commands."""
    return CliRunner()


@pytest.fixture
def cli_config(tmp_path: Path) -> Generator[Config]:
    """Create an isolated config specifically for CLI tests.

    Uses 'echo' as editor to avoid actually opening files.
    Disables vector indexing for speed.
    """
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()

    cfg = Config(
        notes_root=notes_root,
        editor="echo",  # No-op editor for testing
        notebooks=[
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
            NotebookConfig(name="work", date_based=False),
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

    # Cleanup - IMPORTANT: restore ENABLE_VECTOR_INDEXING to avoid affecting other tests/processes
    scanner_module.ENABLE_VECTOR_INDEXING = True
    reset_search()  # Must reset before config to avoid stale references
    config_module.reset_config()
    reset_db()


@pytest.fixture
def mock_cli_config(cli_config: Config, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Mock get_config() to return cli_config for CLI tests.

    This patches the get_config function itself (not just _config variable)
    so that even if reset_config() is called during the test, subsequent
    calls to get_config() will still return the cli config.
    """
    # Reset any cached config first
    config_module.reset_config()
    # Patch get_config to always return cli_config
    monkeypatch.setattr(config_module, "get_config", lambda: cli_config)
    return cli_config


@pytest.fixture
def indexed_note(
    cli_runner: CliRunner, mock_cli_config: Config
) -> Callable[[str, str, str], Path]:
    """Factory fixture to create a note and index it.

    Usage:
        def test_something(indexed_note):
            path = indexed_note("projects", "task.md", "# Tasks\\n- [ ] Do thing")
    """

    def _create(notebook: str, filename: str, content: str) -> Path:
        path = mock_cli_config.notes_root / notebook / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        cli_runner.invoke(cli, ["index"])
        return path

    return _create


@pytest.fixture
def indexed_todo_note(
    cli_runner: CliRunner, mock_cli_config: Config
) -> Callable[[list[str], str], Path]:
    """Factory fixture to create a note with todos and index it.

    Usage:
        def test_todo_done(indexed_todo_note):
            path = indexed_todo_note(["Task 1", "Task 2 @due(friday)"])
    """

    def _create(todos: list[str], notebook: str = "projects") -> Path:
        content = "# Tasks\n\n" + "\n".join(f"- [ ] {t}" for t in todos)
        path = mock_cli_config.notes_root / notebook / "tasks.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        cli_runner.invoke(cli, ["index"])
        return path

    return _create


@pytest.fixture
def get_todo_id(cli_runner: CliRunner) -> Callable[[str], str | None]:
    """Helper to get a todo ID by matching content in 'nb todo' output.

    Usage:
        def test_done(get_todo_id, indexed_todo_note):
            indexed_todo_note(["My task"])
            todo_id = get_todo_id("My task")
            result = cli_runner.invoke(cli, ["todo", "done", todo_id])
    """

    def _get_id(content_match: str) -> str | None:
        result = cli_runner.invoke(cli, ["todo"])
        # Parse output to find todo ID
        # Format is: "o content  source  ...  id"
        for line in result.output.split("\n"):
            if content_match in line:
                # ID is last 6 chars before any trailing text
                parts = line.split()
                if parts:
                    # Look for a 6-char hex-like string
                    for part in reversed(parts):
                        # Todo IDs are displayed as 6 hex characters
                        if len(part) >= 6 and all(
                            c in "0123456789abcdef" for c in part[:6]
                        ):
                            return part
        return None

    return _get_id
