"""Attachment management for nb."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from nb.config import get_config
from nb.models import Attachment
from nb.utils.hashing import make_attachment_id


def get_attachments_dir() -> Path:
    """Get the attachments directory, creating it if needed."""
    config = get_config()
    attachments_dir = config.attachments_path
    attachments_dir.mkdir(parents=True, exist_ok=True)
    return attachments_dir


def is_url(path: str) -> bool:
    """Check if a path is a URL."""
    try:
        result = urlparse(path)
        return result.scheme in ("http", "https", "ftp", "file")
    except Exception:
        return False


def resolve_attachment_path(attachment: Attachment) -> Path | None:
    """Resolve an attachment's path to an absolute path.

    Returns None if the attachment is a URL or the file doesn't exist.
    """
    if attachment.type == "url":
        return None

    path = Path(attachment.path)

    if path.is_absolute():
        return path if path.exists() else None

    # Check if it's relative to attachments directory
    config = get_config()
    attachments_path = config.attachments_path / path
    if attachments_path.exists():
        return attachments_path

    # Check if it's relative to notes root
    notes_path = config.notes_root / path
    if notes_path.exists():
        return notes_path

    return None


def copy_file_to_attachments(source: Path, target_name: str | None = None) -> Path:
    """Copy a file to the attachments directory.

    Args:
        source: Path to the source file.
        target_name: Optional target filename. Uses source name if not provided.

    Returns:
        Path to the copied file (relative to attachments dir).

    Raises:
        FileNotFoundError: If source doesn't exist.
        IsADirectoryError: If source is a directory.

    """
    if not source.exists():
        raise FileNotFoundError(f"File not found: {source}")
    if source.is_dir():
        raise IsADirectoryError(f"Cannot attach directory: {source}")

    attachments_dir = get_attachments_dir()

    # Use source name if no target provided
    if target_name is None:
        target_name = source.name

    # Handle name collisions by adding a counter
    target_path = attachments_dir / target_name
    if target_path.exists():
        stem = source.stem
        suffix = source.suffix
        counter = 1
        while target_path.exists():
            target_name = f"{stem}_{counter}{suffix}"
            target_path = attachments_dir / target_name
            counter += 1

    # Copy the file
    shutil.copy2(source, target_path)

    return target_path


def create_attachment(
    path_or_url: str,
    owner_type: str,
    owner_id: str,
    title: str | None = None,
    copy: bool = False,
) -> Attachment:
    """Create an attachment for a note or todo.

    Args:
        path_or_url: File path or URL to attach.
        owner_type: Type of owner ("note" or "todo").
        owner_id: ID of the owning note or todo.
        title: Optional display title.
        copy: If True, copy file to attachments directory.

    Returns:
        The created Attachment object.

    Raises:
        FileNotFoundError: If path doesn't exist (for non-URLs).

    """
    # Determine type
    if is_url(path_or_url):
        attachment_type = "url"
        final_path = path_or_url
        copied = False
    else:
        attachment_type = "file"
        source = Path(path_or_url).resolve()

        if not source.exists():
            raise FileNotFoundError(f"File not found: {source}")

        if copy:
            copied_path = copy_file_to_attachments(source)
            # Store relative path to attachments dir
            final_path = copied_path.name
            copied = True
        else:
            # Store absolute path for linked files
            final_path = str(source)
            copied = False

    # Generate ID
    attachment_id = make_attachment_id(final_path, owner_type, owner_id)

    return Attachment(
        id=attachment_id,
        type=attachment_type,
        path=final_path,
        title=(
            title or Path(path_or_url).name if not is_url(path_or_url) else path_or_url
        ),
        added_date=date.today(),
        copied=copied,
    )


def attach_to_note(
    note_path: Path,
    path_or_url: str,
    title: str | None = None,
    copy: bool = False,
) -> Attachment:
    """Attach a file or URL to a note by appending @attach line.

    Args:
        note_path: Path to the note file.
        path_or_url: File path or URL to attach.
        title: Optional display title.
        copy: If True, copy file to attachments directory.

    Returns:
        The created Attachment object.

    """
    from nb.utils.hashing import make_note_hash

    # Create the attachment
    content = note_path.read_text(encoding="utf-8")
    note_id = make_note_hash(content)

    attachment = create_attachment(
        path_or_url,
        owner_type="note",
        owner_id=note_id,
        title=title,
        copy=copy,
    )

    # Append @attach line to the note
    attach_line = f"\n@attach: {attachment.path}"
    if attachment.title and attachment.title != Path(attachment.path).name:
        attach_line = f'\n@attach: {attachment.path} "{attachment.title}"'

    with open(note_path, "a", encoding="utf-8") as f:
        f.write(attach_line + "\n")

    return attachment


def attach_to_todo(
    note_path: Path,
    line_number: int,
    path_or_url: str,
    title: str | None = None,
    copy: bool = False,
) -> Attachment:
    """Attach a file or URL to a todo by inserting @attach line after it.

    Args:
        note_path: Path to the note file containing the todo.
        line_number: 1-based line number of the todo.
        path_or_url: File path or URL to attach.
        title: Optional display title.
        copy: If True, copy file to attachments directory.

    Returns:
        The created Attachment object.

    """
    from nb.utils.hashing import make_todo_id

    # Read the file
    content = note_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    if line_number < 1 or line_number > len(lines):
        raise ValueError(f"Invalid line number: {line_number}")

    # Get the todo line to generate its ID
    todo_line = lines[line_number - 1]
    from nb.core.todos import clean_todo_content

    clean_content = clean_todo_content(todo_line.split("]", 1)[-1].strip())
    todo_id = make_todo_id(note_path, clean_content)

    # Create the attachment
    attachment = create_attachment(
        path_or_url,
        owner_type="todo",
        owner_id=todo_id,
        title=title,
        copy=copy,
    )

    # Get the indentation of the todo
    indent_match = len(todo_line) - len(todo_line.lstrip())
    indent = " " * (indent_match + 2)  # Indent 2 more spaces than todo

    # Build @attach line
    attach_line = f"{indent}@attach: {attachment.path}"
    if attachment.title and attachment.title != Path(attachment.path).name:
        attach_line = f'{indent}@attach: {attachment.path} "{attachment.title}"'

    # Insert after the todo line
    lines.insert(line_number, attach_line)

    # Write back
    note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return attachment


def list_attachments_in_file(path: Path) -> list[tuple[int, str]]:
    """List all @attach lines in a file.

    Returns:
        List of (line_number, path) tuples.

    """
    if not path.exists():
        return []

    import re

    attach_pattern = re.compile(r"^\s*@attach:\s*(.+)$")
    results = []

    content = path.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines(), 1):
        match = attach_pattern.match(line)
        if match:
            attach_path = match.group(1).strip()
            # Remove optional title in quotes
            if '"' in attach_path:
                attach_path = attach_path.split('"')[0].strip()
            results.append((i, attach_path))

    return results


def remove_attachment_from_file(path: Path, line_number: int) -> bool:
    """Remove an @attach line from a file.

    Args:
        path: Path to the file.
        line_number: 1-based line number of the @attach line.

    Returns:
        True if removed, False otherwise.

    """
    if not path.exists():
        return False

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    if line_number < 1 or line_number > len(lines):
        return False

    line = lines[line_number - 1]
    if "@attach:" not in line:
        return False

    lines.pop(line_number - 1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def open_attachment(attachment: Attachment) -> bool:
    """Open an attachment with the system default handler.

    Args:
        attachment: The attachment to open.

    Returns:
        True if opened successfully, False otherwise.

    """
    import subprocess
    import sys

    if attachment.type == "url":
        target = attachment.path
    else:
        resolved = resolve_attachment_path(attachment)
        if resolved is None:
            return False
        target = str(resolved)

    try:
        if sys.platform == "win32":
            import os

            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.run(["open", target], check=True)
        else:
            subprocess.run(["xdg-open", target], check=True)
        return True
    except Exception:
        return False
