"""Tests for nb summarize and tldr commands."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_note_with_frontmatter() -> str:
    """Sample note with frontmatter for testing."""
    return """\
---
date: 2025-11-28
tags:
  - project
  - planning
---

# Project Planning Meeting

We discussed the Q1 roadmap.

## Action Items

- [ ] Create project timeline @due(friday)
- [ ] Review budget estimates @priority(1)
- [x] Send meeting invite

## Decisions

- Use React for frontend
- PostgreSQL for database
"""


@pytest.fixture
def sample_simple_note() -> str:
    """Simple note without frontmatter."""
    return """\
# Quick Notes

Just some random thoughts about the project.
Need to follow up on API design.
"""


# =============================================================================
# resolve_target Tests
# =============================================================================


class TestResolveTarget:
    """Tests for target resolution logic."""

    def test_resolve_no_args_returns_today(self, mock_cli_config: Config, monkeypatch):
        """No args should resolve to today's daily note."""
        from datetime import date

        from nb.core.ai.summarize import resolve_target
        from nb.core.notes import ensure_daily_note

        # Use actual today's date (don't mock) - simpler approach
        today = date.today()

        # Create today's note
        ensure_daily_note(today, mock_cli_config.notes_root)

        target = resolve_target(notes_root=mock_cli_config.notes_root)

        assert target.target_type == "single_note"
        assert len(target.notes) == 1
        assert "today" in target.description

    def test_resolve_no_args_raises_if_no_today_note(self, mock_cli_config: Config):
        """Should raise if today's note doesn't exist."""
        from nb.core.ai.summarize import resolve_target

        with pytest.raises(ValueError, match="No daily note exists for today"):
            resolve_target(notes_root=mock_cli_config.notes_root)

    def test_resolve_yesterday(
        self, mock_cli_config: Config, fixed_today: date, monkeypatch
    ):
        """'yesterday' should resolve to yesterday's note."""
        from nb.core.ai.summarize import resolve_target
        from nb.core.notes import ensure_daily_note

        # Patch date.today in summarize module
        monkeypatch.setattr("nb.core.ai.summarize.date", type(fixed_today))

        yesterday = fixed_today - timedelta(days=1)
        ensure_daily_note(yesterday, mock_cli_config.notes_root)

        target = resolve_target(
            target="yesterday", notes_root=mock_cli_config.notes_root
        )

        assert target.target_type == "single_note"
        assert len(target.notes) == 1
        assert "yesterday" in target.description

    def test_resolve_specific_note_path(
        self, mock_cli_config: Config, sample_simple_note: str
    ):
        """path/note should resolve to specific note."""
        from nb.core.ai.summarize import resolve_target

        # Create a specific note
        note_path = mock_cli_config.notes_root / "work" / "meeting.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(sample_simple_note, encoding="utf-8")

        target = resolve_target(
            target="work/meeting", notes_root=mock_cli_config.notes_root
        )

        assert target.target_type == "single_note"
        assert len(target.notes) == 1
        assert target.notes[0].path == Path("work/meeting.md")

    def test_resolve_notebook_name(
        self, mock_cli_config: Config, sample_simple_note: str
    ):
        """Notebook name (no /) should resolve to all notes in notebook."""
        from nb.core.ai.summarize import resolve_target

        # Create multiple notes in the notebook
        work_dir = mock_cli_config.notes_root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            note_path = work_dir / f"note{i}.md"
            note_path.write_text(sample_simple_note, encoding="utf-8")

        target = resolve_target(target="work", notes_root=mock_cli_config.notes_root)

        assert target.target_type == "notebook"
        assert len(target.notes) == 3
        assert "work notebook" in target.description

    def test_resolve_with_days_filter(
        self,
        mock_cli_config: Config,
        sample_note_with_frontmatter: str,
        cli_runner: CliRunner,
    ):
        """--days should limit to last N days."""
        from nb.core.ai.summarize import resolve_target

        # Create notes with different dates
        for i in range(5):
            note_date = date.today() - timedelta(days=i)
            content = sample_note_with_frontmatter.replace(
                "2025-11-28", note_date.isoformat()
            )
            note_path = mock_cli_config.notes_root / "work" / f"note{i}.md"
            note_path.write_text(content, encoding="utf-8")

        # Index
        cli_runner.invoke(cli, ["index"])

        target = resolve_target(
            target="work", days=3, notes_root=mock_cli_config.notes_root
        )

        assert target.target_type == "notebook"
        assert len(target.notes) <= 3
        assert "last 3 days" in target.description

    def test_resolve_note_not_found(self, mock_cli_config: Config):
        """Should raise if specific note doesn't exist."""
        from nb.core.ai.summarize import resolve_target

        with pytest.raises(ValueError, match="Note not found"):
            resolve_target(
                target="work/nonexistent", notes_root=mock_cli_config.notes_root
            )


# =============================================================================
# Frontmatter Tests
# =============================================================================


class TestFrontmatterUpdate:
    """Tests for frontmatter summary storage."""

    def test_updates_existing_frontmatter(
        self, mock_cli_config: Config, sample_note_with_frontmatter: str
    ):
        """Should update existing frontmatter with summary key."""
        import frontmatter

        from nb.core.ai.summarize import update_note_frontmatter_summary

        note_path = mock_cli_config.notes_root / "work" / "test.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(sample_note_with_frontmatter, encoding="utf-8")

        summary = "This is a test summary."
        update_note_frontmatter_summary(
            Path("work/test.md"), summary, mock_cli_config.notes_root
        )

        # Verify
        with note_path.open(encoding="utf-8") as f:
            post = frontmatter.load(f)

        assert post.metadata["summary"] == summary
        assert "date" in post.metadata  # Other keys preserved
        assert "tags" in post.metadata

    def test_adds_frontmatter_to_note_without(
        self, mock_cli_config: Config, sample_simple_note: str
    ):
        """Should add frontmatter to note that doesn't have it."""
        import frontmatter

        from nb.core.ai.summarize import update_note_frontmatter_summary

        note_path = mock_cli_config.notes_root / "work" / "simple.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(sample_simple_note, encoding="utf-8")

        summary = "A brief summary of the note."
        update_note_frontmatter_summary(
            Path("work/simple.md"), summary, mock_cli_config.notes_root
        )

        # Verify
        with note_path.open(encoding="utf-8") as f:
            post = frontmatter.load(f)

        assert post.metadata["summary"] == summary

    def test_get_frontmatter_summary_returns_existing(self, mock_cli_config: Config):
        """Should return existing summary from frontmatter."""
        from nb.core.ai.summarize import _get_frontmatter_summary

        note_content = """\
---
summary: Existing summary text
date: 2025-11-28
---

# Note Content
"""
        note_path = mock_cli_config.notes_root / "work" / "has-summary.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(note_content, encoding="utf-8")

        result = _get_frontmatter_summary(Path("work/has-summary.md"))

        assert result == "Existing summary text"

    def test_get_frontmatter_summary_returns_none_if_missing(
        self, mock_cli_config: Config, sample_note_with_frontmatter: str
    ):
        """Should return None if note has no summary in frontmatter."""
        from nb.core.ai.summarize import _get_frontmatter_summary

        note_path = mock_cli_config.notes_root / "work" / "no-summary.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(sample_note_with_frontmatter, encoding="utf-8")

        result = _get_frontmatter_summary(Path("work/no-summary.md"))

        assert result is None


# =============================================================================
# CLI Command Tests
# =============================================================================


class TestSummarizeCommand:
    """Tests for nb summarize CLI command."""

    def test_summarize_help(self, cli_runner: CliRunner):
        """Test summarize command shows help."""
        result = cli_runner.invoke(cli, ["summarize", "--help"])

        assert result.exit_code == 0
        assert "Summarize notes with AI" in result.output
        assert "--notebook" in result.output
        assert "--front-matter" in result.output

    def test_summarize_no_note_error(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Should show error when no daily note exists."""
        result = cli_runner.invoke(cli, ["summarize"])

        assert result.exit_code == 1
        assert "No daily note exists for today" in result.output

    @patch("nb.core.ai.summarize.get_llm_client")
    def test_summarize_single_note(
        self,
        mock_get_client,
        cli_runner: CliRunner,
        mock_cli_config: Config,
        sample_note_with_frontmatter: str,
    ):
        """Test summarizing a single note."""
        # Create note
        note_path = mock_cli_config.notes_root / "work" / "meeting.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(sample_note_with_frontmatter, encoding="utf-8")

        # Mock LLM response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is a summary of the meeting notes."
        mock_response.input_tokens = 100
        mock_response.output_tokens = 50
        mock_client.complete.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = cli_runner.invoke(cli, ["summarize", "work/meeting", "--no-stream"])

        assert result.exit_code == 0
        assert "Summary:" in result.output
        mock_client.complete.assert_called_once()


class TestTldrCommand:
    """Tests for nb tldr CLI command."""

    def test_tldr_help(self, cli_runner: CliRunner):
        """Test tldr command shows help."""
        result = cli_runner.invoke(cli, ["tldr", "--help"])

        assert result.exit_code == 0
        assert "Quick 1-2 sentence summary" in result.output

    @patch("nb.core.ai.summarize.get_llm_client")
    def test_tldr_single_note(
        self,
        mock_get_client,
        cli_runner: CliRunner,
        mock_cli_config: Config,
        sample_note_with_frontmatter: str,
    ):
        """Test TLDR of a single note."""
        # Create note
        note_path = mock_cli_config.notes_root / "work" / "meeting.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(sample_note_with_frontmatter, encoding="utf-8")

        # Mock LLM response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Meeting about Q1 roadmap with action items."
        mock_response.input_tokens = 100
        mock_response.output_tokens = 20
        mock_client.complete.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = cli_runner.invoke(cli, ["tldr", "work/meeting", "--no-stream"])

        assert result.exit_code == 0
        assert "TLDR:" in result.output


# =============================================================================
# Save to Note Tests
# =============================================================================


class TestAppendSummaryToNote:
    """Tests for saving summary to a note."""

    def test_append_to_existing_note(
        self, mock_cli_config: Config, sample_simple_note: str
    ):
        """Should append summary to existing note."""
        from nb.core.ai.summarize import append_summary_to_note

        note_path = mock_cli_config.notes_root / "work" / "target.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(sample_simple_note, encoding="utf-8")

        result_path = append_summary_to_note(
            summary="This is the summary.",
            target_description="work notebook",
            note_path=Path("work/target.md"),
            notes_root=mock_cli_config.notes_root,
        )

        assert result_path == note_path
        content = note_path.read_text(encoding="utf-8")
        assert "## Summary: work notebook" in content
        assert "This is the summary." in content

    def test_append_creates_note_if_missing(self, mock_cli_config: Config):
        """Should create note if it doesn't exist."""
        from nb.core.ai.summarize import append_summary_to_note

        result_path = append_summary_to_note(
            summary="New summary.",
            target_description="test",
            note_path=Path("work/new-note.md"),
            notes_root=mock_cli_config.notes_root,
        )

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "New summary." in content

    def test_append_to_today_note(
        self, mock_cli_config: Config, fixed_today: date, monkeypatch
    ):
        """Should append to today's daily note when note_path is None."""
        from nb.core.ai.summarize import append_summary_to_note
        from nb.core.notes import ensure_daily_note

        # Patch date.today in summarize module
        monkeypatch.setattr("nb.core.ai.summarize.date", type(fixed_today))

        ensure_daily_note(fixed_today, mock_cli_config.notes_root)

        result_path = append_summary_to_note(
            summary="Today's summary.",
            target_description="daily summary",
            note_path=None,
            notes_root=mock_cli_config.notes_root,
        )

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "Today's summary." in content


# =============================================================================
# Map-Reduce Tests
# =============================================================================


class TestMapReduceSummarization:
    """Tests for multi-note map-reduce summarization."""

    @patch("nb.core.ai.summarize.get_llm_client")
    def test_map_reduce_calls_llm_for_each_note(
        self,
        mock_get_client,
        mock_cli_config: Config,
        sample_simple_note: str,
    ):
        """Map phase should call LLM for each note."""
        from nb.core.ai.summarize import resolve_target, summarize_notes_map_reduce

        # Create notes
        work_dir = mock_cli_config.notes_root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            note_path = work_dir / f"note{i}.md"
            note_path.write_text(sample_simple_note, encoding="utf-8")

        # Mock LLM
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Individual summary."
        mock_response.input_tokens = 50
        mock_response.output_tokens = 25
        mock_client.complete.return_value = mock_response
        mock_get_client.return_value = mock_client

        target = resolve_target(target="work", notes_root=mock_cli_config.notes_root)
        result = summarize_notes_map_reduce(target, mode="summarize")

        # 3 notes + 1 reduce = 4 calls
        assert mock_client.complete.call_count == 4
        assert len(result.individual_summaries) == 3

    @patch("nb.core.ai.summarize.get_llm_client")
    def test_map_reduce_uses_cached_summaries(
        self,
        mock_get_client,
        mock_cli_config: Config,
    ):
        """Should skip LLM call if note has summary in frontmatter."""
        from nb.core.ai.summarize import resolve_target, summarize_notes_map_reduce

        # Create note with existing summary
        note_with_summary = """\
---
summary: Cached summary from frontmatter.
---

# Note Content
"""
        note_without = """\
# Another Note

Some content.
"""
        work_dir = mock_cli_config.notes_root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "cached.md").write_text(note_with_summary, encoding="utf-8")
        (work_dir / "fresh.md").write_text(note_without, encoding="utf-8")

        # Mock LLM
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Fresh summary."
        mock_response.input_tokens = 50
        mock_response.output_tokens = 25
        mock_client.complete.return_value = mock_response
        mock_get_client.return_value = mock_client

        target = resolve_target(target="work", notes_root=mock_cli_config.notes_root)
        result = summarize_notes_map_reduce(target, mode="summarize")

        # Only 1 note summary + 1 reduce = 2 calls (cached note skipped)
        assert mock_client.complete.call_count == 2
        assert len(result.individual_summaries) == 2
        # Verify cached summary was used
        cached_summary = next(
            s for s in result.individual_summaries if "cached" in str(s.path)
        )
        assert cached_summary.summary == "Cached summary from frontmatter."
