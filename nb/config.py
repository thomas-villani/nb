"""Configuration management for nb."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class NotebookConfig:
    """Configuration for a notebook."""

    name: str
    date_based: bool = False  # If True, uses YYYY/Week/YYYY-MM-DD.md structure
    todo_exclude: bool = False  # If True, exclude from `nb todo` by default
    path: Path | None = None  # External path (None = inside notes_root)

    @property
    def is_external(self) -> bool:
        """Check if this notebook is external (outside notes_root)."""
        return self.path is not None


@dataclass
class LinkedTodoConfig:
    """Configuration for a linked external todo file."""

    path: Path
    alias: str
    sync: bool = True


@dataclass
class LinkedNoteConfig:
    """Configuration for a linked external note file or directory."""

    path: Path
    alias: str
    notebook: str | None = None  # Virtual notebook name (defaults to alias)
    recursive: bool = True  # For directories, scan recursively


@dataclass
class EmbeddingsConfig:
    """Configuration for embedding generation (localvectordb)."""

    provider: str = "ollama"  # "ollama" or "openai"
    model: str = "nomic-embed-text"
    base_url: str | None = None  # For custom Ollama endpoint
    api_key: str | None = None  # For OpenAI


@dataclass
class Config:
    """Application configuration."""

    notes_root: Path
    editor: str
    notebooks: list[NotebookConfig] = field(
        default_factory=lambda: [
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
            NotebookConfig(name="work", date_based=False),
            NotebookConfig(name="personal", date_based=False),
        ]
    )
    linked_todos: list[LinkedTodoConfig] = field(default_factory=list)
    linked_notes: list[LinkedNoteConfig] = field(default_factory=list)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    date_format: str = "%Y-%m-%d"
    time_format: str = "%H:%M"

    def get_notebook(self, name: str) -> NotebookConfig | None:
        """Get a notebook configuration by name."""
        for nb in self.notebooks:
            if nb.name == name:
                return nb
        return None

    def notebook_names(self) -> list[str]:
        """Get list of notebook names."""
        return [nb.name for nb in self.notebooks]

    def excluded_notebooks(self) -> list[str]:
        """Get list of notebooks excluded from todo by default."""
        return [nb.name for nb in self.notebooks if nb.todo_exclude]

    def get_notebook_path(self, name: str) -> Path | None:
        """Get the filesystem path for a notebook.

        For internal notebooks, returns notes_root/name.
        For external notebooks, returns the configured path.
        Returns None if notebook doesn't exist.
        """
        nb = self.get_notebook(name)
        if nb is None:
            return None
        if nb.path is not None:
            return nb.path
        return self.notes_root / name

    def external_notebooks(self) -> list[NotebookConfig]:
        """Get list of external notebooks."""
        return [nb for nb in self.notebooks if nb.is_external]

    @property
    def nb_dir(self) -> Path:
        """Return path to .nb configuration directory."""
        return self.notes_root / ".nb"

    @property
    def db_path(self) -> Path:
        """Return path to SQLite database."""
        return self.nb_dir / "index.db"

    @property
    def config_path(self) -> Path:
        """Return path to config file."""
        return self.nb_dir / "config.yaml"

    @property
    def vectors_path(self) -> Path:
        """Return path to localvectordb vectors directory."""
        return self.nb_dir / "vectors"

    @property
    def attachments_path(self) -> Path:
        """Return path to attachments directory."""
        return self.nb_dir / "attachments"


# Default configuration values
DEFAULT_NOTES_ROOT = Path.home() / "notes"
DEFAULT_EDITOR = "micro"

DEFAULT_CONFIG_YAML = """\
# nb configuration
# See: https://github.com/user/nb-cli

# Root directory for all notes
notes_root: ~/notes

# Editor to use (uses $EDITOR if set, otherwise this value)
editor: micro

# Notebook directories (created under notes_root)
# Set date_based: true to use YYYY/Week/YYYY-MM-DD.md structure
# Set todo_exclude: true to exclude from `nb todo` by default
# Set path: to use an external directory as a notebook
notebooks:
  - name: daily
    date_based: true     # Uses date-organized structure
  - name: projects
    date_based: false
  - name: work
    date_based: true
  - name: personal
    date_based: true
    todo_exclude: true
  # External notebook example:
  # - name: obsidian
  #   path: ~/Documents/Obsidian/vault
  #   date_based: false

# Linked external todo files (optional)
# linked_todos:
#   - path: ~/code/myproject/TODO.md
#     alias: myproject
#     sync: true

# Linked external note files or directories (optional)
# linked_notes:
#   - path: ~/docs/wiki
#     alias: wiki
#     notebook: wiki        # Virtual notebook name
#     recursive: true       # Scan subdirectories
#   - path: ~/code/project/docs/design.md
#     alias: project-design

# Embedding configuration for semantic search
embeddings:
  provider: ollama    # "ollama" or "openai"
  model: nomic-embed-text
  # base_url: http://localhost:11434  # Optional: custom Ollama endpoint
  # api_key: null  # Required for OpenAI

# Date/time display formats
date_format: "%Y-%m-%d"
time_format: "%H:%M"
"""


def expand_path(path: str | Path) -> Path:
    """Expand ~ and environment variables in a path."""
    path_str = str(path)
    # Expand environment variables
    path_str = os.path.expandvars(path_str)
    # Expand ~
    return Path(path_str).expanduser()


def get_default_notes_root() -> Path:
    """Get the default notes root directory."""
    # Check environment variable first
    env_root = os.environ.get("NB_NOTES_ROOT")
    if env_root:
        return expand_path(env_root)
    return DEFAULT_NOTES_ROOT


def get_config_path(notes_root: Path | None = None) -> Path:
    """Get the path to the config file."""
    if notes_root is None:
        notes_root = get_default_notes_root()
    return notes_root / ".nb" / "config.yaml"


def _parse_notebooks(data: list[Any]) -> list[NotebookConfig]:
    """Parse notebooks configuration.

    Supports both old format (list of strings) and new format (list of dicts).
    External notebooks can specify a path outside notes_root.
    """
    result = []
    for item in data:
        if isinstance(item, str):
            # Old format: just a string name
            # "daily" is date-based by default for backwards compatibility
            result.append(NotebookConfig(name=item, date_based=(item == "daily")))
        elif isinstance(item, dict):
            # New format: dict with name and optional settings
            ext_path = None
            if "path" in item:
                ext_path = expand_path(item["path"])
            result.append(
                NotebookConfig(
                    name=item["name"],
                    date_based=item.get("date_based", False),
                    todo_exclude=item.get("todo_exclude", False),
                    path=ext_path,
                )
            )
    return result


def _parse_linked_todos(data: list[dict[str, Any]]) -> list[LinkedTodoConfig]:
    """Parse linked_todos configuration."""
    result = []
    for item in data:
        result.append(
            LinkedTodoConfig(
                path=expand_path(item["path"]),
                alias=item["alias"],
                sync=item.get("sync", True),
            )
        )
    return result


def _parse_linked_notes(data: list[dict[str, Any]]) -> list[LinkedNoteConfig]:
    """Parse linked_notes configuration."""
    result = []
    for item in data:
        result.append(
            LinkedNoteConfig(
                path=expand_path(item["path"]),
                alias=item["alias"],
                notebook=item.get("notebook"),
                recursive=item.get("recursive", True),
            )
        )
    return result


def _parse_embeddings(data: dict[str, Any] | None) -> EmbeddingsConfig:
    """Parse embeddings configuration."""
    if data is None:
        return EmbeddingsConfig()
    return EmbeddingsConfig(
        provider=data.get("provider", "ollama"),
        model=data.get("model", "nomic-embed-text"),
        base_url=data.get("base_url"),
        api_key=data.get("api_key"),
    )


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file.

    If config file doesn't exist, creates default configuration.
    """
    if config_path is None:
        config_path = get_config_path()

    # If config doesn't exist, try to find notes_root from default location
    if not config_path.exists():
        # Check if we should create default config
        notes_root = get_default_notes_root()
        config_path = notes_root / ".nb" / "config.yaml"

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Parse configuration with defaults
    notes_root = expand_path(data.get("notes_root", DEFAULT_NOTES_ROOT))

    # Get editor: prefer $EDITOR environment variable
    editor = os.environ.get("EDITOR") or data.get("editor", DEFAULT_EDITOR)

    # Parse notebooks (supports both old string format and new dict format)
    raw_notebooks = data.get("notebooks", ["daily", "projects", "work", "personal"])
    notebooks = _parse_notebooks(raw_notebooks)

    linked_todos = _parse_linked_todos(data.get("linked_todos", []))
    linked_notes = _parse_linked_notes(data.get("linked_notes", []))
    embeddings = _parse_embeddings(data.get("embeddings"))
    date_format = data.get("date_format", "%Y-%m-%d")
    time_format = data.get("time_format", "%H:%M")

    return Config(
        notes_root=notes_root,
        editor=editor,
        notebooks=notebooks,
        linked_todos=linked_todos,
        linked_notes=linked_notes,
        embeddings=embeddings,
        date_format=date_format,
        time_format=time_format,
    )


def save_config(config: Config) -> None:
    """Save configuration to YAML file."""
    # Build embeddings dict, excluding None values
    embeddings_data = {
        "provider": config.embeddings.provider,
        "model": config.embeddings.model,
    }
    if config.embeddings.base_url:
        embeddings_data["base_url"] = config.embeddings.base_url
    if config.embeddings.api_key:
        embeddings_data["api_key"] = config.embeddings.api_key

    # Build notebook list with optional fields
    notebooks_data = []
    for nb in config.notebooks:
        nb_dict: dict[str, Any] = {
            "name": nb.name,
            "date_based": nb.date_based,
        }
        if nb.todo_exclude:
            nb_dict["todo_exclude"] = True
        if nb.path is not None:
            nb_dict["path"] = str(nb.path)
        notebooks_data.append(nb_dict)

    data = {
        "notes_root": str(config.notes_root),
        "editor": config.editor,
        "notebooks": notebooks_data,
        "linked_todos": [
            {"path": str(lt.path), "alias": lt.alias, "sync": lt.sync}
            for lt in config.linked_todos
        ],
        "linked_notes": [
            {
                "path": str(ln.path),
                "alias": ln.alias,
                "notebook": ln.notebook,
                "recursive": ln.recursive,
            }
            for ln in config.linked_notes
        ],
        "embeddings": embeddings_data,
        "date_format": config.date_format,
        "time_format": config.time_format,
    }

    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config.config_path, "w", encoding="utf-8") as f:
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
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG_YAML)

    # Load and ensure directories
    config = load_config(config_path)
    ensure_directories(config)

    return config


def add_notebook(
    name: str,
    date_based: bool = False,
    todo_exclude: bool = False,
    path: Path | None = None,
) -> NotebookConfig:
    """Add a new notebook to the configuration.

    Args:
        name: Name of the notebook
        date_based: Whether to use date-based organization
        todo_exclude: Whether to exclude from nb todo by default
        path: External path (None for internal notebook)

    Returns:
        The created NotebookConfig

    Raises:
        ValueError: If notebook name already exists
    """
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
    config = get_config()

    for i, nb in enumerate(config.notebooks):
        if nb.name == name:
            config.notebooks.pop(i)
            save_config(config)
            return True

    return False


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
