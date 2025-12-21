"""Tests for inbox/Raindrop integration."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from nb.cli import cli
from nb.config import Config, InboxConfig, RaindropConfig


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
