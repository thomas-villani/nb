"""Tests for the AI Executive Assistant.

Tests core functionality of the assistant including context gathering,
action queuing, and tool execution.
"""

from __future__ import annotations

from nb.core.ai.assistant import (
    AssistantContext,
    PendingAction,
    clear_pending_actions,
    gather_assistant_context,
    generate_action_id,
    queue_write_action,
)
from nb.core.ai.assistant_tools import (
    execute_assistant_tool,
    execute_write_action,
    get_assistant_tools,
)
from nb.core.llm import ToolCall, ToolResult


class TestAssistantContext:
    """Tests for AssistantContext dataclass."""

    def test_context_creation(self):
        """Test creating an empty context."""
        context = AssistantContext()

        assert context.messages == []
        assert context.pending_actions == []
        assert context.executed_actions == []
        assert context.sources == []
        assert context.input_tokens == 0
        assert context.output_tokens == 0
        assert context.tool_calls_count == 0
        assert context.tools_used == []


class TestPendingAction:
    """Tests for PendingAction dataclass."""

    def test_action_creation(self):
        """Test creating a pending action."""
        action = PendingAction(
            id="abc123",
            action_type="create_todo",
            description="Add todo to daily note",
            details={"content": "Test todo"},
            preview="- [ ] Test todo",
            tool_call_id="tool_123",
        )

        assert action.id == "abc123"
        assert action.action_type == "create_todo"
        assert action.description == "Add todo to daily note"
        assert action.details == {"content": "Test todo"}
        assert action.preview == "- [ ] Test todo"


class TestActionQueue:
    """Tests for action queuing and execution."""

    def test_generate_action_id(self):
        """Test action ID generation."""
        id1 = generate_action_id()
        id2 = generate_action_id()

        assert len(id1) == 8
        assert id1 != id2

    def test_queue_write_action(self):
        """Test queuing a write action."""
        context = AssistantContext()

        result = queue_write_action(
            context=context,
            action_type="create_todo",
            description="Add todo",
            details={"content": "Test"},
            preview="- [ ] Test",
            tool_call_id="tool_123",
        )

        assert len(context.pending_actions) == 1
        assert context.pending_actions[0].action_type == "create_todo"
        assert isinstance(result, ToolResult)
        assert "queued" in result.content.lower()

    def test_clear_pending_actions(self):
        """Test clearing pending actions."""
        context = AssistantContext()
        context.pending_actions.append(
            PendingAction(
                id="test",
                action_type="create_todo",
                description="Test",
                details={},
                preview="",
                tool_call_id="",
            )
        )

        clear_pending_actions(context)

        assert len(context.pending_actions) == 0


class TestToolDefinitions:
    """Tests for tool definitions."""

    def test_get_assistant_tools(self):
        """Test that all expected tools are defined."""
        tools = get_assistant_tools()

        tool_names = [t.name for t in tools]

        # Read tools
        assert "search_notes" in tool_names
        assert "read_note" in tool_names
        assert "query_todos" in tool_names
        assert "get_project_stats" in tool_names
        assert "get_calendar_events" in tool_names

        # Write tools
        assert "create_todo" in tool_names
        assert "update_todo" in tool_names
        assert "create_note" in tool_names
        assert "append_to_note" in tool_names

    def test_tool_has_required_fields(self):
        """Test that tools have name, description, and parameters."""
        tools = get_assistant_tools()

        for tool in tools:
            assert tool.name
            assert tool.description
            assert isinstance(tool.parameters, dict)
            assert "type" in tool.parameters
            assert tool.parameters["type"] == "object"


class TestGatherContext:
    """Tests for context gathering."""

    def test_gather_context_empty(self, mock_config, temp_notes_root):
        """Test gathering context with no todos."""
        context = gather_assistant_context(include_calendar=False)

        assert isinstance(context, str)
        assert "No pending todos" in context or len(context) > 0


class TestToolExecution:
    """Tests for tool execution routing."""

    def test_execute_read_tool(self, mock_config, temp_notes_root):
        """Test executing a read-only tool."""
        context = AssistantContext()
        tool_call = ToolCall(
            id="test_123",
            name="query_todos",
            arguments={"status": "pending"},
        )

        result = execute_assistant_tool(tool_call, context)

        assert isinstance(result, ToolResult)
        assert not result.is_error

    def test_execute_write_tool_queues_action(self, mock_config, temp_notes_root):
        """Test that write tools queue actions instead of executing."""
        context = AssistantContext()
        tool_call = ToolCall(
            id="test_123",
            name="create_todo",
            arguments={"content": "Test todo"},
        )

        result = execute_assistant_tool(tool_call, context)

        assert isinstance(result, ToolResult)
        assert len(context.pending_actions) == 1
        assert context.pending_actions[0].action_type == "create_todo"
        assert "queued" in result.content.lower()

    def test_unknown_tool_returns_error(self, mock_config, temp_notes_root):
        """Test that unknown tools return an error."""
        context = AssistantContext()
        tool_call = ToolCall(
            id="test_123",
            name="unknown_tool",
            arguments={},
        )

        result = execute_assistant_tool(tool_call, context)

        assert result.is_error
        assert "unknown" in result.content.lower()


class TestWriteActionExecution:
    """Tests for write action execution after confirmation."""

    def test_execute_create_todo_action(
        self, mock_config, temp_notes_root, create_note
    ):
        """Test executing a create_todo action."""
        # Create a test note (notebook, filename, content)
        note_path = create_note("projects", "test.md", "# Test\n")

        action = PendingAction(
            id="test123",
            action_type="create_todo",
            description="Add todo",
            details={
                "content": "Test todo item",
                "note_path": "projects/test.md",
            },
            preview="- [ ] Test todo item",
            tool_call_id="tool_123",
        )

        result = execute_write_action(action)

        assert "created" in result.lower() or "test todo" in result.lower()

        # Verify the todo was added
        content = note_path.read_text()
        assert "Test todo item" in content

    def test_execute_append_to_note_action(
        self, mock_config, temp_notes_root, create_note
    ):
        """Test executing an append_to_note action."""
        # Create a test note (notebook, filename, content)
        note_path = create_note("projects", "test.md", "# Test\n\nInitial content.\n")

        action = PendingAction(
            id="test123",
            action_type="append_to_note",
            description="Append to note",
            details={
                "note_path": "projects/test.md",
                "content": "Appended content here.",
            },
            preview="Appended content here.",
            tool_call_id="tool_123",
        )

        result = execute_write_action(action)

        assert "appended" in result.lower()

        # Verify the content was appended
        content = note_path.read_text()
        assert "Appended content here" in content
