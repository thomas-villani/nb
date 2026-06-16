"""JSON serialization helpers shared across the web routers.

Moved verbatim from the old ``nb.webserver``: notebook color resolution, note
alias lookup, and frontmatter -> JSON-serializable conversion.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from nb.config import get_config

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


def serialize_frontmatter(fm: dict[str, Any]) -> dict[str, Any]:
    """Convert frontmatter values to JSON-serializable types."""
    result: dict[str, Any] = {}
    for key, val in fm.items():
        if isinstance(val, (date, datetime)):
            result[key] = val.isoformat()
        elif isinstance(val, list):
            result[key] = [
                v.isoformat() if isinstance(v, (date, datetime)) else v for v in val
            ]
        else:
            result[key] = val
    return result
