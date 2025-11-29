"""Tests for nb.utils.hashing module."""

from __future__ import annotations

from pathlib import Path

from nb.utils.hashing import (
    hash_content,
    make_attachment_id,
    make_note_hash,
    make_todo_id,
    normalize_path,
)


class TestNormalizePath:
    """Tests for normalize_path function."""

    def test_path_object(self):
        path = Path("folder/subfolder/file.md")
        result = normalize_path(path)
        assert result == "folder/subfolder/file.md"

    def test_string_with_forward_slashes(self):
        result = normalize_path("folder/subfolder/file.md")
        assert result == "folder/subfolder/file.md"

    def test_string_with_backslashes(self):
        result = normalize_path("folder\\subfolder\\file.md")
        assert result == "folder/subfolder/file.md"

    def test_mixed_slashes(self):
        result = normalize_path("folder/sub\\file.md")
        assert result == "folder/sub/file.md"

    def test_windows_absolute_path(self):
        path = Path("C:/Users/test/notes/file.md")
        result = normalize_path(path)
        assert result == "C:/Users/test/notes/file.md"


class TestHashContent:
    """Tests for hash_content function."""

    def test_default_length(self):
        result = hash_content("test content")
        assert len(result) == 8
        assert result.isalnum()  # Hex characters

    def test_custom_length(self):
        result = hash_content("test content", length=16)
        assert len(result) == 16

    def test_deterministic(self):
        result1 = hash_content("same content")
        result2 = hash_content("same content")
        assert result1 == result2

    def test_different_content(self):
        result1 = hash_content("content one")
        result2 = hash_content("content two")
        assert result1 != result2

    def test_empty_string(self):
        result = hash_content("")
        assert len(result) == 8
        # SHA256 of empty string is known
        assert result == "e3b0c442"  # First 8 chars of SHA256("")


class TestMakeTodoId:
    """Tests for make_todo_id function."""

    def test_generates_id(self):
        path = Path("daily/2025/Nov/2025-11-26.md")
        content = "Review PR #123"

        result = make_todo_id(path, content)

        assert len(result) == 8
        assert result.isalnum()

    def test_deterministic(self):
        path = Path("daily/2025/Nov/2025-11-26.md")
        content = "Same todo"

        result1 = make_todo_id(path, content)
        result2 = make_todo_id(path, content)

        assert result1 == result2

    def test_different_path(self):
        content = "Same content"

        result1 = make_todo_id(Path("file1.md"), content)
        result2 = make_todo_id(Path("file2.md"), content)

        assert result1 != result2

    def test_different_content(self):
        path = Path("file.md")

        result1 = make_todo_id(path, "Content 1")
        result2 = make_todo_id(path, "Content 2")

        assert result1 != result2

    def test_cross_platform_consistency(self):
        # Same path represented differently should produce same ID
        path_unix = Path("folder/subfolder/file.md")

        result1 = make_todo_id(path_unix, "content")

        # Simulate Windows path normalization
        path_str = "folder\\subfolder\\file.md"
        normalized = path_str.replace("\\", "/")
        combined = f"{normalized}:content"
        result2 = hash_content(combined)

        assert result1 == result2


class TestMakeNoteHash:
    """Tests for make_note_hash function."""

    def test_generates_hash(self):
        content = "# My Note\n\nSome content here."

        result = make_note_hash(content)

        assert len(result) == 8

    def test_deterministic(self):
        content = "Same content"

        result1 = make_note_hash(content)
        result2 = make_note_hash(content)

        assert result1 == result2

    def test_different_content(self):
        result1 = make_note_hash("Content version 1")
        result2 = make_note_hash("Content version 2")

        assert result1 != result2

    def test_detects_changes(self):
        original = "Original content"
        modified = "Original content modified"

        hash1 = make_note_hash(original)
        hash2 = make_note_hash(modified)

        assert hash1 != hash2


class TestMakeAttachmentId:
    """Tests for make_attachment_id function."""

    def test_generates_id(self):
        result = make_attachment_id(
            path="/path/to/file.pdf",
            parent_type="note",
            parent_id="abc12345"
        )

        assert len(result) == 8

    def test_deterministic(self):
        result1 = make_attachment_id("file.pdf", "note", "id123")
        result2 = make_attachment_id("file.pdf", "note", "id123")

        assert result1 == result2

    def test_different_paths(self):
        result1 = make_attachment_id("file1.pdf", "note", "id123")
        result2 = make_attachment_id("file2.pdf", "note", "id123")

        assert result1 != result2

    def test_different_parent_type(self):
        result1 = make_attachment_id("file.pdf", "note", "id123")
        result2 = make_attachment_id("file.pdf", "todo", "id123")

        assert result1 != result2

    def test_different_parent_id(self):
        result1 = make_attachment_id("file.pdf", "note", "id123")
        result2 = make_attachment_id("file.pdf", "note", "id456")

        assert result1 != result2

    def test_url_attachment(self):
        result = make_attachment_id(
            path="https://example.com/doc.pdf",
            parent_type="todo",
            parent_id="todo123"
        )

        assert len(result) == 8
