"""AI Executive Assistant for interactive task and note management.

Provides a conversational interface with write-capable tools for managing
todos and notes, with a confirmation flow for all write operations.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from nb.core.ai.ask import NoteReference
from nb.core.llm import (
    Message,
    ToolDefinition,
    ToolResult,
    get_llm_client,
)
from nb.index.todos_repo import get_sorted_todos
from nb.models import TodoStatus

if TYPE_CHECKING:
    from nb.models import Todo


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class PendingAction:
    """A write action pending user confirmation."""

    id: str
    action_type: str  # "create_todo", "update_todo", "create_note", "append_to_note"
    description: str  # Human-readable description
    details: dict[str, Any]  # Full parameters for execution
    preview: str  # Formatted preview of the change
    tool_call_id: str  # Original tool call ID for response


@dataclass
class AssistantContext:
    """Context for the assistant session."""

    messages: list[Message] = field(default_factory=list)
    pending_actions: list[PendingAction] = field(default_factory=list)
    executed_actions: list[PendingAction] = field(default_factory=list)
    sources: list[NoteReference] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls_count: int = 0
    tools_used: list[str] = field(default_factory=list)


@dataclass
class AssistantResult:
    """Result from an assistant session or turn."""

    response: str
    pending_actions: list[PendingAction] = field(default_factory=list)
    executed_actions: list[PendingAction] = field(default_factory=list)
    sources: list[NoteReference] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0


# ============================================================================
# System Prompt
# ============================================================================


ASSISTANT_SYSTEM_PROMPT = """\
You are an AI Executive Assistant helping manage tasks and notes.

Today is {today_date}.

You have access to tools that can:
- READ: Search notes, read note content, query todos, get project stats, view calendar
- WRITE: Create todos, update todo status/due dates, create notes, append to notes

IMPORTANT GUIDELINES:
1. When the user asks to make changes, use the appropriate write tools
2. Write operations will be queued for user confirmation before execution
3. For bulk changes, confirm your understanding before proceeding
4. Reference todo IDs when modifying specific todos (shown as 6-char hashes like "abc123")
5. Use natural language dates for due dates (e.g., "next monday", "tomorrow", "2025-01-15")
6. Default to adding todos to today's daily note unless specified otherwise

CURRENT CONTEXT:
{context}
{additional_context}
Available tools:
{available_tools}
"""

BUDGET_WARNING = """\

WARNING: Approaching token budget ({tokens_used:,}/{budget:,}). Please wrap up your response.
"""


# ============================================================================
# Context Gathering
# ============================================================================


def gather_assistant_context(
    notebook: str | None = None,
    include_calendar: bool = True,
    max_todos: int = 30,
) -> str:
    """Gather contextual information to inject into the system prompt.

    Args:
        notebook: Filter to specific notebook.
        include_calendar: Whether to include calendar events.
        max_todos: Maximum todos to include.

    Returns:
        Formatted context string.
    """
    parts = []
    today = date.today()

    # Fetch todos
    todos = get_sorted_todos(
        completed=False,
        notebooks=[notebook] if notebook else None,
        exclude_note_excluded=True,
    )

    # Categorize todos
    overdue = [t for t in todos if t.is_overdue]
    in_progress = [t for t in todos if t.status == TodoStatus.IN_PROGRESS]
    due_today = [t for t in todos if t.due_date_only == today and not t.is_overdue]
    due_soon = [
        t
        for t in todos
        if t.due_date_only
        and not t.is_overdue
        and t.due_date_only != today
        and t.due_date_only <= today + timedelta(days=7)
    ]

    # Format overdue todos
    if overdue:
        parts.append("## OVERDUE TODOS")
        for t in overdue[:15]:
            parts.append(_format_todo_for_context(t))
        parts.append("")

    # Format in-progress todos
    if in_progress:
        parts.append("## IN PROGRESS")
        for t in in_progress[:10]:
            parts.append(_format_todo_for_context(t))
        parts.append("")

    # Format due today
    if due_today:
        parts.append("## DUE TODAY")
        for t in due_today[:10]:
            parts.append(_format_todo_for_context(t))
        parts.append("")

    # Format due soon
    if due_soon:
        parts.append("## DUE THIS WEEK")
        for t in due_soon[:10]:
            parts.append(_format_todo_for_context(t))
        parts.append("")

    # Calendar events
    if include_calendar:
        try:
            from nb.core.calendar import get_week_events

            events = get_week_events()
            if events:
                parts.append("## CALENDAR (This Week)")
                for e in events[:15]:
                    start_str = e.start.strftime("%a %H:%M")
                    end_str = e.end.strftime("%H:%M")
                    parts.append(f"- {start_str}-{end_str}: {e.subject}")
                parts.append("")
        except Exception:
            pass

    # Recent notes summary
    try:
        from nb.core.notes import get_recently_modified_notes

        recent = get_recently_modified_notes(limit=5)
        if recent:
            parts.append("## RECENTLY MODIFIED NOTES")
            for path, mtime in recent:
                parts.append(f"- {path} (modified {mtime.strftime('%Y-%m-%d')})")
            parts.append("")
    except Exception:
        pass

    if not parts:
        parts.append("(No pending todos or recent activity)")

    return "\n".join(parts)


def _format_todo_for_context(todo: Todo) -> str:
    """Format a todo for context display."""
    # Status checkbox
    if todo.status == TodoStatus.COMPLETED:
        checkbox = "[x]"
    elif todo.status == TodoStatus.IN_PROGRESS:
        checkbox = "[^]"
    else:
        checkbox = "[ ]"

    line = f"- {checkbox} [{todo.id[:6]}] {todo.content}"

    if todo.due_date:
        due_str = todo.due_date.strftime("%Y-%m-%d")
        if todo.is_overdue:
            line += f" @due({due_str}) **OVERDUE**"
        else:
            line += f" @due({due_str})"

    if todo.priority:
        line += f" @priority({todo.priority.value})"

    if todo.tags:
        line += " " + " ".join(f"#{t}" for t in todo.tags[:3])

    if todo.source:
        line += f" (in: {todo.source.path})"

    return line


# ============================================================================
# Action Queue Management
# ============================================================================


def generate_action_id() -> str:
    """Generate a unique action ID."""
    return uuid.uuid4().hex[:8]


def queue_write_action(
    context: AssistantContext,
    action_type: str,
    description: str,
    details: dict[str, Any],
    preview: str,
    tool_call_id: str,
) -> ToolResult:
    """Queue a write action for confirmation instead of executing immediately.

    Args:
        context: The assistant context.
        action_type: Type of action (create_todo, update_todo, etc.).
        description: Human-readable description.
        details: Full parameters for execution.
        preview: Formatted preview string.
        tool_call_id: Original tool call ID.

    Returns:
        ToolResult indicating the action was queued.
    """
    action = PendingAction(
        id=generate_action_id(),
        action_type=action_type,
        description=description,
        details=details,
        preview=preview,
        tool_call_id=tool_call_id,
    )
    context.pending_actions.append(action)

    return ToolResult(
        tool_call_id=tool_call_id,
        content=f"Action queued for confirmation: {description}",
    )


def execute_pending_actions(
    context: AssistantContext,
    action_ids: list[str] | None = None,
) -> list[tuple[str, bool, str]]:
    """Execute confirmed pending actions.

    Args:
        context: The assistant context.
        action_ids: Specific action IDs to execute. None = all.

    Returns:
        List of (action_id, success, message) tuples.
    """
    from nb.core.ai.assistant_tools import execute_write_action

    results = []

    # Determine which actions to execute
    if action_ids is None:
        actions_to_execute = list(context.pending_actions)
    else:
        actions_to_execute = [a for a in context.pending_actions if a.id in action_ids]

    for action in actions_to_execute:
        try:
            message = execute_write_action(action)
            results.append((action.id, True, message))
            context.executed_actions.append(action)
        except Exception as e:
            results.append((action.id, False, str(e)))

    # Remove executed actions from pending
    executed_ids = {r[0] for r in results if r[1]}
    context.pending_actions = [
        a for a in context.pending_actions if a.id not in executed_ids
    ]

    return results


def clear_pending_actions(context: AssistantContext) -> None:
    """Clear all pending actions without executing."""
    context.pending_actions.clear()


# ============================================================================
# Tool Helpers
# ============================================================================


def _format_tools_for_prompt(tools: list[ToolDefinition]) -> str:
    """Format tool list for system prompt."""
    lines = []
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)


# ============================================================================
# Main Assistant Functions
# ============================================================================


def run_assistant_turn(
    context: AssistantContext,
    user_input: str,
    notebook: str | None = None,
    include_calendar: bool = True,
    use_smart_model: bool = True,
    max_tool_calls: int = 10,
    token_budget: int = 100000,
    additional_context: str = "",
) -> str:
    """Run a single turn of the assistant conversation.

    Args:
        context: The assistant context (mutated in place).
        user_input: User's input message.
        notebook: Filter context to specific notebook.
        include_calendar: Whether to include calendar context.
        use_smart_model: Use smart model for better reasoning.
        max_tool_calls: Maximum tool calls per turn.
        token_budget: Maximum tokens to consume.
        additional_context: Additional context from files, clipboard, or notes.

    Returns:
        Assistant's response text.
    """
    from nb.core.ai.assistant_tools import execute_assistant_tool, get_assistant_tools

    client = get_llm_client()

    # Get tools
    tools = get_assistant_tools()

    # Format additional context with section header if present
    formatted_additional = ""
    if additional_context:
        formatted_additional = f"\n\n## USER-PROVIDED CONTEXT\n\n{additional_context}\n"

    # Build system prompt (only on first turn or if context is empty)
    if not context.messages:
        injected_context = gather_assistant_context(notebook, include_calendar)
        system_prompt = ASSISTANT_SYSTEM_PROMPT.format(
            today_date=date.today().strftime("%A, %B %d, %Y"),
            context=injected_context,
            additional_context=formatted_additional,
            available_tools=_format_tools_for_prompt(tools),
        )
    else:
        # Reuse the initial system prompt structure
        injected_context = gather_assistant_context(notebook, include_calendar)
        system_prompt = ASSISTANT_SYSTEM_PROMPT.format(
            today_date=date.today().strftime("%A, %B %d, %Y"),
            context=injected_context,
            additional_context=formatted_additional,
            available_tools=_format_tools_for_prompt(tools),
        )

    # Add user message
    context.messages.append(Message(role="user", content=user_input))

    # Agent loop
    calls_this_turn = 0
    response_text = ""

    while calls_this_turn < max_tool_calls:
        # Check token budget
        total_tokens = context.input_tokens + context.output_tokens
        current_system = system_prompt
        if total_tokens >= token_budget * 0.9:
            current_system += BUDGET_WARNING.format(
                tokens_used=total_tokens, budget=token_budget
            )

        if total_tokens >= token_budget:
            response_text = "I've reached my token budget for this session. Please review any pending actions."
            break

        # Call LLM
        response = client.complete(
            messages=context.messages,
            system=current_system,
            tools=tools,
            use_smart_model=use_smart_model,
        )

        context.input_tokens += response.input_tokens
        context.output_tokens += response.output_tokens

        if response.tool_calls:
            # Add assistant message with tool calls
            context.messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # Process tool calls
            for tool_call in response.tool_calls:
                calls_this_turn += 1
                context.tool_calls_count += 1

                if tool_call.name not in context.tools_used:
                    context.tools_used.append(tool_call.name)

                # Execute tool
                result = execute_assistant_tool(tool_call, context)

                # Add tool result
                context.messages.append(
                    Message(role="tool", content="", tool_result=result)
                )
        else:
            # LLM provided text without tool calls - this is the response
            response_text = response.content
            context.messages.append(Message(role="assistant", content=response_text))
            break

    return response_text


def run_assistant_turn_stream(
    context: AssistantContext,
    user_input: str,
    notebook: str | None = None,
    include_calendar: bool = True,
    use_smart_model: bool = True,
    max_tool_calls: int = 10,
    token_budget: int = 100000,
    additional_context: str = "",
) -> Iterator[tuple[str, bool]]:
    """Stream a single turn of the assistant conversation.

    Yields tuples of (content, is_final).

    Args:
        Same as run_assistant_turn.

    Yields:
        Tuple of (text_chunk, is_final_response).
    """
    from nb.core.ai.assistant_tools import execute_assistant_tool, get_assistant_tools

    client = get_llm_client()

    # Get tools
    tools = get_assistant_tools()

    # Format additional context with section header if present
    formatted_additional = ""
    if additional_context:
        formatted_additional = f"\n\n## USER-PROVIDED CONTEXT\n\n{additional_context}\n"

    # Build system prompt
    injected_context = gather_assistant_context(notebook, include_calendar)
    system_prompt = ASSISTANT_SYSTEM_PROMPT.format(
        today_date=date.today().strftime("%A, %B %d, %Y"),
        context=injected_context,
        additional_context=formatted_additional,
        available_tools=_format_tools_for_prompt(tools),
    )

    # Add user message
    context.messages.append(Message(role="user", content=user_input))

    # Agent loop
    calls_this_turn = 0

    while calls_this_turn < max_tool_calls:
        # Check token budget
        total_tokens = context.input_tokens + context.output_tokens
        current_system = system_prompt
        if total_tokens >= token_budget * 0.9:
            current_system += BUDGET_WARNING.format(
                tokens_used=total_tokens, budget=token_budget
            )

        if total_tokens >= token_budget:
            yield (
                "I've reached my token budget. Please review any pending actions.",
                True,
            )
            return

        # Call LLM (non-streaming for tool calls, streaming for final response)
        response = client.complete(
            messages=context.messages,
            system=current_system,
            tools=tools,
            use_smart_model=use_smart_model,
        )

        context.input_tokens += response.input_tokens
        context.output_tokens += response.output_tokens

        if response.tool_calls:
            # Add assistant message with tool calls
            context.messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # Process tool calls
            for tool_call in response.tool_calls:
                calls_this_turn += 1
                context.tool_calls_count += 1

                if tool_call.name not in context.tools_used:
                    context.tools_used.append(tool_call.name)

                yield (f"[Executing: {tool_call.name}]", False)

                # Execute tool
                result = execute_assistant_tool(tool_call, context)

                # Add tool result
                context.messages.append(
                    Message(role="tool", content="", tool_result=result)
                )
        else:
            # Final response - stream it
            context.messages.append(Message(role="assistant", content=response.content))
            yield (response.content, True)
            return

    yield ("Maximum tool calls reached.", True)
