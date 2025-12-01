"""Shared utilities for CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from nb.config import get_config, init_config

if TYPE_CHECKING:
    from nb.models import Todo

# Main console for stdout (user-facing output)
console = Console(highlight=False)

# Stderr console for progress indicators (doesn't interfere with piped output)
stderr_console = Console(file=sys.stderr, highlight=False)

# Maximum stdin size (1MB) to prevent accidental huge input
MAX_STDIN_SIZE = 1024 * 1024


def get_stdin_content() -> str | None:
    """Read content from stdin if available (non-blocking check).

    Returns:
        Content from stdin stripped of leading/trailing whitespace,
        or None if stdin is a TTY (interactive terminal) or empty.

    Raises:
        SystemExit: If stdin contains binary data or exceeds size limit.
    """
    # If stdin is a TTY, user is typing interactively - no piped input
    if sys.stdin.isatty():
        return None

    try:
        content = sys.stdin.read()
    except UnicodeDecodeError:
        console.print("[red]Error: stdin appears to contain binary data.[/red]")
        console.print("[dim]Only text content can be piped to nb.[/dim]")
        raise SystemExit(1) from None

    if not content:
        return None

    # Check for binary content (null bytes are a strong indicator)
    if "\x00" in content:
        console.print("[red]Error: stdin appears to contain binary data.[/red]")
        console.print("[dim]Only text content can be piped to nb.[/dim]")
        raise SystemExit(1)

    # Check size limit
    if len(content) > MAX_STDIN_SIZE:
        console.print(
            f"[red]Error: stdin content exceeds size limit ({MAX_STDIN_SIZE // 1024}KB).[/red]"
        )
        console.print("[dim]Consider saving to a file and linking it instead.[/dim]")
        raise SystemExit(1)

    stripped = content.strip()
    return stripped if stripped else None


@contextmanager
def spinner(description: str) -> Iterator[Callable[[str], None]]:
    """Context manager for a spinner with status updates.

    Usage:
        with spinner("Indexing notes") as update:
            for item in items:
                update(f"Processing {item}")
                process(item)

    Args:
        description: Initial description to show next to spinner.

    Yields:
        A function to update the status text.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=stderr_console,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=None)

        def update(new_description: str) -> None:
            progress.update(task, description=new_description)

        yield update


@contextmanager
def progress_bar(
    description: str,
    total: int,
    show_count: bool = True,
) -> Iterator[Callable[[int], None]]:
    """Context manager for a progress bar.

    Usage:
        with progress_bar("Indexing", total=100) as advance:
            for item in items:
                process(item)
                advance()  # or advance(5) to advance by 5

    Args:
        description: Description to show.
        total: Total number of items.
        show_count: Whether to show M/N count.

    Yields:
        A function to advance progress (default by 1).
    """
    columns = [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
    ]
    if show_count:
        columns.append(MofNCompleteColumn())
    columns.append(TimeElapsedColumn())

    with Progress(
        *columns,
        console=stderr_console,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=total)

        def advance(n: int = 1) -> None:
            progress.advance(task, n)

        yield advance


class MultiStageProgress:
    """Progress indicator for multi-stage operations.

    Usage:
        with MultiStageProgress() as mp:
            with mp.stage("Scanning files"):
                scan_files()

            with mp.stage("Indexing", total=100) as advance:
                for item in items:
                    index(item)
                    advance()

            with mp.stage("Syncing"):
                sync()
    """

    def __init__(self) -> None:
        from rich.progress import TaskID

        self._progress: Progress | None = None
        self._current_task: TaskID | None = None

    def __enter__(self) -> MultiStageProgress:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=stderr_console,
            transient=True,
        )
        self._progress.start()
        return self

    def __exit__(self, *args) -> None:
        if self._progress:
            self._progress.stop()

    @contextmanager
    def stage(
        self, description: str, total: int | None = None
    ) -> Iterator[Callable[[int], None]]:
        """Start a new stage in the multi-stage operation.

        Args:
            description: Stage description.
            total: If provided, shows a progress bar. Otherwise shows spinner.

        Yields:
            Function to advance progress (if total provided).
        """
        if not self._progress:
            raise RuntimeError("MultiStageProgress must be used as context manager")

        # Remove previous task if any
        if self._current_task is not None:
            self._progress.remove_task(self._current_task)

        self._current_task = self._progress.add_task(description, total=total)

        def advance(n: int = 1) -> None:
            if self._current_task is not None:
                self._progress.advance(self._current_task, n)

        try:
            yield advance
        finally:
            # Mark complete if it had a total
            if total is not None and self._current_task is not None:
                self._progress.update(self._current_task, completed=total)


def print_note(path: Path) -> None:
    """Print a note's content to console with markdown formatting."""
    from rich.markdown import Markdown

    if not path.exists():
        console.print(f"[red]Note not found: {path}[/red]")
        raise SystemExit(1)

    content = path.read_text(encoding="utf-8")

    # Print header with path info
    console.print(f"[dim]─── {path.name} ───[/dim]\n")

    # Render markdown
    md = Markdown(content)
    console.print(md)
    console.print()


def ensure_setup() -> None:
    """Ensure nb is set up (creates config and directories on first run)."""
    config = get_config()
    if not config.nb_dir.exists():
        init_config(config.notes_root)


def find_todo(todo_id: str):
    """Find a todo by ID or ID prefix."""
    from nb.index.db import get_db
    from nb.index.todos_repo import get_todo_by_id

    # First try exact match
    t = get_todo_by_id(todo_id)
    if t:
        return t

    # Try prefix match
    db = get_db()
    rows = db.fetchall(
        "SELECT id FROM todos WHERE id LIKE ?",
        (f"{todo_id}%",),
    )

    if len(rows) == 1:
        return get_todo_by_id(rows[0]["id"])
    elif len(rows) > 1:
        console.print(
            f"[yellow]Multiple todos match '{todo_id}'. Be more specific.[/yellow]"
        )
        for row in rows[:5]:
            t = get_todo_by_id(row["id"])
            if t:
                console.print(f"  {row['id'][:6]}: {t.content[:50]}")
        return None

    return None


def get_notebook_display_info(notebook_name: str) -> tuple[str, str | None]:
    """Get display color and icon for a notebook.

    Args:
        notebook_name: Name of the notebook

    Returns:
        Tuple of (color, icon). Color defaults to "magenta", icon may be None.
    """
    config = get_config()
    nb_config = config.get_notebook(notebook_name)
    if nb_config:
        color = nb_config.color or "magenta"
        icon = nb_config.icon
    else:
        color = "magenta"
        icon = None
    return color, icon


def resolve_notebook(name: str, interactive: bool = True) -> str | None:
    """Resolve a notebook name, with fuzzy matching if no exact match.

    Args:
        name: The notebook name to resolve.
        interactive: If True, prompt user to select from fuzzy matches.

    Returns:
        Resolved notebook name, or None if not found/cancelled.

    """
    from nb.utils.fuzzy import resolve_with_fuzzy

    config = get_config()

    # Get all notebook names
    notebook_names = [nb.name for nb in config.notebooks]

    return resolve_with_fuzzy(
        name,
        notebook_names,
        item_type="notebook",
        interactive=interactive,
    )


def resolve_note_for_todo_filter(
    note_ref: str,
    notebook: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve a note reference for todo filtering.

    This handles:
    - Linked note aliases (e.g., "nbtodo" resolves to the linked file path)
    - Linked todo aliases (e.g., "mytodos" for linked todo files)
    - Regular notes (e.g., "notebook/note-name" or just "note-name")
    - Section syntax (e.g., "note::Section" or "notebook/note::Section")

    Args:
        note_ref: The note reference (name, path, or linked alias).
            Can include ::section for section filtering.
        notebook: Optional notebook to narrow search.

    Returns:
        Tuple of (path_pattern, section_pattern) where:
        - path_pattern is suitable for use in query_todos notes filter
        - section_pattern is the section to filter by (partial match)
        Either or both may be None if not found/specified.

    """
    from nb.core.aliases import get_note_by_alias
    from nb.core.links import (
        get_linked_file,
        get_linked_note,
        get_linked_note_in_notebook,
    )
    from nb.utils.hashing import normalize_path

    config = get_config()

    # Parse section from note_ref (e.g., "notebook/note::Section")
    section_pattern = None
    if "::" in note_ref:
        note_ref, section_pattern = note_ref.rsplit("::", 1)

    # Strip @ prefix if present
    check_ref = note_ref[1:] if note_ref.startswith("@") else note_ref

    # Check if it matches a note alias (from nb alias command)
    alias_path = get_note_by_alias(check_ref)
    if alias_path and alias_path.exists():
        try:
            rel_path = alias_path.relative_to(config.notes_root)
            return (normalize_path(rel_path), section_pattern)
        except ValueError:
            return (normalize_path(alias_path), section_pattern)

    # If notebook specified, check for linked note in that notebook first
    if notebook:
        linked = get_linked_note_in_notebook(notebook, check_ref)
        if linked:
            return (normalize_path(linked.path), section_pattern)

    # Check if it matches a linked note alias (from config or DB)
    linked_note = get_linked_note(check_ref)
    if linked_note:
        return (normalize_path(linked_note.path), section_pattern)

    # Also check linked todo files (from config or DB)
    linked_file = get_linked_file(check_ref)
    if linked_file:
        return (normalize_path(linked_file.path), section_pattern)

    # Try to resolve as a regular note (only if no @ prefix)
    if not note_ref.startswith("@"):
        resolved_path = resolve_note(note_ref, notebook=notebook, interactive=True)
        if resolved_path:
            # Return the path relative to notes_root for LIKE matching
            try:
                rel_path = resolved_path.relative_to(config.notes_root)
                return (normalize_path(rel_path), section_pattern)
            except ValueError:
                # External path, return full normalized path
                return (normalize_path(resolved_path), section_pattern)

    return (None, section_pattern)


def resolve_note(
    note_ref: str,
    notebook: str | None = None,
    interactive: bool = True,
) -> Path | None:
    """Resolve a note reference, with fuzzy matching if no exact match.

    Args:
        note_ref: The note reference (name or path) to resolve.
        notebook: Optional notebook to search within.
        interactive: If True, prompt user to select from fuzzy matches.

    Returns:
        Resolved note Path, or None if not found/cancelled.

    """
    from nb.core.notebooks import get_notebook_notes_with_linked
    from nb.core.notes import list_notes
    from nb.utils.fuzzy import prompt_fuzzy_selection_with_context, resolve_with_fuzzy

    config = get_config()

    # Get candidate notes
    # get_notebook_notes_with_linked returns tuples (path, is_linked, alias)
    # list_notes returns just paths
    note_paths: list[Path] = []
    if notebook:
        notes_with_linked = get_notebook_notes_with_linked(notebook)
        note_paths = [path for path, _, _ in notes_with_linked]
    else:
        note_paths = list_notes(notes_root=config.notes_root)

    if not note_paths:
        return None

    # Build a mapping from display names to paths
    # Use stem (filename without extension) as the display name
    name_to_path: dict[str, Path] = {}
    # Also build a context mapping for better display in fuzzy selection
    name_to_context: dict[str, str] = {}

    for note_path in note_paths:
        # Use the stem as the primary lookup key
        stem = note_path.stem

        # Determine notebook context for this note
        note_notebook = None
        try:
            rel = note_path.relative_to(config.notes_root)
            if len(rel.parts) > 1:
                note_notebook = rel.parts[0]
        except ValueError:
            pass

        if stem not in name_to_path:
            name_to_path[stem] = note_path
            # Store context showing the full notebook/note path
            if note_notebook:
                name_to_context[stem] = f"[dim]{note_notebook}/[/dim]{stem}"
            else:
                name_to_context[stem] = stem
        else:
            # Stem already exists, add with full path to disambiguate
            if note_notebook:
                full_ref = f"{note_notebook}/{stem}"
                if full_ref not in name_to_path:
                    name_to_path[full_ref] = note_path
                    name_to_context[full_ref] = f"[dim]{note_notebook}/[/dim]{stem}"

        # Also add notebook/stem for direct lookup
        if note_notebook:
            full_ref = f"{note_notebook}/{stem}"
            if full_ref not in name_to_path:
                name_to_path[full_ref] = note_path
                name_to_context[full_ref] = f"[dim]{note_notebook}/[/dim]{stem}"

    # Try exact match first (case-insensitive)
    note_ref_lower = note_ref.lower()
    for name, path in name_to_path.items():
        if name.lower() == note_ref_lower:
            return path

    # Try fuzzy matching with context display
    if interactive:
        resolved_name = prompt_fuzzy_selection_with_context(
            note_ref,
            list(name_to_path.keys()),
            name_to_context,
            item_type="note",
        )
    else:
        resolved_name = resolve_with_fuzzy(
            note_ref,
            list(name_to_path.keys()),
            item_type="note",
            interactive=False,
        )

    if resolved_name:
        return name_to_path.get(resolved_name)

    return None


def get_display_path(path: Path) -> Path:
    """Get a path suitable for display (relative to notes_root if possible).

    Args:
        path: Absolute or relative path to a note.

    Returns:
        Path relative to notes_root if possible, otherwise the original path.
    """
    config = get_config()
    try:
        return path.relative_to(config.notes_root)
    except ValueError:
        return path


def ensure_note_path(path: str | Path, notes_root: Path | None = None) -> Path:
    """Ensure path has .md extension and resolve to absolute path.

    Args:
        path: Path string or Path object (can be relative to notes_root).
        notes_root: Override notes root directory.

    Returns:
        Absolute path with .md extension.
    """
    if notes_root is None:
        notes_root = get_config().notes_root

    if isinstance(path, str):
        path = Path(path)

    if not path.suffix:
        path = path.with_suffix(".md")

    if not path.is_absolute():
        path = notes_root / path

    return path


def open_or_show_note(path: Path, show: bool = False) -> None:
    """Open a note in editor or print to console.

    Args:
        path: Absolute path to the note.
        show: If True, print note to console instead of opening editor.
    """
    from nb.core.notes import open_note

    if show:
        print_note(path)
    else:
        rel_path = get_display_path(path)
        console.print(f"[dim]Opening {rel_path}...[/dim]")
        open_note(path)


def resolve_note_ref(
    note_ref: str,
    notebook: str | None = None,
    ensure_exists: bool = True,
    create_if_date_based: bool = False,
    interactive: bool = True,
) -> Path | None:
    """Unified note resolution handling all cases.

    Resolves a note reference to an absolute path, handling:
    - Note aliases (created with 'nb alias')
    - Linked note aliases (from 'nb link')
    - notebook/note format parsing
    - Date-based notebooks (e.g., "friday" -> daily note for Friday)
    - Fuzzy matching for note names
    - Path with/without .md extension

    Args:
        note_ref: The note reference. Can be:
            - A note alias (e.g., "myalias")
            - A linked note alias (e.g., "nbtodo")
            - A notebook/note format (e.g., "daily/friday")
            - A date string for date-based notebooks (e.g., "friday", "nov 26")
            - A path relative to notes_root (e.g., "projects/ideas")
        notebook: Optional notebook context. If provided:
            - For date-based notebooks, note_ref is parsed as a date.
            - For non-date-based notebooks, note_ref is treated as a note name.
        ensure_exists: If True, return None for non-existent notes.
            If False, return the resolved path even if the file doesn't exist.
        create_if_date_based: If True and notebook is date-based, create the note
            if it doesn't exist.
        interactive: If True, prompt user to select from fuzzy matches.

    Returns:
        Absolute path to the note, or None if not found.
    """
    from nb.core.aliases import get_note_by_alias
    from nb.core.links import get_linked_note_in_notebook
    from nb.core.notebooks import (
        ensure_notebook_note,
        get_notebook_note_path,
        is_notebook_date_based,
    )
    from nb.utils.dates import parse_fuzzy_date

    config = get_config()

    # Parse notebook/note format if present
    if "/" in note_ref and not notebook:
        parts = note_ref.split("/", 1)
        notebook = parts[0]
        note_ref = parts[1]

    # Check if note_ref is a note alias (only if no notebook specified)
    if not notebook:
        alias_path = get_note_by_alias(note_ref)
        if alias_path and alias_path.exists():
            return alias_path

    # Resolve notebook with fuzzy matching if specified
    if notebook:
        nb_config = config.get_notebook(notebook)
        if not nb_config:
            resolved = resolve_notebook(notebook, interactive=interactive)
            if resolved:
                notebook = resolved
            else:
                return None

        # Check if note_ref matches a linked note alias in this notebook
        linked = get_linked_note_in_notebook(notebook, note_ref)
        if linked:
            return linked.path

        # Handle date-based vs non-date-based notebooks
        if is_notebook_date_based(notebook):
            parsed = parse_fuzzy_date(note_ref)
            if parsed:
                if create_if_date_based:
                    return ensure_notebook_note(notebook, dt=parsed)
                else:
                    note_path = get_notebook_note_path(notebook, dt=parsed)
                    if ensure_exists and not note_path.exists():
                        return None
                    return note_path
            else:
                console.print(f"[red]Could not parse date: {note_ref}[/red]")
                return None
        else:
            # Non-date-based notebook: treat note_ref as a name
            try:
                note_path = get_notebook_note_path(notebook, name=note_ref)
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
                return None

            if not note_path.exists():
                # Try fuzzy matching
                resolved_path = resolve_note(
                    note_ref, notebook=notebook, interactive=interactive
                )
                if resolved_path:
                    # Convert to absolute if needed
                    if not resolved_path.is_absolute():
                        resolved_path = config.notes_root / resolved_path
                    return resolved_path
                if ensure_exists:
                    return None
            return note_path

    # No notebook specified - check various possibilities

    # First check if it's a path to an existing note
    note_path = ensure_note_path(note_ref, notes_root=config.notes_root)
    if note_path.exists():
        return note_path

    # Try to parse as a date (for daily notes)
    parsed = parse_fuzzy_date(note_ref)
    if parsed:
        from nb.core.notes import ensure_daily_note, get_daily_note_path

        if create_if_date_based:
            return ensure_daily_note(parsed)
        else:
            daily_path = get_daily_note_path(parsed)
            if ensure_exists and not daily_path.exists():
                return None
            return daily_path

    # Try fuzzy matching across all notes
    resolved_path = resolve_note(note_ref, interactive=interactive)
    if resolved_path:
        # Convert to absolute if needed
        if not resolved_path.is_absolute():
            resolved_path = config.notes_root / resolved_path
        return resolved_path

    return None


def resolve_attachment_target(
    target: str | None,
) -> tuple[Path | None, Todo | None]:
    """Resolve an attachment target to either a note path or todo.

    Args:
        target: Target string. Can be:
            - None (defaults to today's daily note)
            - A todo ID (8+ chars, no slashes)
            - A note path (relative to notes_root)

    Returns:
        Tuple of (note_path, todo). One will be set, the other None.
        If target is a todo, returns (None, todo).
        If target is a note, returns (note_path, None).
        If target is None, returns (today's daily note path, None).
        If target not found, returns (None, None).
    """
    from datetime import date

    from nb.core.notes import ensure_daily_note

    config = get_config()

    if target is None:
        # Default to today's note
        return (ensure_daily_note(date.today()), None)

    # Check if it looks like a todo ID (8+ chars, no path separators)
    if len(target) >= 8 and "/" not in target and "\\" not in target:
        t = find_todo(target)
        if t:
            return (None, t)
        # Fall through to try as note path

    # Treat as note path
    note_path = ensure_note_path(target, notes_root=config.notes_root)

    if not note_path.exists():
        console.print(f"[red]Note not found: {target}[/red]")
        return (None, None)

    return (note_path, None)
