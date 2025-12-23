"""Attachment-related CLI commands."""

from __future__ import annotations

import click

from nb.cli.completion import complete_notebook
from nb.cli.utils import console, ensure_note_path, resolve_attachment_target


def register_attachment_commands(cli: click.Group) -> None:
    """Register all attachment-related commands with the CLI."""
    cli.add_command(attach)


@click.group()
def attach() -> None:
    """Manage file attachments.

    Attach files or URLs to notes and todos. Files can be linked
    (referenced in place) or copied to the attachments directory.
    """
    pass


@attach.command("file")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--to", "target", help="Note path or todo ID to attach to")
@click.option("--title", "-t", help="Display title for the attachment")
@click.option("--copy", "-c", is_flag=True, help="Copy file to attachments directory")
def attach_file(
    file_path: str, target: str | None, title: str | None, copy: bool
) -> None:
    """Attach a file to a note or todo.

    By default attaches to today's daily note. Use --to to specify a target.

    Examples:
        nb attach file ./document.pdf
        nb attach file ~/image.png --to daily/2025-11-27.md
        nb attach file report.pdf --to abc12345 --copy

    """
    from nb.core.attachments import attach_to_note, attach_to_todo

    note_path, todo = resolve_attachment_target(target)

    if todo:
        try:
            attachment = attach_to_todo(
                todo.source.path,
                todo.line_number,
                file_path,
                title=title,
                copy=copy,
            )
            console.print(f"[green]Attached:[/green] {attachment.path}")
            console.print(f"[dim]To todo: {todo.content[:50]}...[/dim]")
            return
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None

    if not note_path:
        raise SystemExit(1)

    try:
        attachment = attach_to_note(note_path, file_path, title=title, copy=copy)
        console.print(f"[green]Attached:[/green] {attachment.path}")
        console.print(f"[dim]To: {note_path.name}[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None


@attach.command("url")
@click.argument("url")
@click.option("--to", "target", help="Note path or todo ID to attach to")
@click.option("--title", "-t", help="Display title for the URL")
def attach_url(url: str, target: str | None, title: str | None) -> None:
    """Attach a URL to a note or todo.

    By default attaches to today's daily note. Use --to to specify a target.

    Examples:
        nb attach url https://example.com/doc
        nb attach url https://github.com/repo --to projects/myproject.md

    """
    from nb.core.attachments import attach_to_note, attach_to_todo

    note_path, todo = resolve_attachment_target(target)

    if todo:
        try:
            attachment = attach_to_todo(
                todo.source.path,
                todo.line_number,
                url,
                title=title,
                copy=False,
            )
            console.print(f"[green]Attached:[/green] {attachment.path}")
            console.print(f"[dim]To todo: {todo.content[:50]}...[/dim]")
            return
        except Exception as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1) from None

    if not note_path:
        raise SystemExit(1)

    try:
        attachment = attach_to_note(note_path, url, title=title, copy=False)
        console.print(f"[green]Attached:[/green] {attachment.path}")
        console.print(f"[dim]To: {note_path.name}[/dim]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None


@attach.command("list")
@click.argument("target", required=False)
@click.option(
    "--all",
    "-a",
    "list_all",
    is_flag=True,
    help="List all attachments across all notes",
)
@click.option(
    "--type",
    "attach_type",
    type=click.Choice(["file", "url"]),
    help="Filter by type",
)
@click.option(
    "--notebook", "-n", help="Filter by notebook", shell_complete=complete_notebook
)
def attach_list(
    target: str | None,
    list_all: bool,
    attach_type: str | None,
    notebook: str | None,
) -> None:
    """List attachments in a note or across all notes.

    Shows all @attach lines in the specified note (or today's note by default).
    Use --all to list all attachments across the entire database.

    Examples:
        nb attach list
        nb attach list daily/2025-11-27.md
        nb attach list --all
        nb attach list --all --type file
        nb attach list --all --notebook projects

    """
    from datetime import date

    from nb.core.attachments import list_attachments_in_file, resolve_attachment_path
    from nb.core.notes import ensure_daily_note
    from nb.models import Attachment

    # If --all flag, query from database
    if list_all:
        from nb.index.attachments_repo import query_attachments

        attachments = query_attachments(
            attachment_type=attach_type,
            notebook=notebook,
        )

        if not attachments:
            console.print("[dim]No attachments found.[/dim]")
            return

        console.print(f"\n[bold]All Attachments ({len(attachments)}):[/bold]\n")

        for attachment, parent_type, parent_id in attachments:
            type_badge = (
                "[cyan]url[/cyan]" if attachment.type == "url" else "[blue]file[/blue]"
            )
            parent_short = parent_id[-40:] if len(parent_id) > 40 else parent_id
            console.print(f"  {type_badge} {attachment.path}")
            console.print(f"       [dim]{parent_type}: {parent_short}[/dim]")
        return

    # Otherwise, show attachments for a specific note
    if target is None:
        note_path = ensure_daily_note(date.today())
    else:
        note_path = ensure_note_path(target)

    if not note_path.exists():
        console.print(f"[red]Note not found: {target}[/red]")
        raise SystemExit(1)

    attachments_in_file = list_attachments_in_file(note_path)

    if not attachments_in_file:
        console.print("[dim]No attachments found.[/dim]")
        return

    console.print(f"\n[bold]Attachments in {note_path.name}:[/bold]\n")

    for line_num, path in attachments_in_file:
        # Check if file exists
        from nb.core.attachments import is_url

        if is_url(path):
            status = "[cyan]url[/cyan]"
        else:
            # Create a temp attachment to resolve path
            temp = Attachment(id="", type="file", path=path)
            resolved = resolve_attachment_path(temp)
            if resolved:
                status = "[green]ok[/green]"
            else:
                status = "[red]missing[/red]"

        console.print(f"  {line_num:4d}: {path}  {status}")


@attach.command("open")
@click.argument("target")
@click.option("--line", "-L", type=int, help="Line number of the attachment")
def attach_open(target: str, line: int | None) -> None:
    """Open an attachment with the system default handler.

    TARGET can be a note path. Use --line to specify which attachment.

    Examples:
        nb attach open daily/2025-11-27.md --line 15

    """
    from nb.core.attachments import list_attachments_in_file, open_attachment
    from nb.models import Attachment

    note_path = ensure_note_path(target)

    if not note_path.exists():
        console.print(f"[red]Note not found: {target}[/red]")
        raise SystemExit(1)

    attachments = list_attachments_in_file(note_path)

    if not attachments:
        console.print("[dim]No attachments in this note.[/dim]")
        return

    if line is None:
        if len(attachments) == 1:
            line = attachments[0][0]
        else:
            console.print(
                "[yellow]Multiple attachments found. Use --line to specify:[/yellow]"
            )
            for ln, path in attachments:
                console.print(f"  {ln:4d}: {path}")
            return

    # Find attachment at line
    found = None
    for ln, path in attachments:
        if ln == line:
            found = path
            break

    if found is None:
        console.print(f"[red]No attachment at line {line}[/red]")
        raise SystemExit(1)

    # Determine type and open
    from nb.core.attachments import is_url

    attachment = Attachment(
        id="",
        type="url" if is_url(found) else "file",
        path=found,
    )

    if open_attachment(attachment):
        console.print(f"[green]Opened:[/green] {found}")
    else:
        console.print(f"[red]Failed to open:[/red] {found}")
        raise SystemExit(1)


@attach.command("stats")
def attach_stats() -> None:
    """Show attachment statistics.

    Displays counts of attachments by type, parent type, and storage method.

    Examples:
        nb attach stats

    """
    from nb.index.attachments_repo import get_attachment_stats

    stats = get_attachment_stats()

    if stats["total"] == 0:
        console.print("[dim]No attachments indexed.[/dim]")
        console.print("[dim]Run 'nb index' to index attachments from your notes.[/dim]")
        return

    console.print("\n[bold]Attachment Statistics[/bold]\n")
    console.print(f"  Total: {stats['total']}")

    # By type
    console.print("\n  [bold]By Type:[/bold]")
    for attach_type, count in stats["by_type"].items():
        console.print(f"    {attach_type}: {count}")

    # By parent type
    console.print("\n  [bold]By Owner:[/bold]")
    for parent_type, count in stats["by_parent_type"].items():
        console.print(f"    {parent_type}: {count}")

    # Storage method
    console.print("\n  [bold]Storage:[/bold]")
    console.print(f"    Copied: {stats['copied']}")
    console.print(f"    Linked: {stats['linked']}")


@attach.command("orphans")
@click.option("--delete", "-d", is_flag=True, help="Delete orphan files")
def attach_orphans(delete: bool) -> None:
    """Find attachment files not referenced by any note.

    Scans the attachments directory for files that have no corresponding
    @attach: reference in any note.

    Examples:
        nb attach orphans
        nb attach orphans --delete

    """
    from nb.index.attachments_repo import find_orphan_attachment_files

    orphans = find_orphan_attachment_files()

    if not orphans:
        console.print("[green]No orphan attachments found.[/green]")
        return

    console.print(f"\n[bold]Orphan Attachments ({len(orphans)}):[/bold]\n")

    total_size = 0
    for path in orphans:
        size = path.stat().st_size
        total_size += size
        size_str = _format_size(size)
        console.print(f"  {path.name}  [dim]{size_str}[/dim]")

    console.print(f"\n  [dim]Total: {_format_size(total_size)}[/dim]")

    if delete:
        console.print()
        for path in orphans:
            try:
                path.unlink()
                console.print(f"  [red]Deleted:[/red] {path.name}")
            except OSError as e:
                console.print(f"  [red]Failed to delete {path.name}: {e}[/red]")
    else:
        console.print("\n[dim]Use --delete to remove these files.[/dim]")


def _format_size(size: int | float) -> str:
    """Format a file size in human-readable form."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
