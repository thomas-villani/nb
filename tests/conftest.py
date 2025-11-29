"""Shared fixtures for nb tests."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Generator

import pytest

from nb import config as config_module
from nb.config import Config, NotebookConfig, EmbeddingsConfig


@pytest.fixture
def temp_notes_root(tmp_path: Path) -> Path:
    """Create a temporary notes root directory with .nb folder."""
    notes_root = tmp_path / "notes"
    notes_root.mkdir(parents=True)
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()
    return notes_root


@pytest.fixture
def temp_config(temp_notes_root: Path) -> Generator[Config, None, None]:
    """Create a temporary configuration for testing."""
    cfg = Config(
        notes_root=temp_notes_root,
        editor="nano",
        notebooks=[
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
            NotebookConfig(name="work", date_based=False),
        ],
        linked_todos=[],
        linked_notes=[],
        embeddings=EmbeddingsConfig(),
        date_format="%Y-%m-%d",
        time_format="%H:%M",
    )

    # Create notebook directories
    for nb in cfg.notebooks:
        if not nb.is_external:
            (temp_notes_root / nb.name).mkdir(exist_ok=True)

    yield cfg

    # Reset the global config singleton after test
    config_module.reset_config()


@pytest.fixture
def mock_config(temp_config: Config, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Mock get_config() to return temp_config."""
    monkeypatch.setattr(config_module, "_config", temp_config)
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
