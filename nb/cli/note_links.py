"""Note link CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click

from nb.cli.completion import complete_notebook
from nb.cli.utils import console, resolve_note_ref
from nb.config import get_config

if TYPE_CHECKING:
    from nb.core.note_links import NoteLink


def register_note_link_commands(cli: click.Group) -> None:
    """Register note link commands with the CLI."""
    cli.add_command(links_cmd)
    cli.add_command(backlinks_cmd)


@click.command("links")
@click.argument("note_ref", required=False)
@click.option(
    "--notebook",
    "-n",
    help="Notebook context for resolving note reference",
    shell_complete=complete_notebook,
)
@click.option(
    "--internal",
    "-i",
    is_flag=True,
    help="Show only internal links",
)
@click.option(
    "--external",
    "-e",
    is_flag=True,
    help="Show only external links",
)
@click.option(
    "--check",
    "-c",
    is_flag=True,
    help="Check for broken links (across all notes if no note specified)",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON",
)
def links_cmd(
    note_ref: str | None,
    notebook: str | None,
    internal: bool,
    external: bool,
    check: bool,
    as_json: bool,
) -> None:
    """Show outgoing links from a note.

    If no note is specified with --check, checks all notes for broken links.

    \b
    Examples:
      nb links today              Links from today's note
      nb links projects/myproject Links from specific note
      nb links --check            Check all notes for broken links
      nb links today --check      Check links in today's note
      nb links -i                 Show only internal links
      nb links -e                 Show only external links
    """
    from nb.core.note_links import get_outgoing_links

    config = get_config()

    # Handle --check mode
    if check:
        _check_broken_links(note_ref, notebook, as_json)
        return

    # Require note_ref for normal mode
    if not note_ref:
        console.print("[red]Please specify a note reference.[/red]")
        console.print("[dim]Use --check to check all notes for broken links.[/dim]")
        raise SystemExit(1)

    # Resolve note reference
    path = resolve_note_ref(note_ref, notebook=notebook)
    if not path:
        raise SystemExit(1)

    # Get links
    links = get_outgoing_links(path, internal_only=internal, external_only=external)

    if as_json:
        output = [
            {
                "target": link.target,
                "display_text": link.display_text,
                "link_type": link.link_type,
                "is_external": link.is_external,
                "resolved_path": (
                    str(link.resolved_path) if link.resolved_path else None
                ),
            }
            for link in links
        ]
        console.print(json.dumps(output, indent=2))
        return

    if not links:
        console.print(f"[dim]No links found in {path.name}[/dim]")
        return

    # Display relative path
    try:
        display_path = path.relative_to(config.notes_root)
    except ValueError:
        display_path = path

    console.print(f"[bold]Outgoing links from {display_path}[/bold]\n")

    # Group by internal/external
    internal_links = [lnk for lnk in links if not lnk.is_external]
    external_links = [lnk for lnk in links if lnk.is_external]

    if internal_links:
        console.print("[cyan]Internal:[/cyan]")
        for link in internal_links:
            _display_link(link, config.notes_root)
        console.print()

    if external_links:
        console.print("[cyan]External:[/cyan]")
        for link in external_links:
            _display_link(link, config.notes_root)
        console.print()

    # Summary
    console.print(
        f"[dim]{len(links)} links ({len(internal_links)} internal, {len(external_links)} external)[/dim]"
    )


def _display_link(link: NoteLink, notes_root: Path) -> None:
    """Display a single link with formatting."""

    # Format based on link type
    if link.link_type == "wiki":
        link_text = f"[[{link.target}]]"
    elif link.link_type == "markdown":
        link_text = f"[{link.display_text}]({link.target})"
    else:
        link_text = f"{link.display_text} ({link.target})"

    # Show resolved path for internal links
    if not link.is_external:
        if link.resolved_path:
            try:
                resolved = link.resolved_path.relative_to(notes_root)
            except ValueError:
                resolved = link.resolved_path
            console.print(f"  {link_text} [dim]→ {resolved}[/dim]")
        else:
            console.print(f"  {link_text} [red](broken)[/red]")
    else:
        console.print(f"  {link_text}")


def _check_broken_links(
    note_ref: str | None,
    notebook: str | None,
    as_json: bool,
) -> None:
    """Check for broken links in one or all notes."""
    from nb.core.note_links import get_broken_links

    # config = get_config()
    # Resolve specific note if provided
    note_path = None
    if note_ref:
        note_path = resolve_note_ref(note_ref, notebook=notebook)
        if not note_path:
            raise SystemExit(1)

    # Get broken links
    broken = get_broken_links(note_path)

    if as_json:
        output = [
            {
                "source_path": str(b.source_path),
                "target": b.target,
                "display_text": b.display_text,
                "link_type": b.link_type,
                "suggestion": b.suggestion,
            }
            for b in broken
        ]
        console.print(json.dumps(output, indent=2))
        return

    if not broken:
        if note_ref:
            console.print(
                f"[green]No broken links in {note_path.name if note_path else note_ref}[/green]"
            )
        else:
            console.print("[green]No broken links found.[/green]")
        return

    console.print("[bold red]Broken links found:[/bold red]\n")

    # Group by source file
    by_source: dict[str, list] = {}
    for b in broken:
        src = str(b.source_path)
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(b)

    for source, links in sorted(by_source.items()):
        console.print(f"[bold]{source}:[/bold]")
        for link in links:
            if link.link_type == "wiki":
                link_text = f"[[{link.target}]]"
            else:
                link_text = f"[{link.display_text}]({link.target})"

            line_info = f"Line {link.line_number}: " if link.line_number else ""
            console.print(f"  {line_info}{link_text} [red]- not found[/red]")

            if link.suggestion:
                console.print(f"    [dim]Did you mean: {link.suggestion}?[/dim]")
        console.print()

    console.print(f"[red]{len(broken)} broken links in {len(by_source)} notes[/red]")


@click.command("backlinks")
@click.argument("note_ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook context for resolving note reference",
    shell_complete=complete_notebook,
)
@click.option(
    "--count",
    "-c",
    is_flag=True,
    help="Show only the count",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON",
)
def backlinks_cmd(
    note_ref: str,
    notebook: str | None,
    count: bool,
    as_json: bool,
) -> None:
    """Show notes that link to the specified note.

    \b
    Examples:
      nb backlinks projects/myproject     Notes linking to myproject
      nb backlinks today                  Notes linking to today's note
      nb backlinks myproject -c           Just show the count
    """
    from nb.core.note_links import get_backlinks

    config = get_config()

    # Resolve note reference
    path = resolve_note_ref(note_ref, notebook=notebook)
    if not path:
        raise SystemExit(1)

    # Get backlinks
    backlinks = get_backlinks(path)

    if as_json:
        output = [
            {
                "source_path": str(b.source_path),
                "display_text": b.display_text,
                "link_type": b.link_type,
                "line_number": b.line_number,
            }
            for b in backlinks
        ]
        console.print(json.dumps(output, indent=2))
        return

    # Display relative path
    try:
        display_path = path.relative_to(config.notes_root)
    except ValueError:
        display_path = path

    if count:
        console.print(f"{len(backlinks)} backlinks to {display_path}")
        return

    if not backlinks:
        console.print(f"[dim]No notes link to {display_path}[/dim]")
        return

    console.print(f"[bold]Notes linking to {display_path}[/bold]\n")

    for b in backlinks:
        # Format source path
        source_display = str(b.source_path)

        # Show link type indicator
        if b.link_type == "wiki":
            link_indicator = "[[...]]"
        elif b.link_type == "markdown":
            link_indicator = "[...](...)"
        else:
            link_indicator = "frontmatter"

        line_info = f":{b.line_number}" if b.line_number else ""
        console.print(
            f"  [cyan]{source_display}{line_info}[/cyan] [dim]({link_indicator})[/dim]"
        )

    console.print(f"\n[dim]{len(backlinks)} backlinks[/dim]")
