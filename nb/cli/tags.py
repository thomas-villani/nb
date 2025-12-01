"""Tag-related CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.table import Table

from nb.cli.completion import complete_notebook
from nb.cli.utils import console
from nb.index.todos_repo import get_tag_stats


def register_tags_commands(cli: click.Group) -> None:
    """Register all tag-related commands with the CLI."""
    cli.add_command(tags_cmd)


@click.command("tags")
@click.option(
    "--sources", "-s", is_flag=True, help="Show source notebooks/notes for each tag"
)
@click.option(
    "--sort",
    type=click.Choice(["count", "alpha"]),
    default="count",
    help="Sort order (default: by count)",
)
@click.option(
    "--notebook",
    "-n",
    "notebooks",
    multiple=True,
    help="Filter by notebook",
    shell_complete=complete_notebook,
)
@click.option("--limit", "-l", type=int, help="Limit number of tags shown")
@click.option(
    "--open",
    "-o",
    "open_todos",
    is_flag=True,
    help="Only count open (non-completed) todos",
)
def tags_cmd(
    sources: bool,
    sort: str,
    notebooks: tuple[str, ...],
    limit: int | None,
    open_todos: bool,
) -> None:
    """List all tags with usage counts.

    Shows tags used across all todos, sorted by frequency.

    \b
    Examples:
      nb tags                   List all tags by count
      nb tags --sort alpha      Alphabetical order
      nb tags --sources         Show which notes use each tag
      nb tags -n work           Tags from work notebook only
      nb tags --limit 10        Top 10 tags
      nb tags --open            Only count open todos
    """
    # Get tag statistics
    tag_stats = get_tag_stats(
        include_sources=sources,
        notebooks=list(notebooks) if notebooks else None,
        completed=False if open_todos else None,
    )

    if not tag_stats:
        console.print("[dim]No tags found.[/dim]")
        return

    # Sort if needed
    if sort == "alpha":
        tag_stats = sorted(tag_stats, key=lambda t: t["tag"])

    # Apply limit
    if limit:
        tag_stats = tag_stats[:limit]

    total_tags = len(tag_stats)
    console.print(f"[bold]Tags[/bold] ({total_tags} total)\n")

    if sources:
        # Detailed view with sources
        for tag_data in tag_stats:
            tag = tag_data["tag"]
            count = tag_data["count"]
            console.print(f"[cyan]#{tag}[/cyan] ({count})")

            # Group sources by notebook
            sources_by_notebook: dict[str, list[tuple[str, int]]] = {}
            for src in tag_data.get("sources", []):
                nb = src["notebook"]
                if nb not in sources_by_notebook:
                    sources_by_notebook[nb] = []
                # Extract note name from path
                note_name = _get_note_name(src["path"])
                sources_by_notebook[nb].append((note_name, src["count"]))

            for nb, note_list in sorted(sources_by_notebook.items()):
                # Sum counts for this notebook
                nb_count = sum(c for _, c in note_list)
                console.print(f"  [dim]{nb}[/dim] ({nb_count})")
                # Show individual notes (limit to top 3 per notebook)
                for note_name, note_count in sorted(note_list, key=lambda x: -x[1])[:3]:
                    console.print(f"    [dim]{note_name}[/dim] ({note_count})")
                if len(note_list) > 3:
                    console.print(f"    [dim]... and {len(note_list) - 3} more[/dim]")

            console.print()
    else:
        # Simple table view
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Tag", style="cyan")
        table.add_column("Count", justify="right")

        for tag_data in tag_stats:
            table.add_row(f"#{tag_data['tag']}", str(tag_data["count"]))

        console.print(table)


def _get_note_name(path: str) -> str:
    """Extract a readable note name from a path."""
    p = Path(path)
    # Get the stem (filename without extension)
    name = p.stem
    # If it looks like a date, keep it simple
    if name and len(name) == 10 and name[4] == "-":
        return name
    # Otherwise, include parent dir for context
    if p.parent.name:
        return f"{p.parent.name}/{name}"
    return name
