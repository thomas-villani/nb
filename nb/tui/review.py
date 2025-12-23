"""Interactive todo review TUI for nb using Wijjit."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, timedelta

from wijjit import Wijjit
from wijjit.elements.modal import ConfirmDialog, TextInputDialog
from wijjit.layout.bounds import Bounds

from nb.config import get_config
from nb.core.todos import (
    delete_todo_from_file,
    set_todo_status_in_file,
    toggle_todo_in_file,
    update_todo_due_date,
)
from nb.index.todos_repo import (
    delete_todo as delete_todo_from_db,
)
from nb.index.todos_repo import (
    get_sorted_todos,
    query_todos,
    update_todo_completion,
    update_todo_status,
)
from nb.models import Todo, TodoStatus
from nb.tui.wijjit_utils import (
    format_due_date_review,
    format_todo_source,
    get_first_of_next_month,
    get_next_monday,
    get_this_friday,
    truncate,
)
from nb.utils.dates import get_week_range, parse_fuzzy_datetime_future


@dataclass
class ReviewStats:
    """Statistics from a review session."""

    total: int = 0
    completed: int = 0
    rescheduled: int = 0
    deleted: int = 0
    skipped: int = 0


def run_review(
    scope: str = "daily",
    tag: str | None = None,
    priority: int | None = None,
    notebooks: list[str] | None = None,
    notes: list[str] | None = None,
    exclude_notebooks: list[str] | None = None,
    include_no_due_date: bool = False,
) -> ReviewStats:
    """Run interactive review session.

    Args:
        scope: Review scope - "daily" (overdue + today), "weekly" (+ this week + no date),
               or "all" (all incomplete todos)
        tag: Filter by tag
        priority: Filter by priority (1=high, 2=medium, 3=low)
        notebooks: Filter by notebooks
        notes: Filter by note paths
        exclude_notebooks: Notebooks to exclude
        include_no_due_date: Also include todos without a due date

    Returns:
        ReviewStats with session statistics.

    """
    from rich.console import Console

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
        todos = get_sorted_todos(
            completed=False,
            tag=tag,
            priority=priority,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
    elif scope == "weekly":
        todos = get_sorted_todos(
            completed=False,
            due_end=week_end,
            tag=tag,
            priority=priority,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        # Also include no-due-date items
        no_date_todos = query_todos(
            completed=False,
            tag=tag,
            priority=priority,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        no_date_todos = [t for t in no_date_todos if t.due_date is None]
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
            priority=priority,
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
            priority=priority,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        existing_ids = {t.id for t in todos}
        for t in today_todos:
            if t.id not in existing_ids:
                todos.append(t)

        # Optionally include no-due-date items
        if include_no_due_date:
            no_date_todos = query_todos(
                completed=False,
                tag=tag,
                priority=priority,
                notebooks=notebooks,
                notes=notes,
                exclude_notebooks=exclude_notebooks,
                exclude_note_excluded=exclude_note_excluded,
            )
            no_date_todos = [t for t in no_date_todos if t.due_date is None]
            existing_ids = {t.id for t in todos}
            for t in no_date_todos:
                if t.id not in existing_ids:
                    todos.append(t)

    if not todos:
        console.print("[green]Nothing to review! All caught up.[/green]")
        return ReviewStats()

    # Sort: overdue first (oldest), then by due date
    def sort_key(t: Todo) -> tuple:
        due = t.due_date_only
        if due is None:
            return (2, date.max)
        elif due < today:
            return (0, due)
        else:
            return (1, due)

    todos.sort(key=sort_key)

    # Initialize stats
    stats = ReviewStats(total=len(todos))

    # Initialize app with state
    app = Wijjit(
        initial_state={
            "todos": list(todos),
            "page": 0,
            "page_size": 8,
            "cursor": 0,
            "stats_completed": 0,
            "stats_rescheduled": 0,
            "stats_deleted": 0,
            "stats_skipped": 0,
            "stats_total": len(todos),
            "message": "",
        }
    )

    def get_current_todo() -> Todo | None:
        """Get the currently highlighted todo from the Select element.

        Uses the highlight state key (synced on navigation) to get the
        currently highlighted item, rather than requiring Enter/Space to select.
        """
        todos = app.state.get("todos", [])
        if not todos:
            return None

        # Use highlighted index (updates on arrow key navigation)
        highlighted_index = app.state.get("selected_todo:highlight")
        if highlighted_index is not None and 0 <= highlighted_index < len(todos):
            return todos[highlighted_index]

        # Fall back to first todo
        return todos[0]

    def remove_current():
        """Remove current todo from list after action."""
        todos = app.state.get("todos", [])
        if not todos:
            return

        # Get the highlighted index to find which item to remove
        highlighted_index = app.state.get("selected_todo:highlight", 0)
        if highlighted_index is None or highlighted_index >= len(todos):
            highlighted_index = 0

        # Remove the highlighted todo
        if 0 <= highlighted_index < len(todos):
            removed_id = todos[highlighted_index].id
            new_todos = [t for t in todos if t.id != removed_id]
            app.state["todos"] = new_todos

            # Keep highlight at same position (or last item if at end)
            if new_todos:
                new_highlight = min(highlighted_index, len(new_todos) - 1)
                app.state["selected_todo:highlight"] = new_highlight
            else:
                app.state["selected_todo:highlight"] = 0
                app.quit()  # Exit when done

    @app.view("review", default=True)
    def review_view():
        """Main review interface."""

        def get_data():
            """Compute fresh data on each render."""
            todos = app.state.get("todos", [])

            # Format todos as options for Select element
            # Each option is {"value": todo_id, "label": display_string}
            todo_options = []

            # Column widths for alignment
            content_width = 60
            source_width = 18

            for todo in todos:
                due_str, _due_style = format_due_date_review(todo)
                source_str = format_todo_source(todo)

                # Checkbox marker
                if todo.completed:
                    marker = "[x]"
                elif todo.in_progress:
                    marker = "[^]"
                else:
                    marker = "[ ]"

                # Build label with fixed-width columns for alignment
                content = truncate(todo.content, content_width)
                source = truncate(source_str, source_width) if source_str else ""
                due = due_str if due_str else ""

                # Format with fixed widths: marker content | source | due
                label = f"{marker} {content:<{content_width}}  {source:<{source_width}}  {due}"

                todo_options.append(
                    {
                        "value": todo.id,
                        "label": label,
                    }
                )

            # Stats
            completed = app.state.get("stats_completed", 0)
            rescheduled = app.state.get("stats_rescheduled", 0)
            deleted = app.state.get("stats_deleted", 0)
            total = app.state.get("stats_total", 0)
            processed = completed + rescheduled + deleted

            remaining = len(todos)
            return {
                "todo_options": todo_options,
                "remaining": remaining,
                "frame_title": f"Review [{remaining} items]",
                "processed": processed,
                "total": total,
                "completed": completed,
                "rescheduled": rescheduled,
                "deleted": deleted,
            }

        return {
            "template": """
{% frame border_style="rounded" title=frame_title %}
  {% vstack spacing=1 padding=1 %}

    {# Todo list as Select element #}
    {% if todo_options %}
      {% select id="selected_todo" options=todo_options visible_rows=10 width=105 border_style="single" title="Todos" %}{% endselect %}
    {% else %}
      {% text dim=true %}All done!{% endtext %}
    {% endif %}

    {# Help text #}
    {% text dim=true %}[d]one [s]tart [t]omorrow [f]riday [m]onday [w]eek [n]month [c]ustom [e]dit [k]skip [x]del [q]uit{% endtext %}

    {# Message bar #}
    {% if state.message %}
      {% text %}{{ state.message }}{% endtext %}
    {% endif %}

    {# Progress #}
    {% text dim=true %}Progress: {{ processed }}/{{ total }} | Done: {{ completed }} | Rescheduled: {{ rescheduled }}{% endtext %}

  {% endvstack %}
{% endframe %}
            """,
            "data": get_data,
        }

    # --- Actions (Select element handles navigation via up/down keys) ---

    @app.on_key("d")
    def mark_done(event):
        """Mark current todo as done (with confirmation)."""
        todo = get_current_todo()
        if not todo:
            return

        def on_confirm():
            try:
                actual_line = toggle_todo_in_file(
                    todo.source.path,
                    todo.line_number,
                    expected_content=todo.content,
                )
                if actual_line is not None:
                    update_todo_completion(todo.id, True)
                    app.state["stats_completed"] = (
                        app.state.get("stats_completed", 0) + 1
                    )
                    stats.completed += 1
                    app.state["message"] = f"Completed: {todo.content[:30]}"
                    remove_current()
            except PermissionError as e:
                app.state["message"] = f"Error: {e}"
            app.state["_refresh"] = True

        def on_cancel():
            app.state["message"] = "Cancelled"
            app.state["_refresh"] = True

        display_text = truncate(todo.content, 40)
        dialog = ConfirmDialog(
            title="Mark Done",
            message=f'Mark as complete?\n\n"{display_text}"',
            on_confirm=on_confirm,
            on_cancel=on_cancel,
            confirm_label="Done",
            cancel_label="Cancel",
            width=50,
            height=11,
        )

        # Show the modal
        overlay = app.show_modal(dialog)

        # Set close callback
        def close_dialog():
            app.overlay_manager.pop(overlay)
            app.state["_refresh"] = True

        dialog.close_callback = close_dialog

    @app.on_key("s")
    def mark_started(event):
        """Mark current todo as started (in progress) and remove from list."""
        todo = get_current_todo()
        if not todo:
            return

        try:
            actual_line = set_todo_status_in_file(
                todo.source.path,
                todo.line_number,
                TodoStatus.IN_PROGRESS,
                expected_content=todo.content,
            )
            if actual_line is not None:
                update_todo_status(todo.id, TodoStatus.IN_PROGRESS)
                app.state["message"] = f"Started: {todo.content[:30]}"
                remove_current()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("t")
    def reschedule_tomorrow(event):
        """Reschedule to tomorrow."""
        todo = get_current_todo()
        if not todo:
            return

        try:
            tomorrow = date.today() + timedelta(days=1)
            actual_line = update_todo_due_date(
                todo.source.path,
                todo.line_number,
                tomorrow,
                expected_content=todo.content,
            )
            if actual_line is not None:
                app.state["stats_rescheduled"] = (
                    app.state.get("stats_rescheduled", 0) + 1
                )
                stats.rescheduled += 1
                app.state["message"] = f"Rescheduled to tomorrow: {todo.content[:25]}"
                remove_current()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("f")
    def reschedule_this_friday(event):
        """Reschedule to this Friday."""
        todo = get_current_todo()
        if not todo:
            return

        try:
            this_friday = get_this_friday()
            actual_line = update_todo_due_date(
                todo.source.path,
                todo.line_number,
                this_friday,
                expected_content=todo.content,
            )
            if actual_line is not None:
                app.state["stats_rescheduled"] = (
                    app.state.get("stats_rescheduled", 0) + 1
                )
                stats.rescheduled += 1
                app.state["message"] = (
                    f"Rescheduled to {this_friday.strftime('%a %b %d')}: {todo.content[:20]}"
                )
                remove_current()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("m")
    def reschedule_next_monday(event):
        """Reschedule to next Monday."""
        todo = get_current_todo()
        if not todo:
            return

        try:
            next_monday = get_next_monday()
            actual_line = update_todo_due_date(
                todo.source.path,
                todo.line_number,
                next_monday,
                expected_content=todo.content,
            )
            if actual_line is not None:
                app.state["stats_rescheduled"] = (
                    app.state.get("stats_rescheduled", 0) + 1
                )
                stats.rescheduled += 1
                app.state["message"] = (
                    f"Rescheduled to {next_monday.strftime('%a %b %d')}: {todo.content[:20]}"
                )
                remove_current()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("w")
    def reschedule_next_week(event):
        """Reschedule to next Monday."""
        todo = get_current_todo()
        if not todo:
            return

        try:
            next_monday = get_next_monday()
            actual_line = update_todo_due_date(
                todo.source.path,
                todo.line_number,
                next_monday,
                expected_content=todo.content,
            )
            if actual_line is not None:
                app.state["stats_rescheduled"] = (
                    app.state.get("stats_rescheduled", 0) + 1
                )
                stats.rescheduled += 1
                app.state["message"] = (
                    f"Rescheduled to {next_monday.strftime('%b %d')}: {todo.content[:20]}"
                )
                remove_current()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("n")
    def reschedule_next_month(event):
        """Reschedule to first of next month."""
        todo = get_current_todo()
        if not todo:
            return

        try:
            next_month = get_first_of_next_month()
            actual_line = update_todo_due_date(
                todo.source.path,
                todo.line_number,
                next_month,
                expected_content=todo.content,
            )
            if actual_line is not None:
                app.state["stats_rescheduled"] = (
                    app.state.get("stats_rescheduled", 0) + 1
                )
                stats.rescheduled += 1
                app.state["message"] = (
                    f"Rescheduled to {next_month.strftime('%b %d')}: {todo.content[:20]}"
                )
                remove_current()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("c")
    def reschedule_custom_date(event):
        """Reschedule to a custom date via input dialog."""
        todo = get_current_todo()
        if not todo:
            return

        def on_submit(date_str: str):
            """Handle date input submission."""
            if not date_str.strip():
                app.state["message"] = "No date entered"
                app.state["_refresh"] = True
                return

            # Parse the date using fuzzy datetime parsing
            parsed_date = parse_fuzzy_datetime_future(date_str.strip())
            if not parsed_date:
                app.state["message"] = f"Could not parse date: {date_str}"
                app.state["_refresh"] = True
                return

            try:
                actual_line = update_todo_due_date(
                    todo.source.path,
                    todo.line_number,
                    parsed_date,
                    expected_content=todo.content,
                )
                if actual_line is not None:
                    app.state["stats_rescheduled"] = (
                        app.state.get("stats_rescheduled", 0) + 1
                    )
                    stats.rescheduled += 1
                    app.state["message"] = (
                        f"Rescheduled to {parsed_date.strftime('%b %d')}: {todo.content[:20]}"
                    )
                    remove_current()
                else:
                    app.state["message"] = "Failed to update due date"
            except PermissionError as e:
                app.state["message"] = f"Error: {e}"
            app.state["_refresh"] = True

        def on_cancel():
            """Handle dialog cancellation."""
            app.state["message"] = "Date entry cancelled"
            app.state["_refresh"] = True

        dialog = TextInputDialog(
            title="Set Due Date",
            prompt=f"Enter due date for: {truncate(todo.content, 40)}",
            placeholder="e.g. tomorrow, friday, Dec 25, 2024-01-15",
            on_submit=on_submit,
            on_cancel=on_cancel,
            submit_label="Set",
            cancel_label="Cancel",
            width=60,
            height=12,
            input_width=40,
        )

        # Center the dialog
        term_size = shutil.get_terminal_size()
        x = (term_size.columns - dialog.width) // 2
        y = (term_size.lines - dialog.height) // 2
        dialog.bounds = Bounds(x=x, y=y, width=dialog.width, height=dialog.height)

        # Show the modal
        overlay = app.show_modal(dialog)

        # Set close callback
        def close_dialog():
            app.overlay_manager.pop(overlay)
            app.state["_refresh"] = True

        dialog.close_callback = close_dialog

    @app.on_key("e")
    def edit_todo(event):
        """Edit in external editor."""
        todo = get_current_todo()
        if not todo:
            return

        open_in_editor(
            todo.source.path,
            line=todo.line_number,
            editor=config.editor,
        )
        app.state["message"] = "Refreshed after edit"

    @app.on_key("k")
    def skip_todo(event):
        """Skip current todo and remove from list."""
        todo = get_current_todo()
        if not todo:
            return

        app.state["stats_skipped"] = app.state.get("stats_skipped", 0) + 1
        stats.skipped += 1
        app.state["message"] = f"Skipped: {todo.content[:30]}"
        remove_current()

    @app.on_key("x")
    def delete_todo(event):
        """Delete current todo (with confirmation)."""
        todo = get_current_todo()
        if not todo:
            return

        def on_confirm():
            try:
                actual_line = delete_todo_from_file(
                    todo.source.path,
                    todo.line_number,
                    expected_content=todo.content,
                )
                if actual_line is not None:
                    delete_todo_from_db(todo.id)
                    app.state["stats_deleted"] = app.state.get("stats_deleted", 0) + 1
                    stats.deleted += 1
                    app.state["message"] = f"Deleted: {todo.content[:30]}"
                    remove_current()
            except PermissionError as e:
                app.state["message"] = f"Error: {e}"
            app.state["_refresh"] = True

        def on_cancel():
            app.state["message"] = "Cancelled"
            app.state["_refresh"] = True

        display_text = truncate(todo.content, 40)
        dialog = ConfirmDialog(
            title="Delete Todo",
            message=f'Delete this todo?\n\n"{display_text}"',
            on_confirm=on_confirm,
            on_cancel=on_cancel,
            confirm_label="Delete",
            cancel_label="Cancel",
            width=50,
            height=11,
        )

        # Show the modal
        overlay = app.show_modal(dialog)

        # Set close callback
        def close_dialog():
            app.overlay_manager.pop(overlay)
            app.state["_refresh"] = True

        dialog.close_callback = close_dialog

    @app.on_key("q")
    def quit_app(event):
        """Quit the review session."""
        app.quit()

    # Run the app
    app.run()

    # Print summary to stdout after app closes
    remaining = len(app.state.get("todos", []))
    if (
        stats.completed > 0
        or stats.rescheduled > 0
        or stats.deleted > 0
        or stats.skipped > 0
    ):
        console.print()
        console.print("[bold]Review Complete![/bold]")
        if stats.completed > 0:
            console.print(f"  [green]Completed:[/green]   {stats.completed}")
        if stats.rescheduled > 0:
            console.print(f"  [cyan]Rescheduled:[/cyan] {stats.rescheduled}")
        if stats.deleted > 0:
            console.print(f"  [red]Deleted:[/red]     {stats.deleted}")
        if stats.skipped > 0:
            console.print(f"  [yellow]Skipped:[/yellow]     {stats.skipped}")
        if remaining > 0:
            console.print()
            console.print(f"  [dim]{remaining} todos still need attention[/dim]")

    return stats
