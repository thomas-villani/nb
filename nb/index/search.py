"""Unified search module using localvectordb for keyword, semantic, and hybrid search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from localvectordb import VectorDB
from localvectordb.core import MetadataField, MetadataFieldType

if TYPE_CHECKING:
    from nb.config import Config
    from nb.models import Note


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
        self._db: VectorDB | None = None

    @property
    def db(self) -> VectorDB:
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
                chunking_method="paragraphs",
                chunk_size=500,
            )
        return self._db

    def index_note(self, note: Note, content: str) -> None:
        """Add or update a note in the search index.

        Args:
            note: The note to index.
            content: The full text content of the note.
        """
        self.db.upsert(
            documents=[content],
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
        vector_weight: float = 0.7,
    ) -> list[SearchResult]:
        """Search notes using keyword, semantic, or hybrid search.

        Args:
            query: The search query.
            search_type: One of "keyword", "vector", or "hybrid".
            k: Maximum number of results to return.
            filters: Optional metadata filters (e.g., {"notebook": "daily"}).
            vector_weight: Weight for vector results in hybrid search (0-1).

        Returns:
            List of search results sorted by relevance.
        """
        try:
            results = self.db.query(
                query,
                search_type=search_type,
                k=k,
                filters=filters,
                vector_weight=vector_weight,
            )
        except Exception as e:
            # Handle case where index is empty or query fails
            if "empty" in str(e).lower() or "no documents" in str(e).lower():
                return []
            raise

        return [
            SearchResult(
                path=r.metadata.get("path", ""),
                title=r.metadata.get("title"),
                snippet=r.content[:200] if r.content else "",
                score=r.score,
                notebook=r.metadata.get("notebook"),
                date=r.metadata.get("date"),
                tags=r.metadata.get("tags"),
            )
            for r in results
        ]

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
) -> list[GrepResult]:
    """Search notes with regex pattern matching.

    Unlike the localvectordb search, this performs raw regex matching
    on the markdown files directly.

    Args:
        pattern: Regex pattern to search for.
        notes_root: Root directory containing notes.
        context_lines: Number of lines of context before/after match.
        case_sensitive: Whether to do case-sensitive matching.

    Returns:
        List of grep results with matched lines and context.
    """
    results = []
    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    # Find all markdown files, excluding .nb directory
    for md_file in notes_root.rglob("*.md"):
        # Skip hidden directories and .nb
        if any(part.startswith(".") for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Skip files we can't read
            continue

        lines = content.splitlines()
        for i, line in enumerate(lines):
            if regex.search(line):
                results.append(
                    GrepResult(
                        path=md_file.relative_to(notes_root),
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
