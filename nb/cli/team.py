"""Team identity CLI commands for shared/multiplayer notebooks."""

from __future__ import annotations

import click

from nb.cli.utils import console
from nb.config import get_config, save_config


def register_team_commands(cli: click.Group) -> None:
    """Register team commands with CLI."""
    cli.add_command(team_cmd)


@click.group("team")
def team_cmd() -> None:
    """Manage your identity for shared (multiplayer) notebooks.

    Your identity attributes todos via @owner(handle) and powers
    'nb todo --mine'. It is stored per-machine and never shared.
    """
    pass


@team_cmd.command("whoami")
def team_whoami() -> None:
    """Show your resolved identity (and where it came from)."""
    from nb.core.team import get_identity

    identity = get_identity()

    if identity.source == "none":
        console.print("[yellow]No identity configured.[/yellow]")
        console.print("Set one with: [cyan]nb team set --handle <you>[/cyan]")
        console.print("[dim]Or configure git: git config user.name / user.email[/dim]")
        return

    console.print(f"[cyan]Name:[/cyan]   {identity.name or '[dim]—[/dim]'}")
    console.print(f"[cyan]Handle:[/cyan] {identity.handle or '[dim]—[/dim]'}")
    console.print(f"[cyan]Email:[/cyan]  {identity.email or '[dim]—[/dim]'}")
    console.print(f"[dim]Source: {identity.source}[/dim]")


@team_cmd.command("set")
@click.option("--name", help='Your display name (e.g. "Thomas Villani")')
@click.option("--handle", help="Short handle used in @owner() (e.g. thomas)")
@click.option("--email", help="Your email, for attribution")
def team_set(name: str | None, handle: str | None, email: str | None) -> None:
    """Set your identity fields.

    \b
    Examples:
        nb team set --name "Thomas Villani" --handle thomas
        nb team set --handle thomas
    """
    if not (name or handle or email):
        console.print(
            "[red]Error:[/red] provide at least one of --name/--handle/--email"
        )
        raise SystemExit(1)

    config = get_config()
    if name is not None:
        config.team.name = name
    if handle is not None:
        config.team.handle = handle
    if email is not None:
        config.team.email = email
    save_config(config)

    console.print("[green]Identity updated.[/green]")
    from nb.core.team import get_identity

    identity = get_identity()
    console.print(
        f"[dim]name={identity.name or '—'} handle={identity.handle or '—'} "
        f"email={identity.email or '—'}[/dim]"
    )
