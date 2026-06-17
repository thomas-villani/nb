"""Note content, link resolution, backlinks and stream endpoints."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from nb.config import Config
from nb.core.notes import get_note, record_note_view
from nb.utils.hashing import normalize_path
from nb.web.server.deps import get_app_config
from nb.web.server.security import _safe_note_path
from nb.web.server.serializers import get_alias_for_path, serialize_frontmatter

router = APIRouter()


@router.get("/api/note")
def get_note_endpoint(
    path: str | None = None,
    config: Config = Depends(get_app_config),
):
    """Get a note's raw content + metadata."""
    if not path:
        return {"error": "Missing path"}

    # Validate path to prevent path traversal attacks
    note_full_path = _safe_note_path(config.notes_root, path)
    if not note_full_path:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    if not note_full_path.exists():
        return {"error": "Not found"}

    content = note_full_path.read_text(encoding="utf-8")
    note = get_note(note_full_path, config.notes_root)
    note_alias = get_alias_for_path(note_full_path)

    from nb.utils.markdown import parse_note_file

    try:
        frontmatter_dict, _ = parse_note_file(note_full_path)
        frontmatter_dict = serialize_frontmatter(frontmatter_dict)
    except Exception:
        frontmatter_dict = {}

    # Record the view for history tracking
    record_note_view(note_full_path, config.notes_root)

    return {
        "content": content,
        "title": note.title if note else note_full_path.stem,
        "path": path,
        "alias": note_alias,
        "frontmatter": frontmatter_dict,
        # Linked/external notes use absolute paths; they are read-only in the web
        # editor (the POST handler rejects absolute paths).
        "isLinked": Path(path).is_absolute(),
    }


@router.post("/api/note")
def save_note_endpoint(
    request: Request,
    body: dict = Body(...),
    config: Config = Depends(get_app_config),
):
    """Create or update a note."""
    note_path = body.get("path", "")
    content = body.get("content", "")
    is_create = body.get("create", False)

    if not note_path:
        return JSONResponse({"error": "Path required"}, status_code=400)

    # For write operations, only allow relative paths within notes_root
    # (don't allow writing to absolute paths or path traversal)
    if Path(note_path).is_absolute():
        return JSONResponse(
            {"error": "Cannot write to absolute paths"}, status_code=400
        )

    full_path = _safe_note_path(config.notes_root, note_path)
    if not full_path:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    if is_create and full_path.exists():
        return JSONResponse({"error": "File already exists"}, status_code=400)

    # Ensure parent directory exists
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")

    # Reindex the note in a separate thread (can be slow for large files).
    # Uses thread-safe version to avoid SQLite threading issues.
    def reindex_note() -> None:
        try:
            from nb.index.scanner import index_note_threadsafe

            index_note_threadsafe(full_path, config.notes_root, index_vectors=True)
        except Exception:
            pass  # Save succeeded, don't fail if indexing fails

    threading.Thread(target=reindex_note, daemon=True).start()

    return {"success": True, "path": note_path}


@router.get("/api/resolve-link")
def resolve_link(
    target: str | None = None,
    source: str | None = None,
    config: Config = Depends(get_app_config),
):
    """Resolve a wiki/markdown link target to a note path."""
    from nb.core.note_links import _find_similar_note, resolve_link_target

    if not target:
        return JSONResponse({"error": "Missing target"}, status_code=400)

    source_path = None
    if source:
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = config.notes_root / source_path

    resolved = resolve_link_target(
        target,
        source_path or config.notes_root,
        config.notes_root,
    )

    if resolved and resolved.exists():
        try:
            rel_path = resolved.relative_to(config.notes_root)
            return {"path": normalize_path(rel_path)}
        except ValueError:
            return {"path": normalize_path(resolved)}
    else:
        suggestion = _find_similar_note(target, config.notes_root)
        return {"path": None, "suggestion": suggestion}


@router.get("/api/backlinks")
def backlinks(
    path: str | None = None,
    config: Config = Depends(get_app_config),
):
    """Get backlinks for a note."""
    from nb.core.note_links import get_backlinks

    if not path:
        return JSONResponse({"error": "Missing path"}, status_code=400)

    backlinks_path = _safe_note_path(config.notes_root, path)
    if not backlinks_path or not backlinks_path.exists():
        return []

    found = get_backlinks(backlinks_path)
    return [
        {
            "source_path": normalize_path(b.source_path),
            "display_text": b.display_text,
            "link_type": b.link_type,
            "line_number": b.line_number,
        }
        for b in found
    ]


@router.get("/api/stream")
def stream(
    notebook: str | None = None,
    offset: int = 0,
    limit: int = 20,
    config: Config = Depends(get_app_config),
):
    """Get notes with full content for continuous reading (paginated).

    Pass ``notebook`` to stream a single notebook, or omit it (or pass the
    ``__all__`` sentinel) to stream every notebook's notes together.
    """
    from nb.index.db import get_db

    db = get_db()

    all_notebooks = not notebook or notebook == "__all__"
    if all_notebooks:
        where = "external = 0"
        where_params: tuple = ()
    else:
        where = "notebook = ? AND external = 0"
        where_params = (notebook,)

    note_rows = db.fetchall(
        f"""SELECT path, title, date, notebook, mtime
           FROM notes WHERE {where}
           ORDER BY COALESCE(date, '') DESC, mtime DESC
           LIMIT ? OFFSET ?""",
        (*where_params, limit, offset),
    )

    count_row = db.fetchone(
        f"SELECT COUNT(*) as total FROM notes WHERE {where}",
        where_params,
    )
    total = count_row["total"] if count_row else 0

    results = []
    for row in note_rows:
        note_path = Path(row["path"])
        full_path = config.notes_root / note_path

        try:
            content = full_path.read_text(encoding="utf-8")
            # Strip frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()
        except Exception:
            content = "[Error reading file]"

        results.append(
            {
                "path": normalize_path(note_path),
                "title": row["title"] or note_path.stem,
                "date": row["date"],
                "notebook": row["notebook"],
                "content": content,
            }
        )

    return {"notes": results, "total": total, "offset": offset}
