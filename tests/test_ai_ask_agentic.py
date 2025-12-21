"""Tests for nb.core.ai.ask_agentic module."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from nb.core.ai.ask import NoteReference, RetrievedContext
from nb.core.ai.ask_agentic import (
    AGENTIC_ASK_SYSTEM_PROMPT,
    AgenticAnswerResult,
    AgenticContext,
    _execute_get_project_stats,
    _execute_query_todos,
    _execute_read_note,
    _execute_search_notes,
    _format_tools_for_prompt,
    execute_ask_tool,
    get_ask_tools,
)
from nb.core.llm import ToolCall
from nb.models import Priority, Todo, TodoSource, TodoStatus


class TestGetAskTools:
    """Tests for tool definitions."""

    def test_all_tools_present(self):
        tools = get_ask_tools()
        names = {t.name for t in tools}

        assert "search_notes" in names
        assert "read_note" in names
        assert "query_todos" in names
        assert "get_project_stats" in names
        assert "complete_answer" in names

    def test_tool_count(self):
        tools = get_ask_tools()
        assert len(tools) == 5

    def test_tools_have_descriptions(self):
        tools = get_ask_tools()
        for tool in tools:
            assert tool.description
            assert len(tool.description) > 10

    def test_tools_have_valid_parameters(self):
        tools = get_ask_tools()
        for tool in tools:
            assert "type" in tool.parameters
            assert tool.parameters["type"] == "object"
            assert "properties" in tool.parameters


class TestFormatToolsForPrompt:
    """Tests for tool formatting in prompts."""

    def test_formats_all_tools(self):
        tools = get_ask_tools()
        formatted = _format_tools_for_prompt(tools)

        assert "search_notes" in formatted
        assert "query_todos" in formatted
        assert "get_project_stats" in formatted
        assert "complete_answer" in formatted

    def test_includes_descriptions(self):
        tools = get_ask_tools()
        formatted = _format_tools_for_prompt(tools)

        # Each line should have tool name and description
        lines = formatted.strip().split("\n")
        for line in lines:
            assert line.startswith("- ")
            assert ":" in line


class TestAgenticContext:
    """Tests for AgenticContext dataclass."""

    def test_create_context(self):
        ctx = AgenticContext()

        assert ctx.messages == []
        assert ctx.sources == []
        assert ctx.input_tokens == 0
        assert ctx.output_tokens == 0
        assert ctx.tool_calls_count == 0
        assert ctx.tools_used == []

    def test_context_with_values(self):
        ref = NoteReference(path="test.md", title="Test", snippet="...", score=0.9)
        ctx = AgenticContext(
            sources=[ref],
            input_tokens=100,
            output_tokens=50,
            tool_calls_count=2,
            tools_used=["search_notes", "query_todos"],
        )

        assert len(ctx.sources) == 1
        assert ctx.input_tokens == 100
        assert ctx.tool_calls_count == 2


class TestAgenticAnswerResult:
    """Tests for AgenticAnswerResult dataclass."""

    def test_create_result(self):
        result = AgenticAnswerResult(
            answer="The answer is 42.",
            sources=[],
            input_tokens=100,
            output_tokens=50,
            tool_calls=3,
            tools_used=["search_notes"],
        )

        assert result.answer == "The answer is 42."
        assert result.tool_calls == 3
        assert "search_notes" in result.tools_used


class TestExecuteSearchNotes:
    """Tests for search_notes tool execution."""

    def test_search_notes_returns_results(self):
        mock_contexts = [
            RetrievedContext(
                path="notes/test.md",
                title="Test Note",
                content="Some content about the topic",
                score=0.85,
                notebook="work",
            )
        ]

        context = AgenticContext()

        with patch(
            "nb.core.ai.ask_agentic._retrieve_context_enriched",
            return_value=mock_contexts,
        ):
            result = _execute_search_notes({"query": "test topic"}, context)

        assert "Found 1 relevant notes" in result
        assert "Test Note" in result
        assert "notes/test.md" in result
        # Should add to sources
        assert len(context.sources) == 1

    def test_search_notes_no_results(self):
        context = AgenticContext()

        with patch(
            "nb.core.ai.ask_agentic._retrieve_context_enriched",
            return_value=[],
        ):
            result = _execute_search_notes({"query": "nonexistent"}, context)

        assert "No matching notes found" in result

    def test_search_notes_no_query(self):
        context = AgenticContext()
        result = _execute_search_notes({}, context)
        assert "Error" in result


class TestExecuteReadNote:
    """Tests for read_note tool execution."""

    def test_read_note_success(self, tmp_path):
        from nb.config import Config, LLMConfig, NotebookConfig

        # Create a test note
        note_path = tmp_path / "work" / "test.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("# Test Note\n\nThis is the content.")

        mock_config = Config(
            notes_root=tmp_path,
            editor="echo",
            notebooks=[NotebookConfig(name="work")],
            llm=LLMConfig(provider="anthropic", api_key="test-key"),
        )

        context = AgenticContext()

        with patch("nb.core.ai.ask_agentic.get_config", return_value=mock_config):
            result = _execute_read_note({"path": "work/test.md"}, context)

        assert "# Test Note" in result
        assert "This is the content" in result
        # Should add to sources
        assert len(context.sources) == 1

    def test_read_note_not_found(self, tmp_path):
        from nb.config import Config, LLMConfig

        mock_config = Config(
            notes_root=tmp_path,
            editor="echo",
            notebooks=[],
            llm=LLMConfig(provider="anthropic", api_key="test-key"),
        )

        context = AgenticContext()

        with patch("nb.core.ai.ask_agentic.get_config", return_value=mock_config):
            result = _execute_read_note({"path": "nonexistent.md"}, context)

        assert "not found" in result.lower()

    def test_read_note_no_path(self):
        context = AgenticContext()
        result = _execute_read_note({}, context)
        assert "Error" in result


class TestExecuteQueryTodos:
    """Tests for query_todos tool execution."""

    @pytest.fixture
    def mock_todos(self):
        """Create mock todos for testing."""
        return [
            Todo(
                id="abc12345",
                content="Fix login bug",
                raw_content="- [ ] Fix login bug @due(2025-01-20) #bug",
                status=TodoStatus.PENDING,
                source=TodoSource(path="work/tasks.md", type="note"),
                line_number=1,
                created_date=date.today(),
                due_date=date.today() + timedelta(days=5),
                priority=Priority.HIGH,
                tags=["bug"],
            ),
            Todo(
                id="def67890",
                content="Update docs",
                raw_content="- [ ] Update docs",
                status=TodoStatus.PENDING,
                source=TodoSource(path="work/tasks.md", type="note"),
                line_number=2,
                created_date=date.today(),
            ),
        ]

    def test_query_todos_returns_results(self, mock_todos):
        context = AgenticContext()

        with patch(
            "nb.core.ai.ask_agentic.get_sorted_todos",
            return_value=mock_todos,
        ):
            result = _execute_query_todos({"notebooks": ["work"]}, context)

        assert "Found 2 todos" in result
        assert "Fix login bug" in result
        assert "Update docs" in result

    def test_query_todos_no_results(self):
        context = AgenticContext()

        with patch(
            "nb.core.ai.ask_agentic.get_sorted_todos",
            return_value=[],
        ):
            result = _execute_query_todos({"notebooks": ["empty"]}, context)

        assert "No todos found" in result

    def test_query_todos_with_filters(self, mock_todos):
        context = AgenticContext()

        with patch(
            "nb.core.ai.ask_agentic.get_sorted_todos",
            return_value=mock_todos,
        ) as mock_query:
            _execute_query_todos(
                {
                    "notebooks": ["work"],
                    "status": "pending",
                    "priority": 1,
                },
                context,
            )

            # Verify filters were passed
            call_kwargs = mock_query.call_args.kwargs
            assert call_kwargs["notebooks"] == ["work"]
            assert call_kwargs["priority"] == 1


class TestExecuteGetProjectStats:
    """Tests for get_project_stats tool execution."""

    def test_get_stats_returns_data(self):
        mock_stats = {
            "total": 10,
            "completed": 5,
            "in_progress": 2,
            "pending": 3,
            "overdue": 1,
            "due_today": 1,
            "due_this_week": 3,
            "by_priority": {
                1: {"total": 3, "completed": 1},
                2: {"total": 5, "completed": 3},
            },
        }

        context = AgenticContext()

        with patch(
            "nb.core.ai.ask_agentic.get_extended_todo_stats",
            return_value=mock_stats,
        ):
            result = _execute_get_project_stats({}, context)

        assert "Total todos" in result
        assert "10" in result
        assert "Completed" in result
        assert "50.0%" in result  # 5/10 = 50%

    def test_get_stats_no_todos(self):
        context = AgenticContext()

        with patch(
            "nb.core.ai.ask_agentic.get_extended_todo_stats",
            return_value={"total": 0},
        ):
            result = _execute_get_project_stats({}, context)

        assert "No todos found" in result


class TestExecuteAskTool:
    """Tests for the main tool execution dispatcher."""

    def test_execute_unknown_tool(self):
        tool_call = ToolCall(id="123", name="unknown_tool", arguments={})
        context = AgenticContext()

        result = execute_ask_tool(tool_call, context)

        assert result.is_error
        assert "Unknown tool" in result.content

    def test_execute_complete_answer(self):
        tool_call = ToolCall(
            id="123",
            name="complete_answer",
            arguments={"answer": "The final answer"},
        )
        context = AgenticContext()

        result = execute_ask_tool(tool_call, context)

        assert not result.is_error
        assert "complete" in result.content.lower()

    def test_execute_search_notes_through_dispatcher(self):
        tool_call = ToolCall(
            id="123",
            name="search_notes",
            arguments={"query": "test"},
        )
        context = AgenticContext()

        mock_contexts = [
            RetrievedContext(
                path="test.md",
                title="Test",
                content="Content",
                score=0.9,
            )
        ]

        with patch(
            "nb.core.ai.ask_agentic._retrieve_context_enriched",
            return_value=mock_contexts,
        ):
            result = execute_ask_tool(tool_call, context)

        assert not result.is_error
        assert "Found 1" in result.content


class TestAgenticSystemPrompt:
    """Tests for the agentic system prompt."""

    def test_prompt_has_placeholder(self):
        assert "{available_tools}" in AGENTIC_ASK_SYSTEM_PROMPT

    def test_prompt_mentions_tools(self):
        formatted = AGENTIC_ASK_SYSTEM_PROMPT.format(
            available_tools="- search_notes: Search\n- query_todos: Query"
        )
        assert "search_notes" in formatted
        assert "query_todos" in formatted

    def test_prompt_mentions_complete_answer(self):
        assert "complete_answer" in AGENTIC_ASK_SYSTEM_PROMPT
