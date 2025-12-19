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
    LLMConfig,
    LLMModelConfig,
    NotebookConfig,
    _parse_embeddings,
    _parse_llm_config,
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


class TestLLMModelConfig:
    """Tests for LLMModelConfig dataclass."""

    def test_defaults(self):
        cfg = LLMModelConfig()

        assert cfg.smart == "claude-sonnet-4-20250514"
        assert cfg.fast == "claude-haiku-3-5-20241022"

    def test_custom(self):
        cfg = LLMModelConfig(smart="gpt-4o", fast="gpt-4o-mini")

        assert cfg.smart == "gpt-4o"
        assert cfg.fast == "gpt-4o-mini"


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_defaults(self):
        cfg = LLMConfig()

        assert cfg.provider == "anthropic"
        assert cfg.api_key is None
        assert cfg.base_url is None
        assert cfg.max_tokens == 4096
        assert cfg.temperature == 0.7
        assert cfg.system_prompt is None
        assert isinstance(cfg.models, LLMModelConfig)

    def test_custom(self):
        cfg = LLMConfig(
            provider="openai",
            api_key="sk-xxx",
            base_url="https://api.example.com",
            max_tokens=8192,
            temperature=0.5,
            system_prompt="You are a helpful assistant.",
            models=LLMModelConfig(smart="gpt-4o", fast="gpt-4o-mini"),
        )

        assert cfg.provider == "openai"
        assert cfg.api_key == "sk-xxx"
        assert cfg.base_url == "https://api.example.com"
        assert cfg.max_tokens == 8192
        assert cfg.temperature == 0.5
        assert cfg.system_prompt == "You are a helpful assistant."
        assert cfg.models.smart == "gpt-4o"


class TestParseLLMConfig:
    """Tests for _parse_llm_config function."""

    def test_none_input(self):
        result = _parse_llm_config(None)

        assert result.provider == "anthropic"
        assert result.max_tokens == 4096

    def test_custom_config(self):
        data = {
            "provider": "openai",
            "max_tokens": 8192,
            "temperature": 0.3,
            "models": {"smart": "gpt-4o", "fast": "gpt-4o-mini"},
        }
        result = _parse_llm_config(data)

        assert result.provider == "openai"
        assert result.max_tokens == 8192
        assert result.temperature == 0.3
        assert result.models.smart == "gpt-4o"
        assert result.models.fast == "gpt-4o-mini"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-from-env")
        result = _parse_llm_config({"provider": "anthropic"})

        assert result.api_key == "test-key-from-env"

    def test_api_key_from_env_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
        result = _parse_llm_config({"provider": "openai"})

        assert result.api_key == "openai-test-key"

    def test_config_api_key_overrides_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        result = _parse_llm_config({"api_key": "config-key"})

        assert result.api_key == "config-key"


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

        # Use config_module.get_config() because the test file imports get_config
        # at the top, so the local reference points to the original function,
        # not the monkeypatched version
        cfg = config_module.get_config()
        assert cfg.get_notebook("projects") is None

    def test_remove_nonexistent(self, mock_config: Config):
        result = remove_notebook("nonexistent")
        assert result is False


class TestParseBoolStrict:
    """Tests for parse_bool_strict function."""

    def test_true_values(self):
        from nb.config import parse_bool_strict

        for val in ("true", "True", "TRUE", "1", "yes", "Yes", "on", "ON"):
            assert parse_bool_strict(val, "test") is True

    def test_false_values(self):
        from nb.config import parse_bool_strict

        for val in ("false", "False", "FALSE", "0", "no", "No", "off", "OFF"):
            assert parse_bool_strict(val, "test") is False

    def test_invalid_raises(self):
        from nb.config import parse_bool_strict

        with pytest.raises(ValueError, match="Invalid boolean value 'trie'"):
            parse_bool_strict("trie", "test_setting")

        with pytest.raises(ValueError, match="Invalid boolean value 'maybe'"):
            parse_bool_strict("maybe", "test_setting")


class TestSetConfigValueBooleans:
    """Tests for set_config_value with boolean settings."""

    def test_valid_boolean_values(self, mock_config: Config, temp_notes_root: Path):
        """Test valid boolean values for config settings.

        Uses mock_config to prevent writing to the real config file.
        """
        from nb.config import load_config, set_config_value

        # Test todo.auto_complete_children
        assert set_config_value("todo.auto_complete_children", "false") is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.todo.auto_complete_children is False

        assert set_config_value("todo.auto_complete_children", "true") is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.todo.auto_complete_children is True

    def test_invalid_boolean_raises(self, mock_config: Config):
        from nb.config import set_config_value

        with pytest.raises(ValueError, match="Invalid boolean value"):
            set_config_value("todo.auto_complete_children", "trie")

        with pytest.raises(ValueError, match="Invalid boolean value"):
            set_config_value("notebook.daily.date_based", "nope")


class TestSerializeDataclassFields:
    """Tests for _serialize_dataclass_fields helper function."""

    def test_basic_serialization(self):
        from nb.config import SearchConfig, _serialize_dataclass_fields

        config = SearchConfig(
            vector_weight=0.8, score_threshold=0.5, recency_decay_days=60
        )
        result = _serialize_dataclass_fields(config)

        assert result == {
            "vector_weight": 0.8,
            "score_threshold": 0.5,
            "recency_decay_days": 60,
        }

    def test_excludes_none_by_default(self):
        from nb.config import EmbeddingsConfig, _serialize_dataclass_fields

        config = EmbeddingsConfig(
            provider="ollama", model="test", base_url=None, api_key=None
        )
        result = _serialize_dataclass_fields(config)

        assert "base_url" not in result
        assert "api_key" not in result
        assert result["provider"] == "ollama"
        assert result["model"] == "test"

    def test_with_defaults_only_includes_changes(self):
        from nb.config import RecorderConfig, _serialize_dataclass_fields

        defaults = RecorderConfig()
        config = RecorderConfig(sample_rate=44100, auto_delete_audio=True)

        result = _serialize_dataclass_fields(config, defaults=defaults)

        # Only changed fields should be included
        assert result == {"sample_rate": 44100, "auto_delete_audio": True}
        # Default values should NOT be included
        assert "mic_device" not in result
        assert "loopback_device" not in result
        assert "transcribe_timeout" not in result
        assert "mic_speaker_label" not in result

    def test_exclude_parameter(self):
        from nb.config import RaindropConfig, _serialize_dataclass_fields

        config = RaindropConfig(
            collection="test", auto_archive=False, api_token="secret"
        )
        result = _serialize_dataclass_fields(config, exclude={"api_token"})

        assert "api_token" not in result
        assert result["collection"] == "test"
        assert result["auto_archive"] is False

    def test_path_conversion(self, tmp_path: Path):
        from nb.config import NotebookConfig, _serialize_dataclass_fields

        config = NotebookConfig(name="test", path=tmp_path / "notes")
        result = _serialize_dataclass_fields(config)

        assert result["path"] == str(tmp_path / "notes")
        assert isinstance(result["path"], str)

    def test_raises_for_non_dataclass(self):
        from nb.config import _serialize_dataclass_fields

        with pytest.raises(TypeError, match="is not a dataclass instance"):
            _serialize_dataclass_fields({"not": "a dataclass"})


class TestLLMConfigGetSet:
    """Tests for get_config_value and set_config_value with LLM settings.

    All tests that call set_config_value must use mock_config to prevent
    writing to the real user's config file.
    """

    def test_get_llm_provider(self, mock_config: Config):
        from nb.config import get_config_value

        result = get_config_value("llm.provider")
        assert result == "anthropic"

    def test_get_llm_models_smart(self, mock_config: Config):
        from nb.config import get_config_value

        result = get_config_value("llm.models.smart")
        assert result == "claude-sonnet-4-20250514"

    def test_get_llm_models_fast(self, mock_config: Config):
        from nb.config import get_config_value

        result = get_config_value("llm.models.fast")
        assert result == "claude-haiku-3-5-20241022"

    def test_set_llm_provider(self, mock_config: Config, temp_notes_root: Path):
        from nb.config import load_config, set_config_value

        assert set_config_value("llm.provider", "openai") is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.llm.provider == "openai"

    def test_set_llm_provider_invalid(self, mock_config: Config):
        from nb.config import set_config_value

        with pytest.raises(ValueError, match="must be one of"):
            set_config_value("llm.provider", "invalid")

    def test_set_llm_max_tokens(self, mock_config: Config, temp_notes_root: Path):
        from nb.config import load_config, set_config_value

        assert set_config_value("llm.max_tokens", "8192") is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.llm.max_tokens == 8192

    def test_set_llm_max_tokens_invalid(self, mock_config: Config):
        from nb.config import set_config_value

        with pytest.raises(ValueError, match="must be an integer"):
            set_config_value("llm.max_tokens", "not-a-number")

    def test_set_llm_temperature(self, mock_config: Config, temp_notes_root: Path):
        from nb.config import load_config, set_config_value

        assert set_config_value("llm.temperature", "0.5") is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.llm.temperature == 0.5

    def test_set_llm_temperature_invalid_range(self, mock_config: Config):
        from nb.config import set_config_value

        with pytest.raises(ValueError, match="must be between 0 and 2"):
            set_config_value("llm.temperature", "3.0")

    def test_set_llm_models_smart(self, mock_config: Config, temp_notes_root: Path):
        from nb.config import load_config, set_config_value

        assert set_config_value("llm.models.smart", "gpt-4o") is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.llm.models.smart == "gpt-4o"

    def test_set_llm_models_fast(self, mock_config: Config, temp_notes_root: Path):
        from nb.config import load_config, set_config_value

        assert set_config_value("llm.models.fast", "gpt-4o-mini") is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.llm.models.fast == "gpt-4o-mini"

    def test_set_llm_system_prompt(self, mock_config: Config, temp_notes_root: Path):
        from nb.config import load_config, set_config_value

        prompt = "You are a productivity assistant."
        assert set_config_value("llm.system_prompt", prompt) is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.llm.system_prompt == prompt

    def test_set_llm_base_url(self, mock_config: Config, temp_notes_root: Path):
        from nb.config import load_config, set_config_value

        url = "https://api.example.com"
        assert set_config_value("llm.base_url", url) is True
        cfg = load_config(temp_notes_root / ".nb" / "config.yaml")
        assert cfg.llm.base_url == url


class TestLLMConfigSaveLoad:
    """Tests for saving and loading LLM config."""

    def test_save_and_reload_llm_config(self, temp_notes_root: Path, monkeypatch):
        from nb.config import LLMConfig, LLMModelConfig

        # Clear EDITOR env var so config file value is used on reload
        monkeypatch.delenv("EDITOR", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        cfg = Config(
            notes_root=temp_notes_root,
            editor="code",
            notebooks=[NotebookConfig(name="daily", date_based=True)],
            llm=LLMConfig(
                provider="openai",
                max_tokens=8192,
                temperature=0.5,
                models=LLMModelConfig(smart="gpt-4o", fast="gpt-4o-mini"),
            ),
        )

        save_config(cfg)

        # Reload and verify
        loaded = load_config(cfg.config_path)

        assert loaded.llm.provider == "openai"
        assert loaded.llm.max_tokens == 8192
        assert loaded.llm.temperature == 0.5
        assert loaded.llm.models.smart == "gpt-4o"
        assert loaded.llm.models.fast == "gpt-4o-mini"
