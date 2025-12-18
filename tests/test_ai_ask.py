"""Tests for nb.core.ai.ask module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nb.core.ai.ask import (
    AnswerResult,
    NoteReference,
    RetrievedContext,
    _build_context_prompt,
    _contexts_to_references,
    _estimate_tokens,
    _get_model_context_limit,
    _truncate_contexts_to_limit,
    ask_notes,
)


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_estimate_tokens_empty(self):
        assert _estimate_tokens("") == 0

    def test_estimate_tokens_short(self):
        # 12 chars / 3 = 4 tokens
        assert _estimate_tokens("Hello world!") == 4

    def test_estimate_tokens_longer(self):
        text = "a" * 300  # 300 chars / 3 = 100 tokens
        assert _estimate_tokens(text) == 100


class TestGetModelContextLimit:
    """Tests for model context limit lookup."""

    def test_known_anthropic_model(self):
        limit = _get_model_context_limit("claude-sonnet-4-20250514")
        assert limit == 180000

    def test_known_openai_model(self):
        limit = _get_model_context_limit("gpt-4o")
        assert limit == 120000

    def test_unknown_model_returns_default(self):
        limit = _get_model_context_limit("unknown-model-xyz")
        assert limit == 30000  # DEFAULT_CONTEXT_LIMIT

    def test_partial_match(self):
        # Should match via partial match
        limit = _get_model_context_limit("claude-3-5-sonnet-latest")
        assert limit == 180000


class TestRetrievedContext:
    """Tests for RetrievedContext dataclass."""

    def test_create_context(self):
        ctx = RetrievedContext(
            path="notes/test.md",
            title="Test Note",
            content="Some content",
            score=0.9,
            notebook="daily",
            date="2025-01-01",
            chunk_count=2,
        )

        assert ctx.path == "notes/test.md"
        assert ctx.title == "Test Note"
        assert ctx.content == "Some content"
        assert ctx.score == 0.9
        assert ctx.notebook == "daily"
        assert ctx.chunk_count == 2


class TestNoteReference:
    """Tests for NoteReference dataclass."""

    def test_create_reference(self):
        ref = NoteReference(
            path="notes/test.md",
            title="Test",
            snippet="Short snippet...",
            score=0.8,
            notebook="work",
        )

        assert ref.path == "notes/test.md"
        assert ref.score == 0.8


class TestAnswerResult:
    """Tests for AnswerResult dataclass."""

    def test_create_result(self):
        result = AnswerResult(
            answer="The answer is 42.",
            sources=[
                NoteReference(path="test.md", title="Test", snippet="...", score=0.9)
            ],
            input_tokens=100,
            output_tokens=50,
        )

        assert result.answer == "The answer is 42."
        assert len(result.sources) == 1
        assert result.input_tokens == 100


class TestTruncateContextsToLimit:
    """Tests for context truncation."""

    def test_contexts_fit_within_limit(self):
        contexts = [
            RetrievedContext(
                path="test1.md", title="Test 1", content="Short", score=0.9
            ),
            RetrievedContext(
                path="test2.md", title="Test 2", content="Also short", score=0.8
            ),
        ]

        result = _truncate_contexts_to_limit(
            contexts,
            max_tokens=10000,
            question="What?",
            system_prompt="Be helpful",
        )

        assert len(result) == 2

    def test_truncates_large_context(self):
        # Create a very long context
        long_content = "x" * 30000  # ~10000 tokens

        contexts = [
            RetrievedContext(
                path="test1.md",
                title="Test 1",
                content=long_content,
                score=0.9,
            ),
        ]

        result = _truncate_contexts_to_limit(
            contexts,
            max_tokens=5000,  # Less than content needs
            question="What?",
            system_prompt="Be helpful",
        )

        assert len(result) == 1
        # Content should be truncated
        assert len(result[0].content) < len(long_content)
        assert "[... content truncated ...]" in result[0].content

    def test_returns_empty_when_no_room(self):
        contexts = [
            RetrievedContext(
                path="test.md", title="Test", content="Content", score=0.9
            ),
        ]

        # Very small limit that can't fit anything
        result = _truncate_contexts_to_limit(
            contexts,
            max_tokens=10,
            question="Long question that takes up space",
            system_prompt="Long system prompt",
        )

        assert len(result) == 0


class TestBuildContextPrompt:
    """Tests for prompt building."""

    def test_builds_prompt_with_contexts(self):
        contexts = [
            RetrievedContext(
                path="notes/test.md",
                title="Test Note",
                content="Some relevant content",
                score=0.9,
                notebook="work",
                date="2025-01-15",
            ),
        ]

        prompt, used = _build_context_prompt(
            question="What is the answer?",
            contexts=contexts,
        )

        assert "notes/test.md" in prompt
        assert "Test Note" in prompt
        assert "Some relevant content" in prompt
        assert "What is the answer?" in prompt
        assert len(used) == 1

    def test_includes_metadata_in_prompt(self):
        contexts = [
            RetrievedContext(
                path="test.md",
                title="Test",
                content="Content",
                score=0.9,
                notebook="daily",
                date="2025-01-01",
            ),
        ]

        prompt, _ = _build_context_prompt("Question?", contexts)

        assert "notebook: daily" in prompt
        assert "date: 2025-01-01" in prompt


class TestContextsToReferences:
    """Tests for converting contexts to references."""

    def test_converts_contexts(self):
        contexts = [
            RetrievedContext(
                path="test.md",
                title="Test",
                content="This is a longer content that should be truncated in the snippet",
                score=0.9,
                notebook="work",
            ),
        ]

        refs = _contexts_to_references(contexts)

        assert len(refs) == 1
        assert refs[0].path == "test.md"
        assert refs[0].title == "Test"
        assert refs[0].score == 0.9
        assert refs[0].notebook == "work"

    def test_truncates_long_snippets(self):
        long_content = "x" * 500

        contexts = [
            RetrievedContext(
                path="test.md",
                title="Test",
                content=long_content,
                score=0.9,
            ),
        ]

        refs = _contexts_to_references(contexts)

        # Should be truncated to 200 chars + "..."
        assert len(refs[0].snippet) == 203
        assert refs[0].snippet.endswith("...")


class TestAskNotes:
    """Tests for ask_notes function with mocked dependencies."""

    @pytest.fixture
    def mock_llm_response(self):
        """Mock LLM response."""
        from nb.core.llm import LLMResponse

        return LLMResponse(
            content="The answer based on your notes is: 42.",
            model="claude-test",
            input_tokens=100,
            output_tokens=50,
        )

    @pytest.fixture
    def mock_search_results(self):
        """Mock search results."""

        class MockResult:
            def __init__(self):
                self.content = "Relevant note content about the topic."
                self.score = 0.85
                self.metadata = {
                    "path": "work/project.md",
                    "title": "Project Notes",
                    "notebook": "work",
                    "date": "2025-01-15",
                }

        return [MockResult()]

    def test_ask_notes_returns_answer(
        self, mock_llm_response, mock_search_results, tmp_path
    ):
        """Test that ask_notes returns an answer."""
        from nb.config import Config, LLMConfig, NotebookConfig

        # Create mock config
        mock_config = Config(
            notes_root=tmp_path,
            editor="echo",
            notebooks=[NotebookConfig(name="work")],
            llm=LLMConfig(provider="anthropic", api_key="test-key"),
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_config),
            patch("nb.core.ai.ask.get_search") as mock_get_search,
            patch("nb.core.ai.ask.get_llm_client") as mock_get_llm,
        ):
            # Setup search mock
            mock_search = MagicMock()
            mock_search.db.query.return_value = mock_search_results
            mock_get_search.return_value = mock_search

            # Setup LLM mock
            mock_client = MagicMock()
            mock_client.complete.return_value = mock_llm_response
            mock_get_llm.return_value = mock_client

            result = ask_notes("What is the answer?")

            assert isinstance(result, AnswerResult)
            assert "42" in result.answer
            assert result.input_tokens == 100
            assert result.output_tokens == 50

    def test_ask_notes_with_notebook_filter(
        self, mock_llm_response, mock_search_results, tmp_path
    ):
        """Test that notebook filter is passed to search."""
        from nb.config import Config, LLMConfig, NotebookConfig

        mock_config = Config(
            notes_root=tmp_path,
            editor="echo",
            notebooks=[NotebookConfig(name="work")],
            llm=LLMConfig(provider="anthropic", api_key="test-key"),
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_config),
            patch("nb.core.ai.ask.get_search") as mock_get_search,
            patch("nb.core.ai.ask.get_llm_client") as mock_get_llm,
        ):
            mock_search = MagicMock()
            mock_search.db.query.return_value = mock_search_results
            mock_get_search.return_value = mock_search

            mock_client = MagicMock()
            mock_client.complete.return_value = mock_llm_response
            mock_get_llm.return_value = mock_client

            ask_notes("Question?", notebook="work")

            # Verify search was called with notebook filter
            call_kwargs = mock_search.db.query.call_args.kwargs
            assert call_kwargs["filters"]["notebook"] == "work"

    def test_ask_notes_no_results(self, tmp_path):
        """Test that empty results return appropriate message."""
        from nb.config import Config, LLMConfig, NotebookConfig

        mock_config = Config(
            notes_root=tmp_path,
            editor="echo",
            notebooks=[NotebookConfig(name="work")],
            llm=LLMConfig(provider="anthropic", api_key="test-key"),
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_config),
            patch("nb.core.ai.ask.get_search") as mock_get_search,
        ):
            mock_search = MagicMock()
            mock_search.db.query.return_value = []  # No results
            mock_get_search.return_value = mock_search

            result = ask_notes("Unknown topic?")

            assert "couldn't find" in result.answer.lower()
            assert len(result.sources) == 0

    def test_ask_notes_with_specific_note(self, mock_llm_response, tmp_path):
        """Test asking about a specific note."""
        from nb.config import Config, LLMConfig, NotebookConfig

        # Create a test note
        note_path = tmp_path / "work" / "test.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("# Test Note\n\nThis is test content.")

        mock_config = Config(
            notes_root=tmp_path,
            editor="echo",
            notebooks=[NotebookConfig(name="work")],
            llm=LLMConfig(provider="anthropic", api_key="test-key"),
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_config),
            patch("nb.core.ai.ask.get_llm_client") as mock_get_llm,
        ):
            mock_client = MagicMock()
            mock_client.complete.return_value = mock_llm_response
            mock_get_llm.return_value = mock_client

            result = ask_notes(
                "What is in this note?",
                note_path=str(note_path),
            )

            assert isinstance(result, AnswerResult)
            # Should have one source (the specific note)
            assert len(result.sources) == 1

    def test_ask_notes_note_not_found(self, tmp_path):
        """Test error when specific note doesn't exist."""
        from nb.config import Config, LLMConfig, NotebookConfig

        mock_config = Config(
            notes_root=tmp_path,
            editor="echo",
            notebooks=[NotebookConfig(name="work")],
            llm=LLMConfig(provider="anthropic", api_key="test-key"),
        )

        with patch("nb.core.ai.ask.get_config", return_value=mock_config):
            with pytest.raises(ValueError, match="Note not found"):
                ask_notes(
                    "Question?",
                    note_path="nonexistent/note.md",
                )
