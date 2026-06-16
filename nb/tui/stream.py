"""Note streaming viewer for nb.

Renders notes end-to-end to the console, optionally through a scrolling
pager (like ``less``). Supports rich markdown output (default) or plain
text (for piping or with ``--plain``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from nb.config import get_config
from nb.models import Note

if TYPE_CHECKING:
    from rich.console import Console, RenderableType


def _resolve_path(note: Note, notes_root: Path) -> Path:
    """Resolve a note's full path."""
    if note.path.is_absolute():
        return note.path
    return notes_root / note.path


def _load_body(note: Note, notes_root: Path) -> str:
    """Load a note's body content, stripping YAML frontmatter when present."""
    full_path = _resolve_path(note, notes_root)
    try:
        from nb.utils.markdown import parse_note_file

        _, body = parse_note_file(full_path)
        return body
    except Exception:
        # Fall back to raw content if frontmatter parsing fails
        try:
            return full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return "*[Error reading file]*"


def build_plain_stream(notes: list[Note], notes_root: Path) -> str:
    """Build a plain-text representation of all notes, end-to-end.

    Used when output is piped or ``--plain`` is requested.
    """
    config = get_config()
    lines: list[str] = []
    for note in notes:
        full_path = _resolve_path(note, notes_root)
        try:
            content = full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = "[Error reading file]"

        title = note.title or "Untitled"
        date_str = note.date.strftime(config.date_format) if note.date else ""
        notebook_str = f"[{note.notebook}]" if note.notebook else ""

        lines.append(f"# {title}")
        meta_line = f"{date_str} {notebook_str}".strip()
        if meta_line:
            lines.append(meta_line)
        lines.append(f"Path: {note.path}")
        lines.append("-" * 40)
        lines.append(content)
        lines.append("\n" + "=" * 60 + "\n")

    return "\n".join(lines)


def _rich_renderables(notes: list[Note], notes_root: Path) -> Iterator[RenderableType]:
    """Yield rich renderables for each note, with clear separators."""
    from rich.markdown import Markdown
    from rich.rule import Rule
    from rich.text import Text

    config = get_config()
    total = len(notes)

    for i, note in enumerate(notes):
        title = note.title or "Untitled"

        # Separator rule carrying the note title
        yield Rule(f"[bold cyan]{title}[/bold cyan]", style="cyan")

        # Metadata line: date · [notebook] · path · n/total
        meta = Text(style="dim")
        parts: list[str] = []
        if note.date:
            parts.append(note.date.strftime(config.date_format))
        if note.notebook:
            parts.append(f"[{note.notebook}]")
        parts.append(str(note.path))
        parts.append(f"{i + 1}/{total}")
        meta.append("  ".join(parts))
        yield meta
        yield Text()  # blank line

        yield Markdown(_load_body(note, notes_root))
        yield Text()  # trailing blank line


def display_note_stream(
    notes: list[Note],
    notes_root: Path,
    console: Console,
    *,
    plain: bool = False,
    use_pager: bool = True,
) -> None:
    """Render notes to the console, end-to-end with clear separators.

    Args:
        notes: Notes to display.
        notes_root: Root directory for resolving relative note paths.
        console: Rich console to render to.
        plain: If True, emit plain text instead of rich markdown.
        use_pager: If True, page the output through a scrolling pager.

    """
    if not notes:
        console.print("[yellow]No notes found.[/yellow]")
        return

    if plain:
        text = build_plain_stream(notes, notes_root)
        if use_pager:
            with console.pager():
                console.print(text, markup=False, highlight=False)
        else:
            console.print(text, markup=False, highlight=False)
        return

    renderables = _rich_renderables(notes, notes_root)
    if use_pager:
        with console.pager(styles=True):
            for renderable in renderables:
                console.print(renderable)
    else:
        for renderable in renderables:
            console.print(renderable)
