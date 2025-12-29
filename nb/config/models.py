"""Configuration dataclass models for nb."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    """Configuration for embedding generation (localvectordb).

    API key is loaded from OPENAI_API_KEY environment variable when using OpenAI provider.
    """

    provider: str = "ollama"  # "ollama" or "openai"
    model: str = "nomic-embed-text"
    base_url: str | None = None  # For custom Ollama endpoint
    api_key: str | None = None  # Loaded from OPENAI_API_KEY env var (not config)
    chunk_size: int = 500  # Max tokens per chunk
    chunking_method: str = "paragraphs"  # sentences, tokens, paragraphs, sections


@dataclass
class SearchConfig:
    """Configuration for search behavior.

    Serper API key is loaded from SERPER_API_KEY environment variable.
    """

    vector_weight: float = 0.7  # Hybrid search: 0=keyword only, 1=vector only
    score_threshold: float = 0.4  # Minimum score to show results
    recency_decay_days: int = 30  # Half-life for recency boost
    serper_api_key: str | None = None  # Loaded from SERPER_API_KEY env var (not config)


@dataclass
class TodoConfig:
    """Configuration for todo behavior."""

    default_sort: str = "source"  # source, tag, priority, created
    inbox_file: str = "todo.md"  # Name of inbox file in notes_root
    auto_complete_children: bool = True  # Complete subtasks when parent is done


@dataclass
class RecorderConfig:
    """Configuration for audio recording.

    Deepgram API key is loaded from DEEPGRAM_API_KEY environment variable.
    """

    mic_device: int | None = None  # Microphone device index (-1 or None for default)
    loopback_device: int | None = None  # System audio device index
    sample_rate: int = 16000  # Sample rate in Hz (16000 recommended for speech)
    auto_delete_audio: bool = False  # Delete WAV file after successful transcription
    transcribe_timeout: int = 600  # Deepgram API timeout in seconds (default 10 min)
    mic_speaker_label: str = "You"  # Label for microphone speaker in transcripts
    deepgram_api_key: str | None = (
        None  # Loaded from DEEPGRAM_API_KEY env var (not config)
    )


@dataclass
class ClipConfig:
    """Configuration for web clipping."""

    user_agent: str = "nb-web-clipper/1.0"  # User-Agent header for HTTP requests
    timeout: int = 30  # Request timeout in seconds
    auto_tag_domain: bool = True  # Auto-tag with source domain


@dataclass
class RaindropCollectionConfig:
    """Configuration for a single Raindrop collection mapping.

    Maps a Raindrop collection to a specific notebook with optional settings.
    """

    name: str  # Collection name in Raindrop
    notebook: str  # Target notebook in nb
    auto_archive: bool = True  # Archive after clipping
    extra_tags: list[str] = field(default_factory=list)  # Additional tags to add


@dataclass
class RaindropConfig:
    """Configuration for Raindrop.io integration.

    API token is loaded from RAINDROP_API_KEY environment variable.

    Supports both legacy single-collection config and new multi-collection mapping.
    """

    # Legacy single collection (backwards compatibility)
    collection: str = "nb-inbox"  # Collection to pull from
    auto_archive: bool = True  # Move to archive after clipping
    api_token: str | None = None  # Loaded from RAINDROP_API_KEY env var (not config)

    # Multi-collection support
    collections: list[RaindropCollectionConfig] = field(default_factory=list)

    # Sync settings
    sync_tags: bool = True  # Sync tag changes from Raindrop to notes
    sync_notes: bool = True  # Sync note changes from Raindrop to notes

    def get_all_collections(
        self, default_notebook: str = "bookmarks"
    ) -> list[RaindropCollectionConfig]:
        """Get all configured collections, including legacy single collection.

        If `collections` list is defined, returns it.
        Otherwise, synthesizes a list from the legacy single-collection config.

        Args:
            default_notebook: Fallback notebook for legacy config (from InboxConfig)

        Returns:
            List of collection configurations
        """
        if self.collections:
            return self.collections
        # Backwards compatibility: convert single collection to list format
        return [
            RaindropCollectionConfig(
                name=self.collection,
                notebook=default_notebook,
                auto_archive=self.auto_archive,
            )
        ]


@dataclass
class InboxConfig:
    """Configuration for inbox/web clipping integration."""

    source: str = "raindrop"  # Source service (currently only "raindrop")
    default_notebook: str = "bookmarks"  # Where clips go by default
    auto_summarize: bool = True  # Auto-generate AI summary/tags when clipping
    raindrop: RaindropConfig = field(default_factory=RaindropConfig)


@dataclass
class GitConfig:
    """Configuration for git integration."""

    enabled: bool = False  # Master switch for git integration
    auto_commit: bool = True  # Auto-commit after note changes
    commit_message_template: str = (
        "Update {path}"  # Supports {path}, {notebook}, {title}, {date}
    )


@dataclass
class LLMModelConfig:
    """Configuration for LLM model selection per use case."""

    smart: str = "claude-sonnet-4-5"  # For complex tasks (planning, analysis)
    fast: str = "claude-haiku-4-5"  # For simple tasks (extraction, quick queries)


@dataclass
class LLMConfig:
    """Configuration for LLM integration.

    Supports Anthropic (Claude) and OpenAI APIs via direct REST calls.
    API key is loaded from ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable
    (based on provider setting).
    """

    provider: str = "anthropic"  # anthropic, openai
    models: LLMModelConfig = field(default_factory=LLMModelConfig)
    api_key: str | None = None  # Loaded from env var (not config)
    base_url: str | None = None  # Custom API endpoint (e.g., for proxies)
    max_tokens: int = 4096  # Max tokens in response
    temperature: float = 0.7  # Sampling temperature
    system_prompt: str | None = None  # Global system prompt for all AI commands


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
    env_file: Path | None = None  # Custom .env file path (default: .nb/.env)
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
    git: GitConfig = field(default_factory=GitConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
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
