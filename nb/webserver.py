"""Minimal web viewer for nb."""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nb.config import get_config
from nb.core.links import list_linked_notes, scan_linked_note_files
from nb.core.notebooks import get_notebook_notes_with_linked, list_notebooks
from nb.core.notes import get_note, get_sections_for_path
from nb.web import get_template


def get_alias_for_path(note_path: Path) -> str | None:
    """Get the alias for a given note path, if one exists.

    Uses get_db() to ensure schema is initialized and consistent with rest of app.
    """
    from nb.index.db import get_db

    config = get_config()
    try:
        db = get_db()
        rows = db.fetchall("SELECT alias, path FROM note_aliases")

        # Always resolve to absolute path for comparison
        # For relative paths, prepend notes_root before resolving
        if note_path.is_absolute():
            target = note_path.resolve()
        else:
            target = (config.notes_root / note_path).resolve()

        for row in rows:
            alias_path = Path(row["path"])
            if not alias_path.is_absolute():
                alias_path = config.notes_root / alias_path
            if alias_path.resolve() == target:
                return row["alias"]
    except Exception:
        # If database doesn't exist or table missing, just return None
        pass
    return None


# Color name to hex mapping for notebook colors
COLOR_MAP = {
    "blue": "#58a6ff",
    "green": "#3fb950",
    "cyan": "#39c5cf",
    "magenta": "#db61a2",
    "red": "#f85149",
    "yellow": "#d29922",
    "orange": "#db6d28",
    "purple": "#a371f7",
    "pink": "#ff7b72",
    "gray": "#7d8590",
    "grey": "#7d8590",
}


def get_color_hex(color: str | None) -> str | None:
    """Convert color name to hex, or return hex if already hex."""
    if not color:
        return None
    if color.startswith("#"):
        return color
    return COLOR_MAP.get(color.lower())


def _is_allowed_external_path(path: Path) -> bool:
    """Check if an absolute path belongs to a configured linked note or file.

    This prevents arbitrary file read by ensuring absolute paths are only
    allowed if they're part of a linked notes directory or linked todo file.

    Args:
        path: The absolute path to validate.

    Returns:
        True if the path belongs to a linked note/file, False otherwise.
    """
    from nb.core.links import list_linked_files, list_linked_notes

    resolved = path.resolve()

    # Check linked notes (files and directories)
    for linked_note in list_linked_notes():
        if not linked_note.path.exists():
            continue
        linked_resolved = linked_note.path.resolve()
        if linked_note.path.is_file():
            # Single file - must match exactly
            if resolved == linked_resolved:
                return True
        else:
            # Directory - check if path is inside it
            try:
                resolved.relative_to(linked_resolved)
                return True
            except ValueError:
                continue

    # Check linked todo files
    for linked_file in list_linked_files():
        if not linked_file.path.exists():
            continue
        if resolved == linked_file.path.resolve():
            return True

    return False


def _safe_note_path(notes_root: Path, rel: str) -> Path | None:
    """Validate and resolve a note path, ensuring it's an allowed location.

    For internal notes (relative paths), ensures the resolved path doesn't
    escape notes_root via path traversal (e.g., "../../etc/passwd").

    For linked/external notes (absolute paths), validates that the path
    belongs to a configured linked note or file to prevent arbitrary file read.

    Args:
        notes_root: The notes root directory.
        rel: The relative or absolute path string from the request.

    Returns:
        Resolved Path if valid, None if path traversal detected or
        absolute path is not an allowed linked location.
    """
    path = Path(rel)

    # Absolute paths must belong to a configured linked note/file
    if path.is_absolute():
        if _is_allowed_external_path(path):
            return path
        return None  # Reject absolute paths not in linked locations

    # For relative paths, resolve and check containment
    resolved = (notes_root / rel).resolve()
    try:
        resolved.relative_to(notes_root.resolve())
    except ValueError:
        # Path escapes notes_root - path traversal attempt
        return None
    return resolved


# Template is now loaded from nb/web/ package (static files)
# See nb/web/__init__.py for get_template()


class NBHandler(http.server.BaseHTTPRequestHandler):
    """Request handler for nb web viewer."""

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress default logging

    def send_json(self, data: object, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_html(self, html: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def read_body(self) -> dict:
        """Read JSON body from request."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        return json.loads(body) if body else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        config = get_config()

        # Serve main page
        if path == "/" or path == "/index.html":
            self.send_html(get_template())
            return

        # API: List notebooks
        if path == "/api/notebooks":
            from nb.index.db import get_db

            db = get_db()
            nbs = []

            # Get notebook stats from database
            notebook_stats = {}
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
                        notebook_stats[row["notebook"]]["last_viewed"] = row[
                            "last_viewed"
                        ]
                    else:
                        notebook_stats[row["notebook"]] = {
                            "last_modified": None,
                            "last_viewed": row["last_viewed"],
                        }

            # Regular notebooks
            for name in list_notebooks(config.notes_root):
                notes_with_linked = get_notebook_notes_with_linked(
                    name, config.notes_root
                )
                nb_config = config.get_notebook(name)
                color = get_color_hex(nb_config.color) if nb_config else None
                stats = notebook_stats.get(name, {})
                nbs.append(
                    {
                        "name": name,
                        "count": len(notes_with_linked),
                        "color": color,
                        "isLinked": False,
                        "lastModified": stats.get("last_modified"),
                        "lastViewed": stats.get("last_viewed"),
                    }
                )

            # Virtual notebooks from linked notes
            linked_notes = list_linked_notes()
            seen_notebooks = {nb["name"] for nb in nbs}
            for linked in linked_notes:
                virtual_nb = linked.notebook or f"@{linked.alias}"
                if virtual_nb not in seen_notebooks:
                    files = scan_linked_note_files(linked)
                    stats = notebook_stats.get(virtual_nb, {})
                    nbs.append(
                        {
                            "name": virtual_nb,
                            "count": len(files),
                            "color": "#39c5cf",  # Cyan for linked notebooks
                            "isLinked": True,
                            "alias": linked.alias,
                            "lastModified": stats.get("last_modified"),
                            "lastViewed": stats.get("last_viewed"),
                        }
                    )
                    seen_notebooks.add(virtual_nb)

            self.send_json(nbs)
            return

        # API: List notes in notebook
        if path.startswith("/api/notebooks/"):
            from urllib.parse import unquote

            notebook = unquote(path.split("/")[-1])
            result = []

            # Check if it's a virtual linked notebook
            is_virtual_linked = notebook.startswith("@")
            linked_config = None

            if is_virtual_linked:
                # Find the linked note config for this virtual notebook
                for linked in list_linked_notes():
                    virtual_nb = linked.notebook or f"@{linked.alias}"
                    if virtual_nb == notebook:
                        linked_config = linked
                        break

            if linked_config:
                # List files from linked note - query database for indexed data
                from nb.index.db import get_db

                db = get_db()

                # Query notes for this virtual notebook from the database
                note_rows = db.fetchall(
                    """SELECT path, title, date, source_alias, mtime
                       FROM notes WHERE notebook = ? AND external = 1
                       ORDER BY COALESCE(date, '') DESC, mtime DESC""",
                    (notebook,),
                )

                # Get lastViewed for all notes
                # Note: note_views stores paths with OS separators, notes table uses forward slashes
                from nb.utils.hashing import normalize_path

                view_rows = db.fetchall(
                    """SELECT note_path, MAX(viewed_at) as last_viewed
                       FROM note_views
                       GROUP BY note_path""",
                )
                # Normalize paths to forward slashes for lookup
                last_viewed_map = {
                    normalize_path(row["note_path"]): row["last_viewed"]
                    for row in view_rows
                }

                if note_rows:
                    for row in note_rows:
                        note_path = Path(row["path"])
                        path_str = str(note_path).replace("\\", "/")

                        # Get tags for this note from database
                        tag_rows = db.fetchall(
                            "SELECT tag FROM note_tags WHERE note_path = ?",
                            (row["path"],),
                        )
                        tags = [t["tag"] for t in tag_rows]

                        note_alias = (
                            get_alias_for_path(note_path) or row["source_alias"]
                        )

                        result.append(
                            {
                                "path": path_str,
                                "title": row["title"] or note_path.stem,
                                "filename": note_path.name,
                                "date": row["date"],  # Already in YYYY-MM-DD format
                                "mtime": row["mtime"],  # Unix timestamp
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
                        path_str = str(file_path).replace("\\", "/")
                        note_alias = get_alias_for_path(file_path)
                        # Get mtime from file stat
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
                from nb.index.db import get_db

                db = get_db()

                # Query notes with their dates from the database
                note_rows = db.fetchall(
                    """SELECT path, title, date, external, source_alias, mtime
                       FROM notes WHERE notebook = ?
                       ORDER BY COALESCE(date, '') DESC, mtime DESC""",
                    (notebook,),
                )

                # Get lastViewed for all notes in this notebook
                # Note: note_views stores paths with OS separators, notes table uses forward slashes
                from nb.utils.hashing import normalize_path

                view_rows = db.fetchall(
                    """SELECT note_path, MAX(viewed_at) as last_viewed
                       FROM note_views
                       GROUP BY note_path""",
                )
                # Normalize paths to forward slashes for lookup
                last_viewed_map = {
                    normalize_path(row["note_path"]): row["last_viewed"]
                    for row in view_rows
                }

                if note_rows:
                    # Use database results (faster, includes indexed dates)
                    for row in note_rows:
                        note_path = Path(row["path"])
                        is_external = bool(row["external"])

                        if is_external or note_path.is_absolute():
                            # Linked/external note - use absolute path
                            full_path = (
                                note_path
                                if note_path.is_absolute()
                                else config.notes_root / note_path
                            )
                            path_str = str(full_path).replace("\\", "/")
                        else:
                            path_str = str(note_path).replace("\\", "/")

                        # Get tags for this note from database
                        tag_rows = db.fetchall(
                            "SELECT tag FROM note_tags WHERE note_path = ?",
                            (row["path"],),
                        )
                        tags = [t["tag"] for t in tag_rows]

                        # Get alias
                        check_path = (
                            note_path
                            if note_path.is_absolute()
                            else config.notes_root / note_path
                        )
                        note_alias = (
                            get_alias_for_path(check_path) or row["source_alias"]
                        )

                        result.append(
                            {
                                "path": path_str,
                                "title": row["title"] or note_path.stem,
                                "filename": note_path.name,
                                "date": row["date"],  # Already in YYYY-MM-DD format
                                "mtime": row["mtime"],  # Unix timestamp
                                "lastViewed": last_viewed_map.get(row["path"]),
                                "tags": tags,
                                "alias": note_alias,
                                "isLinked": is_external,
                                "sections": get_sections_for_path(note_path),
                            }
                        )
                else:
                    # Fall back to file-based scan (for un-indexed notes)
                    notes_with_linked = get_notebook_notes_with_linked(
                        notebook, config.notes_root
                    )
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
                            path_str = str(full_path).replace("\\", "/")
                        else:
                            full_path = config.notes_root / note_path
                            note = get_note(note_path, config.notes_root)
                            path_str = str(note_path).replace("\\", "/")

                        check_path = (
                            note_path
                            if note_path.is_absolute()
                            else config.notes_root / note_path
                        )
                        note_alias = get_alias_for_path(check_path) or linked_alias

                        # Get mtime from file stat
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
                                "lastViewed": last_viewed_map.get(
                                    str(note_path).replace("\\", "/")
                                ),
                                "tags": note.tags if note else [],
                                "alias": note_alias,
                                "isLinked": is_linked,
                                "sections": get_sections_for_path(note_path),
                            }
                        )

            self.send_json(result)
            return

        # API: Get note content
        if path == "/api/note":
            note_path_str = query.get("path", [None])[0]
            if not note_path_str:
                self.send_json({"error": "Missing path"})
                return

            # Validate path to prevent path traversal attacks
            note_full_path = _safe_note_path(config.notes_root, note_path_str)
            if not note_full_path:
                self.send_json({"error": "Invalid path"}, 400)
                return

            if not note_full_path.exists():
                self.send_json({"error": "Not found"})
                return

            content = note_full_path.read_text(encoding="utf-8")
            note = get_note(note_full_path, config.notes_root)
            note_alias = get_alias_for_path(note_full_path)

            # Parse frontmatter for display
            from datetime import date, datetime

            from nb.utils.markdown import parse_note_file

            def serialize_frontmatter(fm: dict) -> dict:
                """Convert frontmatter values to JSON-serializable types."""
                result: dict = {}
                for key, val in fm.items():
                    if isinstance(val, (date, datetime)):
                        result[key] = val.isoformat()
                    elif isinstance(val, list):
                        result[key] = [
                            v.isoformat() if isinstance(v, (date, datetime)) else v
                            for v in val
                        ]
                    else:
                        result[key] = val
                return result

            try:
                frontmatter_dict, _ = parse_note_file(note_full_path)
                frontmatter_dict = serialize_frontmatter(frontmatter_dict)
            except Exception:
                frontmatter_dict = {}

            # Record the view for history tracking
            from nb.core.notes import record_note_view

            record_note_view(note_full_path, config.notes_root)

            self.send_json(
                {
                    "content": content,
                    "title": note.title if note else note_full_path.stem,
                    "path": note_path_str,
                    "alias": note_alias,
                    "frontmatter": frontmatter_dict,
                }
            )
            return

        # API: Resolve link target to note path
        if path == "/api/resolve-link":
            from nb.core.note_links import _find_similar_note, resolve_link_target

            target = query.get("target", [None])[0]
            source = query.get("source", [None])[0]

            if not target:
                self.send_json({"error": "Missing target"}, 400)
                return

            # Determine source path for relative link resolution
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
                # Return the path relative to notes_root or absolute for external
                try:
                    rel_path = resolved.relative_to(config.notes_root)
                    self.send_json({"path": str(rel_path).replace("\\", "/")})
                except ValueError:
                    # External path - return absolute
                    self.send_json({"path": str(resolved).replace("\\", "/")})
            else:
                # Not found - try to suggest a similar note
                suggestion = _find_similar_note(target, config.notes_root)
                self.send_json({"path": None, "suggestion": suggestion})
            return

        # API: Get graph data for visualization
        if path == "/api/graph":
            from nb.index.db import get_db

            db = get_db()

            nodes = []
            edges = []
            node_ids = set()

            # Get all notes as nodes
            note_rows = db.fetchall(
                "SELECT path, title, notebook FROM notes WHERE external = 0"
            )

            for row in note_rows:
                path_str = row["path"].replace("\\", "/")
                node_ids.add(path_str)
                nodes.append(
                    {
                        "id": path_str,
                        "title": row["title"] or Path(row["path"]).stem,
                        "type": "note",
                        "notebook": row["notebook"],
                    }
                )

            # Get all notebooks as nodes
            notebook_rows = db.fetchall(
                "SELECT DISTINCT notebook FROM notes WHERE external = 0 AND notebook IS NOT NULL"
            )
            notebook_ids = set()
            nb_config_map = {}
            for row in notebook_rows:
                nb_name = row["notebook"]
                if nb_name and nb_name not in notebook_ids:
                    notebook_ids.add(nb_name)
                    nb_id = f"notebook:{nb_name}"
                    nb_conf = config.get_notebook(nb_name)
                    color = get_color_hex(nb_conf.color) if nb_conf else None
                    nb_config_map[nb_name] = color
                    nodes.append(
                        {
                            "id": nb_id,
                            "title": nb_name,
                            "type": "notebook",
                            "color": color,
                        }
                    )

            # Get all tags as nodes
            tag_rows = db.fetchall("SELECT DISTINCT tag FROM note_tags")
            tag_ids = set()
            for row in tag_rows:
                tag = row["tag"]
                if tag and tag not in tag_ids:
                    tag_ids.add(tag)
                    nodes.append(
                        {
                            "id": f"tag:{tag}",
                            "title": f"#{tag}",
                            "type": "tag",
                        }
                    )

            # Add note → notebook edges
            for row in note_rows:
                path_str = row["path"].replace("\\", "/")
                nb_name = row["notebook"]
                if nb_name:
                    edges.append(
                        {
                            "source": path_str,
                            "target": f"notebook:{nb_name}",
                            "type": "notebook",
                        }
                    )

            # Add note → tag edges
            note_tag_rows = db.fetchall("SELECT note_path, tag FROM note_tags")
            for row in note_tag_rows:
                path_str = row["note_path"].replace("\\", "/")
                if path_str in node_ids:
                    edges.append(
                        {
                            "source": path_str,
                            "target": f"tag:{row['tag']}",
                            "type": "tag",
                        }
                    )

            # Add note → note edges (from links)
            link_rows = db.fetchall(
                """SELECT source_path, target_path FROM note_links
                   WHERE is_external = 0"""
            )

            for row in link_rows:
                source = row["source_path"].replace("\\", "/")
                target = row["target_path"].replace("\\", "/")

                # Resolve target to actual path if it's a partial reference
                if target not in node_ids:
                    # Try to find matching node
                    target_stem = Path(target).stem
                    for node_id in node_ids:
                        if Path(node_id).stem == target_stem:
                            target = node_id
                            break

                if source in node_ids and target in node_ids:
                    edges.append(
                        {
                            "source": source,
                            "target": target,
                            "type": "link",
                        }
                    )

            self.send_json({"nodes": nodes, "edges": edges})
            return

        # API: Get backlinks for a note
        if path == "/api/backlinks":
            from nb.core.note_links import get_backlinks

            note_path_str = query.get("path", [None])[0]
            if not note_path_str:
                self.send_json({"error": "Missing path"}, 400)
                return

            # Resolve to full path
            backlinks_path = _safe_note_path(config.notes_root, note_path_str)
            if not backlinks_path or not backlinks_path.exists():
                self.send_json([])
                return

            backlinks = get_backlinks(backlinks_path)
            self.send_json(
                [
                    {
                        "source_path": str(b.source_path).replace("\\", "/"),
                        "display_text": b.display_text,
                        "link_type": b.link_type,
                        "line_number": b.line_number,
                    }
                    for b in backlinks
                ]
            )
            return

        # API: Search
        if path == "/api/search":
            q = query.get("q", [""])[0]
            notebook_param = query.get("notebook", [None])[0]
            if q:
                from nb.index.search import get_search

                # Apply notebook filter if specified
                filters: dict | None = (
                    {"notebook": notebook_param} if notebook_param else None
                )
                results = get_search().search(q, k=20, filters=filters)
                self.send_json(
                    [
                        {
                            "path": r.path.replace("\\", "/"),
                            "title": r.title,
                            "snippet": r.snippet,
                        }
                        for r in results
                    ]
                )
            else:
                self.send_json([])
            return

        # API: Todos
        if path == "/api/todos":
            from datetime import date as date_type

            from nb.index.todos_repo import get_sorted_todos

            # Use the module-level flag for showing completed
            todos = get_sorted_todos(completed=None if _show_completed else False)
            today = date_type.today()

            self.send_json(
                [
                    {
                        "id": t.id,
                        "content": t.content,
                        "due": t.due_date.isoformat() if t.due_date else None,
                        "priority": t.priority.value if t.priority else None,
                        "status": t.status.value,
                        "notebook": t.notebook or "unknown",
                        "tags": t.tags or [],
                        "created": (
                            t.created_date.isoformat() if t.created_date else None
                        ),
                        # Use due_date_only for date comparisons (due_date may be datetime)
                        "isOverdue": t.due_date_only is not None
                        and t.due_date_only < today
                        and t.status.value != "completed",
                        "isDueToday": t.due_date_only == today,
                        "isDueThisWeek": t.due_date_only is not None
                        and today
                        < t.due_date_only
                        <= today + __import__("datetime").timedelta(days=7),
                    }
                    for t in todos[:100]
                ]
            )
            return

        # API: Kanban - get board configurations
        if path == "/api/kanban/boards":
            from nb.config import DEFAULT_KANBAN_COLUMNS

            boards = []
            for b in config.kanban_boards:
                boards.append(
                    {
                        "name": b.name,
                        "columns": [
                            {"name": c.name, "filters": c.filters, "color": c.color}
                            for c in b.columns
                        ],
                    }
                )

            # Add default board if none configured
            if not boards:
                boards.append(
                    {
                        "name": "default",
                        "columns": [
                            {"name": c.name, "filters": c.filters, "color": c.color}
                            for c in DEFAULT_KANBAN_COLUMNS
                        ],
                    }
                )

            self.send_json(boards)
            return

        # API: Kanban - get todos for a column
        if path == "/api/kanban/column":
            import json
            from datetime import date as date_type
            from datetime import timedelta

            from nb.index.todos_repo import query_todos
            from nb.models import TodoStatus

            filters_json = query.get("filters", ["{}"])[0]
            notebook_filter = query.get("notebook", [None])[0]

            try:
                filters = json.loads(filters_json)
            except json.JSONDecodeError:
                filters = {}

            today = date_type.today()

            # Map filter keys to query_todos parameters
            kwargs: dict = {
                "parent_only": True,
                "exclude_note_excluded": True,
            }

            if notebook_filter:
                kwargs["notebooks"] = [notebook_filter]

            # Handle status filter
            status_val = filters.get("status")
            if status_val:
                kwargs["status"] = TodoStatus(status_val)
            else:
                kwargs["completed"] = False

            # Handle due date filters
            if filters.get("due_today"):
                kwargs["due_start"] = today
                kwargs["due_end"] = today

            if filters.get("due_this_week"):
                kwargs["due_start"] = today
                kwargs["due_end"] = today + timedelta(days=7)

            if filters.get("overdue"):
                kwargs["overdue"] = True

            if filters.get("priority"):
                kwargs["priority"] = filters["priority"]

            if filters.get("tags") and len(filters["tags"]) > 0:
                kwargs["tag"] = filters["tags"][0]

            todos = query_todos(**kwargs)

            # Post-filter for no_due_date
            if filters.get("no_due_date"):
                todos = [t for t in todos if t.due_date is None]

            self.send_json(
                [
                    {
                        "id": t.id,
                        "content": t.content,
                        "status": t.status.value,
                        "due": t.due_date.isoformat() if t.due_date else None,
                        "priority": t.priority.value if t.priority else None,
                        "notebook": t.notebook,
                        "tags": t.tags,
                    }
                    for t in todos[:50]
                ]
            )
            return

        # API: History - recently viewed and modified notes
        if path == "/api/history":
            from nb.core.notes import (
                get_recently_modified_notes,
                get_recently_viewed_notes,
            )

            limit = int(query.get("limit", [50])[0])
            history_type = query.get("type", ["viewed"])[0]  # 'viewed' or 'modified'

            result = []

            if history_type == "modified":
                # Get recently modified notes
                notes = get_recently_modified_notes(limit=limit)
                for note_path, mtime in notes:
                    try:
                        rel_path = note_path.relative_to(config.notes_root)
                        path_str = str(rel_path).replace("\\", "/")
                    except ValueError:
                        # External path
                        path_str = str(note_path).replace("\\", "/")

                    # Get note metadata from database
                    from nb.index.db import get_db

                    db = get_db()
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
                # Get recently viewed notes
                views = get_recently_viewed_notes(limit=limit)
                for note_path, viewed_at in views:
                    try:
                        rel_path = note_path.relative_to(config.notes_root)
                        path_str = str(rel_path).replace("\\", "/")
                    except ValueError:
                        # External path
                        path_str = str(note_path).replace("\\", "/")

                    # Get note metadata from database
                    from nb.index.db import get_db

                    db = get_db()
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

            self.send_json(result)
            return

        # 404
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        config = get_config()

        # API: Toggle todo completion
        if path.startswith("/api/todos/") and path.endswith("/toggle"):
            todo_id = path.split("/")[-2]

            from nb.core.todos import toggle_todo_in_file
            from nb.index.todos_repo import get_todo_by_id, update_todo_status

            todo = get_todo_by_id(todo_id)
            if not todo:
                self.send_json({"error": "Todo not found"}, 404)
                return

            # Get absolute path for the todo's source file
            source_path = todo.source.path
            if not source_path.is_absolute():
                source_path = config.notes_root / source_path

            try:
                actual_line = toggle_todo_in_file(
                    source_path, todo.line_number, expected_content=todo.content
                )
                if actual_line is None:
                    self.send_json(
                        {"error": "Todo not found at expected location"}, 404
                    )
                    return
                # Update the database
                from nb.models import TodoStatus

                new_status = (
                    TodoStatus.COMPLETED if not todo.completed else TodoStatus.PENDING
                )
                update_todo_status(todo_id, new_status)
                self.send_json({"success": True})
            except PermissionError as e:
                self.send_json({"error": str(e)}, 403)
            return

        # API: Set todo status directly (for kanban drag-and-drop)
        if path.startswith("/api/todos/") and path.endswith("/status"):
            todo_id = path.split("/")[-2]
            body = self.read_body()
            new_status_str = body.get("status")  # "pending", "in_progress", "completed"

            if not new_status_str:
                self.send_json({"error": "Status required"}, 400)
                return

            from nb.core.todos import set_todo_status_in_file
            from nb.index.todos_repo import get_todo_by_id, update_todo_status
            from nb.models import TodoStatus

            try:
                new_status = TodoStatus(new_status_str)
            except ValueError:
                self.send_json({"error": f"Invalid status: {new_status_str}"}, 400)
                return

            todo = get_todo_by_id(todo_id)
            if not todo:
                self.send_json({"error": "Todo not found"}, 404)
                return

            # Get absolute path for the todo's source file
            source_path = todo.source.path
            if not source_path.is_absolute():
                source_path = config.notes_root / source_path

            try:
                actual_line = set_todo_status_in_file(
                    source_path,
                    todo.line_number,
                    new_status,
                    expected_content=todo.content,
                )
                if actual_line is None:
                    self.send_json(
                        {"error": "Todo not found at expected location"}, 404
                    )
                    return
                # Update the database
                update_todo_status(todo_id, new_status)
                self.send_json({"success": True, "status": new_status.value})
            except PermissionError as e:
                self.send_json({"error": str(e)}, 403)
            return

        # API: Update todo due date
        if path.startswith("/api/todos/") and path.endswith("/due"):
            todo_id = path.split("/")[-2]
            body = self.read_body()
            new_date_str = body.get("due")  # ISO date string or null/empty

            from nb.core.todos import remove_todo_due_date, update_todo_due_date
            from nb.index.todos_repo import get_todo_by_id, update_todo_due_date_db

            todo = get_todo_by_id(todo_id)
            if not todo:
                self.send_json({"error": "Todo not found"}, 404)
                return

            # Get absolute path for the todo's source file
            source_path = todo.source.path
            if not source_path.is_absolute():
                source_path = config.notes_root / source_path

            try:
                if new_date_str:
                    # Parse the date string (ISO format: YYYY-MM-DD)
                    from datetime import date as date_type

                    new_date = date_type.fromisoformat(new_date_str)
                    actual_line = update_todo_due_date(
                        source_path,
                        todo.line_number,
                        new_date,
                        expected_content=todo.content,
                    )
                    if actual_line is None:
                        self.send_json(
                            {"error": "Todo not found at expected location"}, 404
                        )
                        return
                    # Update the database
                    update_todo_due_date_db(todo_id, new_date)
                else:
                    # Remove due date
                    actual_line = remove_todo_due_date(
                        source_path,
                        todo.line_number,
                        expected_content=todo.content,
                    )
                    if actual_line is None:
                        self.send_json(
                            {"error": "Todo not found at expected location"}, 404
                        )
                        return
                    # Update the database
                    update_todo_due_date_db(todo_id, None)

                self.send_json({"success": True})
            except PermissionError as e:
                self.send_json({"error": str(e)}, 403)
            except ValueError as e:
                self.send_json({"error": f"Invalid date: {e}"}, 400)
            return

        # API: Create todo
        if path == "/api/todos":
            body = self.read_body()
            content = body.get("content", "").strip()
            if not content:
                self.send_json({"error": "Content required"}, 400)
                return

            from nb.core.todos import add_todo_to_inbox

            add_todo_to_inbox(content)
            self.send_json({"success": True})
            return

        # API: Create/update note
        if path == "/api/note":
            body = self.read_body()
            note_path = body.get("path", "")
            content = body.get("content", "")
            is_create = body.get("create", False)

            if not note_path:
                self.send_json({"error": "Path required"}, 400)
                return

            # For write operations, only allow relative paths within notes_root
            # (don't allow writing to absolute paths or path traversal)
            if Path(note_path).is_absolute():
                self.send_json({"error": "Cannot write to absolute paths"}, 400)
                return

            full_path = _safe_note_path(config.notes_root, note_path)
            if not full_path:
                self.send_json({"error": "Invalid path"}, 400)
                return

            if is_create and full_path.exists():
                self.send_json({"error": "File already exists"}, 400)
                return

            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

            # Reindex the note in a separate thread (can be slow for large files)
            # Uses thread-safe version to avoid SQLite threading issues
            import threading

            def reindex_note():
                try:
                    from nb.index.scanner import index_note_threadsafe

                    index_note_threadsafe(
                        full_path, config.notes_root, index_vectors=True
                    )
                except Exception:
                    pass  # Save succeeded, don't fail if indexing fails

            threading.Thread(target=reindex_note, daemon=True).start()

            self.send_json({"success": True, "path": note_path})
            return

        # 404
        self.send_response(404)
        self.end_headers()


def run_server(
    port: int = 3000, open_browser: bool = True, show_completed: bool = False
) -> None:
    """Start the web server."""
    # Store show_completed in a module-level variable for the handler
    global _show_completed
    _show_completed = show_completed

    # Use regular TCPServer (not threaded) to avoid SQLite threading issues
    class Server(socketserver.TCPServer):
        allow_reuse_address = True

    httpd = Server(("127.0.0.1", port), NBHandler)

    if open_browser:

        def open_delayed() -> None:
            import time

            time.sleep(0.3)
            webbrowser.open(f"http://localhost:{port}")

        threading.Thread(target=open_delayed, daemon=True).start()

    try:
        # poll_interval=0.5 allows Ctrl+C to be detected on Windows
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping...")
        httpd.server_close()
        print("Stopped")


# Module-level flag for completed todos
_show_completed = False
