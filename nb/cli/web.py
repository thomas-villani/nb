"""Web viewer commands for nb."""

from __future__ import annotations

import click
from nb.cli.utils import console


@click.command("web")
@click.option("--port", "-p", default=3000, help="Port to serve on")
@click.option("--no-open", is_flag=True, help="Don't open browser automatically")
@click.option("-c", "--completed", is_flag=True, help="Show completed todos")
def web_cmd(port: int, no_open: bool, completed: bool) -> None:
    """Launch web viewer in browser.

    Starts a local web server and opens your notes in the browser.
    Press Ctrl+C to stop.
    """
    from nb.web import run_server

    console.print(f"[dim]Starting web server at http://localhost:{port}[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    run_server(port=port, open_browser=not no_open, show_completed=completed)


def register_web_commands(cli: click.Group) -> None:
    """Register web commands with the CLI."""
    cli.add_command(web_cmd)
