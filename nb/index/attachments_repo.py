"""Attachment database operations for nb."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from nb.index.db import get_db
from nb.models import Attachment
from nb.utils.hashing import make_attachment_id, normalize_path
from nb.utils.patterns import ATTACH_PATTERN_WITH_TITLE as ATTACH_PATTERN

if TYPE_CHECKING:
    from nb.index.db import Database


def _row_to_attachment(row) -> Attachment:
    """Convert a database row to an Attachment object."""
    return Attachment(
        id=row["id"],
        type=row["type"],
        path=row["path"],
        title=row["title"],
        added_date=date.fromisoformat(row["added_date"]) if row["added_date"] else None,
        copied=bool(row["copied"]),
    )


def upsert_attachment(
    attachment: Attachment,
    parent_type: str,
    parent_id: str,
    commit: bool = True,
    db: Database | None = None,
) -> None:
    """Insert or update an attachment in the database.

    Args:
        attachment: The Attachment to upsert.
        parent_type: Type of parent ("note" or "todo").
        parent_id: ID of the parent (note path or todo ID).
        commit: If True, commit immediately.
        db: Optional database instance.
    """
    if db is None:
        db = get_db()

    db.execute(
        """
        INSERT OR REPLACE INTO attachments
        (id, parent_type, parent_id, type, path, title, added_date, copied)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attachment.id,
            parent_type,
            parent_id,
            attachment.type,
            attachment.path,
            attachment.title,
            attachment.added_date.isoformat() if attachment.added_date else None,
            1 if attachment.copied else 0,
        ),
    )

    if commit:
        db.commit()


def upsert_attachments_batch(
    attachments: list[tuple[Attachment, str, str]],
    db: Database | None = None,
    commit: bool = True,
) -> None:
    """Insert or update multiple attachments in a single transaction.

    Args:
        attachments: List of (Attachment, parent_type, parent_id) tuples.
        db: Optional database instance.
        commit: If True, commit after all inserts.
    """
    if not attachments:
        return

    if db is None:
        db = get_db()

    for attachment, parent_type, parent_id in attachments:
        upsert_attachment(attachment, parent_type, parent_id, commit=False, db=db)

    if commit:
        db.commit()


def delete_attachments_for_parent(
    parent_type: str,
    parent_id: str,
    db: Database | None = None,
) -> None:
    """Delete all attachments for a specific parent.

    Args:
        parent_type: Type of parent ("note" or "todo").
        parent_id: ID of the parent.
        db: Optional database instance.
    """
    if db is None:
        db = get_db()

    db.execute(
        "DELETE FROM attachments WHERE parent_type = ? AND parent_id = ?",
        (parent_type, parent_id),
    )
    db.commit()


def delete_attachments_for_note(
    note_path: Path,
    db: Database | None = None,
    commit: bool = True,
) -> None:
    """Delete all attachments belonging to a note (including its todos).

    Args:
        note_path: Path to the note file.
        db: Optional database instance.
        commit: If True, commit immediately.
    """
    if db is None:
        db = get_db()

    normalized = normalize_path(note_path)

    # Delete note-level attachments
    db.execute(
        "DELETE FROM attachments WHERE parent_type = 'note' AND parent_id = ?",
        (normalized,),
    )

    # Delete todo-level attachments (todos whose source is this note)
    # We need to find todo IDs from this note first
    todo_ids = db.fetchall(
        "SELECT id FROM todos WHERE source_path = ?",
        (normalized,),
    )
    if todo_ids:
        placeholders = ", ".join("?" for _ in todo_ids)
        db.execute(
            f"DELETE FROM attachments WHERE parent_type = 'todo' AND parent_id IN ({placeholders})",
            tuple(row["id"] for row in todo_ids),
        )

    if commit:
        db.commit()


def get_attachment_by_id(attachment_id: str) -> Attachment | None:
    """Get an attachment by its ID."""
    db = get_db()
    row = db.fetchone("SELECT * FROM attachments WHERE id = ?", (attachment_id,))

    if not row:
        return None

    return _row_to_attachment(row)


def get_attachments_for_parent(
    parent_type: str,
    parent_id: str,
) -> list[Attachment]:
    """Get all attachments for a specific parent.

    Args:
        parent_type: Type of parent ("note" or "todo").
        parent_id: ID of the parent.

    Returns:
        List of Attachment objects.
    """
    db = get_db()
    rows = db.fetchall(
        "SELECT * FROM attachments WHERE parent_type = ? AND parent_id = ?",
        (parent_type, parent_id),
    )

    return [_row_to_attachment(row) for row in rows]


def query_attachments(
    attachment_type: str | None = None,
    parent_type: str | None = None,
    notebook: str | None = None,
    copied: bool | None = None,
    search_path: str | None = None,
    search_title: str | None = None,
) -> list[tuple[Attachment, str, str]]:
    """Query attachments with filters.

    Args:
        attachment_type: Filter by type ("file", "url", "conversation").
        parent_type: Filter by parent type ("note" or "todo").
        notebook: Filter by notebook name.
        copied: Filter by copied status.
        search_path: Search in path (partial match).
        search_title: Search in title (partial match).

    Returns:
        List of (Attachment, parent_type, parent_id) tuples.
    """
    db = get_db()

    sql = "SELECT a.* FROM attachments a"
    params: list = []
    conditions: list[str] = []
    joins: list[str] = []

    # Join with notes or todos for notebook filtering
    if notebook:
        joins.append(
            """LEFT JOIN notes n ON (a.parent_type = 'note' AND a.parent_id = n.path)"""
        )
        joins.append(
            """LEFT JOIN todos t ON (a.parent_type = 'todo' AND a.parent_id = t.id)"""
        )
        conditions.append("(n.notebook = ? OR t.project = ?)")
        params.extend([notebook, notebook])

    if joins:
        sql += " " + " ".join(joins)

    if attachment_type:
        conditions.append("a.type = ?")
        params.append(attachment_type)

    if parent_type:
        conditions.append("a.parent_type = ?")
        params.append(parent_type)

    if copied is not None:
        conditions.append("a.copied = ?")
        params.append(1 if copied else 0)

    if search_path:
        conditions.append("a.path LIKE ?")
        params.append(f"%{search_path}%")

    if search_title:
        conditions.append("a.title LIKE ?")
        params.append(f"%{search_title}%")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY a.added_date DESC"

    rows = db.fetchall(sql, tuple(params))

    return [
        (_row_to_attachment(row), row["parent_type"], row["parent_id"]) for row in rows
    ]


def get_all_attachments() -> list[tuple[Attachment, str, str]]:
    """Get all attachments in the database.

    Returns:
        List of (Attachment, parent_type, parent_id) tuples.
    """
    return query_attachments()


def get_attachment_stats() -> dict:
    """Get attachment statistics.

    Returns:
        {
            "total": int,
            "by_type": {"file": int, "url": int, ...},
            "by_parent_type": {"note": int, "todo": int},
            "copied": int,
            "linked": int,
        }
    """
    db = get_db()

    total_row = db.fetchone("SELECT COUNT(*) as count FROM attachments")
    total = total_row["count"] if total_row else 0

    # By type
    type_rows = db.fetchall(
        "SELECT type, COUNT(*) as count FROM attachments GROUP BY type"
    )
    by_type = {row["type"]: row["count"] for row in type_rows}

    # By parent type
    parent_rows = db.fetchall(
        "SELECT parent_type, COUNT(*) as count FROM attachments GROUP BY parent_type"
    )
    by_parent_type = {row["parent_type"]: row["count"] for row in parent_rows}

    # Copied vs linked
    copied_row = db.fetchone(
        "SELECT COUNT(*) as count FROM attachments WHERE copied = 1"
    )
    copied = copied_row["count"] if copied_row else 0

    return {
        "total": total,
        "by_type": by_type,
        "by_parent_type": by_parent_type,
        "copied": copied,
        "linked": total - copied,
    }


def find_orphan_attachment_files() -> list[Path]:
    """Find attachment files that are not referenced in any note.

    Scans the attachments directory and checks each file against the database.

    Returns:
        List of orphan file paths.
    """
    from nb.config import get_config

    config = get_config()
    attachments_dir = config.attachments_path

    if not attachments_dir.exists():
        return []

    db = get_db()
    orphans = []

    for file_path in attachments_dir.iterdir():
        if file_path.is_file():
            # Check if this file is referenced in the database
            # Attachments can be stored as just the filename (for copied files)
            # or as a full path (for linked files)
            filename = file_path.name
            full_path = str(file_path)

            row = db.fetchone(
                "SELECT id FROM attachments WHERE path = ? OR path = ?",
                (filename, full_path),
            )

            if not row:
                orphans.append(file_path)

    return orphans


def extract_attachments_from_content(
    content: str,
    parent_type: str,
    parent_id: str,
    source_path: Path,
) -> list[tuple[Attachment, str, str]]:
    """Extract attachment metadata from markdown content.

    Parses @attach: lines and creates Attachment objects.

    Args:
        content: The markdown content.
        parent_type: Type of parent ("note" or "todo").
        parent_id: ID of the parent.
        source_path: Path to the source file (for ID generation).

    Returns:
        List of (Attachment, parent_type, parent_id) tuples.
    """
    from nb.core.attachments import is_url

    attachments = []

    for match in ATTACH_PATTERN.finditer(content):
        path = match.group(1).strip()
        title = match.group(2)  # May be None

        # Determine attachment type
        attachment_type: Literal["file", "url", "conversation"]
        if is_url(path):
            attachment_type = "url"
        else:
            attachment_type = "file"

        # Generate ID
        attachment_id = make_attachment_id(path, parent_type, parent_id)

        attachment = Attachment(
            id=attachment_id,
            type=attachment_type,
            path=path,
            title=title or (Path(path).name if not is_url(path) else path),
            added_date=date.today(),  # We don't know the actual date
            copied=False,  # We can't determine this from content alone
        )

        attachments.append((attachment, parent_type, parent_id))

    return attachments
