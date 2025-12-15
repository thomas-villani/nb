"""Search-related CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from nb.cli.completion import complete_notebook, complete_tag
from nb.cli.utils import console
from nb.config import get_config
from nb.utils.hashing import normalize_path


def register_search_commands(cli: click.Group) -> None:
    """Register all search-related commands with the CLI."""
    cli.add_command(search_cmd)
    cli.add_command(grep_cmd)
    cli.add_command(index_cmd)
    cli.add_command(stream_notes)


@click.command("search")
@click.argument("query", required=False)
@click.option("-i", "--interactive", is_flag=True, help="Launch interactive search TUI")
@click.option(
    "-s", "--semantic", is_flag=True, help="Use pure semantic search (no keyword)"
)
@click.option(
    "-k", "--keyword", is_flag=True, help="Use pure keyword search (no semantic)"
)
@click.option("-t", "--tag", help="Filter by tag", shell_complete=complete_tag)
@click.option(
    "--notebook", "-n", help="Filter by notebook", shell_complete=complete_notebook
)
@click.option(
    "--when",
    "when_filter",
    help="Filter by date range (e.g., 'last 3 months', 'this week')",
)
@click.option("--since", "since_date", help="Show notes from this date onwards")
@click.option("--until", "until_date", help="Show notes up to this date")
@click.option(
    "--recent", is_flag=True, help="Boost recent results (30% recency weight)"
)
@click.option("--limit", default=20, help="Max results")
@click.option(
    "--threshold",
    "-T",
    default=0.4,
    type=float,
    help="Return results above this score (default 0.4)",
)
def search_cmd(
    query: str | None,
    interactive: bool,
    semantic: bool,
    keyword: bool,
    tag: str | None,
    notebook: str | None,
    when_filter: str | None,
    since_date: str | None,
    until_date: str | None,
    recent: bool,
    limit: int,
    threshold: float,
) -> None:
    """Search notes by keyword, semantic similarity, or both (hybrid).

    By default uses hybrid search (70% semantic, 30% keyword).
    Use --semantic for pure semantic search, --keyword for pure keyword search.
    Use --interactive for an interactive TUI with live filtering.

    \b
    Date filtering:
        --when "last 3 months"    Fuzzy date range
        --when "this week"        Current week
        --since friday            From a date onwards
        --until "nov 20"          Up to a date

    \b
    Examples:
        nb search "machine learning"
        nb search -i                              # Interactive TUI
        nb search -i "project ideas"              # TUI with initial query
        nb search -s "project ideas" --recent
        nb search "TODO" --when "last 2 weeks"
        nb search "meeting notes" --since "last monday"

    """
    # Handle interactive mode
    if interactive:
        from nb.tui.search import run_interactive_search

        # Determine search type for TUI
        if semantic:
            search_type = "vector"
        elif keyword:
            search_type = "keyword"
        else:
            search_type = "hybrid"

        run_interactive_search(
            initial_query=query or "",
            initial_notebook=notebook,
            initial_tag=tag,
            search_type=search_type,
        )
        return

    # Non-interactive mode requires a query
    if not query:
        console.print(
            "[red]Error: Missing argument 'QUERY'. Use -i for interactive mode.[/red]"
        )
        raise SystemExit(1)

    from nb.index.search import get_search
    from nb.utils.dates import parse_date_range, parse_fuzzy_date

    # Determine search type
    if semantic and keyword:
        console.print("[red]Cannot use both --semantic and --keyword[/red]")
        raise SystemExit(1)
    elif semantic:
        search_type = "vector"
    elif keyword:
        search_type = "keyword"
    else:
        search_type = "hybrid"

    # Build filters
    filters: dict[str, str | dict[str, str]] = {}
    if tag:
        filters["tags"] = {"$contains": tag}
    if notebook:
        filters["notebook"] = notebook

    # Handle date filtering
    date_start = None
    date_end = None

    if when_filter:
        start, end = parse_date_range(when_filter)
        if start:
            date_start = start.isoformat()
        if end:
            date_end = end.isoformat()
        if not start and not end:
            console.print(f"[yellow]Could not parse date range: {when_filter}[/yellow]")

    if since_date:
        parsed = parse_fuzzy_date(since_date)
        if parsed:
            date_start = parsed.isoformat()
        else:
            console.print(f"[yellow]Could not parse date: {since_date}[/yellow]")

    if until_date:
        parsed = parse_fuzzy_date(until_date)
        if parsed:
            date_end = parsed.isoformat()
        else:
            console.print(f"[yellow]Could not parse date: {until_date}[/yellow]")

    # Determine recency boost
    recency_boost = 0.3 if recent else 0.0

    try:
        from nb.cli.utils import spinner

        search = get_search()
        with spinner("Searching"):
            results = search.search(
                query,
                search_type=search_type,
                k=limit,
                filters=filters if filters else None,
                date_start=date_start,
                date_end=date_end,
                recency_boost=recency_boost,
                score_threshold=threshold,
            )
    except Exception as e:
        error_msg = str(e).lower()
        console.print(f"[red]Search failed:[/red] {e}")
        if "empty" in error_msg or "no documents" in error_msg:
            console.print(
                "[dim]Hint: Run 'nb index --embeddings' to build the search index.[/dim]"
            )
        elif "connection" in error_msg or "ollama" in error_msg:
            console.print(
                "[dim]Hint: Make sure Ollama is running for embedding generation.[/dim]"
            )
        else:
            console.print(
                "[dim]Hint: Run 'nb index --embeddings' to rebuild the search index.[/dim]"
            )
        raise SystemExit(1) from None

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    # Show filter info
    filter_info = []
    if date_start or date_end:
        if date_start and date_end:
            filter_info.append(f"dates: {date_start} to {date_end}")
        elif date_start:
            filter_info.append(f"since: {date_start}")
        else:
            filter_info.append(f"until: {date_end}")
    if recent:
        filter_info.append("recency boosted")

    if filter_info:
        console.print(f"[dim]Filters: {', '.join(filter_info)}[/dim]")

    console.print(f"\n[bold]Found {len(results)} results:[/bold]\n")

    for r in results:
        # Display path and title
        title = r.title or Path(r.path).stem
        console.print(f"[bold cyan]{r.path}[/bold cyan]")
        console.print(f"  [bold]{title}[/bold]")

        # Display score and metadata
        meta_parts = [f"score: {r.score:.3f}"]
        if r.notebook:
            meta_parts.append(f"notebook: {r.notebook}")
        if r.date:
            meta_parts.append(f"date: {r.date}")
        console.print(f"  [dim]{' | '.join(meta_parts)}[/dim]")

        # Display snippet
        if r.snippet:
            snippet = r.snippet.replace("\n", " ").strip()
            if len(snippet) > 150:
                snippet = snippet[:150] + "..."
            console.print(f"  [dim]{snippet}[/dim]")

        console.print()


@click.command("grep")
@click.argument("pattern")
@click.option("-C", "--context", "context_lines", default=2, help="Context lines")
@click.option(
    "-i", "--ignore-case/--case-sensitive", default=True, help="Case sensitivity"
)
@click.option(
    "--notebook", "-n", help="Filter by notebook", shell_complete=complete_notebook
)
@click.option("--note", help="Filter by specific note (path or alias)")
def grep_cmd(
    pattern: str,
    context_lines: int,
    ignore_case: bool,
    notebook: str | None,
    note: str | None,
) -> None:
    """Search notes with regex pattern matching.

    Unlike 'search', this performs raw regex matching on the files.
    Useful for finding exact strings, code snippets, or patterns.

    \b
    Examples:
        nb grep "TODO.*urgent"
        nb grep "def\\s+\\w+" -C 5
        nb grep "API_KEY" --case-sensitive
        nb grep "config" -n nbcli
        nb grep "setup" --note features

    """
    from nb.index.search import grep_notes

    config = get_config()

    # Resolve note path if specified
    note_path = None
    if note:
        from nb.cli.utils import resolve_note_ref
        from nb.utils.fuzzy import UserCancelled

        try:
            resolved = resolve_note_ref(note, notebook=notebook, ensure_exists=True)
            if resolved:
                note_path = resolved
            else:
                console.print(f"[red]Note not found: {note}[/red]")
                raise SystemExit(1)
        except UserCancelled:
            console.print("[dim]Cancelled.[/dim]")
            raise SystemExit(1) from None

    try:
        results = grep_notes(
            pattern,
            config.notes_root,
            context_lines=context_lines,
            case_sensitive=not ignore_case,
            notebook=notebook,
            note_path=note_path,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None

    if not results:
        console.print("[dim]No matches found.[/dim]")
        return

    console.print(f"\n[bold]Found {len(results)} matches:[/bold]\n")

    current_file = None
    for r in results:
        # Print file header when it changes
        if r.path != current_file:
            if current_file is not None:
                console.print()  # Blank line between files
            console.print(f"[bold cyan]{r.path}[/bold cyan]")
            current_file = r.path

        # Print context before
        for i, line in enumerate(r.context_before):
            line_num = r.line_number - len(r.context_before) + i
            console.print(f"[dim]{line_num:4d}:[/dim] {line}")

        # Print matching line (highlighted)
        console.print(
            f"[yellow]{r.line_number:4d}:[/yellow] [bold]{r.line_content}[/bold]"
        )

        # Print context after
        for i, line in enumerate(r.context_after):
            line_num = r.line_number + 1 + i
            console.print(f"[dim]{line_num:4d}:[/dim] {line}")

        console.print()


@click.command("index")
@click.option("--force", "-f", is_flag=True, help="Force reindex all files")
@click.option("--rebuild", is_flag=True, help="Drop and recreate the database")
@click.option("--embeddings", "-e", is_flag=True, help="Rebuild search embeddings")
@click.option(
    "--vectors-only",
    "-v",
    is_flag=True,
    help="Only rebuild vectors (skip file indexing)",
)
@click.option(
    "--reset-vectors",
    is_flag=True,
    help="Delete vector index before rebuilding (use when changing embedding provider/model)",
)
@click.option(
    "--notebook",
    "-n",
    help="Only reindex this notebook",
    shell_complete=complete_notebook,
)
def index_cmd(
    force: bool,
    rebuild: bool,
    embeddings: bool,
    vectors_only: bool,
    reset_vectors: bool,
    notebook: str | None,
) -> None:
    """Rebuild the notes and todos index.

    Incrementally indexes new and modified files. Use --force to reindex
    all files, or --rebuild to drop and recreate the database entirely.

    \b
    Examples:
      nb index               # Index new/changed files
      nb index --force       # Reindex all files
      nb index -n daily      # Only reindex the 'daily' notebook
      nb index --rebuild     # Drop database and reindex (fixes schema issues)
      nb index --embeddings  # Rebuild semantic search vectors
      nb index --vectors-only  # Rebuild only vectors (e.g., after changing embedding model)
      nb index --reset-vectors --vectors-only  # Clear and rebuild vectors (after changing provider)
    """
    from nb.cli.utils import progress_bar, spinner
    from nb.index.scanner import (
        count_files_to_index,
        count_linked_notes,
        count_notes_for_search_rebuild,
        index_all_notes,
        remove_deleted_notes,
        scan_linked_notes,
    )
    from nb.index.todos_repo import get_todo_stats

    # Handle --reset-vectors: clear vector index before rebuilding
    if reset_vectors:
        if rebuild:
            console.print("[red]Cannot use --reset-vectors with --rebuild[/red]")
            console.print("[dim]Hint: --rebuild already clears the vector index.[/dim]")
            raise SystemExit(1)
        if not vectors_only and not embeddings:
            console.print(
                "[red]--reset-vectors requires --vectors-only or --embeddings[/red]"
            )
            console.print(
                "[dim]Hint: Use --reset-vectors --vectors-only to clear and rebuild vectors.[/dim]"
            )
            raise SystemExit(1)

        import shutil

        from nb.config import get_config
        from nb.index.search import reset_search

        config = get_config()
        vectors_path = config.vectors_path
        if vectors_path.exists():
            reset_search()  # Close any open connections first
            shutil.rmtree(vectors_path)
            console.print("[dim]Cleared vector index.[/dim]")

    # Handle --vectors-only: skip file indexing, just rebuild vectors
    if vectors_only:
        if rebuild:
            console.print("[red]Cannot use --vectors-only with --rebuild[/red]")
            console.print(
                "[dim]Hint: Use --embeddings instead to rebuild both database and vectors.[/dim]"
            )
            raise SystemExit(1)

        search_total = count_notes_for_search_rebuild(notebook=notebook)
        if search_total > 0:
            from nb.index.scanner import rebuild_search_index

            with progress_bar("Rebuilding vectors", total=search_total) as advance:
                search_count = rebuild_search_index(
                    notebook=notebook,
                    on_progress=advance,
                )
            console.print(f"[green]Rebuilt vectors for {search_count} notes.[/green]")
        else:
            console.print("[dim]No notes to rebuild vectors for.[/dim]")
            console.print(
                "[dim]Hint: Run 'nb index' first to index notes to the database.[/dim]"
            )
        return

    if rebuild:
        if notebook:
            console.print("[red]Cannot use --rebuild with --notebook[/red]")
            console.print(
                "[dim]Hint: Use --force to reindex a specific notebook without dropping the database.[/dim]"
            )
            raise SystemExit(1)
        with spinner("Rebuilding database"):
            from nb.index.db import get_db, rebuild_db

            db = get_db()
            rebuild_db(db)
        console.print("[green]Database rebuilt.[/green]")
        force = True  # Force reindex after rebuild

    # Track what we did for the summary
    indexed_notes = 0
    indexed_linked = 0
    search_synced = 0
    removed_count = 0

    # Count and index changed notes
    files_count = count_files_to_index(force=force, notebook=notebook)

    if files_count > 0:
        scope = f"'{notebook}'" if notebook else "all notebooks"
        with progress_bar(f"Scanning {scope}", total=files_count) as advance:
            indexed_notes = index_all_notes(
                force=force,
                notebook=notebook,
                on_progress=advance,
            )

    # Index linked notes (always re-scanned)
    linked_total = count_linked_notes(notebook_filter=notebook)
    if linked_total > 0:
        with progress_bar("Scanning linked notes", total=linked_total) as advance:
            indexed_linked = scan_linked_notes(
                notebook_filter=notebook,
                on_progress=advance,
            )

    if embeddings:
        # Rebuild semantic search vectors
        search_total = count_notes_for_search_rebuild(notebook=notebook)
        if search_total > 0:
            from nb.index.scanner import rebuild_search_index

            with progress_bar("Building embeddings", total=search_total) as advance:
                search_synced = rebuild_search_index(
                    notebook=notebook,
                    on_progress=advance,
                )
    else:
        # Sync any notes missing from VectorDB (lightweight operation)
        from nb.index.scanner import sync_search_index

        with spinner("Syncing search index"):
            search_synced = sync_search_index(notebook=notebook)

    # Clean up notes and todos for files that no longer exist
    removed_count = remove_deleted_notes(notebook=notebook)

    # Print summary
    console.print()
    if indexed_notes > 0:
        console.print(f"[green]Indexed {indexed_notes} notes[/green]")
    else:
        console.print("[dim]Notes: no changes[/dim]")

    if indexed_linked > 0:
        console.print(f"[dim]Linked notes: {indexed_linked} scanned[/dim]")

    if search_synced > 0:
        if embeddings:
            console.print(f"[dim]Search: {search_synced} embeddings built[/dim]")
        else:
            console.print(f"[dim]Search: {search_synced} notes synced[/dim]")

    if removed_count > 0:
        console.print(f"[dim]Cleanup: {removed_count} deleted notes removed[/dim]")

    # Todo summary
    stats = get_todo_stats()
    todo_line = f"Todos: {stats['open']} open, {stats['completed']} completed"
    if stats["overdue"]:
        todo_line += f" [red]({stats['overdue']} overdue)[/red]"
    console.print(todo_line)


@click.command("stream")
@click.option(
    "--notebook", "-n", help="Filter by notebook", shell_complete=complete_notebook
)
@click.option(
    "--when", "-w", help="Date range: 'last week', 'this week', 'last 3 days'"
)
@click.option("--since", help="Start from this date")
@click.option("--until", help="End at this date")
@click.option("--reverse", "-r", is_flag=True, help="Show oldest first")
@click.option("--recent", is_flag=True, help="Stream recently viewed notes")
@click.option(
    "--by-date", is_flag=True, help="Sort by note date instead of modification time"
)
@click.option("--limit", "-l", default=50, help="Limit number of notes")
@click.option(
    "--continuous",
    "--auto",
    "-c",
    is_flag=True,
    help="Show all notes in continuous flow with dividers",
)
def stream_notes(
    notebook: str | None,
    when: str | None,
    since: str | None,
    until: str | None,
    reverse: bool,
    recent: bool,
    by_date: bool,
    limit: int,
    continuous: bool,
) -> None:
    """Browse notes interactively in a streaming view.

    By default shows recently modified notes (most recent first).
    When piped, outputs plain text without the TUI.

    Navigate through notes with keyboard controls:

    \b
    j/k            - Next/previous note
    n/N or p       - Next/previous note (alternate)
    g/G            - First/last note
    /              - Search notes by title or content
    ↑/↓            - Scroll within note (when focused)
    e              - Edit current note (in-app)
    E              - Edit in external editor
    Tab            - Focus content area for scrolling
    q              - Quit

    \b
    Examples:
      nb stream                      # Recently modified notes (default)
      nb stream --by-date            # Notes sorted by date
      nb stream -c                   # Continuous flow with dividers
      nb stream -n daily             # Stream daily notes
      nb stream -w "last week"       # Last week's notes
      nb stream -w "this week"       # This week's notes
      nb stream -n daily -w "last 2 weeks"  # Daily notes from last 2 weeks
      nb stream --recent             # Recently viewed notes
      nb stream --recent -l 20       # Last 20 viewed notes
      nb stream -c -w "this week"    # Continuous flow of this week
      nb stream | head -100          # Pipe first 100 lines

    """
    import sys
    from datetime import date as date_type

    from nb.index.db import get_db
    from nb.models import Note
    from nb.tui.stream import run_note_stream
    from nb.utils.dates import parse_date_range, parse_fuzzy_date

    config = get_config()

    # Check if output is piped (not a tty)
    is_piped = not sys.stdout.isatty()

    # Check for mutually exclusive options
    if recent and by_date:
        console.print("[red]Cannot use both --recent and --by-date[/red]")
        raise SystemExit(1)

    # Helper function to output notes to pipe
    def output_notes_to_pipe(notes_list: list[Note]) -> None:
        """Output notes as plain text to stdout (for piping)."""
        for note in notes_list:
            # Get full path
            if note.path.is_absolute():
                full_path = note.path
            else:
                full_path = config.notes_root / note.path

            # Read content
            try:
                content = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                content = "[Error reading file]"

            # Output header
            title = note.title or "Untitled"
            date_str = note.date.strftime(config.date_format) if note.date else ""
            notebook_str = f"[{note.notebook}]" if note.notebook else ""
            print(f"# {title}")
            if date_str or notebook_str:
                print(f"{date_str} {notebook_str}".strip())
            print(f"Path: {note.path}")
            print("-" * 40)
            print(content)
            print("\n" + "=" * 60 + "\n")

    # Helper function to convert path/mtime data to Note objects
    def paths_to_notes(path_data: list[tuple]) -> list[Note]:
        """Convert list of (path, ...) tuples to Note objects."""
        notes_list = []
        db = get_db()
        for item in path_data:
            path = item[0]
            try:
                rel_path = normalize_path(path.relative_to(config.notes_root))
            except ValueError:
                rel_path = normalize_path(path)
            row = db.fetchone(
                "SELECT title, date, notebook FROM notes WHERE path = ?",
                (rel_path,),
            )
            if row:
                note_date = None
                if row["date"]:
                    try:
                        note_date = date_type.fromisoformat(row["date"])
                    except ValueError:
                        pass
                notes_list.append(
                    Note(
                        path=Path(rel_path),
                        title=row["title"] or "",
                        date=note_date,
                        tags=[],
                        links=[],
                        attachments=[],
                        notebook=row["notebook"] or "",
                        content_hash="",
                    )
                )
        return notes_list

    # Handle --recent (recently viewed) mode
    if recent:
        from nb.core.notes import get_recently_viewed_notes

        view_data = get_recently_viewed_notes(limit=limit * 2, notebook=notebook)
        if not view_data:
            console.print("[yellow]No view history found.[/yellow]")
            return

        # Deduplicate by path, keeping first (most recent) occurrence
        seen_paths: set[Path] = set()
        unique_views = []
        for path, viewed_at in view_data:
            resolved = path.resolve()
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                unique_views.append((path, viewed_at))
                if len(unique_views) >= limit:
                    break

        notes = paths_to_notes(unique_views)
        if reverse:
            notes = list(reversed(notes))

        if not notes:
            console.print("[yellow]No notes found.[/yellow]")
            return

        if is_piped:
            output_notes_to_pipe(notes)
        else:
            console.print(f"[dim]Loading {len(notes)} notes...[/dim]")
            run_note_stream(notes, config.notes_root, continuous=continuous)
        return

    # Handle --by-date mode or date filter options (when/since/until)
    if by_date or when or since or until:
        db = get_db()

        # Build query
        query = "SELECT path, title, date, notebook FROM notes WHERE 1=1"
        params: list = []

        # Filter by notebook
        if notebook:
            query += " AND notebook = ?"
            params.append(notebook)

        # Filter by date range
        if when:
            start, end = parse_date_range(when)
            if start:
                query += " AND date >= ?"
                params.append(start.isoformat())
            if end:
                query += " AND date <= ?"
                params.append(end.isoformat())
        else:
            if since:
                since_date = parse_fuzzy_date(since)
                if since_date:
                    query += " AND date >= ?"
                    params.append(since_date.isoformat())

            if until:
                until_date = parse_fuzzy_date(until)
                if until_date:
                    query += " AND date <= ?"
                    params.append(until_date.isoformat())

        # Order by date
        if reverse:
            query += " ORDER BY date ASC"
        else:
            query += " ORDER BY date DESC"

        if limit:
            query += f" LIMIT {limit}"

        rows = db.fetchall(query, tuple(params))

        if not rows:
            console.print("[yellow]No notes found.[/yellow]")
            return

        # Convert to Note objects
        notes = []
        for row in rows:
            note_date = None
            if row["date"]:
                try:
                    note_date = date_type.fromisoformat(row["date"])
                except ValueError:
                    pass

            notes.append(
                Note(
                    path=Path(row["path"]),
                    title=row["title"] or "",
                    date=note_date,
                    tags=[],
                    links=[],
                    attachments=[],
                    notebook=row["notebook"] or "",
                    content_hash="",
                )
            )

        if is_piped:
            output_notes_to_pipe(notes)
        else:
            console.print(f"[dim]Loading {len(notes)} notes...[/dim]")
            run_note_stream(notes, config.notes_root, continuous=continuous)
        return

    # Default: recently modified notes (most recent first)
    from nb.core.notes import get_recently_modified_notes

    mod_data = get_recently_modified_notes(limit=limit, notebook=notebook)
    if not mod_data:
        console.print("[yellow]No notes found.[/yellow]")
        return

    notes = paths_to_notes(mod_data)
    if reverse:
        notes = list(reversed(notes))

    if not notes:
        console.print("[yellow]No notes found.[/yellow]")
        return

    if is_piped:
        output_notes_to_pipe(notes)
    else:
        console.print(f"[dim]Loading {len(notes)} notes...[/dim]")
        run_note_stream(notes, config.notes_root, continuous=continuous)
