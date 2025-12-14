"""Interactive todo review TUI for nb using Wijjit."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, timedelta

from wijjit import Wijjit
from wijjit.elements.modal import TextInputDialog
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
) -> ReviewStats:
    """Run interactive review session.

    Args:
        scope: Review scope - "daily" (overdue + today), "weekly" (+ this week + no date),
               "all", or "no_due_date" (only todos without due dates)
        tag: Filter by tag
        priority: Filter by priority (1=high, 2=medium, 3=low)
        notebooks: Filter by notebooks
        notes: Filter by note paths
        exclude_notebooks: Notebooks to exclude

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
    elif scope == "no_due_date":
        # Only todos with no due date
        todos = query_todos(
            completed=False,
            tag=tag,
            priority=priority,
            notebooks=notebooks,
            notes=notes,
            exclude_notebooks=exclude_notebooks,
            exclude_note_excluded=exclude_note_excluded,
        )
        todos = [t for t in todos if t.due_date is None]
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
        """Get the currently selected todo from the Select element."""
        selected_id = app.state.get("selected_todo")
        if not selected_id:
            # If nothing selected, get first todo
            todos = app.state.get("todos", [])
            return todos[0] if todos else None

        todos = app.state.get("todos", [])
        for todo in todos:
            if todo.id == selected_id:
                return todo
        return None

    def remove_current():
        """Remove current todo from list after action."""
        selected_id = app.state.get("selected_todo")
        todos = app.state.get("todos", [])

        # Find and remove the selected todo
        new_todos = [t for t in todos if t.id != selected_id]
        app.state["todos"] = new_todos

        # Select next item if available
        if new_todos:
            app.state["selected_todo"] = new_todos[0].id
        else:
            app.state["selected_todo"] = None
            app.navigate("summary")

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
    {% text dim=true %}[d]one [s]tart [t]omorrow [f]riday [m]onday [w]eek [n]month [D]ate [e]dit [k]skip [x]del [q]uit{% endtext %}

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

    @app.view("summary")
    def summary_view():
        """End-of-session summary."""

        def get_data():
            completed = app.state.get("stats_completed", 0)
            rescheduled = app.state.get("stats_rescheduled", 0)
            deleted = app.state.get("stats_deleted", 0)
            skipped = app.state.get("stats_skipped", 0)
            total = app.state.get("stats_total", 0)
            remaining = total - completed - rescheduled - deleted

            return {
                "completed": completed,
                "rescheduled": rescheduled,
                "deleted": deleted,
                "skipped": skipped,
                "remaining": remaining,
            }

        return {
            "template": """
{% frame border_style="double" title="Review Complete!" width=50 height=15 %}
  {% vstack spacing=1 padding=2 %}

    {% if completed > 0 %}
      {% text %}Completed:   {{ completed }}{% endtext %}
    {% endif %}
    {% if rescheduled > 0 %}
      {% text %}Rescheduled: {{ rescheduled }}{% endtext %}
    {% endif %}
    {% if deleted > 0 %}
      {% text %}Deleted:     {{ deleted }}{% endtext %}
    {% endif %}
    {% if skipped > 0 %}
      {% text %}Skipped:     {{ skipped }}{% endtext %}
    {% endif %}

    {% if remaining > 0 %}
      {% text %}{% endtext %}
      {% text %}{{ remaining }} todos still need attention{% endtext %}
    {% endif %}

    {% text %}{% endtext %}
    {% button action="close" %}Close{% endbutton %}

  {% endvstack %}
{% endframe %}
            """,
            "data": get_data,
        }

    # --- Actions (Select element handles navigation via up/down keys) ---

    @app.on_key("d")
    def mark_done(event):
        """Mark current todo as done."""
        todo = get_current_todo()
        if not todo:
            return

        try:
            actual_line = toggle_todo_in_file(
                todo.source.path,
                todo.line_number,
                expected_content=todo.content,
            )
            if actual_line is not None:
                update_todo_completion(todo.id, True)
                app.state["stats_completed"] = app.state.get("stats_completed", 0) + 1
                stats.completed += 1
                app.state["message"] = f"Completed: {todo.content[:30]}"
                remove_current()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("s")
    def mark_started(event):
        """Mark current todo as started (in progress)."""
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
                # Update the todo in the list to show [^] marker
                todos = app.state.get("todos", [])
                for t in todos:
                    if t.id == todo.id:
                        t.status = TodoStatus.IN_PROGRESS
                        break
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

    @app.on_key("D")
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
        """Skip current todo (Select handles navigation, just track the skip)."""
        todo = get_current_todo()
        if not todo:
            return

        app.state["stats_skipped"] = app.state.get("stats_skipped", 0) + 1
        stats.skipped += 1
        app.state["message"] = f"Skipped: {todo.content[:30]} (use arrows to navigate)"

    @app.on_key("x")
    def delete_todo(event):
        """Delete current todo."""
        todo = get_current_todo()
        if not todo:
            return

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

    @app.on_key("q")
    def quit_app(event):
        """Quit and show summary."""
        app.navigate("summary")

    @app.on_action("close")
    def close_summary(event):
        """Close the summary view."""
        app.quit()

    # Run the app
    app.run()

    return stats
