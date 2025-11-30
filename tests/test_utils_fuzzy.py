"""Tests for nb.utils.fuzzy module."""

from __future__ import annotations

from nb.utils.fuzzy import get_fuzzy_matches, resolve_with_fuzzy


class TestGetFuzzyMatches:
    """Tests for get_fuzzy_matches function."""

    def test_exact_match(self):
        """Exact matches should be returned."""
        candidates = ["daily", "projects", "ideas"]
        result = get_fuzzy_matches("daily", candidates)
        assert "daily" in result

    def test_close_match(self):
        """Close matches should be returned."""
        candidates = ["daily", "projects", "ideas"]
        result = get_fuzzy_matches("daly", candidates)  # typo
        assert "daily" in result

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        candidates = ["Daily", "Projects", "Ideas"]
        result = get_fuzzy_matches("daily", candidates)
        assert "Daily" in result

    def test_no_match(self):
        """No matches when nothing is close."""
        candidates = ["daily", "projects", "ideas"]
        result = get_fuzzy_matches("xxxxxxx", candidates)
        assert result == []

    def test_empty_query(self):
        """Empty query returns empty list."""
        candidates = ["daily", "projects", "ideas"]
        result = get_fuzzy_matches("", candidates)
        assert result == []

    def test_empty_candidates(self):
        """Empty candidates returns empty list."""
        result = get_fuzzy_matches("daily", [])
        assert result == []

    def test_limit_results(self):
        """Should limit number of results."""
        candidates = ["test1", "test2", "test3", "test4", "test5", "test6"]
        result = get_fuzzy_matches("test", candidates, n=3)
        assert len(result) <= 3

    def test_prefix_match(self):
        """Prefix matches should work."""
        candidates = ["nb-cli", "nb-core", "notebook"]
        result = get_fuzzy_matches("nb-cl", candidates)
        assert "nb-cli" in result

    def test_multiple_matches(self):
        """Multiple similar candidates should all be returned."""
        candidates = ["project-a", "project-b", "project-c", "other"]
        result = get_fuzzy_matches("project", candidates)
        # All project-* should match
        assert all("project" in r for r in result)


class TestResolveWithFuzzy:
    """Tests for resolve_with_fuzzy function."""

    def test_exact_match_returns_candidate(self):
        """Exact match returns the candidate without prompting."""
        candidates = ["daily", "projects", "ideas"]
        result = resolve_with_fuzzy("daily", candidates, interactive=False)
        assert result == "daily"

    def test_case_insensitive_exact_match(self):
        """Case-insensitive exact match."""
        candidates = ["Daily", "Projects", "Ideas"]
        result = resolve_with_fuzzy("daily", candidates, interactive=False)
        assert result == "Daily"

    def test_no_match_non_interactive(self):
        """No match in non-interactive mode returns None."""
        candidates = ["daily", "projects", "ideas"]
        result = resolve_with_fuzzy("xxxxxxx", candidates, interactive=False)
        assert result is None

    def test_close_match_non_interactive(self):
        """Close match in non-interactive mode with high cutoff."""
        candidates = ["daily", "projects", "ideas"]
        # "dail" is very close to "daily" (>0.8 similarity)
        result = resolve_with_fuzzy("dail", candidates, interactive=False)
        assert result == "daily"

    def test_empty_query(self):
        """Empty query returns None."""
        candidates = ["daily", "projects", "ideas"]
        result = resolve_with_fuzzy("", candidates, interactive=False)
        assert result is None

    def test_empty_candidates(self):
        """Empty candidates returns None."""
        result = resolve_with_fuzzy("daily", [], interactive=False)
        assert result is None
