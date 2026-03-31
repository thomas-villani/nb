"""Link-related CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.table import Table

from nb.cli.utils import console


def register_link_commands(cli: click.Group) -> None:
    """Register all link-related commands with the CLI."""
    cli.add_command(link)


@click.group()
def link() -> None:
    """Manage linked external files.

    Link external markdown files or directories to index them
    alongside your notes. Both todos and note content are indexed.
    """
    pass


@link.command("list")
def link_list() -> None:
    """List all linked external files.

    Shows alias, notebook, path, sync status, and todo exclusion status.
    """
    from nb.core.links import list_linked_notes

    linked_notes = list_linked_notes()

    if not linked_notes:
        console.print("[dim]No linked files.[/dim]")
        console.print("[dim]Use 'nb link add <path>' to add one.[/dim]")
        return

    table = Table(show_header=True, title="Linked Notes")
    table.add_column("Alias")
    table.add_column("Notebook")
    table.add_column("Section")
    table.add_column("Path")
    table.add_column("Sync")
    table.add_column("Todo Excl")
    table.add_column("Exists")

    for ln in linked_notes:
        exists = "[green]yes[/green]" if ln.path.exists() else "[red]no[/red]"
        sync = "[green]yes[/green]" if ln.sync else "[dim]no[/dim]"
        todo_excl = "[yellow]yes[/yellow]" if ln.todo_exclude else "[dim]no[/dim]"
        notebook = ln.notebook
        section = ln.section or "[dim]-[/dim]"
        path_str = str(ln.path)
        if ln.path.is_dir():
            path_str += "/" if ln.recursive else " (flat)"
        table.add_row(ln.alias, notebook, section, path_str, sync, todo_excl, exists)

    console.print(table)


@link.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.argument("notebook")
@click.option("--alias", "-a", help="Short name for the file (defaults to filename)")
@click.option(
    "--sync/--no-sync", default=True, help="Sync todo completions back to source"
)
@click.option("--section", "-s", help="Section within the notebook")
@click.option(
    "--no-recursive", is_flag=True, help="Don't scan subdirectories (for directories)"
)
@click.option(
    "--todo-exclude",
    is_flag=True,
    help="Exclude todos from 'nb todo' unless explicitly requested",
)
def link_add(
    path: str,
    notebook: str,
    alias: str | None,
    sync: bool,
    section: str | None,
    no_recursive: bool,
    todo_exclude: bool,
) -> None:
    """Link an external file or directory to a notebook.

    NOTEBOOK can use "notebook/section" syntax to specify both notebook
    and section in one argument (e.g., "projects/vizier").

    Linked notes are indexed like regular notes - both note content and todos
    are collected. Linked notes appear in 'nb list -n <notebook>'.

    With --sync (default), completing a todo will update the source file.
    With --todo-exclude, todos won't appear in 'nb todo' unless you filter
    by the notebook explicitly with -n.

    Examples:
        nb link add ~/work/TODO.md projects          # Link to projects notebook
        nb link add ~/repos/vizier projects/vizier    # Link to projects, section vizier
        nb link add ~/docs/wiki work -s docs          # Link to work, section docs
        nb link add ~/project/tasks.md work --todo-exclude  # Hide from nb todo

    """
    from nb.config import get_config
    from nb.core.links import add_linked_note
    from nb.index.scanner import index_single_linked_note

    p = Path(path)

    # Parse notebook/section syntax
    if "/" in notebook and section is None:
        config = get_config()
        nb_part, sec_part = notebook.split("/", 1)
        if config.get_notebook(nb_part):
            notebook = nb_part
            section = sec_part

    try:
        linked = add_linked_note(
            p,
            notebook=notebook,
            alias=alias,
            section=section,
            recursive=not no_recursive,
            todo_exclude=todo_exclude,
            sync=sync,
        )
        note_count = index_single_linked_note(linked.alias)

        display_target = f"{linked.notebook}/{linked.section}" if linked.section else linked.notebook
        console.print(f"[green]Linked:[/green] {linked.alias} -> {display_target}")
        console.print(f"[dim]Indexed {note_count} notes.[/dim]")
        if todo_exclude:
            console.print("[dim]Todos excluded from 'nb todo' by default.[/dim]")
        if not sync:
            console.print("[dim]Sync disabled - completions won't update source.[/dim]")

    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None


@link.command("remove")
@click.argument("alias")
def link_remove(alias: str) -> None:
    """Stop tracking a linked external file.

    This does not delete the file, just removes it from tracking.
    """
    from nb.core.links import get_linked_note, remove_linked_note
    from nb.index.scanner import remove_linked_note_from_index

    linked_note = get_linked_note(alias)
    if linked_note:
        remove_linked_note_from_index(alias)
        remove_linked_note(alias)
        console.print(f"[green]Removed link:[/green] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("sync")
@click.argument("alias", required=False)
def link_sync(alias: str | None) -> None:
    """Re-scan linked files and update index.

    If ALIAS is provided, only that linked note is scanned.
    Otherwise, all linked notes are scanned.
    """
    from nb.core.links import get_linked_note, list_linked_notes
    from nb.index.scanner import index_single_linked_note, scan_linked_notes

    if alias:
        linked_note = get_linked_note(alias)
        if linked_note:
            if not linked_note.path.exists():
                console.print(f"[red]Path does not exist: {linked_note.path}[/red]")
                raise SystemExit(1)
            note_count = index_single_linked_note(alias)
            console.print(f"[green]Synced:[/green] {note_count} notes")
        else:
            console.print(f"[red]Linked file not found: {alias}[/red]")
            raise SystemExit(1)
    else:
        note_total = scan_linked_notes()
        link_count = len(list_linked_notes())
        console.print(f"[green]Synced:[/green] {link_count} links ({note_total} notes)")


@link.command("enable-sync")
@click.argument("alias")
def link_enable_sync(alias: str) -> None:
    """Enable syncing completions back to a linked file."""
    from nb.core.links import update_linked_note_sync

    if update_linked_note_sync(alias, True):
        console.print(f"[green]Enabled sync for:[/green] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("disable-sync")
@click.argument("alias")
def link_disable_sync(alias: str) -> None:
    """Disable syncing completions back to a linked file.

    Todos will still be tracked, but completing them won't modify the source.
    """
    from nb.core.links import update_linked_note_sync

    if update_linked_note_sync(alias, False):
        console.print(f"[yellow]Disabled sync for:[/yellow] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("exclude-todos")
@click.argument("alias")
def link_exclude_todos(alias: str) -> None:
    """Exclude todos from this linked note from 'nb todo'.

    Todos will still be indexed, but won't appear in 'nb todo' unless
    you explicitly filter by this notebook with -n.
    """
    from nb.core.links import update_linked_note_todo_exclude

    if update_linked_note_todo_exclude(alias, True):
        console.print(f"[yellow]Excluded todos for:[/yellow] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)


@link.command("include-todos")
@click.argument("alias")
def link_include_todos(alias: str) -> None:
    """Include todos from this linked note in 'nb todo'."""
    from nb.core.links import update_linked_note_todo_exclude

    if update_linked_note_todo_exclude(alias, False):
        console.print(f"[green]Included todos for:[/green] {alias}")
    else:
        console.print(f"[red]Linked file not found: {alias}[/red]")
        raise SystemExit(1)
