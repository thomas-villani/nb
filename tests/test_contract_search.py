"""Contract tests for Serper web search API.

These tests call the real Serper API and validate that our client code
works correctly with actual API responses.

Run with: pytest -m contract tests/test_contract_search.py
"""

from __future__ import annotations

import os

import pytest

from nb.core.search import (
    SearchResult,
    format_results_as_markdown,
    search_news,
    search_web,
)

requires_serper_key = pytest.mark.skipif(
    not os.getenv("SERPER_API_KEY"),
    reason="requires SERPER_API_KEY environment variable",
)


@pytest.mark.contract
@requires_serper_key
class TestSerperWebSearchContract:
    """Contract tests for Serper web search API."""

    def test_web_search_returns_results(self):
        """Verify web search returns valid results."""
        results = search_web("python programming", num_results=5)

        assert len(results) > 0
        assert len(results) <= 5

        # Check result structure
        first = results[0]
        assert isinstance(first, SearchResult)
        assert first.title
        assert first.url
        assert first.url.startswith("http")
        assert first.snippet

    def test_web_search_with_time_filter(self):
        """Verify time-filtered web search works."""
        results = search_web("latest python news", num_results=5, since="week")

        assert len(results) > 0

        # Results should be recent (from past week)
        first = results[0]
        assert first.url.startswith("http")


@pytest.mark.contract
@requires_serper_key
class TestSerperNewsSearchContract:
    """Contract tests for Serper news search API."""

    def test_news_search_returns_results(self):
        """Verify news search returns valid results."""
        results = search_news("technology", num_results=5)

        assert len(results) > 0
        assert len(results) <= 5

        # Check news-specific fields
        first = results[0]
        assert isinstance(first, SearchResult)
        assert first.title
        assert first.url
        assert first.snippet
        # News results should have source
        # Note: source may be None for some results

    def test_news_search_with_time_filter(self):
        """Verify time-filtered news search works."""
        results = search_news("AI", num_results=5, since="day")

        assert len(results) > 0


@pytest.mark.contract
@requires_serper_key
class TestSerperResultFormatting:
    """Tests for result formatting (doesn't require API but uses real structure)."""

    def test_format_results_as_markdown(self):
        """Verify markdown formatting works with real-like results."""
        # Get real results to format
        results = search_web("python", num_results=3)

        markdown = format_results_as_markdown(results, "web")

        assert "## Web Search Results" in markdown
        assert "###" in markdown  # Has numbered results
        assert "URL:" in markdown
        assert len(markdown) > 100  # Has substantial content

    def test_format_empty_results(self):
        """Verify empty results are handled gracefully."""
        markdown = format_results_as_markdown([], "web")

        assert "No web results found" in markdown
