"""CLI commands for the MCP memory server (`nb serve --mcp`, `nb mcp ...`).

Exposes an nb notes store as portable, cross-tool memory over the Model Context
Protocol. See etc/mcp-memory-spec.md.
"""

from __future__ import annotations

import json
import time

import click
from rich.console import Console

from nb.config import get_config

console = Console()


def register_mcp_commands(cli: click.Group) -> None:
    """Register the `serve` command and the `mcp` inspection group."""

    # ----------------------------------------------------------------- serve #
    @cli.command()
    @click.option(
        "--mcp",
        "mcp_flag",
        is_flag=True,
        help="Serve the MCP memory server over stdio.",
    )
    @click.option(
        "--memory-notebook",
        "memory_notebook",
        default=None,
        help="Notebook that remember() writes to (overrides config/env).",
    )
    @click.option(
        "--profile",
        type=click.Choice(["memory", "full"]),
        default=None,
        help="Tool profile (default: memory).",
    )
    @click.pass_context
    def serve(
        ctx: click.Context,
        mcp_flag: bool,
        memory_notebook: str | None,
        profile: str | None,
    ) -> None:
        """Run nb as a server for other tools.

        \b
        Currently exposes the MCP memory server over stdio so MCP clients
        (Claude Desktop, Claude Code, Cursor, ...) can recall from and remember
        into your notes:

        \b
            nb serve --mcp
            nb serve --mcp --memory-notebook brain
        """
        if not mcp_flag:
            click.echo(ctx.get_help())
            ctx.exit(0)
        _run_server(memory_notebook, profile)

    # ----------------------------------------------------------------- mcp grp #
    @cli.group()
    def mcp() -> None:
        """Inspect and configure the MCP memory server.

        Run the server itself with `nb serve --mcp`. These subcommands are for
        the human: review the write log and emit client config.
        """
        pass

    @mcp.command("log")
    @click.option("-n", "--lines", default=20, help="Number of recent lines to show.")
    @click.option(
        "-f", "--follow", is_flag=True, help="Follow the log (Ctrl-C to stop)."
    )
    def mcp_log(lines: int, follow: bool) -> None:
        """Show the MCP write audit log (.nb/mcp.log)."""
        from nb.mcp import audit

        config = get_config()
        log_path = audit.get_log_path(config.notes_root)

        for line in audit.read_log(config.notes_root, limit=lines):
            console.print(line)

        if not follow:
            if not log_path.exists():
                console.print("[dim]No MCP writes logged yet.[/dim]")
            return

        # Follow mode: poll for appended lines.
        console.print("[dim]Following… press Ctrl-C to stop.[/dim]")
        try:
            last_size = log_path.stat().st_size if log_path.exists() else 0
            while True:
                time.sleep(0.5)
                if not log_path.exists():
                    continue
                size = log_path.stat().st_size
                if size > last_size:
                    with log_path.open("r", encoding="utf-8") as f:
                        f.seek(last_size)
                        for line in f.read().splitlines():
                            console.print(line)
                    last_size = size
        except KeyboardInterrupt:
            pass

    @mcp.command("print-config")
    @click.option(
        "--name", "server_name", default="nb-memory", help="MCP server entry name."
    )
    @click.option(
        "--memory-notebook",
        "memory_notebook",
        default=None,
        help="Memory notebook to bake into the config (default: resolved config).",
    )
    @click.option(
        "--client",
        "client",
        default=None,
        help="Client label recorded in memory provenance (e.g. claude-desktop).",
    )
    def mcp_print_config(
        server_name: str, memory_notebook: str | None, client: str | None
    ) -> None:
        """Emit a ready-to-paste MCP client config block."""
        from nb.mcp.server import resolve_memory_notebook

        config = get_config()
        nb_name = resolve_memory_notebook(config, memory_notebook)

        env: dict[str, str] = {"NB_MCP_MEMORY_NOTEBOOK": nb_name}
        if client:
            env["NB_MCP_CLIENT"] = client

        block = {
            "mcpServers": {
                server_name: {
                    "command": "nb-mcp",
                    "args": ["--profile", "memory"],
                    "env": env,
                }
            }
        }
        # Plain echo (not Rich) so the JSON is copy-paste clean.
        click.echo(json.dumps(block, indent=2))


def _run_server(memory_notebook: str | None, profile: str | None) -> None:
    """Shared launcher used by `nb serve --mcp`."""
    try:
        from nb.mcp.server import run_server
    except ImportError as e:  # pragma: no cover
        console.print(f"[red]Failed to import MCP server: {e}[/red]")
        console.print("[dim]Install MCP support: uv sync --extra mcp[/dim]")
        raise SystemExit(1) from None

    run_server(memory_notebook=memory_notebook, profile=profile)
