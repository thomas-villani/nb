"""Agentic RAG-based question answering over notes.

Uses LLM tool-calling to query both notes and todos for comprehensive answers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from nb.config import get_config
from nb.core.ai.ask import (
    DEFAULT_ASK_SYSTEM_PROMPT,
    NoteReference,
    RetrievedContext,
    _build_context_prompt,
    _contexts_to_references,
    _get_model_context_limit,
    _retrieve_context_enriched,
)
from nb.core.llm import (
    Message,
    ToolCall,
    ToolDefinition,
    ToolResult,
    get_llm_client,
)
from nb.index.todos_repo import get_extended_todo_stats, get_sorted_todos
from nb.models import TodoStatus

# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class AgenticContext:
    """Context for the agentic ask loop."""

    messages: list[Message] = field(default_factory=list)
    sources: list[NoteReference] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls_count: int = 0
    tools_used: list[str] = field(default_factory=list)
    initial_context: list[RetrievedContext] = field(default_factory=list)


@dataclass
class AgenticAnswerResult:
    """Extended result with tool execution metadata."""

    answer: str
    sources: list[NoteReference] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    tools_used: list[str] = field(default_factory=list)


# ============================================================================
# System Prompt
# ============================================================================

AGENTIC_ASK_SYSTEM_PROMPT = """You are a helpful assistant answering questions based on the user's personal notes and todos.

Initial context from semantic search is provided below. You can:
1. Answer directly if the context contains sufficient information
2. Use tools to gather additional information if needed

Available tools:
{available_tools}

Guidelines:
- For questions about tasks, todos, or project status, use query_todos or get_project_stats
- For questions about note content, use search_notes to find more context or read_note to get full note content
- Synthesize information from multiple sources when appropriate
- When citing information, reference the source note path
- Call complete_answer when you have enough information to provide a comprehensive answer

If the initial context doesn't contain relevant information, don't apologize - just use the appropriate tools to find the answer."""

BUDGET_WARNING_PROMPT = """
IMPORTANT: You are approaching your token budget limit ({tokens_used:,}/{token_budget:,} tokens used).
Please wrap up and call complete_answer with your findings now.
"""


# ============================================================================
# Tool Definitions
# ============================================================================


def get_ask_tools() -> list[ToolDefinition]:
    """Get tool definitions for agentic ask."""
    return [
        ToolDefinition(
            name="search_notes",
            description="Search notes using semantic search. Good for finding information by topic, concept, or keywords.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "notebook": {
                        "type": "string",
                        "description": "Limit to specific notebook (optional)",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter to notes with this tag (optional)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
        ToolDefinition(
            name="read_note",
            description="Read the full content of a specific note by path. Use when you know which note to read.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the note (relative to notes root, e.g. 'projects/myproject/design.md')",
                    },
                },
                "required": ["path"],
            },
        ),
        ToolDefinition(
            name="query_todos",
            description="Query todos/tasks with filters. Use for questions about tasks, what's pending, overdue, or needs to be done.",
            parameters={
                "type": "object",
                "properties": {
                    "notebooks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter to specific notebooks/projects",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "all"],
                        "description": "Filter by status (default: pending)",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag",
                    },
                    "priority": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": "Filter by priority (1=high, 2=medium, 3=low)",
                    },
                    "overdue_only": {
                        "type": "boolean",
                        "description": "Only return overdue todos",
                    },
                    "due_within_days": {
                        "type": "integer",
                        "description": "Only todos due within N days",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="get_project_stats",
            description="Get statistics about todos in a notebook/project: completion rate, overdue count, priority breakdown. Good for questions about progress.",
            parameters={
                "type": "object",
                "properties": {
                    "notebooks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Notebooks to get stats for (empty = all)",
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="complete_answer",
            description="Call this when you have gathered sufficient information and are ready to provide the final answer.",
            parameters={
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "The complete answer in markdown",
                    },
                },
                "required": ["answer"],
            },
        ),
    ]


def _format_tools_for_prompt(tools: list[ToolDefinition]) -> str:
    """Format tool list for system prompt."""
    lines = []
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)


# ============================================================================
# Tool Execution
# ============================================================================


def _execute_search_notes(args: dict[str, Any], context: AgenticContext) -> str:
    """Execute search_notes tool."""
    query = args.get("query", "")
    notebook = args.get("notebook")
    tag = args.get("tag")
    max_results = min(args.get("max_results", 5), 10)

    if not query:
        return "Error: No query provided"

    try:
        contexts = _retrieve_context_enriched(
            question=query,
            notebook=notebook,
            tag=tag,
            max_results=max_results,
            context_window=2,
        )

        if not contexts:
            return "No matching notes found."

        # Add to sources
        new_refs = _contexts_to_references(contexts)
        existing_paths = {s.path for s in context.sources}
        for ref in new_refs:
            if ref.path not in existing_paths:
                context.sources.append(ref)
                existing_paths.add(ref.path)

        # Format results
        lines = [f"## Found {len(contexts)} relevant notes\n"]
        for i, ctx in enumerate(contexts, 1):
            title = ctx.title or Path(ctx.path).stem
            lines.append(f"### [{i}] {title}")
            lines.append(f"Path: {ctx.path}")
            if ctx.notebook:
                lines.append(f"Notebook: {ctx.notebook}")
            lines.append(f"Score: {ctx.score:.2f}")
            # Truncate content for display
            content = ctx.content[:1500] if len(ctx.content) > 1500 else ctx.content
            lines.append(f"\n{content}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


def _execute_read_note(args: dict[str, Any], context: AgenticContext) -> str:
    """Execute read_note tool."""
    note_path = args.get("path", "")

    if not note_path:
        return "Error: No path provided"

    try:
        config = get_config()
        path = Path(note_path)
        if not path.is_absolute():
            path = config.notes_root / path

        if not path.exists():
            return f"Note not found: {note_path}"

        content = path.read_text(encoding="utf-8")

        # Truncate very long notes
        max_chars = 8000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... content truncated ...]"

        # Add to sources if not already there
        existing_paths = {s.path for s in context.sources}
        if note_path not in existing_paths:
            context.sources.append(
                NoteReference(
                    path=note_path,
                    title=path.stem,
                    snippet=content[:200] + "..." if len(content) > 200 else content,
                    score=1.0,
                    notebook=None,
                )
            )

        return f"## Content of {note_path}\n\n{content}"
    except Exception as e:
        return f"Failed to read note: {e}"


def _execute_query_todos(args: dict[str, Any], context: AgenticContext) -> str:
    """Execute query_todos tool."""
    notebooks = args.get("notebooks")
    status_str = args.get("status", "pending")
    tag = args.get("tag")
    priority = args.get("priority")
    overdue_only = args.get("overdue_only", False)
    due_within_days = args.get("due_within_days")
    max_results = min(args.get("max_results", 20), 50)

    try:
        # Convert status string to query params
        if status_str == "all":
            completed = None
        elif status_str == "completed":
            completed = True
        else:
            completed = False

        # Calculate due date range
        due_end = None
        if due_within_days:
            due_end = date.today() + timedelta(days=due_within_days)

        # Query todos
        todos = get_sorted_todos(
            completed=completed,
            notebooks=notebooks,
            tag=tag,
            priority=priority,
            due_end=due_end,
        )

        # Filter by specific status if needed
        if status_str == "in_progress":
            todos = [t for t in todos if t.status == TodoStatus.IN_PROGRESS]

        if overdue_only:
            todos = [t for t in todos if t.is_overdue]

        todos = todos[:max_results]

        if not todos:
            filters = []
            if notebooks:
                filters.append(f"notebooks={notebooks}")
            if status_str != "pending":
                filters.append(f"status={status_str}")
            if tag:
                filters.append(f"tag={tag}")
            filter_str = ", ".join(filters) if filters else "no filters"
            return f"No todos found matching: {filter_str}"

        # Format results
        lines = [f"## Found {len(todos)} todos\n"]
        for todo in todos:
            # Status checkbox
            if todo.status == TodoStatus.COMPLETED:
                checkbox = "[x]"
            elif todo.status == TodoStatus.IN_PROGRESS:
                checkbox = "[^]"
            else:
                checkbox = "[ ]"

            line = f"- {checkbox} {todo.content}"
            if todo.due_date:
                due_str = todo.due_date.strftime("%Y-%m-%d")
                if todo.is_overdue:
                    line += f" @due({due_str}) **OVERDUE**"
                else:
                    line += f" @due({due_str})"
            if todo.priority:
                line += f" @priority({todo.priority.value})"
            if todo.tags:
                line += " " + " ".join(f"#{t}" for t in todo.tags)

            lines.append(line)
            lines.append(f"  Source: {todo.source.path}")

        return "\n".join(lines)
    except Exception as e:
        return f"Todo query failed: {e}"


def _execute_get_project_stats(args: dict[str, Any], context: AgenticContext) -> str:
    """Execute get_project_stats tool."""
    notebooks = args.get("notebooks")

    try:
        stats = get_extended_todo_stats(notebooks=notebooks)

        total = stats.get("total", 0)
        if total == 0:
            if notebooks:
                return f"No todos found in notebooks: {notebooks}"
            return "No todos found."

        completed = stats.get("completed", 0)
        completion_rate = (completed / total * 100) if total > 0 else 0

        lines = [
            "## Project Statistics\n",
            f"- **Total todos**: {total}",
            f"- **Completed**: {completed} ({completion_rate:.1f}%)",
            f"- **In progress**: {stats.get('in_progress', 0)}",
            f"- **Pending**: {stats.get('pending', 0)}",
            f"- **Overdue**: {stats.get('overdue', 0)}",
            f"- **Due today**: {stats.get('due_today', 0)}",
            f"- **Due this week**: {stats.get('due_this_week', 0)}",
        ]

        by_priority = stats.get("by_priority", {})
        if by_priority:
            lines.append("\n### By Priority")
            for p in [1, 2, 3]:
                if p in by_priority:
                    data = by_priority[p]
                    priority_name = {1: "High", 2: "Medium", 3: "Low"}.get(p, str(p))
                    lines.append(
                        f"- {priority_name}: {data.get('total', 0)} total, "
                        f"{data.get('completed', 0)} completed"
                    )

        by_notebook = stats.get("by_notebook", {})
        if by_notebook and len(by_notebook) > 1:
            lines.append("\n### By Notebook")
            for nb, data in by_notebook.items():
                lines.append(
                    f"- {nb}: {data.get('total', 0)} todos, "
                    f"{data.get('overdue', 0)} overdue"
                )

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to get stats: {e}"


def execute_ask_tool(tool_call: ToolCall, context: AgenticContext) -> ToolResult:
    """Execute a tool call and return the result."""
    name = tool_call.name
    args = tool_call.arguments

    try:
        if name == "search_notes":
            result = _execute_search_notes(args, context)
        elif name == "read_note":
            result = _execute_read_note(args, context)
        elif name == "query_todos":
            result = _execute_query_todos(args, context)
        elif name == "get_project_stats":
            result = _execute_get_project_stats(args, context)
        elif name == "complete_answer":
            # Handled specially in the main loop
            result = "Answer complete."
        else:
            result = f"Unknown tool: {name}"
            return ToolResult(tool_call_id=tool_call.id, content=result, is_error=True)

        return ToolResult(tool_call_id=tool_call.id, content=result)
    except Exception as e:
        return ToolResult(
            tool_call_id=tool_call.id, content=f"Tool error: {e}", is_error=True
        )


# ============================================================================
# Main Agentic Ask Function
# ============================================================================


def ask_notes_agentic(
    question: str,
    notebook: str | None = None,
    tag: str | None = None,
    max_context_results: int = 5,
    max_tool_calls: int = 5,
    token_budget: int = 50000,
    use_smart_model: bool = True,
    progress_callback: Callable[[str], None] | None = None,
) -> AgenticAnswerResult:
    """Answer a question using agentic RAG with tool-calling.

    Performs initial semantic search, then gives the LLM tools to query
    notes and todos for comprehensive answers.

    Args:
        question: The question to answer.
        notebook: Filter initial search to a specific notebook.
        tag: Filter initial search to notes with a specific tag.
        max_context_results: Maximum results in initial search.
        max_tool_calls: Maximum tool calls allowed.
        token_budget: Maximum tokens to consume.
        use_smart_model: Use smart model for better reasoning.
        progress_callback: Called with progress updates.

    Returns:
        AgenticAnswerResult with the answer and metadata.
    """
    config = get_config()
    context = AgenticContext()

    # 1. Initial RAG retrieval (same as current ask_notes)
    if progress_callback:
        progress_callback("Searching notes...")

    initial_contexts = _retrieve_context_enriched(
        question=question,
        notebook=notebook,
        tag=tag,
        max_results=max_context_results,
        context_window=3,
    )
    context.initial_context = initial_contexts
    context.sources = _contexts_to_references(initial_contexts)

    # 2. Build initial prompt with context
    model = config.llm.models.smart if use_smart_model else config.llm.models.fast
    max_context_tokens = _get_model_context_limit(model)

    initial_prompt, _ = _build_context_prompt(
        question, initial_contexts, max_context_tokens, DEFAULT_ASK_SYSTEM_PROMPT
    )

    # 3. Initialize messages
    context.messages = [Message(role="user", content=initial_prompt)]

    # 4. Get tools and build system prompt
    tools = get_ask_tools()
    system_prompt = AGENTIC_ASK_SYSTEM_PROMPT.format(
        available_tools=_format_tools_for_prompt(tools)
    )

    # 5. Agent loop
    client = get_llm_client()
    answer = ""

    while context.tool_calls_count < max_tool_calls:
        # Check token budget
        total_tokens = context.input_tokens + context.output_tokens
        if total_tokens >= token_budget * 0.9:
            system_prompt += BUDGET_WARNING_PROMPT.format(
                tokens_used=total_tokens, token_budget=token_budget
            )

        if total_tokens >= token_budget:
            if progress_callback:
                progress_callback("Token budget reached, completing...")
            # Force an answer with what we have
            answer = _generate_forced_answer(question, context, client, use_smart_model)
            break

        response = client.complete(
            messages=context.messages,
            system=system_prompt,
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
                context.tool_calls_count += 1
                if tool_call.name not in context.tools_used:
                    context.tools_used.append(tool_call.name)

                if progress_callback:
                    progress_callback(f"Calling {tool_call.name}...")

                # Check for completion
                if tool_call.name == "complete_answer":
                    answer = tool_call.arguments.get("answer", "")
                    break

                # Execute tool
                result = execute_ask_tool(tool_call, context)

                # Add tool result message
                context.messages.append(
                    Message(role="tool", content="", tool_result=result)
                )

            if answer:
                break
        else:
            # LLM provided text without tool calls - this is the answer
            answer = response.content
            break

    return AgenticAnswerResult(
        answer=answer,
        sources=context.sources,
        input_tokens=context.input_tokens,
        output_tokens=context.output_tokens,
        tool_calls=context.tool_calls_count,
        tools_used=context.tools_used,
    )


def _generate_forced_answer(
    question: str,
    context: AgenticContext,
    client: Any,
    use_smart_model: bool,
) -> str:
    """Generate an answer when token budget is exhausted."""
    # Build summary of what we have
    sources_summary = []
    for source in context.sources[:10]:
        sources_summary.append(f"- {source.path}: {source.snippet[:100]}...")

    prompt = f"""Based on the information gathered so far, please provide a final answer to: {question}

Available sources:
{chr(10).join(sources_summary)}

Provide a concise answer based on the available information."""

    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        use_smart_model=use_smart_model,
    )

    context.input_tokens += response.input_tokens
    context.output_tokens += response.output_tokens

    return response.content


def ask_notes_agentic_stream(
    question: str,
    notebook: str | None = None,
    tag: str | None = None,
    max_context_results: int = 5,
    max_tool_calls: int = 5,
    token_budget: int = 50000,
    use_smart_model: bool = True,
) -> Iterator[tuple[str, AgenticAnswerResult | None]]:
    """Stream agentic ask progress and results.

    Yields tuples of (message, result) where result is None until completion.

    Args:
        Same as ask_notes_agentic()

    Yields:
        Tuple of (progress_message, AgenticAnswerResult or None)
    """
    config = get_config()
    context = AgenticContext()

    # 1. Initial RAG retrieval
    yield ("Searching notes...", None)

    initial_contexts = _retrieve_context_enriched(
        question=question,
        notebook=notebook,
        tag=tag,
        max_results=max_context_results,
        context_window=3,
    )
    context.initial_context = initial_contexts
    context.sources = _contexts_to_references(initial_contexts)

    yield (f"Found {len(initial_contexts)} relevant notes", None)

    # 2. Build initial prompt
    model = config.llm.models.smart if use_smart_model else config.llm.models.fast
    max_context_tokens = _get_model_context_limit(model)

    initial_prompt, _ = _build_context_prompt(
        question, initial_contexts, max_context_tokens, DEFAULT_ASK_SYSTEM_PROMPT
    )

    context.messages = [Message(role="user", content=initial_prompt)]

    # 3. Get tools and build system prompt
    tools = get_ask_tools()
    system_prompt = AGENTIC_ASK_SYSTEM_PROMPT.format(
        available_tools=_format_tools_for_prompt(tools)
    )

    # 4. Agent loop
    client = get_llm_client()
    answer = ""

    yield ("Reasoning...", None)

    while context.tool_calls_count < max_tool_calls:
        total_tokens = context.input_tokens + context.output_tokens
        yield (f"Tokens: {total_tokens:,}/{token_budget:,}", None)

        if total_tokens >= token_budget * 0.9:
            system_prompt += BUDGET_WARNING_PROMPT.format(
                tokens_used=total_tokens, token_budget=token_budget
            )

        if total_tokens >= token_budget:
            yield ("Token budget reached, completing...", None)
            answer = _generate_forced_answer(question, context, client, use_smart_model)
            break

        response = client.complete(
            messages=context.messages,
            system=system_prompt,
            tools=tools,
            use_smart_model=use_smart_model,
        )

        context.input_tokens += response.input_tokens
        context.output_tokens += response.output_tokens

        if response.tool_calls:
            context.messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            for tool_call in response.tool_calls:
                context.tool_calls_count += 1
                if tool_call.name not in context.tools_used:
                    context.tools_used.append(tool_call.name)

                yield (f"Executing: {tool_call.name}", None)

                if tool_call.name == "complete_answer":
                    answer = tool_call.arguments.get("answer", "")
                    break

                result = execute_ask_tool(tool_call, context)
                context.messages.append(
                    Message(role="tool", content="", tool_result=result)
                )

            if answer:
                break
        else:
            answer = response.content
            break

    final_result = AgenticAnswerResult(
        answer=answer,
        sources=context.sources,
        input_tokens=context.input_tokens,
        output_tokens=context.output_tokens,
        tool_calls=context.tool_calls_count,
        tools_used=context.tools_used,
    )

    yield ("Complete!", final_result)
