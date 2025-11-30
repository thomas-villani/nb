"""Notebook-related CLI commands."""

from __future__ import annotations

import click
from rich.table import Table

from nb.cli.utils import console
from nb.config import get_config
from nb.core.notebooks import get_notebook_notes


def register_notebook_commands(cli: click.Group) -> None:
    """Register all notebook-related commands with the CLI."""
    cli.add_command(notebooks_cmd)


@click.group("notebooks", invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Show note counts")
@click.pass_context
def notebooks_cmd(ctx: click.Context, verbose: bool) -> None:
    """Manage notebooks.

    Run without a subcommand to list all notebooks.
    """
    if ctx.invoked_subcommand is None:
        _list_notebooks(verbose)


def _list_notebooks(verbose: bool = False) -> None:
    """List all notebooks."""
    config = get_config()
    nbs = config.notebooks

    if not nbs:
        console.print("[dim]No notebooks found.[/dim]")
        return

    if verbose:
        table = Table(show_header=True)
        table.add_column("Notebook")
        table.add_column("Type")
        table.add_column("Notes", justify="right")
        table.add_column("Path")

        for nb in nbs:
            nb_path = config.get_notebook_path(nb.name)
            if nb_path and nb_path.exists():
                notes = get_notebook_notes(nb.name)
                note_count = str(len(notes))
            else:
                note_count = "[dim]-[/dim]"

            nb_type_parts = []
            if nb.date_based:
                nb_type_parts.append("date")
            if nb.todo_exclude:
                nb_type_parts.append("excl")
            if nb.is_external:
                nb_type_parts.append("ext")
            nb_type = ", ".join(nb_type_parts) if nb_type_parts else "-"

            path_display = str(nb.path) if nb.is_external else f"~/{nb.name}"
            table.add_row(nb.name, nb_type, note_count, path_display)

        console.print(table)
    else:
        for nb in nbs:
            suffix = ""
            if nb.is_external:
                suffix = f" [dim](external: {nb.path})[/dim]"
            elif nb.date_based:
                suffix = " [dim](date-based)[/dim]"
            console.print(f"{nb.name}{suffix}")


@notebooks_cmd.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show details")
def notebooks_list(verbose: bool) -> None:
    """List all notebooks."""
    _list_notebooks(verbose)


@notebooks_cmd.command("create")
@click.argument("name")
@click.option("--from", "from_path", help="External path to use as notebook")
@click.option("--date-based", "-d", is_flag=True, help="Use date-based organization")
@click.option(
    "--todo-exclude", "-x", is_flag=True, help="Exclude from nb todo by default"
)
def notebooks_create(
        name: str,
        from_path: str | None,
        date_based: bool,
        todo_exclude: bool,
) -> None:
    """Create a new notebook.

    Examples:
        nb notebooks create ideas
        nb notebooks create work-log --date-based
        nb notebooks create obsidian --from ~/Documents/Obsidian/vault
        nb notebooks create personal --todo-exclude

    """
    from nb.config import add_notebook, expand_path

    # Validate external path if provided
    ext_path = None
    if from_path:
        ext_path = expand_path(from_path)
        if not ext_path.exists():
            console.print(f"[red]Path does not exist:[/red] {ext_path}")
            raise SystemExit(1)
        if not ext_path.is_dir():
            console.print(f"[red]Path is not a directory:[/red] {ext_path}")
            raise SystemExit(1)

    try:
        nb = add_notebook(
            name=name,
            date_based=date_based,
            todo_exclude=todo_exclude,
            path=ext_path,
        )

        if nb.is_external:
            console.print(
                f"[green]Created external notebook:[/green] {name} -> {ext_path}"
            )
        else:
            config = get_config()
            console.print(f"[green]Created notebook:[/green] {name}")
            console.print(f"[dim]Location: {config.notes_root / name}[/dim]")

        if date_based:
            console.print(
                "[dim]Using date-based organization (YYYY/Week/YYYY-MM-DD.md)[/dim]"
            )
        if todo_exclude:
            console.print("[dim]Excluded from nb todo by default[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@notebooks_cmd.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def notebooks_remove(name: str, yes: bool) -> None:
    """Remove a notebook from configuration.

    Note: This only removes the notebook from nb's configuration.
    The actual files are NOT deleted.
    """
    from nb.config import remove_notebook

    config = get_config()
    nb = config.get_notebook(name)

    if nb is None:
        console.print(f"[red]Notebook not found:[/red] {name}")
        raise SystemExit(1)

    if not yes:
        if nb.is_external:
            console.print(f"Remove external notebook '{name}' from configuration?")
            console.print(f"[dim]Path: {nb.path}[/dim]")
        else:
            console.print(f"Remove notebook '{name}' from configuration?")
            console.print("[dim]Files will NOT be deleted.[/dim]")

        if not click.confirm("Continue?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    if remove_notebook(name):
        console.print(f"[green]Removed notebook:[/green] {name}")
    else:
        console.print(f"[red]Failed to remove notebook:[/red] {name}")
