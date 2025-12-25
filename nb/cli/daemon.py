"""CLI commands for managing the background indexing daemon."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

import click
from rich.console import Console
from rich.table import Table

from nb.config import get_config

console = Console()


def auto_index_if_needed(index_vectors: bool = False) -> bool:
    """Index notes if daemon is not running.

    This helper function can be used by other commands to skip indexing
    when the daemon is handling it. Falls back to normal indexing otherwise.

    Args:
        index_vectors: Whether to also update vector search index.

    Returns:
        True if indexing was performed, False if daemon is handling it.
    """
    from nb.daemon import is_daemon_running
    from nb.index.scanner import index_all_notes

    config = get_config()
    running, _ = is_daemon_running(config.nb_dir)

    if running:
        return False  # Daemon is handling indexing

    # Fall back to normal indexing
    index_all_notes(index_vectors=index_vectors)
    return True


def register_daemon_commands(cli: click.Group) -> None:
    """Register daemon management commands."""

    @cli.group()
    def daemon():
        """Manage background indexing daemon.

        The daemon watches for file changes and keeps the index updated
        automatically, making CLI commands near-instant.

        The daemon is completely optional - nb works perfectly without it.
        When the daemon is not running, commands index on-demand as usual.
        """
        pass

    @daemon.command("start")
    @click.option(
        "-f", "--foreground", is_flag=True, help="Run in foreground (for debugging)"
    )
    def daemon_start(foreground: bool) -> None:
        """Start the background indexing daemon."""
        try:
            from nb.daemon import is_daemon_running, run_daemon
        except ImportError as e:
            console.print(f"[red]Failed to import daemon module: {e}[/red]")
            console.print(
                "[dim]Make sure watchdog is installed: uv pip install watchdog[/dim]"
            )
            raise SystemExit(1) from None

        config = get_config()
        running, _ = is_daemon_running(config.nb_dir)

        if running:
            console.print("[yellow]Daemon is already running[/yellow]")
            return

        if foreground:
            console.print(
                "[dim]Starting daemon in foreground (Ctrl+C to stop)...[/dim]"
            )
            try:
                run_daemon(config.notes_root, config.nb_dir, foreground=True)
            except KeyboardInterrupt:
                console.print("\n[dim]Daemon stopped[/dim]")
        else:
            # Daemonize - run in background
            if sys.platform == "win32":
                # Windows: Use pythonw or subprocess with CREATE_NO_WINDOW
                # Try pythonw first (truly windowless), fall back to python with creation flags
                python_exe = sys.executable
                pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")

                # Use the daemon module as the entry point
                args = [
                    "-m",
                    "nb.daemon",
                    str(config.notes_root),
                    str(config.nb_dir),
                ]

                try:
                    # Try pythonw first
                    from pathlib import Path

                    if Path(pythonw_exe).exists():
                        subprocess.Popen(
                            [pythonw_exe] + args,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.DETACHED_PROCESS
                            | subprocess.CREATE_NO_WINDOW,
                        )
                    else:
                        # Fall back to python with CREATE_NO_WINDOW
                        subprocess.Popen(
                            [python_exe] + args,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.DETACHED_PROCESS
                            | subprocess.CREATE_NO_WINDOW,
                        )
                except OSError as e:
                    console.print(f"[red]Failed to start daemon: {e}[/red]")
                    raise SystemExit(1) from None
            else:
                # Unix: Double fork to fully daemonize
                pid = os.fork()
                if pid > 0:
                    # Parent process - wait a moment and check if started
                    time.sleep(0.5)
                    running, _ = is_daemon_running(config.nb_dir)
                    if running:
                        console.print("[green]Daemon started[/green]")
                    else:
                        console.print(
                            "[red]Daemon failed to start. Check daemon.log[/red]"
                        )
                    return

                # Child process
                os.setsid()
                pid = os.fork()
                if pid > 0:
                    sys.exit(0)

                # Grandchild runs daemon
                os.chdir("/")
                run_daemon(config.notes_root, config.nb_dir, foreground=False)
                sys.exit(0)

            # Wait a moment and verify it started (Windows path continues here)
            time.sleep(1)
            running, _ = is_daemon_running(config.nb_dir)
            if running:
                console.print("[green]Daemon started[/green]")
            else:
                console.print(
                    "[red]Daemon may have failed to start. Check daemon.log[/red]"
                )
                log_file = config.nb_dir / "daemon.log"
                if log_file.exists():
                    console.print(f"[dim]Log file: {log_file}[/dim]")

    @daemon.command("stop")
    def daemon_stop() -> None:
        """Stop the background indexing daemon."""
        from nb.daemon import stop_daemon

        config = get_config()
        if stop_daemon(config.nb_dir):
            console.print("[green]Daemon stopped[/green]")
        else:
            console.print("[dim]Daemon is not running[/dim]")

    @daemon.command("status")
    def daemon_status() -> None:
        """Check daemon status and statistics."""
        from nb.daemon import is_daemon_running

        config = get_config()
        running, state = is_daemon_running(config.nb_dir)

        if running:
            console.print("[green]● Daemon is running[/green]")
            if state:
                start = datetime.fromtimestamp(state["start_time"])
                uptime = datetime.now() - start
                uptime_str = _format_timedelta(uptime)

                table = Table(show_header=False, box=None, padding=(0, 2))
                table.add_column("Key", style="dim")
                table.add_column("Value")

                table.add_row("PID", str(state["pid"]))
                table.add_row("Uptime", uptime_str)
                table.add_row("Files indexed", str(state.get("files_indexed", 0)))
                table.add_row("Files removed", str(state.get("files_removed", 0)))
                table.add_row("Errors", str(state.get("errors", 0)))

                if state.get("last_activity"):
                    last_activity = datetime.fromtimestamp(state["last_activity"])
                    ago = datetime.now() - last_activity
                    table.add_row("Last activity", f"{_format_timedelta(ago)} ago")

                console.print(table)
        else:
            console.print("[dim]○ Daemon is not running[/dim]")
            console.print()
            console.print("[dim]Start with: nb daemon start[/dim]")

    @daemon.command("restart")
    @click.pass_context
    def daemon_restart(ctx: click.Context) -> None:
        """Restart the daemon."""
        from nb.daemon import is_daemon_running

        config = get_config()
        running, _ = is_daemon_running(config.nb_dir)

        if running:
            ctx.invoke(daemon_stop)
            time.sleep(1)

        ctx.invoke(daemon_start)

    @daemon.command("log")
    @click.option("-n", "--lines", default=50, help="Number of lines to show")
    @click.option(
        "-f", "--follow", is_flag=True, help="Follow log output (like tail -f)"
    )
    def daemon_log(lines: int, follow: bool) -> None:
        """View daemon log output."""
        from nb.daemon import get_daemon_log

        config = get_config()
        log_file = config.nb_dir / "daemon.log"

        if not log_file.exists():
            console.print("[dim]No log file found. Daemon may not have run yet.[/dim]")
            return

        if follow:
            # Follow mode - continuously print new lines
            console.print(f"[dim]Following {log_file} (Ctrl+C to stop)...[/dim]")
            try:
                import time

                last_size = 0
                while True:
                    current_size = log_file.stat().st_size
                    if current_size > last_size:
                        with log_file.open(encoding="utf-8") as f:
                            f.seek(last_size)
                            new_content = f.read()
                            if new_content:
                                console.print(new_content, end="")
                        last_size = current_size
                    time.sleep(0.5)
            except KeyboardInterrupt:
                console.print("\n[dim]Stopped following log[/dim]")
        else:
            # Show last N lines
            log_lines = get_daemon_log(config.nb_dir, lines)
            if log_lines:
                for line in log_lines:
                    console.print(line)
            else:
                console.print("[dim]Log file is empty[/dim]")


def _format_timedelta(td: timedelta) -> str:
    """Format a timedelta for human-readable display."""
    total_seconds = int(td.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        return f"{days}d {hours}h"
