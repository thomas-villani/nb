"""Unified search module using localvectordb for keyword, semantic, and hybrid search."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from localvectordb import VectorDB
from localvectordb.core import MetadataField, MetadataFieldType

if TYPE_CHECKING:
    from nb.config import Config
    from nb.models import Note

_logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result from a search query."""

    path: str
    title: str | None
    snippet: str
    score: float
    notebook: str | None = None
    date: str | None = None
    tags: list[str] | None = None


@dataclass
class GrepResult:
    """Result from a grep (regex) search."""

    path: Path
    line_number: int
    line_content: str
    context_before: list[str]
    context_after: list[str]


# Metadata schema for notes in localvectordb
NOTES_SCHEMA = {
    "path": MetadataField(type=MetadataFieldType.TEXT, indexed=True),
    "title": MetadataField(
        type=MetadataFieldType.TEXT,
        indexed=True,
        embedding_enabled=True,
        fts_enabled=True,
    ),
    "notebook": MetadataField(type=MetadataFieldType.TEXT, indexed=True),
    "date": MetadataField(type=MetadataFieldType.DATE, indexed=True),
    "tags": MetadataField(type=MetadataFieldType.JSON),
}


def strip_images_for_embedding(content: str) -> str:
    """Strip images from markdown content before sending to vector embedding.

    Base64-encoded images can be extremely large and exceed token limits for
    embedding models. This function removes all images using all2md's AST
    processing to ensure clean text is sent for embedding.

    Args:
        content: Markdown content that may contain images.

    Returns:
        Markdown content with all images removed.
    """
    if not content:
        return content

    try:
        from all2md import to_markdown
        from all2md.transforms import RemoveImagesTransform

        # Parse markdown and render with transform applied
        return to_markdown(
            content,
            source_format="markdown",
            transforms=[RemoveImagesTransform()],
        )
    except Exception as e:
        # If transform fails, fall back to original content
        # This ensures indexing continues even if all2md has issues
        _logger.debug("Failed to strip images from content: %s", e)
        return content


class NoteSearch:
    """Unified search interface using localvectordb.

    Supports keyword search (FTS5), semantic search (vectors),
    and hybrid search (combined).
    """

    def __init__(self, config: Config):
        """Initialize the search engine.

        Args:
            config: Application configuration with embedding settings.

        """
        self.config = config
        self._db: Any = None

    def __del__(self):
        if self._db is not None:
            self._db.close()

    @property
    def db(self) -> Any:
        """Lazy-initialize the VectorDB connection."""
        if self._db is None:
            # Build embedding config
            embedding_config = {}
            if self.config.embeddings.base_url:
                embedding_config["base_url"] = self.config.embeddings.base_url
            if self.config.embeddings.api_key:
                embedding_config["api_key"] = self.config.embeddings.api_key

            self._db = VectorDB(
                name="notes",
                base_path=str(self.config.vectors_path),
                metadata_schema=NOTES_SCHEMA,
                embedding_provider=self.config.embeddings.provider,
                embedding_model=self.config.embeddings.model,
                embedding_config=embedding_config if embedding_config else None,
                chunking_method=self.config.embeddings.chunking_method,
                chunk_size=self.config.embeddings.chunk_size,
            )
        return self._db

    def index_note(self, note: Note, content: str) -> None:
        """Add or update a note in the search index.

        Args:
            note: The note to index.
            content: The full text content of the note.

        """
        # Strip images (especially base64) to avoid exceeding embedding token limits
        clean_content = strip_images_for_embedding(content)

        self.db.upsert(
            documents=[clean_content],
            metadata=[
                {
                    "path": str(note.path),
                    "title": note.title,
                    "notebook": note.notebook,
                    "date": note.date.isoformat() if note.date else None,
                    "tags": note.tags,
                }
            ],
            ids=[str(note.path)],
        )

    def index_notes_batch(
        self,
        notes: list[tuple[Note, str]],
    ) -> int:
        """Add or update multiple notes in the search index in a single batch.

        This is significantly faster than calling index_note() repeatedly
        because it reduces the number of embedding API calls.

        Args:
            notes: List of (note, content) tuples to index.

        Returns:
            Number of notes successfully indexed.
        """
        if not notes:
            return 0

        documents = []
        metadata_list = []
        ids = []

        for note, content in notes:
            if not content:
                continue
            # Strip images (especially base64) to avoid exceeding embedding token limits
            clean_content = strip_images_for_embedding(content)
            documents.append(clean_content)
            metadata_list.append(
                {
                    "path": str(note.path),
                    "title": note.title,
                    "notebook": note.notebook,
                    "date": note.date.isoformat() if note.date else None,
                    "tags": note.tags,
                }
            )
            ids.append(str(note.path))

        if not documents:
            return 0

        self.db.upsert(
            documents=documents,
            metadata=metadata_list,
            ids=ids,
        )
        return len(documents)

    def delete_note(self, path: str) -> None:
        """Remove a note from the search index.

        Args:
            path: The path of the note to remove.

        """
        try:
            self.db.delete([path])
        except Exception:
            # Ignore errors if note doesn't exist in index
            pass

    def search(
        self,
        query: str,
        search_type: str = "hybrid",
        k: int = 10,
        filters: dict | None = None,
        vector_weight: float | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        recency_boost: float = 0.0,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        """Search notes using keyword, semantic, or hybrid search.

        Args:
            query: The search query.
            search_type: One of "keyword", "vector", or "hybrid".
            k: Maximum number of results to return.
            filters: Optional metadata filters (e.g., {"notebook": "daily"}).
            vector_weight: Weight for vector results in hybrid search (0-1).
                          If None, uses config.search.vector_weight.
            date_start: Filter to notes on or after this date (ISO format).
            date_end: Filter to notes on or before this date (ISO format).
            recency_boost: Weight (0-1) to boost recent results. 0 = no boost.
            score_threshold: Minimum score for result to be displayed.
                            If None, uses config.search.score_threshold.

        Returns:
            List of search results sorted by relevance (with optional recency boost).

        """
        # Use config defaults if not specified
        if vector_weight is None:
            vector_weight = self.config.search.vector_weight
        if score_threshold is None:
            score_threshold = self.config.search.score_threshold
        # Build combined filters
        combined_filters = dict(filters) if filters else {}

        # Add date range filters
        if date_start and date_end:
            combined_filters["date"] = {">=": date_start, "<=": date_end}
        elif date_start:
            combined_filters["date"] = {">=": date_start}
        elif date_end:
            combined_filters["date"] = {"<=": date_end}

        try:
            # Fetch more results if we're going to apply recency boost
            fetch_k = k * 3 if recency_boost > 0 else k
            results = self.db.query(
                query,
                search_type=search_type,
                k=fetch_k,
                filters=combined_filters if combined_filters else None,
                vector_weight=vector_weight,
                score_threshold=score_threshold,
                return_type="chunks",  # Return matching chunks, not whole documents
            )
        except Exception as e:
            # Handle case where index is empty or query fails
            if "empty" in str(e).lower() or "no documents" in str(e).lower():
                return []
            raise

        search_results = [
            SearchResult(
                path=r.metadata.get("path", ""),
                title=r.metadata.get("title"),
                snippet=r.content or "",  # Store full chunk content
                score=r.score,
                notebook=r.metadata.get("notebook"),
                date=r.metadata.get("date"),
                tags=r.metadata.get("tags"),
            )
            for r in results
        ]

        # Apply recency boost if requested
        if recency_boost > 0 and search_results:
            search_results = self._apply_recency_boost(search_results, recency_boost)

        return search_results[:k]

    async def search_async(
        self,
        query: str,
        search_type: str = "hybrid",
        k: int = 10,
        filters: dict | None = None,
        vector_weight: float | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        recency_boost: float = 0.0,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        """Async search notes using keyword, semantic, or hybrid search.

        This is the async version of search() that uses localvectordb's
        async query method for non-blocking search in TUI applications.

        Args:
            query: The search query.
            search_type: One of "keyword", "vector", or "hybrid".
            k: Maximum number of results to return.
            filters: Optional metadata filters (e.g., {"notebook": "daily"}).
            vector_weight: Weight for vector results in hybrid search (0-1).
                          If None, uses config.search.vector_weight.
            date_start: Filter to notes on or after this date (ISO format).
            date_end: Filter to notes on or before this date (ISO format).
            recency_boost: Weight (0-1) to boost recent results. 0 = no boost.
            score_threshold: Minimum score for result to be displayed.
                            If None, uses config.search.score_threshold.

        Returns:
            List of search results sorted by relevance (with optional recency boost).

        """
        # Use config defaults if not specified
        if vector_weight is None:
            vector_weight = self.config.search.vector_weight
        if score_threshold is None:
            score_threshold = self.config.search.score_threshold

        # Build combined filters
        combined_filters = dict(filters) if filters else {}

        # Add date range filters
        if date_start and date_end:
            combined_filters["date"] = {">=": date_start, "<=": date_end}
        elif date_start:
            combined_filters["date"] = {">=": date_start}
        elif date_end:
            combined_filters["date"] = {"<=": date_end}

        try:
            # Fetch more results if we're going to apply recency boost
            fetch_k = k * 3 if recency_boost > 0 else k
            results = await self.db.query_async(
                query,
                search_type=search_type,
                k=fetch_k,
                filters=combined_filters if combined_filters else None,
                vector_weight=vector_weight,
                score_threshold=score_threshold,
                return_type="chunks",  # Return matching chunks, not whole documents
            )
        except Exception as e:
            # Handle case where index is empty or query fails
            if "empty" in str(e).lower() or "no documents" in str(e).lower():
                return []
            raise

        search_results = [
            SearchResult(
                path=r.metadata.get("path", ""),
                title=r.metadata.get("title"),
                snippet=r.content or "",  # Store full chunk content
                score=r.score,
                notebook=r.metadata.get("notebook"),
                date=r.metadata.get("date"),
                tags=r.metadata.get("tags"),
            )
            for r in results
        ]

        # Apply recency boost if requested
        if recency_boost > 0 and search_results:
            search_results = self._apply_recency_boost(search_results, recency_boost)

        return search_results[:k]

    def _apply_recency_boost(
        self, results: list[SearchResult], boost_weight: float
    ) -> list[SearchResult]:
        """Apply a recency boost to search results.

        Recent documents get a score boost proportional to how recent they are.
        The boost decays exponentially over time using config.search.recency_decay_days
        as the half-life.

        Args:
            results: List of search results.
            boost_weight: How much to weight recency (0-1).

        Returns:
            Results re-sorted with recency boost applied.

        """
        from datetime import date as date_type

        today = date_type.today()
        decay_days = self.config.search.recency_decay_days

        for r in results:
            if r.date:
                try:
                    # Parse date and calculate age in days
                    note_date = date_type.fromisoformat(r.date)
                    age_days = (today - note_date).days

                    # Exponential decay with configurable half-life
                    # recency_factor is 1.0 for today, ~0.5 for decay_days ago, etc.
                    recency_factor = 2 ** (-age_days / decay_days)

                    # Combine relevance score with recency
                    # Final score = (1-weight)*relevance + weight*recency
                    r.score = (
                        1 - boost_weight
                    ) * r.score + boost_weight * recency_factor
                except (ValueError, TypeError):
                    pass  # Keep original score if date parsing fails

        # Re-sort by new score
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def search_by_tag(self, tag: str, k: int = 20) -> list[SearchResult]:
        """Find notes with a specific tag.

        Args:
            tag: The tag to search for.
            k: Maximum number of results.

        Returns:
            List of notes containing the tag.

        """
        try:
            docs = self.db.filter(
                where={"tags": {"$contains": tag}},
                limit=k,
            )
        except Exception:
            return []

        return [
            SearchResult(
                path=d.metadata.get("path", ""),
                title=d.metadata.get("title"),
                snippet=d.content[:200] if d.content else "",
                score=1.0,  # Filter results don't have scores
                notebook=d.metadata.get("notebook"),
                date=d.metadata.get("date"),
                tags=d.metadata.get("tags"),
            )
            for d in docs
        ]

    def close(self) -> None:
        """Close the VectorDB connection."""
        if self._db is not None:
            self._db.close()
            self._db = None


def grep_notes(
    pattern: str,
    notes_root: Path,
    context_lines: int = 2,
    case_sensitive: bool = False,
    notebook: str | None = None,
    note_path: Path | None = None,
) -> list[GrepResult]:
    """Search notes with regex pattern matching.

    Unlike the localvectordb search, this performs raw regex matching
    on the markdown files directly.

    Args:
        pattern: Regex pattern to search for.
        notes_root: Root directory containing notes.
        context_lines: Number of lines of context before/after match.
        case_sensitive: Whether to do case-sensitive matching.
        notebook: Filter to files in this notebook.
        note_path: Filter to a specific note file.

    Returns:
        List of grep results with matched lines and context.

    """
    from nb.config import get_config

    results = []
    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}") from None

    # If a specific note path is given, only search that file
    if note_path:
        files_to_search = [
            note_path if note_path.is_absolute() else notes_root / note_path
        ]
    else:
        # Find all markdown files, excluding .nb directory
        files_to_search = []

        # Get notebook config for filtering
        config = get_config()
        notebook_path = None

        if notebook:
            nb_config = config.get_notebook(notebook)
            if nb_config:
                if nb_config.path:
                    # External notebook
                    notebook_path = nb_config.path
                else:
                    # Internal notebook
                    notebook_path = notes_root / notebook

        # Scan notes_root
        for md_file in notes_root.rglob("*.md"):
            # Skip hidden directories and .nb
            if any(
                part.startswith(".") for part in md_file.relative_to(notes_root).parts
            ):
                continue

            # Apply notebook filter
            if notebook_path:
                if (
                    notebook_path not in md_file.parents
                    and md_file.parent != notebook_path
                ):
                    continue

            files_to_search.append(md_file)

        # Also search external notebooks
        for nb in config.external_notebooks():
            if nb.path and nb.path.exists():
                # If filtering by notebook, only include matching external notebooks
                if notebook and nb.name != notebook:
                    continue

                for md_file in nb.path.rglob("*.md"):
                    # Skip hidden directories
                    try:
                        rel_parts = md_file.relative_to(nb.path).parts
                        if any(part.startswith(".") for part in rel_parts):
                            continue
                    except ValueError:
                        continue
                    files_to_search.append(md_file)

    for md_file in files_to_search:
        # Skip hidden directories and .nb
        if any(part.startswith(".") for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Skip files we can't read
            continue

        # Determine relative path for display
        try:
            rel_path = md_file.relative_to(notes_root)
        except ValueError:
            # External file - use absolute path or just filename
            rel_path = md_file

        lines = content.splitlines()
        for i, line in enumerate(lines):
            if regex.search(line):
                results.append(
                    GrepResult(
                        path=rel_path,
                        line_number=i + 1,
                        line_content=line,
                        context_before=lines[max(0, i - context_lines) : i],
                        context_after=lines[i + 1 : i + 1 + context_lines],
                    )
                )

    return results


# Singleton search instance
_search: NoteSearch | None = None


def get_search() -> NoteSearch:
    """Get the global search instance.

    Initializes the search engine on first call.
    """
    global _search
    if _search is None:
        from nb.config import get_config

        config = get_config()
        _search = NoteSearch(config)
    return _search


def reset_search() -> None:
    """Reset the search instance (useful for testing)."""
    global _search
    if _search is not None:
        _search.close()
        _search = None
