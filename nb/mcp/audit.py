"""Audit log for MCP agent writes.

Every write the server performs appends a line to ``<notes_root>/.nb/mcp.log``
when ``mcp.log_writes`` is enabled, so the human can review what agents did via
``nb mcp log``. See etc/mcp-memory-spec.md §9.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

LOG_FILENAME = "mcp.log"


def get_log_path(notes_root: Path) -> Path:
    """Return the path to the MCP audit log."""
    return notes_root / ".nb" / LOG_FILENAME


def log_write(
    notes_root: Path,
    client: str,
    tool: str,
    target: str,
    summary: str,
    enabled: bool = True,
    now: datetime | None = None,
) -> None:
    """Append a single audit line: ``ts · client · tool · target · summary``.

    A no-op when ``enabled`` is False. Best-effort: logging failures never
    propagate to the agent-facing tool call.
    """
    if not enabled:
        return
    if now is None:
        now = datetime.now()

    # Keep summaries to a single, readable line.
    summary = " ".join(summary.split())
    if len(summary) > 200:
        summary = summary[:197] + "..."

    line = f"{now.isoformat(timespec='seconds')} · {client} · {tool} · {target} · {summary}\n"

    try:
        log_path = get_log_path(notes_root)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        # Auditing must never break the actual write.
        pass


def read_log(notes_root: Path, limit: int | None = None) -> list[str]:
    """Return the audit log lines (most recent last), optionally tail-limited."""
    log_path = get_log_path(notes_root)
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    if limit is not None and limit > 0:
        lines = lines[-limit:]
    return lines
