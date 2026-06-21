"""Provenance helpers for agent-written memories.

Every memory the MCP server writes is unmistakably marked as agent-generated so
it is filterable everywhere and trivially reviewable/reversible:

- The day's memory note carries ``source: agent`` / ``nb_managed: mcp`` frontmatter.
- Each memory is a timestamped ``##`` block tagged ``#memory #agent`` with a
  machine-readable ``<!-- nb-mem: ... -->`` comment recording client/session/ts.

See etc/mcp-memory-spec.md §4.
"""

from __future__ import annotations

from datetime import datetime

import frontmatter

# Frontmatter sentinels written to the day's memory note (first write only).
AGENT_FRONTMATTER = {
    "source": "agent",  # sentinel: this note holds agent-written content
    "nb_managed": "mcp",  # written via the MCP server
}
MEMORY_TAG = "memory"
AGENT_TAG = "agent"


def ensure_agent_frontmatter(text: str) -> str:
    """Return ``text`` with the agent provenance frontmatter ensured.

    Adds ``source: agent`` / ``nb_managed: mcp`` and a ``memory`` tag to the
    note's frontmatter if absent, preserving the body. Idempotent.
    """
    post = frontmatter.loads(text)

    changed = False
    for key, value in AGENT_FRONTMATTER.items():
        if post.get(key) != value:
            post[key] = value
            changed = True

    tags = post.get("tags")
    if tags is None:
        post["tags"] = [MEMORY_TAG]
        changed = True
    elif isinstance(tags, list) and MEMORY_TAG not in tags:
        tags.append(MEMORY_TAG)
        changed = True

    if not changed:
        return text

    # frontmatter.dumps preserves the body; only the YAML block is rewritten.
    return frontmatter.dumps(post)


def build_memory_block(
    content: str,
    client: str,
    session: str,
    tags: list[str] | None = None,
    now: datetime | None = None,
) -> str:
    """Build a single timestamped memory block to append to the day's note.

    Returns markdown like::

        ## 2026-06-16 14:32 · claude-desktop
        #memory #agent #tooling

        <content>

        <!-- nb-mem: client=claude-desktop session=a1b2c3 ts=2026-06-16T14:32:05 -->
    """
    if now is None:
        now = datetime.now()

    user_tags = [t.lstrip("#") for t in (tags or []) if t.strip()]
    tag_line = " ".join(f"#{t}" for t in [MEMORY_TAG, AGENT_TAG, *user_tags])

    heading = f"## {now:%Y-%m-%d %H:%M} · {client}"
    comment = f"<!-- nb-mem: client={client} session={session} ts={now.isoformat(timespec='seconds')} -->"

    body = content.strip()
    return f"{heading}\n{tag_line}\n\n{body}\n\n{comment}\n"


def append_memory_block(text: str, block: str) -> str:
    """Append a memory ``block`` to existing note ``text`` with clean spacing."""
    if not text.endswith("\n"):
        text += "\n"
    if not text.endswith("\n\n"):
        text += "\n"
    return text + block
