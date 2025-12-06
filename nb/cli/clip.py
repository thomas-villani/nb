"""Web clipping CLI commands."""

from __future__ import annotations

import click

from nb.cli.completion import complete_notebook
from nb.cli.utils import console, resolve_note_ref


def register_clip_commands(cli: click.Group) -> None:
    """Register clip-related commands with the CLI."""
    cli.add_command(clip)


@click.command()
@click.argument("url")
@click.option(
    "--notebook",
    "-n",
    help="Create new note in this notebook",
    shell_complete=complete_notebook,
)
@click.option(
    "--to",
    "target_note",
    help="Append to specific note (path, alias, or notebook/note)",
)
@click.option(
    "--tag",
    "-t",
    "tags",
    multiple=True,
    help="Additional tags (repeatable)",
)
@click.option(
    "--section",
    "-s",
    help="Extract only this section from the page (supports wildcards)",
)
@click.option(
    "--title",
    "-T",
    help="Custom title (overrides extracted title)",
)
@click.option(
    "--no-domain-tag",
    is_flag=True,
    help="Don't auto-tag with source domain",
)
def clip(
    url: str,
    notebook: str | None,
    target_note: str | None,
    tags: tuple[str, ...],
    section: str | None,
    title: str | None,
    no_domain_tag: bool,
) -> None:
    """Clip web content to a note.

    Fetches content from URL, converts to markdown, and saves as a note.
    By default appends to today's daily note.

    \b
    Examples:
      nb clip https://example.com/article
      nb clip https://example.com/article -n bookmarks
      nb clip https://example.com/article --to projects/research.md
      nb clip https://example.com/article --tag research --tag python
      nb clip https://example.com/article --section "Installation"
      nb clip https://example.com/article --title "My Custom Title"
    """
    import httpx

    from nb.config import get_config
    from nb.core.clip import clip_url, save_clipped_note

    config = get_config()

    # Validate URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Resolve target note if specified
    resolved_target = None
    if target_note:
        resolved_target = resolve_note_ref(target_note, notebook=notebook)
        if not resolved_target:
            console.print(f"[red]Note not found: {target_note}[/red]")
            raise SystemExit(1)
        # Don't use notebook when appending to specific note
        notebook = None

    # Clip the URL
    console.print(f"[dim]Fetching {url}...[/dim]")

    try:
        clipped = clip_url(url, section=section, title=title)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP error: {e.response.status_code}[/red]")
        console.print(f"[dim]{e.response.reason_phrase}[/dim]")
        raise SystemExit(1) from None
    except httpx.RequestError as e:
        console.print(f"[red]Request failed: {e}[/red]")
        raise SystemExit(1) from None
    except Exception as e:
        console.print(f"[red]Failed to clip URL: {e}[/red]")
        raise SystemExit(1) from None

    console.print(f"[green]Clipped:[/green] {clipped.title}")

    # Determine include_domain_tag (respect config unless overridden)
    include_domain_tag = config.clip.auto_tag_domain and not no_domain_tag

    # Save the clipped content
    try:
        # Temporarily override config setting for this call
        original_setting = config.clip.auto_tag_domain
        config.clip.auto_tag_domain = include_domain_tag

        saved_path = save_clipped_note(
            clipped,
            notebook=notebook,
            target_note=resolved_target,
            extra_tags=list(tags) if tags else None,
        )

        # Restore original setting
        config.clip.auto_tag_domain = original_setting

    except FileExistsError:
        console.print("[red]A note with this title already exists.[/red]")
        console.print("[dim]Use --to to append to an existing note.[/dim]")
        raise SystemExit(1) from None
    except Exception as e:
        console.print(f"[red]Failed to save note: {e}[/red]")
        raise SystemExit(1) from None

    # Report success
    if resolved_target:
        console.print(f"[green]Appended to:[/green] {saved_path.name}")
    elif notebook:
        try:
            rel_path = saved_path.relative_to(config.notes_root)
            console.print(f"[green]Created:[/green] {rel_path}")
        except ValueError:
            console.print(f"[green]Created:[/green] {saved_path.name}")
    else:
        console.print(f"[green]Added to:[/green] {saved_path.name}")

    # Show tags
    all_tags = ["clipped"]
    if include_domain_tag:
        all_tags.append(clipped.domain.removeprefix("www."))
    if tags:
        all_tags.extend(tags)
    console.print(f"[dim]Tags: {', '.join(all_tags)}[/dim]")
