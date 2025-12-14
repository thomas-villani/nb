"""Tests for nb.core.notebooks module."""

from __future__ import annotations

from datetime import date

import pytest

from nb.core.notebooks import (
    create_notebook,
    ensure_notebook_note,
    get_default_transcript_notebook,
    get_notebook_for_file,
    get_notebook_note_path,
    get_notebook_notes,
    get_notebook_stats,
    is_notebook_date_based,
    list_notebooks,
    notebook_exists,
)


class TestListNotebooks:
    """Tests for list_notebooks function."""

    def test_lists_notebooks(self, mock_config):
        notes_root = mock_config.notes_root

        notebooks = list_notebooks(notes_root)

        # Should include the ones we created in the fixture
        assert "daily" in notebooks
        assert "projects" in notebooks
        assert "work" in notebooks

    def test_ignores_hidden_directories(self, mock_config):
        notes_root = mock_config.notes_root

        # Create a hidden directory
        hidden = notes_root / ".hidden"
        hidden.mkdir()

        notebooks = list_notebooks(notes_root)

        assert ".hidden" not in notebooks
        assert ".nb" not in notebooks

    def test_empty_root(self, tmp_path):
        notebooks = list_notebooks(tmp_path)
        assert notebooks == []

    def test_nonexistent_root(self, tmp_path):
        notebooks = list_notebooks(tmp_path / "nonexistent")
        assert notebooks == []


class TestGetNotebookNotes:
    """Tests for get_notebook_notes function."""

    def test_lists_notes_in_notebook(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")

        notes = get_notebook_notes("projects", notes_root)

        assert len(notes) == 2
        note_names = [n.name for n in notes]
        assert "note1.md" in note_names
        assert "note2.md" in note_names

    def test_lists_notes_in_subdirectories(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        create_note("projects", "root.md", "# Root\n")

        # Create a subdirectory note
        subdir = notes_root / "projects" / "subproject"
        subdir.mkdir()
        (subdir / "sub.md").write_text("# Sub\n")

        notes = get_notebook_notes("projects", notes_root)

        note_names = [n.name for n in notes]
        assert "root.md" in note_names
        assert "sub.md" in note_names

    def test_ignores_hidden_subdirectories(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        create_note("projects", "visible.md", "# Visible\n")

        hidden = notes_root / "projects" / ".hidden"
        hidden.mkdir()
        (hidden / "hidden.md").write_text("# Hidden\n")

        notes = get_notebook_notes("projects", notes_root)

        note_names = [n.name for n in notes]
        assert "visible.md" in note_names
        assert "hidden.md" not in note_names

    def test_empty_notebook(self, mock_config):
        notes_root = mock_config.notes_root

        notes = get_notebook_notes("projects", notes_root)

        assert notes == []

    def test_nonexistent_notebook(self, mock_config):
        notes_root = mock_config.notes_root

        notes = get_notebook_notes("nonexistent", notes_root)

        assert notes == []


class TestCreateNotebook:
    """Tests for create_notebook function."""

    def test_creates_directory(self, mock_config):
        notes_root = mock_config.notes_root

        path = create_notebook("new-notebook", notes_root)

        assert path.exists()
        assert path.is_dir()
        assert path == notes_root / "new-notebook"

    def test_raises_if_exists(self, mock_config):
        notes_root = mock_config.notes_root

        # projects already exists
        with pytest.raises(FileExistsError):
            create_notebook("projects", notes_root)


class TestNotebookExists:
    """Tests for notebook_exists function."""

    def test_existing_notebook(self, mock_config):
        notes_root = mock_config.notes_root

        assert notebook_exists("projects", notes_root) is True

    def test_nonexistent_notebook(self, mock_config):
        notes_root = mock_config.notes_root

        assert notebook_exists("nonexistent", notes_root) is False


class TestGetNotebookStats:
    """Tests for get_notebook_stats function."""

    def test_counts_notes(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")
        create_note("projects", "note3.md", "# Note 3\n")

        stats = get_notebook_stats("projects", notes_root)

        assert stats["note_count"] == 3

    def test_empty_notebook(self, mock_config):
        notes_root = mock_config.notes_root

        stats = get_notebook_stats("projects", notes_root)

        assert stats["note_count"] == 0


class TestIsNotebookDateBased:
    """Tests for is_notebook_date_based function."""

    def test_daily_is_date_based(self, mock_config):
        assert is_notebook_date_based("daily") is True

    def test_projects_not_date_based(self, mock_config):
        assert is_notebook_date_based("projects") is False

    def test_work_not_date_based(self, mock_config):
        assert is_notebook_date_based("work") is False

    def test_unknown_notebook_default(self, mock_config):
        # Unknown notebooks default to non-date-based unless named "daily"
        assert is_notebook_date_based("random") is False


class TestGetNotebookForFile:
    """Tests for get_notebook_for_file function."""

    def test_internal_notebook(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        note_path = create_note("projects", "test.md", "# Test\n")

        notebook = get_notebook_for_file(note_path)

        assert notebook == "projects"

    def test_nested_file(self, mock_config, create_note):
        notes_root = mock_config.notes_root

        subdir = notes_root / "projects" / "sub1" / "sub2"
        subdir.mkdir(parents=True)
        note_path = subdir / "deep.md"
        note_path.write_text("# Deep\n")

        notebook = get_notebook_for_file(note_path)

        assert notebook == "projects"

    def test_file_outside_notes_root(self, mock_config, tmp_path):
        external_path = tmp_path / "external" / "note.md"
        external_path.parent.mkdir(parents=True)
        external_path.write_text("# External\n")

        notebook = get_notebook_for_file(external_path)

        assert notebook is None


class TestGetNotebookNotePath:
    """Tests for get_notebook_note_path function."""

    def test_date_based_notebook(self, mock_config):
        path = get_notebook_note_path("daily", dt=date(2025, 11, 26))

        assert str(path).endswith("2025-11-26.md")
        assert "2025" in str(path)  # Year folder

    def test_flat_notebook(self, mock_config):
        path = get_notebook_note_path("projects", name="my-note")

        assert path.name == "my-note.md"

    def test_flat_notebook_with_extension(self, mock_config):
        path = get_notebook_note_path("projects", name="my-note.md")

        assert path.name == "my-note.md"

    def test_raises_without_name_for_flat(self, mock_config):
        with pytest.raises(ValueError, match="Name required"):
            get_notebook_note_path("projects")


class TestEnsureNotebookNote:
    """Tests for ensure_notebook_note function."""

    def test_creates_date_based_note(self, mock_config):
        dt = date(2025, 11, 26)

        path = ensure_notebook_note("daily", dt=dt)

        assert path.exists()
        content = path.read_text()
        assert "date: 2025-11-26" in content
        assert "Wednesday, November 26, 2025" in content

    def test_creates_flat_note(self, mock_config):
        path = ensure_notebook_note("projects", name="my-project")

        assert path.exists()
        content = path.read_text()
        assert "title: My Project" in content
        assert "# My Project" in content

    def test_returns_existing_note(self, mock_config):
        dt = date(2025, 11, 26)

        path1 = ensure_notebook_note("daily", dt=dt)
        original_content = path1.read_text()

        # Modify the note
        path1.write_text(original_content + "\nModified!")

        # Ensure again
        path2 = ensure_notebook_note("daily", dt=dt)

        assert path1 == path2
        assert "Modified!" in path2.read_text()

    def test_creates_parent_directories(self, mock_config):
        dt = date(2025, 11, 26)

        path = ensure_notebook_note("daily", dt=dt)

        assert path.parent.exists()


class TestGetDefaultTranscriptNotebook:
    """Tests for get_default_transcript_notebook function."""

    def test_returns_daily_when_configured(self, mock_config):
        """Should return 'daily' when it exists in config."""
        result = get_default_transcript_notebook()
        assert result == "daily"

    def test_returns_first_date_based_when_no_daily(self, temp_notes_root, monkeypatch):
        """Should return first date-based notebook when 'daily' doesn't exist."""
        from nb.config import Config, NotebookConfig, reset_config

        # Config without 'daily' but with a date-based notebook
        config = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[
                NotebookConfig(name="journal", date_based=True),
                NotebookConfig(name="projects", date_based=False),
            ],
        )

        def mock_get_config():
            return config

        import nb.core.notebooks

        monkeypatch.setattr(nb.core.notebooks, "get_config", mock_get_config)
        reset_config()

        result = get_default_transcript_notebook()
        assert result == "journal"

    def test_returns_first_notebook_when_no_date_based(
        self, temp_notes_root, monkeypatch
    ):
        """Should return first notebook when no date-based notebooks exist."""
        from nb.config import Config, NotebookConfig, reset_config

        # Config without any date-based notebooks
        config = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[
                NotebookConfig(name="projects", date_based=False),
                NotebookConfig(name="work", date_based=False),
            ],
        )

        def mock_get_config():
            return config

        import nb.core.notebooks

        monkeypatch.setattr(nb.core.notebooks, "get_config", mock_get_config)
        reset_config()

        result = get_default_transcript_notebook()
        assert result == "projects"

    def test_raises_when_no_notebooks(self, temp_notes_root, monkeypatch):
        """Should raise ValueError when no notebooks are configured."""
        from nb.config import Config, reset_config

        # Config with no notebooks
        config = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[],
        )

        def mock_get_config():
            return config

        import nb.core.notebooks

        monkeypatch.setattr(nb.core.notebooks, "get_config", mock_get_config)
        reset_config()

        with pytest.raises(ValueError, match="No notebooks configured"):
            get_default_transcript_notebook()
