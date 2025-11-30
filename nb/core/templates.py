"""Template operations for nb."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from nb.config import get_config


def get_templates_dir(notes_root: Path | None = None) -> Path:
    """Get the templates directory (.nb/templates).

    Args:
        notes_root: Override notes root directory

    Returns:
        Path to the templates directory.

    """
    if notes_root is None:
        notes_root = get_config().notes_root
    return notes_root / ".nb" / "templates"


def ensure_templates_dir(notes_root: Path | None = None) -> Path:
    """Ensure templates directory exists.

    Args:
        notes_root: Override notes root directory

    Returns:
        Path to the templates directory.

    """
    templates_dir = get_templates_dir(notes_root)
    templates_dir.mkdir(parents=True, exist_ok=True)
    return templates_dir


def list_templates(notes_root: Path | None = None) -> list[str]:
    """List available template names (without .md extension).

    Args:
        notes_root: Override notes root directory

    Returns:
        Sorted list of template names.

    """
    templates_dir = get_templates_dir(notes_root)
    if not templates_dir.exists():
        return []
    return sorted([p.stem for p in templates_dir.glob("*.md")])


def get_template_path(name: str, notes_root: Path | None = None) -> Path:
    """Get full path to a template file.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        Full path to the template file.

    """
    templates_dir = get_templates_dir(notes_root)
    return templates_dir / f"{name}.md"


def template_exists(name: str, notes_root: Path | None = None) -> bool:
    """Check if a template exists.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        True if the template exists.

    """
    return get_template_path(name, notes_root).exists()


def read_template(name: str, notes_root: Path | None = None) -> str | None:
    """Read template content.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        Template content, or None if not found.

    """
    path = get_template_path(name, notes_root)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def create_template(
    name: str,
    content: str,
    notes_root: Path | None = None,
) -> Path:
    """Create a new template file.

    Args:
        name: Template name (without .md extension)
        content: Template content
        notes_root: Override notes root directory

    Returns:
        Path to the created template file.

    Raises:
        FileExistsError: If the template already exists.

    """
    ensure_templates_dir(notes_root)
    path = get_template_path(name, notes_root)
    if path.exists():
        raise FileExistsError(f"Template already exists: {name}")
    path.write_text(content, encoding="utf-8")
    return path


def remove_template(name: str, notes_root: Path | None = None) -> bool:
    """Remove a template.

    Args:
        name: Template name (without .md extension)
        notes_root: Override notes root directory

    Returns:
        True if removed, False if not found.

    """
    path = get_template_path(name, notes_root)
    if path.exists():
        path.unlink()
        return True
    return False


def render_template(
    content: str,
    title: str | None = None,
    notebook: str | None = None,
    dt: date | None = None,
) -> str:
    """Render template variables.

    Supported variables:
    - {{ date }} - ISO date (YYYY-MM-DD)
    - {{ datetime }} - ISO datetime
    - {{ notebook }} - Notebook name
    - {{ title }} - Note title

    Args:
        content: Template content with variables
        title: Note title (for {{ title }})
        notebook: Notebook name (for {{ notebook }})
        dt: Date for the note (for {{ date }}, defaults to today)

    Returns:
        Rendered template with variables replaced.

    """
    if dt is None:
        dt = date.today()

    now = datetime.now()

    replacements = {
        "{{ date }}": dt.isoformat(),
        "{{ datetime }}": now.isoformat(timespec="minutes"),
        "{{ notebook }}": notebook or "",
        "{{ title }}": title or "",
    }

    result = content
    for var, value in replacements.items():
        result = result.replace(var, value)

    return result


# Default template content for new templates
DEFAULT_TEMPLATE_CONTENT = """\
---
date: {{ date }}
---

# {{ title }}

"""
