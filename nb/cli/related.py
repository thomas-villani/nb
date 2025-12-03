"""Related notes CLI command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
from nb.cli.completion import complete_notebook
from nb.cli.utils import console, resolve_note_ref
from nb.config import get_config


def register_related_commands(cli: click.Group) -> None:
    """Register related commands with the CLI."""
    cli.add_command(related_cmd)


@dataclass
class RelatedNote:
    """A note related to the query note."""

    path: str
    title: str
    score: float
    reasons: list[str]  # Why it's related


@click.command("related")
@click.argument("note_ref")
@click.option(
    "--notebook",
    "-n",
    help="Notebook context for resolving note reference",
    shell_complete=complete_notebook,
)
@click.option(
    "--limit",
    "-l",
    default=10,
    type=int,
    help="Maximum number of related notes to show (default: 10)",
)
@click.option(
    "--links-only",
    is_flag=True,
    help="Only consider direct links (no tags or semantic)",
)
@click.option(
    "--tags-only",
    is_flag=True,
    help="Only consider shared tags",
)
@click.option(
    "--semantic-only",
    is_flag=True,
    help="Only use semantic similarity",
)
def related_cmd(
        note_ref: str,
        notebook: str | None,
        limit: int,
        links_only: bool,
        tags_only: bool,
        semantic_only: bool,
) -> None:
    """Find notes related to the given note.

    Combines multiple signals to find related notes:
    - Direct links (outgoing and incoming)
    - Shared tags
    - Semantic similarity (using embeddings)

    \b
    Examples:
      nb related today            Related to today's note
      nb related myproject        Related to myproject
      nb related today -l 5       Show top 5 related
      nb related today --tags-only  Only by shared tags
    """
    config = get_config()

    # Resolve note reference
    path = resolve_note_ref(note_ref, notebook=notebook)
    if not path:
        raise SystemExit(1)

    # Get relative path for display and database queries
    try:
        rel_path = path.relative_to(config.notes_root)
    except ValueError:
        rel_path = path

    rel_path_str = str(rel_path).replace("\\", "/")

    console.print(f"[bold]Notes related to {rel_path.stem}[/bold]\n")

    # Collect related notes with scores
    related: dict[str, RelatedNote] = {}

    # 1. Direct links (weight: 1.0 for outgoing, 0.9 for backlinks)
    if not tags_only and not semantic_only:
        _add_link_relations(path, rel_path_str, related, config)

    # 2. Shared tags (weight: 0.3 per shared tag)
    if not links_only and not semantic_only:
        _add_tag_relations(rel_path_str, related, config)

    # 3. Semantic similarity (weight: 0.5 * similarity score)
    if not links_only and not tags_only:
        _add_semantic_relations(path, rel_path_str, related, config, limit)

    if not related:
        console.print("[dim]No related notes found.[/dim]")
        return

    # Sort by score and display
    sorted_related = sorted(related.values(), key=lambda x: x.score, reverse=True)[
        :limit
    ]

    for i, note in enumerate(sorted_related, 1):
        # Format reasons
        reason_str = ", ".join(note.reasons[:3])
        if len(note.reasons) > 3:
            reason_str += f" +{len(note.reasons) - 3} more"

        # Score indicator
        score_bar = "█" * min(int(note.score * 5), 10)
        score_color = (
            "green" if note.score >= 0.8 else "yellow" if note.score >= 0.4 else "dim"
        )

        console.print(
            f"{i:2}. [{score_color}]{score_bar:10}[/{score_color}] "
            f"[cyan]{note.title}[/cyan]"
        )
        console.print(f"    [dim]{note.path}[/dim]")
        console.print(f"    [dim]{reason_str}[/dim]\n")


def _add_link_relations(
        path: Path,
        rel_path_str: str,
        related: dict[str, RelatedNote],
        config,
) -> None:
    """Add related notes from direct links."""
    from nb.core.note_links import get_backlinks, get_outgoing_links
    from nb.index.db import get_db

    db = get_db()

    # Outgoing links (weight: 1.0)
    outgoing = get_outgoing_links(path, internal_only=True)
    for link in outgoing:
        if link.resolved_path:
            try:
                target_rel = link.resolved_path.relative_to(config.notes_root)
            except ValueError:
                target_rel = link.resolved_path
            target_str = str(target_rel).replace("\\", "/")

            if target_str == rel_path_str:
                continue  # Skip self

            # Get title from database
            row = db.fetchone("SELECT title FROM notes WHERE path = ?", (target_str,))
            title = row["title"] if row else target_rel.stem

            if target_str in related:
                related[target_str].score += 1.0
                related[target_str].reasons.append("linked to")
            else:
                related[target_str] = RelatedNote(
                    path=target_str,
                    title=title,
                    score=1.0,
                    reasons=["linked to"],
                )

    # Backlinks (weight: 0.9)
    backlinks = get_backlinks(path)
    for bl in backlinks:
        source_str = str(bl.source_path).replace("\\", "/")

        if source_str == rel_path_str:
            continue  # Skip self

        # Get title from database
        row = db.fetchone("SELECT title FROM notes WHERE path = ?", (source_str,))
        title = row["title"] if row else bl.source_path.stem

        if source_str in related:
            related[source_str].score += 0.9
            related[source_str].reasons.append("links here")
        else:
            related[source_str] = RelatedNote(
                path=source_str,
                title=title,
                score=0.9,
                reasons=["links here"],
            )


def _add_tag_relations(
        rel_path_str: str,
        related: dict[str, RelatedNote],
        config,
) -> None:
    """Add related notes from shared tags."""
    from nb.index.db import get_db

    db = get_db()

    # Get tags for the source note
    tag_rows = db.fetchall(
        "SELECT tag FROM note_tags WHERE note_path = ?",
        (rel_path_str,),
    )
    source_tags = {row["tag"] for row in tag_rows}

    if not source_tags:
        return

    # Find notes that share tags
    placeholders = ", ".join("?" for _ in source_tags)
    shared_rows = db.fetchall(
        f"""SELECT note_path, tag FROM note_tags
            WHERE tag IN ({placeholders}) AND note_path != ?""",
        (*source_tags, rel_path_str),
    )

    # Group by note and count shared tags
    note_tags: dict[str, set[str]] = {}
    for row in shared_rows:
        np = row["note_path"]
        if np not in note_tags:
            note_tags[np] = set()
        note_tags[np].add(row["tag"])

    # Add to related with weight 0.3 per shared tag
    for note_path, tags in note_tags.items():
        weight = 0.3 * len(tags)
        tag_list = list(tags)[:3]
        reason = f"shared tags: #{', #'.join(tag_list)}"
        if len(tags) > 3:
            reason += f" +{len(tags) - 3}"

        # Get title
        title_row = db.fetchone("SELECT title FROM notes WHERE path = ?", (note_path,))
        title = title_row["title"] if title_row else Path(note_path).stem

        if note_path in related:
            related[note_path].score += weight
            related[note_path].reasons.append(reason)
        else:
            related[note_path] = RelatedNote(
                path=note_path,
                title=title,
                score=weight,
                reasons=[reason],
            )


def _add_semantic_relations(
        path: Path,
        rel_path_str: str,
        related: dict[str, RelatedNote],
        config,
        limit: int,
) -> None:
    """Add related notes from semantic similarity."""
    try:
        from nb.index.search import get_search

        search = get_search()

        # Get the note content for semantic search
        if path.exists():
            content = path.read_text(encoding="utf-8")
            # Use first 1000 chars for query
            query = content[:1000]

            # Search for similar notes
            results = search.search(query, k=limit + 5)  # Extra to filter self

            for result in results:
                result_path = result.path.replace("\\", "/")

                if result_path == rel_path_str:
                    continue  # Skip self

                # Weight by similarity (0.5 * score, capped)
                weight = min(0.5 * result.score, 0.8) if result.score else 0.3
                reason = (
                    f"similar content ({result.score:.0%})"
                    if result.score
                    else "similar content"
                )

                if result_path in related:
                    related[result_path].score += weight
                    related[result_path].reasons.append(reason)
                else:
                    related[result_path] = RelatedNote(
                        path=result_path,
                        title=result.title or Path(result_path).stem,
                        score=weight,
                        reasons=[reason],
                    )
    except Exception:
        # Semantic search may not be available
        pass
