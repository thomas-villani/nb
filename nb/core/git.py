"""Git integration for nb notes."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import git as gitmodule


class GitError(Exception):
    """Base exception for git operations."""

    pass


class GitConflictError(GitError):
    """Raised when a merge conflict occurs."""

    pass


class GitNotInitializedError(GitError):
    """Raised when git repo is not initialized."""

    pass


def is_git_repo(notes_root: Path | None = None) -> bool:
    """Check if notes_root is a git repository.

    Args:
        notes_root: Path to check. Defaults to config notes_root.

    Returns:
        True if .git directory exists.
    """
    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    return (notes_root / ".git").is_dir()


def get_repo(notes_root: Path | None = None) -> gitmodule.Repo | None:
    """Get git.Repo instance for notes_root.

    Args:
        notes_root: Path to repo. Defaults to config notes_root.

    Returns:
        git.Repo instance or None if not a git repo.
    """
    import git

    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    if not is_git_repo(notes_root):
        return None

    return git.Repo(notes_root)


def init_repo(notes_root: Path | None = None) -> gitmodule.Repo:
    """Initialize a git repository in notes_root.

    Args:
        notes_root: Path to initialize. Defaults to config notes_root.

    Returns:
        git.Repo instance for the new repository.

    Raises:
        GitError: If initialization fails.
    """
    import git

    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    try:
        repo = git.Repo.init(notes_root)
        return repo
    except git.GitCommandError as e:
        raise GitError(f"Failed to initialize git repository: {e}") from e


def create_gitignore(notes_root: Path | None = None) -> Path:
    """Create a .gitignore file that excludes the .nb cache directory.

    Args:
        notes_root: Path to notes root. Defaults to config notes_root.

    Returns:
        Path to the created .gitignore file.
    """
    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    gitignore_path = notes_root / ".gitignore"

    content = """\
# nb-cli cache and database (can be rebuilt with 'nb index --force')
.nb/

# Common temporary files
.DS_Store
Thumbs.db
*.swp
*.swo
*~

# Editor directories
.vscode/
.idea/

# Add your own patterns below
"""

    gitignore_path.write_text(content, encoding="utf-8")
    return gitignore_path


def _is_git_enabled() -> bool:
    """Check if git integration is enabled in config."""
    from nb.config import get_config

    config = get_config()
    return getattr(config, "git", None) is not None and config.git.enabled


def commit_file(
    path: Path,
    message: str | None = None,
    notes_root: Path | None = None,
) -> bool:
    """Stage and commit a single file.

    Args:
        path: Path to the file (absolute or relative to notes_root).
        message: Commit message. If None, uses template from config.
        notes_root: Notes root directory.

    Returns:
        True if commit was made, False if no changes to commit.

    Raises:
        GitNotInitializedError: If git repo is not initialized.
        GitError: If commit fails.
    """
    import git

    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        raise GitNotInitializedError(
            "Git repository not initialized. Run 'nb git init' first."
        )

    # Make path relative to notes_root if absolute
    if path.is_absolute():
        try:
            rel_path = path.relative_to(notes_root)
        except ValueError:
            rel_path = path
    else:
        rel_path = path

    # Check if file exists (for staging) or was deleted (for removal)
    abs_path = notes_root / rel_path
    try:
        if abs_path.exists():
            repo.index.add([str(rel_path)])
        else:
            # File was deleted, stage the deletion
            try:
                repo.index.remove([str(rel_path)], working_tree=False)
            except git.GitCommandError:
                # File might not be tracked, ignore
                pass
    except git.GitCommandError as e:
        raise GitError(f"Failed to stage file: {e}") from e

    # Check if there are staged changes
    # For fresh repos without HEAD, we can't diff against HEAD
    try:
        _ = repo.head.commit  # Check if HEAD exists
        # HEAD exists - check if there are staged changes
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            return False
    except (git.InvalidGitRepositoryError, ValueError):
        # Fresh repo with no commits - proceed with commit if we staged something
        pass

    # Generate commit message
    if message is None:
        message = _format_commit_message(rel_path, notes_root)

    try:
        repo.index.commit(message)
        return True
    except git.GitCommandError as e:
        raise GitError(f"Failed to commit: {e}") from e


def commit_all(message: str, notes_root: Path | None = None) -> bool:
    """Stage and commit all changes.

    Args:
        message: Commit message.
        notes_root: Notes root directory.

    Returns:
        True if commit was made, False if no changes to commit.

    Raises:
        GitNotInitializedError: If git repo is not initialized.
        GitError: If commit fails.
    """
    import git

    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        raise GitNotInitializedError(
            "Git repository not initialized. Run 'nb git init' first."
        )

    try:
        # Stage all changes (modified, deleted, new files)
        repo.git.add(A=True)

        # Check if there are changes to commit
        if repo.is_dirty() or repo.untracked_files:
            repo.index.commit(message)
            return True
        return False
    except git.GitCommandError as e:
        raise GitError(f"Failed to commit: {e}") from e


def get_status(notes_root: Path | None = None) -> dict:
    """Get git status information.

    Args:
        notes_root: Notes root directory.

    Returns:
        Dict with keys:
            - branch: Current branch name
            - staged: List of staged files
            - modified: List of modified but unstaged files
            - untracked: List of untracked files
            - ahead: Number of commits ahead of remote
            - behind: Number of commits behind remote

    Raises:
        GitNotInitializedError: If git repo is not initialized.
    """
    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        raise GitNotInitializedError(
            "Git repository not initialized. Run 'nb git init' first."
        )

    # Get branch name
    try:
        branch = repo.active_branch.name
    except TypeError:
        branch = "HEAD (detached)"

    # Get staged files
    staged = []
    try:
        for diff in repo.index.diff("HEAD"):
            staged.append(diff.a_path or diff.b_path)
    except Exception:
        # No HEAD yet (fresh repo)
        staged = [str(item[0]) for item in repo.index.entries.keys()]

    # Get modified (unstaged) files
    modified = [diff.a_path or diff.b_path for diff in repo.index.diff(None)]

    # Get untracked files
    untracked = repo.untracked_files

    # Get ahead/behind counts
    ahead = 0
    behind = 0
    try:
        tracking = repo.active_branch.tracking_branch()
        if tracking:
            ahead = len(list(repo.iter_commits(f"{tracking.name}..HEAD")))
            behind = len(list(repo.iter_commits(f"HEAD..{tracking.name}")))
    except Exception:
        pass

    return {
        "branch": branch,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "ahead": ahead,
        "behind": behind,
    }


def has_remote(notes_root: Path | None = None) -> bool:
    """Check if repository has a remote configured.

    Args:
        notes_root: Notes root directory.

    Returns:
        True if 'origin' remote exists.
    """
    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        return False

    return "origin" in [r.name for r in repo.remotes]


def push(
    notes_root: Path | None = None,
    remote: str = "origin",
    branch: str | None = None,
    force: bool = False,
) -> None:
    """Push commits to remote repository.

    Args:
        notes_root: Notes root directory.
        remote: Remote name (default: origin).
        branch: Branch to push. Defaults to current branch.
        force: Force push (use with caution).

    Raises:
        GitNotInitializedError: If git repo is not initialized.
        GitError: If push fails.
    """
    import git

    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        raise GitNotInitializedError(
            "Git repository not initialized. Run 'nb git init' first."
        )

    if remote not in [r.name for r in repo.remotes]:
        raise GitError(
            f"Remote '{remote}' not found. Add it with 'nb git remote --add <url>'"
        )

    if branch is None:
        try:
            branch = repo.active_branch.name
        except TypeError:
            raise GitError("Cannot push from detached HEAD state") from None

    try:
        remote_obj = repo.remote(remote)
        if force:
            remote_obj.push(branch, force=True)
        else:
            # Set upstream if not set
            push_info = remote_obj.push(branch, set_upstream=True)
            for info in push_info:
                if info.flags & info.ERROR:
                    raise GitError(f"Push failed: {info.summary}")
    except git.GitCommandError as e:
        raise GitError(f"Failed to push: {e}") from e


def pull(
    notes_root: Path | None = None,
    remote: str = "origin",
    branch: str | None = None,
) -> None:
    """Pull changes from remote repository.

    Args:
        notes_root: Notes root directory.
        remote: Remote name (default: origin).
        branch: Branch to pull. Defaults to current branch.

    Raises:
        GitNotInitializedError: If git repo is not initialized.
        GitConflictError: If merge conflicts occur.
        GitError: If pull fails.
    """
    import git

    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        raise GitNotInitializedError(
            "Git repository not initialized. Run 'nb git init' first."
        )

    if remote not in [r.name for r in repo.remotes]:
        raise GitError(f"Remote '{remote}' not found.")

    if branch is None:
        try:
            branch = repo.active_branch.name
        except TypeError:
            raise GitError("Cannot pull to detached HEAD state") from None

    try:
        remote_obj = repo.remote(remote)
        remote_obj.fetch()

        # Check for conflicts before merging
        try:
            repo.git.merge(f"{remote}/{branch}", no_commit=True, no_ff=True)
            # If we get here, no conflicts - complete the merge
            if repo.index.diff("HEAD"):
                repo.git.commit(m=f"Merge {remote}/{branch}")
        except git.GitCommandError as e:
            if "CONFLICT" in str(e) or "conflict" in str(e).lower():
                # Abort the merge
                repo.git.merge(abort=True)
                # Get conflicting files
                raise GitConflictError(
                    f"Merge conflicts detected. Please resolve manually:\n"
                    f"  cd {notes_root}\n"
                    f"  git pull {remote} {branch}\n"
                    f"  # Resolve conflicts, then: git add . && git commit"
                ) from None
            raise GitError(f"Failed to pull: {e}") from e
    except git.GitCommandError as e:
        raise GitError(f"Failed to pull: {e}") from e


def sync(notes_root: Path | None = None) -> tuple[bool, bool]:
    """Pull then push (convenience function).

    Args:
        notes_root: Notes root directory.

    Returns:
        Tuple of (pull_had_changes, push_had_changes).

    Raises:
        GitNotInitializedError: If git repo is not initialized.
        GitConflictError: If merge conflicts occur during pull.
        GitError: If sync fails.
    """
    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        raise GitNotInitializedError(
            "Git repository not initialized. Run 'nb git init' first."
        )

    if not has_remote(notes_root):
        raise GitError("No remote configured. Add one with 'nb git remote --add <url>'")

    # Track if we had changes
    status_before = get_status(notes_root)
    behind_before = status_before["behind"]

    # Pull
    pull(notes_root)
    pull_had_changes = behind_before > 0

    # Push
    status_after = get_status(notes_root)
    ahead_after = status_after["ahead"]
    if ahead_after > 0:
        push(notes_root)
        push_had_changes = True
    else:
        push_had_changes = False

    return pull_had_changes, push_had_changes


def get_log(limit: int = 10, notes_root: Path | None = None) -> list[dict]:
    """Get commit history.

    Args:
        limit: Maximum number of commits to return.
        notes_root: Notes root directory.

    Returns:
        List of dicts with keys: hash, message, author, date.

    Raises:
        GitNotInitializedError: If git repo is not initialized.
    """
    if notes_root is None:
        from nb.config import get_config

        notes_root = get_config().notes_root

    repo = get_repo(notes_root)
    if repo is None:
        raise GitNotInitializedError(
            "Git repository not initialized. Run 'nb git init' first."
        )

    commits = []
    try:
        for commit in repo.iter_commits(max_count=limit):
            # commit.message can be bytes or str depending on GitPython version
            msg = commit.message
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
            commits.append(
                {
                    "hash": commit.hexsha,
                    "message": msg.strip().split("\n")[0],
                    "author": f"{commit.author.name} <{commit.author.email}>",
                    "date": datetime.fromtimestamp(commit.committed_date),
                }
            )
    except Exception:
        # No commits yet
        pass

    return commits


def _format_commit_message(path: Path, notes_root: Path) -> str:
    """Format commit message using template from config.

    Args:
        path: Relative path to the file.
        notes_root: Notes root directory.

    Returns:
        Formatted commit message.
    """
    from nb.config import get_config

    config = get_config()

    # Get template
    template = "Update {path}"
    if hasattr(config, "git") and config.git is not None:
        template = config.git.commit_message_template

    # Get notebook name from path
    parts = path.parts
    notebook = parts[0] if parts else "notes"

    # Get title from filename
    title = path.stem

    # Format the message
    return template.format(
        path=str(path),
        notebook=notebook,
        title=title,
        date=datetime.now().strftime("%Y-%m-%d"),
    )


def auto_commit_file(path: Path, notes_root: Path | None = None) -> None:
    """Auto-commit a file if git integration is enabled.

    This is a helper function for use in note operations. It silently
    handles errors to avoid breaking note operations.

    Args:
        path: Path to the file.
        notes_root: Notes root directory.
    """
    from nb.config import get_config

    config = get_config()

    # Check if git is enabled and auto_commit is on
    if not hasattr(config, "git") or config.git is None:
        return
    if not config.git.enabled or not config.git.auto_commit:
        return

    # Don't commit if not a git repo
    if notes_root is None:
        notes_root = config.notes_root
    if not is_git_repo(notes_root):
        return

    try:
        commit_file(path, notes_root=notes_root)
    except Exception as e:
        # Non-blocking: just print warning
        print(f"Warning: Git auto-commit failed: {e}", file=sys.stderr)
