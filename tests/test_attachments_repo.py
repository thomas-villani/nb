"""Tests for attachment repository operations."""

from datetime import date
from pathlib import Path

from nb.index.attachments_repo import (
    delete_attachments_for_parent,
    extract_attachments_from_content,
    get_all_attachments,
    get_attachment_by_id,
    get_attachment_stats,
    query_attachments,
    upsert_attachment,
    upsert_attachments_batch,
)
from nb.models import Attachment


class TestUpsertAttachment:
    """Tests for upsert_attachment function."""

    def test_upsert_new_attachment(self, mock_config):
        """Test inserting a new attachment."""
        attachment = Attachment(
            id="test123",
            type="file",
            path="/path/to/file.pdf",
            title="Test File",
            added_date=date(2025, 1, 15),
            copied=False,
        )

        upsert_attachment(attachment, "note", "test-note-path")

        # Verify it was stored
        retrieved = get_attachment_by_id("test123")
        assert retrieved is not None
        assert retrieved.id == "test123"
        assert retrieved.type == "file"
        assert retrieved.path == "/path/to/file.pdf"
        assert retrieved.title == "Test File"
        assert retrieved.copied is False

    def test_upsert_updates_existing(self, mock_config):
        """Test that upsert updates an existing attachment."""
        attachment = Attachment(
            id="test123",
            type="file",
            path="/path/to/file.pdf",
            title="Original Title",
            added_date=date(2025, 1, 15),
            copied=False,
        )
        upsert_attachment(attachment, "note", "test-note-path")

        # Update with same ID
        updated = Attachment(
            id="test123",
            type="file",
            path="/path/to/file.pdf",
            title="Updated Title",
            added_date=date(2025, 1, 16),
            copied=True,
        )
        upsert_attachment(updated, "note", "test-note-path")

        # Verify update
        retrieved = get_attachment_by_id("test123")
        assert retrieved.title == "Updated Title"
        assert retrieved.copied is True


class TestUpsertAttachmentsBatch:
    """Tests for batch upsert."""

    def test_batch_upsert(self, mock_config):
        """Test batch upserting multiple attachments."""
        attachments = [
            (
                Attachment(id="a1", type="file", path="/file1.pdf"),
                "note",
                "note1",
            ),
            (
                Attachment(id="a2", type="url", path="https://example.com"),
                "todo",
                "todo1",
            ),
            (
                Attachment(id="a3", type="file", path="/file2.pdf"),
                "note",
                "note2",
            ),
        ]

        upsert_attachments_batch(attachments)

        # Verify all were inserted
        all_attachments = get_all_attachments()
        assert len(all_attachments) == 3


class TestDeleteAttachments:
    """Tests for delete functions."""

    def test_delete_attachments_for_parent(self, mock_config):
        """Test deleting attachments for a specific parent."""
        # Insert attachments for different parents
        upsert_attachment(
            Attachment(id="a1", type="file", path="/file1.pdf"),
            "note",
            "note1",
        )
        upsert_attachment(
            Attachment(id="a2", type="file", path="/file2.pdf"),
            "note",
            "note1",
        )
        upsert_attachment(
            Attachment(id="a3", type="file", path="/file3.pdf"),
            "note",
            "note2",
        )

        # Delete for note1
        delete_attachments_for_parent("note", "note1")

        # Verify only note2's attachment remains
        all_attachments = get_all_attachments()
        assert len(all_attachments) == 1
        assert all_attachments[0][0].id == "a3"


class TestQueryAttachments:
    """Tests for query functions."""

    def test_query_by_type(self, mock_config):
        """Test filtering by attachment type."""
        upsert_attachment(
            Attachment(id="a1", type="file", path="/file.pdf"),
            "note",
            "note1",
        )
        upsert_attachment(
            Attachment(id="a2", type="url", path="https://example.com"),
            "note",
            "note2",
        )

        files = query_attachments(attachment_type="file")
        assert len(files) == 1
        assert files[0][0].type == "file"

        urls = query_attachments(attachment_type="url")
        assert len(urls) == 1
        assert urls[0][0].type == "url"

    def test_query_by_parent_type(self, mock_config):
        """Test filtering by parent type."""
        upsert_attachment(
            Attachment(id="a1", type="file", path="/file.pdf"),
            "note",
            "note1",
        )
        upsert_attachment(
            Attachment(id="a2", type="file", path="/file2.pdf"),
            "todo",
            "todo1",
        )

        note_attachments = query_attachments(parent_type="note")
        assert len(note_attachments) == 1
        assert note_attachments[0][1] == "note"


class TestGetAttachmentStats:
    """Tests for stats function."""

    def test_stats_empty(self, mock_config):
        """Test stats with no attachments."""
        stats = get_attachment_stats()
        assert stats["total"] == 0
        assert stats["copied"] == 0
        assert stats["linked"] == 0

    def test_stats_with_data(self, mock_config):
        """Test stats with attachments."""
        upsert_attachment(
            Attachment(id="a1", type="file", path="/file.pdf", copied=True),
            "note",
            "note1",
        )
        upsert_attachment(
            Attachment(id="a2", type="url", path="https://example.com"),
            "note",
            "note2",
        )
        upsert_attachment(
            Attachment(id="a3", type="file", path="/file2.pdf", copied=False),
            "todo",
            "todo1",
        )

        stats = get_attachment_stats()
        assert stats["total"] == 3
        assert stats["by_type"].get("file", 0) == 2
        assert stats["by_type"].get("url", 0) == 1
        assert stats["by_parent_type"].get("note", 0) == 2
        assert stats["by_parent_type"].get("todo", 0) == 1
        assert stats["copied"] == 1
        assert stats["linked"] == 2


class TestExtractAttachmentsFromContent:
    """Tests for extraction from markdown content."""

    def test_extract_simple_attachment(self, mock_config):
        """Test extracting a simple @attach line."""
        content = """# Test Note

Some content here.

@attach: /path/to/file.pdf
"""
        attachments = extract_attachments_from_content(
            content,
            parent_type="note",
            parent_id="test-note",
            source_path=Path("/notes/test.md"),
        )

        assert len(attachments) == 1
        attachment, parent_type, parent_id = attachments[0]
        assert attachment.type == "file"
        assert attachment.path == "/path/to/file.pdf"

    def test_extract_attachment_with_title(self, mock_config):
        """Test extracting @attach with title."""
        content = '@attach: /path/to/file.pdf "My Document"'

        attachments = extract_attachments_from_content(
            content,
            parent_type="note",
            parent_id="test-note",
            source_path=Path("/notes/test.md"),
        )

        assert len(attachments) == 1
        assert attachments[0][0].title == "My Document"

    def test_extract_url_attachment(self, mock_config):
        """Test extracting URL attachments."""
        content = "@attach: https://example.com/doc"

        attachments = extract_attachments_from_content(
            content,
            parent_type="note",
            parent_id="test-note",
            source_path=Path("/notes/test.md"),
        )

        assert len(attachments) == 1
        assert attachments[0][0].type == "url"
        assert attachments[0][0].path == "https://example.com/doc"

    def test_extract_multiple_attachments(self, mock_config):
        """Test extracting multiple @attach lines."""
        content = """# Note with attachments

@attach: /file1.pdf
@attach: https://example.com
@attach: /file2.txt "Notes"
"""
        attachments = extract_attachments_from_content(
            content,
            parent_type="note",
            parent_id="test-note",
            source_path=Path("/notes/test.md"),
        )

        assert len(attachments) == 3

    def test_extract_indented_attachment(self, mock_config):
        """Test extracting indented @attach lines (for todos)."""
        content = """- [ ] My todo
  @attach: /related/file.pdf
"""
        attachments = extract_attachments_from_content(
            content,
            parent_type="todo",
            parent_id="test-todo",
            source_path=Path("/notes/test.md"),
        )

        assert len(attachments) == 1
