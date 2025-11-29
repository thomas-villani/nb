"""CLI package for nb."""

from __future__ import annotations

import click

from nb import __version__
from nb.cli.attachments import register_attachment_commands
from nb.cli.completion import handle_powershell_completion, register_completion_commands
from nb.cli.config_cmd import register_config_commands
from nb.cli.links import register_link_commands
from nb.cli.notebooks import register_notebook_commands
from nb.cli.notes import register_note_commands, today
from nb.cli.search import register_search_commands
from nb.cli.todos import register_todo_commands
from nb.cli.utils import ensure_setup


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="nb")
@click.option(
    "-s", "--show", is_flag=True, help="Print note to console instead of opening editor"
)
@click.option("--notebook", "-n", help="Notebook for default today action")
@click.pass_context
def cli(ctx: click.Context, show: bool, notebook: str | None) -> None:
    """A plaintext-first note-taking and todo management CLI.

    Run 'nb' without arguments to open today's daily note.
    Use -s to print the note to console instead.
    Use -n to specify a notebook for the default action.
    """
    ensure_setup()
    ctx.ensure_object(dict)
    ctx.obj["show"] = show
    if ctx.invoked_subcommand is None:
        # Default action: open today's note
        ctx.invoke(today, notebook=notebook)


# Register all command groups
register_note_commands(cli)
register_notebook_commands(cli)
register_config_commands(cli)
register_todo_commands(cli)
register_search_commands(cli)
register_link_commands(cli)
register_attachment_commands(cli)
register_completion_commands(cli)


def main() -> None:
    """Entry point for the CLI."""
    if not handle_powershell_completion(cli):
        cli()


__all__ = ["cli", "main"]
