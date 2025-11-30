"""Interactive todo viewer for nb."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nb.config import get_config
from nb.core.todos import set_todo_status_in_file, toggle_todo_in_file
from nb.index.todos_repo import (
    get_sorted_todos,
    update_todo_completion,
    update_todo_status,
)
from nb.models import Todo, TodoStatus
from nb.utils.dates import get_week_range


def _format_todo_source(t: Todo) -> str:
    """Format the source of a todo for display."""
    if not t.source:
        return ""

    if t.source.alias:
        # Linked file - show @alias
        return f"@{t.source.alias}"
    elif t.source.type == "inbox":
        return "inbox"
    else:
        # Regular note - show notebook/filename
        config = get_config()
        try:
            rel_path = t.source.path.relative_to(config.notes_root)
            if len(rel_path.parts) > 1:
                return f"{rel_path.parts[0]}/{rel_path.stem}"
            else:
                return rel_path.stem
        except ValueError:
            return t.source.path.stem


@dataclass
class TodoViewState:
    """State for the interactive todo viewer."""

    todos: list[Todo]
    cursor: int = 0
    show_completed: bool = False
    filter_tag: str | None = None
    filter_notebooks: list[str] | None = None
    exclude_notebooks: list[str] | None = None
    message: str | None = None

    def current_todo(self) -> Todo | None:
        """Get the currently selected todo."""
        if not self.todos or self.cursor >= len(self.todos):
            return None
        return self.todos[self.cursor]

    def move_up(self) -> None:
        """Move cursor up."""
        if self.cursor > 0:
            self.cursor -= 1

    def move_down(self) -> None:
        """Move cursor down."""
        if self.cursor < len(self.todos) - 1:
            self.cursor += 1

    def move_to_top(self) -> None:
        """Move cursor to top."""
        self.cursor = 0

    def move_to_bottom(self) -> None:
        """Move cursor to bottom."""
        if self.todos:
            self.cursor = len(self.todos) - 1

    def refresh_todos(self) -> None:
        """Reload todos from database."""
        completed = None if self.show_completed else False
        self.todos = get_sorted_todos(
            completed=completed,
            tag=self.filter_tag,
            notebooks=self.filter_notebooks,
            exclude_notebooks=self.exclude_notebooks,
        )
        # Clamp cursor
        if self.todos:
            self.cursor = min(self.cursor, len(self.todos) - 1)
        else:
            self.cursor = 0


def render_todo_table(state: TodoViewState) -> Table:
    """Render the todo list as a Rich table."""
    table = Table(
        show_header=True,
        header_style="bold",
        show_lines=False,
        expand=True,
        box=None,
    )
    table.add_column("", width=2)  # Cursor indicator
    table.add_column("", width=3)  # Checkbox
    table.add_column("Task", ratio=3)
    table.add_column("Source", width=14)
    table.add_column("Added", width=5)
    table.add_column("Due", width=8)
    table.add_column("Pri", width=3)
    table.add_column("Tags", width=12)
    table.add_column("ID", width=6)

    today = date.today()
    week_start, week_end = get_week_range()

    for i, todo in enumerate(state.todos):
        is_selected = i == state.cursor

        # Cursor indicator
        cursor = ">" if is_selected else " "
        cursor_style = "bold cyan" if is_selected else ""

        # Checkbox: [x]=completed, [^]=in-progress, [ ]=pending
        if todo.completed:
            checkbox = "[x]"
            checkbox_style = "green"
        elif todo.in_progress:
            checkbox = "[^]"
            checkbox_style = "yellow bold"
        else:
            checkbox = "[ ]"
            checkbox_style = "dim"

        # Task content
        content = todo.content
        if len(content) > 35:
            content = content[:32] + "..."
        content_style = "strikethrough" if todo.completed else ""
        if is_selected:
            content_style += " reverse"

        # Source
        source_str = _format_todo_source(todo)
        if len(source_str) > 14:
            source_str = source_str[:11] + "..."
        source_style = "blue"

        # Added (created) date
        if todo.created_date:
            added_str = todo.created_date.strftime("%m/%d")
        else:
            added_str = "-"
        added_style = "dim"

        # Due date
        if todo.due_date:
            due_str = todo.due_date.strftime("%b %d")
            if todo.due_date < today:
                due_style = "red bold"
            elif todo.due_date == today:
                due_style = "yellow bold"
            elif todo.due_date <= week_end:
                due_style = "cyan"
            else:
                due_style = "dim"
        else:
            due_str = "-"
            due_style = "dim"

        # Priority
        if todo.priority:
            pri_str = f"!{todo.priority.value}"
            pri_style = "magenta bold"
        else:
            pri_str = "-"
            pri_style = "dim"

        # Tags
        tags_str = " ".join(f"#{t}" for t in todo.tags[:2]) if todo.tags else "-"
        tags_style = "cyan" if todo.tags else "dim"

        # ID
        id_str = todo.id[:6]
        id_style = "dim"

        table.add_row(
            Text(cursor, style=cursor_style),
            Text(checkbox, style=checkbox_style),
            Text(content, style=content_style),
            Text(source_str, style=source_style),
            Text(added_str, style=added_style),
            Text(due_str, style=due_style),
            Text(pri_str, style=pri_style),
            Text(tags_str, style=tags_style),
            Text(id_str, style=id_style),
        )

    return table


def render_help_bar() -> Text:
    """Render the help bar with keyboard shortcuts."""
    help_text = Text()
    help_text.append(" j/k ", style="bold cyan")
    help_text.append("up/down  ")
    help_text.append(" space ", style="bold cyan")
    help_text.append("toggle  ")
    help_text.append(" s ", style="bold cyan")
    help_text.append("start  ")
    help_text.append(" e ", style="bold cyan")
    help_text.append("edit  ")
    help_text.append(" c ", style="bold cyan")
    help_text.append("completed  ")
    help_text.append(" q ", style="bold cyan")
    help_text.append("quit")
    return help_text


def render_view(state: TodoViewState) -> Panel:
    """Render the complete todo view."""
    from rich.console import Group

    # Build header
    header = Text()
    header.append("Todos", style="bold")
    if state.filter_tag:
        header.append(f" #{state.filter_tag}", style="cyan")
    if state.filter_notebook:
        header.append(f" @{state.filter_notebook}", style="magenta")
    if state.show_completed:
        header.append(" (showing completed)", style="dim")
    header.append(f" [{len(state.todos)} items]", style="dim")

    # Build content
    if state.todos:
        table = render_todo_table(state)
        content = table
    else:
        content = Text("No todos found.", style="dim italic")

    # Build message bar
    if state.message:
        message = Text(f"\n{state.message}", style="green")
    else:
        message = Text()

    # Build help bar
    help_bar = render_help_bar()

    return Panel(
        Group(content, message, Text(""), help_bar),
        title=str(header),
        border_style="cyan",
    )


def get_key() -> str:
    """Read a single keypress from stdin."""
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):  # Special keys
            ch2 = msvcrt.getch()
            # Arrow keys
            if ch2 == b"H":
                return "k"  # Up
            elif ch2 == b"P":
                return "j"  # Down
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
                        return "k"  # Up
                    elif ch3 == "B":
                        return "j"  # Down
                return "\x1b"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def run_interactive_todos(
        show_completed: bool = False,
        tag: str | None = None,
        notebooks: list[str] | None = None,
        exclude_notebooks: list[str] | None = None,
) -> None:
    """Run the interactive todo viewer.

    Args:
        show_completed: Whether to include completed todos.
        tag: Filter by tag.
        notebooks: Filter by notebooks.
        exclude_notebooks: Notebooks to exclude.

    """
    from nb.utils.editor import open_in_editor

    console = Console()
    config = get_config()

    # Initial state
    completed = None if show_completed else False
    todos = get_sorted_todos(
        completed=completed,
        tag=tag,
        notebooks=notebooks,
        exclude_notebooks=exclude_notebooks,
    )

    state = TodoViewState(
        todos=todos,
        show_completed=show_completed,
        filter_tag=tag,
        filter_notebooks=notebooks,
        exclude_notebooks=exclude_notebooks,
    )

    # Clear screen and hide cursor
    console.clear()

    running = True
    while running:
        # Render the view
        console.clear()
        console.print(render_view(state))

        # Clear message after showing
        state.message = None

        # Get keypress
        key = get_key()

        if key in ("q", "\x1b", "\x03"):  # q, Escape, Ctrl+C
            running = False

        elif key in ("j", "J"):  # Down
            state.move_down()

        elif key in ("k", "K"):  # Up
            state.move_up()

        elif key == "g":  # Top
            state.move_to_top()

        elif key == "G":  # Bottom
            state.move_to_bottom()

        elif key == " ":  # Toggle completion
            todo = state.current_todo()
            if todo:
                try:
                    if toggle_todo_in_file(todo.source.path, todo.line_number):
                        new_status = not todo.completed
                        update_todo_completion(todo.id, new_status)
                        action = "Completed" if new_status else "Reopened"
                        state.message = f"{action}: {todo.content[:40]}"
                        state.refresh_todos()
                except PermissionError as e:
                    state.message = f"Error: {e}"

        elif key == "e":  # Edit
            todo = state.current_todo()
            if todo:
                # Exit live mode, open editor, then refresh
                console.clear()
                open_in_editor(
                    todo.source.path,
                    line=todo.line_number,
                    editor=config.editor,
                )
                state.refresh_todos()

        elif key == "s":  # Toggle in-progress status
            todo = state.current_todo()
            if todo:
                if todo.completed:
                    state.message = "Cannot start completed todo. Reopen first."
                else:
                    try:
                        # Toggle between pending and in-progress
                        if todo.in_progress:
                            new_status = TodoStatus.PENDING
                            action = "Paused"
                        else:
                            new_status = TodoStatus.IN_PROGRESS
                            action = "Started"
                        if set_todo_status_in_file(
                                todo.source.path, todo.line_number, new_status
                        ):
                            update_todo_status(todo.id, new_status)
                            state.message = f"{action}: {todo.content[:40]}"
                            state.refresh_todos()
                    except PermissionError as e:
                        state.message = f"Error: {e}"

        elif key == "c":  # Toggle show completed
            state.show_completed = not state.show_completed
            state.refresh_todos()
            if state.show_completed:
                state.message = "Showing completed todos"
            else:
                state.message = "Hiding completed todos"

        elif key == "r":  # Refresh
            state.refresh_todos()
            state.message = "Refreshed"

    # Clean exit
    console.clear()
