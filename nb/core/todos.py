"""Todo extraction and management for nb."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from nb.config import get_config
from nb.models import Attachment, Priority, Todo, TodoSource
from nb.utils.dates import parse_fuzzy_date
from nb.utils.hashing import make_attachment_id, make_todo_id

# Regex patterns for todo parsing
TODO_PATTERN = re.compile(r"^(?P<indent>\s*)- \[(?P<done>[ xX])\] (?P<content>.+)$")
DUE_PATTERN = re.compile(r"@due\((?P<date>[^)]+)\)")
PRIORITY_PATTERN = re.compile(r"@priority\((?P<level>[123])\)")
TAG_PATTERN = re.compile(r"#([^ ]+)")
ATTACH_PATTERN = re.compile(r"^\s*@attach:\s*(.+)$")

# Pattern to detect fenced code blocks
CODE_FENCE_PATTERN = re.compile(r"^```")


def clean_todo_content(content: str) -> str:
    """Remove metadata markers from todo content.

    Removes @due(...), @priority(...), and #tags from the content,
    leaving just the task description.
    """
    # Remove @due(...)
    content = DUE_PATTERN.sub("", content)
    # Remove @priority(...)
    content = PRIORITY_PATTERN.sub("", content)
    # Remove #tags
    content = TAG_PATTERN.sub("", content)
    # Clean up extra whitespace
    content = " ".join(content.split())
    return content.strip()


def parse_due_date(content: str) -> date | None:
    """Extract due date from todo content."""
    match = DUE_PATTERN.search(content)
    if match:
        date_str = match.group("date")
        return parse_fuzzy_date(date_str)
    return None


def parse_priority(content: str) -> Priority | None:
    """Extract priority from todo content."""
    match = PRIORITY_PATTERN.search(content)
    if match:
        level = int(match.group("level"))
        return Priority.from_int(level)
    return None


def parse_tags(content: str) -> list[str]:
    """Extract tags from todo content."""
    return [tag.lower() for tag in TAG_PATTERN.findall(content)]


def extract_todos(
    path: Path,
    source_type: str = "note",
    external: bool = False,
    alias: str | None = None,
    notes_root: Path | None = None,
) -> list[Todo]:
    """Extract all todos from a markdown file.

    Args:
        path: Path to the markdown file
        source_type: Type of source ("note", "inbox", "linked")
        external: Whether this is an external file
        alias: Optional alias for linked files
        notes_root: Notes root for determining project

    Returns:
        List of Todo objects with hierarchy built.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if not path.exists():
        return []

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    todos: list[Todo] = []
    stack: list[tuple[int, Todo]] = []  # (indent_level, todo)
    in_code_block = False
    current_todo: Todo | None = None
    current_todo_indent: int = 0  # Track indent of current todo for details capture
    details_lines: list[str] = []  # Accumulate details lines

    # Determine project (notebook) from path
    from nb.core.notebooks import get_notebook_for_file

    project = get_notebook_for_file(path)

    # Get created date from file or parse from filename
    from nb.utils.dates import parse_date_from_filename

    created_date = parse_date_from_filename(path.name) or date.today()

    source = TodoSource(
        type=source_type,  # type: ignore
        path=path,
        external=external,
        alias=alias,
    )

    def finalize_details() -> None:
        """Save accumulated details to current todo."""
        nonlocal details_lines, current_todo
        if current_todo and details_lines:
            current_todo.details = "\n".join(details_lines)
            details_lines = []

    for line_num, line in enumerate(lines, 1):
        # Track code blocks
        if CODE_FENCE_PATTERN.match(line):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        # Check for attachment line (belongs to previous todo)
        attach_match = ATTACH_PATTERN.match(line)
        if attach_match and current_todo:
            attach_path = attach_match.group(1).strip()
            attachment = Attachment(
                id=make_attachment_id(attach_path, "todo", current_todo.id),
                type="file" if not attach_path.startswith("http") else "url",
                path=attach_path,
                title=None,
                added_date=date.today(),
                copied=False,
            )
            current_todo.attachments.append(attachment)
            continue

        # Check for todo line
        match = TODO_PATTERN.match(line)
        if not match:
            # Not a todo line - check if it's a details line for current todo
            if current_todo and line.strip():
                # Calculate line's indentation
                line_indent = len(line) - len(line.lstrip())
                # If indented more than the todo, it's part of the details
                if line_indent > current_todo_indent:
                    details_lines.append(line.rstrip())
            continue

        # Found a new todo - finalize details for previous todo
        finalize_details()

        indent = len(match.group("indent"))
        done = match.group("done").lower() == "x"
        raw_content = match.group("content")

        # Parse metadata
        clean_content = clean_todo_content(raw_content)
        due_date = parse_due_date(raw_content)
        priority = parse_priority(raw_content)
        tags = parse_tags(raw_content)

        todo = Todo(
            id=make_todo_id(path, clean_content),
            content=clean_content,
            raw_content=raw_content,
            completed=done,
            source=source,
            line_number=line_num,
            created_date=created_date,
            due_date=due_date,
            priority=priority,
            tags=tags,
            project=project,
            parent_id=None,
            children=[],
            attachments=[],
        )

        # Handle nesting - find parent based on indentation
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if stack:
            parent_indent, parent_todo = stack[-1]
            todo.parent_id = parent_todo.id
            parent_todo.children.append(todo)

        stack.append((indent, todo))
        todos.append(todo)
        current_todo = todo
        current_todo_indent = indent

    # Finalize details for the last todo
    finalize_details()

    return todos


def can_toggle_linked_file(path: Path) -> bool:
    """Check if a linked file can be toggled (sync is enabled).

    Args:
        path: Path to check.

    Returns:
        True if the file can be modified, False if it's a linked file with sync disabled.

    """
    from nb.core.links import get_linked_note_by_path, list_linked_notes

    # Check if this exact path is a linked note
    linked = get_linked_note_by_path(path)
    if linked is not None:
        return linked.sync

    # Check if this file is inside a linked directory
    path = path.resolve()
    for ln in list_linked_notes():
        if ln.path.is_dir():
            try:
                path.relative_to(ln.path)
                # File is inside this linked directory
                return ln.sync
            except ValueError:
                continue

    # Not a linked file, so it's fine to toggle
    return True


def toggle_todo_in_file(
    path: Path,
    line_number: int,
    check_linked_sync: bool = True,
) -> bool:
    """Toggle a todo's completion status in its source file.

    Args:
        path: Path to the file
        line_number: 1-based line number of the todo
        check_linked_sync: Whether to check if linked file allows sync

    Returns:
        True if successfully toggled, False otherwise.

    Raises:
        PermissionError: If the file is a linked file with sync disabled.

    """
    if not path.exists():
        return False

    # Check if we're allowed to modify this file
    if check_linked_sync and not can_toggle_linked_file(path):
        raise PermissionError(f"Cannot modify linked file (sync disabled): {path.name}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    if line_number < 1 or line_number > len(lines):
        return False

    line = lines[line_number - 1]
    match = TODO_PATTERN.match(line)

    if not match:
        return False

    done = match.group("done")

    if done.lower() == "x":
        # Mark as incomplete
        new_line = line.replace("[x]", "[ ]").replace("[X]", "[ ]")
    else:
        # Mark as complete
        new_line = line.replace("[ ]", "[x]")

    lines[line_number - 1] = new_line

    # Write back
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def add_todo_to_inbox(text: str, notes_root: Path | None = None) -> Todo:
    """Add a new todo to the inbox (todo.md).

    Args:
        text: The todo text (can include @due, @priority, #tags)
        notes_root: Override notes root directory

    Returns:
        The created Todo object.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    inbox_path = notes_root / "todo.md"

    # Create inbox if it doesn't exist
    if not inbox_path.exists():
        inbox_path.write_text("# Todo Inbox\n\n", encoding="utf-8")

    # Read current content
    content = inbox_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find line number for new todo
    line_number = len(lines) + 1

    # Append the todo
    with open(inbox_path, "a", encoding="utf-8") as f:
        f.write(f"- [ ] {text}\n")

    # Create and return Todo object
    clean_content = clean_todo_content(text)

    source = TodoSource(
        type="inbox",
        path=inbox_path,
        external=False,
        alias=None,
    )

    return Todo(
        id=make_todo_id(inbox_path, clean_content),
        content=clean_content,
        raw_content=text,
        completed=False,
        source=source,
        line_number=line_number,
        created_date=date.today(),
        due_date=parse_due_date(text),
        priority=parse_priority(text),
        tags=parse_tags(text),
        project=None,
        parent_id=None,
        children=[],
        attachments=[],
    )


def get_inbox_path(notes_root: Path | None = None) -> Path:
    """Get the path to the todo inbox file."""
    if notes_root is None:
        notes_root = get_config().notes_root
    return notes_root / "todo.md"


def add_todo_to_daily_note(text: str, dt: date | None = None) -> Todo:
    """Add a new todo to a daily note.

    Args:
        text: The todo text (can include @due, @priority, #tags)
        dt: The date of the daily note (defaults to today)

    Returns:
        The created Todo object.

    """
    from nb.core.notes import ensure_daily_note

    if dt is None:
        dt = date.today()

    # Get the daily note path (creates if needed)
    note_path = ensure_daily_note(dt)

    # Read current content
    content = note_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find line number for new todo
    line_number = len(lines) + 1

    # Append the todo
    with open(note_path, "a", encoding="utf-8") as f:
        f.write(f"- [ ] {text}\n")

    # Create and return Todo object
    clean_content = clean_todo_content(text)

    source = TodoSource(
        type="note",
        path=note_path,
        external=False,
        alias=None,
    )

    return Todo(
        id=make_todo_id(note_path, clean_content),
        content=clean_content,
        raw_content=text,
        completed=False,
        source=source,
        line_number=line_number,
        created_date=dt,
        due_date=parse_due_date(text),
        priority=parse_priority(text),
        tags=parse_tags(text),
        project="daily",
        parent_id=None,
        children=[],
        attachments=[],
    )
