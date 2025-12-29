"""Todo-related CLI commands."""

from __future__ import annotations

import sys
from datetime import date, timedelta

import click

from nb.cli.completion import complete_notebook, complete_tag, complete_view
from nb.cli.utils import (
    console,
    find_todo,
    get_clipboard_content,
    get_display_path,
    get_notebook_display_info,
    get_stdin_content,
    resolve_note_ref,
)
from nb.config import get_config
from nb.core.todos import (
    add_todo_to_daily_note,
    add_todo_to_inbox,
    set_todo_status_in_file,
    toggle_todo_in_file,
)
from nb.index.scanner import index_all_notes
from nb.index.todos_repo import (
    get_todo_children,
    query_todos,
    update_todo_completion,
    update_todo_status,
)
from nb.models import TodoStatus
from nb.utils.dates import get_week_range
from nb.utils.editor import open_in_editor

# Import from submodules
from .display import _list_todos
from .formatters import TODO_ID_DISPLAY_LEN
from .views import (
    _create_todo_view,
    _delete_todo_view,
    _display_kanban,
    _list_todo_views,
)


def register_todo_commands(cli: click.Group) -> None:
    """Register all todo-related commands with the CLI."""
    cli.add_command(todo)


@click.group(invoke_without_command=True)
@click.option("--created-today", is_flag=True, help="Show only todos created today")
@click.option("--created-week", is_flag=True, help="Show only todos created this week")
@click.option("--today", "-T", is_flag=True, help="Show only todos due today")
@click.option("--week", "-W", is_flag=True, help="Show only todos due this week")
@click.option("--overdue", is_flag=True, help="Show only overdue todos")
@click.option("--priority", "-p", type=int, help="Filter by priority (1, 2, or 3)")
@click.option("--tag", "-t", help="Filter by tag", shell_complete=complete_tag)
@click.option(
    "--exclude-tag",
    "-xt",
    multiple=True,
    help="Exclude todos with this tag (repeatable)",
    shell_complete=complete_tag,
)
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (repeatable)",
    shell_complete=complete_notebook,
)
@click.option(
    "--note",
    "-N",
    multiple=True,
    help="Filter by note path or linked alias (repeatable)",
)
@click.option(
    "--section",
    "-S",
    multiple=True,
    help="Filter by path section/subdirectory (repeatable)",
)
@click.option(
    "--exclude-section",
    "-xs",
    multiple=True,
    help="Exclude todos from this section (repeatable)",
)
@click.option(
    "--exclude-notebook",
    "-xn",
    multiple=True,
    help="Exclude todos from this notebook (repeatable)",
    shell_complete=complete_notebook,
)
@click.option(
    "--view", "-v", help="Apply a saved todo view", shell_complete=complete_view
)
@click.option("--create-view", help="Create a view from current filters")
@click.option("--list-views", is_flag=True, help="List all saved views")
@click.option("--delete-view", help="Delete a saved view")
@click.option("--hide-later", is_flag=True, help="Hide todos due later than next week")
@click.option("--hide-no-date", is_flag=True, help="Hide todos with no due date")
@click.option(
    "--focus",
    "-f",
    is_flag=True,
    help="Focus mode: hide later/no-date; hide next week if this week has items",
)
@click.option(
    "--sort-by",
    "-s",
    type=click.Choice(["source", "tag", "priority", "created"]),
    default=None,
    help="Sort todos within groups (default from config)",
)
@click.option(
    "--all",
    "-a",
    "show_all",
    is_flag=True,
    help="Include todos from all sources (even excluded notebooks)",
)
@click.option("--include-completed", "-c", is_flag=True, help="Include completed todos")
@click.option("-i", "--interactive", is_flag=True, help="Open interactive todo viewer")
@click.option("--limit", "-l", type=int, help="Limit the number of todos displayed")
@click.option("--offset", "-o", type=int, default=0, help="Skip the first N todos")
@click.option(
    "--expand",
    "-x",
    is_flag=True,
    help="Expanded view: show more content (up to 80 chars), hide source/due as needed",
)
@click.option(
    "--kanban",
    "-k",
    is_flag=True,
    help="Display todos in kanban board columns",
)
@click.option(
    "--board",
    "-b",
    default="default",
    help="Kanban board name to use (default: 'default')",
)
@click.option(
    "--copy",
    "-C",
    "copy_to_clip",
    is_flag=True,
    help="Copy todo list to clipboard (as checkbox format)",
)
@click.pass_context
def todo(
    ctx: click.Context,
    created_today: bool,
    created_week: bool,
    today: bool,
    week: bool,
    overdue: bool,
    priority: int | None,
    tag: str | None,
    exclude_tag: tuple[str, ...],
    notebook: tuple[str, ...],
    note: tuple[str, ...],
    section: tuple[str, ...],
    exclude_section: tuple[str, ...],
    exclude_notebook: tuple[str, ...],
    view: str | None,
    create_view: str | None,
    list_views: bool,
    delete_view: str | None,
    hide_later: bool,
    hide_no_date: bool,
    focus: bool,
    sort_by: str | None,
    show_all: bool,
    include_completed: bool,
    interactive: bool,
    limit: int | None,
    offset: int,
    expand: bool,
    kanban: bool,
    board: str,
    copy_to_clip: bool,
) -> None:
    """Manage todos.

    Run 'nb todo' without a subcommand to list todos grouped by status and due date:
    OVERDUE, IN PROGRESS, DUE TODAY, DUE TOMORROW, DUE THIS WEEK, DUE NEXT WEEK, DUE LATER, NO DUE DATE.

    Todos can be marked in-progress with 'nb todo start <ID>' which changes
    the marker from [ ] to [^] in the source file.

    \b
    Examples:
      nb todo                 List all open todos
      nb todo -f              Focus mode (hide later/no-date sections)
      nb todo -t work         Show only todos tagged #work
      nb todo -xt waiting     Exclude todos tagged #waiting
      nb todo -p 1            Show only high priority todos
      nb todo -n daily        Show todos from 'daily' notebook only
      nb todo -n daily -n work  Filter by multiple notebooks
      nb todo --note myproject  Filter by specific note
      nb todo --note nbtodo     Filter by linked note alias
      nb todo --note a --note b  Filter by multiple notes
      nb todo -a              Include todos from excluded notebooks
      nb todo -c              Include completed todos
      nb todo -s tag          Sort by tag instead of source
      nb todo --today         Show only todos due today
      nb todo --week          Show only todos due this week
      nb todo -v myview       Apply saved view 'myview'
      nb todo -n work --create-view work  Save current filters as view
      nb todo --list-views    List all saved views
      nb todo -l 10           Show only first 10 todos
      nb todo -o 10 -l 10     Skip first 10, show next 10 (pagination)
      nb todo -x              Expanded view (more content, less metadata)
      nb todo -k              Display as kanban board
      nb todo -k -b sprint    Use custom board config
      nb todo -C              Copy todo list to clipboard
    """
    # If invoking a subcommand, skip the listing logic
    if ctx.invoked_subcommand is not None:
        return

    config = get_config()

    # Handle view operations first (they don't list todos)
    if list_views:
        _list_todo_views(config)
        return

    if delete_view:
        _delete_todo_view(config, delete_view)
        return

    if create_view:
        _create_todo_view(
            config,
            name=create_view,
            notebooks=list(notebook) if notebook else None,
            notes=list(note) if note else None,
            tag=tag,
            priority=priority,
            exclude_tags=list(exclude_tag) if exclude_tag else None,
            hide_later=hide_later,
            hide_no_date=hide_no_date,
            include_completed=include_completed,
        )
        return

    # Apply view if specified
    if view:
        view_config = config.get_todo_view(view)
        if not view_config:
            console.print(f"[red]View not found: {view}[/red]")
            console.print("[dim]Use --list-views to see available views.[/dim]")
            raise SystemExit(1)

        filters = view_config.filters
        # Apply view filters (command-line overrides view filters)
        if not notebook and filters.get("notebooks"):
            notebook = tuple(filters["notebooks"])
        if not note and filters.get("notes"):
            note = tuple(filters["notes"])
        if tag is None and filters.get("tag"):
            tag = filters["tag"]
        if priority is None and filters.get("priority"):
            priority = filters["priority"]
        if not exclude_tag and filters.get("exclude_tags"):
            exclude_tag = tuple(filters["exclude_tags"])
        if not hide_later and filters.get("hide_later"):
            hide_later = True
        if not hide_no_date and filters.get("hide_no_date"):
            hide_no_date = True
        if not include_completed and filters.get("include_completed"):
            include_completed = True

    # Index notes first
    from nb.index.scanner import remove_deleted_notes

    remove_deleted_notes()
    index_all_notes(index_vectors=False)

    # Interactive mode uses TUI
    if interactive:
        from nb.tui.todos import run_interactive_todos

        run_interactive_todos()
        return

    # Resolve notebooks with fuzzy matching
    from nb.cli.utils import resolve_notebook
    from nb.utils.fuzzy import UserCancelled

    effective_notebooks: list[str] = []
    for nb_name in notebook:
        if config.get_notebook(nb_name):
            effective_notebooks.append(nb_name)
        else:
            try:
                resolved = resolve_notebook(nb_name)
            except UserCancelled:
                console.print("[dim]Cancelled.[/dim]")
                raise SystemExit(1) from None
            if resolved:
                effective_notebooks.append(resolved)
            else:
                raise SystemExit(1)

    # Resolve notes
    from nb.cli.utils import resolve_note_for_todo_filter

    effective_notes: list[str] = []
    for note_ref in note:
        try:
            resolved_path, _ = resolve_note_for_todo_filter(note_ref)
        except UserCancelled:
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(1) from None
        if resolved_path:
            effective_notes.append(resolved_path)
        else:
            console.print(f"[yellow]Note not found: {note_ref}[/yellow]")
            raise SystemExit(1)

    # Resolve sections
    effective_sections: list[str] | None = list(section) if section else None

    # Resolve exclude notebooks with fuzzy matching
    all_excluded_notebooks: list[str] | None = None
    if not effective_notebooks and not effective_notes:
        # Apply exclusions only when not filtering by specific notebooks/notes
        if show_all:
            # --all overrides config exclusions but respects CLI exclusions
            all_excluded_notebooks = (
                list(exclude_notebook) if exclude_notebook else None
            )
        else:
            # Merge config exclusions with CLI exclusions
            config_excluded = config.excluded_notebooks() or []
            all_excluded_notebooks = list(set(config_excluded) | set(exclude_notebook))
            if not all_excluded_notebooks:
                all_excluded_notebooks = None

    # Get sort order
    effective_sort = sort_by or config.todo.default_sort

    # Focus mode implies hide_later and hide_no_date
    if focus:
        hide_later = True
        hide_no_date = True

    # Kanban mode
    if kanban:
        _display_kanban(
            notebooks=effective_notebooks if effective_notebooks else None,
            exclude_notebooks=all_excluded_notebooks,
            board_name=board,
        )
        return

    # Regular list view
    _list_todos(
        created_today=created_today,
        created_week=created_week,
        due_today=today,
        due_week=week,
        overdue=overdue,
        priority=priority,
        tag=tag,
        exclude_tags=list(exclude_tag) if exclude_tag else None,
        notebooks=effective_notebooks if effective_notebooks else None,
        notes=effective_notes if effective_notes else None,
        sections=effective_sections,
        exclude_notebooks=all_excluded_notebooks,
        path_sections=list(section) if section else None,
        exclude_path_sections=list(exclude_section) if exclude_section else None,
        hide_later=hide_later,
        hide_no_date=hide_no_date,
        focus=focus,
        sort_by=effective_sort,
        include_completed=include_completed,
        exclude_note_excluded=not show_all,
        limit=limit,
        offset=offset,
        expand=expand,
        copy=copy_to_clip,
    )


# =============================================================================
# SUBCOMMANDS
# =============================================================================


def _complete_todo_with_children(t) -> int:
    """Complete a todo and all its children recursively.

    Returns the count of children that were completed.
    """
    children_completed = 0
    children = get_todo_children(t.id)

    for child in children:
        if child.completed:
            continue

        # Set child to completed in source file (pass content to handle stale line numbers)
        actual_line = set_todo_status_in_file(
            child.source.path,
            child.line_number,
            TodoStatus.COMPLETED,
            expected_content=child.content,
        )
        if actual_line is not None:
            update_todo_completion(child.id, True)
            children_completed += 1

            # Recursively complete grandchildren
            children_completed += _complete_todo_with_children(child)

    return children_completed


def _delete_todo_with_children(t, force: bool = False) -> int:
    """Delete a todo and all its children recursively.

    Returns the count of children that were deleted.
    """
    from nb.core.todos import delete_todo_from_file
    from nb.index.todos_repo import delete_todo

    children_deleted = 0
    children = get_todo_children(t.id)

    # Delete children first (bottom-up to preserve line numbers)
    for child in reversed(children):
        children_deleted += _delete_todo_with_children(child, force=True)

    # Delete from source file (pass content to handle stale line numbers)
    try:
        actual_line = delete_todo_from_file(
            t.source.path, t.line_number, expected_content=t.content
        )
        if actual_line is not None:
            delete_todo(t.id)
            return children_deleted + 1
    except PermissionError as e:
        console.print(f"[red]{e}[/red]")
        console.print(
            "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
        )

    return children_deleted


@todo.command("add")
@click.argument("text", required=False)
@click.option(
    "--today",
    "-t",
    "add_today",
    is_flag=True,
    help="Add to today's daily note instead of inbox",
)
@click.option(
    "--note",
    "-N",
    "target_note",
    help="Add to specific note (path or path::section)",
)
@click.option(
    "--paste",
    "-p",
    is_flag=True,
    help="Read todo(s) from clipboard",
)
def todo_add(
    text: str | None, add_today: bool, target_note: str | None, paste: bool
) -> None:
    """Add a new todo to the inbox (or today's note with --today).

    Accepts todo text as an argument, from stdin (piped input), or from
    clipboard (--paste). All sources are combined if multiple are provided.
    TEXT can include inline metadata:

    \b
      @due(DATE)      Set due date (today, tomorrow, friday, 2024-12-25)
      @priority(N)    Set priority (1=high, 2=medium, 3=low)
      #tag            Add tags

    \b
    Examples:
      nb todo add "Review PR"
      nb todo add "Review PR @due(friday) #work"
      nb todo add "Urgent task @priority(1) @due(today)"
      nb todo add --today "Call dentist"
      nb todo add --note work/project "Document API"
      nb todo add --note work/project::Tasks "New task"

    \b
    Clipboard examples:
      nb todo add --paste                          # Add from clipboard
      nb todo add --paste --today                  # Clipboard to daily note
      nb todo add --paste --note work/project      # Clipboard to specific note

    \b
    Piping examples:
      echo "Review PR" | nb todo add               # Pipe to inbox
      echo "Task @due(friday)" | nb todo add       # Pipe with metadata

    \b
    Multi-line clipboard:
      If clipboard contains checkbox lines (- [ ], - [x], - [^]),
      each line is added as a separate todo.
    """
    # Gather content from all sources (clipboard, stdin, argument)
    parts = []

    if paste:
        clipboard = get_clipboard_content()
        if clipboard:
            parts.append(clipboard)
        else:
            console.print("[yellow]Warning: Clipboard is empty.[/yellow]")

    stdin = get_stdin_content()
    if stdin:
        parts.append(stdin)

    if text:
        parts.append(text)

    content = "\n".join(parts).strip() if parts else None

    if not content:
        console.print("[red]No todo text provided.[/red]")
        console.print('[dim]Usage: nb todo add "text" or nb todo add --paste[/dim]')
        raise SystemExit(1)

    # Parse content for checkbox lines (multi-todo support)
    # If content contains checkbox lines, extract each as a separate todo
    import re

    checkbox_pattern = re.compile(r"^\s*-\s*\[[ x^]\]\s*", re.IGNORECASE)
    lines = content.split("\n")

    # Check if any line looks like a checkbox
    has_checkboxes = any(checkbox_pattern.match(line) for line in lines)

    if has_checkboxes:
        # Extract todo text from each checkbox line
        todo_texts = []
        for line in lines:
            match = checkbox_pattern.match(line)
            if match:
                todo_text = line[match.end() :].strip()
                if todo_text:
                    todo_texts.append(todo_text)
    else:
        # Treat the whole content as a single todo
        todo_texts = [content]
    from nb.core.todos import add_todo_to_note

    if target_note:
        # Parse note::section syntax
        if "::" in target_note:
            note_ref, section = target_note.split("::", 1)
        else:
            note_ref = target_note
            section = None

        # Use resolve_note_ref which handles:
        # - Note aliases (from 'nb alias')
        # - Linked note aliases in notebook context (from 'nb link')
        # - notebook/note format parsing
        # - Date-based notebooks
        # - Fuzzy matching
        from nb.cli.utils import resolve_note_ref
        from nb.utils.fuzzy import UserCancelled

        try:
            resolved_path = resolve_note_ref(note_ref, ensure_exists=True)
        except UserCancelled:
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(1) from None

        if not resolved_path:
            console.print(f"[red]Note not found: {note_ref}[/red]")
            raise SystemExit(1)

        # If section specified, check for ambiguous matches
        if section:
            from rich.prompt import Prompt

            from nb.core.todos import find_matching_sections

            matches = find_matching_sections(resolved_path, section)

            if len(matches) > 1:
                # Multiple matches - prompt user to choose
                console.print(f"[yellow]Multiple sections match '{section}':[/yellow]")
                for i, (_, name) in enumerate(matches, 1):
                    console.print(f"  [cyan]{i}[/cyan]. {name}")
                console.print(
                    f"  [cyan]{len(matches) + 1}[/cyan]. Create new section '{section}'"
                )
                console.print("  [dim]0[/dim]. Cancel")

                choice = Prompt.ask(
                    "Select",
                    choices=[str(i) for i in range(len(matches) + 2)],
                    default="1",
                )

                if choice == "0":
                    console.print("[dim]Cancelled.[/dim]")
                    raise SystemExit(1)
                elif int(choice) == len(matches) + 1:
                    # User wants to create a new section
                    pass  # Keep original section name
                else:
                    # Use the selected section name
                    section = matches[int(choice) - 1][1]

        try:
            added_todos = []
            for todo_text in todo_texts:
                t = add_todo_to_note(todo_text, resolved_path, section=section)
                added_todos.append(t)

            # Display results
            if len(added_todos) == 1:
                t = added_todos[0]
                if t.section:
                    console.print(
                        f"[green]Added to {resolved_path.name}::{t.section}:[/green] {t.content}"
                    )
                else:
                    console.print(
                        f"[green]Added to {resolved_path.name}:[/green] {t.content}"
                    )
                console.print(f"[dim]ID: {t.id[:TODO_ID_DISPLAY_LEN]}[/dim]")
            else:
                section_str = (
                    f"::{added_todos[0].section}" if added_todos[0].section else ""
                )
                console.print(
                    f"[green]Added {len(added_todos)} todos to {resolved_path.name}{section_str}[/green]"
                )
                for t in added_todos:
                    console.print(
                        f"  [dim]{t.id[:TODO_ID_DISPLAY_LEN]}[/dim] {t.content}"
                    )
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None
    elif add_today:
        added_todos = []
        for todo_text in todo_texts:
            t = add_todo_to_daily_note(todo_text)
            added_todos.append(t)

        if len(added_todos) == 1:
            console.print(
                f"[green]Added to today's note:[/green] {added_todos[0].content}"
            )
            console.print(f"[dim]ID: {added_todos[0].id[:TODO_ID_DISPLAY_LEN]}[/dim]")
        else:
            console.print(
                f"[green]Added {len(added_todos)} todos to today's note[/green]"
            )
            for t in added_todos:
                console.print(f"  [dim]{t.id[:TODO_ID_DISPLAY_LEN]}[/dim] {t.content}")
    else:
        added_todos = []
        for todo_text in todo_texts:
            t = add_todo_to_inbox(todo_text)
            added_todos.append(t)

        if len(added_todos) == 1:
            console.print(f"[green]Added to inbox:[/green] {added_todos[0].content}")
            console.print(f"[dim]ID: {added_todos[0].id[:TODO_ID_DISPLAY_LEN]}[/dim]")
        else:
            console.print(f"[green]Added {len(added_todos)} todos to inbox[/green]")
            for t in added_todos:
                console.print(f"  [dim]{t.id[:TODO_ID_DISPLAY_LEN]}[/dim] {t.content}")


@todo.command("done")
@click.argument("todo_id", nargs=-1)
def todo_done(todo_id: tuple[str, ...]) -> None:
    """Mark a todo as completed.

    TODO_ID can be the full ID or just the first few characters.
    The 6-character ID shown in 'nb todo' output is usually sufficient.

    If the todo has child todos (subtasks), they will also be marked as completed.

    \b
    Examples:
      nb todo done abc123
      nb todo done abc123def456...
      nb todo done abc123 def567   # Multiple IDs allowed
    """
    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if t.completed:
            console.print(
                f"[yellow]Todo {_todo[:TODO_ID_DISPLAY_LEN]} is already completed.[/yellow]"
            )
            continue

        # Toggle in source file (pass content to handle stale line numbers)
        try:
            actual_line = toggle_todo_in_file(
                t.source.path, t.line_number, expected_content=t.content
            )
            if actual_line is not None:
                update_todo_completion(t.id, True)
                console.print(f"[green]Completed:[/green] {t.content}")

                # Auto-complete child todos (if enabled in config)
                config = get_config()
                if config.todo.auto_complete_children:
                    children_completed = _complete_todo_with_children(t)
                    if children_completed > 0:
                        console.print(
                            f"[dim]  Also completed {children_completed} subtask(s)[/dim]"
                        )
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("undone")
@click.argument("todo_id", nargs=-1)
def todo_undone(todo_id: tuple[str, ...]) -> None:
    """Mark a todo as incomplete (reopen it).

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo undone abc123
    """
    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if not t.completed:
            console.print(
                f"[yellow]Todo {_todo[:TODO_ID_DISPLAY_LEN]} is not completed.[/yellow]"
            )
            continue

        # Toggle in source file (pass content to handle stale line numbers)
        try:
            actual_line = toggle_todo_in_file(
                t.source.path, t.line_number, expected_content=t.content
            )
            if actual_line is not None:
                update_todo_completion(t.id, False)
                console.print(f"[green]Reopened:[/green] {t.content}")
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("start")
@click.argument("todo_id", nargs=-1)
def todo_start(todo_id: tuple[str, ...]) -> None:
    """Mark a todo as in-progress.

    Changes the todo marker from [ ] to [^] in the source file.
    In-progress todos appear in their own section in 'nb todo' output.

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo start abc123
    """

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if t.completed:
            console.print(
                f"[yellow]Todo {_todo[:TODO_ID_DISPLAY_LEN]} is already completed. Use 'nb todo undone' first.[/yellow]"
            )
            continue

        if t.in_progress:
            console.print(
                f"[yellow]Todo {_todo[:TODO_ID_DISPLAY_LEN]} is already in progress.[/yellow]"
            )
            continue

        # Set status in source file (pass content to handle stale line numbers)
        try:
            actual_line = set_todo_status_in_file(
                t.source.path,
                t.line_number,
                TodoStatus.IN_PROGRESS,
                expected_content=t.content,
            )
            if actual_line is not None:
                update_todo_status(t.id, TodoStatus.IN_PROGRESS)
                console.print(f"[yellow]Started:[/yellow] {t.content}")
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("pause")
@click.argument("todo_id", nargs=-1)
def todo_pause(todo_id: tuple[str, ...]) -> None:
    """Pause an in-progress todo (return to pending).

    Changes the todo marker from [^] to [ ] in the source file.

    TODO_ID can be the full ID or just the first few characters.

    \b
    Examples:
      nb todo pause abc123
    """

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        if t.completed:
            console.print(
                f"[yellow]Todo {_todo[:TODO_ID_DISPLAY_LEN]} is completed. Use 'nb todo undone' first.[/yellow]"
            )
            continue

        if not t.in_progress:
            console.print(
                f"[yellow]Todo {_todo[:TODO_ID_DISPLAY_LEN]} is not in progress.[/yellow]"
            )
            continue

        # Set status in source file (pass content to handle stale line numbers)
        try:
            actual_line = set_todo_status_in_file(
                t.source.path,
                t.line_number,
                TodoStatus.PENDING,
                expected_content=t.content,
            )
            if actual_line is not None:
                update_todo_status(t.id, TodoStatus.PENDING)
                console.print(f"[dim]Paused:[/dim] {t.content}")
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("due")
@click.argument("todo_id", nargs=-1)
@click.argument("date_expr")
def todo_due(todo_id: tuple[str, ...], date_expr: str) -> None:
    """Set or clear the due date for a todo.

    \b
    DATE_EXPR can be:
    - A date: "2025-12-15", "dec 15", "tomorrow", "friday"
    - A date with time: "2025-12-15 14:30", "tomorrow 2pm", "friday 9am"
    - Relative days: "+7" (7 days from now), "+1" (tomorrow), "+30"
    - "none" or "clear" to remove the due date

    Note: "friday" means the NEXT Friday (future), not the most recent.

    \b
    Examples:
      nb todo due abc123 friday         # Set due to next Friday
      nb todo due abc123 tomorrow
      nb todo due abc123 "dec 25"
      nb todo due abc123 2025-12-15
      nb todo due abc123 "friday 2pm"   # With time
      nb todo due abc123 "tomorrow 9am"
      nb todo due abc123 +7             # 7 days from now
      nb todo due abc123 none           # Remove due date
      nb todo due abc def friday        # Multiple IDs
    """
    from nb.core.todos import remove_todo_due_date, update_todo_due_date
    from nb.index.todos_repo import update_todo_due_date_db
    from nb.utils.dates import (
        format_datetime,
        is_clear_date_keyword,
        parse_fuzzy_datetime_future,
    )

    # Check if we should clear the due date
    is_clear = is_clear_date_keyword(date_expr)

    if not is_clear:
        new_date = parse_fuzzy_datetime_future(date_expr)
        if not new_date:
            console.print(f"[red]Could not parse date: {date_expr}[/red]")
            console.print(
                "[dim]Try: tomorrow, friday 2pm, next monday 9am, dec 15, 2025-12-15 14:30, or 'none' to clear[/dim]"
            )
            raise SystemExit(1)
    else:
        new_date = None

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)

        try:
            if is_clear:
                # Remove due date from file
                actual_line = remove_todo_due_date(
                    t.source.path,
                    t.line_number,
                    expected_content=t.content,
                )
            else:
                # Update due date in file
                assert new_date is not None  # Guaranteed by is_clear check above
                actual_line = update_todo_due_date(
                    t.source.path,
                    t.line_number,
                    new_date,
                    expected_content=t.content,
                )

            if actual_line is not None:
                # Update database
                update_todo_due_date_db(t.id, new_date)

                if is_clear:
                    console.print(f"[green]Cleared due date:[/green] {t.content}")
                else:
                    assert new_date is not None
                    # Format with time if not midnight
                    date_display = format_datetime(new_date)
                    console.print(f"[green]Due {date_display}:[/green] {t.content}")
            else:
                console.print("[red]Failed to update todo in source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
                raise SystemExit(1)
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )
            raise SystemExit(1) from None


@todo.command("show")
@click.argument("todo_id")
@click.option(
    "--copy",
    "-C",
    "copy_to_clip",
    is_flag=True,
    help="Copy todo details to clipboard",
)
def todo_show(todo_id: str, copy_to_clip: bool) -> None:
    """Show detailed information about a todo.

    Displays the todo's content, status, source file, due date,
    priority, tags, project, and any subtasks.

    \b
    Examples:
      nb todo show abc123
      nb todo show abc123 --copy    # Copy details to clipboard
    """
    from nb.cli.todos.formatters import format_todo_as_checkbox
    from nb.cli.utils import copy_to_clipboard

    t = find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    console.print(f"\n[bold]{t.content}[/bold]")
    console.print(f"ID: {t.id}")
    # Show status
    if t.completed:
        status_str = "Completed"
    elif t.in_progress:
        status_str = "In Progress"
    else:
        status_str = "Pending"
    console.print(f"Status: {status_str}")
    console.print(f"Source: {t.source.path}:{t.line_number}")

    if t.due_date:
        console.print(f"Due: {t.due_date}")
    if t.priority:
        console.print(f"Priority: {t.priority.value}")
    if t.tags:
        console.print(f"Tags: {', '.join(t.tags)}")
    if t.notebook:
        console.print(f"Notebook: {t.notebook}")

    if t.details:
        console.print("\n[bold]Details:[/bold]")
        console.print(f"[dim]{t.details}[/dim]")

    children = get_todo_children(t.id)
    if children:
        console.print("\n[bold]Subtasks:[/bold]")
        for child in children:
            checkbox = "x" if child.completed else "o"
            console.print(f"  {checkbox} {child.content}")

    # Copy to clipboard if requested
    if copy_to_clip:
        lines = [format_todo_as_checkbox(t)]
        if children:
            for child in children:
                lines.append("  " + format_todo_as_checkbox(child))
        clipboard_text = "\n".join(lines)
        if copy_to_clipboard(clipboard_text):
            console.print("\n[dim]Copied to clipboard.[/dim]")


@todo.command("edit")
@click.argument("todo_id")
def todo_edit(todo_id: str) -> None:
    """Open the source file at the todo's line in your editor.

    Opens the markdown file containing the todo, jumping directly
    to the line where the todo is defined.

    \b
    Examples:
      nb todo edit abc123
    """
    t = find_todo(todo_id)
    if not t:
        console.print(f"[red]Todo not found: {todo_id}[/red]")
        raise SystemExit(1)

    config = get_config()
    path = t.source.path

    # Capture mtime before edit
    try:
        mtime_before = path.stat().st_mtime
    except OSError:
        mtime_before = None

    console.print(f"[dim]Opening {path.name}:{t.line_number}...[/dim]")
    open_in_editor(path, line=t.line_number, editor=config.editor)

    # Sync if file was modified
    try:
        mtime_after = path.stat().st_mtime
        if mtime_before is None or mtime_after != mtime_before:
            from nb.core.notes import _reindex_note_after_edit, update_note_mtime

            print("Syncing nb...", end="", file=sys.stderr, flush=True)
            update_note_mtime(path, config.notes_root)
            _reindex_note_after_edit(path, config.notes_root)
            print(" done", file=sys.stderr)
    except OSError:
        pass


@todo.command("delete")
@click.argument("todo_id", nargs=-1)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def todo_delete(todo_id: tuple[str, ...], force: bool) -> None:
    """Delete a todo from the source file and database.

    TODO_ID can be the full ID or just the first few characters.
    The 6-character ID shown in 'nb todo' output is usually sufficient.

    If the todo has child todos (subtasks), they will also be deleted.

    \b
    Examples:
      nb todo delete abc123
      nb todo delete abc123 def456   # Multiple IDs
      nb todo delete abc123 -f       # Skip confirmation
    """
    from rich.prompt import Confirm

    if not todo_id:
        console.print("[yellow]No todo ID provided.[/yellow]")
        raise SystemExit(1)

    for _todo in todo_id:
        t = find_todo(_todo)
        if not t:
            console.print(f"[red]Todo not found: {_todo}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh the todo index, or use 'nb todo' to list todos.[/dim]"
            )
            continue

        # Check for children
        children = get_todo_children(t.id)
        children_count = len(children)

        # Show confirmation unless --force
        if not force:
            console.print(f"\n[bold]Delete todo:[/bold] {t.content}")
            console.print(f"[dim]Source: {t.source.path.name}:{t.line_number}[/dim]")
            if children_count > 0:
                console.print(
                    f"[yellow]This will also delete {children_count} subtask(s).[/yellow]"
                )

            if not Confirm.ask("Are you sure?", default=False):
                console.print("[dim]Cancelled.[/dim]")
                continue

        # Delete the todo and its children
        try:
            deleted_count = _delete_todo_with_children(t, force=True)
            if deleted_count > 0:
                if children_count > 0:
                    console.print(
                        f"[green]Deleted:[/green] {t.content} [dim](+{children_count} subtask(s))[/dim]"
                    )
                else:
                    console.print(f"[green]Deleted:[/green] {t.content}")
            else:
                console.print("[red]Failed to delete todo from source file.[/red]")
                console.print(
                    "[dim]Hint: The todo may have been edited or moved. Run 'nb index' to refresh.[/dim]"
                )
        except PermissionError as e:
            console.print(f"[red]{e}[/red]")
            console.print(
                "[dim]Hint: Use 'nb link' to enable sync for external files.[/dim]"
            )


@todo.command("review")
@click.option(
    "--weekly", "-w", is_flag=True, help="Include this week + no-due-date items"
)
@click.option(
    "--all",
    "-a",
    "show_all",
    is_flag=True,
    help="Review all incomplete todos",
)
@click.option(
    "--include-no-due-date",
    "-u",
    "include_no_due_date",
    is_flag=True,
    help="Also include todos with no due date",
)
@click.option(
    "--priority",
    "-p",
    type=click.Choice(["1", "2", "3", "high", "medium", "low"], case_sensitive=False),
    help="Filter by priority (1/high, 2/medium, 3/low)",
)
@click.option("--tag", "-t", help="Filter by tag", shell_complete=complete_tag)
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (repeatable)",
    shell_complete=complete_notebook,
)
@click.option(
    "--note",
    "-N",
    multiple=True,
    help="Filter by note path (repeatable)",
)
@click.option(
    "--exclude-notebook",
    "-xn",
    multiple=True,
    help="Exclude todos from this notebook (repeatable)",
    shell_complete=complete_notebook,
)
def todo_review(
    weekly: bool,
    show_all: bool,
    include_no_due_date: bool,
    priority: str | None,
    tag: str | None,
    notebook: tuple[str, ...],
    note: tuple[str, ...],
    exclude_notebook: tuple[str, ...],
) -> None:
    """Interactively review and triage todos.

    Opens an interactive TUI to quickly process overdue and upcoming todos.
    Use keyboard shortcuts to mark done, reschedule, or delete items.

    \b
    Scopes:
      (default)      Overdue + due today
      --weekly       Overdue + this week + items with no due date
      --all          All incomplete todos
      -u             Add todos with no due date to current scope

    \b
    Actions (in TUI):
      d  Mark done         s  Start (in progress)
      t  Tomorrow          f  This Friday
      m  Next Monday       w  Next week
      n  Next month        c  Custom date
      e  Edit in editor    k  Skip (move to next)
      x  Delete            q  Quit review

    \b
    Navigation:
      Up/Down  Move selection    Enter  Select

    \b
    Examples:
      nb todo review              Review overdue + due today
      nb todo review --weekly     Include this week's todos
      nb todo review --all        Review everything incomplete
      nb todo review -u           Include todos with no due date
      nb todo review -p high      Review only high priority todos
      nb todo review -t work      Review only #work tagged todos
      nb todo review -n daily     Review only from daily notebook
    """
    from nb.cli.utils import resolve_notebook
    from nb.tui.review import run_review
    from nb.utils.fuzzy import UserCancelled

    config = get_config()

    # Determine scope
    if show_all:
        scope = "all"
    elif weekly:
        scope = "weekly"
    else:
        scope = "daily"

    # Convert priority string to integer
    priority_int: int | None = None
    if priority:
        priority_map = {"high": 1, "medium": 2, "low": 3, "1": 1, "2": 2, "3": 3}
        priority_int = priority_map.get(priority.lower())

    # Resolve notebooks with fuzzy matching
    effective_notebooks: list[str] = []
    for nb_name in notebook:
        if config.get_notebook(nb_name):
            effective_notebooks.append(nb_name)
        else:
            try:
                resolved = resolve_notebook(nb_name)
            except UserCancelled:
                console.print("[dim]Cancelled.[/dim]")
                raise SystemExit(1) from None
            if resolved:
                effective_notebooks.append(resolved)
            else:
                raise SystemExit(1)

    # Resolve notes
    from nb.cli.utils import resolve_note_for_todo_filter

    effective_notes: list[str] = []
    for note_ref in note:
        try:
            resolved_path, _ = resolve_note_for_todo_filter(note_ref)
        except UserCancelled:
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(1) from None
        if resolved_path:
            effective_notes.append(resolved_path)
        else:
            console.print(f"[yellow]Note not found: {note_ref}[/yellow]")
            raise SystemExit(1)

    # Get excluded notebooks
    # - CLI --exclude-notebook flags always apply (user explicitly requested)
    # - Config exclusions only apply when not using --all (--all overrides config, not CLI)
    # - Skip all exclusions when filtering by specific notebooks or notes
    all_excluded_notebooks: list[str] | None = None
    if not effective_notebooks and not effective_notes:
        if show_all:
            # --all overrides config exclusions, but respect CLI --exclude-notebook
            all_excluded_notebooks = (
                list(exclude_notebook) if exclude_notebook else None
            )
        else:
            # Merge config exclusions with CLI exclusions
            config_excluded = config.excluded_notebooks() or []
            all_excluded_notebooks = list(set(config_excluded) | set(exclude_notebook))
            if not all_excluded_notebooks:
                all_excluded_notebooks = None

    # Convert to proper types
    notebooks_filter = effective_notebooks if effective_notebooks else None
    notes_filter = effective_notes if effective_notes else None

    # Run the review TUI
    run_review(
        scope=scope,
        tag=tag,
        priority=priority_int,
        notebooks=notebooks_filter,
        notes=notes_filter,
        exclude_notebooks=all_excluded_notebooks,
        include_no_due_date=include_no_due_date,
    )


@todo.command("all-done")
@click.argument("note_ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook to search in",
    shell_complete=complete_notebook,
)
@click.option(
    "--in-progress",
    "-i",
    "in_progress_only",
    is_flag=True,
    help="Only mark in-progress todos as completed (not pending)",
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def todo_all_done(
    note_ref: str, notebook: str | None, in_progress_only: bool, force: bool
) -> None:
    """Mark all todos in a note as completed.

    NOTE_REF can be:
    - A note name: "myproject", "friday"
    - A notebook/note path: "work/myproject", "daily/friday"
    - A note alias (from 'nb alias')

    Use --in-progress to only mark in-progress todos as completed,
    leaving pending todos unchanged.

    \b
    Examples:
      nb todo all-done friday                 # Friday's daily note
      nb todo all-done myproject -n work      # work/myproject.md
      nb todo all-done work/myproject         # Same as above
      nb todo all-done myalias                # By alias
      nb todo all-done friday -f              # Skip confirmation
      nb todo all-done friday --in-progress   # Only complete in-progress todos
    """
    from rich.prompt import Confirm

    from nb.cli.utils import resolve_note_ref
    from nb.utils.fuzzy import UserCancelled
    from nb.utils.hashing import normalize_path

    # Handle notebook/note format in note_ref
    if "/" in note_ref and not notebook:
        parts = note_ref.split("/", 1)
        notebook = parts[0]
        note_ref = parts[1]

    # Resolve the note
    try:
        note_path = resolve_note_ref(note_ref, notebook=notebook, ensure_exists=True)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if not note_path:
        console.print(f"[red]Note not found: {note_ref}[/red]")
        raise SystemExit(1)

    # Query incomplete todos for this note
    normalized_path = normalize_path(note_path)
    if in_progress_only:
        # Only get IN_PROGRESS todos (not PENDING)
        todos = query_todos(
            status=TodoStatus.IN_PROGRESS,
            notes=[normalized_path],
            parent_only=False,  # Include subtasks
            exclude_note_excluded=False,  # Don't exclude - user explicitly asked
        )
    else:
        # Get all incomplete todos (PENDING + IN_PROGRESS)
        todos = query_todos(
            completed=False,
            notes=[normalized_path],
            parent_only=False,  # Include subtasks
            exclude_note_excluded=False,  # Don't exclude - user explicitly asked
        )

    if not todos:
        if in_progress_only:
            console.print(f"[dim]No in-progress todos in {note_path.name}[/dim]")
        else:
            console.print(f"[dim]No incomplete todos in {note_path.name}[/dim]")
        return

    # Show confirmation unless --force
    if not force:
        if in_progress_only:
            console.print(
                f"\n[bold]Mark in-progress todos as done in:[/bold] {note_path.name}"
            )
            console.print(f"[dim]Found {len(todos)} in-progress todo(s)[/dim]")
        else:
            console.print(f"\n[bold]Mark all todos as done in:[/bold] {note_path.name}")
            console.print(f"[dim]Found {len(todos)} incomplete todo(s)[/dim]")

        for t in todos[:5]:
            console.print(
                f"  [dim]o[/dim] {t.content[:50]}{'...' if len(t.content) > 50 else ''}"
            )
        if len(todos) > 5:
            console.print(f"  [dim]... and {len(todos) - 5} more[/dim]")

        if not Confirm.ask("Mark all as completed?", default=True):
            console.print("[dim]Cancelled.[/dim]")
            return

    # Mark each todo as complete
    completed_count = 0
    for t in todos:
        try:
            actual_line = set_todo_status_in_file(
                t.source.path,
                t.line_number,
                TodoStatus.COMPLETED,
                expected_content=t.content,
            )
            if actual_line is not None:
                update_todo_status(t.id, TodoStatus.COMPLETED)
                completed_count += 1
        except PermissionError:
            # Skip linked files without sync, but don't fail entirely
            pass

    console.print(
        f"[green]Completed {completed_count} todo(s)[/green] in {note_path.name}"
    )


@todo.command("completed")
@click.option("--today", "-T", is_flag=True, help="Show todos completed today")
@click.option("--yesterday", "-Y", is_flag=True, help="Show todos completed yesterday")
@click.option("--week", "-W", is_flag=True, help="Show todos completed this week")
@click.option("--days", "-d", type=int, help="Show todos completed in last N days")
@click.option(
    "--notebook",
    "-n",
    multiple=True,
    help="Filter by notebook (repeatable)",
    shell_complete=complete_notebook,
)
@click.option("--tag", "-t", help="Filter by tag", shell_complete=complete_tag)
@click.option("--limit", "-l", type=int, default=50, help="Maximum number of todos")
def todo_completed(
    today: bool,
    yesterday: bool,
    week: bool,
    days: int | None,
    notebook: tuple[str, ...],
    tag: str | None,
    limit: int,
) -> None:
    """Show recently completed todos.

    View todos that were marked as completed within a specified time period.
    By default, shows todos completed in the last 7 days.

    \b
    Examples:
      nb todo completed                Show completed in last 7 days
      nb todo completed --today        Show completed today
      nb todo completed --week         Show completed this week
      nb todo completed -d 30          Show completed in last 30 days
      nb todo completed -n work        Show completed from work notebook
      nb todo completed -t project     Show completed todos tagged #project
    """
    # Ensure todos are indexed
    index_all_notes(index_vectors=False)

    config = get_config()

    # Resolve notebooks with fuzzy matching
    from nb.cli.utils import resolve_notebook
    from nb.utils.fuzzy import UserCancelled

    effective_notebooks: list[str] = []
    for nb_name in notebook:
        if config.get_notebook(nb_name):
            effective_notebooks.append(nb_name)
        else:
            try:
                resolved = resolve_notebook(nb_name)
            except UserCancelled:
                console.print("[dim]Cancelled.[/dim]")
                raise SystemExit(1) from None
            if resolved:
                effective_notebooks.append(resolved)
            else:
                raise SystemExit(1)

    # Determine date range
    today_date = date.today()
    if today and yesterday:
        start_date = today_date - timedelta(days=1)
        end_date = today_date
        period_label = "yesterday and today"
    elif today:
        start_date = end_date = today_date
        period_label = "today"
    elif yesterday:
        start_date = end_date = today_date - timedelta(days=1)
        period_label = "yesterday"
    elif week:
        week_start, week_end = get_week_range()
        start_date = week_start
        end_date = week_end
        period_label = "this week"
    elif days:
        start_date = today_date - timedelta(days=days)
        end_date = today_date
        period_label = f"last {days} days"
    else:
        # Default: last 7 days
        start_date = today_date - timedelta(days=7)
        end_date = today_date
        period_label = "last 7 days"

    # Query completed todos
    todos = query_todos(
        status=TodoStatus.COMPLETED,
        completed_date_start=start_date,
        completed_date_end=end_date,
        notebooks=effective_notebooks if effective_notebooks else None,
        tag=tag,
        parent_only=True,
        exclude_note_excluded=False,  # Show all completed todos
    )

    if not todos:
        console.print(f"[dim]No completed todos {period_label}.[/dim]")
        return

    # Group by completion date
    from nb.index.db import get_db

    db = get_db()
    todo_dates = {}
    for t in todos:
        row = db.fetchone("SELECT completed_date FROM todos WHERE id = ?", (t.id,))
        if row and row["completed_date"]:
            todo_dates[t.id] = date.fromisoformat(row["completed_date"])
        else:
            todo_dates[t.id] = t.created_date or today_date

    # Group todos by completion date
    by_date: dict[date, list] = {}
    for t in todos:
        d = todo_dates.get(t.id, today_date)
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(t)

    # Display header
    console.print(f"\n[bold]Completed Todos[/bold] ({period_label})\n")

    # Display grouped by date (newest first)
    displayed = 0
    for d in sorted(by_date.keys(), reverse=True):
        if displayed >= limit:
            break

        # Format date header
        if d == today_date:
            date_label = "Today"
        elif d == today_date - timedelta(days=1):
            date_label = "Yesterday"
        else:
            date_label = d.strftime("%A, %B %d")

        console.print(f"[bold cyan]{date_label}[/bold cyan]")

        for t in by_date[d]:
            if displayed >= limit:
                break

            # Get notebook display info
            nb_color, _ = get_notebook_display_info(t.notebook or "")

            # Truncate content if needed
            content = t.content
            max_content = 60
            if len(content) > max_content:
                content = content[: max_content - 3] + "..."

            # Format the todo line
            nb_display = f"[{nb_color}]{t.notebook}[/{nb_color}]" if t.notebook else ""
            console.print(f"  [green][x][/green] {content} [dim]{nb_display}[/dim]")
            displayed += 1

        console.print()  # Blank line between dates

    # Summary
    total = len(todos)
    if displayed < total:
        console.print(f"[dim]Showing {displayed} of {total} completed todos[/dim]")
    else:
        console.print(f"[dim]{total} todo(s) completed {period_label}[/dim]")


@todo.command("mv")
@click.argument("args", nargs=-1)
def todo_mv(args: tuple[str, ...]) -> None:
    """Move todos to a different note.

    The last argument is the destination note, all preceding arguments are todo IDs.
    Todos will be removed from their source files and added to the destination.

    Destination can include "::section" to specify a section heading.

    Note: Todo IDs will change after moving since IDs include the source path.

    \b
    Examples:
      nb todo mv abc123 work/project
      nb todo mv abc123 def456 work/project
      nb todo mv abc123 work/project::Tasks   # Add under "Tasks" section
      nb todo mv abc123 friday                # Move to today's Friday note
    """
    from nb.core.todos import move_todos_batch
    from nb.utils.fuzzy import UserCancelled

    if len(args) < 2:
        console.print("[red]Usage: nb todo mv <TODO_ID...> <dest-note>[/red]")
        console.print(
            "[dim]Last argument is destination, preceding are todo IDs.[/dim]"
        )
        raise SystemExit(1)

    todo_ids = list(args[:-1])
    dest_ref = args[-1]

    # Parse destination for note::section syntax
    section = None
    if "::" in dest_ref:
        dest_ref, section = dest_ref.split("::", 1)

    config = get_config()

    # Resolve todo IDs (allow partial matches)
    resolved_ids: list[str] = []
    todos_info: list[tuple[str, str]] = []  # (id, content) for display
    for tid in todo_ids:
        t = find_todo(tid)
        if not t:
            console.print(f"[red]Todo not found: {tid}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh, or 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)
        resolved_ids.append(t.id)
        todos_info.append((t.id[:TODO_ID_DISPLAY_LEN], t.content))

    # Resolve destination note
    try:
        dest_path = resolve_note_ref(dest_ref)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if not dest_path:
        console.print(f"[red]Could not resolve destination note: {dest_ref}[/red]")
        raise SystemExit(1)

    dest_display = get_display_path(dest_path)
    section_display = f"::{section}" if section else ""

    try:
        new_todos = move_todos_batch(
            resolved_ids, dest_path, section=section, notes_root=config.notes_root
        )

        console.print(
            f"\n[green]Moved {len(new_todos)} todo(s) to:[/green] {dest_display}{section_display}\n"
        )

        for (old_id, content), new_todo in zip(todos_info, new_todos, strict=True):
            new_id = new_todo.id[:TODO_ID_DISPLAY_LEN]
            # Truncate content if needed
            max_len = 50
            display_content = (
                content if len(content) <= max_len else content[: max_len - 3] + "..."
            )
            console.print(f"  {display_content}")
            console.print(f"    [dim]ID: {old_id} -> {new_id}[/dim]")

    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None
    except PermissionError as e:
        console.print(f"[red]{e}[/red]")
        console.print(
            "[dim]Hint: Use 'nb link --sync' to enable sync for external files.[/dim]"
        )
        raise SystemExit(1) from None


@todo.command("cp")
@click.argument("args", nargs=-1)
def todo_cp(args: tuple[str, ...]) -> None:
    """Copy todos to a different note.

    The last argument is the destination note, all preceding arguments are todo IDs.
    Original todos remain unchanged; copies are added to the destination.

    Destination can include "::section" to specify a section heading.

    Note: Copied todos will get new IDs since IDs include the source path.

    \b
    Examples:
      nb todo cp abc123 work/project
      nb todo cp abc123 def456 work/project
      nb todo cp abc123 work/project::Tasks   # Add under "Tasks" section
    """
    from nb.core.todos import copy_todos_batch
    from nb.utils.fuzzy import UserCancelled

    if len(args) < 2:
        console.print("[red]Usage: nb todo cp <TODO_ID...> <dest-note>[/red]")
        console.print(
            "[dim]Last argument is destination, preceding are todo IDs.[/dim]"
        )
        raise SystemExit(1)

    todo_ids = list(args[:-1])
    dest_ref = args[-1]

    # Parse destination for note::section syntax
    section = None
    if "::" in dest_ref:
        dest_ref, section = dest_ref.split("::", 1)

    config = get_config()

    # Resolve todo IDs (allow partial matches)
    resolved_ids: list[str] = []
    todos_info: list[str] = []  # content for display
    for tid in todo_ids:
        t = find_todo(tid)
        if not t:
            console.print(f"[red]Todo not found: {tid}[/red]")
            console.print(
                "[dim]Hint: Run 'nb index' to refresh, or 'nb todo' to list todos.[/dim]"
            )
            raise SystemExit(1)
        resolved_ids.append(t.id)
        todos_info.append(t.content)

    # Resolve destination note
    try:
        dest_path = resolve_note_ref(dest_ref)
    except UserCancelled:
        console.print("[dim]Cancelled.[/dim]")
        raise SystemExit(1) from None

    if not dest_path:
        console.print(f"[red]Could not resolve destination note: {dest_ref}[/red]")
        raise SystemExit(1)

    dest_display = get_display_path(dest_path)
    section_display = f"::{section}" if section else ""

    try:
        new_todos = copy_todos_batch(
            resolved_ids, dest_path, section=section, notes_root=config.notes_root
        )

        console.print(
            f"\n[green]Copied {len(new_todos)} todo(s) to:[/green] {dest_display}{section_display}\n"
        )

        for content, new_todo in zip(todos_info, new_todos, strict=True):
            new_id = new_todo.id[:TODO_ID_DISPLAY_LEN]
            # Truncate content if needed
            max_len = 50
            display_content = (
                content if len(content) <= max_len else content[: max_len - 3] + "..."
            )
            console.print(f"  {display_content}")
            console.print(f"    [dim]New ID: {new_id}[/dim]")

    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None
