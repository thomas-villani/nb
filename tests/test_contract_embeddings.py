"""Contract tests for embeddings and vector search.

These tests verify that the embedding pipeline works correctly with real
API calls. They require OPENAI_API_KEY for OpenAI embeddings.

Run with: pytest -m contract tests/test_contract_embeddings.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nb import config as config_module
from nb.cli import utils as cli_utils_module
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.core import note_links as note_links_module
from nb.core import notebooks as notebooks_module
from nb.core import templates as templates_module
from nb.core.ai import summarize as summarize_module
from nb.index import scanner as scanner_module
from nb.index.db import reset_db
from nb.index.scanner import index_note
from nb.index.search import NoteSearch, reset_search

requires_openai_key = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="requires OPENAI_API_KEY environment variable",
)


@pytest.mark.contract
@requires_openai_key
class TestOpenAIEmbeddingsContract:
    """Contract tests for OpenAI embeddings via localvectordb."""

    @pytest.fixture
    def vectorized_notes_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Set up notes root with vector indexing enabled."""
        notes_root = tmp_path / "notes"
        notes_root.mkdir()
        nb_dir = notes_root / ".nb"
        nb_dir.mkdir()

        cfg = Config(
            notes_root=notes_root,
            editor="echo",
            notebooks=[
                NotebookConfig(name="work", date_based=False),
            ],
            embeddings=EmbeddingsConfig(
                provider="openai",
                model="text-embedding-3-small",
            ),
        )

        # Create notebook directory
        (notes_root / "work").mkdir()

        # Enable vector indexing
        scanner_module.ENABLE_VECTOR_INDEXING = True

        # Patch config globally
        monkeypatch.setattr(config_module, "_config", cfg)
        monkeypatch.setattr(config_module, "get_config", lambda: cfg)
        monkeypatch.setattr(cli_utils_module, "get_config", lambda: cfg)
        monkeypatch.setattr(templates_module, "get_config", lambda: cfg)
        monkeypatch.setattr(notebooks_module, "get_config", lambda: cfg)
        monkeypatch.setattr(note_links_module, "get_config", lambda: cfg)
        monkeypatch.setattr(summarize_module, "get_config", lambda: cfg)

        yield notes_root, cfg

        # Cleanup
        scanner_module.ENABLE_VECTOR_INDEXING = True
        reset_search()
        config_module.reset_config()
        reset_db()

    def test_index_and_search_returns_results(self, vectorized_notes_root):
        """Verify indexing creates embeddings and search finds them."""
        notes_root, cfg = vectorized_notes_root

        # Create a test note
        note_path = notes_root / "work" / "meeting.md"
        note_path.write_text(
            "# Budget Meeting\n\n"
            "We discussed the Q4 budget allocation.\n"
            "The total budget is $500,000 for the department.",
            encoding="utf-8",
        )

        # Index the note (this should create embeddings)
        index_note(note_path, notes_root)

        # Search for it
        search = NoteSearch(cfg)
        results = search.search("budget allocation", k=5)

        assert len(results) > 0
        assert any("meeting" in r.metadata.get("path", "").lower() for r in results)

    def test_semantic_search_finds_related_content(self, vectorized_notes_root):
        """Verify semantic search finds conceptually related content."""
        notes_root, cfg = vectorized_notes_root

        # Create notes with related but different wording
        note1_path = notes_root / "work" / "finances.md"
        note1_path.write_text(
            "# Financial Planning\n\n"
            "Our quarterly revenue exceeded expectations.\n"
            "The profit margin improved by 15%.",
            encoding="utf-8",
        )

        note2_path = notes_root / "work" / "unrelated.md"
        note2_path.write_text(
            "# Gardening Tips\n\n"
            "Plant tomatoes in spring for best results.\n"
            "Water daily and ensure good sunlight.",
            encoding="utf-8",
        )

        # Index both notes
        index_note(note1_path, notes_root)
        index_note(note2_path, notes_root)

        # Semantic search for "money" should find finances.md
        search = NoteSearch(cfg)
        results = search.search("money earnings", search_type="vector", k=5)

        assert len(results) > 0
        # Financial note should rank higher than gardening
        paths = [r.metadata.get("path", "") for r in results]
        finance_idx = next((i for i, p in enumerate(paths) if "finances" in p), 999)
        garden_idx = next((i for i, p in enumerate(paths) if "unrelated" in p), 999)
        assert (
            finance_idx < garden_idx
        ), "Financial note should rank higher for money-related query"

    def test_hybrid_search_combines_keyword_and_vector(self, vectorized_notes_root):
        """Verify hybrid search works with both keyword and semantic matching."""
        notes_root, cfg = vectorized_notes_root

        # Create a note with specific keywords
        note_path = notes_root / "work" / "project_alpha.md"
        note_path.write_text(
            "# Project Alpha Status\n\n"
            "The alpha project is progressing well.\n"
            "We expect to complete the first milestone next week.",
            encoding="utf-8",
        )

        index_note(note_path, notes_root)

        # Hybrid search should find by keyword
        search = NoteSearch(cfg)
        results = search.search("alpha milestone", search_type="hybrid", k=5)

        assert len(results) > 0
        assert any("alpha" in r.metadata.get("path", "").lower() for r in results)
