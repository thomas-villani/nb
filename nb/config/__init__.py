"""Configuration management for nb.

This package provides configuration loading, saving, and management for the nb CLI.
The main entry points are:
- get_config(): Get the global configuration instance
- reset_config(): Clear the cached configuration
- load_config(): Load configuration from file
- save_config(): Save configuration to file
"""

from __future__ import annotations

# Re-export I/O functions
from .io import (
    # Internal I/O functions (exported for testing)
    _serialize_dataclass_fields,
    add_notebook,
    ensure_directories,
    init_config,
    load_config,
    remove_notebook,
    save_config,
)

# Re-export models
from .models import (
    DEFAULT_CONFIG_YAML,
    DEFAULT_EDITOR,
    DEFAULT_KANBAN_COLUMNS,
    DEFAULT_NOTES_ROOT,
    ClipConfig,
    Config,
    EmbeddingsConfig,
    GitConfig,
    InboxConfig,
    KanbanBoardConfig,
    KanbanColumnConfig,
    LinkedNoteConfig,
    LinkedTodoConfig,
    LLMConfig,
    LLMModelConfig,
    NotebookConfig,
    RaindropConfig,
    RecorderConfig,
    SearchConfig,
    TodoConfig,
    TodoViewConfig,
)

# Re-export parsers
from .parsers import (
    # Internal parser functions (exported for testing)
    _parse_embeddings,
    _parse_inbox_config,
    _parse_llm_config,
    _parse_notebooks,
    _parse_raindrop_config,
    _parse_recorder_config,
    expand_path,
    get_config_path,
    get_default_notes_root,
)

# Re-export utilities
from .utils import (
    BOOL_FALSE_VALUES,
    BOOL_TRUE_VALUES,
    CONFIGURABLE_SETTINGS,
    EMOJI_ALIASES,
    NOTEBOOK_SETTINGS,
    VALID_COLORS,
    get_config_value,
    is_valid_color,
    list_config_settings,
    parse_bool_strict,
    resolve_emoji,
    set_config_value,
)

# Singleton config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance.

    Loads config on first call, returns cached instance thereafter.
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset the cached configuration (useful for testing)."""
    global _config
    _config = None


__all__ = [
    # Utilities
    "BOOL_FALSE_VALUES",
    "BOOL_TRUE_VALUES",
    "CONFIGURABLE_SETTINGS",
    "DEFAULT_CONFIG_YAML",
    "DEFAULT_EDITOR",
    "DEFAULT_KANBAN_COLUMNS",
    "DEFAULT_NOTES_ROOT",
    "EMOJI_ALIASES",
    "NOTEBOOK_SETTINGS",
    "VALID_COLORS",
    # Models
    "ClipConfig",
    "Config",
    "EmbeddingsConfig",
    "GitConfig",
    "InboxConfig",
    "KanbanBoardConfig",
    "KanbanColumnConfig",
    "LLMConfig",
    "LLMModelConfig",
    "LinkedNoteConfig",
    "LinkedTodoConfig",
    "NotebookConfig",
    "RaindropConfig",
    "RecorderConfig",
    "SearchConfig",
    "TodoConfig",
    "TodoViewConfig",
    "_parse_embeddings",
    "_parse_inbox_config",
    "_parse_llm_config",
    "_parse_notebooks",
    "_parse_raindrop_config",
    "_parse_recorder_config",
    "_serialize_dataclass_fields",
    # I/O
    "add_notebook",
    "ensure_directories",
    # Parsers
    "expand_path",
    # Singleton
    "get_config",
    "get_config_path",
    "get_config_value",
    "get_default_notes_root",
    "init_config",
    "is_valid_color",
    "list_config_settings",
    "load_config",
    "parse_bool_strict",
    "remove_notebook",
    "reset_config",
    "resolve_emoji",
    "save_config",
    "set_config_value",
]
