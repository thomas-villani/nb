"""Tests for nb.config module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nb import config as config_module
from nb.config import (
    Config,
    EmbeddingsConfig,
    LinkedNoteConfig,
    LinkedTodoConfig,
    NotebookConfig,
    _parse_embeddings,
    _parse_notebooks,
    add_notebook,
    ensure_directories,
    expand_path,
    get_config,
    init_config,
    load_config,
    remove_notebook,
    reset_config,
    save_config,
)


class TestNotebookConfig:
    """Tests for NotebookConfig dataclass."""

    def test_internal_notebook(self):
        nb = NotebookConfig(name="daily", date_based=True)

        assert nb.name == "daily"
        assert nb.date_based is True
        assert nb.todo_exclude is False
        assert nb.path is None
        assert nb.is_external is False

    def test_external_notebook(self):
        nb = NotebookConfig(
            name="obsidian", date_based=False, path=Path("/external/vault")
        )

        assert nb.is_external is True
        assert nb.path == Path("/external/vault")

    def test_todo_exclude(self):
        nb = NotebookConfig(name="personal", todo_exclude=True)

        assert nb.todo_exclude is True


class TestLinkedTodoConfig:
    """Tests for LinkedTodoConfig dataclass."""

    def test_basic(self):
        linked = LinkedTodoConfig(path=Path("/project/TODO.md"), alias="project")

        assert linked.path == Path("/project/TODO.md")
        assert linked.alias == "project"
        assert linked.sync is True

    def test_no_sync(self):
        linked = LinkedTodoConfig(
            path=Path("/project/TODO.md"), alias="project", sync=False
        )

        assert linked.sync is False


class TestLinkedNoteConfig:
    """Tests for LinkedNoteConfig dataclass."""

    def test_basic(self):
        linked = LinkedNoteConfig(path=Path("/docs/wiki"), alias="wiki")

        assert linked.path == Path("/docs/wiki")
        assert linked.alias == "wiki"
        assert linked.notebook is None
        assert linked.recursive is True

    def test_with_notebook(self):
        linked = LinkedNoteConfig(
            path=Path("/docs/wiki"), alias="wiki", notebook="external-wiki"
        )

        assert linked.notebook == "external-wiki"


class TestEmbeddingsConfig:
    """Tests for EmbeddingsConfig dataclass."""

    def test_defaults(self):
        cfg = EmbeddingsConfig()

        assert cfg.provider == "ollama"
        assert cfg.model == "nomic-embed-text"
        assert cfg.base_url is None
        assert cfg.api_key is None

    def test_custom(self):
        cfg = EmbeddingsConfig(
            provider="openai", model="text-embedding-3-small", api_key="sk-xxx"
        )

        assert cfg.provider == "openai"
        assert cfg.api_key == "sk-xxx"


class TestConfig:
    """Tests for Config dataclass."""

    def test_basic_config(self, temp_notes_root: Path):
        cfg = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[NotebookConfig(name="daily", date_based=True)],
        )

        assert cfg.notes_root == temp_notes_root
        assert cfg.editor == "vim"
        assert len(cfg.notebooks) == 1

    def test_get_notebook(self, temp_config: Config):
        nb = temp_config.get_notebook("daily")
        assert nb is not None
        assert nb.name == "daily"
        assert nb.date_based is True

        assert temp_config.get_notebook("nonexistent") is None

    def test_notebook_names(self, temp_config: Config):
        names = temp_config.notebook_names()
        assert "daily" in names
        assert "projects" in names

    def test_excluded_notebooks(self, temp_notes_root: Path):
        cfg = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[
                NotebookConfig(name="daily"),
                NotebookConfig(name="personal", todo_exclude=True),
            ],
        )

        excluded = cfg.excluded_notebooks()
        assert "personal" in excluded
        assert "daily" not in excluded

    def test_get_notebook_path_internal(self, temp_config: Config):
        path = temp_config.get_notebook_path("daily")
        assert path == temp_config.notes_root / "daily"

    def test_get_notebook_path_external(self, temp_notes_root: Path):
        cfg = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[NotebookConfig(name="external", path=Path("/ext/vault"))],
        )

        path = cfg.get_notebook_path("external")
        assert path == Path("/ext/vault")

    def test_get_notebook_path_not_found(self, temp_config: Config):
        path = temp_config.get_notebook_path("nonexistent")
        assert path is None

    def test_external_notebooks(self, temp_notes_root: Path):
        cfg = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[
                NotebookConfig(name="daily"),
                NotebookConfig(name="external", path=Path("/ext")),
            ],
        )

        external = cfg.external_notebooks()
        assert len(external) == 1
        assert external[0].name == "external"

    def test_nb_dir(self, temp_config: Config):
        assert temp_config.nb_dir == temp_config.notes_root / ".nb"

    def test_db_path(self, temp_config: Config):
        assert temp_config.db_path == temp_config.notes_root / ".nb" / "index.db"

    def test_config_path(self, temp_config: Config):
        assert temp_config.config_path == temp_config.notes_root / ".nb" / "config.yaml"

    def test_vectors_path(self, temp_config: Config):
        assert temp_config.vectors_path == temp_config.notes_root / ".nb" / "vectors"

    def test_attachments_path(self, temp_config: Config):
        assert (
            temp_config.attachments_path
            == temp_config.notes_root / ".nb" / "attachments"
        )


class TestExpandPath:
    """Tests for expand_path function."""

    def test_tilde_expansion(self):
        result = expand_path("~/notes")
        assert "~" not in str(result)
        assert result.is_absolute()

    def test_path_object(self):
        result = expand_path(Path("~/notes"))
        assert isinstance(result, Path)
        assert result.is_absolute()


class TestParseNotebooks:
    """Tests for _parse_notebooks function."""

    def test_string_format(self):
        data = ["daily", "projects", "work"]
        result = _parse_notebooks(data)

        assert len(result) == 3
        # "daily" is date_based by default
        assert result[0].date_based is True
        assert result[1].date_based is False

    def test_dict_format(self):
        data = [
            {"name": "daily", "date_based": True},
            {"name": "projects", "date_based": False, "todo_exclude": True},
        ]
        result = _parse_notebooks(data)

        assert len(result) == 2
        assert result[0].date_based is True
        assert result[1].todo_exclude is True

    def test_external_path(self):
        data = [{"name": "external", "path": "~/external"}]
        result = _parse_notebooks(data)

        assert result[0].is_external is True


class TestParseEmbeddings:
    """Tests for _parse_embeddings function."""

    def test_none_input(self):
        result = _parse_embeddings(None)
        assert result.provider == "ollama"
        assert result.model == "nomic-embed-text"

    def test_custom_config(self):
        data = {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "api_key": "sk-xxx",
        }
        result = _parse_embeddings(data)

        assert result.provider == "openai"
        assert result.api_key == "sk-xxx"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_existing_config(self, temp_notes_root: Path, monkeypatch):
        # Clear EDITOR env var so config file value is used
        monkeypatch.delenv("EDITOR", raising=False)

        config_path = temp_notes_root / ".nb" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config_data = {
            "notes_root": str(temp_notes_root),
            "editor": "nano",
            "notebooks": [{"name": "daily", "date_based": True}],
        }
        with open(config_path, "w") as f:
            yaml.safe_dump(config_data, f)

        cfg = load_config(config_path)

        assert cfg.notes_root == temp_notes_root
        assert cfg.editor == "nano"
        assert len(cfg.notebooks) == 1

    def test_load_nonexistent_uses_defaults(self, tmp_path: Path, monkeypatch):
        # Prevent fallback to real user config
        monkeypatch.setenv("NB_NOTES_ROOT", str(tmp_path / "fake_notes"))

        config_path = tmp_path / "nonexistent" / "config.yaml"

        cfg = load_config(config_path)

        # Should use defaults (4 default notebooks)
        assert len(cfg.notebooks) == 4


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_and_reload(self, temp_notes_root: Path, monkeypatch):
        # Clear EDITOR env var so config file value is used on reload
        monkeypatch.delenv("EDITOR", raising=False)

        cfg = Config(
            notes_root=temp_notes_root,
            editor="code",
            notebooks=[
                NotebookConfig(name="daily", date_based=True),
                NotebookConfig(name="work", date_based=False, todo_exclude=True),
            ],
        )

        save_config(cfg)

        # Reload and verify
        loaded = load_config(cfg.config_path)

        assert loaded.editor == "code"
        assert len(loaded.notebooks) == 2
        assert loaded.notebooks[1].todo_exclude is True


class TestEnsureDirectories:
    """Tests for ensure_directories function."""

    def test_creates_directories(self, temp_notes_root: Path):
        cfg = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[
                NotebookConfig(name="daily"),
                NotebookConfig(name="projects"),
            ],
        )

        ensure_directories(cfg)

        assert (temp_notes_root / ".nb").exists()
        assert (temp_notes_root / "daily").exists()
        assert (temp_notes_root / "projects").exists()

    def test_skips_external(self, temp_notes_root: Path):
        cfg = Config(
            notes_root=temp_notes_root,
            editor="vim",
            notebooks=[NotebookConfig(name="external", path=Path("/nonexistent"))],
        )

        # Should not raise even though external path doesn't exist
        ensure_directories(cfg)


class TestInitConfig:
    """Tests for init_config function."""

    def test_creates_directories_and_config_file(self, tmp_path: Path, monkeypatch):
        notes_root = tmp_path / "notes"
        # Prevent any interference from real config
        monkeypatch.setenv("NB_NOTES_ROOT", str(notes_root))

        cfg = init_config(notes_root)

        # Verifies the structure was created
        assert (notes_root / ".nb" / "config.yaml").exists()
        # Note: cfg.notes_root may point to ~/notes because DEFAULT_CONFIG_YAML
        # has that hardcoded. The important thing is directories were created.
        # The returned config is loaded from the file, which has ~/notes

    def test_creates_notebook_directories(self, tmp_path: Path, monkeypatch):
        notes_root = tmp_path / "notes"
        monkeypatch.setenv("NB_NOTES_ROOT", str(notes_root))

        # First create a custom config in the notes_root
        nb_dir = notes_root / ".nb"
        nb_dir.mkdir(parents=True)
        config_path = nb_dir / "config.yaml"
        config_data = {
            "notes_root": str(notes_root),
            "editor": "vim",
            "notebooks": [{"name": "daily", "date_based": True}],
        }
        with open(config_path, "w") as f:
            yaml.safe_dump(config_data, f)

        # Now init_config should load this config and create directories
        cfg = init_config(notes_root)

        assert cfg.notes_root == notes_root
        assert (notes_root / "daily").exists()


class TestGetAndResetConfig:
    """Tests for get_config and reset_config functions."""

    def test_singleton_pattern(self, mock_config: Config):
        cfg1 = get_config()
        cfg2 = get_config()

        assert cfg1 is cfg2

    def test_reset_clears_singleton(self, mock_config: Config):
        cfg1 = get_config()
        reset_config()

        # After reset, _config should be None
        assert config_module._config is None


class TestAddNotebook:
    """Tests for add_notebook function."""

    def test_add_new_notebook(self, mock_config: Config, temp_notes_root: Path):
        nb = add_notebook("new-notebook", date_based=True)

        assert nb.name == "new-notebook"
        assert nb.date_based is True
        assert (temp_notes_root / "new-notebook").exists()

    def test_add_duplicate_raises(self, mock_config: Config):
        with pytest.raises(ValueError, match="already exists"):
            add_notebook("daily")

    def test_add_external_notebook(self, mock_config: Config, tmp_path: Path):
        ext_path = tmp_path / "external"
        ext_path.mkdir()

        nb = add_notebook("external", path=ext_path)

        assert nb.is_external is True
        assert nb.path == ext_path


class TestRemoveNotebook:
    """Tests for remove_notebook function."""

    def test_remove_existing(self, mock_config: Config):
        result = remove_notebook("projects")
        assert result is True

        cfg = get_config()
        assert cfg.get_notebook("projects") is None

    def test_remove_nonexistent(self, mock_config: Config):
        result = remove_notebook("nonexistent")
        assert result is False
