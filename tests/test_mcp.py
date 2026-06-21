"""Tests for the MCP memory server (nb/mcp).

Most tests run without API keys: they exercise remember/read_note/list_notebooks
and provenance/audit at the filesystem level. The real recall round-trip needs an
embeddings backend, so it is marked `vectorized`; recall's formatting/allowlist
logic is unit-tested here with a stubbed search.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest

from nb.config import Config
from nb.index.search import SearchResult
from nb.mcp import audit, provenance
from nb.mcp.server import ensure_memory_notebook
from nb.mcp.tools_memory import (
    MemoryContext,
    list_notebooks,
    read_note,
    recall,
    remember,
)

requires_openai_key = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="requires OPENAI_API_KEY environment variable",
)


@pytest.fixture
def mcp_ctx(mock_cli_config: Config) -> MemoryContext:
    """A MemoryContext over the test config, with the memory notebook ensured."""
    ensure_memory_notebook("memory")
    return MemoryContext(
        config=mock_cli_config,
        memory_notebook="memory",
        client="test-client",
        session="sess01",
    )


# --------------------------------------------------------------------------- #
# provenance (pure)
# --------------------------------------------------------------------------- #
def test_build_memory_block_has_tags_and_comment() -> None:
    block = provenance.build_memory_block(
        "Tom prefers uv.",
        client="claude-desktop",
        session="abc123",
        tags=["tooling", "#python"],
        now=datetime(2026, 6, 16, 14, 32, 5),
    )
    assert "## 2026-06-16 14:32 · claude-desktop" in block
    assert "#memory #agent #tooling #python" in block
    assert "Tom prefers uv." in block
    assert (
        "<!-- nb-mem: client=claude-desktop session=abc123 ts=2026-06-16T14:32:05 -->"
        in block
    )


def test_ensure_agent_frontmatter_idempotent() -> None:
    text = "---\ndate: 2026-06-16\n---\n\n# Mon\n\nbody\n"
    once = provenance.ensure_agent_frontmatter(text)
    assert "source: agent" in once
    assert "nb_managed: mcp" in once
    assert "body" in once
    # Second pass should not change anything.
    assert provenance.ensure_agent_frontmatter(once) == once


# --------------------------------------------------------------------------- #
# remember
# --------------------------------------------------------------------------- #
def test_remember_writes_dated_provenance_note(mcp_ctx: MemoryContext) -> None:
    msg = remember(mcp_ctx, "Tom prefers uv for all Python tooling.", tags=["tooling"])

    today = date.today().isoformat()
    assert f"memory/{today}" in msg
    assert "#memory #agent #tooling" in msg

    # Locate the written file under the memory notebook.
    memory_files = list((mcp_ctx.notes_root / "memory").rglob(f"{today}.md"))
    assert len(memory_files) == 1
    content = memory_files[0].read_text(encoding="utf-8")

    assert "source: agent" in content
    assert "nb_managed: mcp" in content
    assert "Tom prefers uv for all Python tooling." in content
    assert "#memory #agent #tooling" in content
    assert "nb-mem: client=test-client" in content


def test_remember_auto_creates_memory_notebook(mock_cli_config: Config) -> None:
    # 'brain' is not in the default test notebooks.
    assert mock_cli_config.get_notebook("brain") is None
    ensure_memory_notebook("brain")
    nb = mock_cli_config.get_notebook("brain")
    assert nb is not None
    assert nb.date_based is True


def test_remember_appends_multiple_blocks(mcp_ctx: MemoryContext) -> None:
    remember(mcp_ctx, "First fact.")
    remember(mcp_ctx, "Second fact.")
    today = date.today().isoformat()
    content = next((mcp_ctx.notes_root / "memory").rglob(f"{today}.md")).read_text(
        encoding="utf-8"
    )
    assert "First fact." in content
    assert "Second fact." in content
    # Two memory blocks, one frontmatter sentinel.
    assert content.count("nb-mem:") == 2
    assert content.count("source: agent") == 1


def test_remember_empty_is_noop(mcp_ctx: MemoryContext) -> None:
    msg = remember(mcp_ctx, "   ")
    assert "Nothing to remember" in msg


# --------------------------------------------------------------------------- #
# audit log
# --------------------------------------------------------------------------- #
def test_remember_writes_audit_log(mcp_ctx: MemoryContext) -> None:
    remember(mcp_ctx, "A durable fact about Tom.")
    lines = audit.read_log(mcp_ctx.notes_root)
    assert len(lines) == 1
    assert "test-client" in lines[0]
    assert "remember" in lines[0]
    assert "A durable fact about Tom." in lines[0]


def test_audit_disabled_writes_nothing(mock_cli_config: Config) -> None:
    ensure_memory_notebook("memory")
    ctx = MemoryContext(
        config=mock_cli_config,
        memory_notebook="memory",
        client="test-client",
        log_writes=False,
    )
    remember(ctx, "Should not be logged.")
    assert audit.read_log(ctx.notes_root) == []


# --------------------------------------------------------------------------- #
# read_note
# --------------------------------------------------------------------------- #
def test_read_note_by_path(mcp_ctx: MemoryContext) -> None:
    note = mcp_ctx.notes_root / "projects" / "design.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("# Design\n\nThe plan is X.\n", encoding="utf-8")

    out = read_note(mcp_ctx, "projects/design.md")
    assert "The plan is X." in out


def test_read_note_rejects_nb_internals(mcp_ctx: MemoryContext) -> None:
    secret = mcp_ctx.notes_root / ".nb" / ".env"
    secret.write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    out = read_note(mcp_ctx, ".nb/.env")
    assert "sk-secret" not in out
    assert "Refusing to read internal" in out


def test_read_note_missing(mcp_ctx: MemoryContext) -> None:
    assert "not found" in read_note(mcp_ctx, "projects/nope.md").lower()


# --------------------------------------------------------------------------- #
# list_notebooks
# --------------------------------------------------------------------------- #
def test_list_notebooks_flags_memory_sink(mcp_ctx: MemoryContext) -> None:
    out = list_notebooks(mcp_ctx)
    assert "projects" in out
    assert "memory sink" in out
    # The memory notebook line carries the sink flag.
    sink_line = next(line for line in out.splitlines() if "memory sink" in line)
    assert sink_line.startswith("- memory")


# --------------------------------------------------------------------------- #
# read allowlist
# --------------------------------------------------------------------------- #
def test_readable_allowlist_blocks_other_notebooks(mock_cli_config: Config) -> None:
    ensure_memory_notebook("memory")
    ctx = MemoryContext(
        config=mock_cli_config,
        memory_notebook="memory",
        readable_notebooks=["memory"],
        client="test-client",
    )
    note = ctx.notes_root / "projects" / "secret.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("# Secret\n\nclassified\n", encoding="utf-8")

    out = read_note(ctx, "projects/secret.md")
    assert "classified" not in out
    assert "not readable" in out

    # And list_notebooks hides non-readable notebooks.
    listed = list_notebooks(ctx)
    assert "projects" not in listed
    assert "memory" in listed


# --------------------------------------------------------------------------- #
# recall (formatting/allowlist unit test with stubbed search)
# --------------------------------------------------------------------------- #
def test_recall_formats_and_filters(
    mcp_ctx: MemoryContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = [
        SearchResult(
            path="memory/2026/Jun15-Jun21/2026-06-16.md",
            title="Tooling preferences",
            snippet="Tom prefers uv.",
            score=0.82,
            notebook="memory",
            date="2026-06-16",
        ),
        SearchResult(
            path="projects/secret.md",
            title="Secret",
            snippet="classified",
            score=0.4,
            notebook="projects",
            date=None,
        ),
    ]

    class _Stub:
        def search(self, *a, **k):
            return list(results)

    monkeypatch.setattr("nb.index.search.get_search", lambda: _Stub())

    # No allowlist: both returned, with citations.
    out = recall(mcp_ctx, "what tooling does tom prefer")
    assert '[1] memory/2026-06-16 · "Tooling preferences" (score 0.82)' in out
    assert "Tom prefers uv." in out

    # With an allowlist, the non-readable notebook is filtered out.
    mcp_ctx.readable_notebooks = ["memory"]
    out2 = recall(mcp_ctx, "anything")
    assert "Tooling preferences" in out2
    assert "classified" not in out2


def test_recall_unknown_scope_rejected(mcp_ctx: MemoryContext) -> None:
    mcp_ctx.readable_notebooks = ["memory"]
    out = recall(mcp_ctx, "x", scope="projects")
    assert "not readable" in out


@pytest.mark.vectorized
@requires_openai_key
def test_remember_then_recall_roundtrip(mcp_ctx: MemoryContext) -> None:
    remember(mcp_ctx, "Tom's favourite database for side projects is SQLite.")
    out = recall(mcp_ctx, "what database does Tom like for side projects")
    assert "SQLite" in out
