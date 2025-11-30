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
    color: str | None = None  # Display color (e.g., "blue", "green", "#ff5500")
    icon: str | None = None  # Display icon/emoji (e.g., "📝", "🔧")
    template: str | None = None  # Default template name for new notes

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
    todo_exclude: bool = (
        False  # Exclude todos from nb todo (unless explicitly requested)
    )
    sync: bool = True  # Sync todo completions back to source file


@dataclass
class EmbeddingsConfig:
    """Configuration for embedding generation (localvectordb)."""

    provider: str = "ollama"  # "ollama" or "openai"
    model: str = "nomic-embed-text"
    base_url: str | None = None  # For custom Ollama endpoint
    api_key: str | None = None  # For OpenAI


@dataclass
class TodoViewConfig:
    """Configuration for a saved todo view.

    Views store filter settings that can be applied when listing todos.
    """

    name: str
    filters: dict[str, Any] = field(default_factory=dict)
    # Filter keys supported:
    # - notebooks: list[str] - filter to specific notebooks
    # - notes: list[str] - filter to specific note paths
    # - exclude_notebooks: list[str] - exclude notebooks
    # - priority: int - filter by priority (1, 2, 3)
    # - tags: list[str] - filter by tags
    # - exclude_tags: list[str] - exclude tags
    # - due_today: bool - show only due today
    # - due_week: bool - show only due this week
    # - overdue: bool - show only overdue
    # - hide_later: bool - hide "DUE LATER" section
    # - hide_no_date: bool - hide "NO DUE DATE" section
    # - focus: bool - shorthand for hide_later + hide_no_date
    # - include_completed: bool - include completed todos


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
    todo_views: list[TodoViewConfig] = field(default_factory=list)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    date_format: str = "%Y-%m-%d"
    time_format: str = "%H:%M"

    def get_todo_view(self, name: str) -> TodoViewConfig | None:
        """Get a todo view configuration by name."""
        for view in self.todo_views:
            if view.name == name:
                return view
        return None

    def todo_view_names(self) -> list[str]:
        """Get list of todo view names."""
        return [view.name for view in self.todo_views]

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
# Set color: to customize display color (e.g., blue, green, #ff5500)
# Set icon: to add an emoji/icon prefix (e.g., 📝, 🔧)
notebooks:
  - name: daily
    date_based: true     # Uses date-organized structure
    icon: 📅
  - name: projects
    date_based: false
    color: cyan
    icon: 🔧
  - name: work
    date_based: true
    color: blue
  - name: personal
    date_based: true
    todo_exclude: true
    color: green
  # External notebook example:
  # - name: obsidian
  #   path: ~/Documents/Obsidian/vault
  #   date_based: false

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
                    color=item.get("color"),
                    icon=item.get("icon"),
                    template=item.get("template"),
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


def _parse_todo_views(data: list[dict[str, Any]]) -> list[TodoViewConfig]:
    """Parse todo_views configuration."""
    result = []
    for item in data:
        result.append(
            TodoViewConfig(
                name=item["name"],
                filters=item.get("filters", {}),
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

    # Parse notebooks (supports both old string format and new dict format)
    raw_notebooks = data.get("notebooks", ["daily", "projects", "work", "personal"])
    notebooks = _parse_notebooks(raw_notebooks)

    # Note: linked_todos and linked_notes are stored in the database, not config
    todo_views = _parse_todo_views(data.get("todo_views", []))
    embeddings = _parse_embeddings(data.get("embeddings"))
    date_format = data.get("date_format", "%Y-%m-%d")
    time_format = data.get("time_format", "%H:%M")

    return Config(
        notes_root=notes_root,
        editor=editor,
        notebooks=notebooks,
        todo_views=todo_views,
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
        if nb.color is not None:
            nb_dict["color"] = nb.color
        if nb.icon is not None:
            nb_dict["icon"] = nb.icon
        if nb.template is not None:
            nb_dict["template"] = nb.template
        notebooks_data.append(nb_dict)

    # Note: linked_todos and linked_notes are stored in the database, not config
    data = {
        "notes_root": str(config.notes_root),
        "editor": config.editor,
        "notebooks": notebooks_data,
        "todo_views": [
            {"name": view.name, "filters": view.filters} for view in config.todo_views
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


# Configurable settings with descriptions
CONFIGURABLE_SETTINGS = {
    "editor": "Text editor command (e.g., code, vim, micro)",
    "date_format": "Date display format (e.g., %Y-%m-%d)",
    "time_format": "Time display format (e.g., %H:%M)",
    "embeddings.provider": "Embeddings provider (ollama or openai)",
    "embeddings.model": "Embeddings model name (e.g., nomic-embed-text)",
    "embeddings.base_url": "Custom embeddings API endpoint URL",
    "embeddings.api_key": "API key for embeddings provider (OpenAI)",
}

# Notebook-specific settings (accessed via notebook.<name>.<setting>)
NOTEBOOK_SETTINGS = {
    "color": "Display color (e.g., blue, green, #ff5500)",
    "icon": "Display icon/emoji (e.g., 📝, 🔧, or name like 'wrench')",
    "date_based": "Use date-based organization (true/false)",
    "todo_exclude": "Exclude from nb todo by default (true/false)",
    "template": "Default template name for new notes",
}

# Map of emoji names to emoji characters for convenient CLI input
EMOJI_ALIASES = {
    # Common icons
    "calendar": "📅",
    "note": "📝",
    "notes": "📝",
    "book": "📕",
    "books": "📚",
    "folder": "📁",
    "file": "📄",
    # Tools
    "wrench": "🔧",
    "hammer": "🔨",
    "gear": "⚙️",
    "tools": "🛠️",
    # Status
    "star": "⭐",
    "check": "✅",
    "pin": "📌",
    "flag": "🚩",
    "bell": "🔔",
    # Categories
    "work": "💼",
    "home": "🏠",
    "personal": "👤",
    "idea": "💡",
    "bulb": "💡",
    # Activities
    "code": "💻",
    "computer": "💻",
    "rocket": "🚀",
    "target": "🎯",
    "brain": "🧠",
    # Nature/misc
    "sun": "☀️",
    "moon": "🌙",
    "fire": "🔥",
    "heart": "❤️",
    "sparkle": "✨",
}


def resolve_emoji(value: str) -> str:
    """Resolve an emoji alias to its character, or return as-is.

    Args:
        value: Either an emoji character or an alias name

    Returns:
        The emoji character (resolved from alias if applicable)

    """
    return EMOJI_ALIASES.get(value.lower(), value)


# Valid Rich color names (standard + bright variants)
VALID_COLORS = {
    # Standard colors
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    # Bright variants
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
    # Common aliases
    "grey",
    "gray",
    "purple",
    "orange",
    "pink",
}


def is_valid_color(color: str) -> bool:
    """Check if a color value is valid for Rich.

    Accepts:
    - Named colors (red, blue, cyan, etc.)
    - Hex colors (#ff5500, #f50)
    - RGB notation (rgb(255,85,0))

    """
    color_lower = color.lower()

    # Named color
    if color_lower in VALID_COLORS:
        return True

    # Hex color (#RGB or #RRGGBB)
    if color.startswith("#"):
        hex_part = color[1:]
        if len(hex_part) in (3, 6):
            try:
                int(hex_part, 16)
                return True
            except ValueError:
                pass

    # RGB notation
    if color_lower.startswith("rgb(") and color_lower.endswith(")"):
        return True  # Let Rich validate the exact format

    return False


def get_config_value(key: str) -> Any:
    """Get a config value by dot-notation key.

    Args:
        key: Configuration key (e.g., 'editor', 'embeddings.provider',
             'notebook.daily.color')

    Returns:
        The configuration value, or None if not found.

    """
    config = get_config()
    parts = key.split(".")

    if len(parts) == 1:
        # Top-level setting
        if key == "editor":
            return config.editor
        elif key == "date_format":
            return config.date_format
        elif key == "time_format":
            return config.time_format
        elif key == "notes_root":
            return str(config.notes_root)
    elif parts[0] == "embeddings" and len(parts) == 2:
        # Embeddings setting
        attr = parts[1]
        if hasattr(config.embeddings, attr):
            return getattr(config.embeddings, attr)
    elif parts[0] == "notebook" and len(parts) == 3:
        # Notebook-specific setting: notebook.<name>.<setting>
        nb_name, setting = parts[1], parts[2]
        nb = config.get_notebook(nb_name)
        if nb is not None and setting in NOTEBOOK_SETTINGS:
            return getattr(nb, setting, None)

    return None


def set_config_value(key: str, value: str) -> bool:
    """Set a config value by dot-notation key.

    Args:
        key: Configuration key (e.g., 'editor', 'embeddings.provider',
             'notebook.daily.color')
        value: Value to set (use empty string or 'none' to clear)

    Returns:
        True if successful, False if key not recognized.

    Raises:
        ValueError: If the value is invalid for the setting type.

    """
    config = get_config()
    parts = key.split(".")

    if len(parts) == 1:
        # Top-level setting
        if key == "editor":
            config.editor = value
        elif key == "date_format":
            config.date_format = value
        elif key == "time_format":
            config.time_format = value
        else:
            return False
    elif parts[0] == "embeddings" and len(parts) == 2:
        # Embeddings setting
        attr = parts[1]
        if attr in ("provider", "model", "base_url", "api_key"):
            setattr(config.embeddings, attr, value if value else None)
        else:
            return False
    elif parts[0] == "notebook" and len(parts) == 3:
        # Notebook-specific setting: notebook.<name>.<setting>
        nb_name, setting = parts[1], parts[2]
        nb = config.get_notebook(nb_name)
        if nb is None:
            raise ValueError(f"Notebook '{nb_name}' not found")
        if setting not in NOTEBOOK_SETTINGS:
            return False

        # Handle boolean settings
        if setting in ("date_based", "todo_exclude"):
            bool_value = value.lower() in ("true", "1", "yes")
            setattr(nb, setting, bool_value)
        elif setting == "color":
            # Validate and set color
            if value.lower() in ("", "none"):
                nb.color = None
            elif is_valid_color(value):
                nb.color = value
            else:
                valid = ", ".join(sorted(VALID_COLORS)[:10]) + ", ... or #hex"
                raise ValueError(f"Invalid color '{value}'. Valid: {valid}")
        elif setting == "icon":
            # Resolve emoji alias and set
            if value.lower() in ("", "none"):
                nb.icon = None
            else:
                nb.icon = resolve_emoji(value)
        elif setting == "template":
            # Set default template name
            if value.lower() in ("", "none"):
                nb.template = None
            else:
                nb.template = value
    else:
        return False

    save_config(config)
    reset_config()  # Clear cache to reload with new values
    return True


def list_config_settings() -> dict[str, tuple[str, Any]]:
    """List all configurable settings with their current values.

    Returns:
        Dict mapping key to (description, current_value).

    """
    result = {}
    for key, description in CONFIGURABLE_SETTINGS.items():
        value = get_config_value(key)
        result[key] = (description, value)

    # Add notebook-specific settings
    config = get_config()
    for nb in config.notebooks:
        for setting, description in NOTEBOOK_SETTINGS.items():
            key = f"notebook.{nb.name}.{setting}"
            value = getattr(nb, setting, None)
            result[key] = (description, value)

    return result
