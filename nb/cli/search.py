"""Search-related CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from nb.cli.utils import console
from nb.config import get_config


def register_search_commands(cli: click.Group) -> None:
    """Register all search-related commands with the CLI."""
    cli.add_command(search_cmd)
    cli.add_command(grep_cmd)
    cli.add_command(index_cmd)
    cli.add_command(stream_notes)


@click.command("search")
@click.argument("query")
@click.option(
    "-s", "--semantic", is_flag=True, help="Use pure semantic search (no keyword)"
)
@click.option(
    "-k", "--keyword", is_flag=True, help="Use pure keyword search (no semantic)"
)
@click.option("-t", "--tag", help="Filter by tag")
@click.option("--notebook", "-n", help="Filter by notebook")
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
def search_cmd(
    query: str,
    semantic: bool,
    keyword: bool,
    tag: str | None,
    notebook: str | None,
    when_filter: str | None,
    since_date: str | None,
    until_date: str | None,
    recent: bool,
    limit: int,
) -> None:
    """Search notes by keyword, semantic similarity, or both (hybrid).

    By default uses hybrid search (70% semantic, 30% keyword).
    Use --semantic for pure semantic search, --keyword for pure keyword search.

    Date filtering:
        --when "last 3 months"    Fuzzy date range
        --when "this week"        Current week
        --since friday            From a date onwards
        --until "nov 20"          Up to a date

    Examples:
        nb search "machine learning"
        nb search -s "project ideas" --recent
        nb search "TODO" --when "last 2 weeks"
        nb search "meeting notes" --since "last monday"

    """
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
    filters = {}
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
        search = get_search()
        results = search.search(
            query,
            search_type=search_type,
            k=limit,
            filters=filters if filters else None,
            date_start=date_start,
            date_end=date_end,
            recency_boost=recency_boost,
        )
    except Exception as e:
        console.print(f"[red]Search failed:[/red] {e}")
        console.print(
            "[dim]Make sure the index is built and embeddings are available.[/dim]"
        )
        raise SystemExit(1)

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
def grep_cmd(pattern: str, context_lines: int, ignore_case: bool) -> None:
    """Search notes with regex pattern matching.

    Unlike 'search', this performs raw regex matching on the files.
    Useful for finding exact strings, code snippets, or patterns.

    Examples:
        nb grep "TODO.*urgent"
        nb grep "def\\s+\\w+" -C 5
        nb grep "API_KEY" --case-sensitive

    """
    from nb.index.search import grep_notes

    config = get_config()

    try:
        results = grep_notes(
            pattern,
            config.notes_root,
            context_lines=context_lines,
            case_sensitive=not ignore_case,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

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
@click.option("--notebook", "-n", help="Only reindex this notebook")
def index_cmd(
    force: bool, rebuild: bool, embeddings: bool, notebook: str | None
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
    """
    from nb.index.scanner import index_all_notes
    from nb.index.todos_repo import get_todo_stats

    if rebuild:
        if notebook:
            console.print("[red]Cannot use --rebuild with --notebook[/red]")
            raise SystemExit(1)
        console.print("[yellow]Rebuilding database from scratch...[/yellow]")
        from nb.index.db import get_db, rebuild_db

        db = get_db()
        rebuild_db(db)
        console.print("[green]Database rebuilt.[/green]")
        force = True  # Force reindex after rebuild

    if notebook:
        console.print(f"[dim]Indexing notebook '{notebook}'...[/dim]")
    else:
        console.print("[dim]Indexing notes...[/dim]")
    count = index_all_notes(force=force, notebook=notebook)
    console.print(f"[green]Indexed {count} files.[/green]")

    # Also reindex linked notes (skip if specific notebook requested)
    if not notebook:
        from nb.index.scanner import scan_linked_notes

        linked_count = scan_linked_notes()
        if linked_count:
            console.print(f"[green]Indexed {linked_count} linked notes.[/green]")

    if embeddings:
        console.print("[dim]Rebuilding search index...[/dim]")
        from nb.index.scanner import rebuild_search_index

        search_count = rebuild_search_index()
        console.print(f"[green]Indexed {search_count} notes for search.[/green]")

    stats = get_todo_stats()
    console.print(f"Todos: {stats['open']} open, {stats['completed']} completed")
    if stats["overdue"]:
        console.print(f"[red]{stats['overdue']} overdue[/red]")


@click.command("stream")
@click.option("--notebook", "-n", help="Filter by notebook")
@click.option(
    "--when", "-w", help="Date range: 'last week', 'this week', 'last 3 days'"
)
@click.option("--since", help="Start from this date")
@click.option("--until", help="End at this date")
@click.option("--reverse", "-r", is_flag=True, help="Show oldest first")
@click.option("--recent", is_flag=True, help="Stream recently viewed notes")
@click.option(
    "--recently-modified", is_flag=True, help="Stream recently modified notes"
)
@click.option(
    "--limit", "-l", default=50, help="Limit for --recent/--recently-modified"
)
def stream_notes(
    notebook: str | None,
    when: str | None,
    since: str | None,
    until: str | None,
    reverse: bool,
    recent: bool,
    recently_modified: bool,
    limit: int,
) -> None:
    """Browse notes interactively in a streaming view.

    Navigate through notes with keyboard controls:

    \b
    j/k or ↑/↓     - Scroll within note
    ←/→ or PgUp/Dn - Previous/next note
    n/N or p       - Next/previous note
    g/G            - First/last note (or top/bottom of current)
    d/u            - Half-page down/up
    e              - Edit current note
    q              - Quit

    Examples:
    \b
      nb stream                      # Stream all notes
      nb stream -n daily             # Stream daily notes
      nb stream -w "last week"       # Last week's notes
      nb stream -w "this week"       # This week's notes
      nb stream -n daily -w "last 2 weeks"  # Daily notes from last 2 weeks
      nb stream --recent             # Recently viewed notes
      nb stream --recently-modified  # Recently modified notes
      nb stream --recent -l 20       # Last 20 viewed notes

    """
    from datetime import date as date_type

    from nb.index.db import get_db
    from nb.models import Note
    from nb.tui.stream import run_note_stream
    from nb.utils.dates import parse_date_range, parse_fuzzy_date

    config = get_config()

    # Check for mutually exclusive options
    if recent and recently_modified:
        console.print("[red]Cannot use both --recent and --recently-modified[/red]")
        raise SystemExit(1)

    # Handle --recent (recently viewed) and --recently-modified modes
    if recent or recently_modified:
        from nb.core.notes import get_recently_modified_notes, get_recently_viewed_notes

        if recent:
            # Get recently viewed notes
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

            # Convert to Note objects
            notes = []
            db = get_db()
            for path, viewed_at in unique_views:
                # Look up note info from database
                rel_path = str(path.relative_to(config.notes_root))
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
                    notes.append(
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

            if reverse:
                notes = list(reversed(notes))

        else:
            # Get recently modified notes
            mod_data = get_recently_modified_notes(limit=limit, notebook=notebook)
            if not mod_data:
                console.print("[yellow]No notes found.[/yellow]")
                return

            # Convert to Note objects
            notes = []
            db = get_db()
            for path, mtime in mod_data:
                # Look up note info from database
                rel_path = str(path.relative_to(config.notes_root))
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
                    notes.append(
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

            if reverse:
                notes = list(reversed(notes))

        if not notes:
            console.print("[yellow]No notes found.[/yellow]")
            return

        console.print(f"[dim]Loading {len(notes)} notes...[/dim]")
        run_note_stream(notes, config.notes_root)
        return

    # Standard date-based query
    db = get_db()

    # Build query
    query = "SELECT path, title, date, notebook FROM notes WHERE 1=1"
    params: list = []

    # Filter by notebook
    if notebook:
        query += " AND notebook = ?"
        params.append(notebook)

    # Filter by date range
    # --when takes precedence and uses parse_date_range for week support
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

    console.print(f"[dim]Loading {len(notes)} notes...[/dim]")
    run_note_stream(notes, config.notes_root)
