"""Interactive todo manager for nb using Wijjit."""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

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
from nb.index.db import get_db
from nb.index.todos_repo import (
    delete_todo as delete_todo_from_db,
)
from nb.index.todos_repo import (
    get_sorted_todos,
    update_todo_completion,
    update_todo_status,
)
from nb.models import Todo, TodoStatus
from nb.tui.wijjit_utils import (
    format_due_date_review,
    format_todo_source,
    truncate,
)
from nb.utils.dates import parse_fuzzy_datetime_future


def get_notebooks_with_todos(
    include_completed: bool = False,
    exclude_notebooks: list[str] | None = None,
) -> list[str]:
    """Get notebooks that have at least one todo matching filters.

    Args:
        include_completed: If True, include notebooks with only completed todos.
        exclude_notebooks: Notebooks to exclude from the list.

    Returns:
        List of notebook names that have matching todos.

    """
    db = get_db()
    conditions = ["project IS NOT NULL"]
    params: list = []

    if not include_completed:
        conditions.append("status != 'completed'")

    if exclude_notebooks:
        placeholders = ", ".join("?" for _ in exclude_notebooks)
        conditions.append(f"project NOT IN ({placeholders})")
        params.extend(exclude_notebooks)

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT DISTINCT project
        FROM todos
        WHERE {where_clause}
        ORDER BY project
    """
    rows = db.execute(query, tuple(params)).fetchall()
    return [row[0] for row in rows if row[0]]


def get_notes_with_todos(
    notebook: str | None = None,
    include_completed: bool = False,
    exclude_notebooks: list[str] | None = None,
) -> list[dict]:
    """Get notes that have todos matching filters.

    Args:
        notebook: Filter by notebook name, or None for all.
        include_completed: If True, include notes with only completed todos.
        exclude_notebooks: Notebooks to exclude (only when notebook is None).

    Returns:
        List of dicts with 'path' and 'display' keys.
        The 'path' value uses forward slashes for consistency with database storage.

    """
    db = get_db()
    config = get_config()

    conditions = ["source_path IS NOT NULL"]
    params: list = []

    if notebook:
        conditions.append("project = ?")
        params.append(notebook)
    elif exclude_notebooks:
        # Only apply exclude_notebooks when viewing all notebooks
        placeholders = ", ".join("?" for _ in exclude_notebooks)
        conditions.append(f"(project IS NULL OR project NOT IN ({placeholders}))")
        params.extend(exclude_notebooks)

    if not include_completed:
        conditions.append("status != 'completed'")

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT DISTINCT source_path
        FROM todos
        WHERE {where_clause}
        ORDER BY source_path DESC
    """
    rows = db.execute(query, tuple(params)).fetchall()

    notes = []
    for row in rows:
        # source_path is already stored with forward slashes in the DB
        source_path = row[0]
        path = Path(source_path)
        try:
            rel_path = path.relative_to(config.notes_root)
            # Show as "notebook/filename" or just "filename"
            if len(rel_path.parts) > 1:
                display = f"{rel_path.parts[0]}/{rel_path.stem}"
            else:
                display = rel_path.stem
        except ValueError:
            display = path.stem

        # Keep the path as stored in DB (with forward slashes) for consistent filtering
        notes.append({"path": source_path, "display": display})

    return notes


def get_all_tags() -> list[str]:
    """Get all unique tags from todos.

    Returns:
        List of tag names.

    """
    db = get_db()
    query = "SELECT DISTINCT tag FROM todo_tags ORDER BY tag"
    rows = db.execute(query).fetchall()
    return [row[0] for row in rows]


def run_interactive_todos(
    show_completed: bool = False,
    tag: str | None = None,
    notebooks: list[str] | None = None,
    exclude_notebooks: list[str] | None = None,
) -> None:
    """Run the interactive todo manager.

    Args:
        show_completed: Whether to include completed todos.
        tag: Filter by tag.
        notebooks: Filter by notebooks (from CLI).
        exclude_notebooks: Notebooks to exclude.

    """
    # Initial notebook filter (use CLI filter if provided)
    initial_notebook = notebooks[0] if notebooks and len(notebooks) == 1 else "All"

    # Load initial data with filters
    def load_notebooks_filtered() -> list[str]:
        """Load notebooks that have any todos (for navigation)."""
        # Show ALL notebooks with any todos - no exclusions for navigation
        # The exclude_notebooks filter only applies to the todos list
        return get_notebooks_with_todos(
            include_completed=True,  # Show notebooks with any todos
            exclude_notebooks=None,  # Don't exclude any notebooks from navigation
        )

    def load_todos_filtered(
        notebook_filter: str | None,
        note_filter: str | None,
        tag_filter: str | None,
        include_completed: bool,
    ) -> list[Todo]:
        """Load todos with all filters applied."""
        completed = None if include_completed else False
        nb_list = (
            [notebook_filter] if notebook_filter and notebook_filter != "All" else None
        )
        note_list = [note_filter] if note_filter and note_filter != "All" else None

        # Only exclude note-excluded todos when viewing "All" notebooks/notes.
        # When a specific notebook or note is selected, show all todos
        # (including those from excluded notes) since user explicitly navigated there.
        exclude_excluded = notebook_filter == "All" and note_filter == "All"

        # Only apply exclude_notebooks when viewing "All" notebooks.
        # When a specific notebook is selected, don't exclude it even if it's
        # in the exclude list (user explicitly navigated there).
        effective_exclude_notebooks = (
            exclude_notebooks if notebook_filter == "All" else None
        )

        return get_sorted_todos(
            completed=completed,
            tag=tag_filter,
            notebooks=nb_list,
            notes=note_list,
            exclude_notebooks=effective_exclude_notebooks,
            exclude_note_excluded=exclude_excluded,
        )

    def load_notes_for_notebook(notebook_filter: str | None) -> list[dict]:
        """Load notes that have any todos for the selected notebook (for navigation)."""
        nb = notebook_filter if notebook_filter != "All" else None
        # Show ALL notes with any todos - no exclusions for navigation
        # The exclude_notebooks filter only applies to the todos list
        return get_notes_with_todos(
            notebook=nb,
            include_completed=True,  # Show notes with any todos
            exclude_notebooks=None,  # Don't exclude any notebooks from navigation
        )

    # Initialize state with filters applied
    initial_notebooks = load_notebooks_filtered()
    initial_notes = load_notes_for_notebook(initial_notebook)
    initial_todos = load_todos_filtered(initial_notebook, "All", tag, show_completed)

    app = Wijjit(
        initial_state={
            "todos": initial_todos,
            "notes_with_todos": initial_notes,
            "all_notebooks": initial_notebooks,
            "selected_notebook": initial_notebook,
            "selected_note": "All",
            "selected_tag": tag,
            "show_completed": show_completed,
            "status_filter": "all" if show_completed else "incomplete",
            "edit_mode": False,
            "edit_content": "",
            "edit_note_path": None,
            "message": "Ready. Tab to navigate between panels.",
        }
    )

    # --- Helper Functions ---

    def refresh_notebooks():
        """Reload notebooks list (shows all notebooks with any todos)."""
        app.state["all_notebooks"] = load_notebooks_filtered()

    def refresh_todos():
        """Reload todos with current filters."""
        notebook = app.state.get("selected_notebook", "All")
        note = app.state.get("selected_note", "All")
        tag_filter = app.state.get("selected_tag")
        include_completed = app.state.get("show_completed", False)
        todos = load_todos_filtered(notebook, note, tag_filter, include_completed)
        app.state["todos"] = todos

    def refresh_notes():
        """Reload notes list for current notebook (shows all notes with any todos)."""
        notebook = app.state.get("selected_notebook", "All")
        app.state["notes_with_todos"] = load_notes_for_notebook(notebook)
        app.state["selected_note"] = "All"

    def get_selected_todo() -> Todo | None:
        """Get the currently selected todo from the todo_list Select."""
        todo_id = app.state.get("todo_list")
        if not todo_id:
            return None
        for todo in app.state.get("todos", []):
            if todo.id == todo_id:
                return todo
        return None

    def remove_current_todo():
        """Remove the currently selected todo from the list."""
        todo_id = app.state.get("todo_list")
        if todo_id:
            todos = app.state.get("todos", [])
            app.state["todos"] = [t for t in todos if t.id != todo_id]

    def show_centered_dialog(dialog, width: int, height: int):
        """Show a dialog centered on screen."""
        term_size = shutil.get_terminal_size()
        x = (term_size.columns - width) // 2
        y = (term_size.lines - height) // 2
        dialog.bounds = Bounds(x=x, y=y, width=width, height=height)
        overlay = app.show_modal(dialog)

        def close():
            app.overlay_manager.pop(overlay)
            app.state["_refresh"] = True

        dialog.close_callback = close
        return overlay

    # --- Main View ---

    @app.view("main", default=True)
    def main_view():
        """Main todo manager view."""

        def get_data():
            """Compute fresh data on each render."""
            todos = app.state.get("todos", [])
            notes_with_todos = app.state.get("notes_with_todos", [])
            all_notebooks = app.state.get("all_notebooks", [])
            selected_tag = app.state.get("selected_tag")
            edit_mode = app.state.get("edit_mode", False)
            edit_content = app.state.get("edit_content", "")

            # Build notebook options (filter out any empty names)
            notebook_options = [{"value": "All", "label": "All"}]
            for nb in all_notebooks:
                if nb:  # Skip empty notebook names
                    notebook_options.append({"value": nb, "label": nb})

            # Build note options (filter out any empty display names)
            note_options = [{"value": "All", "label": "All"}]
            for note in notes_with_todos:
                display = note.get("display", "")
                if display:  # Skip notes with empty display names
                    note_options.append(
                        {"value": note["path"], "label": truncate(display, 16)}
                    )

            # Build todo options with aligned columns
            content_width = 50
            source_width = 15
            todo_options = []

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

                # Build label with fixed-width columns
                content = truncate(todo.content or "", content_width)
                source = truncate(source_str, source_width) if source_str else ""
                due = due_str if due_str else ""

                label = f"{marker} {content:<{content_width}}  {source:<{source_width}}  {due}"

                todo_options.append({"value": todo.id, "label": label})

            # Ensure there's always at least one option
            if not todo_options:
                todo_options = [{"value": "_empty", "label": "(No todos to display)"}]

            # Item count text
            todo_count = len(todos)
            item_count_text = f"{todo_count} items" if todo_count != 1 else "1 item"

            return {
                "notebook_options": notebook_options,
                "note_options": note_options,
                "todo_options": todo_options,
                "selected_tag": selected_tag,
                "edit_mode": edit_mode,
                "edit_content": edit_content,
                "item_count_text": item_count_text,
            }

        return {
            "template": """
{% frame border_style="rounded" title="Todo Manager" height="fill" %}
  {% vstack spacing=1 padding=1 %}

    {# Main content area with panels #}
    {% hstack spacing=1 %}

      {# Left column - Notebooks and Notes #}
      {% vstack width=20 spacing=0 %}
        {% select id="notebook_filter" options=notebook_options visible_rows=6 width=18 border_style="single" title="Notebooks" %}{% endselect %}
        {% select id="note_filter" options=note_options visible_rows=6 width=18 border_style="single" title="Notes" %}{% endselect %}
      {% endvstack %}

      {# Right column - Todos or Edit mode #}
      {% if edit_mode %}
        {% vstack width=90 %}
          {% textarea id="note_editor" height=18 width=88 %}{{ edit_content }}{% endtextarea %}
          {% hstack spacing=2 %}
            {% button action="save_edit" %}Save{% endbutton %}
            {% button action="cancel_edit" %}Cancel{% endbutton %}
          {% endhstack %}
        {% endvstack %}
      {% else %}
        {% select id="todo_list" options=todo_options visible_rows=14 width=90 border_style="single" title="Todos" %}{% endselect %}
      {% endif %}

    {% endhstack %}

    {# Filter bar #}
    {% hstack spacing=2 %}
      {% radiogroup id="status_filter" orientation="horizontal" %}
        {% radio value="incomplete" %}Incomplete{% endradio %}
        {% radio value="all" %}All{% endradio %}
      {% endradiogroup %}
      {% if selected_tag %}
        {% text %}Tag: #{{ selected_tag }}{% endtext %}
      {% endif %}
      {% text dim=true %}{{ item_count_text }}{% endtext %}
    {% endhstack %}

    {# Message bar #}
    {% if state.message %}
      {% text %}{{ state.message }}{% endtext %}
    {% endif %}

    {# Help bar #}
    {% text dim=true %}[d]one [s]tart [t]omorrow [D]ate [a]dd [e]dit [x]del [T]ag [q]uit{% endtext %}

  {% endvstack %}
{% endframe %}
            """,
            "data": get_data,
        }

    # --- Selection Change Handlers ---

    def on_state_change(key: str, old_value, new_value):
        """Handle state changes for Select and RadioGroup elements."""
        if key == "notebook_filter" and new_value != old_value:
            app.state["selected_notebook"] = new_value
            refresh_notes()
            refresh_todos()
            count = len(app.state.get("todos", []))
            app.state["message"] = f"Notebook: {new_value} ({count} todos)"
        elif key == "note_filter" and new_value != old_value:
            app.state["selected_note"] = new_value
            refresh_todos()
            count = len(app.state.get("todos", []))
            note_display = "All" if new_value == "All" else Path(new_value).stem
            app.state["message"] = f"Note: {note_display} ({count} todos)"
        elif key == "status_filter" and new_value != old_value:
            app.state["show_completed"] = new_value == "all"
            refresh_todos()
            status_text = "all todos" if new_value == "all" else "incomplete todos"
            app.state["message"] = f"Showing {status_text}"

    app.state.on_change(on_state_change)

    # --- Todo Actions ---

    @app.on_key("d")
    def toggle_done(event):
        """Toggle completion status of selected todo."""
        if app.state.get("edit_mode"):
            return

        todo = get_selected_todo()
        if not todo:
            app.state["message"] = "Select a todo first"
            return

        try:
            actual_line = toggle_todo_in_file(
                todo.source.path,
                todo.line_number,
                expected_content=todo.content,
            )
            if actual_line is not None:
                new_completed = not todo.completed
                update_todo_completion(todo.id, new_completed)
                action = "Completed" if new_completed else "Reopened"
                app.state["message"] = f"{action}: {todo.content[:40]}"
                refresh_todos()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("s")
    def toggle_started(event):
        """Toggle in-progress status of selected todo."""
        if app.state.get("edit_mode"):
            return

        todo = get_selected_todo()
        if not todo:
            app.state["message"] = "Select a todo first"
            return

        if todo.completed:
            app.state["message"] = "Cannot start completed todo. Reopen first."
            return

        try:
            if todo.in_progress:
                new_status = TodoStatus.PENDING
                action = "Paused"
            else:
                new_status = TodoStatus.IN_PROGRESS
                action = "Started"

            actual_line = set_todo_status_in_file(
                todo.source.path,
                todo.line_number,
                new_status,
                expected_content=todo.content,
            )
            if actual_line is not None:
                update_todo_status(todo.id, new_status)
                app.state["message"] = f"{action}: {todo.content[:40]}"
                refresh_todos()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("t")
    def reschedule_tomorrow(event):
        """Reschedule selected todo to tomorrow."""
        if app.state.get("edit_mode"):
            return

        todo = get_selected_todo()
        if not todo:
            app.state["message"] = "Select a todo first"
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
                app.state["message"] = f"Rescheduled to tomorrow: {todo.content[:30]}"
                refresh_todos()
        except PermissionError as e:
            app.state["message"] = f"Error: {e}"

    @app.on_key("D")
    def set_custom_date(event):
        """Set a custom due date via dialog."""
        if app.state.get("edit_mode"):
            return

        todo = get_selected_todo()
        if not todo:
            app.state["message"] = "Select a todo first"
            return

        def on_submit(date_str: str):
            if not date_str.strip():
                app.state["message"] = "No date entered"
                return

            parsed_date = parse_fuzzy_datetime_future(date_str.strip())
            if not parsed_date:
                app.state["message"] = f"Could not parse date: {date_str}"
                return

            try:
                actual_line = update_todo_due_date(
                    todo.source.path,
                    todo.line_number,
                    parsed_date,
                    expected_content=todo.content,
                )
                if actual_line is not None:
                    app.state["message"] = (
                        f"Due date set to {parsed_date.strftime('%b %d')}: {todo.content[:20]}"
                    )
                    refresh_todos()
            except PermissionError as e:
                app.state["message"] = f"Error: {e}"

        def on_cancel():
            app.state["message"] = "Date entry cancelled"

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
        show_centered_dialog(dialog, 60, 12)

    @app.on_key("x")
    def delete_todo(event):
        """Delete selected todo with confirmation."""
        if app.state.get("edit_mode"):
            return

        todo = get_selected_todo()
        if not todo:
            app.state["message"] = "Select a todo first"
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
                    app.state["message"] = f"Deleted: {todo.content[:40]}"
                    remove_current_todo()
            except PermissionError as e:
                app.state["message"] = f"Error: {e}"

        def on_cancel():
            app.state["message"] = "Delete cancelled"

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
        show_centered_dialog(dialog, 50, 11)

    # --- Add Todo ---

    @app.on_key("a")
    def add_todo(event):
        """Add a new todo."""
        if app.state.get("edit_mode"):
            return

        selected_note = app.state.get("selected_note", "All")

        if selected_note != "All":
            # Add to selected note
            show_add_todo_dialog(Path(selected_note))
        else:
            # Default to today's daily note
            daily_note = get_or_create_today_note()
            if daily_note:
                show_add_todo_dialog(daily_note)
            else:
                app.state["message"] = "Could not find or create daily note"

    def get_or_create_today_note() -> Path | None:
        """Get or create today's daily note."""
        from nb.core.notes import ensure_daily_note

        try:
            return ensure_daily_note(date.today())
        except Exception:
            return None

    def show_add_todo_dialog(note_path: Path):
        """Show dialog to add a new todo to a note."""

        def on_submit(todo_text: str):
            if not todo_text.strip():
                app.state["message"] = "No todo text entered"
                return

            try:
                # Read current content
                content = note_path.read_text(encoding="utf-8")
                lines = content.split("\n")

                # Find a good place to add the todo (after existing todos or at end)
                todo_line = f"- [ ] {todo_text.strip()}"
                insert_idx = len(lines)

                # Look for existing todo section
                for i, line in enumerate(lines):
                    if (
                        line.strip().startswith("- [ ]")
                        or line.strip().startswith("- [x]")
                        or line.strip().startswith("- [^]")
                    ):
                        # Found existing todos, insert after the last one
                        insert_idx = i + 1
                        # Continue to find the last todo
                        for j in range(i + 1, len(lines)):
                            if (
                                lines[j].strip().startswith("- [ ]")
                                or lines[j].strip().startswith("- [x]")
                                or lines[j].strip().startswith("- [^]")
                            ):
                                insert_idx = j + 1
                            elif lines[j].strip() and not lines[j].strip().startswith(
                                "-"
                            ):
                                break
                        break

                # Insert the new todo
                lines.insert(insert_idx, todo_line)
                note_path.write_text("\n".join(lines), encoding="utf-8")

                app.state["message"] = f"Added: {todo_text[:40]}"
                refresh_todos()
                refresh_notes()
            except Exception as e:
                app.state["message"] = f"Error adding todo: {e}"

        def on_cancel():
            app.state["message"] = "Add cancelled"

        dialog = TextInputDialog(
            title="Add Todo",
            prompt=f"Add to: {note_path.stem}",
            placeholder="Enter todo text...",
            on_submit=on_submit,
            on_cancel=on_cancel,
            submit_label="Add",
            cancel_label="Cancel",
            width=60,
            height=12,
            input_width=45,
        )
        show_centered_dialog(dialog, 60, 12)

    # --- Edit Mode ---

    @app.on_key("e")
    def enter_edit_mode(event):
        """Edit the note containing the selected todo."""
        if app.state.get("edit_mode"):
            return

        todo = get_selected_todo()
        if not todo:
            app.state["message"] = "Select a todo first"
            return

        try:
            content = todo.source.path.read_text(encoding="utf-8")
            app.state["edit_mode"] = True
            app.state["edit_content"] = content
            app.state["edit_note_path"] = str(todo.source.path)
            app.state["message"] = f"Editing: {todo.source.path.name}"
        except Exception as e:
            app.state["message"] = f"Error loading note: {e}"

    @app.on_action("save_edit")
    def save_edit(event):
        """Save edited note content."""
        note_path = app.state.get("edit_note_path")
        content = app.state.get("note_editor", "")

        if not note_path:
            app.state["message"] = "No note to save"
            return

        try:
            Path(note_path).write_text(content, encoding="utf-8")
            app.state["edit_mode"] = False
            app.state["edit_content"] = ""
            app.state["edit_note_path"] = None
            app.state["message"] = "Saved"
            refresh_todos()
            refresh_notes()
        except Exception as e:
            app.state["message"] = f"Error saving: {e}"

    @app.on_action("cancel_edit")
    def cancel_edit(event):
        """Cancel edit mode."""
        app.state["edit_mode"] = False
        app.state["edit_content"] = ""
        app.state["edit_note_path"] = None
        app.state["message"] = "Edit cancelled"

    @app.on_key("escape")
    def escape_handler(event):
        """Handle escape key."""
        if app.state.get("edit_mode"):
            cancel_edit(event)

    # --- Tag Filter ---

    @app.on_key("T")
    def cycle_tag_filter(event):
        """Cycle through tag filters or clear."""
        if app.state.get("edit_mode"):
            return

        all_tags = get_all_tags()
        if not all_tags:
            app.state["message"] = "No tags found"
            return

        current_tag = app.state.get("selected_tag")
        if current_tag is None:
            # Set to first tag
            app.state["selected_tag"] = all_tags[0]
        elif current_tag in all_tags:
            idx = all_tags.index(current_tag)
            if idx < len(all_tags) - 1:
                app.state["selected_tag"] = all_tags[idx + 1]
            else:
                app.state["selected_tag"] = None
        else:
            app.state["selected_tag"] = None

        refresh_todos()
        tag_display = app.state.get("selected_tag") or "none"
        app.state["message"] = f"Tag filter: {tag_display}"

    # --- Quit ---

    @app.on_key("q")
    def quit_app(event):
        """Quit the application."""
        if app.state.get("edit_mode"):
            app.state["message"] = "Save or cancel edit first"
            return
        app.quit()

    # Run the app
    app.run()
