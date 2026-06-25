"""Shared (multiplayer) notebook CLI commands."""

from __future__ import annotations

import click

from nb.cli.utils import console


def register_share_commands(cli: click.Group) -> None:
    """Register share commands with CLI."""
    cli.add_command(share_cmd)


@click.group("share")
def share_cmd() -> None:
    """Manage shared (multiplayer) notebooks synced over git.

    A shared notebook is an external notebook backed by its own git repository.
    Only shared notebooks are synced — your private notes never leave your machine.
    Use @owner(handle) on todos and 'nb todo --mine' to track who owns what.
    """
    pass


@share_cmd.command("add")
@click.argument("source")
@click.argument("name")
@click.option(
    "--subdir",
    help="Content dir within the repo (e.g. docs or .nbnotes)",
)
@click.option(
    "--date-based",
    "-d",
    default=False,
    help="Date mode: false, daily, or weekly",
)
def share_add(
    source: str, name: str, subdir: str | None, date_based: str | bool
) -> None:
    """Register a shared notebook from a git URL or existing local repo.

    \b
    Examples:
        nb share add git@github.com:team/projectx.git projectx
        nb share add ~/repos/somecode projnotes --subdir .nbnotes
        nb share add ~/repos/somecode projnotes --subdir docs
    """
    from nb.core.git import GitError
    from nb.core.share import add_shared

    try:
        nb = add_shared(source, name, subdir=subdir, date_based=date_based)
    except GitError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None

    console.print(f"[green]Added shared notebook:[/green] {name}")
    console.print(f"[dim]Path: {nb.path}[/dim]")
    console.print("[dim]Sync it with: nb share sync[/dim]")


@share_cmd.command("init")
@click.argument("name")
@click.option("--remote", "-r", help="Remote URL to add as origin and push to")
def share_init(name: str, remote: str | None) -> None:
    """Promote an existing internal notebook into a shared git-backed notebook.

    Moves the notebook out to its own git repo, optionally adds a remote and pushes.

    \b
    Examples:
        nb share init projectx
        nb share init projectx --remote git@github.com:team/projectx.git
    """
    from nb.core.git import GitError
    from nb.core.share import init_shared

    try:
        nb = init_shared(name, remote=remote)
    except GitError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None

    console.print(f"[green]Initialized shared notebook:[/green] {name}")
    console.print(f"[dim]Repo: {nb.path}[/dim]")
    if not remote:
        console.print(
            "[dim]Add a remote later with: "
            "nb share init won't re-run — use git in the repo, "
            "or set it up before teammates clone.[/dim]"
        )


@share_cmd.command("list")
def share_list() -> None:
    """List shared notebooks with their sync status."""
    from nb.core.share import shared_notebooks, status_shared

    notebooks = shared_notebooks()
    if not notebooks:
        console.print("[dim]No shared notebooks. Add one with 'nb share add'.[/dim]")
        return

    statuses = {s.notebook: s for s in status_shared()}

    for nb in notebooks:
        st = statuses.get(nb.name)
        console.print(f"[cyan]{nb.name}[/cyan]")
        console.print(f"  [dim]path:[/dim] {nb.path}")
        if nb.subdir:
            console.print(f"  [dim]subdir:[/dim] {nb.subdir}")
        if st is None or st.error:
            console.print(f"  [red]status: {st.error if st else 'unknown'}[/red]")
            continue
        flags = []
        if st.ahead:
            flags.append(f"[yellow]↑{st.ahead}[/yellow]")
        if st.behind:
            flags.append(f"[yellow]↓{st.behind}[/yellow]")
        if st.dirty:
            flags.append("[yellow]dirty[/yellow]")
        if not st.has_remote:
            flags.append("[dim]no remote[/dim]")
        flag_str = " ".join(flags) if flags else "[green]clean[/green]"
        console.print(f"  [dim]branch:[/dim] {st.branch}  {flag_str}")


@share_cmd.command("status")
@click.argument("name", required=False)
def share_status(name: str | None) -> None:
    """Show git status for one or all shared notebooks."""
    from nb.core.share import status_shared

    statuses = status_shared(name)
    if not statuses:
        console.print("[dim]No shared notebooks.[/dim]")
        return

    for st in statuses:
        console.print(f"[cyan]{st.notebook}[/cyan] [dim]{st.path}[/dim]")
        if st.error:
            console.print(f"  [red]{st.error}[/red]")
            continue
        console.print(f"  branch: {st.branch}")
        if st.ahead:
            console.print(f"  [yellow]ahead by {st.ahead}[/yellow]")
        if st.behind:
            console.print(f"  [yellow]behind by {st.behind}[/yellow]")
        if st.dirty:
            console.print("  [yellow]uncommitted changes[/yellow]")
        if not st.has_remote:
            console.print("  [dim]no remote configured[/dim]")
        if not (st.ahead or st.behind or st.dirty):
            console.print("  [green]up to date[/green]")


@share_cmd.command("sync")
@click.argument("name", required=False)
def share_sync(name: str | None) -> None:
    """Pull + push one or all shared notebooks, then re-index.

    Conflicts in one notebook do not stop the others.

    \b
    Examples:
        nb share sync            Sync all shared notebooks
        nb share sync projectx   Sync only 'projectx'
    """
    from nb.core.git import GitError
    from nb.core.share import sync_shared

    try:
        results = sync_shared(name)
    except GitError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None

    if not results:
        console.print("[dim]No shared notebooks to sync.[/dim]")
        return

    had_conflict = False
    for r in results:
        if r.conflict:
            had_conflict = True
            console.print(f"[red]{r.notebook}: merge conflict[/red]")
            console.print(f"[dim]{r.error}[/dim]")
        elif r.error:
            console.print(f"[red]{r.notebook}: {r.error}[/red]")
        else:
            parts = []
            parts.append("pulled" if r.pulled else "no pull")
            parts.append("pushed" if r.pushed else "no push")
            console.print(
                f"[green]{r.notebook}:[/green] {', '.join(parts)} "
                f"[dim]({r.indexed} files indexed)[/dim]"
            )

    if had_conflict:
        raise SystemExit(1)
