"""Knowledge-graph data endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query

from nb.config import Config
from nb.utils.hashing import normalize_path
from nb.web.server.deps import get_app_config
from nb.web.server.serializers import get_color_hex

router = APIRouter()


@router.get("/api/graph")
def graph(
    notebook: list[str] | None = Query(None),
    config: Config = Depends(get_app_config),
) -> dict:
    """Nodes (notes, notebooks, tags) and edges for the D3 graph.

    Loading every notebook at once is expensive for large vaults, so the graph
    can be scoped to one or more notebooks (repeat the ``notebook`` query param);
    only those notebooks' notes, their tags, and the links between them are
    returned. Omit ``notebook`` to include the whole vault.
    """
    from nb.index.db import get_db

    db = get_db()

    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    # Get notes as nodes (optionally scoped to one or more notebooks)
    if notebook:
        placeholders = ", ".join("?" for _ in notebook)
        note_rows = db.fetchall(
            f"SELECT path, title, notebook FROM notes "
            f"WHERE external = 0 AND notebook IN ({placeholders})",
            tuple(notebook),
        )
    else:
        note_rows = db.fetchall(
            "SELECT path, title, notebook FROM notes WHERE external = 0"
        )
    for row in note_rows:
        path_str = normalize_path(row["path"])
        node_ids.add(path_str)
        nodes.append(
            {
                "id": path_str,
                "title": row["title"] or Path(row["path"]).stem,
                "type": "note",
                "notebook": row["notebook"],
            }
        )

    # Notebook nodes — restricted to the notebooks of the included notes.
    notebook_ids: set[str] = set()
    for row in note_rows:
        nb_name = row["notebook"]
        if nb_name and nb_name not in notebook_ids:
            notebook_ids.add(nb_name)
            nb_conf = config.get_notebook(nb_name)
            color = get_color_hex(nb_conf.color) if nb_conf else None
            nodes.append(
                {
                    "id": f"notebook:{nb_name}",
                    "title": nb_name,
                    "type": "notebook",
                    "color": color,
                }
            )

    # Tag nodes — only tags attached to the included notes (added below as edges
    # are discovered) so a scoped graph doesn't pull in the whole tag universe.
    tag_ids: set[str] = set()

    # Add note -> notebook edges
    for row in note_rows:
        path_str = normalize_path(row["path"])
        nb_name = row["notebook"]
        if nb_name:
            edges.append(
                {
                    "source": path_str,
                    "target": f"notebook:{nb_name}",
                    "type": "notebook",
                }
            )

    # Add note -> tag edges, creating tag nodes only for included notes.
    note_tag_rows = db.fetchall("SELECT note_path, tag FROM note_tags")
    for row in note_tag_rows:
        path_str = normalize_path(row["note_path"])
        tag = row["tag"]
        if path_str in node_ids and tag:
            if tag not in tag_ids:
                tag_ids.add(tag)
                nodes.append({"id": f"tag:{tag}", "title": f"#{tag}", "type": "tag"})
            edges.append(
                {
                    "source": path_str,
                    "target": f"tag:{tag}",
                    "type": "tag",
                }
            )

    # Add note -> note edges (from links)
    link_rows = db.fetchall(
        """SELECT source_path, target_path FROM note_links
           WHERE is_external = 0"""
    )
    for row in link_rows:
        source = normalize_path(row["source_path"])
        target = normalize_path(row["target_path"])

        # Resolve target to actual path if it's a partial reference
        if target not in node_ids:
            target_stem = Path(target).stem
            for node_id in node_ids:
                if Path(node_id).stem == target_stem:
                    target = node_id
                    break

        if source in node_ids and target in node_ids:
            edges.append({"source": source, "target": target, "type": "link"})

    return {"nodes": nodes, "edges": edges}
