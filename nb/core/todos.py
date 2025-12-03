"""Todo extraction and management for nb."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from nb.config import get_config
from nb.models import Attachment, Priority, Todo, TodoSource, TodoStatus
from nb.utils.dates import format_datetime, is_relative_date, parse_fuzzy_datetime
from nb.utils.hashing import make_attachment_id, make_todo_id

# Regex patterns for todo parsing
# Captures: [ ] pending, [x]/[X] completed, [^] in progress
TODO_PATTERN = re.compile(r"^(?P<indent>\s*)- \[(?P<state>[ xX^])\] (?P<content>.+)$")
DUE_PATTERN = re.compile(r"@due\((?P<date>[^)]+)\)")
PRIORITY_PATTERN = re.compile(r"@priority\((?P<level>[123])\)")
TAG_PATTERN = re.compile(r"#([^ ]+)")
ATTACH_PATTERN = re.compile(r"^\s*@attach:\s*(.+)$")

# Pattern to detect fenced code blocks
CODE_FENCE_PATTERN = re.compile(r"^```")

# Patterns for section heading detection
# Markdown headings: # H1, ## H2, ### H3, etc.
HEADING_PATTERN = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.+)$")
# Colon labels: any non-todo line ending with : (e.g., "Morning:", "Installation:")
COLON_LABEL_PATTERN = re.compile(r"^(?P<text>[^:\n]+):$")


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


def parse_due_date(content: str) -> datetime | None:
    """Extract due date (with optional time) from todo content."""
    match = DUE_PATTERN.search(content)
    if match:
        date_str = match.group("date")
        return parse_fuzzy_datetime(date_str)
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
    notebook: str | None = None,
) -> list[Todo]:
    """Extract all todos from a markdown file.

    Args:
        path: Path to the markdown file
        source_type: Type of source ("note", "inbox", "linked")
        external: Whether this is an external file
        alias: Optional alias for linked files
        notes_root: Notes root for determining project
        notebook: Override notebook/project name (for linked notes)

    Returns:
        List of Todo objects with hierarchy built.
        Todos inherit tags from note frontmatter in addition to inline tags.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if not path.exists():
        return []

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Extract tags from note frontmatter only to inherit to todos
    # (Inline body tags are parsed per-todo, not inherited to all todos)
    note_tags: list[str] = []
    try:
        from nb.utils.markdown import parse_note_file

        meta, _ = parse_note_file(path)
        # Only extract frontmatter tags, not inline body tags
        if "tags" in meta:
            fm_tags = meta["tags"]
            if isinstance(fm_tags, list):
                note_tags = [str(t).lower() for t in fm_tags]
            elif isinstance(fm_tags, str):
                note_tags = [t.strip().lower() for t in fm_tags.split(",") if t.strip()]
    except Exception:
        pass  # If frontmatter parsing fails, continue without inherited tags

    todos: list[Todo] = []
    stack: list[tuple[int, Todo]] = []  # (indent_level, todo)
    in_code_block = False
    current_todo: Todo | None = None
    current_todo_indent: int = 0  # Track indent of current todo for details capture
    details_lines: list[str] = []  # Accumulate details lines
    current_section: str | None = None  # Track current section heading
    first_heading_seen = False  # Track if we've seen the title heading

    # Determine project (notebook) from path, or use override
    project: str | None
    if notebook:
        project = notebook
    else:
        from nb.core.notebooks import get_notebook_for_file

        project = get_notebook_for_file(path)

    # Determine path-based sections (subdirectory hierarchy)
    from nb.core.notes import get_sections_for_path

    try:
        relative_path = path.relative_to(notes_root)
    except ValueError:
        relative_path = path
    note_sections = get_sections_for_path(relative_path)

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

        # Check for section headings (before checking for todos)
        # Markdown heading pattern: # H1, ## H2, ### H3, etc.
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            heading_text = heading_match.group("text").strip()
            if heading_text:  # Ignore empty headings
                if not first_heading_seen:
                    # Skip the first heading (title) - it's redundant as section
                    first_heading_seen = True
                else:
                    current_section = heading_text
            continue

        # Colon label pattern: "Label:" (only non-indented, non-todo lines)
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith("-"):
            colon_match = COLON_LABEL_PATTERN.match(stripped_line)
            if colon_match:
                label_text = colon_match.group("text").strip()
                if label_text:  # Ignore empty labels
                    current_section = label_text
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
        state_marker = match.group("state")
        status = TodoStatus.from_marker(state_marker)
        raw_content = match.group("content")

        # Parse metadata
        clean_content = clean_todo_content(raw_content)
        due_date = parse_due_date(raw_content)
        priority = parse_priority(raw_content)
        inline_tags = parse_tags(raw_content)
        # Merge inherited note tags with inline tags (deduplicated)
        all_tags = list(dict.fromkeys(note_tags + inline_tags))

        todo = Todo(
            id=make_todo_id(path, clean_content),
            content=clean_content,
            raw_content=raw_content,
            status=status,
            source=source,
            line_number=line_num,
            created_date=created_date,
            due_date=due_date,
            priority=priority,
            tags=all_tags,
            notebook=project,  # Local var is 'project' for legacy reasons
            parent_id=None,
            children=[],
            attachments=[],
            section=current_section,
            sections=note_sections,  # Path-based subdirectory sections
        )

        # Handle nesting - find parent based on indentation
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if stack:
            _parent_indent, parent_todo = stack[-1]
            todo.parent_id = parent_todo.id
            parent_todo.children.append(todo)

        stack.append((indent, todo))
        todos.append(todo)
        current_todo = todo
        current_todo_indent = indent

    # Finalize details for the last todo
    finalize_details()

    return todos


def find_todo_line(
    lines: list[str],
    expected_line: int,
    expected_content: str,
    search_radius: int = 10,
) -> int | None:
    """Find the actual line number of a todo by content, searching near expected line.

    When files are modified, stored line numbers can become stale. This function
    verifies the content at the expected line and searches nearby if it doesn't match.

    Args:
        lines: List of file lines (from splitlines())
        expected_line: 1-based line number where the todo was expected
        expected_content: The cleaned todo content to match
        search_radius: How many lines above/below to search (default 10)

    Returns:
        1-based line number where the todo was found, or None if not found.
    """
    # First check the expected line
    if 1 <= expected_line <= len(lines):
        line = lines[expected_line - 1]
        match = TODO_PATTERN.match(line)
        if match and clean_todo_content(match.group("content")) == expected_content:
            return expected_line

    # Search nearby lines, alternating above and below
    for offset in range(1, search_radius + 1):
        for candidate_line in [expected_line - offset, expected_line + offset]:
            if 1 <= candidate_line <= len(lines):
                line = lines[candidate_line - 1]
                match = TODO_PATTERN.match(line)
                if (
                    match
                    and clean_todo_content(match.group("content")) == expected_content
                ):
                    return candidate_line

    return None


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
    expected_content: str | None = None,
) -> int | None:
    """Toggle a todo's completion status in its source file.

    Cycles through: pending -> completed -> pending
    (Does not affect in-progress status - use set_todo_status_in_file for that)

    Args:
        path: Path to the file
        line_number: 1-based line number of the todo (may be stale)
        check_linked_sync: Whether to check if linked file allows sync
        expected_content: If provided, verifies/finds the todo by content.
            This handles cases where line numbers become stale due to file edits.

    Returns:
        The actual line number where the todo was toggled, or None if failed.

    Raises:
        PermissionError: If the file is a linked file with sync disabled.

    """
    if not path.exists():
        return None

    # Check if we're allowed to modify this file
    if check_linked_sync and not can_toggle_linked_file(path):
        raise PermissionError(f"Cannot modify linked file (sync disabled): {path.name}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find the actual line number (may differ from stored if file was edited)
    if expected_content:
        actual_line = find_todo_line(lines, line_number, expected_content)
        if actual_line is None:
            return None
    else:
        # Fall back to trusting the line number (legacy behavior)
        if line_number < 1 or line_number > len(lines):
            return None
        actual_line = line_number

    line = lines[actual_line - 1]
    match = TODO_PATTERN.match(line)

    if not match:
        return None

    state = match.group("state")

    if state.lower() == "x":
        # Mark as incomplete (pending)
        new_line = line.replace("[x]", "[ ]").replace("[X]", "[ ]")
    elif state == "^":
        # In-progress -> completed
        new_line = line.replace("[^]", "[x]")
    else:
        # Pending -> completed
        new_line = line.replace("[ ]", "[x]")

    lines[actual_line - 1] = new_line

    # Write back
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return actual_line


def set_todo_status_in_file(
    path: Path,
    line_number: int,
    new_status: TodoStatus,
    check_linked_sync: bool = True,
    expected_content: str | None = None,
) -> int | None:
    """Set a todo's status to a specific state in its source file.

    Args:
        path: Path to the file
        line_number: 1-based line number of the todo (may be stale)
        new_status: The status to set
        check_linked_sync: Whether to check if linked file allows sync
        expected_content: If provided, verifies/finds the todo by content.
            This handles cases where line numbers become stale due to file edits.

    Returns:
        The actual line number where the todo was updated, or None if failed.

    Raises:
        PermissionError: If the file is a linked file with sync disabled.

    """
    if not path.exists():
        return None

    # Check if we're allowed to modify this file
    if check_linked_sync and not can_toggle_linked_file(path):
        raise PermissionError(f"Cannot modify linked file (sync disabled): {path.name}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find the actual line number (may differ from stored if file was edited)
    if expected_content:
        actual_line = find_todo_line(lines, line_number, expected_content)
        if actual_line is None:
            return None
    else:
        # Fall back to trusting the line number (legacy behavior)
        if line_number < 1 or line_number > len(lines):
            return None
        actual_line = line_number

    line = lines[actual_line - 1]
    match = TODO_PATTERN.match(line)

    if not match:
        return None

    # Replace the checkbox marker with the new status marker
    new_marker = new_status.marker
    # Match any of the three markers and replace
    new_line = re.sub(r"\[[ xX^]\]", f"[{new_marker}]", line, count=1)

    lines[actual_line - 1] = new_line

    # Write back
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return actual_line


def add_todo_to_inbox(text: str, notes_root: Path | None = None) -> Todo:
    """Add a new todo to the inbox (todo.md).

    Args:
        text: The todo text (can include @due, @priority, #tags)
        notes_root: Override notes root directory

    Returns:
        The created Todo object.

    """
    if notes_root is None:
        config = get_config()
        notes_root = config.notes_root
    else:
        config = get_config()

    inbox_path = notes_root / config.todo.inbox_file

    # Create inbox if it doesn't exist
    if not inbox_path.exists():
        inbox_path.write_text("# Todo Inbox\n\n", encoding="utf-8")

    # Read current content
    content = inbox_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find line number for new todo
    line_number = len(lines) + 1

    # Append the todo
    with inbox_path.open("a", encoding="utf-8") as f:
        f.write(f"- [ ] {text}\n")

    # Create and return Todo object
    clean_content = clean_todo_content(text)

    source = TodoSource(
        type="inbox",
        path=inbox_path,
        external=False,
        alias=None,
    )

    todo = Todo(
        id=make_todo_id(inbox_path, clean_content),
        content=clean_content,
        raw_content=text,
        status=TodoStatus.PENDING,
        source=source,
        line_number=line_number,
        created_date=date.today(),
        due_date=parse_due_date(text),
        priority=parse_priority(text),
        tags=parse_tags(text),
        notebook=None,
        parent_id=None,
        children=[],
        attachments=[],
        section=None,
    )

    # Insert into database immediately
    from nb.index.todos_repo import upsert_todos_batch

    upsert_todos_batch([todo])

    return todo


def get_inbox_path(notes_root: Path | None = None) -> Path:
    """Get the path to the todo inbox file."""
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root
    return notes_root / config.todo.inbox_file


def find_matching_sections(
    note_path: Path,
    section_query: str,
) -> list[tuple[int, str]]:
    """Find sections in a note that match the given query.

    Args:
        note_path: Path to the note file.
        section_query: The section name to search for (supports partial matching).

    Returns:
        List of (line_index, section_name) tuples for matching sections.
        Returns exact matches first, then partial prefix matches.

    """
    if not note_path.exists():
        return []

    content = note_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    section_lower = section_query.lower()
    all_sections: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        # Check if this is a markdown heading
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            heading_text = heading_match.group("text").strip()
            if heading_text:
                all_sections.append((i, heading_text))
            continue

        # Also check for colon labels
        stripped = line.strip()
        if stripped and not stripped.startswith("-"):
            colon_match = COLON_LABEL_PATTERN.match(stripped)
            if colon_match:
                label = colon_match.group("text").strip()
                if label:
                    all_sections.append((i, label))

    # First check for exact matches (case-insensitive)
    exact_matches = [
        (idx, name) for idx, name in all_sections if name.lower() == section_lower
    ]
    if exact_matches:
        return exact_matches

    # Check for partial prefix matches (case-insensitive)
    partial_matches = [
        (idx, name)
        for idx, name in all_sections
        if name.lower().startswith(section_lower)
    ]
    return partial_matches


def add_todo_to_note(
    text: str,
    note_path: Path,
    section: str | None = None,
    notes_root: Path | None = None,
) -> Todo:
    """Add a todo to a specific note, optionally under a section heading.

    Args:
        text: The todo text (can include @due, @priority, #tags)
        note_path: Path to the note (absolute or relative to notes_root)
        section: Optional section heading to add todo under (case-insensitive)
        notes_root: Override notes root directory

    Returns:
        The created Todo object.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    # Resolve path
    if not note_path.is_absolute():
        full_path = notes_root / note_path
    else:
        full_path = note_path

    if not full_path.exists():
        raise FileNotFoundError(f"Note not found: {note_path}")

    # Read current content
    content = full_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Determine where to insert the todo
    if section:
        # Find the section heading (case-insensitive, supports partial matching)
        section_lower = section.lower()
        section_line_idx = None
        next_heading_idx = None
        matched_section_name = section  # Track actual matched section name

        # Collect all section headings with their line indices
        all_sections: list[tuple[int, str]] = []  # (line_idx, section_name)

        for i, line in enumerate(lines):
            # Check if this is a markdown heading
            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                heading_text = heading_match.group("text").strip()
                if heading_text:
                    all_sections.append((i, heading_text))
                continue

            # Also check for colon labels
            stripped = line.strip()
            if stripped and not stripped.startswith("-"):
                colon_match = COLON_LABEL_PATTERN.match(stripped)
                if colon_match:
                    label = colon_match.group("text").strip()
                    if label:
                        all_sections.append((i, label))

        # First try exact match (case-insensitive)
        for idx, name in all_sections:
            if name.lower() == section_lower:
                section_line_idx = idx
                matched_section_name = name
                break

        # If no exact match, try partial prefix match (case-insensitive)
        if section_line_idx is None:
            partial_matches = [
                (idx, name)
                for idx, name in all_sections
                if name.lower().startswith(section_lower)
            ]
            if len(partial_matches) == 1:
                # Single partial match - use it
                section_line_idx, matched_section_name = partial_matches[0]
            elif len(partial_matches) > 1:
                # Multiple partial matches - use the first one but could warn
                section_line_idx, matched_section_name = partial_matches[0]

        # Find the next heading after our matched section
        if section_line_idx is not None:
            for idx, _name in all_sections:
                if idx > section_line_idx:
                    next_heading_idx = idx
                    break
            # Update section to the actual matched name for the return value
            section = matched_section_name

        if section_line_idx is not None:
            # Insert after the section heading, before the next heading
            if next_heading_idx is not None:
                # Find the last non-empty line before next heading
                insert_idx = next_heading_idx
                # Insert before the next heading
                while (
                    insert_idx > section_line_idx + 1
                    and not lines[insert_idx - 1].strip()
                ):
                    insert_idx -= 1
            else:
                # No next heading, insert at end of file
                insert_idx = len(lines)
                # Ensure there's a blank line before if content exists
                if lines and lines[-1].strip():
                    lines.append("")
                    insert_idx = len(lines)

            lines.insert(insert_idx, f"- [ ] {text}")
            line_number = insert_idx + 1
        else:
            # Section not found, create it at the end
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"## {section}")
            lines.append("")
            lines.append(f"- [ ] {text}")
            line_number = len(lines)
    else:
        # No section specified, append at end
        line_number = len(lines) + 1
        lines.append(f"- [ ] {text}")

    # Write back to file
    full_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Create and return Todo object
    clean_content = clean_todo_content(text)

    # Check if this is a linked note (external file)
    from nb.core.links import find_linked_note_for_path

    linked = find_linked_note_for_path(full_path)

    notebook: str | None
    if linked:
        # This is a linked note - set up as external
        source = TodoSource(
            type="linked",
            path=full_path,
            external=True,
            alias=linked.alias,
        )
        notebook = linked.notebook or f"@{linked.alias}"
    else:
        # Regular note
        from nb.core.notebooks import get_notebook_for_file

        notebook = get_notebook_for_file(full_path)
        source = TodoSource(
            type="note",
            path=full_path,
            external=False,
            alias=None,
        )

    todo = Todo(
        id=make_todo_id(full_path, clean_content),
        content=clean_content,
        raw_content=text,
        status=TodoStatus.PENDING,
        source=source,
        line_number=line_number,
        created_date=date.today(),
        due_date=parse_due_date(text),
        priority=parse_priority(text),
        tags=parse_tags(text),
        notebook=notebook,
        parent_id=None,
        children=[],
        attachments=[],
        section=section,
    )

    # Insert into database immediately
    from nb.index.todos_repo import upsert_todos_batch

    upsert_todos_batch([todo])

    return todo


def delete_todo_from_file(
    path: Path,
    line_number: int,
    check_linked_sync: bool = True,
    expected_content: str | None = None,
) -> int | None:
    """Delete a todo line from its source file.

    Args:
        path: Path to the file
        line_number: 1-based line number of the todo (may be stale)
        check_linked_sync: Whether to check if linked file allows sync
        expected_content: If provided, verifies/finds the todo by content.
            This handles cases where line numbers become stale due to file edits.

    Returns:
        The actual line number that was deleted, or None if failed.

    Raises:
        PermissionError: If the file is a linked file with sync disabled.

    """
    if not path.exists():
        return None

    # Check if we're allowed to modify this file
    if check_linked_sync and not can_toggle_linked_file(path):
        raise PermissionError(f"Cannot modify linked file (sync disabled): {path.name}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find the actual line number (may differ from stored if file was edited)
    if expected_content:
        actual_line = find_todo_line(lines, line_number, expected_content)
        if actual_line is None:
            return None
    else:
        # Fall back to trusting the line number (legacy behavior)
        if line_number < 1 or line_number > len(lines):
            return None
        actual_line = line_number

    line = lines[actual_line - 1]
    match = TODO_PATTERN.match(line)

    if not match:
        return None

    # Remove the line
    del lines[actual_line - 1]

    # Write back
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return actual_line


def update_todo_due_date(
    path: Path,
    line_number: int,
    new_date: datetime | date,
    check_linked_sync: bool = True,
    expected_content: str | None = None,
) -> int | None:
    """Update or add @due() in a todo line.

    If @due() exists, replaces it with the new date.
    If not, adds @due(YYYY-MM-DD) or @due(YYYY-MM-DD HH:MM) before the first #tag or at end of line.

    Args:
        path: Path to the file
        line_number: 1-based line number of the todo (may be stale)
        new_date: The new due date/datetime to set
        check_linked_sync: Whether to check if linked file allows sync
        expected_content: If provided, verifies/finds the todo by content.
            This handles cases where line numbers become stale due to file edits.

    Returns:
        The actual line number where the todo was updated, or None if failed.

    Raises:
        PermissionError: If the file is a linked file with sync disabled.

    """
    if not path.exists():
        return None

    # Check if we're allowed to modify this file
    if check_linked_sync and not can_toggle_linked_file(path):
        raise PermissionError(f"Cannot modify linked file (sync disabled): {path.name}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find the actual line number (may differ from stored if file was edited)
    if expected_content:
        actual_line = find_todo_line(lines, line_number, expected_content)
        if actual_line is None:
            return None
    else:
        # Fall back to trusting the line number (legacy behavior)
        if line_number < 1 or line_number > len(lines):
            return None
        actual_line = line_number

    line = lines[actual_line - 1]
    match = TODO_PATTERN.match(line)

    if not match:
        return None

    # Format datetime appropriately (with time if not midnight)
    if isinstance(new_date, datetime):
        date_str = format_datetime(new_date)
    else:
        date_str = new_date.isoformat()

    if DUE_PATTERN.search(line):
        # Replace existing @due()
        new_line = DUE_PATTERN.sub(f"@due({date_str})", line)
    else:
        # Add @due() - insert before first #tag or at end
        todo_content = match.group("content")
        tag_match = TAG_PATTERN.search(todo_content)

        if tag_match:
            # Insert before first tag
            tag_pos = tag_match.start()
            # Find where content starts in original line
            content_start = line.index(todo_content)
            insert_pos = content_start + tag_pos
            new_line = line[:insert_pos] + f"@due({date_str}) " + line[insert_pos:]
        else:
            # Append at end
            new_line = line.rstrip() + f" @due({date_str})"

    lines[actual_line - 1] = new_line

    # Write back
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return actual_line


def remove_todo_due_date(
    path: Path,
    line_number: int,
    check_linked_sync: bool = True,
    expected_content: str | None = None,
) -> int | None:
    """Remove @due() from a todo line.

    Args:
        path: Path to the file
        line_number: 1-based line number of the todo (may be stale)
        check_linked_sync: Whether to check if linked file allows sync
        expected_content: If provided, verifies/finds the todo by content.
            This handles cases where line numbers become stale due to file edits.

    Returns:
        The actual line number where the todo was updated, or None if failed.

    Raises:
        PermissionError: If the file is a linked file with sync disabled.

    """
    if not path.exists():
        return None

    # Check if we're allowed to modify this file
    if check_linked_sync and not can_toggle_linked_file(path):
        raise PermissionError(f"Cannot modify linked file (sync disabled): {path.name}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find the actual line number (may differ from stored if file was edited)
    if expected_content:
        actual_line = find_todo_line(lines, line_number, expected_content)
        if actual_line is None:
            return None
    else:
        # Fall back to trusting the line number (legacy behavior)
        if line_number < 1 or line_number > len(lines):
            return None
        actual_line = line_number

    line = lines[actual_line - 1]
    match = TODO_PATTERN.match(line)

    if not match:
        return None

    if not DUE_PATTERN.search(line):
        # No @due() to remove
        return actual_line

    # Remove @due() and any extra whitespace
    new_line = DUE_PATTERN.sub("", line)
    # Clean up any double spaces left behind
    new_line = re.sub(r"  +", " ", new_line)
    new_line = new_line.rstrip()

    lines[actual_line - 1] = new_line

    # Write back
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return actual_line


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
    with note_path.open("a", encoding="utf-8") as f:
        f.write(f"- [ ] {text}\n")

    # Create and return Todo object
    clean_content = clean_todo_content(text)

    source = TodoSource(
        type="note",
        path=note_path,
        external=False,
        alias=None,
    )

    todo = Todo(
        id=make_todo_id(note_path, clean_content),
        content=clean_content,
        raw_content=text,
        status=TodoStatus.PENDING,
        source=source,
        line_number=line_number,
        created_date=dt,
        due_date=parse_due_date(text),
        priority=parse_priority(text),
        tags=parse_tags(text),
        notebook="daily",
        parent_id=None,
        children=[],
        attachments=[],
        section=None,
    )

    # Insert into database immediately
    from nb.index.todos_repo import upsert_todos_batch

    upsert_todos_batch([todo])

    return todo


def normalize_due_dates_in_file(path: Path) -> int:
    """Normalize relative due dates in a file to absolute dates.

    Replaces expressions like @due(today), @due(tomorrow), @due(friday)
    with their resolved ISO dates like @due(2025-12-01).

    Args:
        path: Path to the markdown file to normalize.

    Returns:
        Number of due dates that were normalized.
    """
    if not path.exists():
        return 0

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    changes = 0
    modified_lines = []

    for line in lines:
        new_line = line

        # Find all @due(...) patterns in the line
        for match in DUE_PATTERN.finditer(line):
            date_expr = match.group("date")

            # Check if this is a relative date that should be normalized
            if is_relative_date(date_expr):
                # Parse the relative date to get the actual datetime
                parsed_dt = parse_fuzzy_datetime(date_expr)
                if parsed_dt:
                    # Format it as an absolute date (with time if specified)
                    normalized = format_datetime(parsed_dt)
                    # Replace just this @due() expression
                    old_due = f"@due({date_expr})"
                    new_due = f"@due({normalized})"
                    new_line = new_line.replace(old_due, new_due, 1)
                    changes += 1

        modified_lines.append(new_line)

    # Write back only if changes were made
    if changes > 0:
        path.write_text("\n".join(modified_lines) + "\n", encoding="utf-8")

    return changes
