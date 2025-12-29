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

    Pull bookmarks from your Raindrop collections and clip them as notes.
    Supports multiple collections mapped to different notebooks.

    \b
    Setup:
      1. Get a Raindrop API token from https://app.raindrop.io/settings/integrations
      2. Set RAINDROP_API_KEY environment variable
      3. Configure collections in config.yaml (or use default "nb-inbox")

    \b
    Examples:
      nb inbox list                    # Show pending items
      nb inbox pull                    # Interactive: clip from all collections
      nb inbox pull --auto             # Clip all to configured notebooks
      nb inbox pull -c research        # Only pull from 'research' collection
      nb inbox sync                    # Sync tag/note changes from Raindrop
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
    help="Notebook to clip items to (overrides collection mapping)",
    shell_complete=complete_notebook,
)
@click.option("--auto", is_flag=True, help="Clip all items without prompting")
@click.option(
    "--all", "-a", "show_all", is_flag=True, help="Include already-clipped items"
)
@click.option(
    "--limit", "-l", default=10, help="Maximum items to process per collection"
)
@click.option(
    "--collection", "-c", help="Specific Raindrop collection (default: all configured)"
)
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

    With multiple collections configured, processes ALL collections automatically.
    Use --collection to limit to a specific collection.

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
      nb inbox pull                    # Interactive mode, all collections
      nb inbox pull --auto             # Clip all to configured notebooks
      nb inbox pull -n bookmarks       # Clip all to 'bookmarks' (override)
      nb inbox pull -c research        # Only process 'research' collection
      nb inbox pull -l 5               # Process only 5 items per collection
      nb inbox pull -t research        # Add #research tag to all
      nb inbox pull --all              # Include already-clipped items
      nb inbox pull --no-ai            # Disable AI summary generation
    """
    from rich.prompt import Prompt

    from nb.config import get_config
    from nb.config.models import RaindropCollectionConfig
    from nb.core.clip import clip_url, save_clipped_note
    from nb.core.inbox import (
        RaindropAPIError,
        RaindropAuthError,
        RaindropClient,
        get_duplicate_warning,
        is_item_clipped,
        record_clipped_item,
    )

    config = get_config()
    # Determine whether to use AI: flag overrides config, else use config default
    should_use_ai = use_ai if use_ai is not None else config.inbox.auto_summarize

    # Get collections to process
    if collection:
        # User specified a specific collection - find it or create ad-hoc config
        all_collections = config.inbox.raindrop.get_all_collections(
            config.inbox.default_notebook
        )
        matching = [c for c in all_collections if c.name.lower() == collection.lower()]
        if matching:
            collections_to_process = matching
        else:
            # Ad-hoc collection with default settings
            collections_to_process = [
                RaindropCollectionConfig(
                    name=collection,
                    notebook=notebook or config.inbox.default_notebook,
                    auto_archive=config.inbox.raindrop.auto_archive and not no_archive,
                )
            ]
    else:
        # Process all configured collections
        collections_to_process = config.inbox.raindrop.get_all_collections(
            config.inbox.default_notebook
        )

    try:
        client = RaindropClient()
    except RaindropAuthError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        console.print("[dim]Set RAINDROP_API_KEY environment variable[/dim]")
        raise SystemExit(1) from None

    # Global stats
    total_clipped = 0
    total_skipped = 0
    total_errors = 0
    quit_requested = False

    for coll_config in collections_to_process:
        if quit_requested:
            break

        # Determine settings for this collection
        coll_notebook = notebook or coll_config.notebook
        coll_archive = coll_config.auto_archive and not no_archive
        coll_extra_tags = list(coll_config.extra_tags) + list(extra_tags)

        # Verify notebook exists
        if coll_notebook and not config.get_notebook(coll_notebook):
            console.print(
                f"[yellow]Warning: Notebook '{coll_notebook}' not configured.[/yellow]"
            )
            console.print("[dim]Available notebooks:[/dim]")
            for nb in config.notebooks:
                console.print(f"  - {nb.name}")

        try:
            items = client.list_items(collection_name=coll_config.name, limit=limit)
        except RaindropAPIError as e:
            console.print(
                f"[red]API error for collection '{coll_config.name}':[/red] {e}"
            )
            continue

        # Filter out already-clipped items unless --all is specified
        if not show_all:
            original_count = len(items)
            items = [item for item in items if not is_item_clipped(item.id)]
            filtered_count = original_count - len(items)
        else:
            filtered_count = 0

        if not items:
            if filtered_count > 0:
                console.print(
                    f"[dim]No new items in '{coll_config.name}' ({filtered_count} already clipped).[/dim]"
                )
            else:
                console.print(f"[dim]No items in '{coll_config.name}'.[/dim]")
            continue

        # Show collection header
        header = (
            f"\n[bold cyan]Collection: {coll_config.name}[/bold cyan] → {coll_notebook}"
        )
        header += f"\n{len(items)} item{'s' if len(items) != 1 else ''} pending"
        if filtered_count > 0:
            header += f" [dim]({filtered_count} already clipped)[/dim]"
        console.print(header + "\n")

        for i, item in enumerate(items, 1):
            if quit_requested:
                break

            domain = urlparse(item.url).netloc

            # Check for duplicate URL (only relevant when showing all items)
            dup_warning = get_duplicate_warning(item.url) if show_all else None

            # Show item info
            tags_str = (
                " ".join(f"[yellow]#{t}[/yellow]" for t in item.tags)
                if item.tags
                else ""
            )
            console.print(
                f"[cyan]{i}.[/cyan] [bold]{item.title}[/bold] [dim]({domain})[/dim]"
            )
            if tags_str:
                console.print(f"   Tags: {tags_str}")
            if item.note:
                console.print(
                    f"   [dim italic]Note: {item.note[:60]}{'...' if len(item.note) > 60 else ''}[/dim italic]"
                )
            if dup_warning:
                console.print(f"   [yellow]⚠ {dup_warning}[/yellow]")

            if auto:
                # Auto mode: clip without prompting
                action_notebook = coll_notebook
            else:
                # Interactive mode
                prompt_text = f"   → Clip to [{coll_notebook}]"
                response = Prompt.ask(prompt_text, default="")

                response = response.strip().lower()

                if response == "q":
                    console.print("[dim]Quit.[/dim]")
                    quit_requested = True
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
                        raindrop_tags=item.tags,
                        raindrop_note=item.note,
                        collection_name=coll_config.name,
                    )
                    total_skipped += 1
                    continue
                elif response == "d":
                    console.print("   [dim]Marked as duplicate, skipped.[/dim]")
                    record_clipped_item(
                        item.id,
                        item.url,
                        item.title,
                        None,
                        skipped=True,
                        archived=coll_archive,
                        raindrop_tags=item.tags,
                        raindrop_note=item.note,
                        collection_name=coll_config.name,
                    )
                    if coll_archive:
                        try:
                            client.archive_item(item.id)
                        except Exception:
                            pass  # Ignore archive errors for duplicates
                    total_skipped += 1
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
                    action_notebook = coll_notebook

            # Clip the URL
            try:
                console.print(f"   [dim]Fetching {item.url}...[/dim]")

                # Combine item tags with collection extra tags and CLI extra tags
                all_tags = list(item.tags) + coll_extra_tags

                clipped = clip_url(item.url, title=item.title)
                saved_path = save_clipped_note(
                    clipped,
                    notebook=action_notebook,
                    extra_tags=all_tags if all_tags else None,
                    raindrop_note=item.note,
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

                # Record in database with sync metadata
                record_clipped_item(
                    item.id,
                    item.url,
                    item.title,
                    rel_path_display,
                    archived=coll_archive,
                    raindrop_tags=item.tags,
                    raindrop_note=item.note,
                    collection_name=coll_config.name,
                )

                # Archive in Raindrop if configured
                if coll_archive:
                    try:
                        client.archive_item(item.id)
                        console.print("   [dim]Archived in Raindrop[/dim]")
                    except Exception as e:
                        console.print(
                            f"   [yellow]Warning: Could not archive: {e}[/yellow]"
                        )

                total_clipped += 1

            except Exception as e:
                console.print(f"   [red]Error: {e}[/red]")
                total_errors += 1

            console.print()

    # Summary
    console.print(
        f"\n[bold]Done:[/bold] {total_clipped} clipped, {total_skipped} skipped, {total_errors} errors"
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


@inbox.command("sync")
@click.option("--limit", "-l", default=50, help="Maximum items to sync")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be synced without making changes"
)
def sync_items(limit: int, dry_run: bool) -> None:
    """Sync tag and note changes from Raindrop to local notes.

    Checks previously-clipped items for changes in Raindrop and updates
    the local notes accordingly:

    - Tag changes: Updates note frontmatter tags (preserves user-added tags)
    - Note changes: Updates the Raindrop note section in the note content

    Only syncs data that originally came from Raindrop. Tags you add locally
    to notes are preserved and not overwritten.

    \b
    Examples:
      nb inbox sync              # Sync up to 50 items
      nb inbox sync -l 100       # Sync up to 100 items
      nb inbox sync --dry-run    # Preview changes without applying
    """
    from nb.config import get_config
    from nb.core.inbox import sync_clipped_items
    from nb.core.inbox.raindrop import RaindropAuthError

    config = get_config()

    # Check if sync is enabled
    if not config.inbox.raindrop.sync_tags and not config.inbox.raindrop.sync_notes:
        console.print("[yellow]Sync is disabled in configuration.[/yellow]")
        console.print(
            "[dim]Enable with: nb config set inbox.raindrop.sync_tags true[/dim]"
        )
        return

    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be made[/yellow]\n")

    console.print("[bold]Syncing from Raindrop...[/bold]\n")

    try:
        results = sync_clipped_items(limit=limit, dry_run=dry_run)
    except RaindropAuthError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        console.print("[dim]Set RAINDROP_API_KEY environment variable[/dim]")
        raise SystemExit(1) from None

    if not results:
        console.print("[dim]No items to sync.[/dim]")
        return

    updated_count = 0
    error_count = 0
    unchanged_count = 0

    for result in results:
        if result.error:
            console.print(f"[red]Error syncing {result.item_id}:[/red] {result.error}")
            error_count += 1
        elif result.tags_updated or result.note_updated:
            changes = []
            if result.tags_updated:
                # Show tag diff
                old_set = set(result.old_tags)
                new_set = set(result.new_tags)
                added = new_set - old_set
                removed = old_set - new_set
                tag_changes = []
                if added:
                    tag_changes.append(f"+{', '.join(added)}")
                if removed:
                    tag_changes.append(f"-{', '.join(removed)}")
                changes.append(f"tags ({' '.join(tag_changes)})")
            if result.note_updated:
                changes.append("note")
            action = "Would update" if dry_run else "Updated"
            console.print(
                f"[green]{action} {result.note_path}:[/green] {', '.join(changes)}"
            )
            updated_count += 1
        else:
            unchanged_count += 1

    # Summary
    action_word = "would be updated" if dry_run else "updated"
    console.print(
        f"\n[bold]Done:[/bold] {updated_count} {action_word}, {unchanged_count} unchanged, {error_count} errors"
    )
