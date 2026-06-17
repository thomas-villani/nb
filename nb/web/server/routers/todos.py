"""Todo + kanban endpoints (list, create, toggle, status, due)."""

from __future__ import annotations

import json
from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from nb.config import Config
from nb.utils.hashing import normalize_path
from nb.web.server.deps import get_app_config, get_settings
from nb.web.server.settings import AppSettings

router = APIRouter()


@router.get("/api/todos")
def list_todos(
    include_excluded: bool = False,
    settings: AppSettings = Depends(get_settings),
) -> list[dict]:
    """All todos (open by default; completed when the viewer was launched with -c).

    By default todos from notes/links marked ``todo_exclude`` are hidden; pass
    ``include_excluded=true`` to surface them as well.
    """
    from nb.index.todos_repo import get_sorted_todos

    todos = get_sorted_todos(
        completed=None if settings.show_completed else False,
        exclude_note_excluded=not include_excluded,
    )
    today = date_type.today()

    return [
        {
            "id": t.id,
            "content": t.content,
            "due": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority.value if t.priority else None,
            "status": t.status.value,
            "notebook": t.notebook or "unknown",
            "path": (
                normalize_path(t.source.path) if t.source and t.source.path else None
            ),
            "tags": t.tags or [],
            "created": t.created_date.isoformat() if t.created_date else None,
            "isOverdue": (
                t.due_date_only is not None
                and t.due_date_only < today
                and t.status.value != "completed"
            ),
            "isDueToday": t.due_date_only == today,
            "isDueThisWeek": (
                t.due_date_only is not None
                and today < t.due_date_only <= today + timedelta(days=7)
            ),
        }
        for t in todos[:100]
    ]


@router.get("/api/kanban/boards")
def kanban_boards(config: Config = Depends(get_app_config)) -> list[dict]:
    """Kanban board configurations (falls back to the default board)."""
    from nb.config import DEFAULT_KANBAN_COLUMNS

    boards: list[dict] = []
    for b in config.kanban_boards:
        boards.append(
            {
                "name": b.name,
                "columns": [
                    {"name": c.name, "filters": c.filters, "color": c.color}
                    for c in b.columns
                ],
            }
        )

    if not boards:
        boards.append(
            {
                "name": "default",
                "columns": [
                    {"name": c.name, "filters": c.filters, "color": c.color}
                    for c in DEFAULT_KANBAN_COLUMNS
                ],
            }
        )

    return boards


@router.get("/api/kanban/column")
def kanban_column(filters: str = "{}", notebook: str | None = None) -> list[dict]:
    """Todos matching a kanban column's filters."""
    from nb.index.todos_repo import query_todos
    from nb.models import TodoStatus

    try:
        parsed = json.loads(filters)
    except json.JSONDecodeError:
        parsed = {}

    today = date_type.today()

    kwargs: dict = {"parent_only": True, "exclude_note_excluded": True}

    if notebook:
        kwargs["notebooks"] = [notebook]

    status_val = parsed.get("status")
    if status_val:
        kwargs["status"] = TodoStatus(status_val)
    else:
        kwargs["completed"] = False

    if parsed.get("due_today"):
        kwargs["due_start"] = today
        kwargs["due_end"] = today

    if parsed.get("due_this_week"):
        kwargs["due_start"] = today
        kwargs["due_end"] = today + timedelta(days=7)

    if parsed.get("overdue"):
        kwargs["overdue"] = True

    if parsed.get("priority"):
        kwargs["priority"] = parsed["priority"]

    if parsed.get("tags") and len(parsed["tags"]) > 0:
        kwargs["tag"] = parsed["tags"][0]

    todos = query_todos(**kwargs)

    if parsed.get("no_due_date"):
        todos = [t for t in todos if t.due_date is None]

    return [
        {
            "id": t.id,
            "content": t.content,
            "status": t.status.value,
            "due": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority.value if t.priority else None,
            "notebook": t.notebook,
            "tags": t.tags,
        }
        for t in todos[:50]
    ]


@router.post("/api/todos")
def create_todo(body: dict = Body(default={})):
    """Add a new todo to the inbox."""
    content = body.get("content", "").strip()
    if not content:
        return JSONResponse({"error": "Content required"}, status_code=400)

    from nb.core.todos import add_todo_to_inbox

    add_todo_to_inbox(content)
    return {"success": True}


@router.post("/api/todos/{todo_id}/toggle")
def toggle_todo(todo_id: str, config: Config = Depends(get_app_config)):
    """Toggle a todo between completed and pending."""
    from nb.core.todos import toggle_todo_in_file
    from nb.index.todos_repo import get_todo_by_id, update_todo_status
    from nb.models import TodoStatus

    todo = get_todo_by_id(todo_id)
    if not todo:
        return JSONResponse({"error": "Todo not found"}, status_code=404)

    source_path = todo.source.path
    if not source_path.is_absolute():
        source_path = config.notes_root / source_path

    try:
        actual_line = toggle_todo_in_file(
            source_path, todo.line_number, expected_content=todo.content
        )
        if actual_line is None:
            return JSONResponse(
                {"error": "Todo not found at expected location"}, status_code=404
            )
        new_status = TodoStatus.COMPLETED if not todo.completed else TodoStatus.PENDING
        update_todo_status(todo_id, new_status)
        return {"success": True}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)


@router.post("/api/todos/{todo_id}/status")
def set_todo_status(
    todo_id: str,
    body: dict = Body(default={}),
    config: Config = Depends(get_app_config),
):
    """Set a todo's status directly (kanban drag-and-drop)."""
    new_status_str = body.get("status")  # "pending", "in_progress", "completed"
    if not new_status_str:
        return JSONResponse({"error": "Status required"}, status_code=400)

    from nb.core.todos import set_todo_status_in_file
    from nb.index.todos_repo import get_todo_by_id, update_todo_status
    from nb.models import TodoStatus

    try:
        new_status = TodoStatus(new_status_str)
    except ValueError:
        return JSONResponse(
            {"error": f"Invalid status: {new_status_str}"}, status_code=400
        )

    todo = get_todo_by_id(todo_id)
    if not todo:
        return JSONResponse({"error": "Todo not found"}, status_code=404)

    source_path = todo.source.path
    if not source_path.is_absolute():
        source_path = config.notes_root / source_path

    try:
        actual_line = set_todo_status_in_file(
            source_path,
            todo.line_number,
            new_status,
            expected_content=todo.content,
        )
        if actual_line is None:
            return JSONResponse(
                {"error": "Todo not found at expected location"}, status_code=404
            )
        update_todo_status(todo_id, new_status)
        return {"success": True, "status": new_status.value}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)


@router.post("/api/todos/{todo_id}/due")
def set_todo_due(
    todo_id: str,
    body: dict = Body(default={}),
    config: Config = Depends(get_app_config),
):
    """Update or remove a todo's due date."""
    new_date_str = body.get("due")  # ISO date string or null/empty

    from nb.core.todos import remove_todo_due_date, update_todo_due_date
    from nb.index.todos_repo import get_todo_by_id, update_todo_due_date_db

    todo = get_todo_by_id(todo_id)
    if not todo:
        return JSONResponse({"error": "Todo not found"}, status_code=404)

    source_path = todo.source.path
    if not source_path.is_absolute():
        source_path = config.notes_root / source_path

    try:
        if new_date_str:
            new_date = date_type.fromisoformat(new_date_str)
            actual_line = update_todo_due_date(
                source_path,
                todo.line_number,
                new_date,
                expected_content=todo.content,
            )
            if actual_line is None:
                return JSONResponse(
                    {"error": "Todo not found at expected location"}, status_code=404
                )
            update_todo_due_date_db(todo_id, new_date)
        else:
            actual_line = remove_todo_due_date(
                source_path,
                todo.line_number,
                expected_content=todo.content,
            )
            if actual_line is None:
                return JSONResponse(
                    {"error": "Todo not found at expected location"}, status_code=404
                )
            update_todo_due_date_db(todo_id, None)

        return {"success": True}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except ValueError as e:
        return JSONResponse({"error": f"Invalid date: {e}"}, status_code=400)
