"""Data models for nb."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
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

    path: Path  # Relative to notes_root
    title: str
    date: date | None
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    notebook: str = ""
    content_hash: str = ""


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
    completed: bool
    source: TodoSource
    line_number: int
    created_date: date
    due_date: date | None = None
    priority: Priority | None = None
    tags: list[str] = field(default_factory=list)
    project: str | None = None
    parent_id: str | None = None
    children: list[Todo] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    details: str | None = None  # Multi-line details/description below the todo

    @property
    def is_overdue(self) -> bool:
        """Check if todo is past due date."""
        if self.due_date is None:
            return False
        return self.due_date < date.today()

    @property
    def is_due_today(self) -> bool:
        """Check if todo is due today."""
        if self.due_date is None:
            return False
        return self.due_date == date.today()

    @property
    def priority_sort_key(self) -> int:
        """Return sort key for priority (lower is higher priority)."""
        if self.priority is None:
            return 999  # No priority sorts last
        return self.priority.value
