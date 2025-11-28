# nb - Design Document

> This document describes the architecture, data models, and design decisions for nb.
> For usage documentation, see [README.md](README.md).

---

## Overview

`nb` is a command-line tool for managing daily notes and todos in plaintext markdown files. It emphasizes:

- **Plaintext as source of truth** - all data lives in markdown files you can edit directly
- **Date-centric organization** - daily notes organized chronologically, with project notebooks
- **Automatic todo extraction** - GFM-style todos (`- [ ]`) are scanned and surfaced in a unified interface
- **Semantic + keyword search** - find notes by meaning or exact terms
- **Rich TUI** - interactive interfaces built with Wijjit for browsing and managing todos

---

## Core Concepts

### Notes
Markdown files with optional YAML frontmatter. Always associated with a date (explicit or inferred from filename). Can contain tags, wiki-style links, attachments, and todos.

### Notebooks
Folders containing notes. One special `daily/` notebook organized by `YYYY/MM/YYYY-MM-DD.md`. Other notebooks are user-defined (e.g., `projects/`, `work/`).

### Todos
Extracted from notes via GFM checkbox syntax. Stored in a SQLite index for fast querying but always synced back to source files. Support due dates, priorities, tags, subtasks, and attachments.

### Linked Todo Files
External markdown files (e.g., `TODO.md` in repos) that are indexed alongside internal notes. Optionally sync completions back to the source.

---

## Directory Structure

```
~/notes/                        # configurable root
├── daily/
│   └── 2025/
│       └── 11/
│           ├── 2025-11-25.md
│           └── 2025-11-26.md
├── projects/
│   ├── cli-notes/
│   │   └── architecture.md
│   └── webapp/
├── work/
│   └── meetings/
├── todo.md                     # inbox for standalone todos
└── .nb/
    ├── config.yaml
    ├── index.db                # SQLite: notes, todos, attachments, links
    └── vectors/                # localvectordb embeddings
```

---

## Note Format

```markdown
---
date: 2025-11-26
tags: [meeting, api, work]
attachments:
  - url: https://example.com/spec
    title: API Specification
---

# Daily Notes - November 26, 2025

Met with Sarah about the [project architecture](projects/cli-notes/architecture|architecture).

## Action Items

- [ ] Follow up with Sarah re: API docs @due(friday) @priority(1) #urgent
  - [ ] Draft initial outline
  - [ ] Review existing docs
  @attach: ~/docs/api-notes.pdf
- [ ] Review PR #1234 #work
- [x] Send weekly update

## Notes

Some thoughts on the design...
```

### Syntax Elements

| Element    | Syntax               | Example                                               |
|------------|----------------------|-------------------------------------------------------|
| Todo       | `- [ ]` / `- [x]`    | `- [ ] Task here`                                     |
| Due date   | `@due(...)`          | `@due(friday)`, `@due(2025-12-01)`, `@due(next week)` |
| Priority   | `@priority(1\|2\|3)` | `@priority(1)` (1=high, 3=low)                        |
| Tag        | `#tag`               | `#urgent #work`                                       |
| Attachment | `@attach: <path>`    | `@attach: ~/docs/file.pdf`                            |
| Link       | `[title](path)`      | `[API Design](projects/api/design)`                   |
| Subtask    | Indented todo        | `  - [ ] Subtask`                                     |

---

## Commands

### Notes

```bash
nb                              # open today's note (default action)
nb today | t                    # open today's note
nb yesterday | y                # open yesterday's note  
nb <date>                       # fuzzy date: "nov 20", "last friday", "2025-11-20"
nb open <path> | o              # open note in a notebook
nb new <path>                   # create new note (prompts for title)
nb add "<text>"                 # append line to today's note
nb edit <path>                  # open note in $EDITOR
nb attach <note> <path> [--copy]  # attach file/url to note
```

### Notebooks

```bash
nb notebooks | nbs              # list all notebooks
nb notebook create <path>       # create new notebook
nb notebook <name>              # list notes in a notebook
```

### Stream (Continuous View)

```bash
nb stream | st                  # daily notes, scrollable concatenation
nb stream --week                # this week's notes
nb stream --month               # this month
nb stream --range <start> <end> # custom range
nb stream --notebook <name>     # notes from specific notebook
nb stream --tag <tag>           # notes with specific tag
```

### Todos

```bash
nb todo | td                    # list open todos (sorted, grouped)
nb todo -i                      # interactive TUI with keyboard navigation
nb todo add "<text>" | ta       # add to inbox (todo.md)
nb todo done <id>               # mark complete (updates source file)
nb todo undone <id>             # mark incomplete
nb todo edit <id>               # edit todo (opens source at line)
nb todo show <id>               # show details + attachments

# Filters (composable)
--today                         # created today
--week                          # created this week
--overdue                       # past due
-p, --priority <1|2|3>          # by priority level
--project <name>                # from notebook/project
-t, --tag <tag>                 # with tag
--all                           # include completed
```

#### Interactive Mode (`nb todo -i`)

Keyboard shortcuts:
- `j/k` or arrows - navigate up/down
- `Space` - toggle completion
- `e` - edit todo (opens source file at line)
- `c` - toggle showing completed todos
- `g/G` - jump to top/bottom
- `r` - refresh
- `q` - quit

### Linked External Files

#### Linked Todo Files

Track todos from external markdown files (e.g., `TODO.md` in project repos):

```bash
nb link list                    # list all linked files (todos and notes)
nb link add <path>              # link a todo file (uses filename as alias)
nb link add <path> --alias work # link with custom alias
nb link add <path> --no-sync    # link read-only (no completion sync)
nb link remove <alias>          # stop tracking a file
nb link sync                    # re-scan all linked todo files
nb link sync <alias>            # re-scan specific file
nb link enable-sync <alias>     # enable bidirectional sync
nb link disable-sync <alias>    # disable sync (read-only)
```

#### Linked Note Files/Directories

Link external note files or directories to index them as searchable notes:

```bash
nb link note list               # list all linked note sources
nb link note add <path>         # link a file or directory
nb link note add ~/docs/wiki    # link directory (scans .md recursively)
nb link note add <path> --alias docs --notebook external-docs
nb link note add <path> --no-recursive  # don't scan subdirectories
nb link note remove <alias>     # stop tracking
nb link note sync               # re-scan all linked notes
nb link note sync <alias>       # re-scan specific source
```

### Attachments

Attach files or URLs to notes and todos:

```bash
nb attach file <path>           # attach file to today's note
nb attach file <path> --to <note>    # attach to specific note
nb attach file <path> --to <todo-id> # attach to a todo
nb attach file <path> --copy    # copy file to .nb/attachments/
nb attach url <url>             # attach URL to today's note
nb attach list [note]           # list attachments in a note
nb attach open <note> --line N  # open attachment at line N
```

### Search

```bash
nb search "<query>" | s         # hybrid search (70% semantic, 30% keyword)
nb search -s "<query>" | ss     # pure semantic search
nb search -k "<query>"          # pure keyword search
nb search -t <tag>              # by tag
nb search -n <notebook>         # filter by notebook
nb grep "<pattern>"             # regex pattern matching
nb grep "<pattern>" -C 5        # with context lines
nb grep "<pattern>" -i          # case-insensitive (default)
```

### Metadata & Maintenance

```bash
nb tags                         # list all tags with counts
nb links <note>                 # show backlinks to a note
nb stats                        # overview statistics
nb index [--embeddings]         # rebuild index
nb config                       # open config file
```

---

## Todo Sorting

Default sort order (oldest unfinished + soonest due first):

1. **Overdue** - by how overdue (oldest first)
2. **Due today**
3. **Due this week** - by due date
4. **Due later** - by due date
5. **No due date** - by created date (oldest first)

Within each group, secondary sort by priority (1 > 2 > 3 > none).

---

## Configuration

`~/notes/.nb/config.yaml`:

```yaml
# Paths
notes_root: ~/notes
editor: $EDITOR  # or explicit: vim, code, micro, etc.

# Notebooks
notebooks:
  - daily      # special: date-organized
  - projects
  - work
  - personal

# Linked external todo files
linked_todos:
  - path: ~/code/myproject/TODO.md
    alias: myproject
    sync: true    # bidirectional sync (completions update source)

  - path: ~/code/webapp/roadmap.md
    alias: webapp
    sync: false   # read-only (no writes to source)

# Linked external note files/directories
linked_notes:
  - path: ~/docs/wiki
    alias: wiki
    notebook: "@wiki"    # virtual notebook name
    recursive: true      # scan subdirectories

  - path: ~/code/project/docs
    alias: project-docs
    notebook: "@project"

# Embeddings for semantic search (localvectordb)
embeddings:
  provider: ollama           # "ollama" or "openai"
  model: nomic-embed-text    # embedding model name
  # base_url: http://localhost:11434  # custom Ollama endpoint
  # api_key: sk-...          # required for OpenAI

# Display
date_format: "%Y-%m-%d"
time_format: "%H:%M"
```

### Environment Variables

- `NB_NOTES_ROOT` - Override notes root directory
- `EDITOR` - Default editor for opening notes

---

## Data Models

### Note

```python
@dataclass
class Note:
    path: Path                      # relative to notes root
    title: str                      # from H1 or filename
    date: date | None               # from frontmatter or filename
    tags: list[str]
    links: list[str]                # outgoing [[wiki]] links
    attachments: list[Attachment]
    notebook: str                   # parent folder
    content_hash: str               # for change detection
```

### Todo

```python
@dataclass
class Todo:
    id: str                         # hash(source_path + content + line_number)
    content: str                    # cleaned text (without metadata markers)
    raw_content: str                # original line content
    completed: bool
    source: TodoSource
    line_number: int
    created_date: date
    due_date: date | None
    priority: Priority | None       # 1, 2, 3
    tags: list[str]
    project: str | None             # inferred from notebook
    parent_id: str | None           # for subtasks
    children: list[Todo]
    attachments: list[Attachment]

class Priority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3

@dataclass
class TodoSource:
    type: Literal["note", "inbox", "linked"]
    path: Path
    external: bool                  # outside notes root
    alias: str | None               # for linked files
```

### Attachment

```python
@dataclass
class Attachment:
    id: str
    type: Literal["file", "url", "conversation"]
    path: str                       # local path or URL
    title: str | None
    added_date: date
    copied: bool                    # local copy exists in attachments/
```

---

## Database Schema (SQLite)

```sql
-- Notes
CREATE TABLE notes (
    path TEXT PRIMARY KEY,
    title TEXT,
    date TEXT,
    notebook TEXT,
    content_hash TEXT,
    updated_at TEXT
);

CREATE TABLE note_tags (
    note_path TEXT REFERENCES notes(path) ON DELETE CASCADE,
    tag TEXT,
    PRIMARY KEY (note_path, tag)
);

CREATE TABLE note_links (
    source_path TEXT REFERENCES notes(path) ON DELETE CASCADE,
    target_path TEXT,
    display_text TEXT,
    PRIMARY KEY (source_path, target_path)
);

-- Todos
CREATE TABLE todos (
    id TEXT PRIMARY KEY,
    content TEXT,
    raw_content TEXT,
    completed INTEGER DEFAULT 0,
    source_type TEXT,               -- 'note', 'inbox', 'linked'
    source_path TEXT,
    source_external INTEGER DEFAULT 0,
    source_alias TEXT,
    line_number INTEGER,
    created_date TEXT,
    due_date TEXT,
    priority INTEGER,
    project TEXT,
    parent_id TEXT REFERENCES todos(id),
    content_hash TEXT
);

CREATE TABLE todo_tags (
    todo_id TEXT REFERENCES todos(id) ON DELETE CASCADE,
    tag TEXT,
    PRIMARY KEY (todo_id, tag)
);

-- Attachments (polymorphic)
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    parent_type TEXT,               -- 'note' or 'todo'
    parent_id TEXT,
    type TEXT,                      -- 'file', 'url', 'conversation'
    path TEXT,
    title TEXT,
    added_date TEXT,
    copied INTEGER DEFAULT 0
);

-- Linked files
CREATE TABLE linked_files (
    alias TEXT PRIMARY KEY,
    path TEXT UNIQUE,
    sync INTEGER DEFAULT 1
);

-- Indexes
CREATE INDEX idx_todos_due ON todos(due_date);
CREATE INDEX idx_todos_completed ON todos(completed);
CREATE INDEX idx_todos_project ON todos(project);
CREATE INDEX idx_todos_source ON todos(source_path);
CREATE INDEX idx_notes_date ON notes(date);
CREATE INDEX idx_notes_notebook ON notes(notebook);

-- FTS for keyword search
CREATE VIRTUAL TABLE notes_fts USING fts5(
    path, title, content,
    content='notes',
    content_rowid='rowid'
);
```

---

## Project Structure

```
nb-cli/
├── pyproject.toml
├── README.md
├── nb/
│   ├── __init__.py
│   ├── cli.py                  # Click CLI entry point
│   ├── config.py               # config loading, paths, defaults
│   ├── models.py               # dataclasses (Note, Todo, Attachment)
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── notes.py            # note CRUD, frontmatter parsing
│   │   ├── todos.py            # todo extraction, completion sync
│   │   ├── attachments.py      # attachment management (link/copy)
│   │   ├── notebooks.py        # notebook operations
│   │   └── links.py            # linked external todo files
│   │
│   ├── index/
│   │   ├── __init__.py
│   │   ├── db.py               # SQLite connection, schema, migrations
│   │   ├── scanner.py          # filesystem scanning, indexing
│   │   ├── search.py           # unified search (localvectordb + grep)
│   │   └── todos_repo.py       # todo database operations
│   │
│   ├── tui/
│   │   ├── __init__.py
│   │   └── todos.py            # interactive todo viewer
│   │
│   └── utils/
│       ├── __init__.py
│       ├── dates.py            # fuzzy date parsing
│       ├── editor.py           # open $EDITOR at line
│       └── hashing.py          # content hashing for IDs
│
└── tests/
    └── ...
```

---

## TUI Design (Wijjit)

### Todo List View (`nb todo -i`)

```
┌─ Todos ─────────────────────────────────────── 12 open ─┐
│ Filter: all                              [/] to filter  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ OVERDUE                                                 │
│ ○ Call the dentist                       Nov 24  !1    │
│                                                         │
│ DUE TODAY                                               │
│ ○ Ship the API                       @due(today)  #work │
│   ○ Write documentation                                 │
│   ○ Get review from Sarah                               │
│   ● Write tests                                         │
│                                                         │
│ DUE THIS WEEK                                           │
│ ○ Follow up with Sarah              @due(Fri)  #urgent │
│ ○ Review PR #1234                   @due(Thu)  #work   │
│                                                         │
│ NO DUE DATE                                             │
│ ○ Research vector DB options                   Nov 20  │
│ ○ Update documentation                         Nov 18  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ ↑↓ navigate  ␣ toggle  o open  e edit  / filter  q quit │
└─────────────────────────────────────────────────────────┘
```

**Keybindings:**
- `j/k` or `↑/↓` - navigate
- `Space` or `Enter` - toggle completion
- `o` - open source note at line in editor
- `e` - edit todo inline
- `/` - filter (fuzzy, or `#tag`, `@due:week`, `@priority:1`)
- `Tab` - cycle grouping (none → project → due → tag)
- `c` - toggle showing completed
- `a` - add new todo to inbox
- `?` - help
- `q` - quit

### Stream View (`nb stream`)

```
┌─ Stream: Daily ─────────────────────── Nov 26 → Nov 20 ─┐
│                                                         │
│ ═══════════════════════════════════════════════════════ │
│  November 26, 2025 (today)              daily/2025/11   │
│ ═══════════════════════════════════════════════════════ │
│                                                         │
│ Met with Sarah about the [[architecture]].              │
│                                                         │
│ - [ ] Follow up with Sarah re: API docs #urgent        │
│ - [ ] Review PR #1234                                   │
│ - [x] Send weekly update                                │
│                                                         │
│ ═══════════════════════════════════════════════════════ │
│  November 25, 2025                      daily/2025/11   │
│ ═══════════════════════════════════════════════════════ │
│                                                         │
│ Worked on the email CLI. Got IMAP sync working.         │
│                                                         │
│ - [x] Fix IMAP connection pooling                       │
│                                                         │
│ ░░░░░░░░░░░░░░░░ loading more... ░░░░░░░░░░░░░░░░░░░░░ │
├─────────────────────────────────────────────────────────┤
│ ↑↓ scroll  o open  / search  g goto  ␣ toggle todo  q   │
└─────────────────────────────────────────────────────────┘
```

**Keybindings:**
- `j/k` or scroll - smooth scroll through content
- `Page Up/Down` - jump by note
- `o` - open note under cursor in editor
- `/` - grep search within stream (shows context or highlights)
- `g` - goto specific date
- `f` - filter by tag
- `Space/Enter` on todo - toggle completion
- `Enter` on `[[link]]` - navigate (backspace to return)
- `q` - quit

### Grep Results in Stream

When searching with `/`:

```
┌─ Search: "API" ────────────────────────── 3 matches ────┐
│                                                         │
│ daily/2025/11/2025-11-26.md:5                          │
│   Met with Sarah about the API design.                  │
│                                                         │
│ daily/2025/11/2025-11-26.md:12                         │
│   - [ ] Follow up with Sarah re: [API] docs #urgent    │
│                                                         │
│ projects/cli-notes/architecture.md:42                   │
│   The REST [API] should follow standard conventions...  │
│   We'll use OpenAPI for documentation.                  │
│   Authentication via bearer tokens.                     │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ ↑↓ navigate  Enter open  n next  N prev  Esc clear      │
└─────────────────────────────────────────────────────────┘
```

---

## Integration: localvectordb

Semantic search uses `localvectordb` for embeddings:

```python
from localvectordb import VectorDB
from nb.config import get_config

def get_vector_db() -> VectorDB:
    config = get_config()
    return VectorDB(
        name="notes",
        path=config.notes_root / ".nb" / "vectors",
        embedding_provider=config.embeddings.provider,
        embedding_model=config.embeddings.model,
        chunking_method="paragraphs",
        chunk_size=500,
    )

def index_note(note: Note, content: str):
    db = get_vector_db()
    db.upsert(
        documents=[content],
        metadata=[{
            "path": str(note.path),
            "title": note.title,
            "date": note.date.isoformat() if note.date else None,
            "notebook": note.notebook,
            "tags": note.tags,
        }],
        ids=[str(note.path)],
    )

def semantic_search(query: str, k: int = 10, filters: dict = None):
    db = get_vector_db()
    return db.query(query, search_type="hybrid", k=k, filters=filters)
```

---

## Key Algorithms

### Todo Extraction

```python
import re
from dataclasses import dataclass

TODO_RE = re.compile(r'^(?P<indent>\s*)- \[(?P<done>[ xX])\] (?P<content>.+)$')
DUE_RE = re.compile(r'@due\((?P<date>[^)]+)\)')
PRIORITY_RE = re.compile(r'@priority\((?P<level>[123])\)')
TAG_RE = re.compile(r'#(\w+)')
ATTACH_RE = re.compile(r'^\s*@attach:\s*(.+)$')

def extract_todos(filepath: Path) -> list[Todo]:
    todos = []
    stack = []  # for tracking parent todos by indent
    
    with open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            match = TODO_RE.match(line)
            if not match:
                # Check for attachment line
                if stack and ATTACH_RE.match(line):
                    attach_path = ATTACH_RE.match(line).group(1)
                    stack[-1].attachments.append(parse_attachment(attach_path))
                continue
            
            indent = len(match.group('indent'))
            content = match.group('content')
            completed = match.group('done').lower() == 'x'
            
            # Parse metadata from content
            due = parse_fuzzy_date(DUE_RE.search(content))
            priority = int(m.group('level')) if (m := PRIORITY_RE.search(content)) else None
            tags = TAG_RE.findall(content)
            clean = clean_content(content)  # remove @due, @priority, #tags
            
            todo = Todo(
                id=make_id(filepath, clean, line_num),
                content=clean,
                raw_content=content,
                completed=completed,
                line_number=line_num,
                due_date=due,
                priority=priority,
                tags=tags,
                # ... other fields
            )
            
            # Handle nesting
            while stack and stack[-1][0] >= indent:
                stack.pop()
            
            if stack:
                parent = stack[-1][1]
                todo.parent_id = parent.id
                parent.children.append(todo)
            
            stack.append((indent, todo))
            todos.append(todo)
    
    return todos
```

### Todo Completion Sync

```python
def toggle_todo(todo_id: str) -> bool:
    """Toggle todo completion, update source file."""
    todo = db.get_todo(todo_id)
    if not todo:
        return False
    
    # Read source file
    lines = todo.source.path.read_text().splitlines()
    line = lines[todo.line_number - 1]
    
    # Toggle checkbox
    if todo.completed:
        new_line = line.replace('[x]', '[ ]').replace('[X]', '[ ]')
    else:
        new_line = line.replace('[ ]', '[x]')
    
    lines[todo.line_number - 1] = new_line
    
    # Write back
    todo.source.path.write_text('\n'.join(lines) + '\n')
    
    # Update database
    todo.completed = not todo.completed
    db.update_todo(todo)
    
    return True
```

---

## Implementation Phases

### Phase 1: Core Foundation ✅
- [x] Project scaffolding, config, CLI skeleton
- [x] Note model, daily note creation/opening
- [x] Basic notebook support
- [x] SQLite schema and migrations

### Phase 2: Todo System ✅
- [x] Todo extraction from markdown
- [x] Todo listing with filters and sorting
- [x] Completion toggling with source sync
- [x] Subtask support
- [x] `todo.md` inbox

### Phase 3: Search & Index ✅
- [x] Filesystem scanner with change detection
- [x] Unified search via localvectordb (keyword, semantic, hybrid)
- [x] Grep for regex pattern matching
- [x] Tag and backlink indexing
- [x] Linked external todo files with bidirectional sync
- [x] Attachments (link + copy modes)
- [x] Basic interactive todo TUI (`nb todo -i`)

### Phase 4: Advanced TUI
- [ ] Full Wijjit todo list view
- [ ] Stream/continuous view with lazy loading
- [ ] Grep search in stream
- [ ] Interactive filtering

### Phase 5: Advanced Features
- [ ] Wiki-link navigation
- [ ] Due date reminders (optional)

---

## Dependencies

```toml
[project]
dependencies = [
    "click>=8.0",
    "pyyaml>=6.0",
    "python-dateutil>=2.8",    # fuzzy date parsing
    "python-frontmatter>=1.0", # yaml frontmatter
    "wijjit",                  # TUI framework
    "localvectordb",           # semantic search
    "rich>=13.0",              # pretty printing in CLI
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov",
    "black",
    "ruff",
    "mypy",
]
```

---

## Design Decisions

1. **Todo ID stability** - Hash of (filepath + content + line_number). If content changes, old todo is "deleted" and new one "added". No need to track edit history of individual todos.

2. **Command structure** - `nb` opens today's note (note-centric default). `nb todo` is the entry point for todo management.

3. **Search distinction** - `nb search` for FTS5/semantic search, `nb grep` for literal pattern matching with context lines. Clear separation of use cases.

## Open Questions

1. **Conflict handling** - If a file is edited externally while TUI is open, we reload on focus. Should we detect conflicts more gracefully, or is simple reload sufficient?

2. **Recurring todos** - Syntax like `@recur(weekly)` is appealing but adds complexity. Defer to future version.

3. **Mobile/sync** - Notes are plaintext so work with any sync (Dropbox, git, Syncthing). Leave sync to external tools.

4. **Archive behavior** - When a daily note gets old, should it move to an archive? Or just leave the directory structure flat by year/month? (Leaning toward: leave flat, the YYYY/MM structure is sufficient organization.)