"""Todo database operations for nb."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from nb.index.db import get_db
from nb.models import Priority, Todo, TodoSource, TodoStatus
from nb.utils.hashing import normalize_path


def _row_to_todo(row) -> Todo:
    """Convert a database row to a Todo object."""
    source = TodoSource(
        type=row["source_type"],
        path=Path(row["source_path"]),
        external=bool(row["source_external"]),
        alias=row["source_alias"],
    )

    # Handle status from DB, with fallback to completed for unmigrated data
    if "status" in row.keys() and row["status"]:
        status = TodoStatus(row["status"])
    else:
        # Fallback for old data without status column
        status = TodoStatus.COMPLETED if row["completed"] else TodoStatus.PENDING

    return Todo(
        id=row["id"],
        content=row["content"],
        raw_content=row["raw_content"],
        status=status,
        source=source,
        line_number=row["line_number"],
        created_date=(
            date.fromisoformat(row["created_date"])
            if row["created_date"]
            else date.today()
        ),
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        priority=Priority.from_int(row["priority"]) if row["priority"] else None,
        tags=[],  # Loaded separately
        notebook=row["project"],  # DB column is 'project'
        parent_id=row["parent_id"],
        children=[],  # Loaded separately if needed
        attachments=[],  # Loaded separately if needed
        details=row["details"] if "details" in row.keys() else None,
        section=row["section"] if "section" in row.keys() else None,
    )


def _load_todo_tags(todo_id: str) -> list[str]:
    """Load tags for a todo from the database."""
    db = get_db()
    rows = db.fetchall("SELECT tag FROM todo_tags WHERE todo_id = ?", (todo_id,))
    return [row["tag"] for row in rows]


def upsert_todo(todo: Todo) -> None:
    """Insert or update a todo in the database.

    Preserves created_date for existing todos.
    """
    db = get_db()

    # Check if todo already exists to preserve created_date
    existing = db.fetchone("SELECT created_date FROM todos WHERE id = ?", (todo.id,))
    if existing and existing["created_date"]:
        # Preserve the original created_date
        created_date = existing["created_date"]
    else:
        # New todo - use the provided date or today
        created_date = (
            todo.created_date.isoformat()
            if todo.created_date
            else date.today().isoformat()
        )

    db.execute(
        """
        INSERT OR REPLACE INTO todos (
            id, content, raw_content, completed, status, source_type, source_path,
            source_external, source_alias, line_number, created_date,
            due_date, priority, project, parent_id, content_hash, details, section
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            todo.id,
            todo.content,
            todo.raw_content,
            1 if todo.completed else 0,  # Keep completed for backwards compat
            todo.status.value,
            todo.source.type,
            normalize_path(todo.source.path),
            1 if todo.source.external else 0,
            todo.source.alias,
            todo.line_number,
            created_date,
            todo.due_date.isoformat() if todo.due_date else None,
            todo.priority.value if todo.priority else None,
            todo.notebook,
            todo.parent_id,
            None,  # content_hash not used currently
            todo.details,
            todo.section,
        ),
    )

    # Update tags
    db.execute("DELETE FROM todo_tags WHERE todo_id = ?", (todo.id,))
    if todo.tags:
        db.executemany(
            "INSERT INTO todo_tags (todo_id, tag) VALUES (?, ?)",
            [(todo.id, tag) for tag in todo.tags],
        )

    db.commit()


def get_todo_by_id(todo_id: str) -> Todo | None:
    """Get a todo by its ID."""
    db = get_db()
    row = db.fetchone("SELECT * FROM todos WHERE id = ?", (todo_id,))

    if not row:
        return None

    todo = _row_to_todo(row)
    todo.tags = _load_todo_tags(todo_id)
    return todo


def delete_todo(todo_id: str) -> None:
    """Delete a todo from the database."""
    db = get_db()
    db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    db.commit()


def delete_todos_for_source(source_path: Path) -> None:
    """Delete all todos from a specific source file.

    Handles both normalized (forward slashes) and legacy (backslashes) paths
    for backward compatibility with existing data.
    """
    db = get_db()
    normalized = normalize_path(source_path)
    # Also try the original str() representation for legacy data
    legacy = str(source_path)

    if normalized != legacy:
        # Delete both normalized and legacy paths
        db.execute(
            "DELETE FROM todos WHERE source_path = ? OR source_path = ?",
            (normalized, legacy),
        )
    else:
        db.execute("DELETE FROM todos WHERE source_path = ?", (normalized,))
    db.commit()


def update_todo_completion(todo_id: str, completed: bool) -> None:
    """Update a todo's completion status.

    This also updates the status column for consistency.
    """
    db = get_db()
    status = TodoStatus.COMPLETED if completed else TodoStatus.PENDING
    db.execute(
        "UPDATE todos SET completed = ?, status = ? WHERE id = ?",
        (1 if completed else 0, status.value, todo_id),
    )
    db.commit()


def update_todo_status(todo_id: str, status: TodoStatus) -> None:
    """Update a todo's status.

    This also updates the completed column for backwards compatibility.
    """
    db = get_db()
    completed = 1 if status == TodoStatus.COMPLETED else 0
    db.execute(
        "UPDATE todos SET status = ?, completed = ? WHERE id = ?",
        (status.value, completed, todo_id),
    )
    db.commit()


def query_todos(
    completed: bool | None = None,
    status: TodoStatus | None = None,
    include_in_progress: bool = True,
    due_start: date | None = None,
    due_end: date | None = None,
    created_start: date | None = None,
    created_end: date | None = None,
    overdue: bool = False,
    priority: int | None = None,
    notebooks: list[str] | None = None,
    notes: list[str] | None = None,
    exclude_notebooks: list[str] | None = None,
    tag: str | None = None,
    exclude_tags: list[str] | None = None,
    source_path: Path | None = None,
    parent_only: bool = True,
    exclude_note_excluded: bool = True,
) -> list[Todo]:
    """Query todos with filters.

    Args:
        completed: Filter by completion status (backwards compat, prefer status)
        status: Filter by specific TodoStatus
        include_in_progress: When completed=False, also include in_progress todos
        due_start: Filter by due date >= this
        due_end: Filter by due date <= this
        created_start: Filter by created date >= this
        created_end: Filter by created date <= this
        overdue: Only include overdue todos
        priority: Filter by priority level (1, 2, or 3)
        notebooks: Filter by notebook names (stored as project in DB)
        notes: Filter by specific note paths (relative to notes root)
        exclude_notebooks: List of notebooks to exclude
        tag: Filter by tag
        exclude_tags: List of tags to exclude
        source_path: Filter by source file path
        parent_only: If True, only return top-level todos (not subtasks)
        exclude_note_excluded: If True, exclude todos from notes with todo_exclude=true

    Returns:
        List of matching Todo objects.

    """
    db = get_db()

    sql = "SELECT DISTINCT t.* FROM todos t"
    params: list = []
    conditions: list[str] = []
    joins: list[str] = []

    # Join with tags if filtering by tag
    if tag:
        joins.append("JOIN todo_tags tt ON t.id = tt.todo_id")
        conditions.append("tt.tag = ?")
        params.append(tag.lower())

    # Join with notes if filtering by note-level todo_exclude
    if exclude_note_excluded:
        joins.append("LEFT JOIN notes n ON t.source_path = n.path")
        conditions.append("(n.todo_exclude IS NULL OR n.todo_exclude = 0)")

    # Add joins to SQL
    if joins:
        sql += " " + " ".join(joins)

    # Filter conditions
    # Prefer status over completed if both provided
    if status is not None:
        conditions.append("t.status = ?")
        params.append(status.value)
    elif completed is not None:
        if completed:
            conditions.append("t.status = ?")
            params.append(TodoStatus.COMPLETED.value)
        else:
            # Not completed means pending or in_progress
            if include_in_progress:
                conditions.append("t.status IN (?, ?)")
                params.append(TodoStatus.PENDING.value)
                params.append(TodoStatus.IN_PROGRESS.value)
            else:
                conditions.append("t.status = ?")
                params.append(TodoStatus.PENDING.value)

    if due_start:
        conditions.append("t.due_date >= ?")
        params.append(due_start.isoformat())

    if due_end:
        conditions.append("t.due_date <= ?")
        params.append(due_end.isoformat())

    if created_start:
        conditions.append("t.created_date >= ?")
        params.append(created_start.isoformat())

    if created_end:
        conditions.append("t.created_date <= ?")
        params.append(created_end.isoformat())

    if overdue:
        conditions.append("t.due_date < ? AND t.status != ?")
        params.append(date.today().isoformat())
        params.append(TodoStatus.COMPLETED.value)

    if priority:
        conditions.append("t.priority = ?")
        params.append(priority)

    # Filter by notebooks
    if notebooks:
        placeholders = ", ".join("?" for _ in notebooks)
        conditions.append(f"t.project IN ({placeholders})")
        params.extend(notebooks)

    # Handle notes filter (matches source_path containing the note path)
    if notes:
        note_conditions = []
        for note_path in notes:
            # Check if this looks like a full/absolute path (contains drive letter or starts with /)
            is_full_path = (
                len(note_path) > 2 and note_path[1] == ":"  # Windows: C:/...
            ) or note_path.startswith(
                "/"
            )  # Unix: /home/...

            if is_full_path:
                # For full paths (linked notes), match the path prefix
                # This allows matching files within a linked directory
                note_conditions.append("(t.source_path = ? OR t.source_path LIKE ?)")
                # Exact match for files
                if note_path.endswith(".md"):
                    params.append(note_path)
                else:
                    params.append(f"{note_path}.md")
                # Prefix match for directories (files within the linked dir)
                params.append(f"{note_path}/%")
            else:
                # Match notes by path ending (e.g., "daily/2025-01-01" matches ".../daily/2025-01-01.md")
                note_conditions.append("t.source_path LIKE ?")
                # Handle both with and without .md extension
                if note_path.endswith(".md"):
                    params.append(f"%{note_path}")
                else:
                    params.append(f"%{note_path}.md")
        conditions.append(f"({' OR '.join(note_conditions)})")

    if exclude_notebooks:
        placeholders = ", ".join("?" for _ in exclude_notebooks)
        conditions.append(f"(t.project IS NULL OR t.project NOT IN ({placeholders}))")
        params.extend(exclude_notebooks)

    if exclude_tags:
        # Exclude todos that have any of the specified tags
        placeholders = ", ".join("?" for _ in exclude_tags)
        conditions.append(
            f"NOT EXISTS (SELECT 1 FROM todo_tags et WHERE et.todo_id = t.id AND et.tag IN ({placeholders}))"
        )
        params.extend([t.lower() for t in exclude_tags])

    if source_path:
        conditions.append("t.source_path = ?")
        params.append(normalize_path(source_path))

    if parent_only:
        conditions.append("t.parent_id IS NULL")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    rows = db.fetchall(sql, tuple(params))

    todos = []
    for row in rows:
        todo = _row_to_todo(row)
        todo.tags = _load_todo_tags(todo.id)
        todos.append(todo)

    return todos


def get_todo_children(parent_id: str) -> list[Todo]:
    """Get child todos of a parent."""
    db = get_db()
    rows = db.fetchall(
        "SELECT * FROM todos WHERE parent_id = ? ORDER BY line_number",
        (parent_id,),
    )

    children = []
    for row in rows:
        todo = _row_to_todo(row)
        todo.tags = _load_todo_tags(todo.id)
        # Recursively load children
        todo.children = get_todo_children(todo.id)
        children.append(todo)

    return children


def get_sorted_todos(
    completed: bool | None = False,
    tag: str | None = None,
    exclude_tags: list[str] | None = None,
    notebooks: list[str] | None = None,
    notes: list[str] | None = None,
    exclude_notebooks: list[str] | None = None,
    priority: int | None = None,
    due_start: date | None = None,
    due_end: date | None = None,
    created_start: date | None = None,
    created_end: date | None = None,
    exclude_note_excluded: bool = True,
) -> list[Todo]:
    """Get todos sorted by the default sorting order.

    Sorting order:
    1. Overdue (oldest first)
    2. In Progress (by due date, then created date)
    3. Due today
    4. Due this week (by date)
    5. Due later (by date)
    6. No due date (by created date, oldest first)

    Within each group, secondary sort by priority (1 > 2 > 3 > none).
    """
    todos = query_todos(
        completed=completed,
        tag=tag,
        exclude_tags=exclude_tags,
        notebooks=notebooks,
        notes=notes,
        exclude_notebooks=exclude_notebooks,
        priority=priority,
        due_start=due_start,
        due_end=due_end,
        created_start=created_start,
        created_end=created_end,
        parent_only=True,
        exclude_note_excluded=exclude_note_excluded,
    )

    today = date.today()

    def sort_key(todo: Todo) -> tuple:
        # Group: 0=overdue, 1=in_progress, 2=today, 3=this week, 4=later, 5=no due date
        # In-progress todos get their own group (1) regardless of due date
        if todo.in_progress:
            group = 1
            date_key = todo.due_date or todo.created_date or today
        elif todo.due_date is None:
            group = 5
            date_key = todo.created_date or today
        elif todo.due_date < today:
            group = 0
            date_key = todo.due_date
        elif todo.due_date == today:
            group = 2
            date_key = todo.due_date
        elif (todo.due_date - today).days <= 7:
            group = 3
            date_key = todo.due_date
        else:
            group = 4
            date_key = todo.due_date

        # Priority: 1, 2, 3, then 999 for no priority
        priority_key = todo.priority.value if todo.priority else 999

        # line_number preserves document order for todos from the same source
        return (group, date_key, priority_key, todo.line_number)

    return sorted(todos, key=sort_key)


def get_todo_stats() -> dict[str, int]:
    """Get todo statistics."""
    db = get_db()

    total = db.fetchone("SELECT COUNT(*) as count FROM todos WHERE parent_id IS NULL")
    completed = db.fetchone(
        "SELECT COUNT(*) as count FROM todos WHERE parent_id IS NULL AND status = ?",
        (TodoStatus.COMPLETED.value,),
    )
    in_progress = db.fetchone(
        "SELECT COUNT(*) as count FROM todos WHERE parent_id IS NULL AND status = ?",
        (TodoStatus.IN_PROGRESS.value,),
    )
    overdue = db.fetchone(
        "SELECT COUNT(*) as count FROM todos WHERE parent_id IS NULL AND status != ? AND due_date < ?",
        (TodoStatus.COMPLETED.value, date.today().isoformat()),
    )
    due_today = db.fetchone(
        "SELECT COUNT(*) as count FROM todos WHERE parent_id IS NULL AND status != ? AND due_date = ?",
        (TodoStatus.COMPLETED.value, date.today().isoformat()),
    )

    return {
        "total": total["count"] if total else 0,
        "completed": completed["count"] if completed else 0,
        "in_progress": in_progress["count"] if in_progress else 0,
        "open": (total["count"] if total else 0)
        - (completed["count"] if completed else 0),
        "overdue": overdue["count"] if overdue else 0,
        "due_today": due_today["count"] if due_today else 0,
    }
