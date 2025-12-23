"""Data models for nb."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass


class Priority(Enum):
    """Todo priority levels."""

    HIGH = 1
    MEDIUM = 2
    LOW = 3

    @classmethod
    def from_int(cls, value: int) -> Priority | None:
        """Create Priority from integer value."""
        try:
            return cls(value)
        except ValueError:
            return None


class TodoStatus(Enum):
    """Todo status states."""

    PENDING = "pending"  # [ ]
    IN_PROGRESS = "in_progress"  # [^]
    COMPLETED = "completed"  # [x] or [X]

    @classmethod
    def from_marker(cls, marker: str) -> TodoStatus:
        """Create TodoStatus from checkbox marker character."""
        if marker in ("x", "X"):
            return cls.COMPLETED
        elif marker == "^":
            return cls.IN_PROGRESS
        else:
            return cls.PENDING

    @property
    def marker(self) -> str:
        """Return the checkbox marker for this status."""
        if self == TodoStatus.COMPLETED:
            return "x"
        elif self == TodoStatus.IN_PROGRESS:
            return "^"
        else:
            return " "


@dataclass
class Attachment:
    """An attachment to a note or todo."""

    id: str
    type: Literal["file", "url", "conversation"]
    path: str
    title: str | None = None
    added_date: date | None = None
    copied: bool = False


@dataclass
class Note:
    """A markdown note file."""

    id: str  # Stable ID based on path (SHA256(path)[:8])
    path: Path  # Relative to notes_root
    title: str
    date: date | None
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    notebook: str = ""
    content_hash: str = ""
    sections: list[str] = field(
        default_factory=list
    )  # Path-based subdirectory sections


@dataclass
class TodoSource:
    """The source location of a todo item."""

    type: Literal["note", "inbox", "linked"]
    path: Path
    external: bool = False
    alias: str | None = None


@dataclass
class Todo:
    """A todo item extracted from a note."""

    id: str
    content: str  # Cleaned text without metadata markers
    raw_content: str  # Original line content
    status: TodoStatus
    source: TodoSource
    line_number: int
    created_date: date
    due_date: datetime | None = None  # Supports optional time component
    priority: Priority | None = None
    tags: list[str] = field(default_factory=list)
    notebook: str | None = None  # Database column is 'project' for legacy reasons
    parent_id: str | None = None
    children: list[Todo] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    details: str | None = None  # Multi-line details/description below the todo
    section: str | None = None  # Section heading above the todo (markdown heading)
    sections: list[str] = field(
        default_factory=list
    )  # Path-based subdirectory sections

    @property
    def completed(self) -> bool:
        """Check if todo is completed (backwards compatibility)."""
        return self.status == TodoStatus.COMPLETED

    @property
    def in_progress(self) -> bool:
        """Check if todo is in progress."""
        return self.status == TodoStatus.IN_PROGRESS

    @property
    def due_date_only(self) -> date | None:
        """Get just the date portion of due_date."""
        if self.due_date is None:
            return None
        if isinstance(self.due_date, datetime):
            return self.due_date.date()
        return self.due_date  # Already a date

    @property
    def has_due_time(self) -> bool:
        """Check if due_date has a non-midnight time component."""
        if self.due_date is None:
            return False
        if isinstance(self.due_date, datetime):
            return self.due_date.time() != time.min
        return False  # date objects have no time

    @property
    def is_overdue(self) -> bool:
        """Check if todo is past due date.

        For datetime with time: considers both date and time.
        For datetime at midnight or date: only considers the date.
        """
        if self.due_date is None:
            return False
        if self.has_due_time:
            return self.due_date < datetime.now()
        # Compare dates only
        due = self.due_date_only
        return due < date.today() if due else False

    @property
    def is_due_today(self) -> bool:
        """Check if todo is due today."""
        if self.due_date is None:
            return False
        due = self.due_date_only
        return due == date.today() if due else False

    @property
    def priority_sort_key(self) -> int:
        """Return sort key for priority (lower is higher priority)."""
        if self.priority is None:
            return 999  # No priority sorts last
        return self.priority.value
