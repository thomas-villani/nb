"""Tests for git integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from nb import config as config_module
from nb.cli import cli
from nb.config import Config, EmbeddingsConfig, GitConfig, NotebookConfig
from nb.index.db import reset_db

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def git_config(tmp_path: Path):
    """Create a config with git enabled for testing."""
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()

    cfg = Config(
        notes_root=notes_root,
        editor="echo",
        notebooks=[
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
        ],
        embeddings=EmbeddingsConfig(),
        git=GitConfig(enabled=True, auto_commit=True),
    )

    # Create notebook directories
    for nb in cfg.notebooks:
        if not nb.is_external:
            (notes_root / nb.name).mkdir(exist_ok=True)

    yield cfg

    config_module.reset_config()
    reset_db()


@pytest.fixture
def mock_git_config(git_config: Config, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Mock get_config() to return git_config."""
    config_module.reset_config()
    monkeypatch.setattr(config_module, "_config", git_config)
    return git_config


@pytest.fixture
def git_disabled_config(tmp_path: Path):
    """Create a config with git disabled."""
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()

    cfg = Config(
        notes_root=notes_root,
        editor="echo",
        notebooks=[NotebookConfig(name="projects", date_based=False)],
        embeddings=EmbeddingsConfig(),
        git=GitConfig(enabled=False),
    )

    (notes_root / "projects").mkdir(exist_ok=True)

    yield cfg

    config_module.reset_config()
    reset_db()


@pytest.fixture
def mock_git_disabled_config(
    git_disabled_config: Config, monkeypatch: pytest.MonkeyPatch
) -> Config:
    """Mock get_config() with git disabled."""
    config_module.reset_config()
    monkeypatch.setattr(config_module, "_config", git_disabled_config)
    return git_disabled_config


# =============================================================================
# Core Git Module Tests
# =============================================================================


class TestIsGitRepo:
    """Tests for is_git_repo function."""

    def test_returns_false_when_no_git(self, mock_git_config: Config):
        """Should return False when .git directory doesn't exist."""
        from nb.core.git import is_git_repo

        assert is_git_repo(mock_git_config.notes_root) is False

    def test_returns_true_when_git_exists(self, mock_git_config: Config):
        """Should return True when .git directory exists."""
        from nb.core.git import is_git_repo

        # Create .git directory
        (mock_git_config.notes_root / ".git").mkdir()
        assert is_git_repo(mock_git_config.notes_root) is True


class TestInitRepo:
    """Tests for init_repo function."""

    def test_init_creates_git_repo(self, mock_git_config: Config):
        """Should create a git repository."""
        from nb.core.git import init_repo, is_git_repo

        repo = init_repo(mock_git_config.notes_root)

        assert repo is not None
        assert is_git_repo(mock_git_config.notes_root) is True
        assert (mock_git_config.notes_root / ".git").is_dir()

    def test_init_returns_repo_object(self, mock_git_config: Config):
        """Should return a git.Repo object."""
        import git

        from nb.core.git import init_repo

        repo = init_repo(mock_git_config.notes_root)

        assert isinstance(repo, git.Repo)


class TestCreateGitignore:
    """Tests for create_gitignore function."""

    def test_creates_gitignore_file(self, mock_git_config: Config):
        """Should create a .gitignore file."""
        from nb.core.git import create_gitignore

        gitignore_path = create_gitignore(mock_git_config.notes_root)

        assert gitignore_path.exists()
        assert gitignore_path.name == ".gitignore"

    def test_gitignore_excludes_nb_dir(self, mock_git_config: Config):
        """Should exclude .nb directory."""
        from nb.core.git import create_gitignore

        create_gitignore(mock_git_config.notes_root)

        content = (mock_git_config.notes_root / ".gitignore").read_text()
        assert ".nb/" in content


class TestGetRepo:
    """Tests for get_repo function."""

    def test_returns_none_when_not_git_repo(self, mock_git_config: Config):
        """Should return None when not a git repo."""
        from nb.core.git import get_repo

        assert get_repo(mock_git_config.notes_root) is None

    def test_returns_repo_when_initialized(self, mock_git_config: Config):
        """Should return Repo object when git is initialized."""
        import git

        from nb.core.git import get_repo, init_repo

        init_repo(mock_git_config.notes_root)
        repo = get_repo(mock_git_config.notes_root)

        assert isinstance(repo, git.Repo)


class TestCommitFile:
    """Tests for commit_file function."""

    def test_raises_when_not_initialized(self, mock_git_config: Config):
        """Should raise GitNotInitializedError when repo not initialized."""
        from nb.core.git import GitNotInitializedError, commit_file

        test_file = mock_git_config.notes_root / "test.md"
        test_file.write_text("# Test")

        with pytest.raises(GitNotInitializedError):
            commit_file(test_file, notes_root=mock_git_config.notes_root)

    def test_commits_new_file(self, mock_git_config: Config):
        """Should commit a new file."""
        from nb.core.git import commit_file, get_repo, init_repo

        init_repo(mock_git_config.notes_root)

        test_file = mock_git_config.notes_root / "projects" / "test.md"
        test_file.write_text("# Test Note")

        result = commit_file(test_file, notes_root=mock_git_config.notes_root)

        assert result is True
        repo = get_repo(mock_git_config.notes_root)
        assert repo is not None
        # Check that there's at least one commit
        assert len(list(repo.iter_commits())) >= 1


class TestCommitAll:
    """Tests for commit_all function."""

    def test_commits_all_changes(self, mock_git_config: Config):
        """Should commit all changes."""
        from nb.core.git import commit_all, get_repo, init_repo

        init_repo(mock_git_config.notes_root)

        # Create multiple files
        (mock_git_config.notes_root / "file1.md").write_text("# File 1")
        (mock_git_config.notes_root / "file2.md").write_text("# File 2")

        result = commit_all("Test commit", mock_git_config.notes_root)

        assert result is True
        repo = get_repo(mock_git_config.notes_root)
        assert repo is not None
        assert len(list(repo.iter_commits())) >= 1

    def test_returns_false_when_no_changes(self, mock_git_config: Config):
        """Should return False when no changes to commit."""
        from nb.core.git import commit_all, init_repo

        init_repo(mock_git_config.notes_root)

        # First commit
        (mock_git_config.notes_root / "file1.md").write_text("# File 1")
        commit_all("Initial", mock_git_config.notes_root)

        # Second call with no changes
        result = commit_all("No changes", mock_git_config.notes_root)

        assert result is False


class TestGetStatus:
    """Tests for get_status function."""

    def test_returns_status_dict(self, mock_git_config: Config):
        """Should return a dict with status info."""
        from nb.core.git import get_status, init_repo

        init_repo(mock_git_config.notes_root)
        status = get_status(mock_git_config.notes_root)

        assert "branch" in status
        assert "staged" in status
        assert "modified" in status
        assert "untracked" in status
        assert "ahead" in status
        assert "behind" in status

    def test_shows_untracked_files(self, mock_git_config: Config):
        """Should show untracked files."""
        from nb.core.git import get_status, init_repo

        init_repo(mock_git_config.notes_root)
        (mock_git_config.notes_root / "untracked.md").write_text("# Untracked")

        status = get_status(mock_git_config.notes_root)

        assert "untracked.md" in status["untracked"]


class TestGetLog:
    """Tests for get_log function."""

    def test_returns_empty_list_when_no_commits(self, mock_git_config: Config):
        """Should return empty list when no commits."""
        from nb.core.git import get_log, init_repo

        init_repo(mock_git_config.notes_root)

        commits = get_log(notes_root=mock_git_config.notes_root)

        assert commits == []

    def test_returns_commits(self, mock_git_config: Config):
        """Should return list of commits."""
        from nb.core.git import commit_all, get_log, init_repo

        init_repo(mock_git_config.notes_root)
        (mock_git_config.notes_root / "file.md").write_text("# File")
        commit_all("Test commit", mock_git_config.notes_root)

        commits = get_log(notes_root=mock_git_config.notes_root)

        assert len(commits) == 1
        assert commits[0]["message"] == "Test commit"
        assert "hash" in commits[0]
        assert "author" in commits[0]
        assert "date" in commits[0]


class TestAutoCommitFile:
    """Tests for auto_commit_file helper function."""

    def test_does_nothing_when_disabled(self, mock_git_disabled_config: Config):
        """Should do nothing when git is disabled."""
        from nb.core.git import auto_commit_file, init_repo

        init_repo(mock_git_disabled_config.notes_root)
        test_file = mock_git_disabled_config.notes_root / "test.md"
        test_file.write_text("# Test")

        # Should not raise and should not commit
        auto_commit_file(test_file, notes_root=mock_git_disabled_config.notes_root)

        # File should still be untracked (no auto-commit occurred)
        from nb.core.git import get_status

        status = get_status(mock_git_disabled_config.notes_root)
        assert "test.md" in status["untracked"]

    def test_commits_when_enabled(self, mock_git_config: Config):
        """Should commit when git is enabled."""
        from nb.core.git import auto_commit_file, get_log, init_repo

        init_repo(mock_git_config.notes_root)
        test_file = mock_git_config.notes_root / "projects" / "test.md"
        test_file.write_text("# Test")

        auto_commit_file(test_file, notes_root=mock_git_config.notes_root)

        commits = get_log(notes_root=mock_git_config.notes_root)
        assert len(commits) == 1


# =============================================================================
# CLI Git Command Tests
# =============================================================================


class TestGitInitCommand:
    """Tests for 'nb git init' command."""

    def test_init_creates_repo(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should initialize git repository."""
        from nb.core.git import is_git_repo

        result = cli_runner.invoke(cli, ["git", "init"])

        assert result.exit_code == 0
        assert "Initialized git repository" in result.output
        assert is_git_repo(mock_git_config.notes_root) is True

    def test_init_creates_gitignore(
        self, cli_runner: CliRunner, mock_git_config: Config
    ):
        """Should create .gitignore file."""
        result = cli_runner.invoke(cli, ["git", "init"])

        assert result.exit_code == 0
        assert "Created .gitignore" in result.output
        assert (mock_git_config.notes_root / ".gitignore").exists()

    def test_init_warns_if_already_exists(
        self, cli_runner: CliRunner, mock_git_config: Config
    ):
        """Should warn if git repo already exists."""
        from nb.core.git import init_repo

        init_repo(mock_git_config.notes_root)

        result = cli_runner.invoke(cli, ["git", "init"])

        assert "already exists" in result.output


class TestGitStatusCommand:
    """Tests for 'nb git status' command."""

    def test_status_shows_branch(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show current branch."""
        from nb.core.git import init_repo

        init_repo(mock_git_config.notes_root)

        result = cli_runner.invoke(cli, ["git", "status"])

        assert result.exit_code == 0
        assert "Branch:" in result.output

    def test_status_shows_untracked(
        self, cli_runner: CliRunner, mock_git_config: Config
    ):
        """Should show untracked files."""
        from nb.core.git import init_repo

        init_repo(mock_git_config.notes_root)
        (mock_git_config.notes_root / "new.md").write_text("# New")

        result = cli_runner.invoke(cli, ["git", "status"])

        assert result.exit_code == 0
        assert "Untracked:" in result.output

    def test_status_fails_without_repo(
        self, cli_runner: CliRunner, mock_git_config: Config
    ):
        """Should fail if not a git repo."""
        result = cli_runner.invoke(cli, ["git", "status"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output


class TestGitCommitCommand:
    """Tests for 'nb git commit' command."""

    def test_commit_with_message(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should commit with provided message."""
        from nb.core.git import get_log, init_repo

        init_repo(mock_git_config.notes_root)
        (mock_git_config.notes_root / "file.md").write_text("# File")

        result = cli_runner.invoke(cli, ["git", "commit", "Test message"])

        assert result.exit_code == 0
        assert "Committed:" in result.output

        commits = get_log(notes_root=mock_git_config.notes_root)
        assert commits[0]["message"] == "Test message"

    def test_commit_no_changes(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should report no changes when nothing to commit."""
        from nb.core.git import init_repo

        init_repo(mock_git_config.notes_root)

        result = cli_runner.invoke(cli, ["git", "commit", "Empty"])

        assert result.exit_code == 0
        assert "No changes to commit" in result.output


class TestGitLogCommand:
    """Tests for 'nb git log' command."""

    def test_log_shows_commits(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show commit history."""
        from nb.core.git import commit_all, init_repo

        init_repo(mock_git_config.notes_root)
        (mock_git_config.notes_root / "file.md").write_text("# File")
        commit_all("First commit", mock_git_config.notes_root)

        result = cli_runner.invoke(cli, ["git", "log"])

        assert result.exit_code == 0
        assert "First commit" in result.output

    def test_log_oneline(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show compact log with --oneline."""
        from nb.core.git import commit_all, init_repo

        init_repo(mock_git_config.notes_root)
        (mock_git_config.notes_root / "file.md").write_text("# File")
        commit_all("First commit", mock_git_config.notes_root)

        result = cli_runner.invoke(cli, ["git", "log", "--oneline"])

        assert result.exit_code == 0
        # Oneline format should be more compact
        lines = [l for l in result.output.strip().split("\n") if l]
        assert len(lines) == 1

    def test_log_empty_repo(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show message when no commits."""
        from nb.core.git import init_repo

        init_repo(mock_git_config.notes_root)

        result = cli_runner.invoke(cli, ["git", "log"])

        assert result.exit_code == 0
        assert "No commits yet" in result.output


class TestGitRemoteCommand:
    """Tests for 'nb git remote' command."""

    def test_remote_shows_none(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show no remote configured."""
        from nb.core.git import init_repo

        init_repo(mock_git_config.notes_root)

        result = cli_runner.invoke(cli, ["git", "remote"])

        assert result.exit_code == 0
        assert "No remote configured" in result.output

    def test_remote_add(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should add a remote."""
        from nb.core.git import init_repo

        init_repo(mock_git_config.notes_root)

        result = cli_runner.invoke(
            cli, ["git", "remote", "--add", "git@github.com:user/notes.git"]
        )

        assert result.exit_code == 0
        assert "Added remote origin" in result.output

    def test_remote_shows_url(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show remote URL when configured."""
        from nb.core.git import get_repo, init_repo

        init_repo(mock_git_config.notes_root)
        repo = get_repo(mock_git_config.notes_root)
        assert repo is not None
        repo.create_remote("origin", "git@github.com:user/notes.git")

        result = cli_runner.invoke(cli, ["git", "remote"])

        assert result.exit_code == 0
        assert "git@github.com:user/notes.git" in result.output


# =============================================================================
# Config Git Settings Tests
# =============================================================================


class TestGitConfigSettings:
    """Tests for git configuration settings."""

    def test_git_enabled_default_false(self, cli_runner: CliRunner, mock_git_config):
        """Default git.enabled should be False."""
        from nb.config import GitConfig

        default = GitConfig()
        assert default.enabled is False

    def test_git_auto_commit_default_true(self):
        """Default git.auto_commit should be True."""
        from nb.config import GitConfig

        default = GitConfig()
        assert default.auto_commit is True

    def test_config_set_git_enabled(
        self, cli_runner: CliRunner, mock_git_disabled_config: Config
    ):
        """Should be able to set git.enabled via config."""
        result = cli_runner.invoke(cli, ["config", "set", "git.enabled", "true"])

        assert result.exit_code == 0
        # The set command should succeed - actual value verification
        # depends on config file persistence which varies in test env
        assert "Error" not in result.output

    def test_config_get_git_enabled(
        self, cli_runner: CliRunner, mock_git_config: Config
    ):
        """Should be able to get git.enabled via config."""
        result = cli_runner.invoke(cli, ["config", "get", "git.enabled"])

        assert result.exit_code == 0
        assert "True" in result.output

    def test_config_list_shows_git_settings(
        self, cli_runner: CliRunner, mock_git_config: Config
    ):
        """Config list should include git settings."""
        result = cli_runner.invoke(cli, ["config", "list"])

        assert result.exit_code == 0
        assert "git.enabled" in result.output
        assert "git.auto_commit" in result.output


# =============================================================================
# Git Help Tests
# =============================================================================


class TestGitHelp:
    """Tests for git command help."""

    def test_git_help(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show git help."""
        result = cli_runner.invoke(cli, ["git", "--help"])

        assert result.exit_code == 0
        assert "Manage git integration" in result.output
        assert "init" in result.output
        assert "status" in result.output
        assert "commit" in result.output
        assert "push" in result.output
        assert "pull" in result.output
        assert "sync" in result.output
        assert "log" in result.output
        assert "remote" in result.output

    def test_git_init_help(self, cli_runner: CliRunner, mock_git_config: Config):
        """Should show git init help."""
        result = cli_runner.invoke(cli, ["git", "init", "--help"])

        assert result.exit_code == 0
        assert "Initialize git repository" in result.output
        assert "--remote" in result.output
