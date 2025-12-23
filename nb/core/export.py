"""Note export functionality using all2md."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from typing import Literal

SUPPORTED_FORMATS = {"pdf", "docx", "html"}

SortOrder = Literal["date", "modified", "name"]


def _check_all2md_installed() -> None:
    """Check if all2md is installed, raise helpful error if not."""
    try:
        import all2md  # noqa: F401
    except ImportError:
        raise ImportError(
            "Export requires 'all2md' package. Install with: uv pip install all2md"
        ) from None


def export_note(
    source_path: Path,
    output_path: Path,
    format: str | None = None,
) -> Path:
    """Export a note to PDF, DOCX, or HTML format.

    Args:
        source_path: Path to the markdown note
        output_path: Destination path for exported file
        format: Output format (pdf, docx, html). Inferred from extension if not specified.

    Returns:
        Path to the exported file.

    Raises:
        ValueError: If format is unsupported or cannot be inferred
        FileNotFoundError: If source doesn't exist
        ImportError: If all2md is not installed
    """
    _check_all2md_installed()
    from all2md import convert

    if not source_path.exists():
        raise FileNotFoundError(f"Note not found: {source_path}")

    # Infer format from extension if not provided
    if not format:
        format = output_path.suffix.lstrip(".").lower()

    if format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format: {format}. Use: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert using all2md
    convert(source_path, output_path, target_format=format)  # type: ignore[arg-type]

    return output_path


def _get_note_date(path: Path) -> date | None:
    """Extract date from note frontmatter or filename."""
    import re

    content = path.read_text(encoding="utf-8")

    # Try frontmatter date
    frontmatter_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if frontmatter_match:
        fm_content = frontmatter_match.group(1)
        date_match = re.search(
            r"^date:\s*(\d{4}-\d{2}-\d{2})", fm_content, re.MULTILINE
        )
        if date_match:
            try:
                return date.fromisoformat(date_match.group(1))
            except ValueError:
                pass

    # Try filename date pattern (YYYY-MM-DD)
    filename_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
    if filename_match:
        try:
            return date.fromisoformat(filename_match.group(1))
        except ValueError:
            pass

    return None


def export_notebook(
    notebook_path: Path,
    output_path: Path,
    format: str | None = None,
    sort_by: SortOrder = "date",
    reverse: bool = False,
    notes_root: Path | None = None,
) -> tuple[Path, int]:
    """Export all notes in a notebook to a single file.

    Args:
        notebook_path: Path to the notebook directory
        output_path: Destination path for exported file
        format: Output format (pdf, docx, html). Inferred from extension if not specified.
        sort_by: Sort order - "date" (frontmatter/filename), "modified", or "name"
        reverse: If True, reverse the sort order (newest/last first)
        notes_root: Notes root directory for relative path display

    Returns:
        Tuple of (output path, number of notes exported).

    Raises:
        ValueError: If format is unsupported or notebook is empty
        FileNotFoundError: If notebook doesn't exist
        ImportError: If all2md is not installed
    """
    _check_all2md_installed()
    from all2md import convert

    if not notebook_path.exists():
        raise FileNotFoundError(f"Notebook not found: {notebook_path}")

    if not notebook_path.is_dir():
        raise ValueError(f"Not a notebook (directory): {notebook_path}")

    # Infer format from extension if not provided
    if not format:
        format = output_path.suffix.lstrip(".").lower()

    if format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format: {format}. Use: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )

    # Collect all markdown files
    notes = list(notebook_path.rglob("*.md"))
    if not notes:
        raise ValueError(f"No notes found in notebook: {notebook_path}")

    # Sort notes
    if sort_by == "date":
        # Sort by date (from frontmatter or filename), with fallback to name
        def date_key(p: Path) -> tuple[date, str]:
            d = _get_note_date(p)
            return (d or date.min, p.name)

        notes.sort(key=date_key, reverse=reverse)
    elif sort_by == "modified":
        notes.sort(key=lambda p: p.stat().st_mtime, reverse=reverse)
    else:  # name
        notes.sort(key=lambda p: p.name.lower(), reverse=reverse)

    # Build combined markdown content
    combined_parts: list[str] = []
    for note_path in notes:
        content = note_path.read_text(encoding="utf-8")

        # Create separator with note info
        if notes_root:
            try:
                rel_path: str | Path = note_path.relative_to(notes_root)
            except ValueError:
                rel_path = note_path.name
        else:
            rel_path = note_path.name

        separator = f"\n\n---\n\n# {rel_path}\n\n"
        combined_parts.append(separator)
        combined_parts.append(content)

    combined_content = "".join(combined_parts)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file and convert
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(combined_content)
        tmp_path = Path(tmp.name)

    try:
        convert(tmp_path, output_path, target_format=format)  # type: ignore[arg-type]
    finally:
        tmp_path.unlink()

    return output_path, len(notes)
