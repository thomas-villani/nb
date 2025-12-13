"""Web clipping functionality for nb."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from nb.config import get_config


@dataclass
class ClippedContent:
    """Represents content clipped from a URL."""

    url: str
    title: str
    markdown: str
    domain: str
    document_metadata: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_note_content(
        self,
        extra_tags: list[str] | None = None,
        include_domain_tag: bool = True,
    ) -> str:
        """Generate markdown note content with frontmatter.

        Args:
            extra_tags: Additional tags to include
            include_domain_tag: Whether to auto-tag with source domain

        Returns:
            Complete markdown content with frontmatter
        """
        tags = ["clipped"]
        if include_domain_tag:
            # Clean domain for use as tag (remove www. prefix)
            clean_domain = self.domain.removeprefix("www.")
            tags.append(clean_domain)
        if extra_tags:
            tags.extend(extra_tags)

        # Build frontmatter
        frontmatter_lines = [
            "---",
            f'title: "{self.title}"',
            f"date: {self.fetched_at.strftime('%Y-%m-%d')}",
            f"source: {self.url}",
            f"captured: {self.fetched_at.isoformat()}",
            f"tags: [{', '.join(tags)}]",
        ]

        # Add document metadata if present
        if self.document_metadata:
            frontmatter_lines.append("document_metadata:")
            for key, value in self.document_metadata.items():
                # Escape quotes in values
                escaped_value = value.replace('"', '\\"')
                frontmatter_lines.append(f'  {key}: "{escaped_value}"')

        frontmatter_lines.append("---")

        # Build content
        content_lines = [
            "",
            f"# {self.title}",
            "",
            f"[Original source]({self.url})",
            "",
            self.markdown,
        ]

        return "\n".join(frontmatter_lines + content_lines)


def fetch_url(url: str) -> str:
    """Fetch HTML content from a URL.

    Args:
        url: The URL to fetch

    Returns:
        The HTML content as a string

    Raises:
        httpx.HTTPError: If the request fails
    """
    config = get_config()

    headers = {
        "User-Agent": config.clip.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    with httpx.Client(
        timeout=config.clip.timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def extract_metadata_from_html(html: str) -> dict[str, str]:
    """Extract document metadata from HTML meta tags.

    Extracts common metadata including:
    - author (from meta name="author" or og:author)
    - description (from meta name="description" or og:description)
    - published (from article:published_time or meta name="date")
    - modified (from article:modified_time)
    - keywords (from meta name="keywords")
    - site_name (from og:site_name)

    Args:
        html: The HTML content to parse

    Returns:
        Dictionary of metadata key-value pairs (empty values omitted)
    """
    metadata: dict[str, str] = {}

    # Helper to extract meta content by name or property
    def get_meta(name: str | None = None, property: str | None = None) -> str | None:
        if name:
            # Match: <meta name="author" content="...">
            pattern = rf'<meta\s+[^>]*name=["\']?{re.escape(name)}["\']?\s+[^>]*content=["\']([^"\']+)["\']'
            match = re.search(pattern, html, re.IGNORECASE)
            if not match:
                # Try reversed order: content before name
                pattern = rf'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']?{re.escape(name)}["\']?'
                match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        if property:
            # Match: <meta property="og:author" content="...">
            pattern = rf'<meta\s+[^>]*property=["\']?{re.escape(property)}["\']?\s+[^>]*content=["\']([^"\']+)["\']'
            match = re.search(pattern, html, re.IGNORECASE)
            if not match:
                # Try reversed order
                pattern = rf'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']?{re.escape(property)}["\']?'
                match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    # Author - try multiple sources
    author = (
        get_meta(name="author")
        or get_meta(property="og:author")
        or get_meta(property="article:author")
        or get_meta(name="twitter:creator")
    )
    if author:
        metadata["author"] = author

    # Description
    description = get_meta(name="description") or get_meta(property="og:description")
    if description:
        # Truncate long descriptions
        if len(description) > 300:
            description = description[:297] + "..."
        metadata["description"] = description

    # Published date
    published = (
        get_meta(property="article:published_time")
        or get_meta(name="date")
        or get_meta(name="pubdate")
        or get_meta(name="publishdate")
        or get_meta(property="og:published_time")
    )
    if published:
        metadata["published"] = published

    # Modified date
    modified = (
        get_meta(property="article:modified_time")
        or get_meta(name="lastmod")
        or get_meta(property="og:updated_time")
    )
    if modified:
        metadata["modified"] = modified

    # Keywords
    keywords = get_meta(name="keywords")
    if keywords:
        metadata["keywords"] = keywords

    # Site name
    site_name = get_meta(property="og:site_name")
    if site_name:
        metadata["site_name"] = site_name

    # Article section/category
    section = get_meta(property="article:section") or get_meta(name="category")
    if section:
        metadata["section"] = section

    return metadata


def html_to_markdown(html: str, section: str | None = None) -> str:
    """Convert HTML to markdown, optionally extracting a section.

    Args:
        html: The HTML content to convert
        section: Optional section name/pattern to extract (uses fnmatch)

    Returns:
        Markdown content (possibly just a section)
    """
    from all2md import to_ast, to_markdown
    from all2md.ast.sections import extract_sections

    if section:
        # Parse to AST, extract section, render to markdown
        doc = to_ast(html, source_format="html")
        try:
            extracted = extract_sections(doc, section, case_sensitive=False)
            return to_markdown(extracted)
        except ValueError as e:
            # Section not found - include error message and full content
            full_content = to_markdown(html, source_format="html")
            return (
                f"*Note: Section '{section}' not found. Error: {e}*\n\n{full_content}"
            )
    else:
        # Simple conversion
        return to_markdown(html, source_format="html")


def extract_title_from_markdown(markdown: str) -> str:
    """Extract the first H1 heading from markdown as the title.

    Args:
        markdown: The markdown content

    Returns:
        The title (first H1) or "Untitled" if none found
    """
    # Look for first H1 heading
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def extract_title_from_html(html: str) -> str:
    """Extract the title from HTML <title> tag.

    Args:
        html: The HTML content

    Returns:
        The title or "Untitled" if not found
    """
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def clip_url(
    url: str,
    section: str | None = None,
    title: str | None = None,
) -> ClippedContent:
    """Clip content from a URL and convert to markdown.

    Args:
        url: The URL to clip
        section: Optional section name/pattern to extract
        title: Optional custom title (overrides extracted title)

    Returns:
        ClippedContent with the clipped markdown and metadata

    Raises:
        httpx.HTTPError: If fetching fails
        ValueError: If conversion fails
    """
    # Parse URL to get domain
    parsed = urlparse(url)
    domain = parsed.netloc

    # Fetch HTML
    html = fetch_url(url)

    # Extract document metadata
    document_metadata = extract_metadata_from_html(html)

    # Convert to markdown
    markdown = html_to_markdown(html, section=section)

    # Determine title
    if title:
        resolved_title = title
    else:
        # Try HTML title first, fall back to markdown H1
        resolved_title = extract_title_from_html(html)
        if resolved_title == "Untitled":
            resolved_title = extract_title_from_markdown(markdown)

    return ClippedContent(
        url=url,
        title=resolved_title,
        markdown=markdown,
        domain=domain,
        document_metadata=document_metadata,
    )


def clip_file(
    file_path: Path,
    section: str | None = None,
    title: str | None = None,
) -> ClippedContent:
    """Clip content from a local file and convert to markdown.

    Uses all2md to convert various file formats (PDF, DOCX, PPTX, etc.) to markdown.

    Args:
        file_path: Path to the file to convert
        section: Optional section name/pattern to extract
        title: Optional custom title (overrides extracted title)

    Returns:
        ClippedContent with the converted markdown and metadata

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If conversion fails
    """
    from all2md import to_markdown

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Get file stats for metadata
    file_stat = file_path.stat()

    # Convert file to markdown (all2md auto-detects format from extension)
    try:
        markdown = to_markdown(file_path, source_format="auto")
    except Exception as e:
        raise ValueError(f"Failed to convert file: {e}") from e

    # If section extraction requested, apply it
    if section:
        from all2md import to_ast
        from all2md.ast.sections import extract_sections

        try:
            doc = to_ast(markdown, source_format="markdown")
            extracted = extract_sections(doc, section, case_sensitive=False)
            markdown = to_markdown(extracted)
        except ValueError as e:
            # Section not found - include error message and full content
            markdown = (
                f"*Note: Section '{section}' not found. Error: {e}*\n\n{markdown}"
            )

    # Determine title
    if title:
        resolved_title = title
    else:
        # Try to extract from markdown, otherwise use filename
        resolved_title = extract_title_from_markdown(markdown)
        if resolved_title == "Untitled":
            resolved_title = file_path.stem  # Filename without extension

    # Build metadata from file info
    document_metadata = {
        "source_file": str(file_path.absolute()),
        "file_size": str(file_stat.st_size),
        "file_type": file_path.suffix.lstrip(".").upper() or "unknown",
    }

    return ClippedContent(
        url=f"file://{file_path.absolute()}",
        title=resolved_title,
        markdown=markdown,
        domain="local-file",
        document_metadata=document_metadata,
    )


def _safe_reindex(path: Path, notes_root: Path) -> str | None:
    """Re-index a note, handling errors gracefully.

    Some clipped content may have duplicate links or other issues
    that cause indexing to fail. We still want to save the note.

    Returns:
        None if successful, error message string if indexing failed.
    """
    from nb.core.notes import _reindex_note_after_edit

    try:
        _reindex_note_after_edit(path, notes_root)
        return None
    except Exception as e:
        # Return error message - the note will be indexed on next full index run
        return str(e)


def save_clipped_note(
    clipped: ClippedContent,
    notebook: str | None = None,
    target_note: Path | None = None,
    extra_tags: list[str] | None = None,
) -> Path:
    """Save clipped content as a note or append to existing note.

    Args:
        clipped: The clipped content to save
        notebook: Notebook to create new note in (if target_note not specified)
        target_note: Existing note to append to (absolute path)
        extra_tags: Additional tags to include

    Returns:
        Path to the created/modified note
    """
    from nb.core.notebooks import is_notebook_date_based
    from nb.core.notes import ensure_daily_note

    config = get_config()
    include_domain_tag = config.clip.auto_tag_domain

    if target_note:
        # Append to existing note
        note_content = clipped.to_note_content(
            extra_tags=extra_tags,
            include_domain_tag=include_domain_tag,
        )

        # Strip frontmatter for appending (keep just the content)
        lines = note_content.split("\n")
        # Find end of frontmatter
        frontmatter_end = 0
        if lines[0] == "---":
            for i, line in enumerate(lines[1:], 1):
                if line == "---":
                    frontmatter_end = i + 1
                    break

        append_content = "\n".join(lines[frontmatter_end:])

        with target_note.open("a", encoding="utf-8") as f:
            f.write(f"\n---\n\n{append_content}")

        # Re-index to update search and todos
        _safe_reindex(target_note, config.notes_root)
        return target_note

    elif notebook:
        # Create new note in specified notebook
        # Generate filename from title
        slug = slugify(clipped.title)
        if is_notebook_date_based(notebook):
            # For date-based notebooks, include date prefix
            date_prefix = clipped.fetched_at.strftime("%Y-%m-%d")
            filename = f"{date_prefix}-{slug}"
        else:
            filename = slug

        note_path = Path(notebook) / f"{filename}.md"
        full_path = config.notes_root / note_path

        # Check if note already exists
        if full_path.exists():
            raise FileExistsError(f"Note already exists: {note_path}")

        # Create directory structure
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate full content and write
        content = clipped.to_note_content(
            extra_tags=extra_tags,
            include_domain_tag=include_domain_tag,
        )
        full_path.write_text(content, encoding="utf-8")

        # Re-index to update search and todos
        _safe_reindex(full_path, config.notes_root)
        return full_path

    else:
        # Append to today's daily note
        daily_path = ensure_daily_note(date.today())

        note_content = clipped.to_note_content(
            extra_tags=extra_tags,
            include_domain_tag=include_domain_tag,
        )

        # Strip frontmatter for appending
        lines = note_content.split("\n")
        frontmatter_end = 0
        if lines[0] == "---":
            for i, line in enumerate(lines[1:], 1):
                if line == "---":
                    frontmatter_end = i + 1
                    break

        append_content = "\n".join(lines[frontmatter_end:])

        with daily_path.open("a", encoding="utf-8") as f:
            f.write(f"\n---\n\n{append_content}")

        # Re-index to update search and todos
        _safe_reindex(daily_path, config.notes_root)
        return daily_path


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a URL-friendly slug.

    Args:
        text: The text to slugify
        max_length: Maximum length of the slug

    Returns:
        A lowercase, hyphenated slug
    """
    # Convert to lowercase
    slug = text.lower()

    # Replace non-alphanumeric chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)

    # Remove leading/trailing hyphens
    slug = slug.strip("-")

    # Truncate to max length (at word boundary if possible)
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0]

    return slug or "untitled"
