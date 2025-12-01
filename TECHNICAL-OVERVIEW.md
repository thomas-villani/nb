# nb CLI - Technical Overview

This document provides a comprehensive technical breakdown of the `nb` CLI application architecture, data flow, and implementation details.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Core Data Models](#core-data-models)
4. [Configuration System](#configuration-system)
5. [Indexing System](#indexing-system)
6. [Search Functionality](#search-functionality)
7. [Todo Extraction & Management](#todo-extraction--management)
8. [Database Schema](#database-schema)
9. [CLI Commands](#cli-commands)
10. [Text User Interface (TUI)](#text-user-interface-tui)
11. [Web Interface](#web-interface)
12. [Recording & Transcription](#recording--transcription)
13. [Performance Analysis & Optimization](#performance-analysis--optimization)
14. [Frequently Asked Questions](#frequently-asked-questions)
15. [Extensibility Points](#extensibility-points)

---

## Architecture Overview

The `nb` CLI is a note-taking and task management tool built with Python. It follows a layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer (click)                      │
│    nb/cli/  (notes, todos, search, record, web, config...)  │
├─────────────────────────────────────────────────────────────┤
│              TUI Layer (rich)    |    Web Layer (HTTP)      │
│         nb/tui/todos.py, review.py   |   nb/web.py          │
├─────────────────────────────────────────────────────────────┤
│                    Core Business Logic                      │
│  nb/core/notes.py | todos.py | links.py | templates.py | aliases.py │
├─────────────────────────────────────────────────────────────┤
│                   Optional: Recorder                        │
│     nb/recorder/audio.py | transcriber.py | formatter.py   │
├─────────────────────────────────────────────────────────────┤
│                     Index & Search                          │
│  nb/index/scanner.py  |  search.py  |  db.py  |  todos_repo.py │
├─────────────────────────────────────────────────────────────┤
│                       Data Layer                            │
│           SQLite (index.db)  |  localvectordb (vectors/)    │
├─────────────────────────────────────────────────────────────┤
│                      File System                            │
│                  Markdown files (notes_root/)               │
└─────────────────────────────────────────────────────────────┘
```

**Key Principles:**
- **Markdown as Source of Truth**: The database is a cache/index; markdown files are authoritative
- **On-Demand Indexing**: No background processes; indexing triggered by commands
- **Lazy Initialization**: Vector search, database connections initialized on first use
- **Content Hash Change Detection**: Only reindex files that have actually changed
- **Optional Dependencies**: Recorder features require `uv sync --extra recorder`

---

## Project Structure

```
nb-cli/
├── nb/                          # Main application package
│   ├── config.py                # Configuration management
│   ├── models.py                # Data models (Note, Todo, TodoStatus, etc.)
│   ├── web.py                   # Web interface (HTTP server + UI)
│   ├── cli/                     # CLI commands (Click framework)
│   │   ├── __init__.py          # Main CLI entry point & aliases
│   │   ├── notes.py             # Note commands (today, new, edit, list)
│   │   ├── todos.py             # Todo commands (list, add, done, review)
│   │   ├── search.py            # Search commands (search, grep)
│   │   ├── record.py            # Recording commands (start, transcribe)
│   │   ├── web.py               # Web server command
│   │   ├── templates.py         # Template management commands
│   │   ├── stats.py             # Statistics commands
│   │   ├── tags.py              # Tag-related commands
│   │   ├── config_cmd.py        # Config get/set commands
│   │   ├── notebooks.py         # Notebook management
│   │   ├── links.py             # Linked files commands
│   │   └── attachments.py       # Attachment commands
│   ├── core/                    # Core business logic
│   │   ├── notebooks.py         # Notebook operations
│   │   ├── notes.py             # Note file operations
│   │   ├── todos.py             # Todo extraction & manipulation
│   │   ├── templates.py         # Template management
│   │   ├── aliases.py           # Note aliasing system
│   │   ├── attachments.py       # Attachment management
│   │   └── links.py             # Linked files management
│   ├── index/                   # Indexing & search
│   │   ├── db.py                # SQLite database layer (schema v12)
│   │   ├── scanner.py           # File scanning & indexing
│   │   ├── search.py            # Search engine (vector + FTS)
│   │   └── todos_repo.py        # Todo database queries
│   ├── tui/                     # Text User Interface
│   │   ├── todos.py             # Interactive todo viewer
│   │   ├── review.py            # Interactive todo review mode
│   │   └── stream.py            # Console streaming utilities
│   ├── recorder/                # Audio recording (optional)
│   │   ├── __init__.py          # Availability checking
│   │   ├── audio.py             # Microphone/system audio capture
│   │   ├── transcriber.py       # Deepgram API integration
│   │   └── formatter.py         # Transcription formatting
│   └── utils/                   # Utilities
│       ├── dates.py             # Date parsing & formatting
│       ├── hashing.py           # ID & hash generation
│       ├── markdown.py          # Markdown parsing
│       ├── fuzzy.py             # Fuzzy matching utilities
│       └── editor.py            # External editor integration
├── pyproject.toml               # Project metadata & dependencies
└── .nb/                         # Application data directory
    ├── config.yaml              # User configuration
    ├── index.db                 # SQLite database
    ├── vectors/                 # localvectordb storage
    ├── templates/               # Note templates
    └── attachments/             # Copied attachments
```

**Key Dependencies:**
- `click` (8.0+) - CLI framework
- `rich` (13.0+) - Pretty console output and TUI
- `python-frontmatter` (1.0+) - YAML frontmatter parsing
- `python-dateutil` (2.8+) - Fuzzy date parsing
- `localvectordb` - Vector embeddings for semantic search
- `pyyaml` (6.0+) - YAML configuration

**Optional Dependencies** (install with `uv sync --extra recorder`):
- `sounddevice` - Audio recording
- `deepgram-sdk` - Speech-to-text transcription

---

## Core Data Models

**Location:** `nb/models.py`

### TodoStatus (Enum)
```python
class TodoStatus(Enum):
    PENDING = "pending"        # [ ] checkbox
    IN_PROGRESS = "in_progress"  # [^] checkbox
    COMPLETED = "completed"    # [x] or [X] checkbox

    @classmethod
    def from_marker(cls, marker: str) -> "TodoStatus":
        """Convert checkbox marker to status."""

    @property
    def marker(self) -> str:
        """Return the checkbox marker for this status."""
```

### Note
```python
@dataclass
class Note:
    path: str              # Relative path within notes_root
    title: str | None      # From frontmatter or first H1
    date: date | None      # From frontmatter or filename (YYYY-MM-DD)
    tags: list[str]        # From frontmatter and inline #tags
    links: list[str]       # Wiki-style [[links]]
    attachments: list[Attachment]
    notebook: str | None   # First directory component
    content_hash: str      # SHA256 for change detection
```

### Todo
```python
@dataclass
class Todo:
    id: str                # SHA256(path:line:content)[:8]
    content: str           # Cleaned text (metadata removed)
    raw_content: str       # Original line text
    status: TodoStatus     # pending | in_progress | completed
    source: TodoSource     # Where this todo came from
    line_number: int       # 1-based line in source file
    created_date: date | None
    due_date: date | None  # Parsed from @due(...)
    completed_date: date | None  # When marked complete
    priority: Priority | None  # From @priority(1|2|3)
    tags: list[str]        # From #tag syntax
    project: str | None    # Inferred from path
    parent_id: str | None  # For subtasks
    children: list[Todo]   # Nested todos
    attachments: list[Attachment]
    details: str | None    # Multi-line description (lines after todo)
    section: str | None    # Section heading this todo is under

    @property
    def completed(self) -> bool:
        """Backwards-compatible: True if status is COMPLETED."""

    @property
    def in_progress(self) -> bool:
        """True if status is IN_PROGRESS."""

    @property
    def is_overdue(self) -> bool

    @property
    def is_due_today(self) -> bool

    @property
    def priority_sort_key(self) -> int
```

### TodoSource
```python
@dataclass
class TodoSource:
    type: str      # "note" | "inbox" | "linked"
    path: Path     # Absolute path to source file
    external: bool # Whether from linked external file
    alias: str | None  # Alias for linked files
```

### Attachment
```python
@dataclass
class Attachment:
    id: str                # Unique identifier
    type: Literal["file", "url", "conversation"]
    path: str              # File path or URL
    title: str | None      # Display title
    added_date: date | None
    copied: bool           # Whether copied to attachments folder
```

---

## Configuration System

**Location:** `nb/config.py`

### Config File Location
`~/.nb/config.yaml` (within notes_root)

### Configuration Classes

#### NotebookConfig
```python
@dataclass
class NotebookConfig:
    name: str              # Notebook identifier
    path: str | None       # Custom path (for external notebooks)
    date_based: bool       # Uses week folder structure
    todo_exclude: bool     # Exclude from todo listings
    color: str | None      # Display color (e.g., "blue", "#ff5500")
    icon: str | None       # Display emoji/icon
    template: str | None   # Default template for new notes
```

#### TodoViewConfig
```python
@dataclass
class TodoViewConfig:
    name: str              # View name (e.g., "work", "urgent")
    filters: dict          # Filter settings (tags, priority, etc.)
```

#### RecorderConfig
```python
@dataclass
class RecorderConfig:
    mic_device: str | None      # Microphone device name
    loopback_device: str | None # System audio device
    sample_rate: int            # Default: 16000
    auto_delete_audio: bool     # Delete after transcription
    transcribe_timeout: int     # Timeout in seconds
    mic_speaker_label: bool     # Label mic/speaker in transcription
```

### Configuration Hierarchy
```yaml
notes_root: ~/notes          # Base directory
editor: code                 # Default editor ($EDITOR overrides)
date_format: "%Y-%m-%d"
time_format: "%H:%M"
daily_title_format: "%A, %B %d, %Y"  # Title for daily notes
week_start_day: monday       # "monday" or "sunday"

notebooks:
  - name: daily
    date_based: true         # Uses week folder structure
    icon: ":calendar:"       # Emoji alias
    color: blue
  - name: projects
    template: project        # Use project.md template
  - name: work
    todo_exclude: true       # Don't show todos from this notebook
  - name: obsidian           # External notebook
    path: ~/obsidian/vault
    color: purple

todo_views:                  # Saved filter presets
  - name: urgent
    filters:
      priority: 1
      tags: [urgent]
  - name: work
    filters:
      notebook: work

recorder:                    # Audio recording settings
  mic_device: null           # Auto-detect
  sample_rate: 16000
  auto_delete_audio: false
  mic_speaker_label: true

embeddings:
  provider: ollama           # or "openai"
  model: nomic-embed-text
  base_url: http://localhost:11434
```

**Note:** Linked todos and linked notes are now stored in the **database**, not config.yaml.

### Derived Paths
```python
config.nb_dir           # notes_root/.nb
config.db_path          # notes_root/.nb/index.db
config.vectors_path     # notes_root/.nb/vectors
config.attachments_path # notes_root/.nb/attachments
config.templates_path   # notes_root/.nb/templates
```

### Helper Functions
```python
get_notebook(name)         # Get NotebookConfig by name
notebook_names()           # List all notebook names
excluded_notebooks()       # Notebooks with todo_exclude=True
external_notebooks()       # Notebooks with custom paths
get_notebook_path(name)    # Resolve filesystem path

get_todo_view(name)        # Get TodoViewConfig by name
todo_view_names()          # List all view names

save_config()              # Persist config changes to YAML
add_notebook(config)       # Add notebook at runtime
remove_notebook(name)      # Remove notebook

resolve_emoji(value)       # Convert ":calendar:" → 📅
is_valid_color(color)      # Validate Rich color format
```

### Environment Variables
```bash
NB_NOTES_ROOT     # Override default ~/notes
EDITOR            # Override configured editor
OPENAI_API_KEY    # For OpenAI embeddings
DEEPGRAM_API_KEY  # For audio transcription
```

---

## Indexing System

**Location:** `nb/index/scanner.py`

### When Indexing Occurs

| Trigger | What Happens |
|---------|--------------|
| `nb todo` (listing) | `index_all_notes()` runs automatically |
| `nb todo -i` | Full reindex before interactive mode |
| `nb index` | Explicit reindex (changed files only) |
| `nb index --force` | Force reindex all files |
| `nb index --embeddings` | Rebuild vector search index |
| `nb link sync` | Re-scan linked files |

### Change Detection Algorithm

```python
def needs_reindex(path: Path) -> bool:
    """
    1. Compute SHA256 hash of file content
    2. Query database: SELECT content_hash FROM notes WHERE path = ?
    3. Compare hashes:
       - If file not in database → True (needs indexing)
       - If hash changed → True (needs indexing)
       - Otherwise → False (skip)
    """
```

**Key Insight:** This O(1) per-file check enables efficient incremental indexing.

### Indexing Workflow

```
index_all_notes()
    │
    ├─► scan_notes()
    │       └─► Walk directory tree
    │           └─► Find all *.md files
    │           └─► Exclude: hidden directories, .nb/
    │
    ├─► For each file:
    │       │
    │       ├─► needs_reindex(path)?
    │       │       │
    │       │       ├─► No → Skip
    │       │       │
    │       │       └─► Yes → index_note(path)
    │       │               │
    │       │               ├─► Parse metadata (title, date, tags, links)
    │       │               ├─► Upsert to notes table
    │       │               ├─► Update note_tags (many-to-many)
    │       │               ├─► Update note_links (wiki-style)
    │       │               ├─► Index to vector DB (if enabled)
    │       │               └─► Extract and index todos
    │       │
    │       └─► Continue to next file
    │
    └─► Return count of indexed files
```

### File Watching

**Current Implementation:** None - there is no active file watcher.

All indexing is on-demand, triggered by CLI commands. This is a deliberate design choice for simplicity and reliability.

**Potential Enhancement:** Could add `watchdog` library for live updates:
```python
# Hypothetical implementation
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class NoteChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.md'):
            index_note(Path(event.src_path))
```

---

## Search Functionality

**Location:** `nb/index/search.py`

### Search Types

| Type | Description | Backend |
|------|-------------|---------|
| Keyword | Exact term matching | localvectordb FTS5 |
| Semantic | Embedding similarity | localvectordb + Ollama/OpenAI |
| Hybrid (default) | 70% semantic + 30% keyword | Both |

### Search Flow

```
search(query, search_type="hybrid", k=10, filters={})
    │
    ├─► Build filters (tags, notebook, date range)
    │
    ├─► Query localvectordb
    │       ├─► FTS5 for keyword matching
    │       └─► Vector similarity for semantic
    │
    ├─► Combine results (for hybrid)
    │
    ├─► Apply recency boost (if --recent flag)
    │       └─► Score × 2^(-age_days / 30)
    │
    └─► Return top k SearchResults
```

### When Content is Indexed for Search

1. **During `index_note()`** - if content changed and vectors enabled
2. **During `rebuild_search_index()`** - regenerate from database
3. **During linked note indexing** - includes vector indexing
4. **Automatic cleanup** - when notes deleted

### Vector Search Configuration

```yaml
embeddings:
  provider: ollama         # Local, no API calls
  model: nomic-embed-text  # Default model
  base_url: http://localhost:11434
```

**Storage:** `notes_root/.nb/vectors/`

**Chunking Strategy:** Paragraphs, 500 character chunks

---

## Todo Extraction & Management

**Location:** `nb/core/todos.py`

### Todo Syntax

```markdown
- [ ] Pending task @due(friday) @priority(1) #urgent
  - [ ] Subtask (indentation creates hierarchy)
- [^] In-progress task (started but not done)
- [x] Completed task
@attach: ~/docs/file.pdf   # Attachment for previous todo

## Section Heading
- [ ] This todo will have section="Section Heading"

- [ ] Multi-line todo
  Additional details on following lines
  are captured in the `details` field
```

### Parsing Patterns

```python
TODO_PATTERN = r"^(?P<indent>\s*)- \[(?P<status>[ xX^])\] (?P<content>.+)$"
DUE_PATTERN = r"@due\((?P<date>[^)]+)\)"
PRIORITY_PATTERN = r"@priority\((?P<level>[123])\)"
TAG_PATTERN = r"#(\w+)"
ATTACH_PATTERN = r"^\s*@attach:\s*(.+)$"
HEADING_PATTERN = r"^#{1,6}\s+(.+)$"
COLON_LABEL_PATTERN = r"^([A-Z][^:]+):$"  # "Tasks:" style sections
```

### Extraction Algorithm

```
extract_todos(path, notebook=None)
    │
    ├─► Skip code blocks (track ``` fences)
    │
    ├─► Track current section heading
    │
    ├─► For each line:
    │       ├─► Match HEADING_PATTERN → update current section
    │       ├─► Match TODO_PATTERN
    │       │       ├─► Parse status ([ ] → pending, [^] → in_progress, [x] → completed)
    │       │       ├─► Parse metadata (@due, @priority, #tags)
    │       │       ├─► Clean content (remove metadata markers)
    │       │       ├─► Assign current section
    │       │       └─► Build hierarchy from indentation
    │       ├─► Non-todo indented lines → append to previous todo's details
    │       └─► Match @attach → add attachment to previous todo
    │
    └─► Return list[Todo] with parent-child relationships, sections, details
```

### Due Date Parsing

The `parse_fuzzy_date()` function supports:
- Relative: "friday", "next week", "tomorrow"
- Absolute: "2025-12-01", "Dec 1"
- Natural: "in 3 days", "end of month"

### Todo ID Generation

```python
def make_todo_id(path: str, line_number: int, content: str) -> str:
    return sha256(f"{path}:{line_number}:{content}")[:8]
```

IDs are stable across sessions but change if content or location changes.

---

## Database Schema

**Location:** `nb/index/db.py`

### Schema Version: 12

Auto-migrates on startup; backward compatible. Migration history:
- v5: Added `mtime` column for fast change detection
- v6: Added `details` column for multi-line todo content
- v7: Added `note_views` table and per-note `todo_exclude` flag
- v8: Added `todo_exclude` and `sync` columns to linked_notes
- v9: Added `section` column for todo heading tracking
- v10: Added `status` column (pending/in_progress/completed), migrated from boolean
- v11: Added `note_aliases` table for quick note access
- v12: Added `completed_date` column for activity tracking

### Tables

#### notes
```sql
CREATE TABLE notes (
    path TEXT PRIMARY KEY,
    title TEXT,
    date TEXT,              -- ISO format
    notebook TEXT,
    content_hash TEXT,      -- SHA256
    content TEXT,           -- Full content for grep
    mtime REAL,             -- File modification time (v5)
    external INTEGER,       -- 0=internal, 1=linked
    source_alias TEXT,
    todo_exclude INTEGER,   -- 0=include, 1=exclude from todos (v7)
    updated_at TEXT
);
```

#### todos
```sql
CREATE TABLE todos (
    id TEXT PRIMARY KEY,
    content TEXT,
    raw_content TEXT,
    status TEXT,            -- 'pending'|'in_progress'|'completed' (v10)
    source_type TEXT,       -- note|inbox|linked
    source_path TEXT,
    source_external INTEGER,
    source_alias TEXT,
    line_number INTEGER,
    created_date TEXT,
    due_date TEXT,
    completed_date TEXT,    -- When marked complete (v12)
    priority INTEGER,       -- 1|2|3
    project TEXT,
    parent_id TEXT REFERENCES todos(id) ON DELETE CASCADE,
    content_hash TEXT,
    details TEXT,           -- Multi-line description (v6)
    section TEXT            -- Section heading (v9)
);
```

#### note_views (v7)
```sql
CREATE TABLE note_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path TEXT NOT NULL,
    viewed_at TEXT NOT NULL,  -- ISO timestamp
    FOREIGN KEY (note_path) REFERENCES notes(path) ON DELETE CASCADE
);
```

#### note_aliases (v11)
```sql
CREATE TABLE note_aliases (
    alias TEXT PRIMARY KEY,
    note_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (note_path) REFERENCES notes(path) ON DELETE CASCADE
);
```

#### linked_notes
```sql
CREATE TABLE linked_notes (
    path TEXT PRIMARY KEY,
    alias TEXT,
    recursive INTEGER,
    todo_exclude INTEGER,   -- (v8)
    sync INTEGER            -- (v8)
);
```

#### Indexes

```sql
-- Performance-critical indexes
CREATE INDEX idx_todos_due ON todos(due_date);
CREATE INDEX idx_todos_status ON todos(status);
CREATE INDEX idx_todos_project ON todos(project);
CREATE INDEX idx_todos_source ON todos(source_path);
CREATE INDEX idx_todos_parent ON todos(parent_id);
CREATE INDEX idx_todos_section ON todos(section);
CREATE INDEX idx_todo_tags_tag ON todo_tags(tag);

CREATE INDEX idx_notes_date ON notes(date);
CREATE INDEX idx_notes_notebook ON notes(notebook);
CREATE INDEX idx_notes_mtime ON notes(mtime);

CREATE INDEX idx_note_views_path ON note_views(note_path);
CREATE INDEX idx_note_views_time ON note_views(viewed_at);
```

---

## CLI Commands

**Location:** `nb/cli/` (modular command structure)

### Command Aliases

| Alias | Expands To |
|-------|------------|
| `t` | `today` |
| `y` | `yesterday` |
| `l` | `last` |
| `o` | `open` |
| `s` | `search` |
| `ss` | `search --semantic` |
| `td` | `todo` |
| `ta` | `todo add` |
| `nbs` | `notebooks` |
| `rec` | `record` |

### Notes Management

| Command | Description |
|---------|-------------|
| `nb` / `nb today` | Open today's daily note |
| `nb yesterday` | Open yesterday's note |
| `nb last [N]` | Open note from N days ago |
| `nb open <path\|alias>` | Open note by path or alias |
| `nb new <path>` | Create new note (with template support) |
| `nb edit <path>` | Edit existing note |
| `nb add "<text>"` | Append to today's note |
| `nb list` | List notes |
| `nb notebooks` | Show all notebooks |
| `nb alias <alias> <path>` | Create note alias |
| `nb alias list` | List all aliases |
| `nb alias remove <alias>` | Remove alias |

### Todos

| Command | Description |
|---------|-------------|
| `nb todo` | List todos (triggers indexing) |
| `nb todo -i` | Interactive TUI mode |
| `nb todo add "<text>"` | Add to inbox |
| `nb todo done <id>` | Mark complete |
| `nb todo undone <id>` | Mark incomplete |
| `nb todo start <id>` | Mark as in-progress ([^]) |
| `nb todo show <id>` | Show details |
| `nb todo edit <id>` | Edit source at line |
| `nb todo review` | Interactive review mode |
| `nb todo due` | Show todos due today |
| `nb todo all-done` | Show all completed today |

**Filtering:**
```bash
nb todo --today          # Due today
nb todo --week           # Due this week
nb todo --overdue        # Past due
nb todo --focus          # Overdue + today + this week + next week
nb todo -p 1             # High priority only
nb todo -t urgent        # Tagged #urgent
nb todo -T archived      # Exclude #archived tag
nb todo -n work          # From notebook "work"
nb todo -N personal      # Exclude notebook "personal"
nb todo --note <path>    # From specific note
nb todo --project work   # Specific project
nb todo --all            # Include completed
nb todo -a               # Include excluded notebooks
nb todo --hide-later     # Hide "due later" section
nb todo --hide-no-date   # Hide "no due date" section
nb todo --sort-by tag    # Sort by: source|tag|priority|created

# Creation date filters
nb todo --created-today  # Created today
nb todo --created-week   # Created this week
```

**Saved Views:**
```bash
nb todo --view urgent        # Load saved view
nb todo --list-views         # List all views
nb todo --create-view work   # Save current filters as view
nb todo --delete-view work   # Delete saved view
```

### Search

| Command | Description |
|---------|-------------|
| `nb search "<query>"` | Hybrid search (default) |
| `nb search -s "<query>"` | Semantic only |
| `nb search -k "<query>"` | Keyword only |
| `nb search -t <tag>` | Filter by tag |
| `nb search -n <notebook>` | Filter by notebook |
| `nb search --recent` | Boost recent results |
| `nb grep "<pattern>"` | Regex search |

### Templates

| Command | Description |
|---------|-------------|
| `nb template list` | List available templates |
| `nb template show <name>` | Show template content |
| `nb template create <name>` | Create new template |
| `nb template edit <name>` | Edit template |
| `nb template delete <name>` | Delete template |

### Recording & Transcription

| Command | Description |
|---------|-------------|
| `nb record start` | Start recording audio |
| `nb record start --name <name>` | Record with custom name |
| `nb record start --mic-only` | Record microphone only |
| `nb record start --system-only` | Record system audio only |
| `nb record start --dictate` | Dictation mode (mic → transcript) |
| `nb record list` | List recordings |
| `nb record transcribe <file>` | Transcribe audio file |
| `nb record purge` | Delete old audio files |

### Web Interface

| Command | Description |
|---------|-------------|
| `nb web` | Start web server (port 3000) |
| `nb web --port 8080` | Use custom port |
| `nb web --no-open` | Don't open browser |
| `nb web --completed` | Show completed todos |

### Statistics

| Command | Description |
|---------|-------------|
| `nb stats` | Show productivity statistics |
| `nb stats --week` | This week's stats |
| `nb stats --month` | This month's stats |

### Linked Files

| Command | Description |
|---------|-------------|
| `nb link list` | Show all links |
| `nb link add <path>` | Link external file |
| `nb link remove <alias>` | Unlink |
| `nb link sync` | Re-scan all links |
| `nb link enable-sync <alias>` | Enable completion sync |
| `nb link disable-sync <alias>` | Disable sync |

### Index & Config

| Command | Description |
|---------|-------------|
| `nb index` | Reindex changed files |
| `nb index --force` | Reindex all |
| `nb index --embeddings` | Rebuild vectors |
| `nb config` | Open config file |
| `nb config get <key>` | Get config value |
| `nb config set <key> <value>` | Set config value |

---

## Text User Interface (TUI)

**Location:** `nb/tui/todos.py`, `nb/tui/review.py`

### Interactive Mode: `nb todo -i`

Uses Rich library for rendering. Displays todos in a navigable table with color coding.

### Color Coding

| Condition | Style |
|-----------|-------|
| Overdue | Red bold |
| Due today | Yellow bold |
| Due this week | Cyan |
| Due later | Dim |
| In-progress | Blue |
| Completed | Strikethrough green |

### Controls

| Key | Action |
|-----|--------|
| `j/k` or arrows | Navigate up/down |
| `Space` | Toggle completion |
| `s` | Start (mark in-progress) |
| `e` | Edit (opens source at line) |
| `c` | Toggle showing completed |
| `g/G` | Jump to top/bottom |
| `r` | Refresh todos |
| `q` | Quit |

### Review Mode: `nb todo review`

**Location:** `nb/tui/review.py`

Interactive todo review for weekly/daily reviews. Presents todos one at a time with actions.

```
┌────────────────────────────────────────────┐
│  Review Mode (3 of 15)                     │
├────────────────────────────────────────────┤
│  - [ ] Finish quarterly report             │
│        @due(friday) @priority(1) #work     │
│                                            │
│        Source: daily/2025/Nov25-Dec01/...  │
│        Section: Work Tasks                 │
├────────────────────────────────────────────┤
│  [d]one  [s]kip  [r]eschedule  [e]dit     │
│  [D]elete  [q]uit                          │
└────────────────────────────────────────────┘
```

**Review Actions:**
| Key | Action |
|-----|--------|
| `d` | Mark complete |
| `s` | Skip (keep pending) |
| `r` | Reschedule (prompt for new date) |
| `e` | Edit source file |
| `D` | Delete todo |
| `q` | Quit review |

**Review Statistics:** Tracks completed, skipped, rescheduled, and deleted counts.

---

## Web Interface

**Location:** `nb/web.py`

### Overview

A modern dark-themed web UI accessible via `nb web`. Launches a local HTTP server (default port 3000) with a single-page application for browsing notes and managing todos.

### Features

- **Notebook Browser**: Cards with color indicators and note counts
- **Note Viewer**: Markdown rendering with syntax highlighting (GitHub dark theme)
- **Full-text Search**: Live search results as you type
- **Todo Manager**: Status groups (Overdue, In Progress, Due Today, etc.)
- **Note Editor**: Create and edit notes in-browser
- **Todo Creation**: Add todos with metadata (@due, @priority, #tags)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/notebooks` | GET | List all notebooks with metadata |
| `/api/notebooks/{name}` | GET | List notes in a notebook |
| `/api/note` | GET | Get note content (query: `path`) |
| `/api/note` | POST | Create or update note |
| `/api/todos` | GET | List todos with filtering |
| `/api/todos/{id}/toggle` | POST | Toggle todo completion |
| `/api/todos` | POST | Create new todo |
| `/api/search` | GET | Search notes (query: `q`) |

### Tech Stack

- Pure Python HTTP server (no external framework)
- Vanilla JavaScript with marked.js for markdown
- CSS with dark theme and responsive layout
- highlight.js for code syntax highlighting

---

## Recording & Transcription

**Location:** `nb/recorder/`

### Overview

Optional audio recording and transcription features for capturing meetings, dictation, and voice notes. Requires extra dependencies.

### Installation

```bash
uv sync --extra recorder
```

### Architecture

```
nb/recorder/
├── __init__.py       # is_available(), require_recorder()
├── audio.py          # SoundDeviceRecorder class
├── transcriber.py    # Deepgram API integration
└── formatter.py      # Markdown output formatting
```

### Audio Recording

**Location:** `nb/recorder/audio.py`

```python
class SoundDeviceRecorder:
    """Records audio from microphone and/or system audio."""

    def __init__(self, mic_device=None, loopback_device=None, sample_rate=16000):
        ...

    def start(self) -> None
    def stop(self) -> Path  # Returns WAV file path
    def is_recording(self) -> bool
```

**Features:**
- Dual-channel recording (mic + system audio)
- Device selection via config or CLI flags
- WAV file output at configurable sample rate

### Transcription

**Location:** `nb/recorder/transcriber.py`

Uses Deepgram API for speech-to-text with speaker diarization.

```python
def transcribe(
    audio_path: Path,
    timeout: int = 300,
    speaker_labels: bool = True
) -> TranscriptionResult:
    """Transcribe audio file using Deepgram API."""
```

**Features:**
- Speaker diarization (identifies different speakers)
- Mic/speaker channel labeling for dual-source recordings
- Timeout handling for long recordings

**Environment:** Requires `DEEPGRAM_API_KEY`

### Output Formatting

**Location:** `nb/recorder/formatter.py`

```python
def format_transcription(
    result: TranscriptionResult,
    mic_speaker_label: bool = True
) -> str:
    """Format transcription as markdown with speaker labels."""
```

**Output Example:**
```markdown
## Meeting Transcription

**Speaker 1 (Mic):** Hello, let's discuss the project timeline.

**Speaker 2 (System):** Sure, I think we should aim for Q2.

...
```

---

## Performance Analysis & Optimization

### Current Performance Characteristics

| Operation | Complexity | Notes |
|-----------|------------|-------|
| File scan | O(n) | Walks entire directory tree |
| Change detection | O(1) per file | Hash comparison |
| Todo query | O(log n) | Indexed on due_date, priority |
| Vector search | O(k) | Limited by k results |

### Bottlenecks & Mitigations

#### 1. Full Directory Scan
**Problem:** `scan_notes()` walks entire directory tree on every `nb todo` command.

**Current Mitigation:** Two-tier change detection:
1. **mtime check** (schema v5): Compare file modification time against stored `mtime` column
2. **Content hash**: Only compute hash if mtime changed, skip if hash unchanged

```python
def needs_reindex(path: Path) -> bool:
    stored_mtime = get_stored_mtime(path)
    current_mtime = path.stat().st_mtime
    if current_mtime == stored_mtime:
        return False  # Fast path: unchanged
    # mtime changed, verify with hash
    return compute_hash(path) != get_stored_hash(path)
```

#### 2. Vector Search Initialization
**Problem:** First search call initializes localvectordb (loads embeddings model).

**Current Mitigation:** Lazy loading via `@property`.

**Potential Optimization:** Background thread pre-warm on first CLI invocation.

#### 3. Todo Hierarchy Loading
**Problem:** `get_todo_children()` uses recursion for nested todos.

**Current Mitigation:** Most todos are top-level.

**Risk:** Deep nesting could cause stack issues (unlikely in practice).

#### 4. No Background Indexing
**Problem:** All indexing is synchronous on CLI commands.

**Potential Optimization:** File watcher daemon:
```bash
# Hypothetical
nb daemon start   # Background indexing service
nb daemon stop
```

### Implemented Optimizations

1. **mtime-based Change Detection** (schema v5) - Fast O(1) skip for unchanged files
2. **Database Indexes** - Optimized queries on due_date, status, section, mtime
3. **Lazy Vector Initialization** - Only load embeddings when needed

### Potential Future Optimizations

1. **Parallel File Processing** - Use `concurrent.futures` for indexing
2. **Optional Daemon Mode** - Background file watcher
3. **Index-Only Mode** - Skip vector indexing for faster `nb todo`

---

## Frequently Asked Questions

### How do tags work?

Tags are supported on **both notes and todos** but work slightly differently:

**Note Tags** (extracted in `nb/utils/markdown.py:77-101`):
1. **Frontmatter tags** - YAML `tags:` field
   ```yaml
   ---
   tags: [meeting, project-x]
   ---
   ```
2. **Inline tags** - `#tag` patterns in the body text
   ```markdown
   This is about #planning and #architecture
   ```
3. Both sources are combined (deduplicated, lowercased, sorted)
4. Stored in `note_tags` table (many-to-many relationship)
5. Indexed in vector search metadata for filtering

**Todo Tags** (extracted in `nb/core/todos.py:60-62`):
1. **Inline only** - `#tag` patterns in the todo text
   ```markdown
   - [ ] Review PR #urgent #code-review
   ```
2. Tags are stripped from displayed content but preserved for filtering
3. Stored in `todo_tags` table (many-to-many relationship)

**Filtering by tag:**
```bash
nb search -t meeting          # Notes with #meeting tag
nb todo -t urgent             # Todos with #urgent tag
```

---

### Are attachments indexed for vector search?

**No.** Attachments are **not** included in the vector search index.

Looking at `nb/index/search.py:96-115`, the `index_note()` function only indexes:
- Document content (note body text)
- Metadata: path, title, notebook, date, tags

Attachments are:
- Stored in the `attachments` SQLite table
- Associated with notes or todos via `parent_type` and `parent_id`
- Can be listed with `nb attach list`
- **Not searchable** via semantic or keyword search

**Potential Enhancement:** Could index attachment filenames/titles as metadata, or OCR/parse PDF/text attachments for full content indexing.

---

### Can notes be tagged as well as todos?

**Yes!** Both support tags:

| Feature | Notes | Todos |
|---------|-------|-------|
| Frontmatter tags | ✅ `tags: [a, b]` | ❌ |
| Inline #tags | ✅ | ✅ |
| Storage | `note_tags` table | `todo_tags` table |
| Search filter | `nb search -t tag` | `nb todo -t tag` |
| Vector metadata | ✅ | ❌ |

---

### Does it track when todo items are added/detected?

**Partially.** The `created_date` field exists but has limitations:

**How it works** (`nb/core/todos.py:105-108`):
```python
created_date = parse_date_from_filename(path.name) or date.today()
```

| Source File | `created_date` Value |
|-------------|---------------------|
| `daily/2025/01/2025-01-15.md` | `2025-01-15` (from filename) |
| `projects/roadmap.md` | Today's date (when indexed) |
| Linked external file | Today's date (when indexed) |

**Limitations:**
1. It's not the actual "creation time" of the todo
2. For non-dated files, it's the indexing date (resets if DB rebuilt)
3. No tracking of when a todo was first detected vs. modified

---

### How does the in-progress status work?

Use `[^]` checkbox syntax to mark a todo as in-progress:

```markdown
- [ ] Pending task
- [^] Started but not done
- [x] Completed task
```

**Commands:**
```bash
nb todo start <id>    # Mark as in-progress
nb todo done <id>     # Mark as completed
nb todo undone <id>   # Reset to pending
```

**Status Flow:**
```
PENDING [ ] ──► IN_PROGRESS [^] ──► COMPLETED [x]
    ▲                                    │
    └────────────────────────────────────┘
                   undone
```

---

### How do note aliases work?

Aliases provide quick access to frequently used notes:

```bash
nb alias standup daily/2025/Nov25-Dec01/2025-11-28.md
nb open standup  # Opens the aliased note
nb alias list    # List all aliases
nb alias remove standup
```

Aliases are stored in the `note_aliases` database table (schema v11).

---

### What is the week folder structure?

Date-based notebooks use week folders for organization:

```
daily/
└── 2025/
    ├── Nov25-Dec01/           # Week folder (Mon-Sun)
    │   ├── 2025-11-25.md
    │   ├── 2025-11-26.md
    │   └── ...
    └── Dec02-Dec08/
        └── ...
```

The `week_start_day` config option controls whether weeks start on Monday or Sunday.

---

### How does todo completion tracking work?

Schema v12 added `completed_date` to track when todos are marked complete:

```sql
UPDATE todos SET status = 'completed', completed_date = '2025-11-28' WHERE id = ?
```

This enables:
- `nb todo all-done` - Show todos completed today
- `nb stats` - Productivity statistics
- Activity tracking over time

---

## Extensibility Points

### Adding Search Backends
Current: localvectordb

Could add:
- Elasticsearch
- Meilisearch
- SQLite FTS5 directly

### Adding File Watchers
Current: None

Could add `watchdog` for live indexing.

### Adding Output Formats
Current: Rich console output

Could add:
- `--json` flag for JSON output
- `--csv` flag for CSV export
- Markdown table output

### Adding Custom Metadata
Could extend frontmatter parsing in `nb/core/notes.py` to support custom fields.

### Adding Templates
Templates are stored in `notes_root/.nb/templates/` as markdown files with variable support:

```markdown
---
title: {{ title }}
date: {{ date }}
tags: [{{ notebook }}]
---

# {{ title }}

Created on {{ datetime }}
```

Variables: `{{ date }}`, `{{ datetime }}`, `{{ notebook }}`, `{{ title }}`

### Adding New Todo Metadata
The todo parsing system in `nb/core/todos.py` can be extended:

1. Add new pattern: `NEW_PATTERN = r"@newfield\((?P<value>[^)]+)\)"`
2. Parse in `extract_todos()` function
3. Add field to `Todo` dataclass in `nb/models.py`
4. Add column in database migration
5. Update `todos_repo.py` for storage/retrieval

---

## Data Flow Examples

### `nb todo done <id>`

```
1. CLI: todo_done(todo_id)
       │
       ├─► _find_todo(todo_id)
       │       └─► Query database by ID (exact or prefix match)
       │
       ├─► toggle_todo_in_file(path, line_number, new_status)
       │       ├─► Check sync permission for linked files
       │       ├─► Read source file
       │       ├─► Match regex, change [ ] or [^] → [x]
       │       └─► Write file back
       │
       ├─► update_todo_status(id, "completed", completed_date=today)
       │       └─► UPDATE todos SET status = 'completed',
       │                          completed_date = ? WHERE id = ?
       │
       └─► Display confirmation
```

### `nb search "query"`

```
1. CLI: search_notes("query")
       │
       ├─► NoteSearch.search(query, "hybrid", k=10)
       │       │
       │       ├─► Generate query embedding (Ollama)
       │       ├─► Query localvectordb
       │       │       ├─► Vector similarity search
       │       │       └─► FTS5 keyword search
       │       ├─► Combine scores (70/30)
       │       └─► Return top k results
       │
       └─► Display results with Rich console
```

---

## Consistency Guarantees

| Guarantee | Implementation |
|-----------|----------------|
| Source of truth | Markdown files (not database) |
| Database | Cache/index, can be rebuilt with `nb index --force` |
| Sync writes | File modified first, then database updated |
| Linked files | Completion only written if `sync=True` |
| Atomic updates | SQLite transactions for consistency |

---

## Summary

The `nb` CLI is a well-architected note-taking tool with:

- **On-demand indexing** with efficient mtime + hash change detection
- **Hybrid search** combining semantic and keyword matching
- **Flexible todo management** with three status states (pending/in-progress/completed)
- **External file linking** for integration with other tools
- **Interactive TUI** for efficient task management with review mode
- **Web interface** for browser-based access
- **Audio recording & transcription** (optional) for meetings
- **Note templates** for consistent note creation
- **Note aliases** for quick access to frequently used notes
- **Saved todo views** for filter presets
- **Activity tracking** with completion dates and statistics

Key areas for potential improvement:
1. Background indexing via file watcher daemon
2. Parallel file processing for large vaults
3. JSON/CSV export formats
