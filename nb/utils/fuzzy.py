"""Fuzzy matching utilities for nb."""

from __future__ import annotations

import difflib


def get_fuzzy_matches(
    query: str,
    candidates: list[str],
    n: int = 5,
    cutoff: float = 0.6,
) -> list[str]:
    """Find candidates that fuzzy-match the query.

    Uses difflib.get_close_matches() to find similar strings.

    Args:
        query: The string to match against.
        candidates: List of candidate strings to search.
        n: Maximum number of matches to return (default 5).
        cutoff: Minimum similarity ratio (0.0-1.0, default 0.6).

    Returns:
        List of matching candidates, sorted by similarity.

    """
    if not query or not candidates:
        return []

    # get_close_matches is case-sensitive, so we do case-insensitive matching
    query_lower = query.lower()
    candidate_map = {c.lower(): c for c in candidates}

    matches = difflib.get_close_matches(
        query_lower,
        candidate_map.keys(),
        n=n,
        cutoff=cutoff,
    )

    # Return original-case versions
    return [candidate_map[m] for m in matches]


def prompt_fuzzy_selection(
    query: str,
    candidates: list[str],
    item_type: str = "item",
) -> str | None:
    """Interactively prompt user to select from fuzzy matches.

    Args:
        query: The original query that didn't match.
        candidates: List of all valid candidates.
        item_type: Type of item for display (e.g., "notebook", "note").

    Returns:
        Selected candidate string, or None if user cancels.

    """
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()

    matches = get_fuzzy_matches(query, candidates)

    if not matches:
        console.print(f"[red]No {item_type} found matching '{query}'[/red]")
        return None

    console.print(f"[yellow]No exact match for '{query}'. Did you mean:[/yellow]")

    for i, match in enumerate(matches, 1):
        console.print(f"  [cyan]{i}[/cyan]. {match}")

    console.print("  [dim]0[/dim]. Cancel")

    choice = Prompt.ask(
        "Select",
        choices=[str(i) for i in range(len(matches) + 1)],
        default="1",
    )

    if choice == "0":
        return None

    return matches[int(choice) - 1]


def resolve_with_fuzzy(
    query: str,
    candidates: list[str],
    item_type: str = "item",
    interactive: bool = True,
) -> str | None:
    """Resolve a query to a candidate, with fuzzy matching fallback.

    First tries exact match (case-insensitive), then falls back to
    fuzzy matching with optional interactive selection.

    Args:
        query: The string to resolve.
        candidates: List of valid candidates.
        item_type: Type of item for display messages.
        interactive: If True, prompt user to select from fuzzy matches.

    Returns:
        Resolved candidate string, or None if not found/cancelled.

    """
    if not query or not candidates:
        return None

    # Try exact match first (case-insensitive)
    query_lower = query.lower()
    for candidate in candidates:
        if candidate.lower() == query_lower:
            return candidate

    # Try fuzzy matching
    if interactive:
        return prompt_fuzzy_selection(query, candidates, item_type)
    else:
        # Non-interactive: return best match if confident enough
        matches = get_fuzzy_matches(query, candidates, n=1, cutoff=0.8)
        return matches[0] if matches else None
