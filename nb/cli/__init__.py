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
from nb.cli.clip import register_clip_commands
from nb.cli.completion import (
    complete_notebook,
    handle_powershell_completion,
    register_completion_commands,
)
from nb.cli.config_cmd import register_config_commands
from nb.cli.graph import register_graph_commands
from nb.cli.inbox import register_inbox_commands
from nb.cli.links import register_link_commands
from nb.cli.note_links import register_note_link_commands
from nb.cli.notebooks import register_notebook_commands
from nb.cli.notes import register_note_commands, today
from nb.cli.record import register_record_commands
from nb.cli.related import register_related_commands
from nb.cli.search import register_search_commands
from nb.cli.stats import register_stats_commands
from nb.cli.tags import register_tags_commands
from nb.cli.templates import register_template_commands
from nb.cli.todos import register_todo_commands
from nb.cli.transcribe import register_transcribe_commands
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
        "ls": "list",
        "nbs": "notebooks",
        "td": "todo",
        "rec": "record",
        "c": "clip",
    }

    # Special aliases that need argument injection
    SPECIAL_ALIASES: ClassVar[dict[str, tuple[str, list[str]]]] = {
        "ss": ("search", ["--semantic"]),  # ss -> search --semantic
        "ta": ("todo", ["add"]),  # ta -> todo add
        "td": ("todo", ["done"]),  # td -> todo done
        "now": ("todo", ["--today"]),  # now -> todo --today
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


_nb_art = """
[blue]
               █████
              ░░███
    ████████   ░███████
   ░░███░░███  ░███░░███
    ░███ ░███  ░███ ░███
    ░███ ░███  ░███ ░███
    ████ █████ ████████
   ░░░░ ░░░░░ ░░░░░░░░
[/blue]
[bright_green]Copyright (c) 2025, Tom Villani, Ph.D.[/bright_green]

[dim][cyan]nb[/cyan] was created because I prefer command line applications
over web apps. This tool allows you to collect todo
items from notes scattered across many notebooks or repos.

Long live the CLI![/dim]"""


def _print_about(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print(
        Panel(
            _nb_art,
            title="About",
            title_align="left",
            expand=False,
            border_style="bold blue",
        )
    )
    ctx.exit()


@click.group(cls=AliasedGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="nb")
@click.option(
    "--about",
    "-A",
    is_flag=True,
    callback=_print_about,
    expose_value=False,
    is_eager=True,
)
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
@click.pass_context
def help_cmd(ctx):
    """Open documentation in web browser."""
    import webbrowser

    from rich.console import Console

    console = Console()

    # Look for docs in package (installed) then dev location
    package_docs = Path(__file__).parent.parent / "_docs" / "index.html"
    dev_docs = (
        Path(__file__).parent.parent.parent / "docs" / "build" / "html" / "index.html"
    )

    if package_docs.exists():
        docs_path = package_docs
    elif dev_docs.exists():
        docs_path = dev_docs
    else:
        console.print("[red]Documentation not found.[/red]")
        console.print("[dim]Build docs with: cd docs && make html[/dim]")
        raise SystemExit(1)

    # Open in browser
    url = docs_path.as_uri()
    console.print("[green]Opening documentation...[/green]")
    webbrowser.open(url)


# Register all command groups
register_note_commands(cli)
register_notebook_commands(cli)
register_config_commands(cli)
register_todo_commands(cli)
register_search_commands(cli)
register_link_commands(cli)
register_note_link_commands(cli)
register_graph_commands(cli)
register_related_commands(cli)
register_attachment_commands(cli)
register_template_commands(cli)
register_completion_commands(cli)
register_stats_commands(cli)
register_tags_commands(cli)
register_web_commands(cli)
register_record_commands(cli)
register_transcribe_commands(cli)
register_clip_commands(cli)
register_inbox_commands(cli)


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
