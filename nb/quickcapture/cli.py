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


def _check_gui_deps() -> None:
    """Fail loudly when the popup can't be shown; warn when the tray can't.

    tkinter is part of the standard library but is omitted from some minimal
    or uv-managed Python builds, in which case the popup silently can't open.
    """
    import importlib.util

    try:
        import tkinter  # noqa: F401
    except Exception as exc:  # ImportError, or missing _tkinter C extension
        console.print(
            f"[red]Quick-capture needs tkinter, which isn't available:[/red] {exc}"
        )
        console.print(
            "[dim]tkinter ships with the standard python.org installers but is "
            "omitted from some minimal/uv-managed Python builds. Install a Python "
            "with Tk support and reinstall nb there.[/dim]"
        )
        raise SystemExit(1) from None

    if importlib.util.find_spec("pystray") is None:
        console.print(
            "[yellow]Tray icon unavailable[/yellow] (pystray not installed); the "
            "hotkey still works."
        )
        console.print("[dim]For the tray icon: uv sync --extra quickcapture[/dim]")


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
        _check_gui_deps()

        from nb.quickcapture.app import QuickCaptureApp

        app = QuickCaptureApp(hotkey=hotkey)

        def _ready() -> None:
            tray = (
                "tray icon active"
                if app.tray_enabled
                else "no tray (pystray not installed)"
            )
            console.print(
                f"[green]Quick-capture ready[/green] — press [bold]{hotkey}[/bold] "
                f"to capture. [dim]({tray}; Ctrl-C to quit)[/dim]"
            )
            if not app.tray_enabled:
                console.print(
                    "[dim]If nothing appears when you press the hotkey, another app may own "
                    "it — retry with e.g. [bold]nb quickcapture --hotkey ctrl+shift+space[/bold].[/dim]"
                )

        console.print(f"[dim]Registering {hotkey}…[/dim]")
        if not app.run(on_ready=_ready):
            console.print(
                f"[red]Could not register hotkey '{hotkey}':[/red] {app.startup_error}"
            )
            console.print(
                "[dim]It is likely already in use — by another application, or because "
                "quick-capture is already running. Try a different combo, e.g. "
                "[bold]nb quickcapture --hotkey ctrl+shift+space[/bold].[/dim]"
            )
            raise SystemExit(1)

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
