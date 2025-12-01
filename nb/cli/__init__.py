"""CLI package for nb."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

# Ensure stdout handles Unicode when piped (e.g., `nb show today | more`)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import click

from nb import __version__
from nb.cli.attachments import register_attachment_commands
from nb.cli.completion import complete_notebook, handle_powershell_completion, register_completion_commands
from nb.cli.config_cmd import register_config_commands
from nb.cli.links import register_link_commands
from nb.cli.notebooks import register_notebook_commands
from nb.cli.notes import register_note_commands, today
from nb.cli.search import register_search_commands
from nb.cli.stats import register_stats_commands
from nb.cli.tags import register_tags_commands
from nb.cli.templates import register_template_commands
from nb.cli.todos import register_todo_commands
from nb.cli.utils import ensure_setup
from nb.cli.web import register_web_commands


class AliasedGroup(click.Group):
    """Click group that supports command aliases with proper flag passthrough."""

    ALIASES: ClassVar[dict[str, str]] = {
        "t": "today",
        "y": "yesterday",
        "l": "last",
        "o": "open",
        "s": "search",
        "nbs": "notebooks",
        "td": "todo",
    }

    # Special aliases that need argument injection
    SPECIAL_ALIASES: ClassVar[dict[str, tuple[str, list[str]]]] = {
        "ss": ("search", ["--semantic"]),  # ss -> search --semantic
        "ta": ("todo", ["add"]),  # ta -> todo add
    }

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # Try original command first
        rv = super().get_command(ctx, cmd_name)
        if rv is not None:
            return rv

        # Check simple aliases
        if cmd_name in self.ALIASES:
            return super().get_command(ctx, self.ALIASES[cmd_name])

        # Check special aliases (they'll be handled in resolve_command)
        if cmd_name in self.SPECIAL_ALIASES:
            target_cmd = self.SPECIAL_ALIASES[cmd_name][0]
            return super().get_command(ctx, target_cmd)

        return None

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        # Handle special aliases that inject arguments
        if args:
            cmd_name = args[0]
            if cmd_name in self.SPECIAL_ALIASES:
                target_cmd, inject_args = self.SPECIAL_ALIASES[cmd_name]
                # Replace alias with target command and inject args
                args = [target_cmd] + inject_args + args[1:]

        return super().resolve_command(ctx, args)


@click.group(cls=AliasedGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="nb")
@click.option(
    "-s", "--show", is_flag=True, help="Print note to console instead of opening editor"
)
@click.option(
    "--notebook",
    "-n",
    help="Notebook for default today action",
    shell_complete=complete_notebook,
)
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


@cli.command("help")
@click.option("--plain", "-p", is_flag=True, help="Print in plaintext")
@click.pass_context
def help_cmd(ctx, plain: bool):
    """Displays readme.md in rich formatting to stdout"""
    from rich.console import Console
    from rich.markdown import Markdown

    console = Console()
    readme_file = Path(__file__).parent.parent.parent / "readme.md2"
    if readme_file.exists():
        content = readme_file.read_text(encoding="utf-8")
        if not plain:
            content = Markdown(content)
    else:
        content = "Error! readme.md file not found."
        if not plain:
            content = f"[bright_red]{content}[/bright_red]"

    if plain:
        print(content)
    else:
        console.print(content)
    return


# Register all command groups
register_note_commands(cli)
register_notebook_commands(cli)
register_config_commands(cli)
register_todo_commands(cli)
register_search_commands(cli)
register_link_commands(cli)
register_attachment_commands(cli)
register_template_commands(cli)
register_completion_commands(cli)
register_stats_commands(cli)
register_tags_commands(cli)
register_web_commands(cli)


def main() -> None:
    """Entry point for the CLI."""
    if not handle_powershell_completion(cli):
        cli()


def main_todo() -> None:
    """Entry point for nbt (nb todo alias).

    Injects 'todo' as the first argument so all nb todo flags work.
    """
    sys.argv = [sys.argv[0], "todo"] + sys.argv[1:]
    main()


__all__ = ["cli", "main", "main_todo"]
