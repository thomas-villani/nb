"""Inbox CLI commands for pulling bookmarks from external services."""

from __future__ import annotations

from urllib.parse import urlparse

import click

from nb.cli.completion import complete_notebook
from nb.cli.utils import console


def register_inbox_commands(cli: click.Group) -> None:
    """Register inbox-related commands with the CLI."""
    cli.add_command(inbox)


@click.group()
def inbox() -> None:
    """Manage inbox items from Raindrop.io.

    Pull bookmarks from your Raindrop inbox collection and clip them as notes.

    \b
    Setup:
      1. Get a Raindrop API token from https://app.raindrop.io/settings/integrations
      2. Set RAINDROP_API_KEY environment variable
      3. Create a "nb-inbox" collection in Raindrop (or configure a different one)

    \b
    Examples:
      nb inbox list                    # Show pending items
      nb inbox pull                    # Interactive: clip each item
      nb inbox pull --auto             # Clip all to default notebook
      nb inbox pull -n bookmarks       # Clip all to 'bookmarks' notebook
      nb inbox clear                   # Archive all without clipping
    """
    pass


@inbox.command("list")
@click.option("--limit", "-l", default=20, help="Maximum items to show")
@click.option("--collection", "-c", help="Raindrop collection name")
@click.option(
    "--all", "-a", "show_all", is_flag=True, help="Include already-clipped items"
)
def list_items(limit: int, collection: str | None, show_all: bool) -> None:
    """List pending items in the Raindrop inbox.

    Shows bookmarks waiting to be clipped from your Raindrop collection.
    Already-clipped items are hidden by default (use --all to show them).

    \b
    Examples:
      nb inbox list              # Show up to 20 pending items
      nb inbox list -l 50        # Show up to 50 items
      nb inbox list -c reading   # List from 'reading' collection
      nb inbox list --all        # Include already-clipped items
    """
    from nb.config import get_config
    from nb.core.inbox import (
        RaindropAPIError,
        RaindropAuthError,
        get_duplicate_warning,
        is_item_clipped,
        list_inbox_items,
    )

    config = get_config()

    try:
        items = list_inbox_items(collection=collection, limit=limit)
    except RaindropAuthError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        console.print("[dim]Set RAINDROP_API_KEY environment variable[/dim]")
        raise SystemExit(1) from None
    except RaindropAPIError as e:
        console.print(f"[red]API error:[/red] {e}")
        raise SystemExit(1) from None

    # Filter out already-clipped items unless --all is specified
    if not show_all:
        original_count = len(items)
        items = [item for item in items if not is_item_clipped(item.id)]
        filtered_count = original_count - len(items)
    else:
        filtered_count = 0

    if not items:
        coll_name = collection or config.inbox.raindrop.collection
        if filtered_count > 0:
            console.print(
                f"[dim]No new items in '{coll_name}' collection ({filtered_count} already clipped).[/dim]"
            )
        else:
            console.print(f"[dim]No items in '{coll_name}' collection.[/dim]")
        return

    header = f"\n[bold]Inbox:[/bold] {len(items)} item{'s' if len(items) != 1 else ''}"
    if filtered_count > 0:
        header += f" [dim]({filtered_count} already clipped, hidden)[/dim]"
    console.print(header + "\n")

    for i, item in enumerate(items, 1):
        # Parse domain from URL
        domain = urlparse(item.url).netloc

        # Check for duplicate (only relevant when showing all)
        dup_warning = get_duplicate_warning(item.url) if show_all else None

        # Format tags
        tags_str = (
            " ".join(f"[yellow]#{t}[/yellow]" for t in item.tags) if item.tags else ""
        )

        console.print(f"[cyan]{i:>3}.[/cyan] [bold]{item.title}[/bold]")
        console.print(f"     [dim]{domain}[/dim] {tags_str}")

        if dup_warning:
            console.print(f"     [yellow]⚠ {dup_warning}[/yellow]")

        if item.excerpt:
            # Truncate excerpt
            excerpt = (
                item.excerpt[:100] + "..." if len(item.excerpt) > 100 else item.excerpt
            )
            console.print(f"     [dim italic]{excerpt}[/dim italic]")

        console.print()


@inbox.command("pull")
@click.option(
    "--notebook",
    "-n",
    help="Notebook to clip items to",
    shell_complete=complete_notebook,
)
@click.option("--auto", is_flag=True, help="Clip all items without prompting")
@click.option(
    "--all", "-a", "show_all", is_flag=True, help="Include already-clipped items"
)
@click.option("--limit", "-l", default=10, help="Maximum items to process")
@click.option("--collection", "-c", help="Raindrop collection name")
@click.option(
    "--tag", "-t", "extra_tags", multiple=True, help="Additional tags (repeatable)"
)
@click.option("--no-archive", is_flag=True, help="Don't archive items after clipping")
@click.option(
    "--ai/--no-ai",
    "use_ai",
    default=None,
    help="Generate AI summary for clipped content (default: from config)",
)
def pull_items(
    notebook: str | None,
    auto: bool,
    show_all: bool,
    limit: int,
    collection: str | None,
    extra_tags: tuple[str, ...],
    no_archive: bool,
    use_ai: bool | None,
) -> None:
    """Pull and clip items from Raindrop inbox.

    By default runs interactively, prompting for each item.
    Already-clipped items are hidden by default (use --all to include them).
    Use --auto to clip all items without prompting.

    AI summaries are generated by default (configurable via inbox.auto_summarize).
    Use --no-ai to disable or --ai to force enable.

    \b
    Interactive mode commands:
      Enter     - Clip to default/specified notebook
      <name>    - Clip to different notebook
      s         - Skip this item
      q         - Quit processing
      d         - Mark as duplicate and skip
      ?         - Show help

    \b
    Examples:
      nb inbox pull                    # Interactive mode with AI summaries
      nb inbox pull --auto             # Clip all to default notebook
      nb inbox pull -n bookmarks       # Clip all to 'bookmarks'
      nb inbox pull -l 5               # Process only 5 items
      nb inbox pull -t research        # Add #research tag to all
      nb inbox pull --all              # Include already-clipped items
      nb inbox pull --no-ai            # Disable AI summary generation
    """
    from rich.prompt import Prompt

    from nb.config import get_config
    from nb.core.clip import clip_url, save_clipped_note
    from nb.core.inbox import (
        RaindropAPIError,
        RaindropAuthError,
        RaindropClient,
        get_duplicate_warning,
        is_item_clipped,
        list_inbox_items,
        record_clipped_item,
    )

    config = get_config()
    target_notebook = notebook or config.inbox.default_notebook
    should_archive = config.inbox.raindrop.auto_archive and not no_archive
    # Determine whether to use AI: flag overrides config, else use config default
    should_use_ai = use_ai if use_ai is not None else config.inbox.auto_summarize

    # Verify notebook exists
    if target_notebook and not config.get_notebook(target_notebook):
        console.print(
            f"[yellow]Warning: Notebook '{target_notebook}' not configured.[/yellow]"
        )
        console.print("[dim]Available notebooks:[/dim]")
        for nb in config.notebooks:
            console.print(f"  - {nb.name}")

    try:
        items = list_inbox_items(collection=collection, limit=limit)
        client = RaindropClient() if should_archive else None
    except RaindropAuthError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        console.print("[dim]Set RAINDROP_API_KEY environment variable[/dim]")
        raise SystemExit(1) from None
    except RaindropAPIError as e:
        console.print(f"[red]API error:[/red] {e}")
        raise SystemExit(1) from None

    # Filter out already-clipped items unless --all is specified
    if not show_all:
        original_count = len(items)
        items = [item for item in items if not is_item_clipped(item.id)]
        filtered_count = original_count - len(items)
    else:
        filtered_count = 0

    if not items:
        coll_name = collection or config.inbox.raindrop.collection
        if filtered_count > 0:
            console.print(
                f"[dim]No new items in '{coll_name}' collection ({filtered_count} already clipped).[/dim]"
            )
        else:
            console.print(f"[dim]No items in '{coll_name}' collection.[/dim]")
        return

    header = f"\n[bold]Inbox:[/bold] {len(items)} item{'s' if len(items) != 1 else ''} pending"
    if filtered_count > 0:
        header += f" [dim]({filtered_count} already clipped, hidden)[/dim]"
    console.print(header + "\n")

    # Stats
    clipped_count = 0
    skipped_count = 0
    error_count = 0

    for i, item in enumerate(items, 1):
        domain = urlparse(item.url).netloc

        # Check for duplicate URL (only relevant when showing all items)
        dup_warning = get_duplicate_warning(item.url) if show_all else None

        # Show item info
        tags_str = (
            " ".join(f"[yellow]#{t}[/yellow]" for t in item.tags) if item.tags else ""
        )
        console.print(
            f"[cyan]{i}.[/cyan] [bold]{item.title}[/bold] [dim]({domain})[/dim]"
        )
        if tags_str:
            console.print(f"   Tags: {tags_str}")
        if dup_warning:
            console.print(f"   [yellow]⚠ {dup_warning}[/yellow]")

        if auto:
            # Auto mode: clip without prompting
            action_notebook = target_notebook
        else:
            # Interactive mode
            prompt_text = f"   → Clip to [{target_notebook}]"
            response = Prompt.ask(prompt_text, default="")

            response = response.strip().lower()

            if response == "q":
                console.print("[dim]Quit.[/dim]")
                break
            elif response == "s":
                console.print("   [dim]Skipped.[/dim]")
                record_clipped_item(
                    item.id,
                    item.url,
                    item.title,
                    None,
                    skipped=True,
                    archived=False,
                )
                skipped_count += 1
                continue
            elif response == "d":
                console.print("   [dim]Marked as duplicate, skipped.[/dim]")
                record_clipped_item(
                    item.id,
                    item.url,
                    item.title,
                    None,
                    skipped=True,
                    archived=should_archive,
                )
                if should_archive and client:
                    try:
                        client.archive_item(item.id)
                    except Exception:
                        pass  # Ignore archive errors for duplicates
                skipped_count += 1
                continue
            elif response == "?":
                console.print("\n[bold]Commands:[/bold]")
                console.print("  [cyan]Enter[/cyan]  - Clip to default notebook")
                console.print("  [cyan]<name>[/cyan] - Clip to specified notebook")
                console.print("  [cyan]s[/cyan]      - Skip this item")
                console.print("  [cyan]d[/cyan]      - Mark as duplicate and skip")
                console.print("  [cyan]q[/cyan]      - Quit\n")
                # Re-prompt for this item
                continue
            elif response:
                action_notebook = response
            else:
                action_notebook = target_notebook

        # Clip the URL
        try:
            console.print(f"   [dim]Fetching {item.url}...[/dim]")

            # Combine item tags with extra tags
            all_tags = list(item.tags) + list(extra_tags)

            clipped = clip_url(item.url, title=item.title)
            saved_path = save_clipped_note(
                clipped,
                notebook=action_notebook,
                extra_tags=all_tags if all_tags else None,
            )

            # Get relative path for display
            try:
                rel_path_display = str(saved_path.relative_to(config.notes_root))
            except ValueError:
                rel_path_display = saved_path.name

            console.print(f"   [green]Clipped to:[/green] {rel_path_display}")

            # Generate AI summary if enabled
            if should_use_ai:
                console.print("   [dim]Generating summary...[/dim]", end="")
                try:
                    from nb.core.ai.summarize import (
                        generate_content_tldr,
                        update_note_frontmatter_summary,
                    )

                    summary = generate_content_tldr(
                        content=clipped.markdown,
                        title=clipped.title,
                        use_smart_model=False,  # Use fast model for cost efficiency
                    )
                    if summary:
                        update_note_frontmatter_summary(saved_path, summary)
                        console.print(
                            f"\r   [dim]Summary:[/dim] {summary[:80]}{'...' if len(summary) > 80 else ''}"
                        )
                    else:
                        console.print(
                            "\r   [dim]Summary: skipped (AI unavailable)[/dim]"
                        )
                except Exception:
                    # Graceful failure - continue without summary
                    console.print("\r   [dim]Summary: skipped (error)[/dim]")

            # Record in database
            record_clipped_item(
                item.id,
                item.url,
                item.title,
                rel_path_display,
                archived=should_archive,
            )

            # Archive in Raindrop if configured
            if should_archive and client:
                try:
                    client.archive_item(item.id)
                    console.print("   [dim]Archived in Raindrop[/dim]")
                except Exception as e:
                    console.print(
                        f"   [yellow]Warning: Could not archive: {e}[/yellow]"
                    )

            clipped_count += 1

        except Exception as e:
            console.print(f"   [red]Error: {e}[/red]")
            error_count += 1

        console.print()

    # Summary
    console.print(
        f"\n[bold]Done:[/bold] {clipped_count} clipped, {skipped_count} skipped, {error_count} errors"
    )


@inbox.command("clear")
@click.option("--collection", "-c", help="Raindrop collection name")
@click.option("--limit", "-l", default=50, help="Maximum items to archive")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def clear_inbox(collection: str | None, limit: int, force: bool) -> None:
    """Archive all items in inbox without clipping.

    Moves all items from the inbox collection to Raindrop's Archive.
    Useful for clearing out items you've already read or don't need.

    \b
    Examples:
      nb inbox clear              # Archive all items (with confirmation)
      nb inbox clear -f           # Archive without confirmation
      nb inbox clear -l 10        # Archive only 10 items
      nb inbox clear -c reading   # Clear 'reading' collection
    """
    from rich.prompt import Confirm

    from nb.config import get_config
    from nb.core.inbox import (
        RaindropAPIError,
        RaindropAuthError,
        RaindropClient,
        list_inbox_items,
        record_clipped_item,
    )

    config = get_config()

    try:
        items = list_inbox_items(collection=collection, limit=limit)
        client = RaindropClient()
    except RaindropAuthError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise SystemExit(1) from None
    except RaindropAPIError as e:
        console.print(f"[red]API error:[/red] {e}")
        raise SystemExit(1) from None

    if not items:
        coll_name = collection or config.inbox.raindrop.collection
        console.print(f"[dim]No items in '{coll_name}' collection.[/dim]")
        return

    console.print(
        f"\n[bold]Found {len(items)} item{'s' if len(items) != 1 else ''} to archive[/bold]\n"
    )

    # Show first few items
    for item in items[:5]:
        console.print(f"  • {item.title}")
    if len(items) > 5:
        console.print(f"  [dim]... and {len(items) - 5} more[/dim]")

    if not force:
        if not Confirm.ask("\nArchive all items without clipping?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    console.print()

    archived_count = 0
    error_count = 0

    for item in items:
        try:
            client.archive_item(item.id)
            record_clipped_item(
                item.id,
                item.url,
                item.title,
                None,
                skipped=True,
                archived=True,
            )
            console.print(
                f"[dim]Archived: {item.title[:50]}...[/dim]"
                if len(item.title) > 50
                else f"[dim]Archived: {item.title}[/dim]"
            )
            archived_count += 1
        except Exception as e:
            console.print(f"[red]Error archiving {item.title}: {e}[/red]")
            error_count += 1

    console.print(
        f"\n[bold]Done:[/bold] {archived_count} archived, {error_count} errors"
    )


@inbox.command("history")
@click.option("--limit", "-l", default=20, help="Maximum items to show")
@click.option("--include-skipped", is_flag=True, help="Include skipped items")
def show_history(limit: int, include_skipped: bool) -> None:
    """Show history of clipped inbox items.

    Lists items that have been previously processed from the inbox.

    \b
    Examples:
      nb inbox history              # Show last 20 clipped items
      nb inbox history -l 50        # Show last 50 items
      nb inbox history --include-skipped  # Include skipped items
    """
    from nb.core.inbox import list_clipped_items

    items = list_clipped_items(limit=limit, include_skipped=include_skipped)

    if not items:
        console.print("[dim]No clipping history found.[/dim]")
        return

    console.print(
        f"\n[bold]Clipping History:[/bold] {len(items)} item{'s' if len(items) != 1 else ''}\n"
    )

    for item in items:
        title = item["title"] or "Untitled"
        clipped_at = item["clipped_at"]
        note_path = item["note_path"]
        skipped = item["skipped"]
        archived = item["archived"]

        if skipped:
            status = "[dim]skipped[/dim]"
        elif note_path:
            status = f"→ [green]{note_path}[/green]"
        else:
            status = "[dim]no note[/dim]"

        date_str = clipped_at[:10] if clipped_at else "—"
        archive_icon = " [dim]📦[/dim]" if archived else ""

        console.print(
            f"  [dim]{date_str}[/dim]  {title[:50]}{'...' if len(title) > 50 else ''}  {status}{archive_icon}"
        )
