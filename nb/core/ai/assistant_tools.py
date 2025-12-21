"""Tool definitions and implementations for the AI Executive Assistant.

Tools are separated into read-only tools (execute immediately) and
write tools (queued for user confirmation).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nb.config import get_config
from nb.core.ai.ask import NoteReference
from nb.core.llm import ToolCall, ToolDefinition, ToolResult
from nb.index.todos_repo import get_extended_todo_stats, get_sorted_todos
from nb.models import TodoStatus

if TYPE_CHECKING:
    from nb.core.ai.assistant import AssistantContext, PendingAction


# ============================================================================
# Tool Definitions
# ============================================================================


def get_assistant_tools() -> list[ToolDefinition]:
    """Get all tool definitions for the assistant."""
    return [
        # Read-only tools (from ask_agentic, adapted)
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
            description="Read the full content of a specific note by path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the note (relative to notes root, e.g. 'projects/myproject/notes.md')",
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
            description="Get statistics about todos in a notebook/project: completion rate, overdue count, priority breakdown.",
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
            name="get_calendar_events",
            description="Get calendar events for today or this week. Requires Outlook to be available.",
            parameters={
                "type": "object",
                "properties": {
                    "range": {
                        "type": "string",
                        "enum": ["today", "week"],
                        "description": "Time range (default: week)",
                        "default": "week",
                    },
                },
                "required": [],
            },
        ),
        # Write tools (queued for confirmation)
        ToolDefinition(
            name="create_todo",
            description="Add a new todo task. Defaults to today's daily note if no note_path specified.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The todo text. Can include inline metadata like @due(2025-01-15) @priority(1) #tag",
                    },
                    "note_path": {
                        "type": "string",
                        "description": "Path to note (relative to notes root). Omit to use today's daily note.",
                    },
                    "section": {
                        "type": "string",
                        "description": "Section heading to add todo under (case-insensitive)",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in natural language (e.g., 'tomorrow', 'next monday', '2025-01-15')",
                    },
                    "priority": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": "Priority level (1=high, 2=medium, 3=low)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to apply (without # prefix)",
                    },
                },
                "required": ["content"],
            },
        ),
        ToolDefinition(
            name="update_todo",
            description="Update a todo's status, due date, or delete it. Use todo_id (6-char hash) from query_todos results.",
            parameters={
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "string",
                        "description": "The todo ID (6-character hash) or full ID",
                    },
                    "todo_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Multiple todo IDs for batch updates (use instead of todo_id)",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                        "description": "New status to set",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "New due date (natural language or ISO format). Use 'remove' to clear due date.",
                    },
                    "delete": {
                        "type": "boolean",
                        "description": "Set to true to delete the todo(s)",
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="create_note",
            description="Create a new note file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path for the new note (relative to notes root, e.g., 'projects/myproject/design.md')",
                    },
                    "title": {
                        "type": "string",
                        "description": "Note title (used as H1 heading)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Initial content for the note",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to add in frontmatter",
                    },
                },
                "required": ["path"],
            },
        ),
        ToolDefinition(
            name="append_to_note",
            description="Append content to an existing note.",
            parameters={
                "type": "object",
                "properties": {
                    "note_path": {
                        "type": "string",
                        "description": "Path to the note (relative to notes root)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to append",
                    },
                    "section": {
                        "type": "string",
                        "description": "Section heading to append under (creates if doesn't exist)",
                    },
                },
                "required": ["note_path", "content"],
            },
        ),
    ]


# ============================================================================
# Read Tool Execution (immediate)
# ============================================================================


def _execute_search_notes(args: dict[str, Any], context: AssistantContext) -> str:
    """Execute search_notes tool."""
    from nb.core.ai.ask import (
        _contexts_to_references,
        _retrieve_context_enriched,
    )

    query = args.get("query", "")
    notebook = args.get("notebook")
    max_results = min(args.get("max_results", 5), 10)

    if not query:
        return "Error: No query provided"

    try:
        contexts = _retrieve_context_enriched(
            question=query,
            notebook=notebook,
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
        lines = [f"Found {len(contexts)} relevant notes:\n"]
        for i, ctx in enumerate(contexts, 1):
            title = ctx.title or Path(ctx.path).stem
            lines.append(f"### [{i}] {title}")
            lines.append(f"Path: {ctx.path}")
            if ctx.notebook:
                lines.append(f"Notebook: {ctx.notebook}")
            content = ctx.content[:1500] if len(ctx.content) > 1500 else ctx.content
            lines.append(f"\n{content}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


def _execute_read_note(args: dict[str, Any], context: AssistantContext) -> str:
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

        # Add to sources
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


def _execute_query_todos(args: dict[str, Any], context: AssistantContext) -> str:
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
        lines = [f"Found {len(todos)} todos:\n"]
        for todo in todos:
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
                line += " " + " ".join(f"#{t}" for t in todo.tags)

            lines.append(line)
            lines.append(f"  Source: {todo.source.path}")

        return "\n".join(lines)
    except Exception as e:
        return f"Todo query failed: {e}"


def _execute_get_project_stats(args: dict[str, Any], context: AssistantContext) -> str:
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

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to get stats: {e}"


def _execute_get_calendar(args: dict[str, Any], context: AssistantContext) -> str:
    """Execute get_calendar_events tool."""
    time_range = args.get("range", "week")

    try:
        from nb.core.calendar import get_today_events, get_week_events

        if time_range == "today":
            events = get_today_events()
        else:
            events = get_week_events()

        if not events:
            return f"No calendar events found for {time_range}."

        lines = [f"## Calendar Events ({time_range})\n"]
        for e in events:
            start_str = e.start.strftime("%a %b %d %H:%M")
            end_str = e.end.strftime("%H:%M")
            duration = e.duration_minutes
            lines.append(f"- {start_str}-{end_str} ({duration}min): {e.subject}")
            if e.location:
                lines.append(f"  Location: {e.location}")

        return "\n".join(lines)
    except ImportError:
        return "Calendar integration not available (requires pywin32 on Windows)."
    except Exception as e:
        return f"Failed to get calendar: {e}"


# ============================================================================
# Write Tool Execution (queued for confirmation)
# ============================================================================


def _queue_create_todo(
    args: dict[str, Any], context: AssistantContext, tool_call_id: str
) -> ToolResult:
    """Queue a create_todo action."""
    from nb.core.ai.assistant import queue_write_action

    content = args.get("content", "")
    note_path = args.get("note_path")
    section = args.get("section")
    due_date = args.get("due_date")
    priority = args.get("priority")
    tags = args.get("tags", [])

    if not content:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Error: No content provided",
            is_error=True,
        )

    # Build the full todo text with metadata
    todo_text = content

    # Add metadata if not already in content
    if due_date and "@due(" not in content:
        todo_text += f" @due({due_date})"
    if priority and "@priority(" not in content:
        todo_text += f" @priority({priority})"
    if tags:
        for tag in tags:
            if f"#{tag}" not in content:
                todo_text += f" #{tag}"

    # Determine destination
    if note_path:
        dest = f"{note_path}"
        if section:
            dest += f" (under '{section}')"
    else:
        dest = "today's daily note"
        if section:
            dest += f" (under '{section}')"

    description = f"Add todo to {dest}"
    preview = f"- [ ] {todo_text}"

    return queue_write_action(
        context=context,
        action_type="create_todo",
        description=description,
        details={
            "content": todo_text,
            "note_path": note_path,
            "section": section,
        },
        preview=preview,
        tool_call_id=tool_call_id,
    )


def _queue_update_todo(
    args: dict[str, Any], context: AssistantContext, tool_call_id: str
) -> ToolResult:
    """Queue an update_todo action."""
    from nb.core.ai.assistant import queue_write_action

    todo_id = args.get("todo_id")
    todo_ids = args.get("todo_ids", [])
    status = args.get("status")
    due_date = args.get("due_date")
    delete = args.get("delete", False)

    # Normalize to list
    if todo_id and not todo_ids:
        todo_ids = [todo_id]

    if not todo_ids:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Error: No todo_id or todo_ids provided",
            is_error=True,
        )

    # Build description
    actions = []
    if status:
        actions.append(f"set status to {status}")
    if due_date:
        if due_date.lower() == "remove":
            actions.append("remove due date")
        else:
            actions.append(f"set due date to {due_date}")
    if delete:
        actions.append("delete")

    if not actions:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Error: No update action specified (status, due_date, or delete)",
            is_error=True,
        )

    action_str = ", ".join(actions)
    if len(todo_ids) == 1:
        description = f"Update todo {todo_ids[0][:6]}: {action_str}"
    else:
        description = f"Update {len(todo_ids)} todos: {action_str}"

    # Build preview
    preview_lines = []
    for tid in todo_ids[:5]:
        preview_lines.append(f"  [{tid[:6]}] -> {action_str}")
    if len(todo_ids) > 5:
        preview_lines.append(f"  ... and {len(todo_ids) - 5} more")
    preview = "\n".join(preview_lines)

    return queue_write_action(
        context=context,
        action_type="update_todo",
        description=description,
        details={
            "todo_ids": todo_ids,
            "status": status,
            "due_date": due_date,
            "delete": delete,
        },
        preview=preview,
        tool_call_id=tool_call_id,
    )


def _queue_create_note(
    args: dict[str, Any], context: AssistantContext, tool_call_id: str
) -> ToolResult:
    """Queue a create_note action."""
    from nb.core.ai.assistant import queue_write_action

    path = args.get("path", "")
    title = args.get("title")
    content = args.get("content", "")
    tags = args.get("tags", [])

    if not path:
        return ToolResult(
            tool_call_id=tool_call_id, content="Error: No path provided", is_error=True
        )

    description = f"Create note: {path}"
    preview_lines = [f"Path: {path}"]
    if title:
        preview_lines.append(f"Title: {title}")
    if tags:
        preview_lines.append(f"Tags: {', '.join(tags)}")
    if content:
        preview_lines.append(f"Content: {content[:100]}...")
    preview = "\n".join(preview_lines)

    return queue_write_action(
        context=context,
        action_type="create_note",
        description=description,
        details={
            "path": path,
            "title": title,
            "content": content,
            "tags": tags,
        },
        preview=preview,
        tool_call_id=tool_call_id,
    )


def _queue_append_to_note(
    args: dict[str, Any], context: AssistantContext, tool_call_id: str
) -> ToolResult:
    """Queue an append_to_note action."""
    from nb.core.ai.assistant import queue_write_action

    note_path = args.get("note_path", "")
    content = args.get("content", "")
    section = args.get("section")

    if not note_path:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Error: No note_path provided",
            is_error=True,
        )
    if not content:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Error: No content provided",
            is_error=True,
        )

    dest = note_path
    if section:
        dest += f" (under '{section}')"

    description = f"Append to {dest}"
    preview = content[:200] + ("..." if len(content) > 200 else "")

    return queue_write_action(
        context=context,
        action_type="append_to_note",
        description=description,
        details={
            "note_path": note_path,
            "content": content,
            "section": section,
        },
        preview=preview,
        tool_call_id=tool_call_id,
    )


# ============================================================================
# Write Action Execution (after confirmation)
# ============================================================================


def execute_write_action(action: PendingAction) -> str:
    """Execute a confirmed write action.

    Args:
        action: The pending action to execute.

    Returns:
        Success message.

    Raises:
        Exception: If execution fails.
    """
    if action.action_type == "create_todo":
        return _execute_create_todo_action(action.details)
    elif action.action_type == "update_todo":
        return _execute_update_todo_action(action.details)
    elif action.action_type == "create_note":
        return _execute_create_note_action(action.details)
    elif action.action_type == "append_to_note":
        return _execute_append_to_note_action(action.details)
    else:
        raise ValueError(f"Unknown action type: {action.action_type}")


def _execute_create_todo_action(details: dict[str, Any]) -> str:
    """Execute a create_todo action."""
    from nb.core.todos import add_todo_to_daily_note, add_todo_to_note

    content = details["content"]
    note_path = details.get("note_path")
    section = details.get("section")

    if note_path:
        config = get_config()
        path = Path(note_path)
        if not path.is_absolute():
            path = config.notes_root / path
        todo = add_todo_to_note(content, path, section=section)
        return f"Created todo in {note_path}: {todo.content}"
    else:
        todo = add_todo_to_daily_note(content)
        return f"Created todo in today's note: {todo.content}"


def _execute_update_todo_action(details: dict[str, Any]) -> str:
    """Execute an update_todo action."""
    from nb.core.todos import (
        delete_todo_from_file,
        remove_todo_due_date,
        set_todo_status_in_file,
        update_todo_due_date,
    )
    from nb.index.todos_repo import get_todo_by_id
    from nb.utils.dates import parse_fuzzy_date_future

    todo_ids = details["todo_ids"]
    status = details.get("status")
    due_date = details.get("due_date")
    delete = details.get("delete", False)

    results = []

    for todo_id in todo_ids:
        # Find the todo
        todo = get_todo_by_id(todo_id)
        if not todo:
            results.append(f"[{todo_id[:6]}] Not found")
            continue

        path = Path(todo.source.path)
        line_number = todo.line_number
        expected_content = todo.content

        try:
            if delete:
                result = delete_todo_from_file(
                    path, line_number, expected_content=expected_content
                )
                if result:
                    results.append(f"[{todo_id[:6]}] Deleted")
                else:
                    results.append(f"[{todo_id[:6]}] Delete failed")
            else:
                # Handle status update
                if status:
                    status_map = {
                        "pending": TodoStatus.PENDING,
                        "in_progress": TodoStatus.IN_PROGRESS,
                        "completed": TodoStatus.COMPLETED,
                    }
                    new_status = status_map.get(status)
                    if new_status:
                        result = set_todo_status_in_file(
                            path,
                            line_number,
                            new_status,
                            expected_content=expected_content,
                        )
                        if result:
                            results.append(f"[{todo_id[:6]}] Status -> {status}")
                        else:
                            results.append(f"[{todo_id[:6]}] Status update failed")

                # Handle due date update
                if due_date:
                    if due_date.lower() == "remove":
                        result = remove_todo_due_date(
                            path, line_number, expected_content=expected_content
                        )
                        if result:
                            results.append(f"[{todo_id[:6]}] Due date removed")
                        else:
                            results.append(f"[{todo_id[:6]}] Due date removal failed")
                    else:
                        # Parse the date
                        parsed_date = parse_fuzzy_date_future(due_date)
                        if parsed_date:
                            result = update_todo_due_date(
                                path,
                                line_number,
                                parsed_date,
                                expected_content=expected_content,
                            )
                            if result:
                                results.append(
                                    f"[{todo_id[:6]}] Due date -> {parsed_date.strftime('%Y-%m-%d')}"
                                )
                            else:
                                results.append(
                                    f"[{todo_id[:6]}] Due date update failed"
                                )
                        else:
                            results.append(
                                f"[{todo_id[:6]}] Could not parse date: {due_date}"
                            )
        except PermissionError as e:
            results.append(f"[{todo_id[:6]}] Permission denied: {e}")
        except Exception as e:
            results.append(f"[{todo_id[:6]}] Error: {e}")

    return "\n".join(results)


def _execute_create_note_action(details: dict[str, Any]) -> str:
    """Execute a create_note action."""
    from nb.core.notes import create_note

    path = details["path"]
    title = details.get("title")
    content = details.get("content", "")
    tags = details.get("tags", [])

    config = get_config()
    note_path = Path(path)
    if not note_path.is_absolute():
        note_path = config.notes_root / note_path

    # Create the note
    created_path = create_note(
        path=note_path,
        title=title or note_path.stem,
        tags=tags if tags else None,
    )

    # Append content if provided
    if content:
        existing = created_path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n\n"):
            if existing.endswith("\n"):
                existing += "\n"
            else:
                existing += "\n\n"
        created_path.write_text(existing + content + "\n", encoding="utf-8")

    return f"Created note: {path}"


def _execute_append_to_note_action(details: dict[str, Any]) -> str:
    """Execute an append_to_note action."""
    note_path_str = details["note_path"]
    content = details["content"]
    section = details.get("section")

    config = get_config()
    note_path = Path(note_path_str)
    if not note_path.is_absolute():
        note_path = config.notes_root / note_path

    if not note_path.exists():
        raise FileNotFoundError(f"Note not found: {note_path_str}")

    existing = note_path.read_text(encoding="utf-8")
    lines = existing.splitlines()

    if section:
        # Find or create section
        section_lower = section.lower()
        section_idx = None

        for i, line in enumerate(lines):
            if line.strip().lower().startswith(f"## {section_lower}"):
                section_idx = i
                break

        if section_idx is not None:
            # Find end of section (next heading or EOF)
            insert_idx = len(lines)
            for i in range(section_idx + 1, len(lines)):
                if lines[i].startswith("## "):
                    insert_idx = i
                    break

            # Insert before next section
            lines.insert(insert_idx, content)
            if insert_idx > 0 and lines[insert_idx - 1].strip():
                lines.insert(insert_idx, "")
        else:
            # Create section at end
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"## {section}")
            lines.append("")
            lines.append(content)
    else:
        # Append at end
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(content)

    note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Appended to {note_path_str}"


# ============================================================================
# Tool Router
# ============================================================================


def execute_assistant_tool(
    tool_call: ToolCall, context: AssistantContext
) -> ToolResult:
    """Execute a tool call and return the result.

    Read tools execute immediately. Write tools are queued for confirmation.

    Args:
        tool_call: The tool call to execute.
        context: The assistant context.

    Returns:
        ToolResult with the output.
    """
    name = tool_call.name
    args = tool_call.arguments

    try:
        # Read-only tools (execute immediately)
        if name == "search_notes":
            result = _execute_search_notes(args, context)
            return ToolResult(tool_call_id=tool_call.id, content=result)

        elif name == "read_note":
            result = _execute_read_note(args, context)
            return ToolResult(tool_call_id=tool_call.id, content=result)

        elif name == "query_todos":
            result = _execute_query_todos(args, context)
            return ToolResult(tool_call_id=tool_call.id, content=result)

        elif name == "get_project_stats":
            result = _execute_get_project_stats(args, context)
            return ToolResult(tool_call_id=tool_call.id, content=result)

        elif name == "get_calendar_events":
            result = _execute_get_calendar(args, context)
            return ToolResult(tool_call_id=tool_call.id, content=result)

        # Write tools (queue for confirmation)
        elif name == "create_todo":
            return _queue_create_todo(args, context, tool_call.id)

        elif name == "update_todo":
            return _queue_update_todo(args, context, tool_call.id)

        elif name == "create_note":
            return _queue_create_note(args, context, tool_call.id)

        elif name == "append_to_note":
            return _queue_append_to_note(args, context, tool_call.id)

        else:
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Unknown tool: {name}",
                is_error=True,
            )

    except Exception as e:
        return ToolResult(
            tool_call_id=tool_call.id,
            content=f"Tool error: {e}",
            is_error=True,
        )
