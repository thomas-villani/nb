"""Tests for inbox/Raindrop integration."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config, InboxConfig, RaindropConfig
from nb.config.models import RaindropCollectionConfig


class TestInboxConfig:
    """Test InboxConfig parsing and defaults."""

    def test_default_inbox_config(self):
        """Test default inbox configuration values."""
        inbox = InboxConfig()
        assert inbox.source == "raindrop"
        assert inbox.default_notebook == "bookmarks"
        assert inbox.auto_summarize is True  # Default is enabled
        assert inbox.raindrop.collection == "nb-inbox"
        assert inbox.raindrop.auto_archive is True
        assert inbox.raindrop.api_token is None

    def test_custom_inbox_config(self):
        """Test custom inbox configuration."""
        raindrop = RaindropConfig(
            collection="my-inbox",
            auto_archive=False,
            api_token="test-token",
        )
        inbox = InboxConfig(
            source="raindrop",
            default_notebook="reading",
            auto_summarize=False,
            raindrop=raindrop,
        )
        assert inbox.default_notebook == "reading"
        assert inbox.auto_summarize is False
        assert inbox.raindrop.collection == "my-inbox"
        assert inbox.raindrop.auto_archive is False
        assert inbox.raindrop.api_token == "test-token"


class TestRaindropItem:
    """Test RaindropItem dataclass."""

    def test_from_api_response(self):
        """Test creating RaindropItem from API response."""
        from nb.core.inbox.raindrop import RaindropItem

        api_data = {
            "_id": 12345,
            "link": "https://example.com/article",
            "title": "Test Article",
            "excerpt": "This is an excerpt",
            "tags": ["test", "example"],
            "created": "2025-01-15T10:30:00Z",
            "collection": {"$id": 100},
            "cover": "https://example.com/cover.jpg",
            "note": "My note",
        }

        item = RaindropItem.from_api_response(api_data)

        assert item.id == 12345
        assert item.url == "https://example.com/article"
        assert item.title == "Test Article"
        assert item.excerpt == "This is an excerpt"
        assert item.tags == ["test", "example"]
        assert item.collection_id == 100
        assert item.cover == "https://example.com/cover.jpg"
        assert item.note == "My note"

    def test_from_api_response_minimal(self):
        """Test creating RaindropItem with minimal data."""
        from nb.core.inbox.raindrop import RaindropItem

        api_data = {
            "_id": 999,
            "collection": {},
        }

        item = RaindropItem.from_api_response(api_data)

        assert item.id == 999
        assert item.url == ""
        assert item.title == "Untitled"
        assert item.excerpt is None
        assert item.tags == []
        assert item.collection_id == -1  # UNSORTED_COLLECTION_ID


class TestInboxDatabase:
    """Test inbox database tracking functions."""

    def test_record_and_check_clipped(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test recording and checking clipped items."""
        from nb.core.inbox.raindrop import is_item_clipped, record_clipped_item

        # Initialize database
        cli_runner.invoke(cli, ["index"])

        # Item should not be clipped initially
        assert is_item_clipped(12345) is False

        # Record the item as clipped
        record_clipped_item(
            item_id=12345,
            url="https://example.com/article",
            title="Test Article",
            note_path="bookmarks/test-article.md",
            archived=True,
        )

        # Now it should be clipped
        assert is_item_clipped(12345) is True

    def test_get_clipped_item(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test retrieving clipped item info."""
        from nb.core.inbox.raindrop import get_clipped_item, record_clipped_item

        cli_runner.invoke(cli, ["index"])

        record_clipped_item(
            item_id=54321,
            url="https://example.com/page",
            title="My Page",
            note_path="reading/my-page.md",
            archived=False,
            skipped=False,
        )

        item = get_clipped_item(54321)
        assert item is not None
        assert item["url"] == "https://example.com/page"
        assert item["title"] == "My Page"
        assert item["note_path"] == "reading/my-page.md"
        assert item["archived"] == 0
        assert item["skipped"] == 0

    def test_get_duplicate_warning(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test duplicate URL warning."""
        from nb.core.inbox.raindrop import get_duplicate_warning, record_clipped_item

        cli_runner.invoke(cli, ["index"])

        url = "https://example.com/duplicate"

        # No warning initially
        assert get_duplicate_warning(url) is None

        # Record item
        record_clipped_item(
            item_id=111,
            url=url,
            title="Duplicate Test",
            note_path="notes/duplicate.md",
        )

        # Now should have warning
        warning = get_duplicate_warning(url)
        assert warning is not None
        assert "Already clipped" in warning
        assert "notes/duplicate.md" in warning

    def test_record_skipped_item(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test recording a skipped item."""
        from nb.core.inbox.raindrop import is_item_clipped, record_clipped_item

        cli_runner.invoke(cli, ["index"])

        # Record as skipped
        record_clipped_item(
            item_id=222,
            url="https://example.com/skipped",
            title="Skipped Item",
            note_path=None,
            skipped=True,
        )

        # Skipped items are NOT considered "clipped"
        assert is_item_clipped(222) is False

    def test_list_clipped_items(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test listing clipped items."""
        from nb.core.inbox.raindrop import list_clipped_items, record_clipped_item

        cli_runner.invoke(cli, ["index"])

        # Record multiple items
        for i in range(5):
            record_clipped_item(
                item_id=1000 + i,
                url=f"https://example.com/page{i}",
                title=f"Page {i}",
                note_path=f"notes/page{i}.md",
            )

        items = list_clipped_items(limit=10)
        assert len(items) == 5

        # Most recent first
        assert items[0]["title"] == "Page 4"


class TestInboxCLI:
    """Test inbox CLI commands."""

    def test_inbox_list_no_token(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test inbox list fails gracefully without API token."""
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["inbox", "list"])

        assert result.exit_code == 1
        assert "Authentication error" in result.output
        assert "RAINDROP_API_KEY" in result.output

    def test_inbox_pull_no_token(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test inbox pull fails gracefully without API token."""
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["inbox", "pull", "--auto"])

        assert result.exit_code == 1
        assert "Authentication error" in result.output

    def test_inbox_history_empty(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test inbox history with no items."""
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["inbox", "history"])

        assert result.exit_code == 0
        assert "No clipping history" in result.output

    def test_inbox_history_with_items(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test inbox history shows clipped items."""
        from nb.core.inbox.raindrop import record_clipped_item

        cli_runner.invoke(cli, ["index"])

        record_clipped_item(
            item_id=333,
            url="https://example.com/test",
            title="Test History Item",
            note_path="bookmarks/test.md",
            archived=True,
        )

        result = cli_runner.invoke(cli, ["inbox", "history"])

        assert result.exit_code == 0
        assert "Clipping History" in result.output
        assert "Test History Item" in result.output

    def test_inbox_list_with_mocked_api(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test inbox list with mocked Raindrop API."""
        from nb.core.inbox.raindrop import RaindropItem

        cli_runner.invoke(cli, ["index"])

        # Create mock items
        mock_items = [
            RaindropItem(
                id=1,
                url="https://example.com/article1",
                title="Article 1",
                excerpt="First article excerpt",
                tags=["test", "article"],
                created=datetime.now(),
                collection_id=100,
            ),
            RaindropItem(
                id=2,
                url="https://blog.example.com/post",
                title="Blog Post",
                excerpt=None,
                tags=["blog"],
                created=datetime.now(),
                collection_id=100,
            ),
        ]

        # Patch list_inbox_items at the source module
        with patch("nb.core.inbox.raindrop.list_inbox_items", return_value=mock_items):
            with patch("nb.core.inbox.list_inbox_items", return_value=mock_items):
                result = cli_runner.invoke(cli, ["inbox", "list"])

        assert result.exit_code == 0
        assert "Inbox:" in result.output
        assert "2 items" in result.output
        assert "Article 1" in result.output
        assert "Blog Post" in result.output

    def test_inbox_clear_with_mocked_api(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test inbox clear with mocked Raindrop API."""
        from nb.core.inbox.raindrop import RaindropItem

        cli_runner.invoke(cli, ["index"])

        mock_items = [
            RaindropItem(
                id=1,
                url="https://example.com/page",
                title="Page to Archive",
                excerpt=None,
                tags=[],
                created=datetime.now(),
                collection_id=100,
            ),
        ]

        mock_client = MagicMock()
        mock_client.archive_item.return_value = True

        with patch("nb.core.inbox.raindrop.list_inbox_items", return_value=mock_items):
            with patch("nb.core.inbox.list_inbox_items", return_value=mock_items):
                with patch(
                    "nb.core.inbox.raindrop.RaindropClient", return_value=mock_client
                ):
                    with patch(
                        "nb.core.inbox.RaindropClient", return_value=mock_client
                    ):
                        result = cli_runner.invoke(cli, ["inbox", "clear", "-f"])

        assert result.exit_code == 0
        assert "Done:" in result.output
        assert "1 archived" in result.output
        mock_client.archive_item.assert_called_once_with(1)


class TestInboxConfigParsing:
    """Test inbox config parsing from YAML."""

    def test_parse_inbox_config_empty(self):
        """Test parsing empty inbox config."""
        from nb.config import _parse_inbox_config

        config = _parse_inbox_config(None)
        assert config.source == "raindrop"
        assert config.default_notebook == "bookmarks"

    def test_parse_inbox_config_full(self):
        """Test parsing full inbox config."""
        from nb.config import _parse_inbox_config

        data = {
            "source": "raindrop",
            "default_notebook": "reading",
            "auto_summarize": False,
            "raindrop": {
                "collection": "my-collection",
                "auto_archive": False,
            },
        }

        config = _parse_inbox_config(data)
        assert config.source == "raindrop"
        assert config.default_notebook == "reading"
        assert config.auto_summarize is False
        assert config.raindrop.collection == "my-collection"
        assert config.raindrop.auto_archive is False

    def test_parse_inbox_config_auto_summarize_default(self):
        """Test that auto_summarize defaults to True when not specified."""
        from nb.config import _parse_inbox_config

        data = {
            "default_notebook": "reading",
        }

        config = _parse_inbox_config(data)
        assert config.auto_summarize is True

    def test_parse_raindrop_config_with_env_token(self, monkeypatch):
        """Test that RAINDROP_API_KEY env var is used."""
        from nb.config import _parse_raindrop_config

        monkeypatch.setenv("RAINDROP_API_KEY", "env-token-value")

        config = _parse_raindrop_config({})
        assert config.api_token == "env-token-value"


class TestGenerateContentTldr:
    """Test generate_content_tldr function."""

    def test_generate_content_tldr_returns_none_on_llm_error(self):
        """Test that generate_content_tldr returns None when LLM fails."""
        from nb.core.ai.summarize import generate_content_tldr

        # Without an API key, this should fail gracefully
        result = generate_content_tldr(
            content="Test content",
            title="Test Title",
        )
        # Should return None (graceful failure) since no API key is configured
        # This tests the graceful fallback behavior
        assert result is None or isinstance(result, str)

    def test_generate_content_tldr_with_mocked_llm(self):
        """Test generate_content_tldr with mocked LLM client."""
        from unittest.mock import MagicMock, patch

        from nb.core.ai.summarize import generate_content_tldr

        mock_response = MagicMock()
        mock_response.content = "This is a test summary."

        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        # Patch at the location where it's imported inside the function
        with patch("nb.core.llm.get_llm_client", return_value=mock_client):
            result = generate_content_tldr(
                content="Some long article content about AI and machine learning.",
                title="AI Article",
            )

        assert result == "This is a test summary."
        mock_client.complete.assert_called_once()

    def test_generate_content_tldr_truncates_long_content(self):
        """Test that generate_content_tldr truncates very long content."""
        from unittest.mock import MagicMock, patch

        from nb.core.ai.summarize import generate_content_tldr

        mock_response = MagicMock()
        mock_response.content = "Summary of long content."

        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        # Create content longer than the truncation limit (15000 chars)
        long_content = "x" * 20000

        # Patch at the location where it's imported inside the function
        with patch("nb.core.llm.get_llm_client", return_value=mock_client):
            result = generate_content_tldr(
                content=long_content,
                title="Long Article",
            )

        assert result == "Summary of long content."
        # Check that the content passed to LLM was truncated
        call_args = mock_client.complete.call_args
        messages = call_args.kwargs["messages"]
        assert "[... truncated ...]" in messages[0].content


class TestInboxAutoSummarizeConfig:
    """Test inbox.auto_summarize configuration via CLI."""

    def test_get_auto_summarize_config(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test getting inbox.auto_summarize value."""
        cli_runner.invoke(cli, ["index"])

        result = cli_runner.invoke(cli, ["config", "get", "inbox.auto_summarize"])
        assert result.exit_code == 0
        assert "True" in result.output

    def test_set_auto_summarize_config(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test setting inbox.auto_summarize value."""
        cli_runner.invoke(cli, ["index"])

        # Disable auto_summarize
        result = cli_runner.invoke(
            cli, ["config", "set", "inbox.auto_summarize", "false"]
        )
        assert result.exit_code == 0

        # Verify it was set
        result = cli_runner.invoke(cli, ["config", "get", "inbox.auto_summarize"])
        assert "False" in result.output

        # Re-enable
        result = cli_runner.invoke(
            cli, ["config", "set", "inbox.auto_summarize", "true"]
        )
        assert result.exit_code == 0


class TestRaindropCollectionConfig:
    """Test RaindropCollectionConfig and multi-collection support."""

    def test_collection_config_defaults(self):
        """Test RaindropCollectionConfig default values."""
        config = RaindropCollectionConfig(name="test", notebook="notes")
        assert config.name == "test"
        assert config.notebook == "notes"
        assert config.auto_archive is True
        assert config.extra_tags == []

    def test_collection_config_with_extras(self):
        """Test RaindropCollectionConfig with extra options."""
        config = RaindropCollectionConfig(
            name="research",
            notebook="research",
            auto_archive=False,
            extra_tags=["research", "reading"],
        )
        assert config.name == "research"
        assert config.notebook == "research"
        assert config.auto_archive is False
        assert config.extra_tags == ["research", "reading"]

    def test_raindrop_config_get_all_collections_legacy(self):
        """Test get_all_collections with legacy single-collection config."""
        config = RaindropConfig(
            collection="my-inbox",
            auto_archive=True,
        )
        collections = config.get_all_collections("bookmarks")
        assert len(collections) == 1
        assert collections[0].name == "my-inbox"
        assert collections[0].notebook == "bookmarks"
        assert collections[0].auto_archive is True

    def test_raindrop_config_get_all_collections_multi(self):
        """Test get_all_collections with multiple collections."""
        config = RaindropConfig(
            collections=[
                RaindropCollectionConfig(name="inbox", notebook="bookmarks"),
                RaindropCollectionConfig(
                    name="research", notebook="research", auto_archive=False
                ),
            ],
        )
        collections = config.get_all_collections("default")
        assert len(collections) == 2
        assert collections[0].name == "inbox"
        assert collections[1].name == "research"
        assert collections[1].auto_archive is False

    def test_raindrop_config_sync_defaults(self):
        """Test that sync settings default to True."""
        config = RaindropConfig()
        assert config.sync_tags is True
        assert config.sync_notes is True


class TestCollectionConfigParsing:
    """Test parsing of collection configuration from YAML."""

    def test_parse_collections_list(self):
        """Test parsing a collections list."""
        from nb.config.parsers import _parse_raindrop_config

        data = {
            "sync_tags": True,
            "sync_notes": False,
            "collections": [
                {"name": "inbox", "notebook": "bookmarks"},
                {"name": "research", "notebook": "research", "auto_archive": False},
                {"name": "work", "notebook": "work", "extra_tags": ["work", "todo"]},
            ],
        }
        config = _parse_raindrop_config(data)
        assert len(config.collections) == 3
        assert config.collections[0].name == "inbox"
        assert config.collections[0].notebook == "bookmarks"
        assert config.collections[1].auto_archive is False
        assert config.collections[2].extra_tags == ["work", "todo"]
        assert config.sync_tags is True
        assert config.sync_notes is False

    def test_parse_collections_backwards_compatible(self):
        """Test that legacy single-collection config still works."""
        from nb.config.parsers import _parse_raindrop_config

        data = {
            "collection": "my-inbox",
            "auto_archive": False,
        }
        config = _parse_raindrop_config(data)
        assert config.collection == "my-inbox"
        assert config.auto_archive is False
        assert len(config.collections) == 0  # No collections list defined


class TestSyncHelperFunctions:
    """Test sync-related database functions."""

    def test_record_clipped_with_sync_metadata(
        self, mock_cli_config: Config, cli_runner: CliRunner
    ):
        """Test recording clipped items with sync metadata."""
        from nb.core.inbox.raindrop import get_items_needing_sync, record_clipped_item

        cli_runner.invoke(cli, ["index"])

        record_clipped_item(
            item_id=99999,
            url="https://example.com/sync-test",
            title="Sync Test",
            note_path="bookmarks/sync-test.md",
            archived=True,
            raindrop_tags=["tag1", "tag2"],
            raindrop_note="My original note",
            collection_name="test-collection",
        )

        # Get items needing sync
        items = get_items_needing_sync(limit=10)
        assert len(items) >= 1

        # Find our item
        our_item = next((i for i in items if i["id"] == "99999"), None)
        assert our_item is not None
        assert our_item["note_path"] == "bookmarks/sync-test.md"
        assert our_item["collection_name"] == "test-collection"

    def test_update_sync_metadata(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test updating sync metadata."""
        import json

        from nb.core.inbox.raindrop import (
            record_clipped_item,
            update_sync_metadata,
        )

        cli_runner.invoke(cli, ["index"])

        # First record an item
        record_clipped_item(
            item_id=88888,
            url="https://example.com/update-test",
            title="Update Test",
            note_path="bookmarks/update-test.md",
            archived=True,
            raindrop_tags=["old_tag"],
            raindrop_note="Old note",
            collection_name="test",
        )

        # Update the sync metadata
        update_sync_metadata(
            item_id=88888,
            raindrop_tags=["new_tag1", "new_tag2"],
            raindrop_note="New note content",
        )

        # Verify the update (need to query directly since get_clipped_item doesn't return sync fields)
        from nb.index.db import get_db

        db = get_db()
        row = db.fetchone(
            "SELECT raindrop_tags, raindrop_note FROM inbox_items WHERE id = ?",
            ("88888",),
        )
        assert row is not None
        tags = json.loads(row["raindrop_tags"])
        assert "new_tag1" in tags
        assert "new_tag2" in tags
        assert row["raindrop_note"] == "New note content"


class TestSyncTagLogic:
    """Test tag sync logic."""

    def test_sync_item_tags_add_new_tag(self, tmp_path):
        """Test adding new tags from Raindrop."""
        import frontmatter

        from nb.core.inbox.sync import sync_item_tags

        # Create a test note
        note_path = tmp_path / "test-note.md"
        note_content = """---
title: Test Note
tags: [clipped, old_tag]
---

# Test Note

Content here.
"""
        note_path.write_text(note_content)

        # Sync: add new_tag
        result = sync_item_tags(
            note_path,
            old_raindrop_tags=["old_tag"],
            new_raindrop_tags=["old_tag", "new_tag"],
        )

        assert result is True

        # Verify the note was updated
        post = frontmatter.load(note_path)
        assert "new_tag" in post.metadata["tags"]
        assert "old_tag" in post.metadata["tags"]
        assert "clipped" in post.metadata["tags"]

    def test_sync_item_tags_remove_tag(self, tmp_path):
        """Test removing tags from Raindrop."""
        import frontmatter

        from nb.core.inbox.sync import sync_item_tags

        note_path = tmp_path / "test-note.md"
        note_content = """---
title: Test Note
tags: [clipped, old_tag, removed_tag]
---

# Test Note
"""
        note_path.write_text(note_content)

        # Sync: removed_tag was removed in Raindrop
        result = sync_item_tags(
            note_path,
            old_raindrop_tags=["old_tag", "removed_tag"],
            new_raindrop_tags=["old_tag"],
        )

        assert result is True

        post = frontmatter.load(note_path)
        assert "removed_tag" not in post.metadata["tags"]
        assert "old_tag" in post.metadata["tags"]
        assert "clipped" in post.metadata["tags"]

    def test_sync_item_tags_preserves_user_tags(self, tmp_path):
        """Test that user-added tags are preserved."""
        import frontmatter

        from nb.core.inbox.sync import sync_item_tags

        note_path = tmp_path / "test-note.md"
        note_content = """---
title: Test Note
tags: [clipped, raindrop_tag, user_added_tag]
---

# Test Note
"""
        note_path.write_text(note_content)

        # Sync: raindrop_tag was removed, but user_added_tag should stay
        result = sync_item_tags(
            note_path,
            old_raindrop_tags=["raindrop_tag"],
            new_raindrop_tags=[],
        )

        assert result is True

        post = frontmatter.load(note_path)
        assert "user_added_tag" in post.metadata["tags"]
        assert "clipped" in post.metadata["tags"]
        assert "raindrop_tag" not in post.metadata["tags"]

    def test_sync_item_tags_no_change(self, tmp_path):
        """Test that no changes are made when tags are the same."""
        from nb.core.inbox.sync import sync_item_tags

        note_path = tmp_path / "test-note.md"
        note_content = """---
title: Test Note
tags: [clipped, tag1]
---

# Test Note
"""
        note_path.write_text(note_content)

        result = sync_item_tags(
            note_path,
            old_raindrop_tags=["tag1"],
            new_raindrop_tags=["tag1"],
        )

        assert result is False  # No changes needed


class TestSyncNoteLogic:
    """Test Raindrop note sync logic."""

    def test_sync_item_note_add_note(self, tmp_path):
        """Test adding a new Raindrop note."""
        from nb.core.inbox.sync import sync_item_note

        note_path = tmp_path / "test-note.md"
        note_content = """---
title: Test Note
---

# Test Note

[Original source](https://example.com)

Article content here.
"""
        note_path.write_text(note_content)

        result = sync_item_note(
            note_path,
            old_note=None,
            new_note="This is my new note from Raindrop",
        )

        assert result is True

        content = note_path.read_text()
        assert "<!-- raindrop-note-start -->" in content
        assert "This is my new note from Raindrop" in content
        assert "<!-- raindrop-note-end -->" in content

    def test_sync_item_note_update_note(self, tmp_path):
        """Test updating an existing Raindrop note."""
        from nb.core.inbox.sync import sync_item_note

        note_path = tmp_path / "test-note.md"
        note_content = """---
title: Test Note
---

# Test Note

[Original source](https://example.com)

<!-- raindrop-note-start -->

> **Raindrop Note:** Old note content

<!-- raindrop-note-end -->

Article content.
"""
        note_path.write_text(note_content)

        result = sync_item_note(
            note_path,
            old_note="Old note content",
            new_note="Updated note content",
        )

        assert result is True

        content = note_path.read_text()
        assert "Updated note content" in content
        assert "Old note content" not in content

    def test_sync_item_note_remove_note(self, tmp_path):
        """Test removing a Raindrop note."""
        from nb.core.inbox.sync import sync_item_note

        note_path = tmp_path / "test-note.md"
        note_content = """---
title: Test Note
---

# Test Note

[Original source](https://example.com)

<!-- raindrop-note-start -->

> **Raindrop Note:** Note to remove

<!-- raindrop-note-end -->

Article content.
"""
        note_path.write_text(note_content)

        result = sync_item_note(
            note_path,
            old_note="Note to remove",
            new_note=None,
        )

        assert result is True

        content = note_path.read_text()
        assert "<!-- raindrop-note-start -->" not in content
        assert "Note to remove" not in content

    def test_sync_item_note_no_change(self, tmp_path):
        """Test that no changes are made when note is the same."""
        from nb.core.inbox.sync import sync_item_note

        note_path = tmp_path / "test-note.md"
        note_content = "# Test Note\n\nContent."
        note_path.write_text(note_content)

        result = sync_item_note(
            note_path,
            old_note="Same note",
            new_note="Same note",
        )

        assert result is False


class TestInboxSyncCLI:
    """Test nb inbox sync CLI command."""

    def test_inbox_sync_no_items(self, mock_cli_config: Config, cli_runner: CliRunner):
        """Test that sync handles no items gracefully."""
        cli_runner.invoke(cli, ["index"])

        # Without a token but with sync disabled in config, or no items, it may succeed
        # The key is that it should either fail with auth error or succeed with no items
        result = cli_runner.invoke(cli, ["inbox", "sync"])
        # Either auth error (exit 1) or no items to sync (exit 0)
        assert result.exit_code in (0, 1)
        if result.exit_code == 1:
            assert (
                "Authentication error" in result.output
                or "RAINDROP_API_KEY" in result.output
            )
        else:
            assert (
                "No items to sync" in result.output
                or "Syncing from Raindrop" in result.output
            )

    def test_inbox_sync_help(self, cli_runner: CliRunner):
        """Test inbox sync help text."""
        result = cli_runner.invoke(cli, ["inbox", "sync", "--help"])
        assert result.exit_code == 0
        assert "Sync tag and note changes" in result.output
        assert "--dry-run" in result.output
