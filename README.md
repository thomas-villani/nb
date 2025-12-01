# nb - Notes & Todos CLI

A plaintext-first command-line tool for managing notes and todos in markdown files.

## Features

- **Daily notes** - Automatic date-organized journal entries with week-based folders
- **Note templates** - Create reusable templates with variables for new notes
- **Todo management** - Extract and track todos from any markdown file with in-progress support
- **Todo views** - Save and reuse filter configurations for quick access
- **Statistics dashboard** - View completion rates, activity trends, and breakdowns by notebook/priority/tag
- **Tag management** - List and explore tags with usage counts and source breakdown
- **Multiple notebooks** - Organize notes by project, including external directories
- **Fuzzy finding** - Auto-suggest notebooks and notes when exact match not found
- **Unified search** - Keyword, semantic, and hybrid search powered by localvectordb
- **Note streaming** - Browse notes interactively with keyboard navigation
- **Linked files** - Index external todo files and note directories
- **Attachments** - Attach files and URLs to notes and todos
- **Interactive mode** - Keyboard-driven todo management
- **Web viewer** - Browse notes in a browser with search and todos

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

- Python 3.13+
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
nb open myalias           # Open note by alias (created with nb alias)
nb open friday -n work    # Open Friday's note in work notebook
nb open myproject -n ideas  # Open ideas/myproject.md

nb show                   # Show today's note in console
nb show friday            # Show Friday's daily note
nb show myalias           # Show note by alias
nb show -n work           # Show today in work notebook
nb show friday -n work    # Show Friday in work notebook
nb show myproject -n ideas  # Show ideas/myproject.md

nb last                   # Open last modified note
nb last -s                # Show last modified note in console
nb last -n work           # Last modified note in work notebook
nb last --viewed          # Open last viewed note (instead of modified)
nb last --viewed -n work  # Last viewed note in work notebook

nb history                # Show last 10 viewed notes
nb history -l 50          # Show last 50 viewed notes
nb history -o 10          # Skip first 10, show next 10
nb history -n work        # Filter by notebook
nb history -f             # Show full paths instead of filenames
nb history -g             # Group entries by notebook
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
nb new -n work -T meeting  # Create note using a template
nb edit daily/2025-11-27   # Edit an existing note
nb add "Quick thought"     # Append text to today's note
nb add "Note" --note myproject       # Append to specific note
nb add "Note" --note work/myproject  # Notebook/note format
nb add "Note" -N proj                # Using alias

# Stdin piping support
echo "random thought" | nb add              # Pipe to today's note
cat notes.txt | nb add                      # Pipe file content
git diff --stat | nb add --note work/log    # Pipe command output
pbpaste | nb add                            # Pipe clipboard (macOS)

nb list                    # List latest 3 notes per notebook (with colors/tags)
nb list --all              # List all notes in all notebooks
nb list --week             # List this week's daily notes
nb list --month            # List this month's daily notes
nb list -n work            # List notes in work notebook
nb list -n work --week     # List this week's notes in work notebook
nb list -f                 # Show full paths to notes

nb stream                  # Browse all notes interactively
nb stream -n daily         # Browse daily notes
nb stream -w "last week"   # Browse last week's notes
nb stream -n daily -w "last 2 weeks"  # Daily notes from last 2 weeks
nb stream --recent         # Browse recently viewed notes
nb stream --recently-modified  # Browse recently modified notes
nb stream --recent -l 20   # Last 20 viewed notes
```

### Note Templates

Create reusable templates for new notes with variable substitution:

```bash
nb template list            # List available templates
nb template new meeting     # Create and edit a new template
nb template edit meeting    # Edit an existing template
nb template show meeting    # Display template contents
nb template remove meeting  # Delete a template
```

Templates are stored in `.nb/templates/` as markdown files. Use variables that get replaced when creating notes:

| Variable | Description |
|----------|-------------|
| `{{ date }}` | ISO date (2025-11-29) |
| `{{ datetime }}` | ISO datetime |
| `{{ notebook }}` | Notebook name |
| `{{ title }}` | Note title |

Example template (`meeting.md`):

```markdown
---
date: {{ date }}
---

# {{ title }}

## Attendees

-

## Agenda

-

## Notes

## Action Items

- [ ]
```

#### Using Templates

```bash
nb new -n work -T meeting           # Use template when creating note
nb new project-kickoff -n projects -T meeting
```

#### Default Templates per Notebook

Configure a default template for a notebook in config:

```yaml
notebooks:
  - name: work
    date_based: true
    template: meeting   # Auto-use .nb/templates/meeting.md
```

### Note Aliases

Create short aliases for frequently accessed notes:

```bash
nb alias readme projects/README     # Create alias for a note
nb alias standup daily/2025-11-29   # Alias for a specific daily note
nb alias meeting work/meeting-notes # Alias within a notebook

nb aliases                          # List all aliases
nb unalias readme                   # Remove an alias
```

Aliases work with `open`, `show`, and todo filtering:

```bash
nb open readme             # Open aliased note
nb open daily/readme       # Also works with notebook/alias format
nb show readme             # Show aliased note in console
nb todo --note readme      # Filter todos by aliased note
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

### Fuzzy Finding

When you specify a notebook or note that doesn't exist, nb will suggest similar matches:

```bash
$ nb open myproject -n idas
No exact match for 'idas'. Did you mean:
  1. ideas
  2. daily
  0. Cancel
Select [1]: 1
Opening ideas/myproject.md...
```

This works with:
- `nb open` - notebook and note names
- `nb todo -n` - notebook filters

### Todos

Todos are extracted from markdown files using GitHub-style checkboxes:

```markdown
- [ ] Task to do @due(friday) @priority(1) #urgent
- [^] In-progress task (currently working on)
- [x] Completed task
  - [ ] Subtask (nested todos are supported)
```

#### Commands

```bash
nb todo                 # List all open todos (grouped by status and due date)
nb todo -f              # Focus mode: hide "due later" and "no date" sections
nb todo -a              # Include todos from all sources (even excluded notebooks)
nb todo -c              # Include completed todos
nb todo -n daily        # Show todos from a specific notebook
nb todo -n daily -n work  # Filter by multiple notebooks
nb todo --note projects/myproject  # Filter by specific note
nb todo --note nbtodo              # Filter by linked note alias
nb todo --note readme              # Filter by note alias
nb todo --note work/project::Tasks # Filter by section within note
nb todo --note a --note b          # Filter by multiple notes
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

# Pagination
nb todo --limit 10      # Show only first 10 todos
nb todo -l 5            # Short form
nb todo -l 10 -o 10     # Show todos 11-20 (offset + limit)

# Todo actions
nb todo add "New task"  # Add to inbox (todo.md)
nb todo add --today "Call dentist"  # Add to today's note
nb todo add --note work/project "Document API"  # Add to specific note
nb todo add --note work/project::Tasks "New task"  # Add under specific section

# Stdin piping support
echo "Review PR" | nb todo add               # Pipe to inbox
pbpaste | nb todo add --today                # Pipe clipboard to daily note
echo "Task @due(friday)" | nb todo add       # Pipe with metadata

nb todo done abc123     # Mark complete (by ID prefix)
nb todo undone abc123   # Mark incomplete
nb todo start abc123    # Mark as in-progress ([ ] -> [^])
nb todo pause abc123    # Pause in-progress todo ([^] -> [ ])
nb todo show abc123     # Show todo details
nb todo edit abc123     # Open source file at todo line

# Saved views
nb todo -n work -t urgent --create-view work-urgent  # Save current filters as a view
nb todo -v work-urgent  # Apply saved view
nb todo --list-views    # List all saved views
nb todo --delete-view work-urgent  # Delete a view
```

Todos are grouped by status and due date: OVERDUE, IN PROGRESS, DUE TODAY, DUE THIS WEEK, DUE NEXT WEEK, DUE LATER, NO DUE DATE.

#### Adding Todos to Specific Notes

Use `--note` / `-N` to add todos directly to a specific note instead of the inbox:

```bash
nb todo add "Review docs" --note work/project       # Add to work/project.md
nb todo add "Call client" -N daily/2025-11-29       # Add to specific daily note
nb todo add "New feature" --note ideas::Backlog     # Add under "Backlog" section
nb ta "Quick task" -N work/project::Tasks           # Using alias with section
```

The syntax `notebook/note::Section` targets a section heading within the note:
- If the section exists, the todo is added at the end of that section
- If the section doesn't exist, it's created as a new `## Section` heading

Note names support fuzzy matching - if no exact match is found, similar notes will be suggested.

Todos can be hidden from `nb todo` at three levels:
- **Notebook-level**: Set `todo_exclude: true` in notebook config
- **Note-level**: Set `todo_exclude: true` in note frontmatter
- **Linked note-level**: Use `--todo-exclude` when linking or `nb link exclude-todos`

Use `-a/--all` to include all todos, `-n <notebook>` to view a specific notebook, or `--note` to view a specific note (bypasses exclusion filters).

#### Interactive Mode

```bash
nb todo -i              # Launch interactive viewer
```

Keyboard shortcuts:
- `j/k` - Navigate up/down
- `Space` - Toggle completion
- `s` - Toggle in-progress status (start/pause)
- `e` - Edit (open source file)
- `c` - Toggle showing completed
- `g/G` - Jump to top/bottom
- `r` - Refresh
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
nb search "query" --until "nov 20"       # Up to a date
nb search "query" --recent               # Boost recent results
nb search "query" --limit 5              # Limit number of results

nb grep "pattern"       # Regex search
nb grep "TODO.*urgent" -C 5  # With context lines
nb grep "config" -n work     # Filter by notebook
nb grep "setup" --note myproject  # Filter by specific note
```

### Statistics

View todo statistics with completion rates, activity trends, and breakdowns:

```bash
nb stats                    # Full dashboard with overview and notebook breakdown
nb stats --compact          # Single panel summary
nb stats --by-notebook      # Show breakdown by notebook
nb stats --by-priority      # Show breakdown by priority
nb stats --by-tag           # Show top tags by usage
nb stats -n work -n daily   # Stats for specific notebooks
nb stats --days 7           # Week activity trends (default: 30 days)
nb stats -x personal        # Exclude notebooks from stats
```

The dashboard shows:
- **Overview**: Total todos, completed count and rate, in-progress, pending, overdue, due today/week
- **Activity sparklines**: Todos created and completed over time
- **Breakdowns**: Stats per notebook, priority level, or top tags

### Tags

List and explore tags used across todos:

```bash
nb tags                   # List all tags sorted by count
nb tags --sort alpha      # Alphabetical order
nb tags --sources         # Show which notebooks/notes use each tag
nb tags -n work           # Tags from work notebook only
nb tags --limit 10        # Top 10 tags
nb tags --open            # Only count open (non-completed) todos
```

### Linked Files

Link external markdown files or directories to index them alongside your notes.
Both note content and todos are indexed (like any other note):

```bash
nb link add ~/code/project/TODO.md        # Link a single file
nb link add ~/docs/wiki                    # Link a directory (recursive)
nb link add ~/vault --alias vault -n @vault  # Custom alias and notebook
nb link add ~/docs --no-recursive          # Don't scan subdirectories

nb link list                              # Show all linked files
nb link sync                              # Re-scan and update index
nb link sync wiki                         # Sync a specific link
nb link remove wiki                       # Stop tracking
```

#### Options

| Option | Description |
|--------|-------------|
| `--alias, -a` | Short name for the link (defaults to filename/dirname) |
| `--notebook, -n` | Virtual notebook name (defaults to `@alias`) |
| `--sync/--no-sync` | Sync todo completions back to source file (default: sync) |
| `--todo-exclude` | Hide todos from `nb todo` by default |
| `--no-recursive` | Don't scan subdirectories (for directory links) |

#### Todo Exclusion

By default, todos from linked notes appear in `nb todo`. Use `--todo-exclude` to hide them:

```bash
nb link add ~/work/archive --todo-exclude  # Todos hidden from nb todo
nb todo -n @archive                        # View them explicitly
nb link exclude-todos wiki                 # Toggle exclusion on existing link
nb link include-todos wiki                 # Re-enable todos
```

#### Sync Control

With `--sync` (default), completing a todo with `nb todo done` updates the source file.
Disable this if you don't want nb to modify external files:

```bash
nb link add ~/shared/tasks.md --no-sync   # Won't modify source file
nb link disable-sync wiki                 # Disable on existing link
nb link enable-sync wiki                  # Re-enable sync
```

Linked notes appear in `nb list` with `(linked)` indicator and under a virtual notebook (prefixed with `@` by default).

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
nb index -n daily     # Only reindex a specific notebook
nb index --rebuild    # Drop and recreate database (for schema changes)
nb index --embeddings # Rebuild search embeddings
nb index --vectors-only  # Rebuild only vectors (skip file indexing)
```

### Web Viewer

Browse notebooks and notes in a browser with a clean reading experience:

```bash
nb web                    # Start server and open browser
nb web --port 8080        # Custom port (default: 3000)
nb web --no-open          # Start server without opening browser
nb web -c                 # Include completed todos
```

Features:
- Browse notebooks and notes with notebook colors from config
- Create and edit notes directly in the browser
- Markdown rendering with syntax highlighting for code blocks
- Full-text search across all notes
- Todo management: add new todos, toggle completion, view by section
- Todo sections: Overdue, In Progress, Due Today, Due This Week, Due Later, No Due Date
- Sort todos by status, notebook, due date, priority, or created date
- Dark theme, mobile responsive
- Zero additional dependencies (stdlib HTTP server + CDN for markdown/highlighting)

Press `Ctrl+C` to stop the server.

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

# Notebook-specific settings (notebook.<name>.<setting>):
nb config set notebook.work.color blue      # Set display color
nb config set notebook.projects.icon wrench # Set icon (emoji alias)
nb config set notebook.daily.icon 📅        # Set icon (direct emoji)
nb config get notebook.work.color           # Get notebook color

# Available icon aliases: calendar, note, book, wrench, hammer, gear,
#   star, check, pin, flag, work, home, code, rocket, target, brain, etc.

# Todo exclusion (for notebooks or individual notes)
nb config exclude personal      # Exclude notebook from nb todo
nb config include personal      # Re-include notebook in nb todo
nb config exclude projects/old-idea  # Exclude specific note (updates frontmatter)
nb config include projects/old-idea  # Re-include specific note
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
    icon: 📅                  # Display icon in listings
  - name: projects
    date_based: false
    color: cyan               # Display color (blue, green, cyan, etc.)
    icon: 🔧
  - name: work
    date_based: true
    color: blue
  - name: personal
    date_based: false
    todo_exclude: true        # Hidden from `nb todo` by default
    color: green
  - name: obsidian
    path: ~/Documents/Obsidian/vault   # External directory
    date_based: false

# Linked external files and directories
linked_notes:
  - path: ~/docs/wiki
    alias: wiki
    notebook: "@wiki"
    recursive: true
    todo_exclude: false   # Include todos in nb todo
    sync: true            # Sync completions back to source
  - path: ~/code/project/TODO.md
    alias: project
    notebook: "@project"
    sync: true
  - path: ~/work/archive
    alias: archive
    todo_exclude: true    # Hide from nb todo by default

# Semantic search embeddings
embeddings:
  provider: ollama      # or "openai"
  model: nomic-embed-text

# Saved todo views (created with --create-view)
todo_views:
  - name: work-urgent
    filters:
      notebooks: [work]
      tag: urgent
      hide_later: true
  - name: daily-focus
    filters:
      notebooks: [daily]
      hide_later: true
      hide_no_date: true
```

### Notebook Options

| Option | Description |
|--------|-------------|
| `name` | Notebook name (required) |
| `date_based` | Use week-based date organization |
| `todo_exclude` | Exclude from `nb todo` by default |
| `path` | External directory path (makes notebook external) |
| `color` | Display color in listings (e.g., blue, green, cyan, magenta, #ff5500) |
| `icon` | Display icon/emoji prefix (e.g., 📅, 🔧, 📝) |
| `template` | Default template name for new notes in this notebook |

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
    ├── templates/            # Note templates
    │   ├── meeting.md
    │   └── daily.md
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
- [ ] Pending task
- [^] In-progress task (currently being worked on)
- [x] Completed task
  - [ ] Nested subtask
  - [x] Completed subtask
```

#### Todo Status

| Marker | Status | Description |
|--------|--------|-------------|
| `[ ]` | Pending | Task not yet started |
| `[^]` | In Progress | Task currently being worked on |
| `[x]` | Completed | Task finished |

Use `nb todo start <id>` to mark a todo as in-progress, or `nb todo pause <id>` to return it to pending.

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

**Tag Inheritance**: Todos automatically inherit tags from their note's frontmatter. For example, if a note has `tags: [project, urgent]` in frontmatter, all todos in that note will have those tags in addition to any inline `#tags`.

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

## Command Aliases

| Alias | Command |
|-------|---------|
| `t` | `today` |
| `y` | `yesterday` |
| `l` | `last` |
| `o` | `open` |
| `s` | `search` |
| `ss` | `search --semantic` |
| `td` | `todo` |
| `ta` | `todo add` (supports `--today`, `--note`/`-N`) |
| `nbs` | `notebooks` |
| `nbt` | Standalone command equivalent to `nb todo` |

The `nbt` command is a separate executable that works exactly like `nb todo`:

```bash
nbt                  # Same as: nb todo
nbt -n work          # Same as: nb todo -n work
nbt add "Task"       # Same as: nb todo add "Task"
```

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
