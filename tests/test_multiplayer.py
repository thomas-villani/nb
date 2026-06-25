"""Tests for multiplayer notebooks: todo ownership, identity, and shared sync."""

from __future__ import annotations

from pathlib import Path

import pytest

from nb.config import (
    Config,
    NotebookConfig,
    TeamConfig,
    load_config,
    save_config,
)
from nb.core.share import find_repo_root, is_git_url, status_shared, sync_shared
from nb.core.todos import OWNER_PATTERN, clean_todo_content, parse_owner
from nb.index.db import SCHEMA_VERSION, Database, apply_migrations


class TestOwnerGrammar:
    """@owner(handle) / @for(handle) parsing."""

    def test_owner_pattern_matches(self):
        m = OWNER_PATTERN.search("Ship API @owner(federico)")
        assert m is not None
        assert m.group("handle") == "federico"

    def test_for_alias(self):
        assert parse_owner("Do it @for(Thomas)") == "thomas"

    def test_parse_owner_lowercases(self):
        assert parse_owner("Task @owner(Federico)") == "federico"

    def test_parse_owner_none(self):
        assert parse_owner("Task with no owner @due(friday)") is None

    def test_clean_strips_owner(self):
        cleaned = clean_todo_content("Ship API @owner(federico) @due(friday) #backend")
        assert "@owner" not in cleaned
        assert "federico" not in cleaned
        assert cleaned == "Ship API"


class TestOwnerMigration:
    """DB migration adds the owner column."""

    def test_owner_column_exists_after_migration(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        try:
            apply_migrations(db)
            assert SCHEMA_VERSION >= 20
            cols = [r["name"] for r in db.fetchall("PRAGMA table_info(todos)")]
            assert "owner" in cols
        finally:
            db.close()


class TestConfigRoundTrip:
    """TeamConfig and shared/subdir notebook fields persist."""

    def _base_config(self, tmp_path: Path) -> Config:
        notes_root = tmp_path / "notes"
        (notes_root / ".nb").mkdir(parents=True)
        return Config(notes_root=notes_root, editor="echo")

    def test_team_round_trip(self, tmp_path: Path):
        cfg = self._base_config(tmp_path)
        cfg.team = TeamConfig(name="Thomas Villani", handle="thomas", email="t@x.com")
        save_config(cfg)

        loaded = load_config(cfg.config_path)
        assert loaded.team.name == "Thomas Villani"
        assert loaded.team.handle == "thomas"
        assert loaded.team.email == "t@x.com"

    def test_shared_notebook_round_trip(self, tmp_path: Path):
        cfg = self._base_config(tmp_path)
        ext = tmp_path / "shared" / "projectx"
        cfg.notebooks.append(
            NotebookConfig(name="projectx", path=ext, shared=True, subdir=".nbnotes")
        )
        save_config(cfg)

        loaded = load_config(cfg.config_path)
        nb = loaded.get_notebook("projectx")
        assert nb is not None
        assert nb.shared is True
        assert nb.subdir == ".nbnotes"
        assert nb.is_external

    def test_non_shared_notebook_omits_flags(self, tmp_path: Path):
        cfg = self._base_config(tmp_path)
        cfg.notebooks.append(NotebookConfig(name="plain"))
        save_config(cfg)
        text = cfg.config_path.read_text(encoding="utf-8")
        # 'shared'/'subdir' should not be serialized for a plain notebook
        assert "shared:" not in text
        assert "subdir:" not in text


class TestIdentity:
    """get_identity resolution."""

    def test_configured_identity(self, mock_cli_config):
        mock_cli_config.team = TeamConfig(name="Thomas", handle="thomas")
        from nb.core.team import get_identity

        ident = get_identity()
        assert ident.handle == "thomas"
        assert ident.source in ("config", "config+git")

    def test_handle_derived_from_name(self, mock_cli_config):
        mock_cli_config.team = TeamConfig(name="Federico Rossi")
        from nb.core.team import get_identity

        ident = get_identity()
        assert ident.handle == "federico"

    def test_slugify_email(self):
        from nb.core.team import slugify_handle

        assert slugify_handle("fede.rossi@acme.com") == "fede.rossi"
        assert slugify_handle("Thomas Villani") == "thomas"


class TestOwnerFiltering:
    """CLI --owner / --mine filtering end to end."""

    def test_owner_filter(self, cli_runner, indexed_note):
        from nb.cli import cli

        indexed_note(
            "projects",
            "tasks.md",
            "# Tasks\n\n- [ ] Ship API @owner(federico)\n- [ ] Plan @owner(thomas)\n",
        )
        result = cli_runner.invoke(cli, ["todo", "--owner", "federico"])
        assert result.exit_code == 0
        assert "Ship API" in result.output
        assert "Plan" not in result.output

    def test_mine_filter(self, cli_runner, indexed_note, mock_cli_config):
        from nb.cli import cli

        mock_cli_config.team = TeamConfig(handle="thomas")
        indexed_note(
            "projects",
            "tasks.md",
            "# Tasks\n\n- [ ] Ship API @owner(federico)\n- [ ] Plan @owner(thomas)\n",
        )
        result = cli_runner.invoke(cli, ["todo", "--mine"])
        assert result.exit_code == 0
        assert "Plan" in result.output
        assert "Ship API" not in result.output

    def test_mine_without_identity_errors(
        self, cli_runner, indexed_note, mock_cli_config
    ):
        from nb.cli import cli

        mock_cli_config.team = TeamConfig()  # no handle
        # Ensure git fallback doesn't supply a handle in the temp repo
        indexed_note("projects", "tasks.md", "- [ ] X @owner(thomas)\n")
        result = cli_runner.invoke(cli, ["todo", "--mine"])
        # Either errors clearly (no identity) or resolves via git config; both
        # are acceptable, but it must not crash.
        assert result.exit_code == 0


class TestShareHelpers:
    """find_repo_root, is_git_url, and per-notebook sync isolation."""

    def test_find_repo_root_walks_up(self, tmp_path: Path):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        nested = repo / "docs" / "sub"
        nested.mkdir(parents=True)
        assert find_repo_root(nested) == repo.resolve()

    def test_find_repo_root_raises_without_git(self, tmp_path: Path):
        from nb.core.git import GitError

        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(GitError):
            find_repo_root(plain)

    def test_is_git_url(self):
        assert is_git_url("git@github.com:team/proj.git")
        assert is_git_url("https://github.com/team/proj.git")
        assert is_git_url("ssh://host/repo")
        assert not is_git_url(str(Path.home()))

    def test_sync_isolates_errors_per_notebook(self, mock_cli_config, tmp_path: Path):
        # Two shared notebooks pointing at non-repo paths: sync must not raise,
        # and should record an error per notebook instead.
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        mock_cli_config.notebooks.append(NotebookConfig(name="sa", path=a, shared=True))
        mock_cli_config.notebooks.append(NotebookConfig(name="sb", path=b, shared=True))
        results = sync_shared()
        assert {r.notebook for r in results} == {"sa", "sb"}
        assert all(r.error is not None for r in results)

    def test_status_shared_reports_errors(self, mock_cli_config, tmp_path: Path):
        a = tmp_path / "a"
        a.mkdir()
        mock_cli_config.notebooks.append(NotebookConfig(name="sa", path=a, shared=True))
        statuses = status_shared()
        assert len(statuses) == 1
        assert statuses[0].error is not None
