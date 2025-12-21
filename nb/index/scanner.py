"""Filesystem scanning and indexing for nb."""

from __future__ import annotations

import fnmatch
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from nb.config import get_config
from nb.core.note_parser import get_note
from nb.core.todos import extract_todos, normalize_due_dates_in_file
from nb.index.attachments_repo import (
    delete_attachments_for_note,
    extract_attachments_from_content,
    upsert_attachments_batch,
)
from nb.index.db import Database, get_db
from nb.index.todos_repo import (
    delete_todos_for_source,
    get_todo_dates_for_source,
    upsert_todos_batch,
)
from nb.utils.hashing import make_note_hash, normalize_path

# Thread-local storage for database connections
_thread_local = threading.local()

# Flag to enable/disable vector search indexing
# Set to False to skip vector indexing (useful if embeddings not available)
ENABLE_VECTOR_INDEXING = True

# Lock for vector indexing (localvectordb may not be thread-safe)
_vector_lock = threading.Lock()

# Logger for vector indexing issues
_logger = logging.getLogger(__name__)


def _get_thread_db() -> Database:
    """Get a thread-local database connection.

    Each thread gets its own SQLite connection to avoid thread-safety issues.
    """
    if not hasattr(_thread_local, "db"):
        from nb.index.db import Database, init_db

        config = get_config()
        _thread_local.db = Database(config.db_path)
        init_db(_thread_local.db)
    return _thread_local.db


def load_nbignore(notes_root: Path) -> list[str]:
    """Load ignore patterns from .nbignore file.

    The .nbignore file uses fnmatch-style patterns (similar to .gitignore but simpler).
    Each line is a pattern, blank lines and lines starting with # are ignored.

    Example .nbignore:
        # Ignore archive folders
        archive
        old_*
        temp/
    """
    ignore_file = notes_root / ".nbignore"
    if not ignore_file.exists():
        return []

    patterns = []
    try:
        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith("#"):
                patterns.append(line)
    except Exception:
        pass  # If we can't read the file, just ignore it
    return patterns


def should_ignore(path: Path, patterns: list[str], notes_root: Path) -> bool:
    """Check if a path matches any ignore pattern.

    Args:
        path: Absolute path to the file
        patterns: List of fnmatch patterns from .nbignore
        notes_root: The notes root directory

    Returns:
        True if the path should be ignored
    """
    if not patterns:
        return False

    try:
        rel_path = path.relative_to(notes_root)
    except ValueError:
        return False

    rel_str = str(rel_path).replace("\\", "/")

    for pattern in patterns:
        # Match against full relative path
        if fnmatch.fnmatch(rel_str, pattern):
            return True
        # Match with wildcard prefix for nested matches
        if fnmatch.fnmatch(rel_str, f"*/{pattern}"):
            return True
        if fnmatch.fnmatch(rel_str, f"**/{pattern}"):
            return True
        # Check if any path component matches the pattern
        for part in rel_path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def scan_notes(notes_root: Path | None = None) -> list[Path]:
    """Find all markdown files in the notes root and external notebooks.

    Excludes:
    - Hidden directories (starting with .)
    - Hidden files (starting with .)
    - Files/directories matching patterns in .nbignore
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    notes = []

    # Load .nbignore patterns
    ignore_patterns = load_nbignore(notes_root)

    # Scan notes_root
    if notes_root.exists():
        for md_file in notes_root.rglob("*.md"):
            rel_parts = md_file.relative_to(notes_root).parts
            # Skip hidden directories and hidden files (starting with .)
            if any(part.startswith(".") for part in rel_parts):
                continue
            # Skip files matching .nbignore patterns
            if should_ignore(md_file, ignore_patterns, notes_root):
                continue
            notes.append(md_file)

    # Scan external notebooks
    config = get_config()
    for nb in config.external_notebooks():
        if nb.path and nb.path.exists():
            # Load .nbignore for external notebook if present
            ext_ignore_patterns = load_nbignore(nb.path)
            for md_file in nb.path.rglob("*.md"):
                # Skip hidden directories and hidden files
                try:
                    rel_parts = md_file.relative_to(nb.path).parts
                    if any(part.startswith(".") for part in rel_parts):
                        continue
                    # Skip files matching .nbignore patterns
                    if should_ignore(md_file, ext_ignore_patterns, nb.path):
                        continue
                except ValueError:
                    continue
                notes.append(md_file)

    return sorted(notes)


def get_file_hash(path: Path) -> str:
    """Compute content hash for a file."""
    content = path.read_text(encoding="utf-8")
    return make_note_hash(content)


def needs_reindex(path: Path, notes_root: Path | None = None) -> bool:
    """Check if a file needs to be reindexed.

    Compares the file's content hash against the stored hash in the database.
    This approach was chosen over mtime-based checking due to occasional
    mtime inconsistencies on some platforms (particularly Windows).

    Returns True if:
    - File is not in the database
    - File's content hash differs from the stored hash
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    try:
        relative = path.relative_to(notes_root)
    except ValueError:
        relative = path

    # Get current file mtime
    # try:
    #     _current_mtime = path.stat().st_mtime
    # except OSError:
    #     return True  # File doesn't exist or can't be read

    db = get_db()
    row = db.fetchone(
        "SELECT mtime, content_hash FROM notes WHERE path = ?",
        (normalize_path(relative),),
    )

    if not row:
        return True  # New file

    # Fast path: mtime unchanged AND hash matches means file unchanged
    # Note: We can't trust mtime alone due to potential race conditions
    # where mtime was captured but old content was read during indexing.
    # Always verify with content hash for correctness.
    current_hash = get_file_hash(path)
    if row["content_hash"] == current_hash:
        return False  # Content unchanged, no reindex needed

    # Content changed (hash mismatch), needs reindex
    return True


def index_note(
    path: Path,
    notes_root: Path | None = None,
    index_vectors: bool = True,
) -> None:
    """Index a single note file.

    Parses the note and its todos, storing them in the database.

    Args:
        path: Path to the note file.
        notes_root: Override notes root directory.
        index_vectors: Whether to also index to localvectordb for search.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    # Resolve full path first
    if path.is_absolute():
        full_path = path
    else:
        full_path = notes_root / path

    # Normalize relative due dates FIRST (e.g., @due(today) -> @due(2025-12-01))
    # This must happen before reading content/hash to avoid re-indexing next time
    normalize_due_dates_in_file(full_path)

    # Now read the normalized content and compute hash
    note = get_note(path, notes_root)
    if not note:
        return

    # Read the full content for storage and vector indexing
    try:
        content = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        content = ""

    # Get file mtime for caching (after normalization)
    try:
        mtime = full_path.stat().st_mtime
    except OSError:
        mtime = None

    # Check for todo_exclude in frontmatter and extract links
    from nb.utils.markdown import (
        extract_all_links,
        extract_frontmatter_links,
        extract_todo_exclude,
        parse_note_file,
    )

    try:
        meta, body = parse_note_file(full_path)
        todo_exclude = 1 if extract_todo_exclude(meta) else 0
        # Extract all links from body (wiki + markdown) and frontmatter
        body_links = extract_all_links(body)
        frontmatter_links = extract_frontmatter_links(meta)
        all_links = body_links + frontmatter_links
    except Exception:
        todo_exclude = 0
        all_links = []

    db = get_db()

    # Upsert note (now includes content, mtime, and todo_exclude columns)
    # Use normalize_path for consistent path format with todos table
    normalized_note_path = normalize_path(note.path)
    db.execute(
        """
        INSERT OR REPLACE INTO notes (path, title, date, notebook, content_hash, content, mtime, todo_exclude, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_note_path,
            note.title,
            note.date.isoformat() if note.date else None,
            note.notebook,
            note.content_hash,
            content,
            mtime,
            todo_exclude,
            datetime.now().isoformat(),
        ),
    )

    # Update tags
    db.execute("DELETE FROM note_tags WHERE note_path = ?", (normalized_note_path,))
    if note.tags:
        db.executemany(
            "INSERT INTO note_tags (note_path, tag) VALUES (?, ?)",
            [(normalized_note_path, tag) for tag in note.tags],
        )

    # Update links (using extracted links with full metadata)
    # Use INSERT OR IGNORE to handle duplicate target links in the same note
    db.execute("DELETE FROM note_links WHERE source_path = ?", (normalized_note_path,))
    if all_links:
        db.executemany(
            """INSERT OR IGNORE INTO note_links
               (source_path, target_path, display_text, link_type, is_external)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (
                    normalized_note_path,
                    target,
                    display,
                    link_type,
                    1 if is_external else 0,
                )
                for target, display, link_type, is_external in all_links
            ],
        )

    # Update sections (path-based subdirectory hierarchy)
    from nb.core.note_parser import get_sections_for_path

    sections = get_sections_for_path(note.path)
    db.execute("DELETE FROM note_sections WHERE note_path = ?", (normalized_note_path,))
    if sections:
        db.executemany(
            "INSERT INTO note_sections (note_path, section, depth) VALUES (?, ?, ?)",
            [
                (normalized_note_path, section, depth)
                for depth, section in enumerate(sections)
            ],
        )

    db.commit()

    # Index to localvectordb for search
    if index_vectors and ENABLE_VECTOR_INDEXING and content:
        try:
            from nb.index.search import get_search

            search = get_search()
            search.index_note(note, content)
        except Exception as e:
            # Don't fail indexing if vector search fails
            # (e.g., embedding service not available)
            _logger.debug("Vector indexing failed for %s: %s", path, e)

    # Index todos (file was already normalized at the start of this function)
    config = get_config()
    if full_path.name == config.todo.inbox_file:
        source_type = "inbox"
    else:
        source_type = "note"

    # Preserve dates before deleting (so we can restore them after re-indexing)
    preserved_dates = get_todo_dates_for_source(full_path)

    # Delete existing todos for this file
    delete_todos_for_source(full_path)

    # Extract and index new todos (batch for performance)
    todos = extract_todos(full_path, source_type=source_type, notes_root=notes_root)
    upsert_todos_batch(todos, preserved_dates=preserved_dates)

    # Index attachments (delete existing first, then extract from content)
    delete_attachments_for_note(full_path)
    if content:
        # Extract note-level attachments
        note_attachments = extract_attachments_from_content(
            content,
            parent_type="note",
            parent_id=normalized_note_path,
            source_path=full_path,
        )
        if note_attachments:
            upsert_attachments_batch(note_attachments)


def count_files_to_index(
    notes_root: Path | None = None,
    force: bool = False,
    notebook: str | None = None,
) -> int:
    """Count the number of files that need to be indexed.

    This is useful for progress reporting - call before index_all_notes()
    to know the total count.

    Args:
        notes_root: Override notes root directory
        force: If True, count all files (not just changed ones)
        notebook: If specified, only count files in this notebook

    Returns:
        Number of files that need indexing.
    """
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    note_files = scan_notes(notes_root)

    # Filter to specific notebook if requested
    if notebook:
        notebook_config = config.get_notebook(notebook)
        if notebook_config:
            if notebook_config.path:
                notebook_path = notebook_config.path
            else:
                notebook_path = notes_root / notebook
            note_files = [
                f
                for f in note_files
                if notebook_path in f.parents or f.parent == notebook_path
            ]

    if force:
        return len(note_files)

    return len([path for path in note_files if needs_reindex(path, notes_root)])


def index_all_notes(
    notes_root: Path | None = None,
    force: bool = False,
    index_vectors: bool = True,
    max_workers: int = 4,
    notebook: str | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Index all notes in the notes root.

    Args:
        notes_root: Override notes root directory
        force: If True, reindex all files even if unchanged
        index_vectors: Whether to also index to localvectordb for search
        max_workers: Maximum number of parallel workers (default 4)
        notebook: If specified, only index files in this notebook
        on_progress: Optional callback called after each file is indexed.
            The callback receives the number of files indexed so far.

    Returns:
        Number of files indexed.

    """
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    note_files = scan_notes(notes_root)

    # Filter to specific notebook if requested
    if notebook:
        notebook_config = config.get_notebook(notebook)
        if notebook_config:
            if notebook_config.path:
                # External notebook - filter by its path
                notebook_path = notebook_config.path
            else:
                # Internal notebook - filter by notebook directory
                notebook_path = notes_root / notebook
            note_files = [
                f
                for f in note_files
                if notebook_path in f.parents or f.parent == notebook_path
            ]

    # Filter to files that need reindexing
    files_to_index = [
        path for path in note_files if force or needs_reindex(path, notes_root)
    ]

    if not files_to_index:
        return 0

    # For small batches or when vectors are needed, use sequential processing
    # (vector indexing may not be thread-safe)
    if len(files_to_index) <= 3 or (index_vectors and ENABLE_VECTOR_INDEXING):
        count = 0
        for path in files_to_index:
            try:
                index_note(path, notes_root, index_vectors=index_vectors)
                count += 1
                if on_progress:
                    on_progress(1)  # Advance by 1 (not cumulative count)
            except Exception:
                pass
        return count

    # Parallel processing for larger batches without vector indexing
    count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                index_note_threadsafe, path, notes_root, index_vectors
            ): path
            for path in files_to_index
        }
        for future in as_completed(futures):
            try:
                future.result()
                count += 1
                if on_progress:
                    on_progress(1)  # Advance by 1 (not cumulative count)
            except Exception:
                # Log error but continue with other files
                pass

    return count


def index_note_threadsafe(
    path: Path,
    notes_root: Path,
    index_vectors: bool = True,
) -> None:
    """Thread-safe version of index_note for use from background threads.

    Uses thread-local database connections to avoid SQLite threading issues.
    Call this instead of index_note() when indexing from a background thread.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    # Resolve full path first
    if path.is_absolute():
        full_path = path
    else:
        full_path = notes_root / path

    # Normalize relative due dates FIRST (e.g., @due(today) -> @due(2025-12-01))
    # This must happen before reading content/hash to avoid re-indexing next time
    normalize_due_dates_in_file(full_path)

    # Now read the normalized content and compute hash
    note = get_note(path, notes_root)
    if not note:
        return

    # Read the full content for storage and vector indexing
    try:
        content = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        content = ""

    # Get file mtime for caching (after normalization)
    try:
        mtime = full_path.stat().st_mtime
    except OSError:
        mtime = None

    # Check for todo_exclude in frontmatter and extract links
    from nb.utils.markdown import (
        extract_all_links,
        extract_frontmatter_links,
        extract_todo_exclude,
        parse_note_file,
    )

    try:
        meta, body = parse_note_file(full_path)
        todo_exclude = 1 if extract_todo_exclude(meta) else 0
        # Extract all links from body (wiki + markdown) and frontmatter
        body_links = extract_all_links(body)
        frontmatter_links = extract_frontmatter_links(meta)
        all_links = body_links + frontmatter_links
    except Exception:
        todo_exclude = 0
        all_links = []

    # Use thread-local database connection
    db = _get_thread_db()

    # Upsert note
    # Use normalize_path for consistent path format with todos table
    normalized_note_path = normalize_path(note.path)
    db.execute(
        """
        INSERT OR REPLACE INTO notes (path, title, date, notebook, content_hash, content, mtime, todo_exclude, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_note_path,
            note.title,
            note.date.isoformat() if note.date else None,
            note.notebook,
            note.content_hash,
            content,
            mtime,
            todo_exclude,
            datetime.now().isoformat(),
        ),
    )

    # Update tags
    db.execute("DELETE FROM note_tags WHERE note_path = ?", (normalized_note_path,))
    if note.tags:
        db.executemany(
            "INSERT INTO note_tags (note_path, tag) VALUES (?, ?)",
            [(normalized_note_path, tag) for tag in note.tags],
        )

    # Update links (using extracted links with full metadata)
    # Use INSERT OR IGNORE to handle duplicate target links in the same note
    db.execute("DELETE FROM note_links WHERE source_path = ?", (normalized_note_path,))
    if all_links:
        db.executemany(
            """INSERT OR IGNORE INTO note_links
               (source_path, target_path, display_text, link_type, is_external)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (
                    normalized_note_path,
                    target,
                    display,
                    link_type,
                    1 if is_external else 0,
                )
                for target, display, link_type, is_external in all_links
            ],
        )

    # Update sections (path-based subdirectory hierarchy)
    from nb.core.note_parser import get_sections_for_path

    sections = get_sections_for_path(note.path)
    db.execute("DELETE FROM note_sections WHERE note_path = ?", (normalized_note_path,))
    if sections:
        db.executemany(
            "INSERT INTO note_sections (note_path, section, depth) VALUES (?, ?, ?)",
            [
                (normalized_note_path, section, depth)
                for depth, section in enumerate(sections)
            ],
        )

    db.commit()

    # Index to localvectordb for search (with lock for thread safety)
    if index_vectors and ENABLE_VECTOR_INDEXING and content:
        with _vector_lock:
            try:
                from nb.index.search import get_search

                search = get_search()
                search.index_note(note, content)
            except Exception as e:
                _logger.debug("Vector indexing failed for %s: %s", path, e)

    # Index todos (file was already normalized at the start of this function)
    config = get_config()
    if full_path.name == config.todo.inbox_file:
        source_type = "inbox"
    else:
        source_type = "note"

    # Preserve dates before deleting (so we can restore them after re-indexing)
    preserved_dates = get_todo_dates_for_source(full_path, db=db)

    # Delete existing todos for this file (use thread-local db for thread safety)
    delete_todos_for_source(full_path, db=db)

    # Extract and index new todos (batch for performance, use thread-local db)
    todos = extract_todos(full_path, source_type=source_type, notes_root=notes_root)
    upsert_todos_batch(todos, db=db, preserved_dates=preserved_dates)

    # Index attachments (delete existing first, then extract from content)
    delete_attachments_for_note(full_path, db=db)
    if content:
        # Extract note-level attachments
        note_attachments = extract_attachments_from_content(
            content,
            parent_type="note",
            parent_id=normalized_note_path,
            source_path=full_path,
        )
        if note_attachments:
            upsert_attachments_batch(note_attachments, db=db)


def rebuild_search_index(
    notes_root: Path | None = None,
    notebook: str | None = None,
    on_progress: Callable[[int], None] | None = None,
    batch_size: int = 25,
) -> int:
    """Rebuild the localvectordb search index from scratch.

    Reads all notes from the database and indexes them to localvectordb.
    Useful when the vector index is corrupted or needs to be regenerated.

    Uses batch indexing for significantly better performance - batching
    reduces the number of embedding API calls.

    Args:
        notes_root: Override notes root directory
        notebook: If specified, only rebuild index for this notebook
        on_progress: Optional callback called after each note is indexed.
            The callback receives the number of notes indexed so far.
        batch_size: Number of notes to index in each batch (default 25).

    Returns:
        Number of notes indexed.

    """
    from nb.models import Note

    if notes_root is None:
        notes_root = get_config().notes_root

    if not ENABLE_VECTOR_INDEXING:
        return 0

    from nb.index.search import get_search

    db = get_db()
    search = get_search()

    # Get notes from database (optionally filtered by notebook)
    if notebook:
        rows = db.fetchall(
            "SELECT path, title, date, notebook, content FROM notes WHERE notebook = ?",
            (notebook,),
        )
    else:
        rows = db.fetchall("SELECT path, title, date, notebook, content FROM notes")

    if not rows:
        return 0

    count = 0
    batch: list[tuple[Note, str]] = []
    pending_progress = 0  # Track notes added to batch but not yet reported
    first_error: Exception | None = None  # Track first error for reporting

    def flush_batch() -> int:
        """Flush the current batch to the search index."""
        nonlocal batch, first_error
        if not batch:
            return 0
        try:
            indexed = search.index_notes_batch(batch)
            batch = []
            return indexed
        except Exception as e:
            # Capture first error for reporting
            if first_error is None:
                first_error = e
            # Fall back to one-by-one indexing on batch failure
            indexed = 0
            for note, content in batch:
                try:
                    search.index_note(note, content)
                    indexed += 1
                except Exception:
                    pass
            batch = []
            return indexed

    for row in rows:
        if not row["content"]:
            continue

        # Build a simple note-like object for indexing
        note = Note(
            path=Path(row["path"]),
            title=row["title"] or "",
            date=None,  # Will be parsed from string if needed
            tags=[],  # We'd need to query tags separately
            links=[],
            attachments=[],
            notebook=row["notebook"] or "",
            content_hash="",
        )

        # Get tags for this note
        tag_rows = db.fetchall(
            "SELECT tag FROM note_tags WHERE note_path = ?",
            (row["path"],),
        )
        note.tags = [r["tag"] for r in tag_rows]

        # Parse date if present
        if row["date"]:
            from datetime import date as date_type

            try:
                note.date = date_type.fromisoformat(row["date"])
            except ValueError:
                pass

        batch.append((note, row["content"]))
        pending_progress += 1

        # Flush batch when it reaches the batch size
        if len(batch) >= batch_size:
            indexed = flush_batch()
            count += indexed
            # Report progress for all notes in the batch
            if on_progress:
                on_progress(pending_progress)  # Advance by batch size
            pending_progress = 0

    # Flush any remaining notes
    if batch:
        indexed = flush_batch()
        count += indexed
        if on_progress:
            on_progress(pending_progress)  # Advance by remaining count

    # If no notes were indexed but we had notes to index, raise the first error
    if count == 0 and first_error is not None:
        raise first_error

    return count


def count_notes_for_search_rebuild(notebook: str | None = None) -> int:
    """Count notes that will be processed during search index rebuild.

    Args:
        notebook: If specified, only count notes in this notebook.

    Returns:
        Number of notes with content to index.
    """
    if not ENABLE_VECTOR_INDEXING:
        return 0

    db = get_db()
    if notebook:
        row = db.fetchone(
            "SELECT COUNT(*) as cnt FROM notes WHERE notebook = ? AND content IS NOT NULL AND content != ''",
            (notebook,),
        )
    else:
        row = db.fetchone(
            "SELECT COUNT(*) as cnt FROM notes WHERE content IS NOT NULL AND content != ''"
        )
    return row["cnt"] if row else 0


def sync_search_index(
    notebook: str | None = None,
    on_progress: Callable[[int], None] | None = None,
    batch_size: int = 25,
) -> int:
    """Sync notes from SQLite to VectorDB that are missing from VectorDB.

    This is more efficient than a full rebuild when only some notes are missing.
    Uses batch indexing for better performance.

    Args:
        notebook: If specified, only sync notes from this notebook
        on_progress: Optional callback called after each batch is synced.
            The callback receives the number of notes synced so far.
        batch_size: Number of notes to index in each batch (default 25).

    Returns:
        Number of notes synced.

    """
    from nb.models import Note

    if not ENABLE_VECTOR_INDEXING:
        return 0

    from nb.index.search import get_search

    db = get_db()
    search = get_search()

    # Get all note paths from SQLite (optionally filtered by notebook)
    if notebook:
        sqlite_rows = db.fetchall(
            "SELECT path, title, date, notebook, content FROM notes WHERE notebook = ?",
            (notebook,),
        )
    else:
        sqlite_rows = db.fetchall(
            "SELECT path, title, date, notebook, content FROM notes"
        )

    if not sqlite_rows:
        return 0

    # Get all note paths from VectorDB
    try:
        vector_filter = {"notebook": notebook} if notebook else {}
        vector_docs = search.db.filter(where=vector_filter, limit=10000)
        vector_paths = {d.metadata.get("path") for d in vector_docs}
    except Exception:
        # If VectorDB query fails, treat as empty
        vector_paths = set()

    count = 0
    batch: list[tuple[Note, str]] = []
    pending_progress = 0  # Track notes added to batch but not yet reported
    first_error: Exception | None = None  # Track first error for reporting

    def flush_batch() -> int:
        """Flush the current batch to the search index."""
        nonlocal batch, first_error
        if not batch:
            return 0
        try:
            indexed = search.index_notes_batch(batch)
            batch = []
            return indexed
        except Exception as e:
            # Capture first error for reporting
            if first_error is None:
                first_error = e
            # Fall back to one-by-one indexing on batch failure
            indexed = 0
            for note, content in batch:
                try:
                    search.index_note(note, content)
                    indexed += 1
                except Exception:
                    pass
            batch = []
            return indexed

    # Find notes in SQLite but not in VectorDB
    for row in sqlite_rows:
        if row["path"] in vector_paths:
            continue

        if not row["content"]:
            continue

        # Build note object
        note = Note(
            path=Path(row["path"]),
            title=row["title"] or "",
            date=None,
            tags=[],
            links=[],
            attachments=[],
            notebook=row["notebook"] or "",
            content_hash="",
        )

        # Get tags
        tag_rows = db.fetchall(
            "SELECT tag FROM note_tags WHERE note_path = ?",
            (row["path"],),
        )
        note.tags = [r["tag"] for r in tag_rows]

        # Parse date
        if row["date"]:
            from datetime import date as date_type

            try:
                note.date = date_type.fromisoformat(row["date"])
            except ValueError:
                pass

        batch.append((note, row["content"]))
        pending_progress += 1

        # Flush batch when it reaches the batch size
        if len(batch) >= batch_size:
            indexed = flush_batch()
            count += indexed
            # Report progress for all notes in the batch
            if on_progress:
                on_progress(pending_progress)  # Advance by batch size
            pending_progress = 0

    # Flush any remaining notes
    if batch:
        indexed = flush_batch()
        count += indexed
        if on_progress:
            on_progress(pending_progress)  # Advance by remaining count

    # If no notes were synced but we had notes to sync, raise the first error
    if count == 0 and first_error is not None:
        raise first_error

    return count


def index_todos_from_file(path: Path, notes_root: Path | None = None) -> int:
    """Index todos from a single file.

    Returns the number of todos indexed.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    config = get_config()
    if not path.is_absolute():
        path = notes_root / path

    # Determine source type
    if path.name == config.todo.inbox_file:
        source_type = "inbox"
    else:
        source_type = "note"

    # Preserve dates before deleting
    preserved_dates = get_todo_dates_for_source(path)

    # Delete existing todos for this file
    delete_todos_for_source(path)

    # Normalize relative due dates (e.g., @due(today) -> @due(2025-12-01))
    normalize_due_dates_in_file(path)

    # Extract and index new todos (batch for performance)
    todos = extract_todos(path, source_type=source_type, notes_root=notes_root)
    upsert_todos_batch(todos, preserved_dates=preserved_dates)

    return len(todos)


def scan_linked_files() -> int:
    """Scan all linked external todo files and index their todos.

    Returns the number of todos indexed.
    """
    from nb.core.links import list_linked_files

    linked_files = list_linked_files()
    total_todos = 0

    for linked in linked_files:
        if not linked.path.exists():
            continue

        # Preserve dates before deleting
        preserved_dates = get_todo_dates_for_source(linked.path)

        # Delete existing todos for this linked file
        delete_todos_for_source(linked.path)

        # Normalize relative due dates if sync is enabled
        if linked.sync:
            normalize_due_dates_in_file(linked.path)

        # Extract and index todos (batch for performance)
        todos = extract_todos(
            linked.path,
            source_type="linked",
            notes_root=get_config().notes_root,
            external=True,
            alias=linked.alias,
        )

        upsert_todos_batch(todos, preserved_dates=preserved_dates)
        total_todos += len(todos)

    return total_todos


def index_linked_file(path: Path, alias: str | None = None) -> int:
    """Index todos from a single linked external file.

    Args:
        path: Path to the linked file.
        alias: Optional alias for the file.

    Returns:
        Number of todos indexed.

    """
    if not path.exists():
        return 0

    # Preserve dates before deleting
    preserved_dates = get_todo_dates_for_source(path)

    # Delete existing todos for this file
    delete_todos_for_source(path)

    # Extract and index todos (batch for performance)
    todos = extract_todos(
        path,
        source_type="linked",
        notes_root=get_config().notes_root,
        external=True,
        alias=alias,
    )

    upsert_todos_batch(todos, preserved_dates=preserved_dates)

    return len(todos)


def remove_deleted_notes(
    notes_root: Path | None = None, notebook: str | None = None
) -> int:
    """Remove notes from the database that no longer exist on disk.

    Also removes associated todos and entries from the localvectordb search index.

    Args:
        notes_root: Root path for notes. Defaults to config.notes_root.
        notebook: Optional notebook name to limit cleanup to. If provided, only
            notes within that notebook's directory are checked.

    Returns the number of notes removed.
    """
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    db = get_db()

    # Build query to select internal notes, optionally filtered by notebook
    if notebook:
        notebook_config = config.get_notebook(notebook)
        if notebook_config:
            if notebook_config.path:
                # External notebook - external=1 in db, path is absolute
                rows = db.fetchall(
                    "SELECT path, external FROM notes WHERE external = 1 AND source_alias = ?",
                    (notebook,),
                )
                # For external notebooks, path is absolute
                check_root = Path()  # Use path as-is
            else:
                # Internal notebook - filter by path prefix
                notebook_prefix = f"{notebook}/"
                rows = db.fetchall(
                    "SELECT path, external FROM notes WHERE (external IS NULL OR external = 0) "
                    "AND (path LIKE ? OR path LIKE ?)",
                    (f"{notebook_prefix}%", f"{notebook}\\%"),
                )
                check_root = notes_root
        else:
            # Invalid notebook name, nothing to remove
            return 0
    else:
        # Only check internal notes (external=0 or NULL)
        rows = db.fetchall(
            "SELECT path, external FROM notes WHERE external IS NULL OR external = 0"
        )
        check_root = notes_root

    removed = 0
    removed_paths = []

    for row in rows:
        if notebook and notebook_config and notebook_config.path:
            # External notebook: path is absolute
            full_path = Path(row["path"])
        else:
            full_path = check_root / row["path"]

        if not full_path.exists():
            # Delete todos for this note first
            delete_todos_for_source(full_path)
            # Then delete the note
            db.execute("DELETE FROM notes WHERE path = ?", (row["path"],))
            removed_paths.append(row["path"])
            removed += 1

    if removed:
        db.commit()

        # Remove from localvectordb search index
        if ENABLE_VECTOR_INDEXING:
            try:
                from nb.index.search import get_search

                search = get_search()
                for path in removed_paths:
                    search.delete_note(path)
            except Exception as e:
                # Don't fail if vector search cleanup fails
                _logger.debug("Vector cleanup failed: %s", e)

    return removed


# =============================================================================
# Linked Note Indexing
# =============================================================================


def index_linked_note(
    path: Path,
    notebook: str,
    alias: str,
    notes_root: Path | None = None,
    index_vectors: bool = True,
    todo_exclude: bool = False,
    sync: bool = True,
) -> None:
    """Index a single linked (external) note file.

    Args:
        path: Absolute path to the note file.
        notebook: Virtual notebook name for the note.
        alias: Alias of the linked note source.
        notes_root: Override notes root directory.
        index_vectors: Whether to index for vector search.
        todo_exclude: Whether to exclude todos from this linked note.
        sync: Whether to sync changes (like normalizing due dates) back to the file.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    note = get_note(path, notes_root)
    if not note:
        return

    # Override notebook for linked notes
    note.notebook = notebook

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        content = ""

    # Get file mtime for caching
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    # Determine effective todo_exclude with proper precedence:
    # 1. If frontmatter explicitly sets todo_exclude (true OR false), use that
    # 2. Otherwise, inherit from link config OR notebook config
    from nb.utils.markdown import (
        extract_all_links,
        extract_frontmatter_links,
        parse_note_file,
    )

    frontmatter_has_explicit_value = False
    frontmatter_exclude = False
    all_links: list[tuple[str, str, str, bool]] = []

    try:
        meta, body = parse_note_file(path)
        if "todo_exclude" in meta:
            frontmatter_has_explicit_value = True
            frontmatter_exclude = bool(meta.get("todo_exclude", False))
        # Extract all links from body (wiki + markdown) and frontmatter
        body_links = extract_all_links(body)
        frontmatter_links = extract_frontmatter_links(meta)
        all_links = body_links + frontmatter_links
    except Exception:
        pass

    # Check notebook-level todo_exclude from config.yaml
    config = get_config()
    nb_config = config.get_notebook(notebook)
    notebook_exclude = nb_config.todo_exclude if nb_config else False

    # Precedence: frontmatter > link config/notebook config
    if frontmatter_has_explicit_value:
        # Frontmatter explicitly set - use its value (can be True OR False)
        effective_todo_exclude = frontmatter_exclude
    else:
        # Inherit from link config OR notebook config
        effective_todo_exclude = todo_exclude or notebook_exclude

    db = get_db()

    # Use normalized path as the unique identifier for external notes
    # This ensures consistency with how todos store source_path
    note_path = normalize_path(path)

    # Upsert note with external flag and todo_exclude
    db.execute(
        """
        INSERT OR REPLACE INTO notes
        (path, title, date, notebook, content_hash, content, mtime, external, source_alias, todo_exclude, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            note_path,
            note.title,
            note.date.isoformat() if note.date else None,
            notebook,
            note.content_hash,
            content,
            mtime,
            1,  # external = True
            alias,
            1 if effective_todo_exclude else 0,
            datetime.now().isoformat(),
        ),
    )

    # Update tags
    db.execute("DELETE FROM note_tags WHERE note_path = ?", (note_path,))
    if note.tags:
        db.executemany(
            "INSERT INTO note_tags (note_path, tag) VALUES (?, ?)",
            [(note_path, tag) for tag in note.tags],
        )

    # Update links (using extracted links with full metadata)
    # Use INSERT OR IGNORE to handle duplicate target links in the same note
    db.execute("DELETE FROM note_links WHERE source_path = ?", (note_path,))
    if all_links:
        db.executemany(
            """INSERT OR IGNORE INTO note_links
               (source_path, target_path, display_text, link_type, is_external)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (note_path, target, display, link_type, 1 if is_external else 0)
                for target, display, link_type, is_external in all_links
            ],
        )

    db.commit()

    # Index to localvectordb
    if index_vectors and ENABLE_VECTOR_INDEXING and content:
        try:
            from nb.index.search import get_search

            # Update path for search to include notebook context
            note.path = Path(note_path)
            search = get_search()
            search.index_note(note, content)
        except Exception:
            pass

    # Also index todos from this file (batch for performance)
    # Preserve dates before deleting
    preserved_dates = get_todo_dates_for_source(path)
    delete_todos_for_source(path)

    # Normalize relative due dates if sync is enabled
    if sync:
        normalize_due_dates_in_file(path)

    todos = extract_todos(
        path,
        source_type="linked",
        external=True,
        alias=alias,
        notes_root=notes_root,
        notebook=notebook,
    )
    upsert_todos_batch(todos, preserved_dates=preserved_dates)


def scan_linked_notes(
    notebook_filter: str | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Scan all linked external note files/directories and index them.

    Args:
        notebook_filter: If specified, only scan linked notes for this notebook.
        on_progress: Optional callback called after each note is indexed.
            The callback receives the number of notes indexed so far.

    Returns the number of notes indexed.
    """
    from nb.core.links import list_linked_notes, scan_linked_note_files

    linked_notes = list_linked_notes()
    total_notes = 0

    for linked in linked_notes:
        if not linked.path.exists():
            continue

        notebook = linked.notebook or f"@{linked.alias}"

        # Filter by notebook if specified
        if notebook_filter and notebook != notebook_filter:
            continue

        # Get all files from this linked source
        files = scan_linked_note_files(linked)

        for file_path in files:
            index_linked_note(
                file_path,
                notebook=notebook,
                alias=linked.alias,
                todo_exclude=linked.todo_exclude,
                sync=linked.sync,
            )
            total_notes += 1
            if on_progress:
                on_progress(1)  # Advance by 1 (not cumulative count)

    return total_notes


def count_linked_notes(notebook_filter: str | None = None) -> int:
    """Count the number of linked notes that would be scanned.

    Args:
        notebook_filter: If specified, only count linked notes for this notebook.

    Returns:
        Total number of linked note files.
    """
    from nb.core.links import list_linked_notes, scan_linked_note_files

    linked_notes = list_linked_notes()
    total = 0

    for linked in linked_notes:
        if not linked.path.exists():
            continue

        notebook = linked.notebook or f"@{linked.alias}"
        if notebook_filter and notebook != notebook_filter:
            continue

        files = scan_linked_note_files(linked)
        total += len(files)

    return total


def index_single_linked_note(alias: str) -> int:
    """Index notes from a single linked note source.

    Args:
        alias: Alias of the linked note.

    Returns:
        Number of notes indexed.

    """
    from nb.core.links import get_linked_note, scan_linked_note_files

    linked = get_linked_note(alias)
    if not linked or not linked.path.exists():
        return 0

    files = scan_linked_note_files(linked)
    notebook = linked.notebook or f"@{linked.alias}"

    for file_path in files:
        index_linked_note(
            file_path,
            notebook=notebook,
            alias=linked.alias,
            todo_exclude=linked.todo_exclude,
            sync=linked.sync,
        )

    return len(files)


def remove_linked_note_from_index(alias: str) -> int:
    """Remove all notes and todos from a linked source from the index.

    Args:
        alias: Alias of the linked note source.

    Returns:
        Number of notes removed.

    """
    db = get_db()

    # Get paths to remove from vector index
    rows = db.fetchall(
        "SELECT path FROM notes WHERE source_alias = ?",
        (alias,),
    )
    paths = [row["path"] for row in rows]

    # Remove notes from database
    cursor = db.execute(
        "DELETE FROM notes WHERE source_alias = ?",
        (alias,),
    )

    # Also remove todos from this linked source
    db.execute(
        "DELETE FROM todos WHERE source_alias = ?",
        (alias,),
    )

    db.commit()

    # Remove from vector index
    if ENABLE_VECTOR_INDEXING and paths:
        try:
            from nb.index.search import get_search

            search = get_search()
            for path in paths:
                search.delete_note(path)
        except Exception:
            pass

    return cursor.rowcount
