"""Search endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from nb.utils.hashing import normalize_path

router = APIRouter()


@router.get("/api/search")
def search(q: str = "", notebook: str | None = None):
    """Hybrid (semantic + keyword) search over notes."""
    if not q:
        return []

    # Lazy import so tests can patch nb.index.search.get_search.
    from nb.index.search import get_search

    filters: dict | None = {"notebook": notebook} if notebook else None
    results = get_search().search(q, k=20, filters=filters)
    return [
        {
            "path": normalize_path(r.path),
            "title": r.title,
            "snippet": r.snippet,
        }
        for r in results
    ]
