"""Memory-tier MCP tools: recall, remember, list_notebooks, read_note.

Thin adapters over ``nb.core`` / ``nb.index`` — no business logic is duplicated
here. See etc/mcp-memory-spec.md §5.1.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from nb.config.models import Config

from . import audit, provenance


@dataclass
class MemoryContext:
    """Resolved server settings shared by all memory tools."""

    config: Config
    memory_notebook: str
    readable_notebooks: list[str] = field(default_factory=list)  # [] => all
    recency_boost: float = 0.3
    default_limit: int = 6
    log_writes: bool = True
    client: str = "unknown"
    session: str = field(default_factory=lambda: uuid.uuid4().hex[:6])

    @property
    def notes_root(self) -> Path:
        return self.config.notes_root

    def is_readable(self, notebook: str | None) -> bool:
        """Whether a notebook is within the read allowlist (empty => all)."""
        if not self.readable_notebooks:
            return True
        return notebook in self.readable_notebooks


# --------------------------------------------------------------------------- #
# recall
# --------------------------------------------------------------------------- #
def recall(
    ctx: MemoryContext,
    query: str,
    scope: str | None = None,
    limit: int | None = None,
    since: str | None = None,
) -> str:
    """Search the notes store and return ranked passages with citations."""
    from nb.index.search import get_search

    limit = limit or ctx.default_limit
    limit = max(1, min(int(limit), 20))

    if scope and not ctx.is_readable(scope):
        return f"Notebook '{scope}' is not readable by this server."

    filters = {"notebook": scope} if scope else None
    # Fetch extra when an allowlist may trim results post-hoc.
    fetch_k = limit if not ctx.readable_notebooks else max(limit * 3, 30)

    results = get_search().search(
        query,
        search_type="hybrid",
        k=fetch_k,
        filters=filters,
        date_start=since,
        recency_boost=ctx.recency_boost,
    )

    if ctx.readable_notebooks:
        results = [r for r in results if ctx.is_readable(r.notebook)]
    results = results[:limit]

    if not results:
        return f"No memories found for: {query!r}"

    lines: list[str] = []
    for i, r in enumerate(results, start=1):
        title = r.title or Path(r.path).stem
        locator = "/".join(p for p in (r.notebook, r.date) if p) or Path(r.path).name
        lines.append(f'[{i}] {locator} · "{title}" (score {r.score:.2f})')
        snippet = (r.snippet or "").strip()
        if snippet:
            lines.append(snippet)
        lines.append("")

    return "\n".join(lines).rstrip()


# --------------------------------------------------------------------------- #
# remember
# --------------------------------------------------------------------------- #
def remember(
    ctx: MemoryContext,
    content: str,
    tags: list[str] | None = None,
) -> str:
    """Append a memory to the memory notebook's note for today."""
    from nb.core.notebooks import ensure_notebook_note, is_notebook_date_based
    from nb.core.notes import _reindex_note_after_edit

    content = (content or "").strip()
    if not content:
        return "Nothing to remember: content was empty."

    today = date.today()
    nb_name = ctx.memory_notebook

    # Resolve today's note in the memory notebook (mirrors `nb today` behaviour).
    if is_notebook_date_based(nb_name):
        path = ensure_notebook_note(nb_name, dt=today)
    else:
        path = ensure_notebook_note(nb_name, dt=today, name=today.isoformat())

    text = path.read_text(encoding="utf-8")
    text = provenance.ensure_agent_frontmatter(text)
    block = provenance.build_memory_block(
        content,
        client=ctx.client,
        session=ctx.session,
        tags=tags,
        now=datetime.now(),
    )
    text = provenance.append_memory_block(text, block)
    path.write_text(text, encoding="utf-8")

    # Reindex inline so the memory is immediately recallable.
    _reindex_note_after_edit(path, ctx.notes_root)

    user_tags = [t.lstrip("#") for t in (tags or []) if t.strip()]
    tag_display = " ".join(
        f"#{t}" for t in [provenance.MEMORY_TAG, provenance.AGENT_TAG, *user_tags]
    )
    target = f"{nb_name}/{today.isoformat()}"
    audit.log_write(
        ctx.notes_root,
        client=ctx.client,
        tool="remember",
        target=target,
        summary=content,
        enabled=ctx.log_writes,
    )
    return f"Remembered in {target} ({tag_display})."


# --------------------------------------------------------------------------- #
# list_notebooks
# --------------------------------------------------------------------------- #
def list_notebooks(ctx: MemoryContext) -> str:
    """List notebooks (memory namespaces) with note counts."""
    from nb.core.notes import get_all_notes

    counts: dict[str, int] = {}
    for _path, _title, notebook, _tags in get_all_notes(notes_root=ctx.notes_root):
        if notebook:
            counts[notebook] = counts.get(notebook, 0) + 1

    lines: list[str] = []
    for nb in ctx.config.notebooks:
        if not ctx.is_readable(nb.name):
            continue
        n = counts.get(nb.name, 0)
        flags = []
        if nb.name == ctx.memory_notebook:
            flags.append("memory sink")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"- {nb.name} ({n} note{'s' if n != 1 else ''}){suffix}")

    # The memory notebook may not be registered yet if nothing was remembered.
    if ctx.is_readable(ctx.memory_notebook) and not any(
        nb.name == ctx.memory_notebook for nb in ctx.config.notebooks
    ):
        lines.append(f"- {ctx.memory_notebook} (0 notes) [memory sink]")

    return "\n".join(lines) if lines else "No notebooks found."


# --------------------------------------------------------------------------- #
# read_note
# --------------------------------------------------------------------------- #
def read_note(ctx: MemoryContext, ref: str) -> str:
    """Read the full content of a note by id or path."""
    from nb.core.note_parser import get_notebook_for_path
    from nb.core.notes import get_note_by_id

    ref = (ref or "").strip()
    if not ref:
        return "No note reference provided."

    notes_root = ctx.notes_root.resolve()

    # 1) Try id resolution (as returned in recall citations).
    path = get_note_by_id(ref, notes_root=ctx.notes_root)

    # 2) Fall back to path resolution (absolute or relative to notes_root).
    if path is None:
        candidate = Path(ref)
        path = candidate if candidate.is_absolute() else ctx.notes_root / candidate

    try:
        resolved = path.resolve()
    except OSError:
        return f"Could not resolve note: {ref}"

    # Never expose .nb internals (config, .env, index, logs).
    nb_dir = (notes_root / ".nb").resolve()
    if resolved == nb_dir or nb_dir in resolved.parents:
        return "Refusing to read internal .nb files."

    if not resolved.exists() or not resolved.is_file():
        return f"Note not found: {ref}"

    # Enforce the read allowlist by the note's notebook.
    notebook = get_notebook_for_path(resolved)
    if not ctx.is_readable(notebook):
        return f"Note '{ref}' is not readable by this server."

    return resolved.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def register_memory_tools(mcp, ctx: MemoryContext) -> None:
    """Register the four memory-tier tools on a FastMCP instance."""

    @mcp.tool(name="recall")
    def recall_tool(
        query: str,
        scope: str | None = None,
        limit: int | None = None,
        since: str | None = None,
    ) -> str:
        """Search the user's personal notes/memory for relevant information.

        Returns ranked passages with citations. Use this before answering
        questions about the user's past decisions, preferences, projects, or
        anything they may have told you before.

        Args:
            query: Natural-language description of what to recall.
            scope: Optional notebook name to restrict the search.
            limit: Max passages to return (1-20, default from config).
            since: Optional ISO date; only recall memories on/after this date.
        """
        return recall(ctx, query, scope=scope, limit=limit, since=since)

    @mcp.tool(name="remember")
    def remember_tool(content: str, tags: list[str] | None = None) -> str:
        """Store a fact, preference, or note in the user's long-term memory.

        The memory can be recalled in future conversations across any tool. Use
        when the user shares durable information worth keeping.

        Args:
            content: The fact/note to remember, in clear standalone prose.
            tags: Optional topical tags (without the leading #).
        """
        return remember(ctx, content, tags=tags)

    @mcp.tool(name="list_notebooks")
    def list_notebooks_tool() -> str:
        """List the user's notebooks (memory namespaces) with note counts."""
        return list_notebooks(ctx)

    @mcp.tool(name="read_note")
    def read_note_tool(ref: str) -> str:
        """Read the full content of a note by its path or id.

        Args:
            ref: Note path or id, as returned in recall citations.
        """
        return read_note(ctx, ref)
