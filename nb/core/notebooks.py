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
        List of relative paths to notes in the notebook.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

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


def get_notebook_note_path(
    notebook: str,
    dt: date | None = None,
    name: str | None = None,
) -> Path:
    """Get the path for a note in a notebook.

    For date-based notebooks, creates path like: notebook/YYYY/MM/YYYY-MM-DD.md
    For flat notebooks, creates path like: notebook/name.md

    Args:
        notebook: Name of the notebook
        dt: Date for date-based notebooks (defaults to today)
        name: Filename for flat notebooks (required if not date-based)

    Returns:
        Full path to the note file.

    Raises:
        ValueError: If name is required but not provided.
    """
    config = get_config()

    if is_notebook_date_based(notebook):
        if dt is None:
            dt = date.today()
        return (
            config.notes_root / notebook / str(dt.year) / f"{dt.month:02d}" / f"{dt}.md"
        )
    else:
        if name is None:
            raise ValueError(f"Name required for non-date-based notebook: {notebook}")
        # Ensure .md extension
        if not name.endswith(".md"):
            name = f"{name}.md"
        return config.notes_root / notebook / name


def ensure_notebook_note(
    notebook: str,
    dt: date | None = None,
    name: str | None = None,
) -> Path:
    """Ensure a note exists in a notebook, creating it if necessary.

    For date-based notebooks, creates the daily note with a header.
    For flat notebooks, creates an empty note with a title.

    Args:
        notebook: Name of the notebook
        dt: Date for date-based notebooks (defaults to today)
        name: Filename for flat notebooks (required if not date-based)

    Returns:
        Path to the note file.
    """
    path = get_notebook_note_path(notebook, dt=dt, name=name)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

        if is_notebook_date_based(notebook):
            if dt is None:
                dt = date.today()
            # Create daily note with header
            path.write_text(
                f"---\ndate: {dt}\n---\n\n# {dt.strftime('%A, %B %d, %Y')}\n\n",
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
