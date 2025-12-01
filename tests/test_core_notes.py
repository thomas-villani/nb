"""Tests for nb.core.notes module."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nb.core.notes import (
    create_note,
    ensure_daily_note,
    get_daily_note_path,
    get_note,
    get_notebook_for_path,
    list_daily_notes,
    list_notes,
)


class TestGetDailyNotePath:
    """Tests for get_daily_note_path function."""

    def test_path_structure(self, mock_config):
        dt = date(2025, 11, 26)
        notes_root = mock_config.notes_root

        path = get_daily_note_path(dt, notes_root)

        # Should be: daily/2025/Nov24-Nov30/2025-11-26.md
        assert path.parent.parent.parent.name == "daily"
        assert path.parent.parent.name == "2025"
        assert "Nov" in path.parent.name
        assert path.name == "2025-11-26.md"

    def test_different_weeks(self, mock_config):
        notes_root = mock_config.notes_root

        path1 = get_daily_note_path(date(2025, 11, 26), notes_root)
        path2 = get_daily_note_path(date(2025, 12, 3), notes_root)

        # Different weeks should have different week folder names
        assert path1.parent.name != path2.parent.name


class TestEnsureDailyNote:
    """Tests for ensure_daily_note function."""

    def test_creates_note_if_missing(self, mock_config):
        dt = date(2025, 11, 26)
        notes_root = mock_config.notes_root

        path = ensure_daily_note(dt, notes_root)

        assert path.exists()
        content = path.read_text()
        # Default format includes day of week from config.daily_title_format
        assert "# Wednesday, November 26, 2025" in content
        assert "date:" in content

    def test_returns_existing_note(self, mock_config, create_note):
        dt = date(2025, 11, 26)
        notes_root = mock_config.notes_root

        # Create the note first
        path1 = ensure_daily_note(dt, notes_root)
        original_content = path1.read_text()

        # Modify content
        path1.write_text(original_content + "\nModified!", encoding="utf-8")

        # Ensure again - should return same file without overwriting
        path2 = ensure_daily_note(dt, notes_root)

        assert path1 == path2
        assert "Modified!" in path2.read_text()

    def test_creates_directory_structure(self, mock_config):
        dt = date(2025, 11, 26)
        notes_root = mock_config.notes_root

        path = ensure_daily_note(dt, notes_root)

        assert path.parent.exists()
        assert path.parent.parent.exists()  # Year folder
        assert path.parent.parent.parent.exists()  # daily folder


class TestCreateNote:
    """Tests for create_note function."""

    def test_creates_note_with_template(self, mock_config):
        notes_root = mock_config.notes_root

        path = create_note(
            Path("projects/myproject/ideas.md"),
            title="Project Ideas",
            dt=date(2025, 11, 26),
            tags=["brainstorm"],
            notes_root=notes_root,
        )

        assert path.exists()
        content = path.read_text()
        assert "# Project Ideas" in content
        assert "brainstorm" in content
        assert "date:" in content

    def test_adds_md_extension(self, mock_config):
        notes_root = mock_config.notes_root

        path = create_note(
            Path("projects/test-note"),  # No extension
            title="Test",
            notes_root=notes_root,
        )

        assert path.suffix == ".md"

    def test_raises_if_exists(self, mock_config):
        notes_root = mock_config.notes_root

        # Create first note
        create_note(Path("test.md"), notes_root=notes_root)

        # Try to create again
        with pytest.raises(FileExistsError):
            create_note(Path("test.md"), notes_root=notes_root)

    def test_creates_parent_directories(self, mock_config):
        notes_root = mock_config.notes_root

        path = create_note(
            Path("deep/nested/path/note.md"),
            notes_root=notes_root,
        )

        assert path.exists()
        assert (notes_root / "deep" / "nested" / "path").is_dir()


class TestGetNote:
    """Tests for get_note function."""

    def test_parses_note_with_frontmatter(
        self, mock_config, create_note, sample_note_content
    ):
        notes_root = mock_config.notes_root

        # Create a note with frontmatter
        note_path = create_note("projects", "test.md", sample_note_content)

        note = get_note(note_path, notes_root)

        assert note is not None
        assert note.title == "Team Standup"
        assert note.date == date(2025, 11, 26)
        assert "meeting" in note.tags
        assert "project" in note.tags
        assert note.notebook == "projects"

    def test_extracts_wiki_links(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = """\
---
date: 2025-11-26
---

See [[other-note]] and [[path/to/note|Display Text]].
"""
        note_path = create_note("projects", "test.md", content)

        note = get_note(note_path, notes_root)

        assert "other-note" in note.links
        assert "path/to/note" in note.links

    def test_returns_none_for_missing_file(self, mock_config):
        notes_root = mock_config.notes_root

        note = get_note(Path("nonexistent.md"), notes_root)

        assert note is None

    def test_relative_path(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        content = "---\ndate: 2025-11-26\n---\n# Test\n"
        create_note("projects", "test.md", content)

        note = get_note(Path("projects/test.md"), notes_root)

        assert note is not None
        assert note.path == Path("projects/test.md")


class TestGetNotebookForPath:
    """Tests for get_notebook_for_path function."""

    def test_extracts_notebook_name(self):
        assert get_notebook_for_path(Path("daily/2025/file.md")) == "daily"
        assert get_notebook_for_path(Path("projects/subdir/note.md")) == "projects"
        assert get_notebook_for_path(Path("work/task.md")) == "work"

    def test_no_notebook_for_root_file(self):
        assert get_notebook_for_path(Path("standalone.md")) == ""


class TestListNotes:
    """Tests for list_notes function."""

    def test_lists_all_notes(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")
        create_note("work", "task.md", "# Task\n")

        notes = list_notes(notes_root=notes_root)

        assert len(notes) >= 3
        note_names = [n.name for n in notes]
        assert "note1.md" in note_names
        assert "note2.md" in note_names
        assert "task.md" in note_names

    def test_filters_by_notebook(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("work", "task.md", "# Task\n")

        notes = list_notes(notebook="projects", notes_root=notes_root)

        assert len(notes) == 1
        assert notes[0].name == "note1.md"

    def test_ignores_hidden_directories(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        create_note("projects", "visible.md", "# Visible\n")

        # Create a hidden directory with a note
        hidden_dir = notes_root / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "hidden.md").write_text("# Hidden\n")

        notes = list_notes(notes_root=notes_root)

        note_names = [n.name for n in notes]
        assert "visible.md" in note_names
        assert "hidden.md" not in note_names

    def test_empty_notebook(self, mock_config):
        notes_root = mock_config.notes_root

        notes = list_notes(notebook="empty", notes_root=notes_root)

        assert notes == []


class TestListDailyNotes:
    """Tests for list_daily_notes function."""

    def test_lists_daily_notes(self, mock_config):
        notes_root = mock_config.notes_root

        # Create some daily notes
        from nb.core.notes import ensure_daily_note

        ensure_daily_note(date(2025, 11, 25), notes_root)
        ensure_daily_note(date(2025, 11, 26), notes_root)
        ensure_daily_note(date(2025, 11, 27), notes_root)

        notes = list_daily_notes(notes_root=notes_root)

        assert len(notes) == 3
        # Should be sorted descending
        assert "2025-11-27" in notes[0].name
        assert "2025-11-25" in notes[-1].name

    def test_filters_by_date_range(self, mock_config):
        notes_root = mock_config.notes_root

        from nb.core.notes import ensure_daily_note

        ensure_daily_note(date(2025, 11, 20), notes_root)
        ensure_daily_note(date(2025, 11, 25), notes_root)
        ensure_daily_note(date(2025, 11, 30), notes_root)

        notes = list_daily_notes(
            start=date(2025, 11, 24),
            end=date(2025, 11, 28),
            notes_root=notes_root,
        )

        assert len(notes) == 1
        assert "2025-11-25" in notes[0].name

    def test_empty_daily_folder(self, mock_config):
        notes_root = mock_config.notes_root

        notes = list_daily_notes(notes_root=notes_root)

        assert notes == []
