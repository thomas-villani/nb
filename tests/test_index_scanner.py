"""Tests for nb.index.scanner module."""

from __future__ import annotations

import pytest

from nb.index import scanner as scanner_module
from nb.index.db import get_db, reset_db
from nb.index.scanner import (
    get_file_hash,
    index_all_notes,
    index_note,
    index_todos_from_file,
    needs_reindex,
    remove_deleted_notes,
    scan_notes,
)
from nb.utils.hashing import normalize_path


@pytest.fixture
def db_fixture(mock_config):
    """Set up database for scanner tests."""
    # Reset the global db instance
    reset_db()
    scanner_module.ENABLE_VECTOR_INDEXING = False  # Disable vector indexing for tests

    yield mock_config

    # Cleanup
    reset_db()


class TestScanNotes:
    """Tests for scan_notes function."""

    def test_finds_markdown_files(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")
        create_note("work", "task.md", "# Task\n")

        notes = scan_notes(notes_root)

        filenames = [n.name for n in notes]
        assert "note1.md" in filenames
        assert "note2.md" in filenames
        assert "task.md" in filenames

    def test_ignores_hidden_directories(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        create_note("projects", "visible.md", "# Visible\n")

        hidden = notes_root / ".hidden"
        hidden.mkdir()
        (hidden / "hidden.md").write_text("# Hidden\n")

        notes = scan_notes(notes_root)

        filenames = [n.name for n in notes]
        assert "visible.md" in filenames
        assert "hidden.md" not in filenames

    def test_ignores_nb_directory(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        create_note("projects", "note.md", "# Note\n")

        nb_dir = notes_root / ".nb"
        nb_dir.mkdir(exist_ok=True)
        (nb_dir / "internal.md").write_text("# Internal\n")

        notes = scan_notes(notes_root)

        filenames = [n.name for n in notes]
        assert "note.md" in filenames
        assert "internal.md" not in filenames


class TestGetFileHash:
    """Tests for get_file_hash function."""

    def test_consistent_hash(self, tmp_path):
        file_path = tmp_path / "test.md"
        file_path.write_text("# Test content\n")

        hash1 = get_file_hash(file_path)
        hash2 = get_file_hash(file_path)

        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path):
        file1 = tmp_path / "file1.md"
        file2 = tmp_path / "file2.md"

        file1.write_text("Content 1")
        file2.write_text("Content 2")

        assert get_file_hash(file1) != get_file_hash(file2)


class TestNeedsReindex:
    """Tests for needs_reindex function."""

    def test_new_file_needs_reindex(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        note_path = create_note("projects", "new.md", "# New note\n")

        assert needs_reindex(note_path, notes_root) is True

    def test_indexed_file_unchanged(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        note_path = create_note("projects", "test.md", "# Test\n")

        # Index the note
        index_note(note_path, notes_root, index_vectors=False)

        # Should not need reindexing
        assert needs_reindex(note_path, notes_root) is False

    def test_indexed_file_changed(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        note_path = create_note("projects", "test.md", "# Test\n")

        # Index the note
        index_note(note_path, notes_root, index_vectors=False)

        # Modify the file
        note_path.write_text("# Modified\n")

        # Should need reindexing
        assert needs_reindex(note_path, notes_root) is True


class TestIndexNote:
    """Tests for index_note function."""

    def test_indexes_note_metadata(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        content = """\
---
date: 2025-11-26
tags:
  - meeting
  - important
---

# Test Note

Some content here.
"""
        note_path = create_note("projects", "test.md", content)

        index_note(note_path, notes_root, index_vectors=False)

        db = get_db()
        # Use path relative to notes_root (may use OS-specific separators)
        rel_path = normalize_path(note_path.relative_to(notes_root))
        row = db.fetchone("SELECT * FROM notes WHERE path = ?", (rel_path,))

        assert row is not None
        assert row["title"] == "Test Note"
        assert row["date"] == "2025-11-26"
        assert row["notebook"] == "projects"

    def test_indexes_tags(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        content = """\
---
tags:
  - tag1
  - tag2
---

# Note

#inline_tag
"""
        note_path = create_note("projects", "test.md", content)

        index_note(note_path, notes_root, index_vectors=False)

        db = get_db()
        rel_path = normalize_path(note_path.relative_to(notes_root))
        tags = db.fetchall("SELECT tag FROM note_tags WHERE note_path = ?", (rel_path,))
        tag_list = [t["tag"] for t in tags]

        assert "tag1" in tag_list
        assert "tag2" in tag_list
        assert "inline_tag" in tag_list

    def test_indexes_links(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        content = """\
# Note

See [[other-note]] and [[path/to/note|Display]].
"""
        note_path = create_note("projects", "test.md", content)

        index_note(note_path, notes_root, index_vectors=False)

        db = get_db()
        rel_path = normalize_path(note_path.relative_to(notes_root))
        links = db.fetchall(
            "SELECT target_path FROM note_links WHERE source_path = ?", (rel_path,)
        )
        link_list = [lnk["target_path"] for lnk in links]

        assert "other-note" in link_list
        assert "path/to/note" in link_list

    def test_indexes_todos(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        content = """\
# Note

- [ ] Todo 1 @priority(1)
- [x] Todo 2 #done
- [ ] Todo 3 @due(2025-12-01)
"""
        note_path = create_note("projects", "test.md", content)

        index_note(note_path, notes_root, index_vectors=False)

        db = get_db()
        todos = db.fetchall("SELECT * FROM todos")

        assert len(todos) == 3

    def test_updates_on_reindex(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        content = "# Original Title\n"
        note_path = create_note("projects", "test.md", content)

        # First index
        index_note(note_path, notes_root, index_vectors=False)

        # Modify and reindex
        note_path.write_text("# New Title\n")
        index_note(note_path, notes_root, index_vectors=False)

        db = get_db()
        rel_path = normalize_path(note_path.relative_to(notes_root))
        row = db.fetchone("SELECT * FROM notes WHERE path = ?", (rel_path,))

        assert row["title"] == "New Title"


class TestIndexAllNotes:
    """Tests for index_all_notes function."""

    def test_indexes_multiple_files(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")
        create_note("work", "task.md", "# Task\n")

        count = index_all_notes(notes_root, index_vectors=False)

        assert count == 3

        db = get_db()
        notes = db.fetchall("SELECT * FROM notes")
        assert len(notes) == 3

    def test_skips_unchanged_files(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")

        # First index
        count1 = index_all_notes(notes_root, index_vectors=False)
        assert count1 == 2

        # Second index should skip unchanged
        count2 = index_all_notes(notes_root, index_vectors=False)
        assert count2 == 0

    def test_force_reindex(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")

        # First index
        index_all_notes(notes_root, index_vectors=False)

        # Force reindex
        count = index_all_notes(notes_root, force=True, index_vectors=False)
        assert count == 2


class TestIndexTodosFromFile:
    """Tests for index_todos_from_file function."""

    def test_indexes_todos(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        content = """\
# Tasks

- [ ] Task 1
- [ ] Task 2
- [x] Task 3
"""
        note_path = create_note("projects", "test.md", content)

        count = index_todos_from_file(note_path, notes_root)

        assert count == 3

    def test_updates_on_reindex(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        content = "- [ ] Original task\n"
        note_path = create_note("projects", "test.md", content)

        index_todos_from_file(note_path, notes_root)

        # Modify and reindex
        note_path.write_text("- [ ] New task 1\n- [ ] New task 2\n")
        count = index_todos_from_file(note_path, notes_root)

        assert count == 2

        db = get_db()
        todos = db.fetchall("SELECT * FROM todos")
        # Old todo should be removed, new ones added
        assert len(todos) == 2


class TestRemoveDeletedNotes:
    """Tests for remove_deleted_notes function."""

    def test_removes_deleted_notes(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        note1 = create_note("projects", "note1.md", "# Note 1\n")
        note2 = create_note("projects", "note2.md", "# Note 2\n")

        # Index both
        index_all_notes(notes_root, index_vectors=False)

        db = get_db()
        assert len(db.fetchall("SELECT * FROM notes")) == 2

        # Delete one file
        note1.unlink()

        # Clean up
        removed = remove_deleted_notes(notes_root)

        assert removed == 1
        notes = db.fetchall("SELECT * FROM notes")
        assert len(notes) == 1
        # Path may use OS-specific separators
        assert "note2.md" in notes[0]["path"]

    def test_no_removal_if_all_exist(self, db_fixture, create_note):
        notes_root = db_fixture.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        create_note("projects", "note2.md", "# Note 2\n")

        index_all_notes(notes_root, index_vectors=False)

        removed = remove_deleted_notes(notes_root)

        assert removed == 0

    def test_removes_todos_when_note_deleted(self, db_fixture, create_note):
        """Todos should be deleted when their source note is removed."""
        notes_root = db_fixture.notes_root

        note1 = create_note("projects", "note1.md", "# Note 1\n- [ ] Todo from note1\n")
        create_note("projects", "note2.md", "# Note 2\n- [ ] Todo from note2\n")

        # Index both
        index_all_notes(notes_root, index_vectors=False)

        db = get_db()
        assert len(db.fetchall("SELECT * FROM notes")) == 2
        assert len(db.fetchall("SELECT * FROM todos")) == 2

        # Delete one file
        note1.unlink()

        # Clean up
        removed = remove_deleted_notes(notes_root)

        assert removed == 1
        # Note should be gone
        notes = db.fetchall("SELECT * FROM notes")
        assert len(notes) == 1
        # Todos from deleted note should be gone too
        todos = db.fetchall("SELECT * FROM todos")
        assert len(todos) == 1
        assert "Todo from note2" in todos[0]["content"]

    def test_removes_deleted_notes_by_notebook(self, db_fixture, create_note):
        """When filtering by notebook, only that notebook's deleted notes are removed."""
        notes_root = db_fixture.notes_root

        note1 = create_note("projects", "note1.md", "# Note 1\n- [ ] Project todo\n")
        note2 = create_note("work", "note2.md", "# Note 2\n- [ ] Work todo\n")

        # Index both
        index_all_notes(notes_root, index_vectors=False)

        db = get_db()
        assert len(db.fetchall("SELECT * FROM notes")) == 2
        assert len(db.fetchall("SELECT * FROM todos")) == 2

        # Delete both files
        note1.unlink()
        note2.unlink()

        # Clean up only projects notebook
        removed = remove_deleted_notes(notes_root, notebook="projects")

        assert removed == 1
        # projects note should be gone, work note still exists in DB (even though file deleted)
        notes = db.fetchall("SELECT * FROM notes")
        assert len(notes) == 1
        assert "work" in notes[0]["path"]
        # Only project todo should be removed
        todos = db.fetchall("SELECT * FROM todos")
        assert len(todos) == 1
        assert "Work todo" in todos[0]["content"]

    def test_notebook_filter_invalid_notebook(self, db_fixture, create_note):
        """Invalid notebook name should return 0 without errors."""
        notes_root = db_fixture.notes_root

        create_note("projects", "note1.md", "# Note 1\n")
        index_all_notes(notes_root, index_vectors=False)

        # Try to clean up non-existent notebook
        removed = remove_deleted_notes(notes_root, notebook="nonexistent")

        assert removed == 0
