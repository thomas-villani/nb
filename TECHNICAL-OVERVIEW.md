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
11. [Performance Analysis & Optimization](#performance-analysis--optimization)
12. [Frequently Asked Questions](#frequently-asked-questions)
13. [Extensibility Points](#extensibility-points)

---

## Architecture Overview

The `nb` CLI is a note-taking and task management tool built with Python. It follows a layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer (click)                      │
│                        nb/cli.py                            │
├─────────────────────────────────────────────────────────────┤
│                      TUI Layer (rich)                       │
│                      nb/tui/todos.py                        │
├─────────────────────────────────────────────────────────────┤
│                    Core Business Logic                      │
│    nb/core/notes.py  |  todos.py  |  links.py  |  attachments.py │
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

---

## Project Structure

```
nb-cli/
├── nb/                          # Main application package
│   ├── cli.py                   # CLI entry point (click commands)
│   ├── config.py                # Configuration management
│   ├── models.py                # Data models (Note, Todo, etc.)
│   ├── core/                    # Core business logic
│   │   ├── notebooks.py         # Notebook operations
│   │   ├── notes.py             # Note file operations
│   │   ├── todos.py             # Todo extraction & manipulation
│   │   ├── attachments.py       # Attachment management
│   │   └── links.py             # Linked files management
│   ├── index/                   # Indexing & search
│   │   ├── db.py                # SQLite database layer
│   │   ├── scanner.py           # File scanning & indexing
│   │   ├── search.py            # Search engine (vector + FTS)
│   │   └── todos_repo.py        # Todo database queries
│   ├── tui/                     # Text User Interface
│   │   └── todos.py             # Interactive todo viewer
│   └── utils/                   # Utilities
│       ├── dates.py             # Date parsing & formatting
│       ├── hashing.py           # ID & hash generation
│       ├── markdown.py          # Markdown parsing
│       └── editor.py            # External editor integration
├── pyproject.toml               # Project metadata & dependencies
└── .nb/                         # Application data directory
    ├── config.yaml              # User configuration
    ├── index.db                 # SQLite database
    ├── vectors/                 # localvectordb storage
    └── attachments/             # Copied attachments
```

**Key Dependencies:**
- `click` (8.0+) - CLI framework
- `rich` (13.0+) - Pretty console output and TUI
- `python-frontmatter` (1.0+) - YAML frontmatter parsing
- `python-dateutil` (2.8+) - Fuzzy date parsing
- `localvectordb` - Vector embeddings for semantic search
- `pyyaml` (6.0+) - YAML configuration

---

## Core Data Models

**Location:** `nb/models.py`

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
    completed: bool
    source: TodoSource     # Where this todo came from
    line_number: int       # 1-based line in source file
    created_date: date | None
    due_date: date | None  # Parsed from @due(...)
    priority: Priority | None  # From @priority(1|2|3)
    tags: list[str]        # From #tag syntax
    project: str | None    # Inferred from path
    parent_id: str | None  # For subtasks
    children: list[Todo]   # Nested todos
    attachments: list[Attachment]

    @property
    def is_overdue(self) -> bool

    @property
    def is_due_today(self) -> bool
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

---

## Configuration System

**Location:** `nb/config.py`

### Config File Location
`~/.nb/config.yaml` (within notes_root)

### Configuration Hierarchy
```yaml
notes_root: ~/notes        # Base directory
editor: code               # Default editor ($EDITOR overrides)
date_format: "%Y-%m-%d"
time_format: "%H:%M"

notebooks:
  - name: daily
    date_based: true       # Uses YYYY/MM/YYYY-MM-DD.md structure
  - name: projects
  - name: work

linked_todos:              # External todo files
  - path: ~/work/tasks.md
    alias: work
    sync: true             # Write completion changes back

linked_notes:              # External note directories
  - path: ~/obsidian/vault
    alias: obsidian
    recursive: true

embeddings:
  provider: ollama         # or "openai"
  model: nomic-embed-text
  base_url: http://localhost:11434
```

### Derived Paths
```python
config.nb_dir           # notes_root/.nb
config.db_path          # notes_root/.nb/index.db
config.vectors_path     # notes_root/.nb/vectors
config.attachments_path # notes_root/.nb/attachments
```

### Environment Variables
```bash
NB_NOTES_ROOT     # Override default ~/notes
EDITOR            # Override configured editor
OPENAI_API_KEY    # For OpenAI embeddings
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
- [ ] Task description @due(friday) @priority(1) #urgent
  - [ ] Subtask (indentation creates hierarchy)
- [x] Completed task
@attach: ~/docs/file.pdf   # Attachment for previous todo
```

### Parsing Patterns

```python
TODO_PATTERN = r"^(?P<indent>\s*)- \[(?P<done>[ xX])\] (?P<content>.+)$"
DUE_PATTERN = r"@due\((?P<date>[^)]+)\)"
PRIORITY_PATTERN = r"@priority\((?P<level>[123])\)"
TAG_PATTERN = r"#(\w+)"
ATTACH_PATTERN = r"^\s*@attach:\s*(.+)$"
```

### Extraction Algorithm

```
extract_todos(path)
    │
    ├─► Skip code blocks (track ``` fences)
    │
    ├─► For each line:
    │       ├─► Match TODO_PATTERN
    │       ├─► Parse metadata (@due, @priority, #tags)
    │       ├─► Clean content (remove metadata markers)
    │       └─► Build hierarchy from indentation
    │
    ├─► Handle @attach lines (belong to previous todo)
    │
    └─► Return list[Todo] with parent-child relationships
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

### Schema Version: 4

Auto-migrates on startup; backward compatible.

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
    external INTEGER,       -- 0=internal, 1=linked
    source_alias TEXT,
    updated_at TEXT
);
```

#### todos
```sql
CREATE TABLE todos (
    id TEXT PRIMARY KEY,
    content TEXT,
    raw_content TEXT,
    completed INTEGER,
    source_type TEXT,       -- note|inbox|linked
    source_path TEXT,
    source_external INTEGER,
    source_alias TEXT,
    line_number INTEGER,
    created_date TEXT,
    due_date TEXT,
    priority INTEGER,       -- 1|2|3
    project TEXT,
    parent_id TEXT REFERENCES todos(id) ON DELETE CASCADE,
    content_hash TEXT
);
```

#### Indexes

```sql
-- Performance-critical indexes
CREATE INDEX idx_todos_due ON todos(due_date);
CREATE INDEX idx_todos_completed ON todos(completed);
CREATE INDEX idx_todos_project ON todos(project);
CREATE INDEX idx_todos_source ON todos(source_path);
CREATE INDEX idx_todos_parent ON todos(parent_id);
CREATE INDEX idx_todo_tags_tag ON todo_tags(tag);

CREATE INDEX idx_notes_date ON notes(date);
CREATE INDEX idx_notes_notebook ON notes(notebook);
```

---

## CLI Commands

**Location:** `nb/cli.py`

### Notes Management

| Command | Description |
|---------|-------------|
| `nb` | Open today's daily note |
| `nb t` | Alias for today |
| `nb y` | Open yesterday's note |
| `nb o` | Open specific date |
| `nb new <path>` | Create new note |
| `nb edit <path>` | Edit existing note |
| `nb add "<text>"` | Append to today's note |
| `nb list` | List notes |
| `nb notebooks` | Show all notebooks |

### Todos

| Command | Description |
|---------|-------------|
| `nb todo` | List todos (triggers indexing) |
| `nb todo -i` | Interactive TUI mode |
| `nb todo add "<text>"` | Add to inbox |
| `nb todo done <id>` | Mark complete |
| `nb todo undone <id>` | Mark incomplete |
| `nb todo show <id>` | Show details |
| `nb todo edit <id>` | Edit source at line |

**Filtering:**
```bash
nb todo --today          # Due today
nb todo --week           # Due this week
nb todo --overdue        # Past due
nb todo -p 1             # High priority only
nb todo -t urgent        # Tagged #urgent
nb todo --project work   # Specific project
nb todo --all            # Include completed
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

---

## Text User Interface (TUI)

**Location:** `nb/tui/todos.py`

### Interactive Mode: `nb todo -i`

Uses Rich library for rendering. Displays todos in a navigable table with color coding.

### Color Coding

| Condition | Style |
|-----------|-------|
| Overdue | Red bold |
| Due today | Yellow bold |
| Due this week | Cyan |
| Due later | Dim |
| Completed | Strikethrough green |

### Controls

| Key | Action |
|-----|--------|
| `j/k` or arrows | Navigate up/down |
| `Space` | Toggle completion |
| `e` | Edit (opens source at line) |
| `c` | Toggle showing completed |
| `g/G` | Jump to top/bottom |
| `r` | Refresh todos |
| `q` | Quit |

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

**Current Mitigation:** Content hash change detection skips unchanged files.

**Potential Optimization:**
```python
# Cache directory structure with mtime checking
def scan_notes_incremental():
    cached_mtimes = load_mtime_cache()
    for path in walk_directory():
        if path.stat().st_mtime > cached_mtimes.get(path, 0):
            yield path  # Only yield potentially changed files
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

### Recommended Optimizations

1. **Incremental Directory Scan** - Track directory mtimes
2. **Parallel File Processing** - Use `concurrent.futures` for indexing
3. **Optional Daemon Mode** - Background file watcher
4. **Index-Only Mode** - Skip vector indexing for faster `nb todo`

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

**Potential Enhancement:**
- Store first-seen timestamp in database
- Preserve across reindexing
- Track modification history

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

---

## Data Flow Examples

### `nb todo done <id>`

```
1. CLI: todo_done(todo_id)
       │
       ├─► _find_todo(todo_id)
       │       └─► Query database by ID (exact or prefix match)
       │
       ├─► toggle_todo_in_file(path, line_number)
       │       ├─► Check sync permission for linked files
       │       ├─► Read source file
       │       ├─► Match regex, change [ ] → [x]
       │       └─► Write file back
       │
       ├─► update_todo_completion(id, True)
       │       └─► UPDATE todos SET completed = 1 WHERE id = ?
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

- **On-demand indexing** with efficient change detection
- **Hybrid search** combining semantic and keyword matching
- **Flexible todo management** with rich metadata support
- **External file linking** for integration with other tools
- **Interactive TUI** for efficient task management

Key areas for potential improvement:
1. Background indexing for faster startup
2. Incremental directory scanning
3. Parallel file processing
4. Optional daemon mode for live updates
