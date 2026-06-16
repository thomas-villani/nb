"""Recently viewed / modified notes endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from nb.config import Config
from nb.utils.hashing import normalize_path
from nb.web.server.deps import get_app_config

router = APIRouter()


@router.get("/api/history")
def history(
    limit: int = 50,
    type: str = "viewed",
    config: Config = Depends(get_app_config),
) -> list[dict]:
    """Recently viewed or modified notes."""
    from nb.core.notes import (
        get_recently_modified_notes,
        get_recently_viewed_notes,
    )
    from nb.index.db import get_db

    db = get_db()
    result: list[dict] = []

    if type == "modified":
        notes = get_recently_modified_notes(limit=limit)
        for note_path, mtime in notes:
            try:
                path_str = normalize_path(note_path.relative_to(config.notes_root))
            except ValueError:
                path_str = normalize_path(note_path)

            mod_row = db.fetchone(
                "SELECT title, notebook FROM notes WHERE path = ?",
                (path_str,),
            )
            result.append(
                {
                    "path": path_str,
                    "title": mod_row["title"] if mod_row else note_path.stem,
                    "notebook": mod_row["notebook"] if mod_row else None,
                    "timestamp": mtime.isoformat(),
                    "type": "modified",
                }
            )
    else:
        views = get_recently_viewed_notes(limit=limit)
        for note_path, viewed_at in views:
            try:
                path_str = normalize_path(note_path.relative_to(config.notes_root))
            except ValueError:
                path_str = normalize_path(note_path)

            view_row = db.fetchone(
                "SELECT title, notebook FROM notes WHERE path = ?",
                (path_str,),
            )
            result.append(
                {
                    "path": path_str,
                    "title": view_row["title"] if view_row else note_path.stem,
                    "notebook": view_row["notebook"] if view_row else None,
                    "timestamp": viewed_at.isoformat(),
                    "type": "viewed",
                }
            )

    return result
