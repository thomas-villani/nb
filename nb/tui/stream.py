"""Interactive note streaming viewer for nb using Wijjit."""

from __future__ import annotations

from pathlib import Path

from wijjit import Wijjit

from nb.config import get_config
from nb.models import Note


def run_note_stream(
    notes: list[Note],
    notes_root: Path,
    continuous: bool = False,
) -> None:
    """Run the interactive note streaming viewer.

    Args:
        notes: List of notes to stream through.
        notes_root: Root directory for notes.
        continuous: If True, show all notes in a continuous flow with dividers.

    """
    from rich.console import Console

    from nb.utils.editor import open_in_editor

    if not notes:
        Console().print("[yellow]No notes found.[/yellow]")
        return

    config = get_config()

    def load_note_content(note: Note) -> str:
        """Load content for a note."""
        if note.path.is_absolute():
            full_path = note.path
        else:
            full_path = notes_root / note.path

        try:
            return full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return "[Error reading file]"

    def get_note_path(note: Note) -> Path:
        """Get the full path for a note."""
        if note.path.is_absolute():
            return note.path
        return notes_root / note.path

    # Lazy loading settings for continuous mode
    NOTES_PER_BATCH = 10

    def format_note_header(note: Note, index: int) -> str:
        """Format a note header for the continuous view."""
        title = note.title or "Untitled"
        date_str = note.date.strftime(config.date_format) if note.date else ""
        notebook = f"[{note.notebook}]" if note.notebook else ""
        return f"# {title}\n\n*{date_str}* {notebook} — Note {index + 1}/{len(notes)}\n\n---\n\n"

    def build_continuous_content(up_to_index: int) -> str:
        """Build content for continuous mode with notes up to given index."""
        parts = []
        for i in range(min(up_to_index + 1, len(notes))):
            note = notes[i]
            header = format_note_header(note, i)
            content = load_note_content(note)
            parts.append(header + content)
        return "\n\n---\n\n".join(parts)

    # Load initial content
    if continuous:
        # Load first batch only
        initial_loaded = min(NOTES_PER_BATCH, len(notes)) - 1
        initial_content = build_continuous_content(initial_loaded)
    else:
        initial_loaded = 0
        initial_content = load_note_content(notes[0])

    # Initialize app with state
    app = Wijjit(
        initial_state={
            "notes": notes,
            "current_index": 0,
            "note_content": initial_content,
            "edit_mode": False,
            "continuous_mode": continuous,
            "loaded_up_to": initial_loaded,  # For lazy loading in continuous mode
            "message": "",
        }
    )

    def get_current_note() -> Note | None:
        """Get the currently displayed note."""
        notes = app.state.get("notes", [])
        idx = app.state.get("current_index", 0)
        if not notes or idx >= len(notes):
            return None
        return notes[idx]

    def refresh_content():
        """Reload content for current note."""
        note = get_current_note()
        if note:
            app.state["note_content"] = load_note_content(note)

    @app.view("main", default=True)
    def main_view():
        """Main note viewing/editing view."""

        def get_data():
            """Compute fresh data on each render."""
            notes = app.state.get("notes", [])
            idx = app.state.get("current_index", 0)
            note_content = app.state.get("note_content", "")
            edit_mode = app.state.get("edit_mode", False)
            continuous_mode = app.state.get("continuous_mode", False)

            # Get current note info
            note = notes[idx] if notes and idx < len(notes) else None

            loaded_up_to = app.state.get("loaded_up_to", 0)
            total_notes = len(notes)
            loaded_count = loaded_up_to + 1 if continuous_mode else 1
            has_more = continuous_mode and loaded_count < total_notes

            if continuous_mode:
                title = f"Stream [{loaded_count}/{total_notes} notes]"
                date_str = ""
                notebook = ""
                nav_info = ""
            elif note:
                title = note.title or "Untitled"
                date_str = note.date.strftime(config.date_format) if note.date else ""
                notebook = note.notebook or ""
                nav_info = f"[{idx + 1}/{len(notes)}]"
            else:
                title = "No note"
                date_str = ""
                notebook = ""
                nav_info = ""

            return {
                "title": title,
                "date_str": date_str,
                "notebook": notebook,
                "nav_info": nav_info,
                "note_content": note_content,
                "edit_mode": edit_mode,
                "continuous_mode": continuous_mode,
                "has_notes": bool(notes),
                "has_more": has_more,
            }

        return {
            "template": """
{% frame border_style="single" title=title height="fill" %}
  {% vstack spacing=1 %}

    {# Header with navigation info (paged mode only) #}
    {% if not continuous_mode %}
      {% hstack spacing=2 %}
        {% if date_str %}
          {% text %}{{ date_str }}{% endtext %}
        {% endif %}
        {% if notebook %}
          {% text dim=true %}[{{ notebook }}]{% endtext %}
        {% endif %}
        {% text dim=true %}{{ nav_info }}{% endtext %}
      {% endhstack %}
    {% endif %}

    {% if has_notes %}
      {% if state.edit_mode %}
        {# Edit mode - textarea with wide width to match content view #}
        {% textarea id="note_editor" height=25 width=120 %}{{ note_content }}{% endtextarea %}

        {% hstack spacing=2 %}
          {% button action="save" %}Save{% endbutton %}
          {% button action="cancel" %}Cancel{% endbutton %}
        {% endhstack %}
      {% else %}
        {# Read mode - markdown content view #}
        {% contentview id="note_viewer" content_type="markdown" height=25 width=120 title="Content" %}
{{ note_content }}
{% endcontentview %}
      {% endif %}
    {% else %}
      {% text dim=true %}No notes to display{% endtext %}
    {% endif %}

    {# Message bar #}
    {% if state.message %}
      {% text %}{{ state.message }}{% endtext %}
    {% endif %}

    {# Navigation buttons (paged mode only) #}
    {% if not state.edit_mode and not continuous_mode %}
      {% hstack spacing=1 %}
        {% button action="prev_note" %}< Prev{% endbutton %}
        {% button action="next_note" %}Next >{% endbutton %}
        {% button action="first_note" %}First{% endbutton %}
        {% button action="last_note" %}Last{% endbutton %}
        {% button action="edit_inapp" %}Edit{% endbutton %}
        {% button action="edit_external" %}External{% endbutton %}
        {% button action="quit" %}Quit{% endbutton %}
      {% endhstack %}
    {% endif %}

    {# Continuous mode controls #}
    {% if not state.edit_mode and continuous_mode %}
      {% hstack spacing=1 %}
        {% if has_more %}
          {% button action="load_more" %}Load More (m){% endbutton %}
        {% endif %}
        {% button action="quit" %}Quit{% endbutton %}
      {% endhstack %}
      {% if has_more %}
        {% text dim=true %}Press 'm' to load more notes{% endtext %}
      {% endif %}
    {% endif %}

  {% endvstack %}
{% endframe %}
            """,
            "data": get_data,
        }

    # --- Navigation ---

    def go_next_note():
        """Navigate to next note."""
        if app.state.get("edit_mode") or app.state.get("continuous_mode"):
            return
        notes = app.state.get("notes", [])
        idx = app.state.get("current_index", 0)
        if idx < len(notes) - 1:
            app.state["current_index"] = idx + 1
            refresh_content()
        else:
            app.state["message"] = "Last note"

    def go_prev_note():
        """Navigate to previous note."""
        if app.state.get("edit_mode") or app.state.get("continuous_mode"):
            return
        idx = app.state.get("current_index", 0)
        if idx > 0:
            app.state["current_index"] = idx - 1
            refresh_content()
        else:
            app.state["message"] = "First note"

    @app.on_key("j")
    def next_note_j(event):
        """Go to next note (j key)."""
        go_next_note()

    @app.on_key("k")
    def prev_note_k(event):
        """Go to previous note (k key)."""
        go_prev_note()

    @app.on_key("n")
    def next_note_n(event):
        """Go to next note (n key)."""
        go_next_note()

    @app.on_key("N")
    def prev_note_N(event):
        """Go to previous note (N key)."""
        go_prev_note()

    @app.on_key("p")
    def prev_note_p(event):
        """Go to previous note (p key)."""
        go_prev_note()

    @app.on_key("g")
    def first_note(event):
        """Go to first note."""
        if app.state.get("edit_mode") or app.state.get("continuous_mode"):
            return
        if app.state.get("current_index", 0) != 0:
            app.state["current_index"] = 0
            refresh_content()

    @app.on_key("G")
    def last_note(event):
        """Go to last note."""
        if app.state.get("edit_mode") or app.state.get("continuous_mode"):
            return
        notes = app.state.get("notes", [])
        last_idx = len(notes) - 1
        if notes and app.state.get("current_index", 0) != last_idx:
            app.state["current_index"] = last_idx
            refresh_content()

    # --- Load More (continuous mode) ---

    def load_more_notes():
        """Load more notes in continuous mode."""
        if not app.state.get("continuous_mode"):
            return

        notes_list = app.state.get("notes", [])
        loaded_up_to = app.state.get("loaded_up_to", 0)

        if loaded_up_to >= len(notes_list) - 1:
            app.state["message"] = "All notes loaded"
            return

        # Load next batch
        new_loaded = min(loaded_up_to + NOTES_PER_BATCH, len(notes_list) - 1)
        app.state["loaded_up_to"] = new_loaded
        app.state["note_content"] = build_continuous_content(new_loaded)
        app.state["message"] = f"Loaded {new_loaded + 1}/{len(notes_list)} notes"

    @app.on_key("m")
    def load_more_key(event):
        """Load more notes (m key)."""
        load_more_notes()

    @app.on_action("load_more")
    def load_more_action(event):
        """Button: Load more notes."""
        load_more_notes()

    # --- Editing ---

    @app.on_key("e")
    def edit_in_app(event):
        """Enter in-app edit mode."""
        if app.state.get("edit_mode"):
            return
        note = get_current_note()
        if note:
            app.state["edit_mode"] = True
            app.state["message"] = "Editing... Press Save or Cancel when done"

    @app.on_key("E")
    def edit_external(event):
        """Open in external editor."""
        if app.state.get("edit_mode"):
            return
        note = get_current_note()
        if note:
            full_path = get_note_path(note)
            open_in_editor(full_path, editor=config.editor)
            refresh_content()
            app.state["message"] = "Refreshed after external edit"

    @app.on_action("save")
    def save_note(event):
        """Save edited note content."""
        note = get_current_note()
        if not note:
            return

        content = app.state.get("note_editor", "")
        full_path = get_note_path(note)

        try:
            full_path.write_text(content, encoding="utf-8")
            app.state["note_content"] = content
            app.state["edit_mode"] = False
            app.state["message"] = "Saved"
        except (OSError, PermissionError) as e:
            app.state["message"] = f"Error saving: {e}"

    @app.on_action("cancel")
    def cancel_edit(event):
        """Cancel editing and restore original content."""
        app.state["edit_mode"] = False
        refresh_content()
        app.state["message"] = "Edit cancelled"

    # --- Quit ---

    @app.on_key("q")
    def quit_app(event):
        """Quit the viewer."""
        if app.state.get("edit_mode"):
            app.state["message"] = "Save or cancel edit first"
            return
        app.quit()

    # Handle escape to cancel edit or quit
    @app.on_key("escape")
    def escape_handler(event):
        """Handle escape key."""
        if app.state.get("edit_mode"):
            cancel_edit(event)
        else:
            app.quit()

    # --- Button Action Handlers ---

    @app.on_action("prev_note")
    def action_prev_note(event):
        """Button: Previous note."""
        go_prev_note()

    @app.on_action("next_note")
    def action_next_note(event):
        """Button: Next note."""
        go_next_note()

    @app.on_action("first_note")
    def action_first_note(event):
        """Button: First note."""
        first_note(event)

    @app.on_action("last_note")
    def action_last_note(event):
        """Button: Last note."""
        last_note(event)

    @app.on_action("edit_inapp")
    def action_edit_inapp(event):
        """Button: Edit in-app."""
        edit_in_app(event)

    @app.on_action("edit_external")
    def action_edit_external(event):
        """Button: Edit in external editor."""
        edit_external(event)

    @app.on_action("quit")
    def action_quit(event):
        """Button: Quit."""
        quit_app(event)

    # Run the app
    app.run()
