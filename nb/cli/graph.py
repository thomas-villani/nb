"""Graph visualization CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from nb.cli.completion import complete_notebook
from nb.cli.utils import console, resolve_note_ref
from nb.config import get_config


def register_graph_commands(cli: click.Group) -> None:
    """Register graph commands with the CLI."""
    cli.add_command(graph_cmd)


@click.command("graph")
@click.argument("note_ref", required=False)
@click.option(
    "--notebook",
    "-n",
    help="Notebook context for resolving note reference",
    shell_complete=complete_notebook,
)
@click.option(
    "--depth",
    "-d",
    default=1,
    type=int,
    help="Depth of connections to show (default: 1)",
)
@click.option(
    "--no-tags",
    is_flag=True,
    help="Don't show tag connections",
)
@click.option(
    "--links-only",
    is_flag=True,
    help="Only show direct note-to-note links",
)
def graph_cmd(
    note_ref: str | None,
    notebook: str | None,
    depth: int,
    no_tags: bool,
    links_only: bool,
) -> None:
    """Show an ASCII graph of note connections.

    If NOTE_REF is provided, shows connections for that note.
    Otherwise shows a summary of the entire knowledge graph.

    \b
    Examples:
      nb graph                    Overview of all connections
      nb graph today              Connections for today's note
      nb graph myproject -d 2     Show 2 levels of connections
      nb graph --links-only       Only show note-to-note links
    """
    if note_ref:
        _show_note_graph(note_ref, notebook, depth, no_tags, links_only)
    else:
        _show_overview_graph(no_tags)


def _show_overview_graph(no_tags: bool) -> None:
    """Show an overview of the entire knowledge graph."""
    from nb.index.db import get_db

    db = get_db()

    # Get counts
    note_count = db.fetchone("SELECT COUNT(*) as cnt FROM notes WHERE external = 0")
    link_count = db.fetchone(
        "SELECT COUNT(*) as cnt FROM note_links WHERE is_external = 0"
    )
    tag_count = db.fetchone("SELECT COUNT(DISTINCT tag) as cnt FROM note_tags")
    notebook_count = db.fetchone(
        "SELECT COUNT(DISTINCT notebook) as cnt FROM notes WHERE external = 0"
    )

    console.print("[bold]Knowledge Graph Overview[/bold]\n")

    # Node counts
    console.print("[cyan]Nodes:[/cyan]")
    console.print(f"  Notes:     {note_count['cnt'] if note_count else 0}")
    console.print(f"  Notebooks: {notebook_count['cnt'] if notebook_count else 0}")
    if not no_tags:
        console.print(f"  Tags:      {tag_count['cnt'] if tag_count else 0}")

    # Edge counts
    console.print("\n[cyan]Edges:[/cyan]")
    console.print(f"  Links:     {link_count['cnt'] if link_count else 0}")

    # Most connected notes
    console.print("\n[cyan]Most Connected Notes:[/cyan]")
    top_notes = db.fetchall(
        """SELECT source_path, COUNT(*) as cnt
           FROM note_links WHERE is_external = 0
           GROUP BY source_path ORDER BY cnt DESC LIMIT 10"""
    )
    for row in top_notes:
        path = Path(row["source_path"])
        console.print(f"  {path.stem}: {row['cnt']} outgoing links")

    # Most linked-to notes
    console.print("\n[cyan]Most Referenced Notes:[/cyan]")
    most_referenced = db.fetchall(
        """SELECT target_path, COUNT(*) as cnt
           FROM note_links WHERE is_external = 0
           GROUP BY target_path ORDER BY cnt DESC LIMIT 10"""
    )
    for row in most_referenced:
        target = row["target_path"]
        console.print(f"  {target}: {row['cnt']} incoming links")

    if not no_tags:
        # Most used tags
        console.print("\n[cyan]Most Used Tags:[/cyan]")
        top_tags = db.fetchall(
            """SELECT tag, COUNT(*) as cnt
               FROM note_tags GROUP BY tag ORDER BY cnt DESC LIMIT 10"""
        )
        for row in top_tags:
            console.print(f"  #{row['tag']}: {row['cnt']} notes")


def _show_note_graph(
    note_ref: str,
    notebook: str | None,
    depth: int,
    no_tags: bool,
    links_only: bool,
) -> None:
    """Show the connection graph for a specific note."""
    from nb.core.note_links import get_backlinks, get_outgoing_links
    from nb.index.db import get_db

    config = get_config()

    # Resolve note reference
    path = resolve_note_ref(note_ref, notebook=notebook)
    if not path:
        raise SystemExit(1)

    # Get relative path for display
    try:
        display_path = path.relative_to(config.notes_root)
    except ValueError:
        display_path = path

    console.print(f"[bold]Graph for {display_path}[/bold]\n")

    # Get outgoing links
    outgoing = get_outgoing_links(path, internal_only=True)
    # Get backlinks
    backlinks = get_backlinks(path)

    # Get tags for this note
    db = get_db()
    note_tags = []
    if not no_tags and not links_only:
        tag_rows = db.fetchall(
            "SELECT tag FROM note_tags WHERE note_path = ?",
            (str(display_path).replace("\\", "/"),),
        )
        note_tags = [row["tag"] for row in tag_rows]

    # Build the ASCII graph
    lines = []

    # Center node
    lines.append(f"[bold cyan]┌─ {display_path.stem} ─┐[/bold cyan]")

    # Outgoing links
    if outgoing:
        lines.append("")
        lines.append("[green]↓ Links to:[/green]")
        for i, link in enumerate(outgoing):
            prefix = "└──" if i == len(outgoing) - 1 else "├──"
            target_display = link.target
            if link.resolved_path:
                target_display = link.resolved_path.stem
            link_type = f"[dim]({link.link_type})[/dim]"
            lines.append(f"  {prefix} {target_display} {link_type}")

            # Show second level if depth > 1
            if depth > 1 and link.resolved_path:
                second_level = get_outgoing_links(
                    link.resolved_path, internal_only=True
                )
                for j, sl in enumerate(second_level[:3]):  # Limit to 3
                    sub_prefix = (
                        "    └──" if j == len(second_level[:3]) - 1 else "    ├──"
                    )
                    sl_display = (
                        sl.resolved_path.stem if sl.resolved_path else sl.target
                    )
                    lines.append(f"  {sub_prefix} {sl_display}")
                if len(second_level) > 3:
                    lines.append(
                        f"      [dim]... and {len(second_level) - 3} more[/dim]"
                    )
    else:
        lines.append("")
        lines.append("[dim]↓ No outgoing links[/dim]")

    # Backlinks
    if backlinks:
        lines.append("")
        lines.append("[yellow]↑ Linked from:[/yellow]")
        for i, bl in enumerate(backlinks):
            prefix = "└──" if i == len(backlinks) - 1 else "├──"
            source_name = bl.source_path.stem
            link_type = f"[dim]({bl.link_type})[/dim]"
            line_info = f"[dim]:L{bl.line_number}[/dim]" if bl.line_number else ""
            lines.append(f"  {prefix} {source_name}{line_info} {link_type}")
    else:
        lines.append("")
        lines.append("[dim]↑ No backlinks[/dim]")

    # Tags
    if note_tags and not links_only:
        lines.append("")
        lines.append("[magenta]# Tags:[/magenta]")
        for i, tag in enumerate(note_tags):
            prefix = "└──" if i == len(note_tags) - 1 else "├──"
            # Find other notes with this tag
            related = db.fetchall(
                "SELECT note_path FROM note_tags WHERE tag = ? AND note_path != ?",
                (tag, str(display_path).replace("\\", "/")),
            )
            count = len(related)
            lines.append(f"  {prefix} #{tag} [dim]({count} other notes)[/dim]")

    # Print the graph
    for line in lines:
        console.print(line)

    # Summary
    console.print("")
    console.print(
        f"[dim]{len(outgoing)} outgoing, {len(backlinks)} incoming"
        + (f", {len(note_tags)} tags" if note_tags else "")
        + "[/dim]"
    )
