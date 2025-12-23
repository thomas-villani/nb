"""Interactive search TUI for nb using Wijjit."""

from __future__ import annotations

import asyncio
from pathlib import Path

from wijjit import Wijjit
from wijjit.logging_config import get_logger

from nb.config import get_config
from nb.index.db import get_db
from nb.index.search import SearchResult, get_search, reset_search
from nb.tui.wijjit_utils import truncate

logger = get_logger("wijjit")


def get_all_notebooks() -> list[str]:
    """Get all unique notebooks from the notes table.

    Returns:
        List of notebook names.

    """
    db = get_db()
    query = "SELECT DISTINCT notebook FROM notes WHERE notebook IS NOT NULL ORDER BY notebook"
    rows = db.execute(query).fetchall()
    return [row[0] for row in rows if row[0]]


def get_all_note_tags() -> list[str]:
    """Get all unique tags from the note_tags table.

    Returns:
        List of tag names.

    """
    db = get_db()
    query = "SELECT DISTINCT tag FROM note_tags ORDER BY tag"
    rows = db.execute(query).fetchall()
    return [row[0] for row in rows if row[0]]


def run_interactive_search(
    initial_query: str = "",
    initial_notebook: str | None = None,
    initial_tag: str | None = None,
    search_type: str = "hybrid",
) -> None:
    """Run the interactive search TUI.

    Args:
        initial_query: Initial search query.
        initial_notebook: Initial notebook filter.
        initial_tag: Initial tag filter.
        search_type: Search type (hybrid, vector, keyword).

    """
    from nb.tui.stream import run_note_stream
    from nb.utils.editor import open_in_editor

    config = get_config()

    # Load initial data
    all_notebooks = get_all_notebooks()
    all_tags = get_all_note_tags()

    # Initialize app with state
    app = Wijjit(
        initial_state={
            # Search state
            "query": initial_query,
            "search_type": search_type,
            "results": [],
            # Filter state
            "notebook_filter": initial_notebook or "All",
            "tag_filter": initial_tag or "All",
            "recency_boost": False,
            # Preview state
            "preview_content": "",
            "preview_title": "",
            "preview_metadata": "",
            # UI state
            "message": "Enter a search query and press Enter.",
            "result_count": 0,
            "is_searching": False,
            # Data for dropdowns
            "all_notebooks": all_notebooks,
            "all_tags": all_tags,
        },
        log_file="debug-search.log",
        log_level="DEBUG",
    )

    # Track background tasks to prevent garbage collection
    background_tasks: set[asyncio.Task] = set()

    async def execute_search():
        """Execute search with current state (async).

        Uses asyncio.to_thread() to run the sync search in a thread pool,
        preventing the event loop from blocking during CPU-intensive search.
        """
        query = app.state.get("query", "").strip()
        if not query:
            app.state["results"] = []
            app.state["result_count"] = 0
            app.state["preview_content"] = ""
            app.state["message"] = "Enter a search query."
            return

        # Build filters
        filters: dict | None = {}
        notebook = app.state.get("notebook_filter")
        if notebook and notebook != "All":
            filters["notebook"] = notebook

        tag = app.state.get("tag_filter")
        if tag and tag != "All":
            filters["tags"] = {"$contains": tag}

        if not filters:
            filters = None

        recency_boost = 0.3 if app.state.get("recency_boost") else 0.0
        search_type_param = app.state.get("search_type", "hybrid")

        # Show searching state
        app.state["is_searching"] = True
        app.state["message"] = "Searching..."
        app.refresh_interval = 0.2  # Enable refresh for spinner animation

        try:
            # Use asyncio.to_thread() with sync search to avoid blocking event loop
            search = get_search()
            results = await asyncio.to_thread(
                search.search,
                query,
                search_type=search_type_param,
                k=50,
                filters=filters,
                recency_boost=recency_boost,
                score_threshold=0.3,
            )

            app.state["results"] = results
            app.state["result_count"] = len(results)

            if results:
                app.state["result_list"] = "0"  # Select first result by index
                load_preview(results[0])
                app.state["message"] = f"Found {len(results)} results."
            else:
                app.state["result_list"] = "_empty"
                app.state["preview_content"] = ""
                app.state["message"] = "No results found."

        except Exception as e:
            app.state["message"] = f"Search error: {e}"
            app.state["results"] = []
            app.state["result_count"] = 0
        finally:
            app.state["is_searching"] = False
            app.refresh_interval = None  # Disable refresh when done

    def get_selected_result() -> SearchResult | None:
        """Get the currently selected search result by index."""
        selected_idx = app.state.get("result_list")
        if not selected_idx or selected_idx == "_empty":
            return None
        try:
            idx = int(selected_idx)
            results = app.state.get("results", [])
            if 0 <= idx < len(results):
                return results[idx]
        except (ValueError, TypeError):
            pass
        return None

    def load_preview(result: SearchResult | None = None):
        """Load preview content for selected result.

        Shows the matching chunk content rather than the full note,
        since search results may include multiple chunks from the same note.
        """
        if result is None:
            result = get_selected_result()

        if not result:
            app.state["preview_content"] = ""
            app.state["preview_title"] = ""
            app.state["preview_metadata"] = ""
            return

        # Use the chunk content from the search result
        app.state["preview_content"] = result.snippet
        app.state["preview_title"] = result.title or Path(result.path).stem

        # Build metadata line
        meta_parts = []
        if result.date:
            meta_parts.append(result.date)
        if result.notebook:
            meta_parts.append(f"[{result.notebook}]")
        meta_parts.append(f"Score: {result.score:.2f}")
        app.state["preview_metadata"] = " | ".join(meta_parts)

    @app.view("main", default=True)
    def main_view():
        """Main search view."""

        def get_data():
            """Compute fresh data on each render."""
            results = app.state.get("results", [])
            all_notebooks = app.state.get("all_notebooks", [])
            all_tags = app.state.get("all_tags", [])
            preview_content = app.state.get("preview_content", "")
            preview_title = app.state.get("preview_title", "")
            preview_metadata = app.state.get("preview_metadata", "")
            result_count = app.state.get("result_count", 0)

            # Build notebook options
            notebook_options = [{"value": "All", "label": "All"}]
            for nb in all_notebooks:
                if nb:
                    notebook_options.append({"value": nb, "label": truncate(nb, 14)})

            # Build tag options
            tag_options = [{"value": "All", "label": "All"}]
            for tag in all_tags:
                if tag:
                    tag_options.append({"value": tag, "label": truncate(tag, 14)})

            # Build result options with aligned columns
            title_width = 35
            notebook_width = 12
            result_options = []

            for i, r in enumerate(results):
                title = truncate(r.title or Path(r.path).stem, title_width)
                notebook = truncate(r.notebook or "", notebook_width)
                score_str = f"{r.score:.2f}"

                label = f"[{score_str}] {title:<{title_width}}  {notebook:<{notebook_width}}"
                # Use index as value to ensure uniqueness (same note can have multiple chunks)
                result_options.append({"value": str(i), "label": label})

            if not result_options:
                result_options = [{"value": "_empty", "label": "(No results)"}]

            # Search type options for radio group
            search_type_options = [
                {"value": "hybrid", "label": "Hybrid"},
                {"value": "vector", "label": "Semantic"},
                {"value": "keyword", "label": "Keyword"},
            ]

            # Compute results title
            results_title = f"Results ({result_count})"

            return {
                "notebook_options": notebook_options,
                "tag_options": tag_options,
                "result_options": result_options,
                "result_count": result_count,
                "results_title": results_title,
                "search_type_options": search_type_options,
                "preview_content": preview_content,
                "preview_title": preview_title,
                "preview_metadata": preview_metadata,
            }

        return {
            "template": """
{% frame border_style="rounded" title="Interactive Search" height="fill" %}
{% hstack width="fill" padding=1 %}
  {% textinput id="search_input" width=60 placeholder="Enter query, press Enter..." action="do_search" %}{{ state.query }}{% endtextinput %}
  {% spinner id="search_spinner" active=state.is_searching style="dots" color="cyan" %}{% endspinner %}
{% endhstack %}
{# Main content area with panels #}
    {% hstack spacing=1 %}

      {# Left column - Filters and Results #}
      {% vstack width=65 height="fill" spacing=0 %}

        {# Search bar with spinner #}

        {% hstack %}
            {% radiogroup id="search_type" orientation="vertical" options=search_type_options %}{% endradiogroup %}
            {% checkbox id="recency_boost" %}Recency boost{% endcheckbox %}
        {% endhstack %}

        {# Results list #}
        {% select id="result_list" options=result_options visible_rows=23 width=60 border_style="single" title=results_title %}{% endselect %}

      {% endvstack %}

      {# Right column - Preview #}
      {% vstack width=65 spacing=0 %}
       {# Filter row #}
        {% hstack spacing=1 %}
          {% select id="notebook_filter" options=notebook_options visible_rows=5 width=26 border_style="single" title="Notebooks" %}{% endselect %}
          {% select id="tag_filter" options=tag_options visible_rows=5 width=26 border_style="single" title="Tags" %}{% endselect %}
        {% endhstack %}

        {% if preview_title %}
          {% text bold=true %}{{ preview_title }}{% endtext %}
          {% text dim=true %}{{ preview_metadata }}{% endtext %}
        {% endif %}
        {% contentview id="preview_pane" content_type="markdown" height=21 width=60 border_style="single" title="Preview" %}
{{ preview_content }}
{% endcontentview %}
      {% endvstack %}

    {% endhstack %}

    {# Message bar #}
    {% if state.message %}
      {% text %}{{ state.message }}{% endtext %}
    {% endif %}

    {# Help bar #}
    {% text dim=true %}Ctrl+E edit | Ctrl+F full note | Ctrl+Y copy | Ctrl+O stream | Ctrl+Q quit{% endtext %}

{% endframe %}
            """,
            "data": get_data,
        }

    # --- State Change Handlers ---

    async def on_state_change(key: str, old_value, new_value):
        """Handle state changes for Select elements."""
        # Update preview when result selection changes
        if key == "result_list" and new_value != old_value and new_value != "_empty":
            load_preview()

    app.state.on_change(on_state_change)

    # --- Search Actions ---

    @app.on_action("do_search")
    async def do_search_action(event):
        """Handle search submission from TextInput."""
        logger.debug("search")
        if app.state.get("is_searching"):
            return
        query = app.state.get("search_input", "")
        app.state["query"] = query
        app.state["is_searching"] = True
        app.state["message"] = "Searching..."
        app.refresh_interval = 0.2
        task = asyncio.create_task(execute_search())
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    # --- Result Actions (Ctrl+key to avoid conflicts with text input) ---

    @app.on_key("ctrl+e")
    def edit_result(event):
        """Open selected result in editor."""
        result = get_selected_result()
        if not result:
            app.state["message"] = "Select a result first"
            return

        full_path = config.notes_root / result.path
        # Quit TUI first, then open editor (required on Windows)
        app.quit()
        open_in_editor(full_path, config.editor)

    @app.on_key("ctrl+f")
    def load_full_note(event):
        """Load full note content in preview (Ctrl+F for full)."""
        result = get_selected_result()
        if not result:
            app.state["message"] = "Select a result first"
            return

        full_path = config.notes_root / result.path

        try:
            content = full_path.read_text(encoding="utf-8")
            app.state["preview_content"] = content
            app.state["message"] = "Showing full note"
        except Exception as e:
            app.state["message"] = f"Error loading: {e}"

    @app.on_key("ctrl+y")
    def copy_path(event):
        """Copy selected result path to clipboard (Ctrl+Y for yank)."""
        import pyperclip

        result = get_selected_result()
        if not result:
            app.state["message"] = "Select a result first"
            return

        full_path = config.notes_root / result.path

        try:
            pyperclip.copy(str(full_path))
            app.state["message"] = f"Copied: {full_path}"
        except Exception as e:
            app.state["message"] = f"Copy failed: {e}"

    @app.on_key("ctrl+o")
    def view_in_stream(event):
        """View selected result in stream viewer (Ctrl+O for open)."""
        result = get_selected_result()
        if not result:
            app.state["message"] = "Select a result first"
            return

        # Create a Note object for the stream viewer
        from nb.models import Note
        from nb.utils.hashing import make_note_id

        full_path = config.notes_root / result.path

        note = Note(
            id=make_note_id(result.path),
            path=full_path,
            title=result.title,
            notebook=result.notebook,
            date=None,  # Could parse from result.date if needed
        )

        # Exit current TUI and launch stream
        app.quit()
        run_note_stream([note], config.notes_root, continuous=False)

    # --- Navigation ---

    # Ctrl+Q not needed, automatically provided by Wijjit

    @app.on_key("escape")
    def escape_handler(event):
        """Handle escape - clear or quit."""
        if app.state.get("query"):
            app.state["query"] = ""
            app.state["search_input"] = ""
            app.state["results"] = []
            app.state["result_count"] = 0
            app.state["preview_content"] = ""
            app.state["message"] = "Search cleared"
        else:
            app.quit()

    # Note: Initial search is triggered by user pressing Enter
    # The initial_query is pre-filled in the search input

    # Run the app with proper cleanup
    try:
        app.run()
    finally:
        # Close the search DB connection to prevent hanging
        reset_search()
