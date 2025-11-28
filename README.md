# nb - Notes & Todos CLI

A plaintext-first command-line tool for managing notes and todos in markdown files.

## Features

- **Daily notes** - Automatic date-organized journal entries with week-based folders
- **Todo management** - Extract and track todos from any markdown file
- **Multiple notebooks** - Organize notes by project, including external directories
- **Unified search** - Keyword, semantic, and hybrid search powered by localvectordb
- **Note streaming** - Browse notes interactively with keyboard navigation
- **Linked files** - Index external todo files and note directories
- **Attachments** - Attach files and URLs to notes and todos
- **Interactive mode** - Keyboard-driven todo management

## Installation

```bash
# Clone the repository
git clone https://github.com/user/nb-cli.git
cd nb-cli

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Requirements

- Python 3.11+
- [Ollama](https://ollama.ai/) (for semantic search, optional)

## Quick Start

```bash
# Open today's daily note
nb

# Add a todo
nb todo add "Review pull request @due(friday) #work"

# List todos
nb todo

# Search notes
nb search "project ideas"
```

## Commands

### Daily Notes

```bash
nb                    # Open today's note (default action)
nb today              # Same as above
nb today -n work      # Open today's note in a specific notebook
nb yesterday          # Open yesterday's note
nb open "nov 25"      # Open note for a specific date
nb open "last friday" # Fuzzy date parsing
```

Date-based notebooks organize notes by work week:
```
daily/2025/Nov25-Dec01/2025-11-27.md
```

### Notes Management

```bash
nb new projects/idea       # Create a new note
nb new -n work             # Create today's note in work notebook
nb new -n ideas my-idea    # Create named note in notebook
nb edit daily/2025-11-27   # Edit an existing note
nb add "Quick thought"     # Append text to today's note
nb list --week             # List this week's daily notes
nb stream daily            # Browse notes interactively
nb stream daily -w "last week"  # Browse last week's notes
```

### Notebook Management

```bash
nb notebooks               # List all notebooks
nb notebooks -v            # Verbose list with note counts
nb notebooks create ideas  # Create a new notebook
nb notebooks create work-log --date-based     # Date-based notebook
nb notebooks create personal --todo-exclude   # Exclude from nb todo
nb notebooks create vault --from ~/Obsidian   # External directory
nb notebooks remove old-project               # Remove from config
```

### Todos

Todos are extracted from markdown files using GitHub-style checkboxes:

```markdown
- [ ] Task to do @due(friday) @priority(1) #urgent
- [x] Completed task
  - [ ] Subtask
```

#### Commands

```bash
nb todo                 # List all open todos
nb todo -n daily        # Show todos from a specific notebook
nb todo -n personal     # View excluded notebook explicitly
nb todo --overdue       # Show overdue todos
nb todo -t work         # Filter by tag
nb todo -p 1            # Filter by priority (1=high, 2=medium, 3=low)
nb todo --all           # Include completed todos

nb todo add "New task"  # Add to inbox (todo.md)
nb todo done abc123     # Mark complete (by ID prefix)
nb todo undone abc123   # Mark incomplete
nb todo show abc123     # Show todo details
nb todo edit abc123     # Open source file at todo line
```

Notebooks with `todo_exclude: true` are hidden from `nb todo` by default.
Use `-n <notebook>` to view them explicitly.

#### Interactive Mode

```bash
nb todo -i              # Launch interactive viewer
```

Keyboard shortcuts:
- `j/k` - Navigate up/down
- `Space` - Toggle completion
- `e` - Edit (open source file)
- `c` - Toggle showing completed
- `g/G` - Jump to top/bottom
- `q` - Quit

#### Metadata Syntax

| Element | Syntax | Example |
|---------|--------|---------|
| Due date | `@due(...)` | `@due(friday)`, `@due(2025-12-01)`, `@due(next week)` |
| Priority | `@priority(1\|2\|3)` | `@priority(1)` (1=high) |
| Tag | `#tag` | `#work #urgent` |

### Search

```bash
nb search "query"       # Hybrid search (semantic + keyword)
nb search -s "query"    # Semantic search only
nb search -k "query"    # Keyword search only
nb search -t mytag      # Filter by tag
nb search -n daily      # Filter by notebook

nb grep "pattern"       # Regex search
nb grep "TODO.*urgent" -C 5  # With context lines
```

### Linked Files

#### Todo Files

Link external todo files (e.g., project TODO.md) to track their todos:

```bash
nb link add ~/code/project/TODO.md
nb link add ~/work/tasks.md --alias work --no-sync
nb link list
nb link sync
nb link remove myproject
```

With `--sync` (default), completing a todo updates the source file.

#### Note Files/Directories

Link external note files or directories to make them searchable:

```bash
nb link note add ~/docs/wiki
nb link note add ~/vault --alias vault --notebook @vault
nb link note add ~/docs --no-recursive
nb link note list
nb link note sync
nb link note remove wiki
```

Linked notes appear under a virtual notebook (prefixed with `@` by default).

### Attachments

```bash
nb attach file ./doc.pdf              # Attach to today's note
nb attach file ./img.png --to note.md # Attach to specific note
nb attach file ./ref.pdf --copy       # Copy to .nb/attachments/
nb attach url https://example.com
nb attach list
nb attach open note.md --line 15
```

### Index & Maintenance

```bash
nb index              # Rebuild notes and todos index
nb index --force      # Force full reindex
nb index --rebuild    # Drop and recreate database (for schema changes)
nb index --embeddings # Rebuild search embeddings
nb config             # Open config file
```

## Configuration

Configuration is stored in `~/notes/.nb/config.yaml`:

```yaml
notes_root: ~/notes
editor: micro  # or vim, code, etc.

# Notebooks (internal and external)
notebooks:
  - name: daily
    date_based: true          # Uses YYYY/Week/YYYY-MM-DD.md structure
  - name: projects
    date_based: false
  - name: work
    date_based: true
  - name: personal
    date_based: false
    todo_exclude: true        # Hidden from `nb todo` by default
  - name: obsidian
    path: ~/Documents/Obsidian/vault   # External directory
    date_based: false

# Linked todo files (for standalone TODO.md files)
linked_todos:
  - path: ~/code/project/TODO.md
    alias: project
    sync: true

# Linked note directories (legacy - prefer external notebooks)
linked_notes:
  - path: ~/docs/wiki
    alias: wiki
    notebook: "@wiki"
    recursive: true

# Semantic search embeddings
embeddings:
  provider: ollama      # or "openai"
  model: nomic-embed-text
```

### Notebook Options

| Option | Description |
|--------|-------------|
| `name` | Notebook name (required) |
| `date_based` | Use week-based date organization |
| `todo_exclude` | Exclude from `nb todo` by default |
| `path` | External directory path (makes notebook external) |

### Environment Variables

- `NB_NOTES_ROOT` - Override notes root directory
- `EDITOR` - Default editor

## Directory Structure

```
~/notes/
├── daily/                    # Date-based notebook
│   └── 2025/
│       ├── Nov18-Nov24/
│       │   └── 2025-11-20.md
│       └── Nov25-Dec01/      # Week folders (Mon-Sun)
│           ├── 2025-11-26.md
│           └── 2025-11-27.md
├── projects/                 # Flat notebook
│   └── myproject.md
├── work/
├── todo.md                   # Todo inbox
└── .nb/
    ├── config.yaml
    ├── index.db              # SQLite database
    ├── vectors/              # Search embeddings
    └── attachments/          # Copied attachments

# External notebook (configured via path:)
~/Documents/Obsidian/vault/   # Indexed as "obsidian" notebook
```

## Note Format

```markdown
---
date: 2025-11-27
tags: [meeting, project]
---

# Meeting Notes

Discussed the new feature with the team.

## Action Items

- [ ] Write documentation @due(friday) @priority(1) #docs
- [ ] Review PR #1234 #work
- [x] Send update email

@attach: ~/docs/spec.pdf
```

## Aliases

| Alias | Command |
|-------|---------|
| `t` | `today` |
| `y` | `yesterday` |
| `o` | `open` |
| `s` | `search` |
| `ss` | `search --semantic` |
| `td` | `todo` |
| `ta` | `todo add` |
| `nbs` | `notebooks` |

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
pytest

# Type checking
mypy nb/

# Linting
ruff check nb/
```

## License

MIT
