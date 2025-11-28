"""Notebook operations for nb."""

from __future__ import annotations

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
