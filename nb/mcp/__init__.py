"""MCP (Model Context Protocol) memory server for nb.

Exposes an `nb` notes store as portable, cross-tool memory for any MCP-capable
agent or chat UI (Claude Desktop, Claude Code, Cursor, ...). Markdown files stay
the source of truth; the index is a rebuildable cache.

See etc/mcp-memory-spec.md for the full design. Entry point: `nb serve --mcp`
(or the `nb-mcp` console script).
"""

from __future__ import annotations
