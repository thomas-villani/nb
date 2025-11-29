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

# Show today's note in console (instead of opening editor)
nb -s

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
nb                        # Open today's note (default action)
nb -n work                # Open today's note in work notebook
nb -s                     # Show today's note in console
nb -s -n work             # Show today's note in work notebook

nb today                  # Same as `nb`
nb today -n work          # Today's note in work notebook
nb yesterday              # Open yesterday's note

nb open "nov 25"          # Open note for a specific date
nb open "last friday"     # Fuzzy date parsing
nb open friday -n work    # Open Friday's note in work notebook
nb open myproject -n ideas  # Open ideas/myproject.md

nb show                   # Show today's note in console
nb show friday            # Show Friday's daily note
nb show -n work           # Show today in work notebook
nb show friday -n work    # Show Friday in work notebook
nb show myproject -n ideas  # Show ideas/myproject.md

nb last                   # Open last modified note
nb last -s                # Show last modified note in console
nb last -n work           # Last modified note in work notebook
nb last --viewed          # Open last viewed note (instead of modified)
nb last --viewed -n work  # Last viewed note in work notebook

nb history                # Show recently viewed notes
nb history -l 50          # Show last 50 viewed notes
nb history -n work        # Filter by notebook
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
nb list -n work            # List notes in work notebook

nb stream                  # Browse all notes interactively
nb stream -n daily         # Browse daily notes
nb stream -w "last week"   # Browse last week's notes
nb stream -n daily -w "last 2 weeks"  # Daily notes from last 2 weeks
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
  - [ ] Subtask (nested todos are supported)
```

#### Commands

```bash
nb todo                 # List all open todos (grouped by due date)
nb todo -f              # Focus mode: hide "due later" and "no date" sections
nb todo -a              # Include todos from all sources (even excluded notebooks)
nb todo -c              # Include completed todos
nb todo -n daily        # Show todos from a specific notebook
nb todo --overdue       # Show overdue todos only
nb todo -t work         # Filter by tag
nb todo -T waiting      # Exclude todos with a tag
nb todo -p 1            # Filter by priority (1=high, 2=medium, 3=low)

# Date filters
nb todo --created-today # Show todos created today
nb todo --created-week  # Show todos created this week
nb todo --due-today     # Show todos due today
nb todo --due-week      # Show todos due this week

# Sorting
nb todo -s tag          # Sort by first tag (default: source)
nb todo -s priority     # Sort by priority
nb todo -s created      # Sort by creation date

nb todo add "New task"  # Add to inbox (todo.md)
nb todo add --today "Call dentist"  # Add to today's note
nb todo done abc123     # Mark complete (by ID prefix)
nb todo undone abc123   # Mark incomplete
nb todo show abc123     # Show todo details
nb todo edit abc123     # Open source file at todo line
```

Todos are grouped by due date: OVERDUE, DUE TODAY, DUE THIS WEEK, DUE NEXT WEEK, DUE LATER, NO DUE DATE.

Todos can be hidden from `nb todo` at two levels:
- **Notebook-level**: Set `todo_exclude: true` in notebook config
- **Note-level**: Set `todo_exclude: true` in note frontmatter

Use `-a/--all` to include all todos, or `-n <notebook>` to view a specific notebook.

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

### Search

```bash
nb search "query"       # Hybrid search (semantic + keyword)
nb search -s "query"    # Semantic search only
nb search -k "query"    # Keyword search only
nb search -t mytag      # Filter by tag
nb search -n daily      # Filter by notebook
nb search "query" --when "last 2 weeks"  # Date range filter
nb search "query" --since friday         # From a date onwards
nb search "query" --recent               # Boost recent results

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
nb link add ~/docs/wiki --notes-only
nb link add ~/vault --alias vault -n @vault
nb link add ~/docs --no-recursive
nb link list
nb link sync
nb link remove wiki
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
```

### Configuration Commands

```bash
nb config                       # Open config file in editor
nb config get editor            # Get a setting value
nb config set editor code       # Set a setting value
nb config list                  # List all configurable settings

# Configurable settings:
nb config set editor vim        # Text editor command
nb config set date_format "%Y-%m-%d"  # Date display format
nb config set time_format "%H:%M"     # Time display format
nb config set embeddings.provider ollama  # Embeddings provider
nb config set embeddings.model nomic-embed-text  # Embeddings model
nb config set embeddings.base_url http://localhost:11434  # Custom endpoint
nb config set embeddings.api_key sk-...  # API key (for OpenAI)
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

Notes are markdown files with optional YAML frontmatter.

### Frontmatter

Frontmatter is optional YAML metadata at the top of the file:

```yaml
---
date: 2025-11-27
title: Meeting Notes
tags: [meeting, project, quarterly]
todo_exclude: true  # Hide todos from this note in nb todo
---
```

| Field | Description |
|-------|-------------|
| `date` | Note date (YYYY-MM-DD format) |
| `title` | Note title (used in search results) |
| `tags` | List of tags for filtering |
| `todo_exclude` | Hide todos from `nb todo` (use `-a` or `-n` to view) |

### Todos

Todos use GitHub-style checkboxes with optional metadata:

```markdown
- [ ] Incomplete task
- [x] Completed task
  - [ ] Nested subtask
  - [x] Completed subtask
```

#### Multi-line Details

Indented content below a todo is captured as details. This is useful for adding context, notes, or sub-items that aren't separate todos:

```markdown
- [ ] Develop presentation for sales:
   - need to include intro slides
   - use the new images
   It would be best to build off the 2024 deck
- [ ] Update website
```

The indented lines become part of the first todo's details. View them with `nb todo show <id>`:

```
Develop presentation for sales:
ID: abc123
Status: Open
Source: daily/2025-11-27.md:5

Details:
   - need to include intro slides
   - use the new images
   It would be best to build off the 2024 deck
```

Note: Indented `- [ ]` checkboxes are treated as subtasks, not details.

#### Todo Metadata

Metadata can be added inline after the todo text:

| Element | Syntax | Examples |
|---------|--------|----------|
| Due date | `@due(...)` | `@due(friday)`, `@due(2025-12-01)`, `@due(next week)`, `@due(tomorrow)` |
| Priority | `@priority(1\|2\|3)` | `@priority(1)` (1=high, 2=medium, 3=low) |
| Tags | `#tag` | `#work`, `#urgent`, `#project-alpha` |

Example todos with metadata:

```markdown
- [ ] Review PR for new feature @due(friday) @priority(1) #code-review
- [ ] Schedule team meeting @due(next monday) #meetings
- [ ] Update documentation @priority(2) #docs #maintenance
- [x] Send project update email #communication
```

### Attachments

Attach files or URLs to notes using the `@attach:` syntax:

```markdown
@attach: ~/Documents/spec.pdf
@attach: ./relative/path/to/file.png
@attach: https://example.com/resource
@attach: [Custom Title](~/path/to/file.pdf)
```

### Complete Example

```markdown
---
date: 2025-11-27
title: Project Kickoff Meeting
tags: [meeting, project, quarterly]
---

# Project Kickoff Meeting

Met with the team to discuss Q1 priorities.

## Attendees

- Alice, Bob, Charlie

## Discussion

Reviewed the roadmap and assigned initial tasks.

## Action Items

- [ ] Write project specification @due(friday) @priority(1) #docs
- [ ] Set up CI/CD pipeline @due(next week) @priority(2) #devops
- [ ] Review competitor analysis @due(dec 15) #research
- [x] Send meeting notes to stakeholders #communication

## Attachments

@attach: ~/Documents/roadmap-2025.pdf
@attach: https://wiki.company.com/project-alpha
```

## Aliases

| Alias | Command |
|-------|---------|
| `t` | `today` |
| `y` | `yesterday` |
| `l` | `last` |
| `o` | `open` |
| `s` | `search` |
| `ss` | `search --semantic` |
| `td` | `todo` |
| `ta` | `todo add` |
| `nbs` | `notebooks` |

## Global Options

These options work with the main `nb` command:

| Option | Description |
|--------|-------------|
| `-s, --show` | Print note to console instead of opening editor |
| `-n, --notebook` | Specify notebook for the default (today) action |
| `--version` | Show version number |
| `--help` | Show help message |

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
