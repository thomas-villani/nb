"""FastMCP server entry point for nb's pluggable memory.

Run via ``nb serve --mcp`` or the ``nb-mcp`` console script. Transport is stdio
only (v1): the MCP client launches this process and talks to it over stdin/stdout,
so all human-facing notices MUST go to stderr to avoid corrupting the protocol.

See etc/mcp-memory-spec.md.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

from nb.config import Config

from .tools_memory import MemoryContext, register_memory_tools

if TYPE_CHECKING:
    from fastmcp import FastMCP

DEFAULT_MEMORY_NOTEBOOK = "memory"


def _eprint(message: str) -> None:
    """Print a notice to stderr (stdout is reserved for the MCP protocol)."""
    print(message, file=sys.stderr, flush=True)


def resolve_memory_notebook(config: Config, override: str | None = None) -> str:
    """Resolve the memory sink notebook.

    Resolution order (first set wins): explicit override (CLI flag) ->
    ``NB_MCP_MEMORY_NOTEBOOK`` env -> ``config.mcp.memory_notebook`` -> "memory".
    """
    if override:
        return override
    env = os.environ.get("NB_MCP_MEMORY_NOTEBOOK")
    if env:
        return env
    return config.mcp.memory_notebook or DEFAULT_MEMORY_NOTEBOOK


def resolve_profile(config: Config, override: str | None = None) -> str:
    """Resolve the tool profile (override -> NB_MCP_PROFILE -> config)."""
    if override:
        return override
    return os.environ.get("NB_MCP_PROFILE") or config.mcp.profile or "memory"


def resolve_client() -> str:
    """Identify the connecting client for provenance (env, else 'unknown')."""
    return os.environ.get("NB_MCP_CLIENT") or "unknown"


def ensure_memory_notebook(name: str) -> None:
    """Ensure the memory notebook exists and is date-based, creating if absent."""
    from nb.config import add_notebook, get_config

    config = get_config()
    if config.get_notebook(name) is None:
        add_notebook(name, date_based=True)
        _eprint(f"[nb-mcp] Created memory notebook '{name}' (date-based).")


def build_context(
    memory_notebook: str | None = None,
    profile: str | None = None,
) -> MemoryContext:
    """Build the shared MemoryContext from config + resolution rules."""
    from nb.config import get_config

    config = get_config()
    nb_name = resolve_memory_notebook(config, memory_notebook)
    ensure_memory_notebook(nb_name)
    # Reload so the context sees the freshly-registered notebook.
    config = get_config()

    return MemoryContext(
        config=config,
        memory_notebook=nb_name,
        readable_notebooks=list(config.mcp.readable_notebooks),
        recency_boost=config.mcp.recall_recency_boost,
        default_limit=config.mcp.recall_default_limit,
        log_writes=config.mcp.log_writes,
        client=resolve_client(),
    )


def create_server(
    memory_notebook: str | None = None,
    profile: str | None = None,
) -> tuple[FastMCP, MemoryContext]:
    """Create and configure the FastMCP server instance.

    Imports ``fastmcp`` lazily so the rest of nb works without the optional
    ``[mcp]`` extra installed.
    """
    try:
        from fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover - exercised via run_server
        raise _missing_mcp_error() from e

    from nb.config import get_config

    config = get_config()
    resolved_profile = resolve_profile(config, profile)
    if resolved_profile == "full":
        _eprint(
            "[nb-mcp] Profile 'full' (power tier) is not available yet; "
            "serving the memory tier only."
        )

    ctx = build_context(memory_notebook=memory_notebook, profile=profile)

    mcp = FastMCP(
        name="nb-memory",
        instructions=(
            "Personal notes/memory for the user, backed by local markdown files. "
            "Use `recall` to look up what the user has told you before, and "
            "`remember` to store durable facts and preferences."
        ),
    )
    register_memory_tools(mcp, ctx)
    return mcp, ctx


def run_server(
    memory_notebook: str | None = None,
    profile: str | None = None,
) -> None:
    """Build the server and serve over stdio (blocking)."""
    try:
        mcp, ctx = create_server(memory_notebook=memory_notebook, profile=profile)
    except RuntimeError as e:
        _eprint(str(e))
        raise SystemExit(1) from e

    _eprint(
        f"[nb-mcp] Serving memory notebook '{ctx.memory_notebook}' "
        f"from {ctx.notes_root} (stdio)."
    )
    mcp.run(transport="stdio")


def _missing_mcp_error() -> RuntimeError:
    return RuntimeError(
        "MCP support is not installed. Install it with:\n"
        "    uv sync --extra mcp\n"
        "or:\n"
        "    pip install 'nb-cli[mcp]'"
    )


def main(argv: list[str] | None = None) -> None:
    """Console-script entry point (``nb-mcp``)."""
    parser = argparse.ArgumentParser(
        prog="nb-mcp",
        description="Serve nb notes as MCP memory over stdio.",
    )
    parser.add_argument(
        "--memory-notebook",
        dest="memory_notebook",
        default=None,
        help="Notebook that remember() writes to (overrides config/env).",
    )
    parser.add_argument(
        "--profile",
        dest="profile",
        choices=["memory", "full"],
        default=None,
        help="Tool profile (default: memory).",
    )
    args = parser.parse_args(argv)
    run_server(memory_notebook=args.memory_notebook, profile=args.profile)


if __name__ == "__main__":  # pragma: no cover
    main()
