"""Markdown parsing utilities."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter

from nb.utils.dates import parse_date_from_filename

# Pattern for wiki-style links: [[path|title]] or [[path]]
WIKI_LINK_PATTERN = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")

# Pattern for inline tags: #tag
INLINE_TAG_PATTERN = re.compile(r"(?:^|[\s(])#(\w+)")

# Pattern for first H1 heading
H1_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def parse_note_file(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a markdown file with YAML frontmatter.

    Returns a tuple of (frontmatter_dict, body_content).
    If no frontmatter exists, returns empty dict and full content.
    """
    with open(path, encoding="utf-8") as f:
        post = frontmatter.load(f)
    return dict(post.metadata), post.content


def extract_title(meta: dict[str, Any], body: str, path: Path) -> str:
    """Extract the title of a note.

    Priority:
    1. 'title' field in frontmatter
    2. First H1 heading in body
    3. Filename (without extension)
    """
    # Check frontmatter
    if "title" in meta:
        return str(meta["title"])

    # Look for first H1
    match = H1_PATTERN.search(body)
    if match:
        return match.group(1).strip()

    # Fall back to filename
    return path.stem


def extract_date(meta: dict[str, Any], path: Path) -> date | None:
    """Extract the date of a note.

    Priority:
    1. 'date' field in frontmatter
    2. Date pattern in filename (YYYY-MM-DD)
    """
    # Check frontmatter
    if "date" in meta:
        date_val = meta["date"]
        if isinstance(date_val, date):
            return date_val
        if isinstance(date_val, str):
            from nb.utils.dates import parse_fuzzy_date

            return parse_fuzzy_date(date_val)

    # Try to extract from filename
    return parse_date_from_filename(path.name)


def extract_todo_exclude(meta: dict[str, Any]) -> bool:
    """Check if note has todo_exclude: true in frontmatter.

    Returns True if todos from this note should be excluded from
    default 'nb todo' display.
    """
    return bool(meta.get("todo_exclude", False))


def extract_tags(meta: dict[str, Any], body: str) -> list[str]:
    """Extract all tags from a note.

    Combines:
    1. 'tags' list in frontmatter
    2. Inline #tags in body
    """
    tags: set[str] = set()

    # Get frontmatter tags
    if "tags" in meta:
        fm_tags = meta["tags"]
        if isinstance(fm_tags, list):
            tags.update(str(t) for t in fm_tags)
        elif isinstance(fm_tags, str):
            # Handle comma-separated string
            tags.update(t.strip() for t in fm_tags.split(",") if t.strip())

    # Find inline tags (skip inside code blocks)
    # Simple approach: just find all #tag patterns
    # A more robust approach would parse markdown properly
    for match in INLINE_TAG_PATTERN.finditer(body):
        tags.add(match.group(1).lower())

    return sorted(tags)


def extract_wiki_links(body: str) -> list[tuple[str, str]]:
    """Extract wiki-style links from note body.

    Returns list of (path, display_text) tuples.
    If no display text is given, it's the same as the path.
    """
    links = []
    for match in WIKI_LINK_PATTERN.finditer(body):
        path = match.group(1).strip()
        display = match.group(2)
        if display:
            display = display.strip()
        else:
            display = path
        links.append((path, display))
    return links


def generate_frontmatter(meta: dict[str, Any]) -> str:
    """Generate YAML frontmatter string from a dictionary."""
    if not meta:
        return ""

    import yaml

    yaml_str = yaml.safe_dump(meta, default_flow_style=False, sort_keys=False)
    return f"---\n{yaml_str}---\n\n"


def create_note_template(
    title: str | None = None,
    dt: date | None = None,
    tags: list[str] | None = None,
) -> str:
    """Generate a note template with frontmatter.

    Args:
        title: Optional title for the note
        dt: Date for the note (defaults to today)
        tags: Optional list of tags

    """
    if dt is None:
        dt = date.today()

    meta: dict[str, Any] = {"date": dt.isoformat()}

    if tags:
        meta["tags"] = tags

    content = generate_frontmatter(meta)

    # Add title as H1 if provided
    if title:
        content += f"# {title}\n\n"
    else:
        # Default title based on date
        content += f"# Notes - {dt.strftime('%B %d, %Y')}\n\n"

    return content


def create_daily_note_template(dt: date) -> str:
    """Generate a template for daily notes."""
    meta = {"date": dt.isoformat()}
    content = generate_frontmatter(meta)
    content += f"# {dt.strftime('%B %d, %Y')}\n\n"
    return content
