"""Configuration I/O functions for nb."""

from __future__ import annotations

import os
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import (
    DEFAULT_CONFIG_YAML,
    DEFAULT_EDITOR,
    ClipConfig,
    Config,
    GitConfig,
    InboxConfig,
    LLMConfig,
    LLMModelConfig,
    NotebookConfig,
    RaindropConfig,
    RecorderConfig,
)
from .parsers import (
    _parse_clip_config,
    _parse_embeddings,
    _parse_git_config,
    _parse_inbox_config,
    _parse_kanban_boards,
    _parse_llm_config,
    _parse_notebooks,
    _parse_recorder_config,
    _parse_search,
    _parse_todo_config,
    _parse_todo_views,
    expand_path,
    get_config_path,
    get_default_notes_root,
)


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file.

    If config file doesn't exist, creates default configuration.

    Environment variables are loaded in this priority order (first wins):
    1. Shell environment variables (already set before nb runs)
    2. Custom env_file specified in config (if set)
    3. Default .nb/.env file

    API keys are ONLY loaded from environment variables, never from config.
    """
    if config_path is None:
        config_path = get_config_path()

    # If config doesn't exist, try to find notes_root from default location
    if not config_path.exists():
        # Check if we should create default config
        notes_root = get_default_notes_root()
        config_path = notes_root / ".nb" / "config.yaml"

    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Parse configuration with defaults
    # If notes_root not in config file, respect NB_NOTES_ROOT env var via get_default_notes_root()
    if "notes_root" in data:
        notes_root = expand_path(data["notes_root"])
    else:
        notes_root = get_default_notes_root()

    # Load environment variables from .env files (for API keys etc.)
    # Priority: shell env vars > custom env_file > default .nb/.env
    # Using override=False means existing env vars are NOT overwritten
    custom_env_file: Path | None = None
    if "env_file" in data:
        custom_env_file = expand_path(data["env_file"])
        if custom_env_file.exists():
            load_dotenv(custom_env_file, override=False)

    # Also load default .nb/.env (won't override vars already set)
    default_env_file = notes_root / ".nb" / ".env"
    if default_env_file.exists():
        load_dotenv(default_env_file, override=False)

    # Get editor: prefer $EDITOR environment variable
    editor = os.environ.get("EDITOR") or data.get("editor", DEFAULT_EDITOR)

    # Parse notebooks (supports both old string format and new dict format)
    raw_notebooks = data.get("notebooks", ["daily", "projects", "work", "personal"])
    notebooks = _parse_notebooks(raw_notebooks)

    # Note: linked_todos and linked_notes are stored in the database, not config
    todo_views = _parse_todo_views(data.get("todo_views", []))
    kanban_boards = _parse_kanban_boards(data.get("kanban_boards", []))
    embeddings = _parse_embeddings(data.get("embeddings"))
    search = _parse_search(data.get("search"))
    todo_config = _parse_todo_config(data.get("todo"))
    recorder_config = _parse_recorder_config(data.get("recorder"))
    clip_config = _parse_clip_config(data.get("clip"))
    inbox_config = _parse_inbox_config(data.get("inbox"))
    git_config = _parse_git_config(data.get("git"))
    llm_config = _parse_llm_config(data.get("llm"))
    date_format = data.get("date_format", "%Y-%m-%d")
    time_format = data.get("time_format", "%H:%M")
    daily_title_format = data.get("daily_title_format", "%A, %B %d, %Y")
    week_start_day = data.get("week_start_day", "monday")

    return Config(
        notes_root=notes_root,
        editor=editor,
        env_file=custom_env_file,
        notebooks=notebooks,
        todo_views=todo_views,
        kanban_boards=kanban_boards,
        embeddings=embeddings,
        search=search,
        todo=todo_config,
        recorder=recorder_config,
        clip=clip_config,
        inbox=inbox_config,
        git=git_config,
        llm=llm_config,
        date_format=date_format,
        time_format=time_format,
        daily_title_format=daily_title_format,
        week_start_day=week_start_day,
    )


def _serialize_dataclass_fields(
    obj: Any,
    defaults: Any | None = None,
    exclude: set[str] | None = None,
    include_none: bool = False,
) -> dict[str, Any]:
    """Serialize a dataclass to a dict using field introspection.

    Args:
        obj: The dataclass instance to serialize.
        defaults: Optional defaults instance to compare against. If provided,
            only fields that differ from defaults will be included.
        exclude: Set of field names to exclude from serialization.
        include_none: If False (default), exclude None values.

    Returns:
        Dictionary of field names to values.

    """
    if not is_dataclass(obj):
        raise TypeError(f"{obj} is not a dataclass instance")

    exclude = exclude or set()
    result: dict[str, Any] = {}

    for _field in fields(obj):
        if _field.name in exclude:
            continue

        value = getattr(obj, _field.name)

        # Skip None values unless explicitly included
        if value is None and not include_none:
            continue

        # Compare with defaults if provided
        if defaults is not None:
            default_value = getattr(defaults, _field.name, None)
            if value == default_value:
                continue

        # Convert Path to string
        if isinstance(value, Path):
            value = str(value)

        result[_field.name] = value

    return result


def _serialize_notebook(nb: NotebookConfig) -> dict[str, Any]:
    """Serialize a NotebookConfig to a dict.

    Always includes: name, date_based
    Conditionally includes: todo_exclude (if True), path, color, icon, template (if not None)

    """
    result: dict[str, Any] = {
        "name": nb.name,
        "date_based": nb.date_based,
    }
    if nb.todo_exclude:
        result["todo_exclude"] = True
    if nb.path is not None:
        result["path"] = str(nb.path)
    if nb.color is not None:
        result["color"] = nb.color
    if nb.icon is not None:
        result["icon"] = nb.icon
    if nb.template is not None:
        result["template"] = nb.template
    return result


def save_config(config: Config) -> None:
    """Save configuration to YAML file.

    This function serializes the Config dataclass to YAML. When adding new fields
    to Config or its nested dataclasses, ensure they are handled here.

    Serialization strategies:
    - embeddings, todo: All fields serialized (use _serialize_dataclass_fields)
    - search: All fields except serper_api_key (use env var for security)
    - recorder: Only non-default values, excluding deepgram_api_key (security)
    - clip: Only non-default values (compare with defaults instance)
    - inbox: Only non-default values, with nested raindrop config
    - notebooks: Custom serialization via _serialize_notebook
    - Security: API key fields are NOT saved (use environment variables)

    """
    # Notebooks: custom serialization with conditional fields
    notebooks_data = [_serialize_notebook(nb) for nb in config.notebooks]

    # Embeddings: all fields except None, with special handling for api_key
    embeddings_data = _serialize_dataclass_fields(config.embeddings)

    # Search: all fields except api_key (use env var for security)
    search_data = _serialize_dataclass_fields(config.search, exclude={"serper_api_key"})

    # Todo: all fields
    todo_data = _serialize_dataclass_fields(config.todo)

    # Recorder: only non-default values, exclude api_key (use env var for security)
    recorder_defaults = RecorderConfig()
    recorder_data = _serialize_dataclass_fields(
        config.recorder, defaults=recorder_defaults, exclude={"deepgram_api_key"}
    )

    # Clip: only non-default values
    clip_defaults = ClipConfig()
    clip_data = _serialize_dataclass_fields(config.clip, defaults=clip_defaults)

    # Inbox: only non-default values, with nested raindrop config
    inbox_data: dict[str, Any] = {}
    inbox_defaults = InboxConfig()
    if config.inbox.source != inbox_defaults.source:
        inbox_data["source"] = config.inbox.source
    if config.inbox.default_notebook != inbox_defaults.default_notebook:
        inbox_data["default_notebook"] = config.inbox.default_notebook
    if config.inbox.auto_summarize != inbox_defaults.auto_summarize:
        inbox_data["auto_summarize"] = config.inbox.auto_summarize

    # Raindrop sub-config (exclude api_token for security - use env var)
    raindrop_defaults = RaindropConfig()
    raindrop_data = _serialize_dataclass_fields(
        config.inbox.raindrop, defaults=raindrop_defaults, exclude={"api_token"}
    )
    if raindrop_data:
        inbox_data["raindrop"] = raindrop_data

    # Git: only non-default values
    git_defaults = GitConfig()
    git_data = _serialize_dataclass_fields(config.git, defaults=git_defaults)

    # LLM: only non-default values, exclude api_key (use env var)
    llm_data: dict[str, Any] = {}
    llm_defaults = LLMConfig()
    if config.llm.provider != llm_defaults.provider:
        llm_data["provider"] = config.llm.provider
    if config.llm.base_url:
        llm_data["base_url"] = config.llm.base_url
    if config.llm.max_tokens != llm_defaults.max_tokens:
        llm_data["max_tokens"] = config.llm.max_tokens
    if config.llm.temperature != llm_defaults.temperature:
        llm_data["temperature"] = config.llm.temperature
    if config.llm.system_prompt:
        llm_data["system_prompt"] = config.llm.system_prompt
    # Serialize models config (only non-default values)
    models_defaults = LLMModelConfig()
    models_data: dict[str, Any] = {}
    if config.llm.models.smart != models_defaults.smart:
        models_data["smart"] = config.llm.models.smart
    if config.llm.models.fast != models_defaults.fast:
        models_data["fast"] = config.llm.models.fast
    if models_data:
        llm_data["models"] = models_data

    # Build main config dict
    # Note: linked_todos and linked_notes are stored in the database, not config
    data: dict[str, Any] = {
        "notes_root": str(config.notes_root),
        "editor": config.editor,
    }

    # Include env_file only if custom path is set
    if config.env_file is not None:
        data["env_file"] = str(config.env_file)

    data.update(
        {
            "notebooks": notebooks_data,
            "todo_views": [
                {"name": view.name, "filters": view.filters}
                for view in config.todo_views
            ],
            "kanban_boards": [
                {
                    "name": board.name,
                    "columns": [
                        {"name": col.name, "filters": col.filters, "color": col.color}
                        for col in board.columns
                    ],
                }
                for board in config.kanban_boards
            ],
            "embeddings": embeddings_data,
            "search": search_data,
            "todo": todo_data,
            "date_format": config.date_format,
            "time_format": config.time_format,
            "daily_title_format": config.daily_title_format,
            "week_start_day": config.week_start_day,
        }
    )

    # Only include optional configs if they have non-default settings
    if recorder_data:
        data["recorder"] = recorder_data
    if clip_data:
        data["clip"] = clip_data
    if inbox_data:
        data["inbox"] = inbox_data
    if git_data:
        data["git"] = git_data
    if llm_data:
        data["llm"] = llm_data

    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    with config.config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def ensure_directories(config: Config) -> None:
    """Create required directories if they don't exist."""
    # Create .nb directory
    config.nb_dir.mkdir(parents=True, exist_ok=True)

    # Create notebook directories (skip external notebooks)
    for nb in config.notebooks:
        if nb.is_external:
            continue  # External notebooks manage their own directories
        notebook_path = config.notes_root / nb.name
        notebook_path.mkdir(parents=True, exist_ok=True)


def init_config(notes_root: Path | None = None) -> Config:
    """Initialize configuration for first-time setup.

    Creates default config file and directory structure.
    """
    if notes_root is None:
        notes_root = get_default_notes_root()

    nb_dir = notes_root / ".nb"
    config_path = nb_dir / "config.yaml"

    # Create directories
    nb_dir.mkdir(parents=True, exist_ok=True)

    # Write default config if it doesn't exist
    if not config_path.exists():
        # Parse default config and update notes_root to the actual path
        # This ensures NB_NOTES_ROOT is respected in the generated config
        default_data = yaml.safe_load(DEFAULT_CONFIG_YAML)
        default_data["notes_root"] = str(notes_root)
        with config_path.open("w", encoding="utf-8") as f:
            # Write header comment
            f.write("# nb configuration\n")
            f.write("# See: https://github.com/thomas-villani/nb-cli\n\n")
            yaml.safe_dump(default_data, f, default_flow_style=False, sort_keys=False)

    # Load and ensure directories
    config = load_config(config_path)
    ensure_directories(config)

    return config


def add_notebook(
    name: str,
    date_based: bool = False,
    todo_exclude: bool = False,
    path: Path | None = None,
    color: str | None = None,
    icon: str | None = None,
) -> NotebookConfig:
    """Add a new notebook to the configuration.

    Args:
        name: Name of the notebook
        date_based: Whether to use date-based organization
        todo_exclude: Whether to exclude from nb todo by default
        path: External path (None for internal notebook)
        color: Display color for the notebook
        icon: Display icon/emoji for the notebook

    Returns:
        The created NotebookConfig

    Raises:
        ValueError: If notebook name already exists

    """
    # Import here to avoid circular imports
    from . import get_config

    config = get_config()

    # Check if notebook already exists
    if config.get_notebook(name) is not None:
        raise ValueError(f"Notebook '{name}' already exists")

    # Create the notebook config
    nb = NotebookConfig(
        name=name,
        date_based=date_based,
        todo_exclude=todo_exclude,
        path=path,
        color=color,
        icon=icon,
    )

    # Add to config and save
    config.notebooks.append(nb)
    save_config(config)

    # Create directory for internal notebooks
    if not nb.is_external:
        notebook_path = config.notes_root / name
        notebook_path.mkdir(parents=True, exist_ok=True)

    return nb


def remove_notebook(name: str) -> bool:
    """Remove a notebook from the configuration.

    Note: This only removes the configuration, not the files.

    Args:
        name: Name of the notebook to remove

    Returns:
        True if removed, False if not found

    """
    # Import here to avoid circular imports
    from . import get_config

    config = get_config()

    for i, nb in enumerate(config.notebooks):
        if nb.name == name:
            config.notebooks.pop(i)
            save_config(config)
            return True

    return False
