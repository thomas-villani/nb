"""SQLite database management for nb."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Current schema version
SCHEMA_VERSION = 15

# Phase 1 schema: notes, tags, links
SCHEMA_V1 = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- Notes
CREATE TABLE IF NOT EXISTS notes (
    path TEXT PRIMARY KEY,
    title TEXT,
    date TEXT,
    notebook TEXT,
    content_hash TEXT,
    updated_at TEXT
);

-- Note tags (many-to-many)
CREATE TABLE IF NOT EXISTS note_tags (
    note_path TEXT REFERENCES notes(path) ON DELETE CASCADE,
    tag TEXT,
    PRIMARY KEY (note_path, tag)
);

-- Note links (wiki-style links between notes)
CREATE TABLE IF NOT EXISTS note_links (
    source_path TEXT REFERENCES notes(path) ON DELETE CASCADE,
    target_path TEXT,
    display_text TEXT,
    PRIMARY KEY (source_path, target_path)
);

-- Indexes for notes
CREATE INDEX IF NOT EXISTS idx_notes_date ON notes(date);
CREATE INDEX IF NOT EXISTS idx_notes_notebook ON notes(notebook);
CREATE INDEX IF NOT EXISTS idx_note_tags_tag ON note_tags(tag);
"""

# Phase 2 additions: todos
SCHEMA_V2 = """
-- Todos
CREATE TABLE IF NOT EXISTS todos (
    id TEXT PRIMARY KEY,
    content TEXT,
    raw_content TEXT,
    completed INTEGER DEFAULT 0,
    source_type TEXT,
    source_path TEXT,
    source_external INTEGER DEFAULT 0,
    source_alias TEXT,
    line_number INTEGER,
    created_date TEXT,
    due_date TEXT,
    priority INTEGER,
    project TEXT,
    parent_id TEXT REFERENCES todos(id) ON DELETE CASCADE,
    content_hash TEXT
);

-- Todo tags (many-to-many)
CREATE TABLE IF NOT EXISTS todo_tags (
    todo_id TEXT REFERENCES todos(id) ON DELETE CASCADE,
    tag TEXT,
    PRIMARY KEY (todo_id, tag)
);

-- Attachments (polymorphic: can belong to note or todo)
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    parent_type TEXT,
    parent_id TEXT,
    type TEXT,
    path TEXT,
    title TEXT,
    added_date TEXT,
    copied INTEGER DEFAULT 0
);

-- Linked external todo files
CREATE TABLE IF NOT EXISTS linked_files (
    alias TEXT PRIMARY KEY,
    path TEXT UNIQUE,
    sync INTEGER DEFAULT 1
);

-- Indexes for todos
CREATE INDEX IF NOT EXISTS idx_todos_due ON todos(due_date);
CREATE INDEX IF NOT EXISTS idx_todos_completed ON todos(completed);
CREATE INDEX IF NOT EXISTS idx_todos_project ON todos(project);
CREATE INDEX IF NOT EXISTS idx_todos_source ON todos(source_path);
CREATE INDEX IF NOT EXISTS idx_todos_parent ON todos(parent_id);
CREATE INDEX IF NOT EXISTS idx_todo_tags_tag ON todo_tags(tag);
CREATE INDEX IF NOT EXISTS idx_attachments_parent ON attachments(parent_type, parent_id);
"""

# Phase 3 additions: content column for notes (used by grep and caching)
SCHEMA_V3 = """
-- Add content column to notes table for grep and caching
ALTER TABLE notes ADD COLUMN content TEXT;
"""

# Phase 3.5 additions: linked notes support
SCHEMA_V4 = """
-- Add external flag and source_alias to notes table
ALTER TABLE notes ADD COLUMN external INTEGER DEFAULT 0;
ALTER TABLE notes ADD COLUMN source_alias TEXT;

-- Linked external note files/directories
CREATE TABLE IF NOT EXISTS linked_notes (
    alias TEXT PRIMARY KEY,
    path TEXT UNIQUE,
    notebook TEXT,
    recursive INTEGER DEFAULT 1
);

-- Index for external notes
CREATE INDEX IF NOT EXISTS idx_notes_external ON notes(external);
CREATE INDEX IF NOT EXISTS idx_notes_source_alias ON notes(source_alias);
"""

# Phase 4 additions: mtime column for fast change detection
SCHEMA_V5 = """
-- Add mtime column to notes table for fast change detection
ALTER TABLE notes ADD COLUMN mtime REAL;
"""

# Phase 5 additions: details column for multi-line todo content
SCHEMA_V6 = """
-- Add details column to todos table for multi-line content
ALTER TABLE todos ADD COLUMN details TEXT;
"""

# Phase 6 additions: note view history and per-note todo exclusion
SCHEMA_V7 = """
-- Note view history for recently viewed tracking
CREATE TABLE IF NOT EXISTS note_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path TEXT NOT NULL,
    viewed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_note_views_path ON note_views(note_path);
CREATE INDEX IF NOT EXISTS idx_note_views_time ON note_views(viewed_at);

-- Per-note todo exclusion flag
ALTER TABLE notes ADD COLUMN todo_exclude INTEGER DEFAULT 0;
"""

# Phase 7 additions: linked notes todo_exclude and sync columns
SCHEMA_V8 = """
-- Add todo_exclude and sync columns to linked_notes table
ALTER TABLE linked_notes ADD COLUMN todo_exclude INTEGER DEFAULT 0;
ALTER TABLE linked_notes ADD COLUMN sync INTEGER DEFAULT 1;
"""

# Phase 8 additions: section heading tracking for todos
SCHEMA_V9 = """
-- Add section column to todos table for heading tracking
ALTER TABLE todos ADD COLUMN section TEXT;
"""

# Phase 9 additions: todo status column (pending, in_progress, completed)
SCHEMA_V10 = """
-- Add status column to todos table for in-progress support
ALTER TABLE todos ADD COLUMN status TEXT DEFAULT 'pending';

-- Migrate existing data from completed column to status
UPDATE todos SET status = CASE WHEN completed = 1 THEN 'completed' ELSE 'pending' END;

-- Add index for status filtering
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
"""

# Phase 10 additions: note aliases for quick access
SCHEMA_V11 = """
-- Note aliases for quick access via nb open <alias>
CREATE TABLE IF NOT EXISTS note_aliases (
    alias TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    notebook TEXT
);

CREATE INDEX IF NOT EXISTS idx_note_aliases_path ON note_aliases(path);
"""

# Phase 11 additions: completed_date tracking for stats
SCHEMA_V12 = """
-- Add completed_date column to todos for activity tracking
ALTER TABLE todos ADD COLUMN completed_date TEXT;

-- Backfill: set completed_date = created_date for existing completed todos
UPDATE todos SET completed_date = created_date WHERE status = 'completed' AND completed_date IS NULL;

-- Index for activity queries
CREATE INDEX IF NOT EXISTS idx_todos_completed_date ON todos(completed_date);
"""

# Phase 12 additions: per-notebook alias uniqueness
SCHEMA_V13 = """
-- Migrate note_aliases to allow same alias in different notebooks
-- Create new table with composite primary key
CREATE TABLE IF NOT EXISTS note_aliases_new (
    alias TEXT NOT NULL,
    path TEXT NOT NULL,
    notebook TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (alias, notebook)
);

-- Copy existing data (use empty string for NULL notebooks)
INSERT OR IGNORE INTO note_aliases_new (alias, path, notebook)
SELECT alias, path, COALESCE(notebook, '') FROM note_aliases;

-- Drop old table and rename
DROP TABLE IF EXISTS note_aliases;
ALTER TABLE note_aliases_new RENAME TO note_aliases;

-- Recreate index
CREATE INDEX IF NOT EXISTS idx_note_aliases_path ON note_aliases(path);

-- Migrate linked_notes to allow same alias in different notebooks
CREATE TABLE IF NOT EXISTS linked_notes_new (
    alias TEXT NOT NULL,
    path TEXT NOT NULL,
    notebook TEXT NOT NULL DEFAULT '',
    recursive INTEGER DEFAULT 1,
    todo_exclude INTEGER DEFAULT 0,
    sync INTEGER DEFAULT 1,
    PRIMARY KEY (alias, notebook)
);

-- Copy existing data (use empty string for NULL notebooks)
INSERT OR IGNORE INTO linked_notes_new (alias, path, notebook, recursive, todo_exclude, sync)
SELECT alias, path, COALESCE(notebook, ''), recursive, COALESCE(todo_exclude, 0), COALESCE(sync, 1) FROM linked_notes;

-- Drop old table and rename
DROP TABLE IF EXISTS linked_notes;
ALTER TABLE linked_notes_new RENAME TO linked_notes;

-- Note: removed UNIQUE constraint on path - same file can be linked multiple times with different aliases
"""

# Phase 13 additions: note link type and external flag
SCHEMA_V14 = """
-- Add link_type column to distinguish wiki-style, markdown, and frontmatter links
ALTER TABLE note_links ADD COLUMN link_type TEXT DEFAULT 'wiki';

-- Add is_external flag for http/https/mailto URLs
ALTER TABLE note_links ADD COLUMN is_external INTEGER DEFAULT 0;

-- Add line_number for locating links in source file
ALTER TABLE note_links ADD COLUMN line_number INTEGER;

-- Index for querying backlinks (notes linking TO a target)
CREATE INDEX IF NOT EXISTS idx_note_links_target ON note_links(target_path);

-- Index for external link queries
CREATE INDEX IF NOT EXISTS idx_note_links_external ON note_links(is_external);
"""

# Phase 14 additions: path-based sections for notes and todos
SCHEMA_V15 = """
-- Note sections (subdirectory hierarchy from path)
CREATE TABLE IF NOT EXISTS note_sections (
    note_path TEXT NOT NULL,
    section TEXT NOT NULL,
    depth INTEGER NOT NULL,
    PRIMARY KEY (note_path, section),
    FOREIGN KEY (note_path) REFERENCES notes(path) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_note_sections_section ON note_sections(section);

-- Todo sections (inherited from note path)
CREATE TABLE IF NOT EXISTS todo_sections (
    todo_id TEXT NOT NULL,
    section TEXT NOT NULL,
    depth INTEGER NOT NULL,
    PRIMARY KEY (todo_id, section),
    FOREIGN KEY (todo_id) REFERENCES todos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_todo_sections_section ON todo_sections(section);
"""

# Migration scripts (indexed by target version)
MIGRATIONS: dict[int, str] = {
    1: SCHEMA_V1,
    2: SCHEMA_V2,
    3: SCHEMA_V3,
    4: SCHEMA_V4,
    5: SCHEMA_V5,
    6: SCHEMA_V6,
    7: SCHEMA_V7,
    8: SCHEMA_V8,
    9: SCHEMA_V9,
    10: SCHEMA_V10,
    11: SCHEMA_V11,
    12: SCHEMA_V12,
    13: SCHEMA_V13,
    14: SCHEMA_V14,
    15: SCHEMA_V15,
}


class Database:
    """SQLite database connection manager."""

    def __init__(self, path: Path):
        self.path = path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database transactions."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute a SQL statement."""
        return self.connect().execute(sql, params)

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        """Execute a SQL statement for multiple parameter sets."""
        self.connect().executemany(sql, params)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """Execute a query and fetch one row."""
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Execute a query and fetch all rows."""
        return self.execute(sql, params).fetchall()

    def commit(self) -> None:
        """Commit the current transaction."""
        if self._conn is not None:
            self._conn.commit()


def get_schema_version(db: Database) -> int:
    """Get the current schema version, or 0 if not initialized."""
    try:
        row = db.fetchone("SELECT version FROM schema_version")
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        # Table doesn't exist
        return 0


def set_schema_version(db: Database, version: int) -> None:
    """Set the schema version."""
    db.execute("DELETE FROM schema_version")
    db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    db.commit()


def apply_migrations(db: Database) -> None:
    """Apply any pending schema migrations."""
    current = get_schema_version(db)

    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            # Apply this migration
            db.connect().executescript(MIGRATIONS[version])
            set_schema_version(db, version)


def init_db(db: Database) -> None:
    """Initialize the database schema.

    Creates tables if they don't exist and applies any pending migrations.
    """
    apply_migrations(db)


# Singleton database instance
_db: Database | None = None


def get_db() -> Database:
    """Get the global database instance.

    Initializes the database on first call.
    """
    global _db
    if _db is None:
        from nb.config import get_config

        config = get_config()
        _db = Database(config.db_path)
        init_db(_db)
    return _db


def reset_db() -> None:
    """Reset the database instance (useful for testing)."""
    global _db
    if _db is not None:
        _db.close()
        _db = None


def rebuild_db(db: Database) -> None:
    """Drop all tables and recreate the schema from scratch.

    This is useful when the data format has changed and a clean
    reindex is needed.

    Also clears the localvectordb index to prevent ghost search results.
    """
    # Drop all tables in reverse dependency order
    tables = [
        "todo_sections",
        "note_sections",
        "todo_tags",
        "note_tags",
        "note_links",
        "note_views",
        "note_aliases",
        "attachments",
        "todos",
        "notes",
        "linked_files",
        "linked_notes",
        "schema_version",
    ]

    for table in tables:
        try:
            db.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass

    db.commit()

    # Clear localvectordb to prevent ghost search results
    try:
        import shutil

        from nb.config import get_config

        config = get_config()
        vectors_path = config.vectors_path
        if vectors_path.exists():
            shutil.rmtree(vectors_path)
        # Also reset the search singleton so it recreates from scratch
        from nb.index.search import reset_search

        reset_search()
    except Exception:
        pass  # Don't fail rebuild if vector clearing fails

    # Recreate schema from scratch
    apply_migrations(db)
