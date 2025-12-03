"""Note link management and querying for nb."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nb.config import get_config
from nb.index.db import get_db
from nb.utils.hashing import normalize_path


@dataclass
class NoteLink:
    """A link from a note to another note or URL."""

    target: str  # Raw target from markdown
    display_text: str
    link_type: str  # 'wiki', 'markdown', 'frontmatter'
    is_external: bool
    resolved_path: Path | None = None  # None if external or broken
    line_number: int | None = None


@dataclass
class Backlink:
    """A link from another note to the current note."""

    source_path: Path
    display_text: str
    link_type: str
    line_number: int | None = None
    context: str | None = None  # Surrounding text


@dataclass
class BrokenLink:
    """A broken internal link."""

    source_path: Path
    target: str
    display_text: str
    link_type: str
    line_number: int | None = None
    suggestion: str | None = None  # Did you mean...?


def get_outgoing_links(
        note_path: Path,
        internal_only: bool = False,
        external_only: bool = False,
) -> list[NoteLink]:
    """Get all links from a note.

    Args:
        note_path: Path to the note (absolute or relative to notes_root).
        internal_only: Only return internal links.
        external_only: Only return external links.

    Returns:
        List of NoteLink objects.
    """
    config = get_config()
    db = get_db()

    # Normalize the path for database lookup
    if note_path.is_absolute():
        try:
            note_path = note_path.relative_to(config.notes_root)
        except ValueError:
            pass  # External note, use as-is
    normalized = normalize_path(note_path)

    # Query links from database
    rows = db.fetchall(
        """SELECT target_path, display_text, link_type, is_external, line_number
           FROM note_links WHERE source_path = ?""",
        (normalized,),
    )

    links: list[NoteLink] = []
    for row in rows:
        is_external = bool(row["is_external"])

        # Apply filters
        if internal_only and is_external:
            continue
        if external_only and not is_external:
            continue

        # Try to resolve internal links
        resolved_path = None
        if not is_external:
            resolved_path = resolve_link_target(
                row["target_path"], note_path, config.notes_root
            )

        links.append(
            NoteLink(
                target=row["target_path"],
                display_text=row["display_text"],
                link_type=row["link_type"] or "wiki",
                is_external=is_external,
                resolved_path=resolved_path,
                line_number=row["line_number"],
            )
        )

    return links


def get_backlinks(note_path: Path) -> list[Backlink]:
    """Get all notes that link to the given note.

    Args:
        note_path: Path to the note (absolute or relative to notes_root).

    Returns:
        List of Backlink objects.
    """
    config = get_config()
    db = get_db()

    # Normalize the path for database lookup
    if note_path.is_absolute():
        try:
            note_path = note_path.relative_to(config.notes_root)
        except ValueError:
            pass  # External note, use as-is
    normalized = normalize_path(note_path)

    # Build patterns to match different link formats
    # Links might be stored as:
    # - Exact path: "projects/myproject.md"
    # - Without extension: "projects/myproject"
    # - Just filename: "myproject"
    # - With alias

    target_patterns = [
        normalized,
        normalized.replace("\\", "/"),  # Normalize slashes
    ]

    # Add version without .md extension
    if normalized.endswith(".md"):
        target_patterns.append(normalized[:-3])
        target_patterns.append(normalized[:-3].replace("\\", "/"))

    # Add just the filename
    stem = Path(normalized).stem
    target_patterns.append(stem)

    # Query for all matching links
    placeholders = ", ".join("?" for _ in target_patterns)
    rows = db.fetchall(
        f"""SELECT source_path, display_text, link_type, line_number
            FROM note_links
            WHERE is_external = 0 AND target_path IN ({placeholders})""",
        tuple(target_patterns),
    )

    backlinks: list[Backlink] = []
    seen_sources: set[str] = set()

    for row in rows:
        source = row["source_path"]
        # Deduplicate by source path
        if source in seen_sources:
            continue
        seen_sources.add(source)

        backlinks.append(
            Backlink(
                source_path=Path(source),
                display_text=row["display_text"],
                link_type=row["link_type"] or "wiki",
                line_number=row["line_number"],
            )
        )

    return backlinks


def resolve_link_target(
        target: str,
        source_path: Path,
        notes_root: Path | None = None,
) -> Path | None:
    """Resolve a link target to an actual note path.

    Handles:
    - Relative paths: `../other.md` or `./sibling.md`
    - Aliases: `[[myalias]]` via get_note_by_alias()
    - Partial names: `[[project]]` -> `projects/project.md`
    - Date references: `[[2025-11-28]]` -> daily note path

    Args:
        target: The link target string.
        source_path: Path to the note containing the link.
        notes_root: Root directory for notes.

    Returns:
        Resolved Path if found, None otherwise.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    # Handle relative paths
    if target.startswith("./") or target.startswith("../"):
        # Resolve relative to source note's directory
        if source_path.is_absolute():
            source_dir = source_path.parent
        else:
            source_dir = (notes_root / source_path).parent
        resolved = (source_dir / target).resolve()
        if resolved.exists():
            return resolved
        # Try with .md extension
        if not resolved.suffix:
            with_md = resolved.with_suffix(".md")
            if with_md.exists():
                return with_md
        return None

    # Try alias resolution
    from nb.core.aliases import get_note_by_alias

    alias_result = get_note_by_alias(target)
    if alias_result and alias_result.exists():
        return alias_result

    # Try direct path (with and without .md)
    direct = notes_root / target
    if direct.exists():
        return direct
    if not direct.suffix:
        with_md = direct.with_suffix(".md")
        if with_md.exists():
            return with_md

    # Try to find by filename match
    target_stem = Path(target).stem
    db = get_db()
    rows = db.fetchall(
        "SELECT path FROM notes WHERE path LIKE ? OR path LIKE ?",
        (f"%/{target_stem}.md", f"%\\{target_stem}.md"),
    )
    if rows:
        # Return first match
        return notes_root / rows[0]["path"]

    # Try date parsing for daily notes
    from nb.utils.dates import parse_fuzzy_date

    parsed_date = parse_fuzzy_date(target)
    if parsed_date:
        from nb.core.notes import get_daily_note_path

        daily_path = get_daily_note_path(parsed_date, notes_root)
        if daily_path.exists():
            return daily_path

    return None


def get_broken_links(note_path: Path | None = None) -> list[BrokenLink]:
    """Find broken internal links.

    Args:
        note_path: If specified, only check links from this note.
                   Otherwise, check all notes.

    Returns:
        List of BrokenLink objects.
    """
    config = get_config()
    db = get_db()

    # Query internal links
    if note_path:
        if note_path.is_absolute():
            try:
                note_path = note_path.relative_to(config.notes_root)
            except ValueError:
                pass
        normalized = normalize_path(note_path)
        rows = db.fetchall(
            """SELECT source_path, target_path, display_text, link_type, line_number
               FROM note_links WHERE source_path = ? AND is_external = 0""",
            (normalized,),
        )
    else:
        rows = db.fetchall(
            """SELECT source_path, target_path, display_text, link_type, line_number
               FROM note_links WHERE is_external = 0"""
        )

    broken: list[BrokenLink] = []

    for row in rows:
        source = Path(row["source_path"])
        target = row["target_path"]

        # Try to resolve the link
        resolved = resolve_link_target(target, source, config.notes_root)
        if resolved is None:
            # Link is broken - try to find a suggestion
            suggestion = _find_similar_note(target, config.notes_root)
            broken.append(
                BrokenLink(
                    source_path=source,
                    target=target,
                    display_text=row["display_text"],
                    link_type=row["link_type"] or "wiki",
                    line_number=row["line_number"],
                    suggestion=suggestion,
                )
            )

    return broken


def _find_similar_note(target: str, notes_root: Path) -> str | None:
    """Find a similar note name for suggestions.

    Uses simple string matching to find potential typos.
    """
    from difflib import get_close_matches

    db = get_db()
    rows = db.fetchall("SELECT path FROM notes")
    all_paths = [row["path"] for row in rows]

    # Extract just filenames for matching
    filenames = [Path(p).stem for p in all_paths]
    target_stem = Path(target).stem

    matches = get_close_matches(target_stem, filenames, n=1, cutoff=0.6)
    if matches:
        # Find the full path for this match
        for path in all_paths:
            if Path(path).stem == matches[0]:
                return path

    return None


def get_link_stats() -> dict[str, int]:
    """Get statistics about links in the notes database.

    Returns:
        Dictionary with link statistics.
    """
    db = get_db()

    total = db.fetchone("SELECT COUNT(*) as cnt FROM note_links")
    internal = db.fetchone(
        "SELECT COUNT(*) as cnt FROM note_links WHERE is_external = 0"
    )
    external = db.fetchone(
        "SELECT COUNT(*) as cnt FROM note_links WHERE is_external = 1"
    )
    wiki = db.fetchone(
        "SELECT COUNT(*) as cnt FROM note_links WHERE link_type = 'wiki'"
    )
    markdown = db.fetchone(
        "SELECT COUNT(*) as cnt FROM note_links WHERE link_type = 'markdown'"
    )
    frontmatter = db.fetchone(
        "SELECT COUNT(*) as cnt FROM note_links WHERE link_type = 'frontmatter'"
    )

    return {
        "total": total["cnt"] if total else 0,
        "internal": internal["cnt"] if internal else 0,
        "external": external["cnt"] if external else 0,
        "wiki": wiki["cnt"] if wiki else 0,
        "markdown": markdown["cnt"] if markdown else 0,
        "frontmatter": frontmatter["cnt"] if frontmatter else 0,
    }
