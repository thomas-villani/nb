"""Markdown parsing utilities."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import yaml.scanner
from nb.config import get_config
from nb.utils.dates import parse_date_from_filename

# Pattern for wiki-style links: [[path|title]] or [[path]]
WIKI_LINK_PATTERN = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")

# Pattern for markdown-style links: [display](target) - negative lookbehind excludes images ![alt](src)
MD_LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")

# Protocols that indicate an external link
EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "ftp://", "file://")

# Pattern for inline tags: #tag
INLINE_TAG_PATTERN = re.compile(r"(?:^|[\s(])#(\w+)")

# Pattern for first H1 heading
H1_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def parse_note_file(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a markdown file with YAML frontmatter.

    Returns a tuple of (frontmatter_dict, body_content).
    If no frontmatter exists, returns empty dict and full content.
    """
    try:
        with path.open(encoding="utf-8") as f:
            post = frontmatter.load(f)
    except yaml.scanner.ScannerError as e:
        print(f"Error parsing yaml in {path}: {e!r}")
        raise e

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


def is_external_link(target: str) -> bool:
    """Check if a link target is an external URL.

    Returns True for http://, https://, mailto:, ftp://, file:// links.
    """
    return target.lower().startswith(EXTERNAL_LINK_PREFIXES)


def extract_markdown_links(body: str) -> list[tuple[str, str, bool]]:
    """Extract markdown-style links from note body.

    Returns list of (target, display_text, is_external) tuples.
    Does not include image links (![alt](src)).
    """
    links = []
    for match in MD_LINK_PATTERN.finditer(body):
        display = match.group(1).strip()
        target = match.group(2).strip()
        external = is_external_link(target)
        links.append((target, display, external))
    return links


def extract_all_links(body: str) -> list[tuple[str, str, str, bool]]:
    """Extract all links (wiki-style and markdown-style) from note body.

    Returns list of (target, display_text, link_type, is_external) tuples.
    - link_type is 'wiki' for [[...]] or 'markdown' for [...](...).
    - is_external is True for http/https/mailto/etc URLs.
    """
    links: list[tuple[str, str, str, bool]] = []

    # Extract wiki-style links (never external - they're internal note references)
    for match in WIKI_LINK_PATTERN.finditer(body):
        target = match.group(1).strip()
        display = match.group(2)
        if display:
            display = display.strip()
        else:
            display = target
        links.append((target, display, "wiki", False))

    # Extract markdown-style links
    for match in MD_LINK_PATTERN.finditer(body):
        display = match.group(1).strip()
        target = match.group(2).strip()
        external = is_external_link(target)
        links.append((target, display, "markdown", external))

    return links


def extract_frontmatter_links(meta: dict[str, Any]) -> list[tuple[str, str, str, bool]]:
    """Extract links from frontmatter 'links' array.

    Returns list of (target, display_text, link_type, is_external) tuples.
    The link_type will be 'frontmatter' to indicate source.

    Supported formats:
        links:
          # Simple strings
          - "note://notebook/note-name"    # Internal note link
          - "https://example.com"          # External URL

          # Object format for URLs
          - title: "My Link"
            url: "https://example.com"

          # Object format for notes
          - title: "Project Plan"
            note: "2026-plan"
            notebook: "work"              # Optional notebook context
    """
    links: list[tuple[str, str, str, bool]] = []

    links_field = meta.get("links")
    if not links_field:
        return links

    # Ensure it's a list
    if isinstance(links_field, str):
        links_field = [links_field]
    elif not isinstance(links_field, list):
        return links

    for item in links_field:
        if isinstance(item, str):
            # String format: URL or note:// protocol
            item = item.strip()
            if not item:
                continue

            if item.startswith("note://"):
                # note://notebook/note-name format
                path = item[7:]  # Remove "note://"
                display = path.split("/")[-1] if "/" in path else path
                links.append((path, display, "frontmatter", False))
            elif is_external_link(item):
                # External URL
                links.append((item, item, "frontmatter", True))
            else:
                # Treat as note reference
                links.append((item, item, "frontmatter", False))

        elif isinstance(item, dict):
            # Object format
            title = str(item.get("title", ""))

            if "url" in item:
                # External URL link
                url = str(item["url"])
                display = title or url
                links.append((url, display, "frontmatter", True))

            elif "note" in item:
                # Internal note link
                note = str(item["note"])
                notebook = item.get("notebook")
                if notebook:
                    target = f"{notebook}/{note}"
                else:
                    target = note
                display = title or note
                links.append((target, display, "frontmatter", False))

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
        config = get_config()
        content += f"# Notes - {dt.strftime(config.daily_title_format)}\n\n"

    return content


def create_daily_note_template(dt: date) -> str:
    """Generate a template for daily notes."""
    config = get_config()
    meta = {"date": dt.isoformat()}
    content = generate_frontmatter(meta)
    content += f"# {dt.strftime(config.daily_title_format)}\n\n"
    return content
