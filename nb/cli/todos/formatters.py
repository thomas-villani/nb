"""Todo display formatting functions."""

from __future__ import annotations

from datetime import date

from nb.cli.utils import console, get_notebook_display_info
from nb.config import get_config
from nb.index.todos_repo import get_todo_children

# Display length for todo IDs (internal IDs are 8 chars, display 6 for brevity)
TODO_ID_DISPLAY_LEN = 6


def _get_todo_source_parts(t) -> dict[str, str]:
    """Extract source parts (notebook, note, section) from a todo.

    Returns a dict with keys: notebook, note, section (all may be empty strings).
    """
    result = {"notebook": "", "note": "", "section": t.section or ""}

    if not t.source:
        return result

    if t.source.alias:
        # Linked file - show notebook/alias (look up from linked notes)
        from nb.core.links import get_linked_note

        linked = get_linked_note(t.source.alias)
        if linked:
            result["notebook"] = linked.notebook or f"@{linked.alias}"
            # For single files, just show alias
            # For directories, show filename
            if linked.path.is_file():
                result["note"] = linked.alias
            else:
                # Show relative_path_stem
                try:
                    rel = t.source.path.relative_to(linked.path)
                    result["note"] = rel.stem
                except ValueError:
                    result["note"] = t.source.path.stem
        else:
            result["notebook"] = f"@{t.source.alias}"
    elif t.source.type == "inbox":
        result["notebook"] = "inbox"
    else:
        # Regular note - show notebook/filename
        config = get_config()
        try:
            rel_path = t.source.path.relative_to(config.notes_root)
            if len(rel_path.parts) > 1:
                result["notebook"] = rel_path.parts[0]
                result["note"] = rel_path.stem
            else:
                result["note"] = rel_path.stem
        except ValueError:
            result["note"] = t.source.path.stem

    return result


def _format_todo_source(
    t, max_width: int = 0, max_section_len: int = 15, hide_notebook: bool = False
) -> str:
    """Format the source of a todo for display (plain text, used for sorting).

    Format: notebook/note_title::Section (if section exists)
            notebook/note_title (if no section)
            note_title::Section (if hide_notebook and section exists)
            note_title (if hide_notebook and no section)

    Args:
        t: Todo object
        max_width: Maximum total width (0 = no limit). If exceeded, truncates with ellipsis.
        max_section_len: Maximum length for section name (default 15)
        hide_notebook: If True, omit notebook from output (show only note)
    """
    parts = _get_todo_source_parts(t)
    if not parts["notebook"] and not parts["note"]:
        return ""

    base_source = ""
    if hide_notebook:
        # Only show note, not notebook
        base_source = parts["note"] or ""
    elif parts["notebook"] and parts["note"]:
        base_source = f"{parts['notebook']}/{parts['note']}"
    elif parts["notebook"]:
        base_source = parts["notebook"]
    elif parts["note"]:
        base_source = parts["note"]

    if parts["section"]:
        section = parts["section"]
        if len(section) > max_section_len:
            section = section[: max_section_len - 1] + "…"
        result = f"{base_source}::{section}"
    else:
        result = base_source

    # Truncate if exceeds max_width
    if max_width > 0 and len(result) > max_width:
        result = result[: max_width - 1] + "…"

    return result


def _format_colored_todo_source(
    t, width: int = 0, max_section_len: int = 15, hide_notebook: bool = False
) -> str:
    """Format the source of a todo with colors for display.

    Uses configured notebook colors and icons.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)
        max_section_len: Maximum length for section name (default 15)
        hide_notebook: If True, omit notebook and icon from output

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    # Check if notebook has an icon - icons take ~2 visual chars (emoji + space)
    # No icon when hiding notebook
    if hide_notebook:
        color, icon = "white", None
    else:
        color, icon = (
            get_notebook_display_info(parts["notebook"])
            if parts["notebook"]
            else ("white", None)
        )
    icon_width = 2 if icon else 0  # emoji + space

    # Adjust available width for text (reserve space for icon)
    text_width = max(width - icon_width, 10) if width > 0 else 0

    # Build the plain source with adjusted width
    plain_source = _format_todo_source(
        t,
        max_width=text_width,
        max_section_len=max_section_len,
        hide_notebook=hide_notebook,
    )

    # Check if we need truncation
    full_plain = _format_todo_source(
        t, max_width=0, max_section_len=max_section_len, hide_notebook=hide_notebook
    )
    needs_truncation = text_width > 0 and len(full_plain) > text_width

    if needs_truncation:
        # Truncate: color each part that fits in the truncated string
        truncated = plain_source
        icon_prefix = f"{icon} " if icon else ""

        # Build colored version by identifying parts in the truncated string
        colored_parts = []
        remaining = truncated

        # Color notebook part (skip if hiding notebook)
        if (
            not hide_notebook
            and parts["notebook"]
            and remaining.startswith(parts["notebook"])
        ):
            colored_parts.append(f"[{color}]{icon_prefix}{parts['notebook']}[/{color}]")
            remaining = remaining[len(parts["notebook"]) :]
            icon_prefix = ""  # Only show icon once
        elif not hide_notebook and parts["notebook"]:
            # Notebook itself was truncated
            colored_parts.append(f"[{color}]{icon_prefix}{remaining}[/{color}]")
            remaining = ""

        # Color "/" separator and note part (skip "/" if hiding notebook)
        if not hide_notebook and remaining.startswith("/") and parts["note"]:
            colored_parts.append("/")
            remaining = remaining[1:]

        # Color note part
        if parts["note"] and remaining:
            # Find how much of the note fits
            if "::" in remaining:
                note_part = remaining.split("::")[0]
            else:
                note_part = remaining.rstrip("…")
                if remaining.endswith("…"):
                    note_part = remaining[:-1]  # Remove ellipsis for now
            if remaining.startswith(parts["note"]):
                colored_parts.append(f"[blue]{parts['note']}[/blue]")
                remaining = remaining[len(parts["note"]) :]
            elif note_part:
                colored_parts.append(f"[blue]{note_part}[/blue]")
                remaining = remaining[len(note_part) :]

        # Color "::" separator and section part
        if remaining.startswith("::"):
            colored_parts.append("::")
            remaining = remaining[2:]
            if remaining:
                colored_parts.append(f"[cyan]{remaining}[/cyan]")
                remaining = ""

        # Any remaining uncolored text
        if remaining:
            colored_parts.append(remaining)

        colored = "".join(colored_parts)
    else:
        # Build full colored source string
        colored_parts = []

        if not hide_notebook and parts["notebook"]:
            icon_prefix = f"{icon} " if icon else ""
            colored_parts.append(f"[{color}]{icon_prefix}{parts['notebook']}[/{color}]")

        if parts["note"]:
            if colored_parts:
                colored_parts.append("/")
            colored_parts.append(f"[blue]{parts['note']}[/blue]")

        if parts["section"]:
            section = parts["section"]
            if len(section) > max_section_len:
                section = section[: max_section_len - 1] + "…"
            colored_parts.append("::")
            colored_parts.append(f"[cyan]{section}[/cyan]")

        colored = "".join(colored_parts)

    # Calculate plain length for padding (text + icon)
    if width > 0:
        visual_len = len(plain_source) + icon_width
        if visual_len < width:
            colored += " " * (width - visual_len)

    return colored


def _format_nosection_source(t, max_width: int = 0, hide_notebook: bool = False) -> str:
    """Format the source of a todo without section (notebook/note only).

    Used for medium-width terminals where full source with section is too wide,
    but compact (notebook only) loses too much context.

    Args:
        t: Todo object
        max_width: Maximum width (0 = no limit)
        hide_notebook: If True, show only note name
    """
    parts = _get_todo_source_parts(t)
    if not parts["notebook"] and not parts["note"]:
        return ""

    if hide_notebook:
        result = parts["note"] or ""
    elif parts["notebook"] and parts["note"]:
        result = f"{parts['notebook']}/{parts['note']}"
    elif parts["notebook"]:
        result = parts["notebook"]
    else:
        result = parts["note"]

    if max_width > 0 and len(result) > max_width:
        result = result[: max_width - 1] + "…"

    return result


def _format_colored_nosection_source(
    t, width: int = 0, hide_notebook: bool = False
) -> str:
    """Format source without section (notebook/note) with colors.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)
        hide_notebook: If True, omit notebook and icon from output

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    if not parts["notebook"] and not parts["note"]:
        return " " * width if width > 0 else ""

    notebook = parts["notebook"] if not hide_notebook else None
    note = parts["note"]

    if hide_notebook:
        color, icon = "white", None
    else:
        color, icon = (
            get_notebook_display_info(notebook) if notebook else ("white", None)
        )

    # Icons take ~2 visual chars (emoji + space)
    icon_width = 2 if icon else 0

    # Build plain source for width calculation
    if hide_notebook:
        plain_source = note or ""
    elif notebook and note:
        plain_source = f"{notebook}/{note}"
    elif notebook:
        plain_source = notebook
    else:
        plain_source = note

    # Adjust available width for text (reserve space for icon)
    text_width = max(width - icon_width, 10) if width > 0 else 0

    # Truncate if needed
    if text_width > 0 and len(plain_source) > text_width:
        # Try to keep at least some of both parts
        truncated = plain_source[: text_width - 1] + "…"
    else:
        truncated = plain_source

    # Build colored version
    colored_parts = []
    remaining = truncated

    if not hide_notebook and notebook and remaining.startswith(notebook):
        icon_prefix = f"{icon} " if icon else ""
        colored_parts.append(f"[{color}]{icon_prefix}{notebook}[/{color}]")
        remaining = remaining[len(notebook) :]
    elif not hide_notebook and notebook:
        # Notebook was truncated
        icon_prefix = f"{icon} " if icon else ""
        colored_parts.append(f"[{color}]{icon_prefix}{remaining}[/{color}]")
        remaining = ""

    if not hide_notebook and remaining.startswith("/") and note:
        colored_parts.append("/")
        remaining = remaining[1:]

    # Color note part
    if remaining:
        if remaining.endswith("…"):
            colored_parts.append(f"[blue]{remaining}[/blue]")
        else:
            colored_parts.append(f"[blue]{remaining}[/blue]")
        remaining = ""

    if remaining:
        colored_parts.append(remaining)

    colored = "".join(colored_parts)

    # Calculate visual length for padding (text + icon)
    if width > 0:
        visual_len = len(truncated) + icon_width
        if visual_len < width:
            colored += " " * (width - visual_len)

    return colored


def _format_compact_source(t, max_width: int = 0, hide_notebook: bool = False) -> str:
    """Format the source of a todo in compact mode (notebook only, or note if hiding).

    Used when terminal is too narrow for full source display.

    Args:
        t: Todo object
        max_width: Maximum width (0 = no limit)
        hide_notebook: If True, show note instead of notebook
    """
    parts = _get_todo_source_parts(t)
    if hide_notebook:
        result = parts["note"] if parts["note"] else ""
    else:
        result = parts["notebook"] if parts["notebook"] else ""

    if max_width > 0 and len(result) > max_width:
        result = result[: max_width - 1] + "…"

    return result


def _format_colored_compact_source(
    t, width: int = 0, hide_notebook: bool = False
) -> str:
    """Format compact source (notebook only, or note if hiding) with colors.

    Args:
        t: Todo object
        width: Width for the column (pads if shorter, truncates if longer)
        hide_notebook: If True, show note instead of notebook

    Returns:
        Rich-formatted string with colors.
    """
    parts = _get_todo_source_parts(t)

    if hide_notebook:
        # Show note instead of notebook
        if not parts["note"]:
            return " " * width if width > 0 else ""
        text = parts["note"]
        # No icon when hiding notebook
        icon_width = 0
        # Truncate if needed
        if width > 0 and len(text) > width:
            text = text[: width - 1] + "…"
        colored = f"[blue]{text}[/blue]"
        if width > 0 and len(text) < width:
            colored += " " * (width - len(text))
        return colored

    if not parts["notebook"]:
        return " " * width if width > 0 else ""

    notebook = parts["notebook"]
    color, icon = get_notebook_display_info(notebook)

    # Icons take ~2 visual chars (emoji + space)
    icon_width = 2 if icon else 0

    # Truncate notebook if needed (reserve space for icon)
    if width > 0:
        text_available = max(width - icon_width, 5)
        if len(notebook) > text_available:
            notebook = notebook[: text_available - 1] + "…"

    icon_prefix = f"{icon} " if icon else ""
    colored = f"[{color}]{icon_prefix}{notebook}[/{color}]"

    # Calculate visual length for padding (text + icon)
    if width > 0:
        visual_len = len(notebook) + icon_width
        if visual_len < width:
            colored += " " * (width - visual_len)

    return colored


def _calculate_column_widths(
    todos: list, hide_notebook: bool = False, expand: bool = False
) -> dict[str, int | bool]:
    """Calculate column widths for aligned todo output.

    Uses dynamic terminal width with progressive truncation:
    1. Full layout with all columns + tags (wide terminals, >130)
    2. No created/tags, no-section source (medium terminals, 90-130)
    3. No created/tags, compact source - notebook only (narrower)
    4. Minimal - hide due date column (very narrow)

    When expand=True, prioritizes content width (up to 80 chars) and hides
    source/due columns as needed to fit.

    Args:
        todos: List of todos to calculate widths for
        hide_notebook: If True, source column shows only note (not notebook/note)
        expand: If True, maximize content width and hide source/due as needed

    Returns dict with column widths and visibility flags:
    - content, source, created, due, priority: int widths
    - show_created, show_due, compact_source, nosection_source, hide_notebook: bool flags
    """
    terminal_width = console.width or 120
    min_content_width = 25
    max_content_width = 60  # Don't pad content beyond this for readability

    # Calculate full source width based on actual content (min 15, max 30)
    # Account for icons which add ~2 visual chars (emoji + space)
    # When hide_notebook=True, don't include notebook or icon in width calculation
    max_source_full = 15
    max_source_nosection = 12  # notebook/note without section
    max_source_compact = 8  # notebook only
    for t in todos:
        parts = _get_todo_source_parts(t)
        _, icon = (
            get_notebook_display_info(parts["notebook"])
            if parts["notebook"]
            else (None, None)
        )
        # No icon when hiding notebook
        icon_width = 0 if hide_notebook else (2 if icon else 0)

        if hide_notebook:
            # Source is just note::section or note
            note = parts["note"] or ""
            section = parts["section"] or ""
            if section:
                source_str = f"{note}::{section}"
            else:
                source_str = note
            nosection_str = note
        else:
            source_str = _format_todo_source(t)
            nosection_str = _format_nosection_source(t)

        # Full source includes icon width
        max_source_full = max(max_source_full, len(source_str) + icon_width)
        # No-section source (notebook/note or just note)
        max_source_nosection = max(
            max_source_nosection, len(nosection_str) + icon_width
        )
        # Compact is notebook + icon (or just note when hiding)
        if hide_notebook:
            note_len = len(parts["note"]) if parts["note"] else 0
            max_source_compact = max(max_source_compact, note_len)
        else:
            notebook_len = len(parts["notebook"]) if parts["notebook"] else 0
            max_source_compact = max(max_source_compact, notebook_len + icon_width)

    source_width_full = min(max_source_full, 30)
    source_width_nosection = min(max_source_nosection, 25)
    source_width_compact = min(max_source_compact, 15)

    # Fixed widths
    created_width = 6  # "+MM/DD"
    due_width = 6  # "Mon DD"
    priority_width = 2  # "!N"
    id_width = 6

    # Base spacing: checkbox(1) + space + gaps between columns
    # With all columns: {checkbox} {content}  {source}  {created}  {due}  {priority}  {id}
    # Gaps: 2 after each column except last = 5 gaps * 2 = 10, plus checkbox overhead = 2
    base_spacing = 2 + id_width  # checkbox + id

    def calc_total(source_w: int, show_created: bool, show_due: bool) -> int:
        """Calculate total width needed for given configuration."""
        total = base_spacing + source_w + priority_width
        total += 2  # gap after content
        total += 2  # gap after source
        if show_created:
            total += created_width + 2  # column + gap
        if show_due:
            total += due_width + 2  # column + gap
        total += 2  # gap after priority
        return total

    def calc_total_no_source(show_due: bool) -> int:
        """Calculate total width needed without source column."""
        total = base_spacing + priority_width
        total += 2  # gap after content
        if show_due:
            total += due_width + 2  # column + gap
        total += 2  # gap after priority
        return total

    # Expanded view mode: maximize content width, show only id + source + content
    # Hide created, due, and priority to give maximum room for todo text
    if expand:
        # Base spacing: id(6) + checkbox(1) + space + gap after content + gap after source
        expand_base = id_width + 2 + 2 + 2  # 12 chars overhead

        # Try with full source
        fixed_total = expand_base + source_width_full
        content_width = terminal_width - fixed_total
        if content_width >= min_content_width:
            return {
                "content": content_width,
                "source": source_width_full,
                "created": 0,
                "due": 0,
                "priority": 0,
                "show_created": False,
                "show_due": False,
                "show_priority": False,
                "compact_source": False,
                "nosection_source": False,
                "hide_notebook": hide_notebook,
                "hide_source": False,
            }

        # Try with compact source
        fixed_total = expand_base + source_width_compact
        content_width = terminal_width - fixed_total
        if content_width >= min_content_width:
            return {
                "content": content_width,
                "source": source_width_compact,
                "created": 0,
                "due": 0,
                "priority": 0,
                "show_created": False,
                "show_due": False,
                "show_priority": False,
                "compact_source": True,
                "nosection_source": False,
                "hide_notebook": hide_notebook,
                "hide_source": False,
            }

        # Fallback: hide source too, maximize content
        fixed_total = id_width + 2 + 2  # id + checkbox + gap
        content_width = max(terminal_width - fixed_total, min_content_width)
        return {
            "content": content_width,
            "source": 0,
            "created": 0,
            "due": 0,
            "priority": 0,
            "show_created": False,
            "show_due": False,
            "show_priority": False,
            "compact_source": False,
            "nosection_source": False,
            "hide_notebook": hide_notebook,
            "hide_source": True,
        }

    # Try configurations in order of preference
    # Use explicit width thresholds for better control over medium-width terminals
    #
    # Tags add variable width (only shown in full layout with show_created=True)
    # so we need extra buffer for step 1 to avoid wrapping

    # 1. Full layout with all columns (wide terminals, typically > 130)
    # Requires extra room for tags (estimate ~20 chars for up to 3 tags)
    fixed_total = calc_total(source_width_full, show_created=True, show_due=True)
    tags_buffer = 20  # Space for tags which aren't in calc_total
    content_width = min(terminal_width - fixed_total - tags_buffer, max_content_width)
    if content_width >= min_content_width:
        return {
            "content": content_width,
            "source": source_width_full,
            "created": created_width,
            "due": due_width,
            "priority": priority_width,
            "show_created": True,
            "show_due": True,
            "compact_source": False,
            "nosection_source": False,
            "hide_notebook": hide_notebook,
            "hide_source": False,
        }

    # 2. Remove created/tags and use no-section source (medium terminals, 90-130)
    # Tags are not shown when show_created=False, so no buffer needed
    fixed_total = calc_total(source_width_nosection, show_created=False, show_due=True)
    content_width = min(terminal_width - fixed_total, max_content_width)
    if content_width >= min_content_width:
        return {
            "content": content_width,
            "source": source_width_nosection,
            "created": 0,
            "due": due_width,
            "priority": priority_width,
            "show_created": False,
            "show_due": True,
            "compact_source": False,
            "nosection_source": True,
            "hide_notebook": hide_notebook,
            "hide_source": False,
        }

    # 3. Remove created and use compact source (notebook only, narrower terminals)
    fixed_total = calc_total(source_width_compact, show_created=False, show_due=True)
    content_width = min(terminal_width - fixed_total, max_content_width)
    if content_width >= min_content_width:
        return {
            "content": content_width,
            "source": source_width_compact,
            "created": 0,
            "due": due_width,
            "priority": priority_width,
            "show_created": False,
            "show_due": True,
            "compact_source": True,
            "nosection_source": False,
            "hide_notebook": hide_notebook,
            "hide_source": False,
        }

    # 4. Remove created, compact source, and hide due date (very narrow)
    fixed_total = calc_total(source_width_compact, show_created=False, show_due=False)
    content_width = min(
        max(terminal_width - fixed_total, min_content_width), max_content_width
    )
    return {
        "content": content_width,
        "source": source_width_compact,
        "created": 0,
        "due": 0,
        "priority": priority_width,
        "show_created": False,
        "show_due": False,
        "compact_source": True,
        "nosection_source": False,
        "hide_notebook": hide_notebook,
        "hide_source": False,
    }


def _print_todo(
    t, indent: int = 0, widths: dict[str, int | bool] | None = None
) -> None:
    """Print a single todo with formatting."""
    prefix = "  " * indent
    indent_width = len(prefix)

    # Checkbox indicator: x=completed, ^=in-progress, o=pending
    if t.completed:
        checkbox = "[green]x[/green]"
    elif t.in_progress:
        checkbox = "[yellow]^[/yellow]"
    else:
        checkbox = "[dim]o[/dim]"

    # Get visibility flags from widths
    show_created = bool(widths.get("show_created", True)) if widths else True
    show_due = bool(widths.get("show_due", True)) if widths else True
    show_priority = bool(widths.get("show_priority", True)) if widths else True
    compact_source = bool(widths.get("compact_source", False)) if widths else False
    nosection_source = bool(widths.get("nosection_source", False)) if widths else False
    hide_notebook = bool(widths.get("hide_notebook", False)) if widths else False
    hide_source = bool(widths.get("hide_source", False)) if widths else False

    # Build content - truncate if needed for alignment
    # Reduce content width by indent amount to keep columns aligned
    content = t.content
    base_content_width = widths["content"] if widths else len(content)
    content_width = max(base_content_width - indent_width, 10)  # minimum 10 chars
    if len(content) > content_width:
        content_display = content[: content_width - 1] + "…"
    else:
        content_display = content.ljust(content_width)

    # Build source column (colored) - different modes for different widths
    source_width = widths["source"] if widths else 15
    if compact_source:
        source_str = _format_compact_source(t, hide_notebook=hide_notebook)
        source_part = _format_colored_compact_source(
            t, source_width, hide_notebook=hide_notebook
        )
    elif nosection_source:
        source_str = _format_nosection_source(t, hide_notebook=hide_notebook)
        source_part = (
            _format_colored_nosection_source(
                t, source_width, hide_notebook=hide_notebook
            )
            if source_str
            else " " * source_width
        )
    else:
        source_str = _format_todo_source(t, hide_notebook=hide_notebook)
        source_part = (
            _format_colored_todo_source(t, source_width, hide_notebook=hide_notebook)
            if source_str
            else " " * source_width
        )

    # Build metadata columns with fixed widths
    created_str = ""
    if show_created and t.created_date:
        created_str = f"+{t.created_date.strftime('%m/%d')}"

    due_str = ""
    due_color = "yellow"  # Default to yellow for future due dates
    if show_due and t.due_date:
        # Show time if not midnight, otherwise just date
        if t.has_due_time:
            due_str = t.due_date.strftime("%b %d %H:%M")
        else:
            due_str = t.due_date.strftime("%b %d")
        # Red if due today or overdue (and not completed)
        due = t.due_date_only
        if due and due <= date.today() and not t.completed:
            due_color = "red"

    priority_str = ""
    if t.priority:
        priority_str = f"!{t.priority.value}"

    # Only show tags when we have full layout (show_created = True)
    # Tags add variable width that would cause wrapping in compact modes
    tags_str = ""
    if t.tags and show_created:
        tags_str = " ".join(f"#{tag}" for tag in t.tags[:3])

    # Build the formatted line with alignment
    short_id = t.id[:TODO_ID_DISPLAY_LEN]

    # Format with Rich markup and padding
    if t.completed:
        content_part = f"[strikethrough]{content_display}[/strikethrough]"
    else:
        content_part = content_display

    priority_part = f"[magenta]{priority_str:>2}[/magenta]" if priority_str else "  "
    tags_part = f"  [cyan]{tags_str}[/cyan]" if tags_str else ""

    # Build line based on visible columns
    # ID stays left-aligned, indent comes after ID before checkbox
    if hide_source:
        line_parts = [f"[dim]{short_id}[/dim] {prefix}{checkbox} {content_part}"]
    else:
        line_parts = [
            f"[dim]{short_id}[/dim] {prefix}{checkbox} {content_part}  {source_part}"
        ]

    if show_created:
        created_part = f"[dim]{created_str:>6}[/dim]" if created_str else " " * 6
        line_parts.append(f"  {created_part}")

    if show_due:
        due_part = f"[{due_color}]{due_str:>6}[/{due_color}]" if due_str else " " * 6
        line_parts.append(f"  {due_part}")

    if show_priority:
        line_parts.append(f"  {priority_part}{tags_part}")

    console.print("".join(line_parts))

    # Print children
    children = get_todo_children(t.id)
    for child in children:
        _print_todo(child, indent=indent + 1, widths=widths)
