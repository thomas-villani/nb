"""CLI commands for the quick-capture tray app (`nb quickcapture`)."""

from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


def _require_windows() -> None:
    if sys.platform != "win32":
        console.print("[red]nb quickcapture currently supports Windows only.[/red]")
        raise SystemExit(1)


def _validate_hotkey(hotkey: str) -> None:
    from nb.quickcapture.hotkey import parse_hotkey

    try:
        parse_hotkey(hotkey)
    except ValueError as exc:
        console.print(f"[red]Invalid --hotkey:[/red] {exc}")
        raise SystemExit(1) from None


def register_quickcapture_commands(cli: click.Group) -> None:
    """Register the `quickcapture` command group on the root CLI group."""

    @cli.group("quickcapture", invoke_without_command=True)
    @click.option(
        "--hotkey",
        default="ctrl+alt+n",
        show_default=True,
        help="Global hotkey that opens the capture popup (e.g. 'ctrl+shift+space').",
    )
    @click.pass_context
    def quickcapture(ctx: click.Context, hotkey: str) -> None:
        """Global quick-capture tray app (Windows).

        With no subcommand, runs the tray app: a system-wide hotkey opens a
        tiny popup to append a todo (or plain line) to a chosen note — by
        default today's daily note — without opening a terminal.

        \b
        Examples:
          nb quickcapture                              # run now
          nb quickcapture --hotkey ctrl+shift+space    # run with a custom hotkey
          nb quickcapture install                      # run automatically at login
          nb quickcapture status                       # show autostart state
          nb quickcapture uninstall                    # stop running at login
        """
        if ctx.invoked_subcommand is not None:
            return

        _require_windows()
        _validate_hotkey(hotkey)

        from nb.quickcapture.app import QuickCaptureApp

        console.print(
            f"[green]nb quick-capture running[/green] — press "
            f"[bold]{hotkey}[/bold] to capture."
        )
        console.print("[dim]Quit via the tray icon, or Ctrl-C here.[/dim]")
        QuickCaptureApp(hotkey=hotkey).run()

    @quickcapture.command("install")
    @click.option(
        "--hotkey",
        default="ctrl+alt+n",
        show_default=True,
        help="Hotkey to launch with at login.",
    )
    def install(hotkey: str) -> None:
        """Run quick-capture automatically at login (per-user, no admin)."""
        _require_windows()
        _validate_hotkey(hotkey)

        from nb.quickcapture import autostart

        command = autostart.enable(hotkey)
        console.print(
            "[green]Autostart enabled.[/green] Quick-capture will start at login."
        )
        console.print(f"[dim]{command}[/dim]")
        console.print(
            "[dim]Start it now without logging out: run [bold]nb quickcapture[/bold].[/dim]"
        )

    @quickcapture.command("uninstall")
    def uninstall() -> None:
        """Stop quick-capture from running at login."""
        _require_windows()

        from nb.quickcapture import autostart

        if autostart.disable():
            console.print("[green]Autostart disabled.[/green]")
        else:
            console.print("[yellow]Autostart was not enabled.[/yellow]")

    @quickcapture.command("status")
    def status() -> None:
        """Show whether quick-capture is set to run at login."""
        _require_windows()

        from nb.quickcapture import autostart

        command = autostart.current()
        if command:
            console.print("[green]Autostart is enabled.[/green]")
            console.print(f"[dim]{command}[/dim]")
        else:
            console.print("[yellow]Autostart is not enabled.[/yellow]")
            console.print(
                "[dim]Enable it with [bold]nb quickcapture install[/bold].[/dim]"
            )
