"""Notebook-related CLI commands."""

from __future__ import annotations

import click
from rich.table import Table

from nb.cli.completion import complete_notebook
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
            if nb.date_mode == "daily":
                nb_type_parts.append("daily")
            elif nb.date_mode == "weekly":
                nb_type_parts.append("weekly")
            if nb.todo_exclude:
                nb_type_parts.append("excl")
            if nb.is_external:
                nb_type_parts.append("ext")
            nb_type = ", ".join(nb_type_parts) if nb_type_parts else "-"

            path_display = str(nb.path) if nb.is_external else f"~/notes/{nb.name}"
            table.add_row(nb.name, nb_type, note_count, path_display)

            # Show sections under the notebook
            for sec in nb.sections:
                sec_type_parts = ["section"]
                if sec.todo_exclude:
                    sec_type_parts.append("excl")
                sec_type = ", ".join(sec_type_parts)
                sec_path = f"~/notes/{nb.name}/{sec.name}"
                table.add_row(
                    f"  [dim]{sec.name}[/dim]",
                    f"[dim]{sec_type}[/dim]",
                    "[dim]-[/dim]",
                    f"[dim]{sec_path}[/dim]",
                )

        console.print(table)
    else:
        for nb in nbs:
            suffix = ""
            if nb.is_external:
                suffix = f" [dim](external: {nb.path})[/dim]"
            elif nb.date_mode == "weekly":
                suffix = " [dim](weekly)[/dim]"
            elif nb.date_mode == "daily":
                suffix = " [dim](daily)[/dim]"
            console.print(f"{nb.name}{suffix}")

            # Show sections under the notebook
            for sec in nb.sections:
                sec_suffix = " [dim](todo excluded)[/dim]" if sec.todo_exclude else ""
                console.print(f"  [dim]{sec.name}{sec_suffix}[/dim]")


@notebooks_cmd.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show details")
def notebooks_list(verbose: bool) -> None:
    """List all notebooks."""
    _list_notebooks(verbose)


@notebooks_cmd.command("create")
@click.argument("name")
@click.option("--from", "from_path", help="External path to use as notebook")
@click.option("--date-based", "-d", is_flag=True, help="Use daily date-based organization (one file per day)")
@click.option("--weekly", "-w", is_flag=True, help="Use weekly organization (one file per week with daily sections)")
@click.option(
    "--todo-exclude", "-x", is_flag=True, help="Exclude from nb todo by default"
)
def notebooks_create(
    name: str,
    from_path: str | None,
    date_based: bool,
    weekly: bool,
    todo_exclude: bool,
) -> None:
    """Create a new notebook.

    Examples:
        nb notebooks create ideas
        nb notebooks create work-log --date-based
        nb notebooks create journal --weekly
        nb notebooks create obsidian --from ~/Documents/Obsidian/vault
        nb notebooks create personal --todo-exclude

    """
    from nb.config import add_notebook, expand_path

    # Validate mutually exclusive flags
    if date_based and weekly:
        console.print("[red]Error:[/red] --date-based and --weekly are mutually exclusive")
        raise SystemExit(1)

    # Determine date_based value
    if weekly:
        date_based_value: str | bool = "weekly"
    elif date_based:
        date_based_value = True  # or "daily" - both work
    else:
        date_based_value = False

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
            date_based=date_based_value,
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

        if weekly:
            console.print(
                "[dim]Using weekly organization (YYYY/Week.md with daily sections)[/dim]"
            )
        elif date_based:
            console.print(
                "[dim]Using daily organization (YYYY/Week/YYYY-MM-DD.md)[/dim]"
            )
        if todo_exclude:
            console.print("[dim]Excluded from nb todo by default[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@notebooks_cmd.command("remove")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def notebooks_remove(name: str, force: bool) -> None:
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

    if not force:
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


@notebooks_cmd.command("merge")
@click.argument("source", shell_complete=complete_notebook)
@click.argument("target", shell_complete=complete_notebook)
@click.option("--section", "-s", help="Place notes into a subfolder/section in the target")
@click.option("--dry-run", is_flag=True, help="Preview what would be moved without doing it")
@click.option("--force", "-f", is_flag=True, help="Overwrite files if they already exist at destination")
@click.option(
    "--keep-source",
    is_flag=True,
    help="Keep the source notebook in configuration after merging (removed by default)",
)
def notebooks_merge(
    source: str,
    target: str,
    section: str | None,
    dry_run: bool,
    force: bool,
    keep_source: bool,
) -> None:
    """Merge all notes from one notebook into another.

    Moves every note from SOURCE into TARGET. Use --section to place
    them in a subfolder (e.g., merging a finished project into an archive).

    Subdirectory structure within the source is preserved. By default,
    the source notebook is removed from configuration after merging.

    \b
    Examples:
      nb notebooks merge myproject archive --section myproject
      nb notebooks merge old-ideas ideas
      nb notebooks merge work-2024 archive --section work-2024 --keep-source
      nb notebooks merge draft published --dry-run
      nb notebooks merge old new --force        # Overwrite conflicts

    """
    from nb.core.notebooks import merge_notebook

    # Show what will happen
    if section:
        dest_desc = f"'{target}/{section}/'"
    else:
        dest_desc = f"'{target}/'"

    if dry_run:
        console.print(f"[dim]Dry run: previewing merge of '{source}' into {dest_desc}[/dim]\n")

    try:
        moves = merge_notebook(
            source,
            target,
            section=section,
            force=force,
            dry_run=dry_run,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None
    except FileExistsError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None

    if not moves:
        console.print("[dim]No notes to merge.[/dim]")
        return

    if dry_run:
        for src, dst in moves:
            console.print(f"  {src} -> [cyan]{dst}[/cyan]")
        console.print(f"\n[dim]Would move {len(moves)} note(s). Run without --dry-run to apply.[/dim]")
        return

    console.print(f"[green]Merged {len(moves)} note(s)[/green] from '{source}' into {dest_desc}")

    # Register the section in the target notebook's config
    if section:
        config = get_config()
        source_config = config.get_notebook(source)
        source_excluded = source_config.todo_exclude if source_config else False

        from nb.config.models import SectionConfig

        target_config = config.get_notebook(target)
        if target_config:
            existing = next((s for s in target_config.sections if s.name == section), None)
            if existing:
                if source_excluded:
                    existing.todo_exclude = True
            else:
                target_config.sections.append(
                    SectionConfig(name=section, todo_exclude=source_excluded)
                )

            from nb.config.io import save_config as _save_config

            _save_config(config)
            if source_excluded:
                console.print(f"[dim]Section '{section}' inherits todo_exclude from '{source}'.[/dim]")

        # Warn about linked notes that reference the source notebook
        from nb.core.links import list_linked_notes

        linked = [ln for ln in list_linked_notes() if (ln.notebook or ln.alias) == source]
        if linked:
            aliases = ", ".join(ln.alias for ln in linked)
            console.print(
                f"[yellow]Note:[/yellow] Linked notes ({aliases}) have notebook '{source}'.\n"
                f"  View their todos with: [cyan]nb todo -n {target}/{section}[/cyan]"
            )

    if not keep_source:
        from nb.config import remove_notebook

        if remove_notebook(source):
            console.print(f"[dim]Removed '{source}' from notebook configuration.[/dim]")
