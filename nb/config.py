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
    chunk_size: int = 500  # Max tokens per chunk
    chunking_method: str = "paragraphs"  # sentences, tokens, paragraphs, sections


@dataclass
class SearchConfig:
    """Configuration for search behavior."""

    vector_weight: float = 0.7  # Hybrid search: 0=keyword only, 1=vector only
    score_threshold: float = 0.4  # Minimum score to show results
    recency_decay_days: int = 30  # Half-life for recency boost


@dataclass
class TodoConfig:
    """Configuration for todo behavior."""

    default_sort: str = "source"  # source, tag, priority, created
    inbox_file: str = "todo.md"  # Name of inbox file in notes_root
    auto_complete_children: bool = True  # Complete subtasks when parent is done


@dataclass
class RecorderConfig:
    """Configuration for audio recording."""

    mic_device: int | None = None  # Microphone device index (-1 or None for default)
    loopback_device: int | None = None  # System audio device index
    sample_rate: int = 16000  # Sample rate in Hz (16000 recommended for speech)
    auto_delete_audio: bool = False  # Delete WAV file after successful transcription
    transcribe_timeout: int = 600  # Deepgram API timeout in seconds (default 10 min)
    mic_speaker_label: str = "You"  # Label for microphone speaker in transcripts


@dataclass
class ClipConfig:
    """Configuration for web clipping."""

    user_agent: str = "nb-web-clipper/1.0"  # User-Agent header for HTTP requests
    timeout: int = 30  # Request timeout in seconds
    auto_tag_domain: bool = True  # Auto-tag with source domain


@dataclass
class RaindropConfig:
    """Configuration for Raindrop.io integration."""

    collection: str = "nb-inbox"  # Collection to pull from
    auto_archive: bool = True  # Move to archive after clipping
    api_token: str | None = None  # Raindrop API token (set via env or config)


@dataclass
class InboxConfig:
    """Configuration for inbox/web clipping integration."""

    source: str = "raindrop"  # Source service (currently only "raindrop")
    default_notebook: str = "bookmarks"  # Where clips go by default
    raindrop: RaindropConfig = field(default_factory=RaindropConfig)


@dataclass
class TodoViewConfig:
    """Configuration for a saved todo view.

    Views store filter settings that can be applied when listing todos.
    """

    name: str
    filters: dict[str, Any] = field(default_factory=dict)
    # Filter keys currently supported by the CLI:
    # - notebooks: list[str] - filter to specific notebooks
    # - notes: list[str] - filter to specific note paths
    # - tag: str - filter by a single tag (note: singular, not 'tags')
    # - priority: int - filter by priority (1, 2, 3)
    # - exclude_tags: list[str] - exclude todos with these tags
    # - hide_later: bool - hide "DUE LATER" section
    # - hide_no_date: bool - hide "NO DUE DATE" section
    # - include_completed: bool - include completed todos


@dataclass
class KanbanColumnConfig:
    """Configuration for a single kanban board column.

    Columns define filters to determine which todos appear in each column.
    """

    name: str
    filters: dict[str, Any] = field(default_factory=dict)
    # Supported filter keys:
    # - status: "pending" | "in_progress" | "completed"
    # - due_today: bool - todos due today
    # - due_this_week: bool - todos due within 7 days
    # - overdue: bool - past due, not completed
    # - no_due_date: bool - todos without a due date
    # - priority: int - filter by priority (1, 2, 3)
    # - tags: list[str] - filter by tags
    color: str = "white"  # Display color for the column header


@dataclass
class KanbanBoardConfig:
    """Configuration for a kanban board.

    Boards contain multiple columns, each with their own filters.
    """

    name: str
    columns: list[KanbanColumnConfig] = field(default_factory=list)


# Default kanban board configuration
DEFAULT_KANBAN_COLUMNS = [
    KanbanColumnConfig(
        name="Backlog",
        filters={"status": "pending", "no_due_date": True},
        color="cyan",
    ),
    KanbanColumnConfig(
        name="In Progress",
        filters={"status": "in_progress"},
        color="green",
    ),
    KanbanColumnConfig(
        name="Due Today",
        filters={"due_today": True, "status": "pending"},
        color="yellow",
    ),
    KanbanColumnConfig(
        name="Done",
        filters={"status": "completed"},
        color="dim",
    ),
]


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
    todo_views: list[TodoViewConfig] = field(default_factory=list)
    kanban_boards: list[KanbanBoardConfig] = field(default_factory=list)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    todo: TodoConfig = field(default_factory=TodoConfig)
    recorder: RecorderConfig = field(default_factory=RecorderConfig)
    clip: ClipConfig = field(default_factory=ClipConfig)
    inbox: InboxConfig = field(default_factory=InboxConfig)
    date_format: str = "%Y-%m-%d"
    time_format: str = "%H:%M"
    daily_title_format: str = "%A, %B %d, %Y"  # e.g., "Friday, November 28, 2025"
    week_start_day: str = "monday"  # monday or sunday

    def get_todo_view(self, name: str) -> TodoViewConfig | None:
        """Get a todo view configuration by name."""
        for view in self.todo_views:
            if view.name == name:
                return view
        return None

    def todo_view_names(self) -> list[str]:
        """Get list of todo view names."""
        return [view.name for view in self.todo_views]

    def get_kanban_board(self, name: str) -> KanbanBoardConfig | None:
        """Get a kanban board configuration by name."""
        for board in self.kanban_boards:
            if board.name == name:
                return board
        return None

    def kanban_board_names(self) -> list[str]:
        """Get list of kanban board names."""
        return [board.name for board in self.kanban_boards]

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
# See: https://github.com/thomas-villani/nb-cli

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
  chunk_size: 500     # Max tokens per chunk (smaller = more precise search)
  chunking_method: paragraphs  # sentences, tokens, paragraphs, sections
  # base_url: http://localhost:11434  # Optional: custom Ollama endpoint
  # api_key: null  # Required for OpenAI

# Search behavior
search:
  vector_weight: 0.7      # Hybrid search balance (0=keyword only, 1=vector only)
  score_threshold: 0.4    # Minimum score to show results
  recency_decay_days: 30  # Half-life in days for recency boost

# Todo behavior
todo:
  default_sort: source           # source, tag, priority, created
  inbox_file: todo.md            # Name of inbox file in notes_root
  auto_complete_children: true   # Complete subtasks when parent done

# Date/time display formats
date_format: "%Y-%m-%d"
time_format: "%H:%M"
daily_title_format: "%A, %B %d, %Y"  # e.g., "Friday, November 28, 2025"
week_start_day: monday  # monday or sunday
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
        chunk_size=data.get("chunk_size", 500),
        chunking_method=data.get("chunking_method", "paragraphs"),
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


def _parse_kanban_columns(data: list[dict[str, Any]]) -> list[KanbanColumnConfig]:
    """Parse kanban column configuration."""
    result = []
    for item in data:
        result.append(
            KanbanColumnConfig(
                name=item["name"],
                filters=item.get("filters", {}),
                color=item.get("color", "white"),
            )
        )
    return result


def _parse_kanban_boards(data: list[dict[str, Any]]) -> list[KanbanBoardConfig]:
    """Parse kanban_boards configuration."""
    result = []
    for item in data:
        columns = _parse_kanban_columns(item.get("columns", []))
        result.append(
            KanbanBoardConfig(
                name=item["name"],
                columns=columns,
            )
        )
    return result


def _parse_search(data: dict[str, Any] | None) -> SearchConfig:
    """Parse search configuration."""
    if data is None:
        return SearchConfig()
    return SearchConfig(
        vector_weight=data.get("vector_weight", 0.7),
        score_threshold=data.get("score_threshold", 0.4),
        recency_decay_days=data.get("recency_decay_days", 30),
    )


def _parse_todo_config(data: dict[str, Any] | None) -> TodoConfig:
    """Parse todo configuration."""
    if data is None:
        return TodoConfig()
    return TodoConfig(
        default_sort=data.get("default_sort", "source"),
        inbox_file=data.get("inbox_file", "todo.md"),
        auto_complete_children=data.get("auto_complete_children", True),
    )


def _parse_recorder_config(data: dict[str, Any] | None) -> RecorderConfig:
    """Parse recorder configuration."""
    if data is None:
        return RecorderConfig()
    return RecorderConfig(
        mic_device=data.get("mic_device"),
        loopback_device=data.get("loopback_device"),
        sample_rate=data.get("sample_rate", 16000),
        auto_delete_audio=data.get("auto_delete_audio", False),
        transcribe_timeout=data.get("transcribe_timeout", 600),
        mic_speaker_label=data.get("mic_speaker_label", "You"),
    )


def _parse_clip_config(data: dict[str, Any] | None) -> ClipConfig:
    """Parse clip configuration."""
    if data is None:
        return ClipConfig()
    return ClipConfig(
        user_agent=data.get("user_agent", "nb-web-clipper/1.0"),
        timeout=data.get("timeout", 30),
        auto_tag_domain=data.get("auto_tag_domain", True),
    )


def _parse_raindrop_config(data: dict[str, Any] | None) -> RaindropConfig:
    """Parse Raindrop configuration."""
    if data is None:
        return RaindropConfig()
    # Check environment variable for API token
    api_token = os.environ.get("RAINDROP_API_KEY") or data.get("api_token")
    return RaindropConfig(
        collection=data.get("collection", "nb-inbox"),
        auto_archive=data.get("auto_archive", True),
        api_token=api_token,
    )


def _parse_inbox_config(data: dict[str, Any] | None) -> InboxConfig:
    """Parse inbox configuration."""
    if data is None:
        return InboxConfig()
    return InboxConfig(
        source=data.get("source", "raindrop"),
        default_notebook=data.get("default_notebook", "bookmarks"),
        raindrop=_parse_raindrop_config(data.get("raindrop")),
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
    date_format = data.get("date_format", "%Y-%m-%d")
    time_format = data.get("time_format", "%H:%M")
    daily_title_format = data.get("daily_title_format", "%A, %B %d, %Y")
    week_start_day = data.get("week_start_day", "monday")

    return Config(
        notes_root=notes_root,
        editor=editor,
        notebooks=notebooks,
        todo_views=todo_views,
        kanban_boards=kanban_boards,
        embeddings=embeddings,
        search=search,
        todo=todo_config,
        recorder=recorder_config,
        clip=clip_config,
        inbox=inbox_config,
        date_format=date_format,
        time_format=time_format,
        daily_title_format=daily_title_format,
        week_start_day=week_start_day,
    )


def save_config(config: Config) -> None:
    """Save configuration to YAML file."""
    # Build embeddings dict, excluding None values
    embeddings_data = {
        "provider": config.embeddings.provider,
        "model": config.embeddings.model,
        "chunk_size": config.embeddings.chunk_size,
        "chunking_method": config.embeddings.chunking_method,
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

    # Build search config dict
    search_data = {
        "vector_weight": config.search.vector_weight,
        "score_threshold": config.search.score_threshold,
        "recency_decay_days": config.search.recency_decay_days,
    }

    # Build todo config dict
    todo_data = {
        "default_sort": config.todo.default_sort,
        "inbox_file": config.todo.inbox_file,
        "auto_complete_children": config.todo.auto_complete_children,
    }

    # Build recorder config dict (only include non-default values)
    recorder_data: dict[str, Any] = {}
    if config.recorder.mic_device is not None:
        recorder_data["mic_device"] = config.recorder.mic_device
    if config.recorder.loopback_device is not None:
        recorder_data["loopback_device"] = config.recorder.loopback_device
    if config.recorder.sample_rate != 16000:
        recorder_data["sample_rate"] = config.recorder.sample_rate
    if config.recorder.auto_delete_audio:
        recorder_data["auto_delete_audio"] = config.recorder.auto_delete_audio
    if config.recorder.transcribe_timeout != 600:
        recorder_data["transcribe_timeout"] = config.recorder.transcribe_timeout
    if config.recorder.mic_speaker_label != "You":
        recorder_data["mic_speaker_label"] = config.recorder.mic_speaker_label

    # Build clip config dict (only include non-default values)
    clip_data: dict[str, Any] = {}
    if config.clip.user_agent != "nb-web-clipper/1.0":
        clip_data["user_agent"] = config.clip.user_agent
    if config.clip.timeout != 30:
        clip_data["timeout"] = config.clip.timeout
    if not config.clip.auto_tag_domain:
        clip_data["auto_tag_domain"] = config.clip.auto_tag_domain

    # Build inbox config dict (only include non-default values)
    inbox_data: dict[str, Any] = {}
    if config.inbox.source != "raindrop":
        inbox_data["source"] = config.inbox.source
    if config.inbox.default_notebook != "bookmarks":
        inbox_data["default_notebook"] = config.inbox.default_notebook
    # Raindrop sub-config
    raindrop_data: dict[str, Any] = {}
    if config.inbox.raindrop.collection != "nb-inbox":
        raindrop_data["collection"] = config.inbox.raindrop.collection
    if not config.inbox.raindrop.auto_archive:
        raindrop_data["auto_archive"] = config.inbox.raindrop.auto_archive
    # Note: api_token is NOT saved to config file for security - use env var
    if raindrop_data:
        inbox_data["raindrop"] = raindrop_data

    # Note: linked_todos and linked_notes are stored in the database, not config
    data: dict[str, Any] = {
        "notes_root": str(config.notes_root),
        "editor": config.editor,
        "notebooks": notebooks_data,
        "todo_views": [
            {"name": view.name, "filters": view.filters} for view in config.todo_views
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

    # Only include recorder config if there are non-default settings
    if recorder_data:
        data["recorder"] = recorder_data

    # Only include clip config if there are non-default settings
    if clip_data:
        data["clip"] = clip_data

    # Only include inbox config if there are non-default settings
    if inbox_data:
        data["inbox"] = inbox_data

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
    "daily_title_format": "Daily note title format (e.g., %A, %B %d, %Y)",
    "week_start_day": "First day of week (monday or sunday)",
    "embeddings.provider": "Embeddings provider (ollama or openai)",
    "embeddings.model": "Embeddings model name (e.g., nomic-embed-text)",
    "embeddings.base_url": "Custom embeddings API endpoint URL",
    "embeddings.api_key": "API key for embeddings provider (OpenAI)",
    "embeddings.chunk_size": "Max tokens per chunk (e.g., 500)",
    "embeddings.chunking_method": "Chunking method (sentences, tokens, paragraphs, sections)",
    "search.vector_weight": "Hybrid search balance: 0=keyword, 1=vector (default 0.7)",
    "search.score_threshold": "Minimum score to show search results (default 0.4)",
    "search.recency_decay_days": "Half-life in days for recency boost (default 30)",
    "todo.default_sort": "Default sort order (source, tag, priority, created)",
    "todo.inbox_file": "Name of inbox file in notes_root (default todo.md)",
    "todo.auto_complete_children": "Complete subtasks when parent done (true/false)",
    "recorder.mic_speaker_label": "Label for microphone speaker in transcripts (default: You)",
    "clip.user_agent": "User-Agent header for web clipping requests",
    "clip.timeout": "Request timeout in seconds (default 30)",
    "clip.auto_tag_domain": "Auto-tag clipped content with source domain (true/false)",
    "inbox.source": "Inbox source service (currently only 'raindrop')",
    "inbox.default_notebook": "Default notebook for clipped items (default: bookmarks)",
    "inbox.raindrop.collection": "Raindrop collection to pull from (default: nb-inbox)",
    "inbox.raindrop.auto_archive": "Move items to archive after clipping (true/false)",
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
        elif key == "daily_title_format":
            return config.daily_title_format
        elif key == "week_start_day":
            return config.week_start_day
        elif key == "notes_root":
            return str(config.notes_root)
    elif parts[0] == "embeddings" and len(parts) == 2:
        # Embeddings setting
        attr = parts[1]
        if hasattr(config.embeddings, attr):
            return getattr(config.embeddings, attr)
    elif parts[0] == "search" and len(parts) == 2:
        # Search setting
        attr = parts[1]
        if hasattr(config.search, attr):
            return getattr(config.search, attr)
    elif parts[0] == "todo" and len(parts) == 2:
        # Todo setting
        attr = parts[1]
        if hasattr(config.todo, attr):
            return getattr(config.todo, attr)
    elif parts[0] == "recorder" and len(parts) == 2:
        # Recorder setting
        attr = parts[1]
        if hasattr(config.recorder, attr):
            return getattr(config.recorder, attr)
    elif parts[0] == "clip" and len(parts) == 2:
        # Clip setting
        attr = parts[1]
        if hasattr(config.clip, attr):
            return getattr(config.clip, attr)
    elif parts[0] == "inbox" and len(parts) == 2:
        # Inbox setting
        attr = parts[1]
        if hasattr(config.inbox, attr):
            return getattr(config.inbox, attr)
    elif parts[0] == "inbox" and len(parts) == 3 and parts[1] == "raindrop":
        # Inbox raindrop setting: inbox.raindrop.<attr>
        attr = parts[2]
        if hasattr(config.inbox.raindrop, attr):
            return getattr(config.inbox.raindrop, attr)
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
        elif key == "daily_title_format":
            config.daily_title_format = value
        elif key == "week_start_day":
            valid_days = ("monday", "sunday")
            if value.lower() not in valid_days:
                raise ValueError(
                    f"week_start_day must be one of: {', '.join(valid_days)}"
                )
            config.week_start_day = value.lower()
        else:
            return False
    elif parts[0] == "embeddings" and len(parts) == 2:
        # Embeddings setting
        attr = parts[1]
        if attr in ("provider", "model", "base_url", "api_key"):
            setattr(config.embeddings, attr, value if value else None)
        elif attr == "chunk_size":
            try:
                config.embeddings.chunk_size = int(value)
            except ValueError:
                raise ValueError(
                    f"chunk_size must be an integer, got '{value}'"
                ) from None
        elif attr == "chunking_method":
            valid_methods = ("sentences", "tokens", "paragraphs", "sections")
            if value not in valid_methods:
                raise ValueError(
                    f"chunking_method must be one of: {', '.join(valid_methods)}"
                )
            config.embeddings.chunking_method = value
        else:
            return False
    elif parts[0] == "search" and len(parts) == 2:
        # Search setting
        attr = parts[1]
        if attr == "vector_weight":
            try:
                weight = float(value)
                if not 0 <= weight <= 1:
                    raise ValueError("vector_weight must be between 0 and 1")
                config.search.vector_weight = weight
            except ValueError as e:
                if "could not convert" in str(e).lower():
                    raise ValueError(
                        f"vector_weight must be a number, got '{value}'"
                    ) from None
                raise
        elif attr == "score_threshold":
            try:
                threshold = float(value)
                if not 0 <= threshold <= 1:
                    raise ValueError("score_threshold must be between 0 and 1")
                config.search.score_threshold = threshold
            except ValueError as e:
                if "could not convert" in str(e).lower():
                    raise ValueError(
                        f"score_threshold must be a number, got '{value}'"
                    ) from None
                raise
        elif attr == "recency_decay_days":
            try:
                days = int(value)
                if days < 1:
                    raise ValueError("recency_decay_days must be at least 1")
                config.search.recency_decay_days = days
            except ValueError as e:
                if "invalid literal" in str(e).lower():
                    raise ValueError(
                        f"recency_decay_days must be an integer, got '{value}'"
                    ) from None
                raise
        else:
            return False
    elif parts[0] == "todo" and len(parts) == 2:
        # Todo setting
        attr = parts[1]
        if attr == "default_sort":
            valid_sorts = ("source", "tag", "priority", "created")
            if value not in valid_sorts:
                raise ValueError(
                    f"default_sort must be one of: {', '.join(valid_sorts)}"
                )
            config.todo.default_sort = value
        elif attr == "inbox_file":
            config.todo.inbox_file = value
        elif attr == "auto_complete_children":
            config.todo.auto_complete_children = value.lower() in ("true", "1", "yes")
        else:
            return False
    elif parts[0] == "recorder" and len(parts) == 2:
        # Recorder setting
        attr = parts[1]
        if attr == "mic_speaker_label":
            config.recorder.mic_speaker_label = value if value else "You"
        else:
            return False
    elif parts[0] == "clip" and len(parts) == 2:
        # Clip setting
        attr = parts[1]
        if attr == "user_agent":
            config.clip.user_agent = value if value else "nb-web-clipper/1.0"
        elif attr == "timeout":
            try:
                timeout = int(value)
                if timeout < 1:
                    raise ValueError("timeout must be at least 1 second")
                config.clip.timeout = timeout
            except ValueError as e:
                if "invalid literal" in str(e).lower():
                    raise ValueError(
                        f"timeout must be an integer, got '{value}'"
                    ) from None
                raise
        elif attr == "auto_tag_domain":
            config.clip.auto_tag_domain = value.lower() in ("true", "1", "yes")
        else:
            return False
    elif parts[0] == "inbox" and len(parts) == 2:
        # Inbox setting
        attr = parts[1]
        if attr == "source":
            valid_sources = ("raindrop",)
            if value not in valid_sources:
                raise ValueError(f"source must be one of: {', '.join(valid_sources)}")
            config.inbox.source = value
        elif attr == "default_notebook":
            config.inbox.default_notebook = value if value else "bookmarks"
        else:
            return False
    elif parts[0] == "inbox" and len(parts) == 3 and parts[1] == "raindrop":
        # Inbox raindrop setting: inbox.raindrop.<attr>
        attr = parts[2]
        if attr == "collection":
            config.inbox.raindrop.collection = value if value else "nb-inbox"
        elif attr == "auto_archive":
            config.inbox.raindrop.auto_archive = value.lower() in ("true", "1", "yes")
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
