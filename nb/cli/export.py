"""Export command for nb-cli."""

from __future__ import annotations

from pathlib import Path

import click

from nb.cli.completion import complete_notebook
from nb.cli.utils import console, get_display_path, resolve_note_ref
from nb.config import get_config
from nb.utils.fuzzy import UserCancelled


def register_export_commands(cli: click.Group) -> None:
    """Register export commands with the CLI."""
    cli.add_command(export_cmd)


@click.command("export")
@click.argument("note_ref")
@click.argument("output")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["pdf", "docx", "html"], case_sensitive=False),
    help="Output format (inferred from extension if not provided)",
)
@click.option(
    "--notebook",
    "-n",
    help="Notebook containing the note",
    shell_complete=complete_notebook,
)
@click.option(
    "--sort",
    "-s",
    "sort_by",
    type=click.Choice(["date", "modified", "name"], case_sensitive=False),
    default="date",
    help="Sort order for notebook export (default: date, oldest first)",
)
@click.option(
    "--reverse",
    "-r",
    is_flag=True,
    help="Reverse sort order (newest/last first)",
)
def export_cmd(
    note_ref: str,
    output: str,
    fmt: str | None,
    notebook: str | None,
    sort_by: str,
    reverse: bool,
) -> None:
    """Export a note or notebook to PDF, DOCX, or HTML.

    NOTE_REF can be:
    - A note path, name, alias, or date (for single note export)
    - A notebook name (exports all notes concatenated)

    OUTPUT is the destination filename.

    Format is inferred from the output extension if --format is not specified.

    When exporting a notebook, notes are sorted by date (oldest first) by default.
    Use --sort to change the order, and --reverse to flip it.

    \b
    Examples:
      # Single note export
      nb export friday report.pdf
      nb export work/project documentation.docx
      nb export myalias output.html

      # Notebook export (all notes concatenated)
      nb export daily/ journal.pdf
      nb export work/ work-notes.docx --sort modified
      nb export daily/ archive.pdf --sort date --reverse
    """
    from nb.core.export import export_note, export_notebook

    config = get_config()

    # Check if note_ref is a notebook (ends with / or matches a notebook name)
    is_notebook = False
    notebook_path: Path | None = None

    # Strip trailing slash for checking
    ref_clean = note_ref.rstrip("/")

    # Check if it's a notebook directory
    potential_nb_path = config.notes_root / ref_clean
    if potential_nb_path.is_dir():
        is_notebook = True
        notebook_path = potential_nb_path

    # Also check configured notebooks by name
    if not is_notebook:
        for nb_config in config.notebooks:
            if nb_config.name == ref_clean:
                nb_path = nb_config.path or (config.notes_root / nb_config.name)
                if nb_path.is_dir():
                    is_notebook = True
                    notebook_path = nb_path
                    break

    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    if is_notebook and notebook_path:
        # Export entire notebook
        try:
            result, count = export_notebook(
                notebook_path,
                output_path,
                format=fmt,
                sort_by=sort_by,  # type: ignore[arg-type]
                reverse=reverse,
                notes_root=config.notes_root,
            )
            sort_desc = f"{sort_by}"
            if reverse:
                sort_desc += " (reversed)"
            console.print(
                f"[green]Exported {count} notes from {ref_clean}/:[/green] {result}"
            )
            console.print(f"[dim]Sorted by: {sort_desc}[/dim]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None
        except Exception as e:
            console.print(f"[red]Export failed: {e}[/red]")
            raise SystemExit(1) from None
    else:
        # Export single note
        try:
            source_path = resolve_note_ref(note_ref, notebook=notebook)
        except UserCancelled:
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(1) from None

        if not source_path:
            console.print(f"[red]Could not resolve note: {note_ref}[/red]")
            raise SystemExit(1)

        display_source = get_display_path(source_path)

        try:
            result = export_note(source_path, output_path, format=fmt)
            console.print(f"[green]Exported:[/green] {display_source} -> {result}")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None
        except Exception as e:
            console.print(f"[red]Export failed: {e}[/red]")
            raise SystemExit(1) from None
