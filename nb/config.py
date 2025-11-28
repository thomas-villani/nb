"""Configuration management for nb."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LinkedTodoConfig:
    """Configuration for a linked external todo file."""

    path: Path
    alias: str
    sync: bool = True


@dataclass
class Config:
    """Application configuration."""

    notes_root: Path
    editor: str
    notebooks: list[str] = field(
        default_factory=lambda: ["daily", "projects", "work", "personal"]
    )
    linked_todos: list[LinkedTodoConfig] = field(default_factory=list)
    date_format: str = "%Y-%m-%d"
    time_format: str = "%H:%M"

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
notebooks:
  - daily      # Special: date-organized daily notes
  - projects
  - work
  - personal

# Linked external todo files (optional)
# linked_todos:
#   - path: ~/code/myproject/TODO.md
#     alias: myproject
#     sync: true

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

    notebooks = data.get("notebooks", ["daily", "projects", "work", "personal"])
    linked_todos = _parse_linked_todos(data.get("linked_todos", []))
    date_format = data.get("date_format", "%Y-%m-%d")
    time_format = data.get("time_format", "%H:%M")

    return Config(
        notes_root=notes_root,
        editor=editor,
        notebooks=notebooks,
        linked_todos=linked_todos,
        date_format=date_format,
        time_format=time_format,
    )


def save_config(config: Config) -> None:
    """Save configuration to YAML file."""
    data = {
        "notes_root": str(config.notes_root),
        "editor": config.editor,
        "notebooks": config.notebooks,
        "linked_todos": [
            {"path": str(lt.path), "alias": lt.alias, "sync": lt.sync}
            for lt in config.linked_todos
        ],
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

    # Create notebook directories
    for notebook in config.notebooks:
        notebook_path = config.notes_root / notebook
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
