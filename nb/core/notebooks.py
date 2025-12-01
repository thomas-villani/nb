"""Notebook operations for nb."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from nb.config import get_config


def list_notebooks(notes_root: Path | None = None) -> list[str]:
    """List all notebook directories.

    Returns a list of notebook names (directory names directly under notes_root).
    Excludes hidden directories and .nb.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if not notes_root.exists():
        return []

    notebooks = []
    for item in notes_root.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            notebooks.append(item.name)

    return sorted(notebooks)


def get_notebook_notes(notebook: str, notes_root: Path | None = None) -> list[Path]:
    """List all notes in a specific notebook.

    Args:
        notebook: Name of the notebook
        notes_root: Override notes root directory

    Returns:
        List of paths to notes in the notebook.
        For internal notebooks: relative paths from notes_root.
        For external notebooks: absolute paths.

    """
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    # Check if this is an external notebook
    nb_config = config.get_notebook(notebook)
    if nb_config and nb_config.is_external:
        notebook_path = nb_config.path
        if not notebook_path or not notebook_path.exists():
            return []

        notes = []
        for md_file in notebook_path.rglob("*.md"):
            # Skip hidden directories
            try:
                rel_parts = md_file.relative_to(notebook_path).parts
                if any(part.startswith(".") for part in rel_parts):
                    continue
            except ValueError:
                continue
            # Return absolute paths for external notebooks
            notes.append(md_file)
        return sorted(notes)

    # Internal notebook
    notebook_path = notes_root / notebook
    if not notebook_path.exists():
        return []

    notes = []
    for md_file in notebook_path.rglob("*.md"):
        # Skip hidden directories
        if any(
            part.startswith(".") for part in md_file.relative_to(notebook_path).parts
        ):
            continue
        try:
            relative = md_file.relative_to(notes_root)
            notes.append(relative)
        except ValueError:
            pass

    return sorted(notes)


def get_notebook_notes_with_linked(
    notebook: str, notes_root: Path | None = None
) -> list[tuple[Path, bool, str | None]]:
    """List all notes in a specific notebook, including linked notes.

    Args:
        notebook: Name of the notebook (can include @ prefix for linked notebooks)
        notes_root: Override notes root directory

    Returns:
        List of (path, is_linked, alias) tuples for notes in the notebook.
        For linked notes, alias is the linked note alias; for regular notes, it's None.

    """
    from nb.core.links import list_linked_notes
    from nb.index.db import get_db

    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    # Get regular notebook notes first
    regular_notes = get_notebook_notes(notebook, notes_root)
    results: list[tuple[Path, bool, str | None]] = [
        (p, False, None) for p in regular_notes
    ]

    # Build a map of paths to aliases for linked notes in this notebook
    path_to_alias: dict[str, str] = {}
    for ln in list_linked_notes():
        ln_notebook = ln.notebook or f"@{ln.alias}"
        if ln_notebook == notebook:
            # For single-file links, map the file path
            if ln.path.is_file():
                path_to_alias[str(ln.path.resolve())] = ln.alias
            else:
                # For directory links, we'll match by checking if path is under ln.path
                # Store the base path and alias for later matching
                path_to_alias[f"dir:{ln.path.resolve()}"] = ln.alias

    # Also check for linked notes with this notebook name
    db = get_db()
    rows = db.fetchall(
        "SELECT path FROM notes WHERE notebook = ? AND external = 1",
        (notebook,),
    )

    for row in rows:
        note_path = Path(row["path"])
        # Try to find the alias for this path
        alias = None
        resolved = (
            str(note_path.resolve()) if note_path.is_absolute() else str(note_path)
        )

        # Check direct path match
        if resolved in path_to_alias:
            alias = path_to_alias[resolved]
        else:
            # Check if it's under a linked directory
            for key, value in path_to_alias.items():
                if key.startswith("dir:"):
                    dir_path = key[4:]
                    try:
                        if note_path.is_absolute():
                            note_path.relative_to(dir_path)
                        alias = value
                        break
                    except ValueError:
                        continue

        results.append((note_path, True, alias))

    # Sort by path
    return sorted(results, key=lambda x: str(x[0]))


def create_notebook(name: str, notes_root: Path | None = None) -> Path:
    """Create a new notebook directory.

    Args:
        name: Name of the notebook (will be used as directory name)
        notes_root: Override notes root directory

    Returns:
        Path to the created notebook directory.

    Raises:
        FileExistsError: If the notebook already exists.

    """
    if notes_root is None:
        notes_root = get_config().notes_root

    notebook_path = notes_root / name

    if notebook_path.exists():
        raise FileExistsError(f"Notebook already exists: {name}")

    notebook_path.mkdir(parents=True)
    return notebook_path


def notebook_exists(name: str, notes_root: Path | None = None) -> bool:
    """Check if a notebook exists."""
    if notes_root is None:
        notes_root = get_config().notes_root

    notebook_path = notes_root / name
    return notebook_path.is_dir()


def get_notebook_stats(notebook: str, notes_root: Path | None = None) -> dict[str, int]:
    """Get statistics for a notebook.

    Returns:
        Dictionary with:
        - note_count: Number of notes
        - todo_count: Number of todos (requires indexing)

    """
    notes = get_notebook_notes(notebook, notes_root)
    return {
        "note_count": len(notes),
    }


def is_notebook_date_based(notebook: str) -> bool:
    """Check if a notebook uses date-based organization.

    Args:
        notebook: Name of the notebook

    Returns:
        True if the notebook uses YYYY/MM/YYYY-MM-DD.md structure.

    """
    config = get_config()
    nb_config = config.get_notebook(notebook)
    if nb_config:
        return nb_config.date_based
    # Default: only "daily" is date-based for unknown notebooks
    return notebook == "daily"


def get_notebook_for_file(path: Path) -> str | None:
    """Determine which notebook a file belongs to.

    Checks both internal notebooks (under notes_root) and external notebooks.

    Args:
        path: Absolute path to the file

    Returns:
        Notebook name, or None if not in any notebook.

    """
    config = get_config()

    # Check external notebooks first (they have explicit paths)
    for nb in config.external_notebooks():
        if nb.path and path.is_relative_to(nb.path):
            return nb.name

    # Check internal notebooks (under notes_root)
    try:
        relative = path.relative_to(config.notes_root)
        if len(relative.parts) > 1:
            # First directory component is the notebook (only if file is in a subdirectory)
            return relative.parts[0]
        # File is in root of notes_root (e.g., ~/notes/quick.md) - no notebook
    except ValueError:
        pass

    return None


def get_notebook_note_path(
    notebook: str,
    dt: date | None = None,
    name: str | None = None,
) -> Path:
    """Get the path for a note in a notebook.

    For date-based notebooks, creates path like: base/YYYY/Nov25-Dec01/YYYY-MM-DD.md
    (organized by work week, Monday-Sunday)

    For flat notebooks, creates path like: base/name.md

    Args:
        notebook: Name of the notebook
        dt: Date for date-based notebooks (defaults to today)
        name: Filename for flat notebooks (required if not date-based)

    Returns:
        Full path to the note file.

    Raises:
        ValueError: If name is required but not provided, or notebook doesn't exist.

    """
    from nb.utils.dates import get_week_folder_name

    config = get_config()
    nb_config = config.get_notebook(notebook)

    # Determine base path (external path or notes_root/notebook)
    if nb_config and nb_config.is_external:
        if not nb_config.path:
            raise ValueError(f"External notebook '{notebook}' has no path configured")
        base_path = nb_config.path
    else:
        base_path = config.notes_root / notebook

    if is_notebook_date_based(notebook):
        if dt is None:
            dt = date.today()
        week_folder = get_week_folder_name(dt)
        return base_path / str(dt.year) / week_folder / f"{dt}.md"
    else:
        if name is None:
            raise ValueError(f"Name required for non-date-based notebook: {notebook}")
        # Ensure .md extension
        if not name.endswith(".md"):
            name = f"{name}.md"
        return base_path / name


def ensure_notebook_note(
    notebook: str,
    dt: date | None = None,
    name: str | None = None,
    template: str | None = None,
) -> Path:
    """Ensure a note exists in a notebook, creating it if necessary.

    For date-based notebooks, creates the daily note with a header.
    For flat notebooks, creates an empty note with a title.

    If a template is specified or the notebook has a default template,
    it will be used instead of the built-in templates.

    Args:
        notebook: Name of the notebook
        dt: Date for date-based notebooks (defaults to today)
        name: Filename for flat notebooks (required if not date-based)
        template: Template name to use (overrides notebook default)

    Returns:
        Path to the note file.

    """
    path = get_notebook_note_path(notebook, dt=dt, name=name)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

        # Resolve template: explicit > notebook default > none
        config = get_config()
        nb_config = config.get_notebook(notebook)
        resolved_template = template
        if resolved_template is None and nb_config and nb_config.template:
            resolved_template = nb_config.template

        if resolved_template:
            from nb.core.templates import read_template, render_template

            template_content = read_template(resolved_template)
            if template_content:
                if dt is None:
                    dt = date.today()
                title = (
                    name.replace("-", " ").replace("_", " ").title()
                    if name
                    else dt.strftime(config.daily_title_format)
                )
                content = render_template(
                    template_content,
                    title=title,
                    notebook=notebook,
                    dt=dt,
                )
                path.write_text(content, encoding="utf-8")
                return path

        # Fall back to built-in templates
        if is_notebook_date_based(notebook):
            if dt is None:
                dt = date.today()
            # Create daily note with header
            path.write_text(
                f"---\ndate: {dt}\n---\n\n# {dt.strftime(config.daily_title_format)}\n\n",
                encoding="utf-8",
            )
        else:
            # Create note with title from filename
            title = path.stem.replace("-", " ").replace("_", " ").title()
            path.write_text(
                f"---\ntitle: {title}\n---\n\n# {title}\n\n",
                encoding="utf-8",
            )

    return path
