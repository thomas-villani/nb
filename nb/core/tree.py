"""Build a hierarchical notebook -> section -> note tree from the index.

The tree mirrors the on-disk structure of notebooks and their subfolders
("sections"), including externally linked notes. It is built entirely from the
indexed ``notes`` table with a single query, so files that are not indexed
(e.g. ``.venv`` / ``.obsidian`` junk inside a notebook directory) never appear.

The output is consumed by the ``GET /api/tree`` web endpoint to render the
file-tree sidebar. See ``nb.webserver``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nb.config import Config, get_config
from nb.core.links import list_linked_notes
from nb.utils.hashing import normalize_path

# Synthetic notebook holding notes that live directly in notes_root (no notebook).
ROOT_NOTEBOOK = "(root)"


def _external_sections(
    abspath: Path,
    notebook: str,
    linked_roots: list[tuple[Path, str, str | None]],
) -> tuple[list[str], str]:
    """Derive (sections, filename) for an external/linked note.

    External notes store an absolute path and an unreliable ``note_sections``
    entry, so we recover the section hierarchy by locating the note relative to
    its linked root directory rather than splitting the absolute path.
    """
    try:
        resolved = abspath.resolve()
    except OSError:
        resolved = abspath

    for root, nb_name, configured_section in linked_roots:
        if nb_name != notebook:
            continue
        try:
            rel = resolved.relative_to(root)
        except ValueError:
            continue
        section_segs = list(rel.parts[:-1])
        if configured_section:
            section_segs = [configured_section, *section_segs]
        return section_segs, abspath.name

    # No matching root (e.g. single-file link): fall back to configured section.
    for _root, nb_name, configured_section in linked_roots:
        if nb_name == notebook and configured_section:
            return [configured_section], abspath.name
    return [], abspath.name


def _finalize_children(node: dict) -> list[dict]:
    """Convert an internal {folders, notes} node into a sorted children list.

    Folders are sorted alphabetically (case-insensitive) and placed before
    notes; notes keep their insertion order (date desc, mtime desc from SQL).
    """
    folders: list[dict] = []
    for seg in sorted(node["folders"].keys(), key=str.lower):
        folder = node["folders"][seg]
        child_list = _finalize_children(folder)
        folders.append(
            {
                "type": "folder",
                "name": folder["name"],
                "path": folder["path"],
                "count": _count_notes(child_list),
                "children": child_list,
            }
        )
    return folders + node["notes"]


def _count_notes(children: list[dict]) -> int:
    """Count note leaves recursively within a children list."""
    total = 0
    for child in children:
        if child["type"] == "note":
            total += 1
        else:
            total += child.get("count", 0)
    return total


def build_note_tree(config: Config | None = None, db: Any = None) -> dict:
    """Build the nested notebook -> section -> note tree.

    Returns a dict of the shape ``{"notebooks": [NotebookNode, ...]}`` where each
    notebook contains a nested list of folder and note children. See module docs
    and the ``/api/tree`` handler for the exact JSON shape.

    Notebook colors are returned as their raw config values (name or hex); the
    web layer resolves them to hex.
    """
    if config is None:
        config = get_config()
    if db is None:
        from nb.index.db import get_db

        db = get_db()

    rows = db.fetchall(
        """SELECT path, title, date, mtime, notebook, external, source_alias
           FROM notes
           ORDER BY notebook, COALESCE(date, '') DESC, mtime DESC"""
    )

    linked_notes = list_linked_notes()
    linked_roots: list[tuple[Path, str, str | None]] = []
    for ln in linked_notes:
        try:
            root = ln.path.resolve()
        except OSError:
            root = ln.path
        linked_roots.append((root, ln.notebook, ln.section))

    # Group note rows by notebook.
    grouped: dict[str, list] = {}
    present: list[str] = []
    for row in rows:
        nb_name = row["notebook"] or ROOT_NOTEBOOK
        if nb_name not in grouped:
            grouped[nb_name] = []
            present.append(nb_name)
        grouped[nb_name].append(row)

    # Notebook ordering: config order, then linked-only virtual notebooks,
    # then any other notebook present in the index (alpha), then (root) last.
    configured = [nb.name for nb in config.notebooks]
    configured_set = set(configured)
    linked_only = [
        ln.notebook for ln in linked_notes if ln.notebook not in configured_set
    ]

    final_order: list[str] = []
    seen: set[str] = set()
    for name in [*configured, *linked_only]:
        if name not in seen:
            final_order.append(name)
            seen.add(name)
    for name in sorted(n for n in present if n not in seen and n != ROOT_NOTEBOOK):
        final_order.append(name)
        seen.add(name)
    if ROOT_NOTEBOOK in present:
        final_order.append(ROOT_NOTEBOOK)

    linked_only_set = set(linked_only)
    notebooks_out: list[dict] = []
    for nb_name in final_order:
        nb_rows = grouped.get(nb_name, [])
        nb_config = config.get_notebook(nb_name)
        is_root = nb_name == ROOT_NOTEBOOK
        is_linked_only = nb_config is None and nb_name in linked_only_set

        root_node: dict = {"folders": {}, "notes": []}
        for row in nb_rows:
            external = bool(row["external"])
            if external:
                abspath = Path(row["path"])
                sections, filename = _external_sections(
                    abspath, row["notebook"] or "", linked_roots
                )
                note_path = normalize_path(abspath)
            elif is_root:
                sections = []
                filename = Path(row["path"]).name
                note_path = row["path"]
            else:
                segs = row["path"].split("/")
                sections = segs[1:-1]
                filename = segs[-1]
                note_path = row["path"]

            note_node = {
                "type": "note",
                "name": filename,
                "title": row["title"] or Path(filename).stem,
                "path": note_path,
                "date": row["date"],
                "mtime": row["mtime"],
                "isLinked": external,
                "alias": row["source_alias"],
            }

            cursor = root_node
            cumulative = "" if is_root else nb_name
            for seg in sections:
                cumulative = f"{cumulative}/{seg}" if cumulative else seg
                folder = cursor["folders"].get(seg)
                if folder is None:
                    folder = {
                        "type": "folder",
                        "name": seg,
                        "path": cumulative,
                        "folders": {},
                        "notes": [],
                    }
                    cursor["folders"][seg] = folder
                cursor = folder
            cursor["notes"].append(note_node)

        children = _finalize_children(root_node)
        notebooks_out.append(
            {
                "name": nb_name,
                "type": "notebook",
                "color": nb_config.color if nb_config else None,
                "icon": nb_config.icon if nb_config else None,
                "isLinked": is_linked_only,
                "isExternal": bool(nb_config.is_external) if nb_config else False,
                "dateMode": nb_config.date_mode if nb_config else "none",
                "count": _count_notes(children),
                "children": children,
            }
        )

    return {"notebooks": notebooks_out}
