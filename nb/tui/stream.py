"""Interactive note streaming viewer for nb."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from nb.models import Note


@dataclass
class StreamState:
    """State for the interactive note streamer."""

    notes: list[Note]
    notes_root: Path
    current_index: int = 0
    scroll_offset: int = 0
    terminal_height: int = 24
    content_lines: list[str] = field(default_factory=list)
    message: str | None = None

    def current_note(self) -> Note | None:
        """Get the currently displayed note."""
        if not self.notes or self.current_index >= len(self.notes):
            return None
        return self.notes[self.current_index]

    def next_note(self) -> bool:
        """Move to next note. Returns False if at end."""
        if self.current_index < len(self.notes) - 1:
            self.current_index += 1
            self.scroll_offset = 0
            self._load_content()
            return True
        return False

    def prev_note(self) -> bool:
        """Move to previous note. Returns False if at start."""
        if self.current_index > 0:
            self.current_index -= 1
            self.scroll_offset = 0
            self._load_content()
            return True
        return False

    def first_note(self) -> None:
        """Jump to first note."""
        self.current_index = 0
        self.scroll_offset = 0
        self._load_content()

    def last_note(self) -> None:
        """Jump to last note."""
        if self.notes:
            self.current_index = len(self.notes) - 1
            self.scroll_offset = 0
            self._load_content()

    def scroll_down(self, lines: int = 1) -> None:
        """Scroll down within the current note."""
        max_offset = max(0, len(self.content_lines) - self.terminal_height + 10)
        self.scroll_offset = min(self.scroll_offset + lines, max_offset)

    def scroll_up(self, lines: int = 1) -> None:
        """Scroll up within the current note."""
        self.scroll_offset = max(0, self.scroll_offset - lines)

    def scroll_to_top(self) -> None:
        """Scroll to top of current note."""
        self.scroll_offset = 0

    def scroll_to_bottom(self) -> None:
        """Scroll to bottom of current note."""
        max_offset = max(0, len(self.content_lines) - self.terminal_height + 10)
        self.scroll_offset = max_offset

    def _load_content(self) -> None:
        """Load content lines for current note."""
        note = self.current_note()
        if not note:
            self.content_lines = []
            return

        # Get the full path to the note
        if note.path.is_absolute():
            full_path = note.path
        else:
            full_path = self.notes_root / note.path

        try:
            content = full_path.read_text(encoding="utf-8")
            self.content_lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            self.content_lines = ["[Error reading file]"]


def get_key() -> str:
    """Read a single keypress from stdin."""
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):  # Special keys
            ch2 = msvcrt.getch()
            # Arrow keys
            if ch2 == b"H":
                return "up"
            elif ch2 == b"P":
                return "down"
            elif ch2 == b"I":  # Page Up
                return "pageup"
            elif ch2 == b"Q":  # Page Down
                return "pagedown"
            return ""
        return ch.decode("utf-8", errors="ignore")
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":  # Escape sequence
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "up"
                    elif ch3 == "B":
                        return "down"
                    elif ch3 == "5":
                        sys.stdin.read(1)  # consume ~
                        return "pageup"
                    elif ch3 == "6":
                        sys.stdin.read(1)  # consume ~
                        return "pagedown"
                return "\x1b"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def render_header(state: StreamState) -> Panel:
    """Render the header with note info and navigation."""
    note = state.current_note()
    if not note:
        return Panel("No notes", style="dim")

    # Build header text
    header = Text()
    header.append(note.title or "Untitled", style="bold")
    header.append("  ")
    if note.date:
        header.append(note.date.strftime("%Y-%m-%d"), style="cyan")
    if note.notebook:
        header.append(f"  [{note.notebook}]", style="magenta")

    # Navigation info
    nav = Text()
    nav.append(f"[{state.current_index + 1}/{len(state.notes)}]", style="dim")

    # Scroll indicator
    if state.content_lines:
        total_lines = len(state.content_lines)
        visible_lines = state.terminal_height - 10
        if total_lines > visible_lines:
            pct = int((state.scroll_offset / max(1, total_lines - visible_lines)) * 100)
            nav.append(f"  {pct}%", style="dim")

    header.append("  ")
    header.append_text(nav)

    return Panel(header, style="blue", padding=(0, 1))


def render_help_bar() -> Text:
    """Render the help bar with keyboard shortcuts."""
    help_text = Text()
    help_text.append(" j/k ", style="bold cyan")
    help_text.append("scroll  ")
    help_text.append(" n/N ", style="bold cyan")
    help_text.append("next/prev  ")
    help_text.append(" g/G ", style="bold cyan")
    help_text.append("top/bottom  ")
    help_text.append(" e ", style="bold cyan")
    help_text.append("edit  ")
    help_text.append(" q ", style="bold cyan")
    help_text.append("quit")
    return help_text


def render_view(state: StreamState, console: Console) -> None:
    """Render the complete streaming view."""
    console.clear()

    # Get terminal size
    state.terminal_height = console.height

    # Render header
    console.print(render_header(state))

    # Render content
    note = state.current_note()
    if note:
        # Calculate visible lines
        content_height = state.terminal_height - 8  # Header + help bar + margins

        # Get the visible portion of content
        visible_lines = state.content_lines[
            state.scroll_offset : state.scroll_offset + content_height
        ]

        if visible_lines:
            content = "\n".join(visible_lines)
            # Render as markdown for nicer formatting
            try:
                console.print(Markdown(content))
            except Exception:
                # Fall back to plain text if markdown fails
                console.print(content)
        else:
            console.print("[dim]End of note[/dim]")
    else:
        console.print("[dim]No note selected[/dim]")

    # Render message if any
    if state.message:
        console.print(f"\n[green]{state.message}[/green]")

    # Render help bar
    console.print()
    console.print(render_help_bar())


def run_note_stream(
    notes: list[Note],
    notes_root: Path,
) -> None:
    """Run the interactive note streaming viewer.

    Args:
        notes: List of notes to stream through.
        notes_root: Root directory for notes.
    """
    from nb.config import get_config
    from nb.utils.editor import open_in_editor

    if not notes:
        Console().print("[yellow]No notes found.[/yellow]")
        return

    console = Console()
    config = get_config()

    state = StreamState(notes=notes, notes_root=notes_root)
    state._load_content()

    running = True
    while running:
        # Render the view
        render_view(state, console)
        state.message = None

        # Get keypress
        key = get_key()

        if key in ("q", "\x1b", "\x03"):  # q, Escape, Ctrl+C
            running = False

        elif key in ("j", "down"):  # Scroll down
            state.scroll_down()

        elif key in ("k", "up"):  # Scroll up
            state.scroll_up()

        elif key == "d" or key == "pagedown":  # Half page down
            state.scroll_down(state.terminal_height // 2)

        elif key == "u" or key == "pageup":  # Half page up
            state.scroll_up(state.terminal_height // 2)

        elif key == "n":  # Next note
            if not state.next_note():
                state.message = "Last note"

        elif key in ("N", "p"):  # Previous note
            if not state.prev_note():
                state.message = "First note"

        elif key == "g":  # First note / top of current note
            if state.scroll_offset > 0:
                state.scroll_to_top()
            else:
                state.first_note()

        elif key == "G":  # Last note / bottom of current note
            max_offset = max(0, len(state.content_lines) - state.terminal_height + 10)
            if state.scroll_offset < max_offset:
                state.scroll_to_bottom()
            else:
                state.last_note()

        elif key == "e":  # Edit current note
            note = state.current_note()
            if note:
                console.clear()
                if note.path.is_absolute():
                    full_path = note.path
                else:
                    full_path = notes_root / note.path
                open_in_editor(full_path, editor=config.editor)
                state._load_content()

        elif key == " ":  # Space = page down
            state.scroll_down(state.terminal_height // 2)

    # Clean exit
    console.clear()
