"""Interactive todo review TUI for nb."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nb.config import get_config
from nb.core.todos import (
    delete_todo_from_file,
    toggle_todo_in_file,
    update_todo_due_date,
)
from nb.index.todos_repo import (
    delete_todo,
    get_sorted_todos,
    query_todos,
    update_todo_completion,
)
from nb.models import Todo
from nb.tui.todos import get_key
from nb.utils.dates import get_week_range


@dataclass
class ReviewStats:
    """Statistics from a review session."""

    total: int = 0
    completed: int = 0
    rescheduled: int = 0
    deleted: int = 0
    skipped: int = 0


@dataclass
class ReviewState:
    """State for the interactive review session."""

    todos: list[Todo]
    cursor: int = 0
    page: int = 0
    page_size: int = 8
    stats: ReviewStats = field(default_factory=ReviewStats)
    message: str | None = None

    def __post_init__(self):
        self.stats.total = len(self.todos)

    def current_todo(self) -> Todo | None:
        """Get the currently selected todo."""
        visible = self.visible_todos()
        if not visible or self.cursor >= len(visible):
            return None
        return visible[self.cursor]

    def visible_todos(self) -> list[Todo]:
        """Get todos on the current page."""
        start = self.page * self.page_size
        end = start + self.page_size
        return self.todos[start:end]

    def move_up(self) -> None:
        """Move cursor up."""
        if self.cursor > 0:
            self.cursor -= 1

    def move_down(self) -> None:
        """Move cursor down."""
        visible = self.visible_todos()
        if self.cursor < len(visible) - 1:
            self.cursor += 1

    def next_page(self) -> bool:
        """Move to next page. Returns False if already at last page."""
        if self.page < self.total_pages() - 1:
            self.page += 1
            self.cursor = 0
            return True
        return False

    def prev_page(self) -> bool:
        """Move to previous page. Returns False if already at first page."""
        if self.page > 0:
            self.page -= 1
            self.cursor = 0
            return True
        return False

    def remove_current(self) -> None:
        """Remove current todo from list after action."""
        visible = self.visible_todos()
        if not visible:
            return

        # Calculate absolute index
        abs_idx = self.page * self.page_size + self.cursor
        if abs_idx < len(self.todos):
            self.todos.pop(abs_idx)

        # Adjust cursor and page if needed
        new_visible = self.visible_todos()
        if not new_visible and self.page > 0:
            self.page -= 1
            new_visible = self.visible_todos()

        if new_visible:
            self.cursor = min(self.cursor, len(new_visible) - 1)
        else:
            self.cursor = 0

    def total_pages(self) -> int:
        """Get total number of pages."""
        if not self.todos:
            return 1
        return (len(self.todos) + self.page_size - 1) // self.page_size

    def remaining(self) -> int:
        """Get count of remaining todos to review."""
        return len(self.todos)

    def processed(self) -> int:
        """Get count of processed todos."""
        return self.stats.completed + self.stats.rescheduled + self.stats.deleted


def _format_todo_source(t: Todo) -> str:
    """Format the source of a todo for display."""
    if not t.source:
        return ""

    if t.source.alias:
        return f"@{t.source.alias}"
    elif t.source.type == "inbox":
        return "inbox"
    else:
        config = get_config()
        try:
            rel_path = t.source.path.relative_to(config.notes_root)
            if len(rel_path.parts) > 1:
                return f"{rel_path.parts[0]}/{rel_path.stem}"
            else:
                return rel_path.stem
        except ValueError:
            return t.source.path.stem


def _get_overdue_days(due_date: date | None) -> int | None:
    """Calculate days overdue (negative if in future)."""
    if not due_date:
        return None
    return (date.today() - due_date).days


def render_todo_row(todo: Todo, is_selected: bool, idx: int) -> tuple:
    """Render a single todo row for the table."""
    today = date.today()
    _week_start, week_end = get_week_range()

    # Cursor indicator
    cursor = ">" if is_selected else " "
    cursor_style = "bold cyan" if is_selected else ""

    # Checkbox
    if todo.completed:
        checkbox = "[x]"
        checkbox_style = "green"
    elif todo.in_progress:
        checkbox = "[^]"
        checkbox_style = "yellow bold"
    else:
        checkbox = "[ ]"
        checkbox_style = "dim"

    # Content
    content = todo.content
    if len(content) > 40:
        content = content[:37] + "..."
    content_style = ""
    if is_selected:
        content_style = "reverse"

    # Source
    source_str = _format_todo_source(todo)
    if len(source_str) > 18:
        source_str = source_str[:15] + "..."

    # Due date with overdue indicator
    due_str = ""
    due_style = "dim"
    if todo.due_date:
        overdue_days = _get_overdue_days(todo.due_date)
        if overdue_days and overdue_days > 0:
            due_str = f"{overdue_days}d overdue"
            due_style = "red bold"
        elif todo.due_date == today:
            due_str = "today"
            due_style = "yellow bold"
        elif todo.due_date <= week_end:
            due_str = todo.due_date.strftime("%a")
            due_style = "cyan"
        else:
            due_str = todo.due_date.strftime("%b %d")
            due_style = "dim"

    # Priority
    pri_str = ""
    if todo.priority:
        pri_str = f"!{todo.priority.value}"

    return (
        Text(cursor, style=cursor_style),
        Text(checkbox, style=checkbox_style),
        Text(content, style=content_style),
        Text(source_str, style="blue"),
        Text(due_str, style=due_style),
        Text(pri_str, style="magenta bold" if pri_str else ""),
    )


def render_help_bar() -> Text:
    """Render the help bar with action keys."""
    help_text = Text()
    help_text.append(" [d]", style="bold cyan")
    help_text.append("one ")
    help_text.append("[t]", style="bold cyan")
    help_text.append("omorrow ")
    help_text.append("[f]", style="bold cyan")
    help_text.append("riday ")
    help_text.append("[F]", style="bold cyan")
    help_text.append(" next Fri ")
    help_text.append("[w]", style="bold cyan")
    help_text.append("eek ")
    help_text.append("[n]", style="bold cyan")
    help_text.append("ext month")
    return help_text


def render_help_bar_2() -> Text:
    """Render the second help bar with remaining actions."""
    help_text = Text()
    help_text.append(" [e]", style="bold cyan")
    help_text.append("dit ")
    help_text.append("[s]", style="bold cyan")
    help_text.append("kip ")
    help_text.append("[x]", style="bold cyan")
    help_text.append(" delete ")
    help_text.append("[q]", style="bold cyan")
    help_text.append("uit")
    return help_text


def render_nav_bar() -> Text:
    """Render navigation help."""
    nav_text = Text()
    nav_text.append(" [j/k]", style="bold dim")
    nav_text.append(" up/down  ")
    nav_text.append("[/]", style="bold dim")
    nav_text.append(" page  ")
    return nav_text


def render_progress_bar(state: ReviewState) -> Text:
    """Render the progress indicator."""
    processed = state.processed()
    total = state.stats.total
    remaining = state.remaining()

    progress_text = Text()

    # Simple text progress
    progress_text.append(f"Progress: {processed}/{total}", style="dim")
    if state.stats.completed > 0:
        progress_text.append(f" | Done: {state.stats.completed}", style="green")
    if state.stats.rescheduled > 0:
        progress_text.append(f" | Rescheduled: {state.stats.rescheduled}", style="cyan")
    if state.stats.deleted > 0:
        progress_text.append(f" | Deleted: {state.stats.deleted}", style="red")
    if remaining > 0:
        progress_text.append(f" | Remaining: {remaining}", style="yellow")

    return progress_text


def render_review_view(state: ReviewState) -> Panel:
    """Render the complete review interface."""
    visible = state.visible_todos()

    # Build header
    header = Text()
    header.append("Review", style="bold")
    header.append(f" [{state.remaining()} items]", style="dim")
    if state.total_pages() > 1:
        header.append(f" | Page {state.page + 1}/{state.total_pages()}", style="dim")

    # Build table
    if visible:
        table = Table(
            show_header=False,
            show_lines=False,
            expand=True,
            box=None,
            padding=(0, 1),
        )
        table.add_column("", width=2)  # Cursor
        table.add_column("", width=3)  # Checkbox
        table.add_column("Task", ratio=3)  # Content
        table.add_column("Source", width=18)
        table.add_column("Due", width=12)
        table.add_column("Pri", width=3)

        for i, todo in enumerate(visible):
            is_selected = i == state.cursor
            row = render_todo_row(todo, is_selected, i)
            table.add_row(*row)

        content = table
    else:
        content = Text("No todos to review!", style="green italic")

    # Build message bar
    if state.message:
        message = Text(f"\n{state.message}", style="green")
    else:
        message = Text()

    # Build bottom section
    help_bar = render_help_bar()
    help_bar_2 = render_help_bar_2()
    nav_bar = render_nav_bar()
    progress = render_progress_bar(state)

    return Panel(
        Group(
            content,
            message,
            Text(""),
            help_bar,
            help_bar_2,
            nav_bar,
            Text(""),
            progress,
        ),
        title=str(header),
        border_style="cyan",
    )


def render_summary(stats: ReviewStats) -> None:
    """Render the end-of-session summary."""
    console = Console()
    console.print()
    console.print("[bold]Review complete![/bold]")
    console.print()

    if stats.completed > 0:
        console.print(f"  [green]Completed:[/green]   {stats.completed}")
    if stats.rescheduled > 0:
        console.print(f"  [cyan]Rescheduled:[/cyan] {stats.rescheduled}")
    if stats.deleted > 0:
        console.print(f"  [red]Deleted:[/red]     {stats.deleted}")
    if stats.skipped > 0:
        console.print(f"  [dim]Skipped:[/dim]     {stats.skipped}")

    remaining = stats.total - stats.completed - stats.rescheduled - stats.deleted
    if remaining > 0:
        console.print()
        console.print(f"  [yellow]{remaining} todos still need attention[/yellow]")
    console.print()


def get_this_friday() -> date:
    """Get the date of this Friday (or next Friday if today is Friday)."""
    today = date.today()
    days_ahead = 4 - today.weekday()  # 4 = Friday
    if days_ahead <= 0:
        # Today is Friday or later, go to next Friday
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def get_next_friday() -> date:
    """Get the date of next week's Friday."""
    this_friday = get_this_friday()
    return this_friday + timedelta(days=7)


def get_next_monday() -> date:
    """Get the date of next Monday."""
    today = date.today()
    days_ahead = 7 - today.weekday()  # 0 = Monday
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def get_first_of_next_month() -> date:
    """Get the first day of next month."""
    today = date.today()
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def run_review(
    scope: str = "daily",
    tag: str | None = None,
    notebooks: list[str] | None = None,
    notes: list[str] | None = None,
    exclude_notebooks: list[str] | None = None,
) -> ReviewStats:
    """Run interactive review session.

    Args:
        scope: Review scope - "daily" (overdue + today), "weekly" (+ this week + no date), "all"
        tag: Filter by tag
        notebooks: Filter by notebooks
        notes: Filter by note paths
        exclude_notebooks: Notebooks to exclude

    Returns:
        ReviewStats with session statistics.

    """
    from nb.index.scanner import index_all_notes
    from nb.utils.editor import open_in_editor

    console = Console()
    config = get_config()

    # Ensure index is up to date
    index_all_notes(index_vectors=False)

    # Query todos based on scope
    today = date.today()
    _week_start, week_end = get_week_range()

    # Don't exclude note-level todo_exclude when filtering by specific notebooks/notes
    exclude_note_excluded = not notebooks and not notes

    if scope == "all":
        # All incomplete todos
        todos = get_sorted_todos(
            completed=False,
            tag=tag,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
    elif scope == "weekly":
        # Overdue + this week + no due date
        todos = get_sorted_todos(
            completed=False,
            due_end=week_end,
            tag=tag,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        # Also include no-due-date items
        no_date_todos = query_todos(
            completed=False,
            tag=tag,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        no_date_todos = [t for t in no_date_todos if t.due_date is None]
        # Merge, avoiding duplicates
        existing_ids = {t.id for t in todos}
        for t in no_date_todos:
            if t.id not in existing_ids:
                todos.append(t)
    else:
        # Daily: overdue + due today only
        todos = query_todos(
            completed=False,
            overdue=True,
            tag=tag,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        # Add due today
        today_todos = query_todos(
            completed=False,
            due_start=today,
            due_end=today,
            tag=tag,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        existing_ids = {t.id for t in todos}
        for t in today_todos:
            if t.id not in existing_ids:
                todos.append(t)

    if not todos:
        console.print("[green]Nothing to review! All caught up.[/green]")
        return ReviewStats()

    # Sort: overdue first (oldest), then by due date
    def sort_key(t: Todo) -> tuple:
        if t.due_date is None:
            return (2, date.max)  # No date last
        elif t.due_date < today:
            return (0, t.due_date)  # Overdue first, oldest first
        else:
            return (1, t.due_date)  # Future dates

    todos.sort(key=sort_key)

    state = ReviewState(todos=list(todos))

    console.clear()

    running = True
    while running:
        # Render the view
        console.clear()
        console.print(render_review_view(state))

        # Clear message after showing
        state.message = None

        # Check if we're done
        if not state.todos:
            state.message = "All done!"
            console.clear()
            console.print(render_review_view(state))
            break

        # Get keypress
        key = get_key()

        if key in ("q", "\x1b", "\x03"):  # q, Escape, Ctrl+C
            running = False

        elif key in ("j", "J"):  # Down
            state.move_down()

        elif key in ("k", "K"):  # Up
            state.move_up()

        elif key == "]" or key == "pagedown":  # Next page
            if not state.next_page():
                state.message = "Last page"

        elif key == "[" or key == "pageup":  # Previous page
            if not state.prev_page():
                state.message = "First page"

        elif key == "d":  # Mark done
            todo = state.current_todo()
            if todo:
                try:
                    actual_line = toggle_todo_in_file(
                        todo.source.path,
                        todo.line_number,
                        expected_content=todo.content,
                    )
                    if actual_line is not None:
                        update_todo_completion(todo.id, True)
                        state.stats.completed += 1
                        state.message = f"Completed: {todo.content[:30]}"
                        state.remove_current()
                except PermissionError as e:
                    state.message = f"Error: {e}"

        elif key == "t":  # Reschedule to tomorrow
            todo = state.current_todo()
            if todo:
                try:
                    tomorrow = today + timedelta(days=1)
                    actual_line = update_todo_due_date(
                        todo.source.path,
                        todo.line_number,
                        tomorrow,
                        expected_content=todo.content,
                    )
                    if actual_line is not None:
                        state.stats.rescheduled += 1
                        state.message = f"Rescheduled to tomorrow: {todo.content[:25]}"
                        state.remove_current()
                except PermissionError as e:
                    state.message = f"Error: {e}"

        elif key == "f":  # Reschedule to this Friday
            todo = state.current_todo()
            if todo:
                try:
                    this_friday = get_this_friday()
                    actual_line = update_todo_due_date(
                        todo.source.path,
                        todo.line_number,
                        this_friday,
                        expected_content=todo.content,
                    )
                    if actual_line is not None:
                        state.stats.rescheduled += 1
                        state.message = f"Rescheduled to {this_friday.strftime('%a %b %d')}: {todo.content[:20]}"
                        state.remove_current()
                except PermissionError as e:
                    state.message = f"Error: {e}"

        elif key == "F":  # Reschedule to next Friday
            todo = state.current_todo()
            if todo:
                try:
                    next_friday = get_next_friday()
                    actual_line = update_todo_due_date(
                        todo.source.path,
                        todo.line_number,
                        next_friday,
                        expected_content=todo.content,
                    )
                    if actual_line is not None:
                        state.stats.rescheduled += 1
                        state.message = f"Rescheduled to {next_friday.strftime('%a %b %d')}: {todo.content[:20]}"
                        state.remove_current()
                except PermissionError as e:
                    state.message = f"Error: {e}"

        elif key == "w":  # Reschedule to next week
            todo = state.current_todo()
            if todo:
                try:
                    next_monday = get_next_monday()
                    actual_line = update_todo_due_date(
                        todo.source.path,
                        todo.line_number,
                        next_monday,
                        expected_content=todo.content,
                    )
                    if actual_line is not None:
                        state.stats.rescheduled += 1
                        state.message = f"Rescheduled to {next_monday.strftime('%b %d')}: {todo.content[:20]}"
                        state.remove_current()
                except PermissionError as e:
                    state.message = f"Error: {e}"

        elif key == "n":  # Reschedule to next month
            todo = state.current_todo()
            if todo:
                try:
                    next_month = get_first_of_next_month()
                    actual_line = update_todo_due_date(
                        todo.source.path,
                        todo.line_number,
                        next_month,
                        expected_content=todo.content,
                    )
                    if actual_line is not None:
                        state.stats.rescheduled += 1
                        state.message = f"Rescheduled to {next_month.strftime('%b %d')}: {todo.content[:20]}"
                        state.remove_current()
                except PermissionError as e:
                    state.message = f"Error: {e}"

        elif key == "e":  # Edit
            todo = state.current_todo()
            if todo:
                console.clear()
                open_in_editor(
                    todo.source.path,
                    line=todo.line_number,
                    editor=config.editor,
                )
                # Refresh todos after editing
                state.message = "Refreshed after edit"
                # Note: The todo might have changed, so we just continue
                # without removing it from the list

        elif key == "s":  # Skip
            todo = state.current_todo()
            if todo:
                state.stats.skipped += 1
                # Just move to next item without removing
                if state.cursor < len(state.visible_todos()) - 1:
                    state.move_down()
                elif state.page < state.total_pages() - 1:
                    state.next_page()
                state.message = "Skipped"

        elif key == "x":  # Delete
            todo = state.current_todo()
            if todo:
                try:
                    actual_line = delete_todo_from_file(
                        todo.source.path,
                        todo.line_number,
                        expected_content=todo.content,
                    )
                    if actual_line is not None:
                        delete_todo(todo.id)
                        state.stats.deleted += 1
                        state.message = f"Deleted: {todo.content[:30]}"
                        state.remove_current()
                except PermissionError as e:
                    state.message = f"Error: {e}"

    # Show summary
    console.clear()
    render_summary(state.stats)

    return state.stats
