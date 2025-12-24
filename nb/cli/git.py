"""Git integration CLI commands."""

from __future__ import annotations

import click

from nb.cli.utils import console
from nb.config import get_config


def register_git_commands(cli: click.Group) -> None:
    """Register git commands with CLI."""
    cli.add_command(git_cmd)


@click.group("git")
def git_cmd() -> None:
    """Manage git integration for notes.

    Initialize a git repository in your notes directory, enable
    auto-commits, and sync with remote repositories.
    """
    pass


@git_cmd.command("init")
@click.option("--remote", "-r", help="Remote repository URL to add")
def git_init(remote: str | None) -> None:
    """Initialize git repository in notes root.

    Creates a git repository and .gitignore file.
    Optionally adds a remote origin.

    \b
    Examples:
        nb git init
        nb git init --remote git@github.com:user/notes.git
    """
    from nb.core.git import create_gitignore, init_repo, is_git_repo

    config = get_config()

    if is_git_repo(config.notes_root):
        console.print(
            f"[yellow]Git repository already exists in:[/yellow] {config.notes_root}"
        )
        return

    try:
        repo = init_repo(config.notes_root)
        console.print(
            f"[green]Initialized git repository in:[/green] {config.notes_root}"
        )

        create_gitignore(config.notes_root)
        console.print("[green]Created .gitignore[/green]")

        if remote:
            repo.create_remote("origin", remote)
            console.print(f"[green]Added remote origin:[/green] {remote}")

        console.print("\n[dim]Enable auto-commits with:[/dim]")
        console.print("  nb config set git.enabled true")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@git_cmd.command("status")
@click.option("--verbose", "-v", is_flag=True, help="Show file details")
def git_status(verbose: bool) -> None:
    """Show git status of notes repository."""
    from nb.core.git import get_status, has_remote, is_git_repo

    config = get_config()

    if not is_git_repo(config.notes_root):
        console.print("[red]Not a git repository.[/red] Run 'nb git init' first.")
        raise SystemExit(1)

    try:
        status = get_status(config.notes_root)

        console.print(f"[cyan]Branch:[/cyan] {status['branch']}")

        if has_remote(config.notes_root):
            if status["ahead"] > 0:
                console.print(f"[yellow]Ahead by {status['ahead']} commit(s)[/yellow]")
            if status["behind"] > 0:
                console.print(
                    f"[yellow]Behind by {status['behind']} commit(s)[/yellow]"
                )

        if status["staged"]:
            console.print(
                f"\n[green]Staged changes:[/green] {len(status['staged'])} file(s)"
            )
            if verbose:
                for f in status["staged"]:
                    console.print(f"  [green]+[/green] {f}")

        if status["modified"]:
            console.print(
                f"\n[yellow]Modified:[/yellow] {len(status['modified'])} file(s)"
            )
            if verbose:
                for f in status["modified"]:
                    console.print(f"  [yellow]M[/yellow] {f}")

        if status["untracked"]:
            console.print(f"\n[dim]Untracked:[/dim] {len(status['untracked'])} file(s)")
            if verbose:
                for f in status["untracked"]:
                    console.print(f"  [dim]?[/dim] {f}")

        if not (status["staged"] or status["modified"] or status["untracked"]):
            console.print("\n[green]Working tree clean[/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@git_cmd.command("commit")
@click.argument("message", required=False)
@click.option("--all", "-a", "commit_all_flag", is_flag=True, help="Commit all changes")
def git_commit(message: str | None, commit_all_flag: bool) -> None:
    """Manually commit changes.

    \b
    Examples:
        nb git commit "Weekly review complete"
        nb git commit --all
    """
    from nb.core.git import commit_all, is_git_repo

    config = get_config()

    if not is_git_repo(config.notes_root):
        console.print("[red]Not a git repository.[/red] Run 'nb git init' first.")
        raise SystemExit(1)

    if not message:
        message = "Manual commit via nb"

    try:
        if commit_all(message, config.notes_root):
            console.print(f"[green]Committed:[/green] {message}")
        else:
            console.print("[dim]No changes to commit[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@git_cmd.command("push")
@click.option("--remote", "-r", default="origin", help="Remote name")
@click.option("--force", "-f", is_flag=True, help="Force push (use with caution)")
def git_push(remote: str, force: bool) -> None:
    """Push commits to remote repository.

    \b
    Example:
        nb git push
        nb git push --remote upstream
    """
    from nb.core.git import has_remote, is_git_repo, push

    config = get_config()

    if not is_git_repo(config.notes_root):
        console.print("[red]Not a git repository.[/red] Run 'nb git init' first.")
        raise SystemExit(1)

    if not has_remote(config.notes_root):
        console.print("[red]No remote configured.[/red]")
        console.print("Add a remote with: nb git remote --add <url>")
        raise SystemExit(1)

    if force:
        console.print(
            "[yellow]Warning: Force push can overwrite remote history![/yellow]"
        )
        click.confirm("Are you sure?", abort=True)

    try:
        push(config.notes_root, remote=remote, force=force)
        console.print(f"[green]Pushed to {remote}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@git_cmd.command("pull")
@click.option("--remote", "-r", default="origin", help="Remote name")
def git_pull(remote: str) -> None:
    """Pull changes from remote repository.

    Aborts on conflicts with instructions for manual resolution.
    """
    from nb.core.git import GitConflictError, is_git_repo, pull

    config = get_config()

    if not is_git_repo(config.notes_root):
        console.print("[red]Not a git repository.[/red] Run 'nb git init' first.")
        raise SystemExit(1)

    try:
        pull(config.notes_root, remote=remote)
        console.print(f"[green]Pulled from {remote}[/green]")
    except GitConflictError as e:
        console.print("[red]Merge conflicts detected:[/red]")
        console.print(str(e))
        console.print("\n[yellow]To resolve:[/yellow]")
        console.print("1. Manually resolve conflicts in the listed files")
        console.print("2. Stage resolved files: git add <file>")
        console.print("3. Complete merge: git commit")
        console.print("4. Or abort: git merge --abort")
        raise SystemExit(1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@git_cmd.command("sync")
def git_sync() -> None:
    """Pull then push (convenience command).

    Equivalent to: nb git pull && nb git push
    """
    from nb.core.git import has_remote, is_git_repo, sync

    config = get_config()

    if not is_git_repo(config.notes_root):
        console.print("[red]Not a git repository.[/red] Run 'nb git init' first.")
        raise SystemExit(1)

    if not has_remote(config.notes_root):
        console.print("[red]No remote configured.[/red]")
        console.print("Add a remote with: nb git remote --add <url>")
        raise SystemExit(1)

    try:
        pull_ok, push_ok = sync(config.notes_root)

        if pull_ok:
            console.print("[green]Pulled from remote[/green]")
        else:
            console.print("[dim]No changes to pull[/dim]")

        if push_ok:
            console.print("[green]Pushed to remote[/green]")
        else:
            console.print("[dim]No changes to push[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@git_cmd.command("log")
@click.option("--limit", "-n", default=10, help="Number of commits to show")
@click.option("--oneline", is_flag=True, help="Compact one-line format")
def git_log(limit: int, oneline: bool) -> None:
    """Show commit history.

    \b
    Example:
        nb git log
        nb git log --limit 20 --oneline
    """
    from nb.core.git import get_log, is_git_repo

    config = get_config()

    if not is_git_repo(config.notes_root):
        console.print("[red]Not a git repository.[/red] Run 'nb git init' first.")
        raise SystemExit(1)

    try:
        commits = get_log(limit, config.notes_root)

        if not commits:
            console.print("[dim]No commits yet[/dim]")
            return

        if oneline:
            for c in commits:
                date_str = c["date"].strftime("%Y-%m-%d")
                console.print(
                    f"[yellow]{c['hash'][:7]}[/yellow] {date_str} {c['message']}"
                )
        else:
            for c in commits:
                console.print(f"[yellow]Commit:[/yellow] {c['hash']}")
                console.print(f"[cyan]Author:[/cyan] {c['author']}")
                console.print(f"[cyan]Date:[/cyan]   {c['date']}")
                console.print(f"\n    {c['message']}\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@git_cmd.command("remote")
@click.argument("url", required=False)
@click.option("--add", "-a", is_flag=True, help="Add remote origin")
@click.option("--remove", "-r", is_flag=True, help="Remove remote origin")
def git_remote(url: str | None, add: bool, remove: bool) -> None:
    """Manage remote repository.

    \b
    Examples:
        nb git remote
        nb git remote --add git@github.com:user/notes.git
        nb git remote --remove
    """
    from nb.core.git import get_repo, is_git_repo

    config = get_config()

    if not is_git_repo(config.notes_root):
        console.print("[red]Not a git repository.[/red] Run 'nb git init' first.")
        raise SystemExit(1)

    repo = get_repo(config.notes_root)
    if repo is None:
        console.print("[red]Could not access repository[/red]")
        raise SystemExit(1)

    try:
        if add:
            if not url:
                console.print("[red]Error:[/red] URL required with --add")
                raise SystemExit(1)

            if "origin" in [r.name for r in repo.remotes]:
                console.print(
                    "[yellow]Warning:[/yellow] Remote 'origin' already exists"
                )
                click.confirm("Remove and re-add?", abort=True)
                repo.delete_remote(repo.remotes.origin)

            repo.create_remote("origin", url)
            console.print(f"[green]Added remote origin:[/green] {url}")

        elif remove:
            if "origin" not in [r.name for r in repo.remotes]:
                console.print("[yellow]No remote 'origin' configured[/yellow]")
            else:
                repo.delete_remote(repo.remotes.origin)
                console.print("[green]Removed remote origin[/green]")

        else:
            # Show current remote
            if "origin" in [r.name for r in repo.remotes]:
                origin = repo.remotes.origin
                console.print(f"[cyan]origin[/cyan] {origin.url}")
            else:
                console.print("[dim]No remote configured[/dim]")
                console.print("Add one with: nb git remote --add <url>")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None
