"""Notebook listing, notebook notes, tree and startup endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from nb.config import Config
from nb.core.links import list_linked_notes, scan_linked_note_files
from nb.core.notebooks import get_notebook_notes_with_linked, list_notebooks
from nb.core.notes import get_note, get_sections_for_path
from nb.utils.hashing import normalize_path
from nb.web.server.deps import get_app_config, get_settings
from nb.web.server.serializers import get_alias_for_path, get_color_hex
from nb.web.server.settings import AppSettings

router = APIRouter()


@router.get("/api/startup")
def startup(settings: AppSettings = Depends(get_settings)) -> dict:
    """Startup info (scope, etc.) used by the frontend on first load."""
    return {"scopeNotebook": settings.scope_notebook}


@router.get("/api/notebooks")
def list_notebooks_endpoint(
    config: Config = Depends(get_app_config),
    settings: AppSettings = Depends(get_settings),
) -> list[dict]:
    """List all notebooks (regular + virtual linked) with stats."""
    from nb.index.db import get_db

    db = get_db()
    nbs: list[dict] = []

    # Get notebook stats from database
    notebook_stats: dict[str, dict] = {}
    # Get max mtime per notebook
    mtime_rows = db.fetchall(
        """SELECT notebook, MAX(mtime) as last_modified
           FROM notes WHERE notebook IS NOT NULL
           GROUP BY notebook"""
    )
    for row in mtime_rows:
        if row["notebook"]:
            notebook_stats[row["notebook"]] = {
                "last_modified": row["last_modified"],
                "last_viewed": None,
            }

    # Get max viewed_at per notebook
    view_rows = db.fetchall(
        """SELECT n.notebook, MAX(nv.viewed_at) as last_viewed
           FROM note_views nv
           JOIN notes n ON nv.note_path = n.path
           WHERE n.notebook IS NOT NULL
           GROUP BY n.notebook"""
    )
    for row in view_rows:
        if row["notebook"]:
            if row["notebook"] in notebook_stats:
                notebook_stats[row["notebook"]]["last_viewed"] = row["last_viewed"]
            else:
                notebook_stats[row["notebook"]] = {
                    "last_modified": None,
                    "last_viewed": row["last_viewed"],
                }

    # Regular notebooks
    for name in list_notebooks(config.notes_root):
        notes_with_linked = get_notebook_notes_with_linked(name, config.notes_root)
        nb_config = config.get_notebook(name)
        color = get_color_hex(nb_config.color) if nb_config else None
        stats = notebook_stats.get(name, {})
        nbs.append(
            {
                "name": name,
                "count": len(notes_with_linked),
                "color": color,
                "isLinked": False,
                "dateMode": nb_config.date_mode if nb_config else "none",
                "lastModified": stats.get("last_modified"),
                "lastViewed": stats.get("last_viewed"),
            }
        )

    # Virtual notebooks from linked notes
    linked_notes = list_linked_notes()
    seen_notebooks = {nb["name"] for nb in nbs}
    for linked in linked_notes:
        virtual_nb = linked.notebook
        if virtual_nb not in seen_notebooks:
            files = scan_linked_note_files(linked)
            stats = notebook_stats.get(virtual_nb, {})
            nbs.append(
                {
                    "name": virtual_nb,
                    "count": len(files),
                    "color": "#39c5cf",  # Cyan for linked notebooks
                    "isLinked": True,
                    "dateMode": "none",
                    "alias": linked.alias,
                    "lastModified": stats.get("last_modified"),
                    "lastViewed": stats.get("last_viewed"),
                }
            )
            seen_notebooks.add(virtual_nb)

    # When scoped to a single notebook, only return that one.
    if settings.scope_notebook:
        nbs = [nb for nb in nbs if nb["name"] == settings.scope_notebook]

    return nbs


@router.get("/api/tree")
def tree(
    config: Config = Depends(get_app_config),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    """Hierarchical notebook -> section -> note tree."""
    from nb.core.tree import build_note_tree

    tree_data = build_note_tree(config)
    # When scoped to a single notebook, only show that one in the tree.
    if settings.scope_notebook:
        tree_data["notebooks"] = [
            nb for nb in tree_data["notebooks"] if nb["name"] == settings.scope_notebook
        ]
    # Resolve notebook colors to hex (linked-only notebooks default to cyan,
    # matching /api/notebooks behavior).
    for nb in tree_data["notebooks"]:
        if nb.get("isLinked") and not nb.get("color"):
            nb["color"] = "#39c5cf"
        else:
            nb["color"] = get_color_hex(nb.get("color"))
    return tree_data


@router.get("/api/notebooks/{name}")
def notebook_notes(
    name: str,
    config: Config = Depends(get_app_config),
) -> list[dict]:
    """List notes in a notebook (regular or virtual linked) with metadata."""
    from nb.index.db import get_db

    result: list[dict] = []

    # Check if it's a virtual linked notebook
    is_virtual_linked = name.startswith("@")
    linked_config = None

    if is_virtual_linked:
        for linked in list_linked_notes():
            if linked.notebook == name:
                linked_config = linked
                break

    db = get_db()

    # Get lastViewed for all notes
    # Note: note_views stores paths with OS separators, notes table uses forward slashes
    view_rows = db.fetchall(
        """SELECT note_path, MAX(viewed_at) as last_viewed
           FROM note_views
           GROUP BY note_path""",
    )
    last_viewed_map = {
        normalize_path(row["note_path"]): row["last_viewed"] for row in view_rows
    }

    if linked_config:
        # List files from linked note - query database for indexed data
        note_rows = db.fetchall(
            """SELECT path, title, date, source_alias, mtime
               FROM notes WHERE notebook = ? AND external = 1
               ORDER BY COALESCE(date, '') DESC, mtime DESC""",
            (name,),
        )

        if note_rows:
            for row in note_rows:
                note_path = Path(row["path"])
                path_str = normalize_path(note_path)

                tag_rows = db.fetchall(
                    "SELECT tag FROM note_tags WHERE note_path = ?",
                    (row["path"],),
                )
                tags = [t["tag"] for t in tag_rows]

                note_alias = get_alias_for_path(note_path) or row["source_alias"]

                result.append(
                    {
                        "path": path_str,
                        "title": row["title"] or note_path.stem,
                        "filename": note_path.name,
                        "date": row["date"],
                        "mtime": row["mtime"],
                        "lastViewed": last_viewed_map.get(row["path"]),
                        "tags": tags,
                        "alias": note_alias,
                        "isLinked": True,
                        "sections": get_sections_for_path(note_path),
                    }
                )
        else:
            # Fall back to file-based scan
            files = scan_linked_note_files(linked_config)
            for file_path in sorted(files, reverse=True):
                note = get_note(file_path, config.notes_root)
                path_str = normalize_path(file_path)
                note_alias = get_alias_for_path(file_path)
                try:
                    file_mtime = file_path.stat().st_mtime
                except OSError:
                    file_mtime = None
                result.append(
                    {
                        "path": path_str,
                        "title": note.title if note else file_path.stem,
                        "filename": file_path.name,
                        "date": (
                            note.date.strftime("%Y-%m-%d")
                            if note and note.date
                            else None
                        ),
                        "mtime": file_mtime,
                        "lastViewed": last_viewed_map.get(path_str),
                        "tags": note.tags if note else [],
                        "alias": note_alias,
                        "isLinked": True,
                        "sections": get_sections_for_path(file_path),
                    }
                )
    else:
        # Regular notebook - query database for notes with metadata
        note_rows = db.fetchall(
            """SELECT path, title, date, external, source_alias, mtime
               FROM notes WHERE notebook = ?
               ORDER BY COALESCE(date, '') DESC, mtime DESC""",
            (name,),
        )

        if note_rows:
            for row in note_rows:
                note_path = Path(row["path"])
                is_external = bool(row["external"])

                if is_external or note_path.is_absolute():
                    full_path = (
                        note_path
                        if note_path.is_absolute()
                        else config.notes_root / note_path
                    )
                    path_str = normalize_path(full_path)
                else:
                    path_str = normalize_path(note_path)

                tag_rows = db.fetchall(
                    "SELECT tag FROM note_tags WHERE note_path = ?",
                    (row["path"],),
                )
                tags = [t["tag"] for t in tag_rows]

                check_path = (
                    note_path
                    if note_path.is_absolute()
                    else config.notes_root / note_path
                )
                note_alias = get_alias_for_path(check_path) or row["source_alias"]

                result.append(
                    {
                        "path": path_str,
                        "title": row["title"] or note_path.stem,
                        "filename": note_path.name,
                        "date": row["date"],
                        "mtime": row["mtime"],
                        "lastViewed": last_viewed_map.get(row["path"]),
                        "tags": tags,
                        "alias": note_alias,
                        "isLinked": is_external,
                        "sections": get_sections_for_path(note_path),
                    }
                )
        else:
            # Fall back to file-based scan (for un-indexed notes)
            notes_with_linked = get_notebook_notes_with_linked(name, config.notes_root)
            for note_path, is_linked, linked_alias in sorted(
                notes_with_linked, reverse=True
            ):
                if is_linked:
                    full_path = (
                        note_path
                        if note_path.is_absolute()
                        else config.notes_root / note_path
                    )
                    note = get_note(full_path, config.notes_root)
                    path_str = normalize_path(full_path)
                else:
                    full_path = config.notes_root / note_path
                    note = get_note(note_path, config.notes_root)
                    path_str = normalize_path(note_path)

                check_path = (
                    note_path
                    if note_path.is_absolute()
                    else config.notes_root / note_path
                )
                note_alias = get_alias_for_path(check_path) or linked_alias

                try:
                    file_mtime = full_path.stat().st_mtime
                except OSError:
                    file_mtime = None

                result.append(
                    {
                        "path": path_str,
                        "title": note.title if note else note_path.stem,
                        "filename": note_path.name,
                        "date": (
                            note.date.strftime("%Y-%m-%d")
                            if note and note.date
                            else None
                        ),
                        "mtime": file_mtime,
                        "lastViewed": last_viewed_map.get(normalize_path(note_path)),
                        "tags": note.tags if note else [],
                        "alias": note_alias,
                        "isLinked": is_linked,
                        "sections": get_sections_for_path(note_path),
                    }
                )

    return result
