"""Web search functionality using Serper API.

Provides web, news, and scholar search capabilities for the research agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


class SearchAPIError(Exception):
    """Error from the search API."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str
    date: str | None = None
    source: str | None = None  # For news results
    publication_info: str | None = None  # For scholar results
    cited_by: int | None = None  # For scholar results


def _get_api_key() -> str:
    """Get the Serper API key from config or environment.

    The API key is loaded from:
    1. config.yaml (search.serper_api_key)
    2. SERPER_API_KEY environment variable
    3. .nb/.env file (loaded automatically by config)

    Raises:
        SearchAPIError: If no API key is configured.
    """
    from nb.config import get_config

    key = get_config().search.serper_api_key
    if not key:
        raise SearchAPIError(
            "Serper API key not configured. "
            "Set SERPER_API_KEY in .nb/.env or environment. "
            "Get an API key from https://serper.dev"
        )
    return key


def _serper_search(
    query: str,
    search_type: Literal["web", "news", "scholar", "patents"] = "web",
    num_results: int = 10,
    since: Literal["hour", "day", "week", "month", "year"] | None = None,
    page: int = 1,
) -> dict:
    """Perform a search using the Serper API.

    Args:
        query: The search query
        search_type: Type of search (web, news, scholar, patents)
        num_results: Number of results to return
        since: Filter results by time period (for web/news)
        page: Page number for pagination

    Returns:
        Raw search results from Serper API

    Raises:
        SearchAPIError: If the API request fails
    """
    api_key = _get_api_key()

    # Map search type to Serper endpoint
    endpoint = "search" if search_type == "web" else search_type
    url = f"https://google.serper.dev/{endpoint}"

    payload: dict = {"q": query}

    if num_results != 10:
        payload["num"] = num_results
    if since:
        payload["tbs"] = since[0]  # h, d, w, m, y
    if page != 1:
        payload["page"] = page

    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)

        if response.status_code == 429:
            raise SearchAPIError("Rate limit exceeded", 429)
        if response.status_code == 401:
            raise SearchAPIError("Invalid API key", 401)
        if response.status_code != 200:
            raise SearchAPIError(
                f"Search API error: {response.text}", response.status_code
            )

        return response.json()
    except httpx.HTTPError as e:
        raise SearchAPIError(f"HTTP error during search: {e}") from e


def search_web(
    query: str,
    num_results: int = 10,
    since: Literal["hour", "day", "week", "month", "year"] | None = None,
) -> list[SearchResult]:
    """Search the web for information.

    Args:
        query: The search query
        num_results: Number of results to return
        since: Filter results by time period

    Returns:
        List of search results
    """
    results = _serper_search(query, "web", num_results, since)

    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            date=item.get("date"),
        )
        for item in results.get("organic", [])
    ]


def search_news(
    query: str,
    num_results: int = 10,
    since: Literal["hour", "day", "week", "month", "year"] = "week",
) -> list[SearchResult]:
    """Search news articles.

    Args:
        query: The search query
        num_results: Number of results to return
        since: Filter results by time period (default: week)

    Returns:
        List of news results
    """
    results = _serper_search(query, "news", num_results, since)

    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            date=item.get("date"),
            source=item.get("source"),
        )
        for item in results.get("news", [])
    ]


def search_scholar(
    query: str,
    num_results: int = 10,
) -> list[SearchResult]:
    """Search academic papers via Google Scholar.

    Args:
        query: The search query
        num_results: Number of results to return

    Returns:
        List of scholar results
    """
    results = _serper_search(query, "scholar", num_results)

    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            date=item.get("year"),
            publication_info=item.get("publicationInfo"),
            cited_by=item.get("citedBy"),
        )
        for item in results.get("organic", [])
    ]


def search_patents(
    query: str,
    num_results: int = 10,
) -> list[SearchResult]:
    """Search patents via Google Patents.

    Args:
        query: The search query
        num_results: Number of results to return

    Returns:
        List of patent results
    """
    results = _serper_search(query, "patents", num_results)

    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            date=item.get("priorityDate") or item.get("filingDate"),
            publication_info=item.get("publicationNumber"),
        )
        for item in results.get("organic", [])
    ]


def format_results_as_markdown(
    results: list[SearchResult],
    search_type: str = "web",
) -> str:
    """Format search results as markdown for LLM consumption.

    Args:
        results: List of search results
        search_type: Type of search performed

    Returns:
        Markdown formatted string
    """
    if not results:
        return f"No {search_type} results found."

    lines = [f"## {search_type.title()} Search Results\n"]

    for i, result in enumerate(results, 1):
        lines.append(f"### {i}. {result.title}")
        lines.append(f"URL: {result.url}")

        if result.date:
            lines.append(f"Date: {result.date}")
        if result.source:
            lines.append(f"Source: {result.source}")
        if result.publication_info:
            lines.append(f"Publication: {result.publication_info}")
        if result.cited_by:
            lines.append(f"Cited by: {result.cited_by}")

        lines.append(f"\n{result.snippet}\n")

    return "\n".join(lines)
