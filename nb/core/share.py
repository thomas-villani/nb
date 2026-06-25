"""Shared (multiplayer) notebooks: external notebooks backed by their own git repo.

A shared notebook is an external NotebookConfig (``path`` outside notes_root) whose
content lives inside a standalone git repository with a remote. Each teammate
registers shared notebooks in their own (gitignored) config; the private notes_root
is never shared.

Git operations reuse ``nb.core.git`` parameterized by the repo *root* — which may be
an ancestor of the notebook's content dir when ``subdir`` is set (use case: hanging
nb notes off an existing code repo).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from nb.config import NotebookConfig, get_config, save_config
from nb.core.git import GitConflictError, GitError


def _default_shared_root() -> Path:
    """Default location for cloned shared notebook repos: notes_root/.nb/shared."""
    return get_config().notes_root / ".nb" / "shared"


def is_git_url(source: str) -> bool:
    """Heuristic: does ``source`` look like a git remote URL rather than a local path?"""
    s = source.strip()
    if "://" in s:  # https://, ssh://, git://
        return True
    if s.startswith("git@"):  # scp-like: git@github.com:user/repo.git
        return True
    # scp-like host:path without scheme (contains a colon before any slash)
    if ":" in s and not Path(s).exists():
        head = s.split(":", 1)[0]
        if "/" not in head and "\\" not in head:
            return True
    return False


def find_repo_root(path: Path) -> Path:
    """Walk up from ``path`` to the enclosing git repository root.

    Args:
        path: A file or directory inside a git working tree.

    Returns:
        The directory containing the ``.git`` entry.

    Raises:
        GitError: If no enclosing git repository is found.
    """
    path = path.resolve()
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    raise GitError(f"No git repository found at or above: {path}")


def shared_notebooks() -> list[NotebookConfig]:
    """Return all notebooks marked as shared."""
    return [nb for nb in get_config().notebooks if nb.shared]


def get_shared_notebook(name: str) -> NotebookConfig:
    """Return the shared notebook with ``name`` or raise."""
    nb = get_config().get_notebook(name)
    if nb is None:
        raise GitError(f"Notebook '{name}' not found.")
    if not nb.shared:
        raise GitError(f"Notebook '{name}' is not a shared notebook.")
    return nb


def reindex_notebook(name: str) -> int:
    """Refresh the index for a single notebook after a sync.

    Removes notes deleted upstream, then force-reindexes. Returns files indexed.
    """
    from nb.index.scanner import index_all_notes, remove_deleted_notes

    remove_deleted_notes(notebook=name)
    return index_all_notes(notebook=name, force=True)


def add_shared(
    source: str,
    name: str,
    subdir: str | None = None,
    date_based: str | bool = False,
) -> NotebookConfig:
    """Register a shared notebook from a git URL or an existing local repo path.

    Args:
        source: A git remote URL (cloned into notes_root/.nb/shared/<name>) or a
            path to an existing local git repo (registered in place).
        name: Notebook name to register.
        subdir: Optional content dir relative to the repo root (e.g. "docs" or
            ".nbnotes"). When set, only that subdir is indexed as the notebook.
        date_based: Date organization mode for the notebook.

    Returns:
        The created NotebookConfig.

    Raises:
        GitError: On clone failure, missing repo, or duplicate notebook name.
    """
    config = get_config()
    if config.get_notebook(name) is not None:
        raise GitError(f"Notebook '{name}' already exists.")

    # Decide whether to clone or register in place:
    #   - A git URL is always cloned into notes_root/.nb/shared/<name>.
    #   - A local path inside a working tree is registered in place (use case 3:
    #     hang nb notes off an existing code repo, synced via that repo's workflow).
    #   - A local path that is NOT a working tree (e.g. a bare repo) is cloned.
    local_path = None if is_git_url(source) else Path(source).expanduser().resolve()
    register_in_place = False
    if local_path is not None:
        if not local_path.exists():
            raise GitError(f"Path does not exist: {local_path}")
        try:
            repo_root = find_repo_root(local_path)
            register_in_place = True
        except GitError:
            register_in_place = False  # not a working tree -> clone it

    if not register_in_place:
        import git

        dest = _default_shared_root() / name
        if dest.exists():
            raise GitError(f"Destination already exists: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        clone_src = source if local_path is None else str(local_path)
        try:
            git.Repo.clone_from(clone_src, str(dest))
        except git.GitCommandError as e:
            raise GitError(f"Failed to clone {source}: {e}") from e
        repo_root = dest

    content_dir = repo_root / subdir if subdir else repo_root
    content_dir.mkdir(parents=True, exist_ok=True)

    from nb.config import add_notebook

    nb = add_notebook(
        name=name,
        date_based=date_based,
        path=content_dir,
        shared=True,
        subdir=subdir,
    )

    reindex_notebook(name)
    return nb


def init_shared(
    name: str,
    remote: str | None = None,
    dest: Path | None = None,
) -> NotebookConfig:
    """Promote an existing internal notebook into a shared git-backed notebook.

    Moves notes_root/<name> to an external location, initializes a git repo there
    (with a .gitignore), optionally adds a remote and pushes, and rewrites the
    notebook config as external + shared.

    Args:
        name: Name of an existing internal notebook.
        remote: Optional remote URL to add as 'origin' and push to.
        dest: Optional destination dir for the repo (default: notes_root/.nb/shared/<name>).

    Returns:
        The updated NotebookConfig.

    Raises:
        GitError: If the notebook is missing, already external/shared, or git fails.
    """
    from nb.core.git import commit_all, create_gitignore, init_repo, push

    config = get_config()
    nb = config.get_notebook(name)
    if nb is None:
        raise GitError(f"Notebook '{name}' not found.")
    if nb.is_external or nb.shared:
        raise GitError(f"Notebook '{name}' is already external/shared.")

    src = config.notes_root / name
    if dest is None:
        dest = _default_shared_root() / name
    dest = dest.expanduser().resolve()
    if dest.exists():
        raise GitError(f"Destination already exists: {dest}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dest))
    else:
        dest.mkdir(parents=True, exist_ok=True)

    # Initialize the repo at the destination and make an initial commit
    init_repo(dest)
    create_gitignore(dest)
    try:
        commit_all("Initialize shared notebook", notes_root=dest)
    except GitError:
        pass  # Empty notebook — nothing to commit yet

    if remote:
        repo = init_repo(dest)  # idempotent: returns existing repo
        if "origin" not in [r.name for r in repo.remotes]:
            repo.create_remote("origin", remote)
        try:
            push(dest)
        except GitError as e:
            raise GitError(f"Notebook moved and committed, but push failed: {e}") from e

    # Rewrite config: external + shared
    nb.path = dest
    nb.shared = True
    nb.subdir = None
    save_config(config)

    reindex_notebook(name)
    return nb


@dataclass
class SyncResult:
    """Outcome of syncing one shared notebook."""

    notebook: str
    pulled: bool = False
    pushed: bool = False
    indexed: int = 0
    conflict: bool = False
    error: str | None = None


def sync_shared(name: str | None = None) -> list[SyncResult]:
    """Sync one or all shared notebooks (git pull+push), then re-index each.

    Conflicts and errors are isolated per-notebook: one failing notebook does not
    abort the others.

    Args:
        name: If given, sync only this shared notebook; otherwise sync all.

    Returns:
        One SyncResult per notebook processed.
    """
    from nb.core.git import commit_all, has_remote, sync

    notebooks = [get_shared_notebook(name)] if name else shared_notebooks()
    results: list[SyncResult] = []

    for nb in notebooks:
        result = SyncResult(notebook=nb.name)
        try:
            if nb.path is None:
                raise GitError("shared notebook has no path")
            repo_root = find_repo_root(nb.path)
            if not has_remote(repo_root):
                raise GitError("no remote configured for this notebook's repo")
            # Commit any local edits first so they get pushed (shared notebooks
            # are edited directly; auto-commit targets notes_root, not this repo).
            commit_all(f"Sync {nb.name} via nb", notes_root=repo_root)
            pulled, pushed = sync(notes_root=repo_root)
            result.pulled = pulled
            result.pushed = pushed
            result.indexed = reindex_notebook(nb.name)
        except GitConflictError as e:
            result.conflict = True
            result.error = str(e)
        except GitError as e:
            result.error = str(e)
        results.append(result)

    return results


@dataclass
class ShareStatus:
    """Git status of one shared notebook."""

    notebook: str
    path: Path
    branch: str = ""
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    has_remote: bool = False
    error: str | None = None


def status_shared(name: str | None = None) -> list[ShareStatus]:
    """Return git status for one or all shared notebooks."""
    from nb.core.git import get_status
    from nb.core.git import has_remote as _has_remote

    notebooks = [get_shared_notebook(name)] if name else shared_notebooks()
    statuses: list[ShareStatus] = []

    for nb in notebooks:
        st = ShareStatus(notebook=nb.name, path=nb.path or Path())
        try:
            if nb.path is None:
                raise GitError("shared notebook has no path")
            repo_root = find_repo_root(nb.path)
            info = get_status(repo_root)
            st.branch = info["branch"]
            st.ahead = info["ahead"]
            st.behind = info["behind"]
            st.dirty = bool(info["staged"] or info["modified"] or info["untracked"])
            st.has_remote = _has_remote(repo_root)
        except GitError as e:
            st.error = str(e)
        statuses.append(st)

    return statuses
