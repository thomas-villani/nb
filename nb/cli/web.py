"""Web viewer commands for nb."""

from __future__ import annotations

import click

from nb.cli.utils import console


@click.command("web")
@click.option("--port", "-p", default=3000, help="Port to serve on")
@click.option("--no-open", is_flag=True, help="Don't open browser automatically")
@click.option("-c", "--completed", is_flag=True, help="Show completed todos")
@click.option(
    "-n",
    "--notebook",
    "notebook",
    default=None,
    help="Scope the viewer to a single notebook",
)
@click.option(
    "--dev",
    is_flag=True,
    help="Dev mode: reload CSS/JS/HTML from disk on each request (no restart needed)",
)
def web_cmd(
    port: int, no_open: bool, completed: bool, notebook: str | None, dev: bool
) -> None:
    """Launch web viewer in browser.

    Starts a local web server and opens your notes in the browser.
    Press Ctrl+C to stop.

    Use -n/--notebook to scope the viewer to a single notebook.
    """
    from nb.web import set_dev_mode
    from nb.webserver import run_server

    if notebook:
        from nb.config import get_config
        from nb.core.links import list_linked_notes
        from nb.core.notebooks import list_notebooks

        config = get_config()
        valid = set(list_notebooks(config.notes_root))
        valid |= {ln.notebook for ln in list_linked_notes()}
        if notebook not in valid:
            console.print(f"[red]Notebook '{notebook}' not found.[/red]")
            if valid:
                console.print(f"[dim]Available: {', '.join(sorted(valid))}[/dim]")
            raise SystemExit(1)

    if dev:
        set_dev_mode(True)
        console.print(
            "[yellow]Dev mode: templates reload from disk on each request[/yellow]"
        )

    console.print(f"[dim]Starting web server at http://localhost:{port}[/dim]")
    if notebook:
        console.print(f"[dim]Scoped to notebook: {notebook}[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    run_server(
        port=port,
        open_browser=not no_open,
        show_completed=completed,
        notebook=notebook,
    )


def register_web_commands(cli: click.Group) -> None:
    """Register web commands with the CLI."""
    cli.add_command(web_cmd)
