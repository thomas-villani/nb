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
- **Note streaming** - Browse notes interactively with keyboard navigation and search
- **Linked files** - Index external todo files and note directories
- **Note linking** - Wiki-style and markdown links between notes with backlink tracking
- **Knowledge graph** - Interactive D3.js visualization in web UI, ASCII graph in CLI
- **Related notes** - Find connected notes by links, tags, and semantic similarity
- **Attachments** - Attach files and URLs to notes and todos
- **Interactive mode** - Keyboard-driven todo management
- **Web viewer** - Browse notes with clickable links, backlinks panel, and graph view
- **Meeting recording** - Record audio and transcribe with speaker diarization (optional)
- **Raindrop inbox** - Pull bookmarks from Raindrop.io and clip them as notes with AI summaries
- **Git integration** - Version control notes with auto-commit and GitHub sync
- **AI assistant** - Interactive AI agent for task management with confirmation flow
- **AI reviews** - Daily/weekly reviews reflecting on completed work, wins, and improvements
- **AI standups** - Morning briefings with yesterday's work, calendar, and focus areas

## Installation

```bash
# Clone the repository
git clone https://github.com/thomas-villani/nb.git
cd nb

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
nb yesterday -n work      # Yesterday's note in work notebook

nb open "nov 25"          # Open note for a specific date
nb open "last friday"     # Fuzzy date parsing
nb open myalias           # Open note by alias (created with nb alias)
nb open friday -n work    # Open Friday's note in work notebook
nb open myproject -n ideas  # Open ideas/myproject.md
nb open newfile -n ideas  # Prompts to create if doesn't exist
nb open newfile --no-prompt  # Fail if note doesn't exist (no prompt)
nb open "quarterly report"    # Open note by partial title match

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

nb history                # Show last 10 modified notes
nb history --viewed       # Show view history instead (notes you opened)
nb history -l 50          # Show last 50 notes
nb history -o 10          # Skip first 10, show next 10
nb history -n work        # Filter by notebook
nb history -F             # Show full paths instead of filenames
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

nb log "Started feature X"           # Append with timestamp to today's note
nb log "Meeting notes" -N project    # Timestamp + content to specific note

# Stdin piping support
echo "random thought" | nb add              # Pipe to today's note
cat notes.txt | nb add                      # Pipe file content
git diff --stat | nb add --note work/log    # Pipe command output
pbpaste | nb add                            # Pipe clipboard (macOS)

nb list                    # List recently modified notes per notebook (default 5)
nb list -l 10              # Show 10 notes per notebook
nb list work               # List notes in 'work' notebook
nb list --all              # List all notes in all notebooks
nb list --week             # List this week's daily notes
nb list --month            # List this month's daily notes
nb list work --week        # List this week's notes in work notebook
nb list -n work            # Alternative: use -n/--notebook option
nb list -F                 # Show full paths to notes
nb list -d                 # Show details (todo count, mtime, date, excluded status)
nb list -T                 # Display as tree grouped by subdirectory sections
nb list -S tasks           # Filter by path section/subdirectory
nb list -xs archive        # Exclude notes from a section
nb list -S tasks -xs done  # Combine include and exclude sections

nb delete friday           # Delete Friday's daily note
nb delete myproject -n work  # Delete work/myproject.md
nb delete work/myproject   # Delete using notebook/note format
nb delete myalias          # Delete note by alias
nb delete friday -f        # Skip confirmation

nb mv work/old-project archive/old-project  # Move a note
nb mv friday archive/2025-01-10             # Move daily note to archive
nb mv work/draft work/final -f              # Overwrite if exists

nb cp work/template work/new-project  # Copy a note
nb cp daily/friday archive/backup     # Copy to different notebook

nb export friday report.pdf           # Export note to PDF
nb export work/project docs.docx      # Export to Word
nb export myproject output.html       # Export to HTML
nb export daily/ journal.pdf          # Export entire notebook (all notes)
nb export daily/ archive.pdf --sort modified  # Sort by modification time
nb export daily/ archive.pdf --reverse        # Newest first

nb stream                  # Recently modified notes (default, TUI)
nb stream --by-date        # Sort by note date instead
nb stream -n daily         # Browse daily notes
nb stream -w "last week"   # Browse last week's notes
nb stream -n daily -w "last 2 weeks"  # Daily notes from last 2 weeks
nb stream --recent         # Browse recently viewed notes
nb stream --recent -l 20   # Last 20 viewed notes
nb stream -c               # Continuous mode (maximized content)
nb stream | head -100      # Pipe mode (plain text output)
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

**Static Variables:**

| Variable | Description |
|----------|-------------|
| `{{ date }}` | ISO date (2025-11-29) |
| `{{ datetime }}` | ISO datetime |
| `{{ notebook }}` | Notebook name |
| `{{ title }}` | Note title |

**Dynamic Variables** (populated from your data):

| Variable | Description |
|----------|-------------|
| `{{ todos_overdue }}` | Overdue incomplete todos |
| `{{ todos_due_today }}` | Todos due on the note's date |
| `{{ todos_due_this_week }}` | Todos due within 7 days |
| `{{ todos_high_priority }}` | High priority (P1) incomplete todos |
| `{{ calendar }}` | Calendar events for the note's date (Outlook) |

Dynamic variables render as reference lists (e.g., `- Task text [todo:abc123]`) that don't create duplicate todos.

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

Example daily template with dynamic variables (`daily.md`):

```markdown
---
date: {{ date }}
---

# {{ title }}

## Overdue
{{ todos_overdue }}

## Due Today
{{ todos_due_today }}

## Meetings
{{ calendar }}

## Notes

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

### Path Lookup

Get the full filesystem path to notebooks, notes, or aliases:

```bash
nb where daily              # Path to daily notebook directory
nb where friday             # Path to Friday's daily note
nb where myalias            # Path to aliased note
nb where myproject -n work  # Path to work/myproject.md
```

Useful for scripting and integrations. When multiple matches exist, all paths are printed (one per line).

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

### Pinned Notes

Pin frequently accessed notes for quick access:

```bash
nb pin readme              # Pin a note
nb pin myproject -n work   # Pin work/myproject.md
nb pin daily/friday        # Pin Friday's daily note

nb pinned                  # List all pinned notes
nb pinned -n work          # List pinned notes in work notebook

nb unpin readme            # Unpin a note
```

Pinned notes are stored in the database for quick retrieval.

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
nb todo -xt waiting     # Exclude todos with a tag
nb todo -p 1            # Filter by priority (1=high, 2=medium, 3=low)

# Date filters
nb todo --created-today # Show todos created today
nb todo --created-week  # Show todos created this week
nb todo --today     # Show todos due today
nb todo --week      # Show todos due this week

# Sorting
nb todo -s tag          # Sort by first tag (default: source)
nb todo -s priority     # Sort by priority
nb todo -s created      # Sort by creation date

# Pagination
nb todo --limit 10      # Show only first 10 todos
nb todo -l 5            # Short form
nb todo -l 10 -o 10     # Show todos 11-20 (offset + limit)

# Display options
nb todo -x              # Expanded view: more content (up to 80 chars), hide source/due as needed
nb todo -x -n daily     # Combine expanded view with notebook filter

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
nb todo delete abc123   # Delete todo from source file
nb todo delete abc -f   # Delete without confirmation

# Move/copy todos between notes
nb todo mv abc123 work/project           # Move todo to another note
nb todo mv abc123 def456 work/project    # Move multiple todos
nb todo mv abc123 work/project::Tasks    # Move to specific section

nb todo cp abc123 work/project           # Copy todo to another note
nb todo cp abc123 def456 work/project    # Copy multiple todos
nb todo cp abc123 work/project::Tasks    # Copy to specific section

# Change due dates
nb todo due abc123 friday      # Set due to next Friday
nb todo due abc123 tomorrow    # Set due to tomorrow
nb todo due abc123 "dec 25"    # Set due to specific date
nb todo due abc123 +7          # Set due 7 days from now
nb todo due abc123 +30         # Set due 30 days from now
nb todo due abc123 none        # Remove due date
nb todo due abc def friday     # Set multiple todos at once

# Bulk completion
nb todo all-done friday        # Mark all todos in Friday's daily note complete
nb todo all-done work/project  # Mark all in work/project.md
nb todo all-done friday -f     # Skip confirmation
nb todo all-done friday -i     # Only mark in-progress todos as complete
nb todo all-done friday -i -f  # In-progress only, skip confirmation

# Completed todos history
nb todo completed              # Show todos completed in last 7 days
nb todo completed --today      # Show todos completed today
nb todo completed --yesterday  # Show todos completed yesterday
nb todo completed --week       # Show todos completed this week
nb todo completed -d 30        # Show todos completed in last 30 days
nb todo completed -n work      # Filter by notebook
nb todo completed -t project   # Filter by tag

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

Launch a full-featured todo management interface with keyboard navigation:

```bash
nb todo -i              # Launch interactive todo manager
nb todo -i -c           # Include completed todos
nb todo -i -t work      # Filter by tag
nb todo -i -n daily     # Filter by notebook
```

The interactive mode uses a three-panel layout:

```
┌─────────────────────────── Todo Manager ─────────────────────────────────────┐
│ ┌─ Notebooks ─┐  ┌────────────────────── Todos ──────────────────────────────┐│
│ │ > All       │  │ [ ] Review PR for auth module       projects     Today    ││
│ │   daily     │  │ [^] Write documentation             daily        Tomorrow ││
│ │   projects  │  │ [ ] Fix login bug                   work         Dec 20   ││
│ │   work      │  │ [ ] Update dependencies             projects     No date  ││
│ ├─── Notes ───┤  │                                                           ││
│ │ > All       │  │                                                           ││
│ │  2025-12-13 │  │                                                           ││
│ │  project-a  │  │                                                           ││
│ └─────────────┘  └───────────────────────────────────────────────────────────┘│
│                                                                               │
│ Filter: (•) Incomplete ( ) All    12 items                                    │
│ [d]one [s]tart [t]omorrow [D]ate [a]dd [e]dit [x]del [T]ag [q]uit            │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Panels:**
- **Notebooks** - Filter by notebook (select "All" to see all notebooks)
- **Notes** - Filter by specific note within selected notebook
- **Todos** - Main todo list with status, content, source, and due date

**Keyboard shortcuts:**

| Key | Action | Description |
|-----|--------|-------------|
| `d` | Toggle done | Mark selected todo complete/incomplete |
| `s` | Toggle started | Mark as in-progress (`[^]`) or back to pending |
| `t` | Tomorrow | Reschedule selected todo to tomorrow |
| `D` | Custom date | Enter a custom due date (e.g., "friday", "dec 25") |
| `a` | Add todo | Add new todo to selected note |
| `e` | Edit | Open note containing the todo in editor |
| `x` | Delete | Delete selected todo (with confirmation) |
| `T` | Tag filter | Filter by tag |
| `Tab` | Focus | Cycle focus between panels |
| `q` | Quit | Exit the TUI |

**Filter toggle:** Use the radio buttons or arrow keys to switch between showing incomplete todos only or all todos.

#### Interactive Review

Review and triage todos one-by-one with quick rescheduling options:

```bash
nb todo review              # Review overdue + due today (TUI)
nb todo review --weekly     # Include this week + no-due-date items
nb todo review --all        # Review all incomplete todos
nb todo review --no-date    # Review only todos without due dates
nb todo review -t work      # Review only #work tagged todos
nb todo review -n daily     # Review only from daily notebook
```

**Keyboard shortcuts:**

| Key | Action | Description |
|-----|--------|-------------|
| `d` | Done | Mark todo as complete |
| `s` | Start | Toggle in-progress status (`[^]`) |
| `t` | Tomorrow | Reschedule to tomorrow |
| `f` | This Friday | Reschedule to this Friday |
| `m` | Next Monday | Reschedule to next Monday |
| `w` | Next week | Reschedule to next Monday |
| `n` | Next month | Reschedule to first of next month |
| `D` | Custom date | Enter custom date (e.g., "dec 25", "+7") |
| `e` | Edit | Open source file in editor |
| `k` | Skip | Skip to next todo |
| `x` | Delete | Delete todo (with confirmation) |
| `q` | Quit | Exit and show summary |

The review TUI displays a summary at the end showing how many todos were completed, rescheduled, deleted, or skipped.

#### Kanban View

Display todos in a kanban board layout with customizable columns:

```bash
nb todo --kanban           # Display kanban board (default board)
nb todo -k                 # Short form
nb todo -k -b myboard      # Use a custom board configuration
```

The kanban view shows todos organized into columns based on their status and filters. The default board has four columns: Backlog, In Progress, Due Today, and Done.

**Custom Boards**

Configure custom kanban boards in `config.yaml`:

```yaml
kanban_boards:
  - name: sprint
    columns:
      - name: "To Do"
        filters: { status: pending, no_due_date: true }
        color: cyan
      - name: "In Progress"
        filters: { status: in_progress }
        color: green
      - name: "Review"
        filters: { tags: [review] }
        color: yellow
      - name: "Done"
        filters: { status: completed }
        color: dim
```

**Available column filters:**
- `status`: "pending", "in_progress", or "completed"
- `due_today`: true - todos due today
- `due_this_week`: true - todos due within 7 days
- `overdue`: true - past due, not completed
- `no_due_date`: true - todos without a due date
- `priority`: 1, 2, or 3
- `tags`: list of tags to filter by

### Search

```bash
nb search "query"       # Hybrid search (semantic + keyword)
nb search -i            # Interactive search TUI
nb search -i "query"    # Interactive TUI with initial query
nb search -s "query"    # Semantic search only
nb search -k "query"    # Keyword search only
nb search -t mytag      # Filter by tag
nb search -n daily      # Filter by notebook
nb search "query" --when "last 2 weeks"  # Date range filter
nb search "query" --since friday         # From a date onwards
nb search "query" --until "nov 20"       # Up to a date
nb search "query" --recent               # Boost recent results
nb search "query" --limit 5              # Limit number of results
nb search "query" -l              # Output file paths only (no content)

nb grep "pattern"       # Regex search
nb grep "TODO.*urgent" -C 5  # With context lines
nb grep "config" -n work     # Filter by notebook
nb grep "setup" --note myproject  # Filter by specific note
nb grep "pattern" -l         # Output file paths only (no context)
```

#### Interactive Search

Launch an interactive search interface with `nb search -i`:

- **Real-time search** - Results update as you type
- **Live filters** - Filter by notebook and tag using dropdowns
- **Note preview** - See content of selected result
- **Direct actions** - Open notes in editor or stream view

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `Enter` | Execute search / open note |
| `↑/↓` | Navigate results |
| `Tab` | Cycle focus between panels |
| `e` | Edit selected note |
| `b` | Browse in stream view |
| `q` | Quit |

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

List and explore tags used across both notes and todos:

```bash
nb tags                   # List all tags sorted by count (from notes + todos)
nb tags --sort alpha      # Alphabetical order
nb tags --sources         # Show which notebooks/notes use each tag
nb tags -n work           # Tags from work notebook only
nb tags --limit 10        # Top 10 tags
nb tags --open            # Only count open (non-completed) todos
nb tags --todos           # Only show tags from todos
nb tags --notes           # Only show tags from notes
```

Tags must start with a letter and can contain letters, numbers, hyphens, and underscores (e.g., `#work`, `#FY2025`, `#project-alpha`). Hex color codes like `#ff00ff` are automatically excluded.

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

### Note Linking

Create connections between notes using wiki-style or markdown links. Links are indexed and can be queried with backlinks.

#### Link Syntax

**In note body:**

```markdown
See [[projects/myproject]] for the full plan.
Also check [[myproject|the project docs]] for details.

For more info, read [the API guide](docs/api.md) or visit [our wiki](https://wiki.example.com).
```

| Syntax | Description |
|--------|-------------|
| `[[path]]` | Wiki-style link to note |
| `[[path\|display]]` | Wiki-style link with custom display text |
| `[text](path.md)` | Markdown link to internal note |
| `[text](https://...)` | Markdown link to external URL |
| `[text](./relative.md)` | Relative path (resolved from note's directory) |

**In frontmatter:**

```yaml
---
date: 2025-12-02
links:
  # String formats
  - "note://work/project-plan"    # Internal note link
  - "https://example.com"          # External URL

  # Object format for URLs
  - title: "Company Wiki"
    url: "https://wiki.example.com"

  # Object format for notes
  - title: "Project Plan"
    note: "2026-plan"
    notebook: "work"              # Optional notebook context
---
```

#### Link Commands

```bash
# Show outgoing links from a note
nb links today                  # Links from today's note
nb links projects/myproject     # Links from specific note
nb links today --internal       # Only internal links
nb links today --external       # Only external links
nb links today --json           # Output as JSON

# Check for broken links
nb links --check                # Check all notes for broken internal links
nb links today --check          # Check specific note

# Show backlinks (notes linking TO a note)
nb backlinks projects/myproject # What notes link to this?
nb backlinks today --count      # Just show the count
nb backlinks myproject --json   # Output as JSON
```

#### Example Output

```bash
$ nb links projects/myproject

Outgoing links from projects/myproject.md:

Internal:
  [[daily/2025-11-28]] → daily/2025/Nov25.../2025-11-28.md
  [[api-docs|API Documentation]] → references/api-docs.md
  [Config guide](./config.md) → projects/config.md

External:
  [Python docs](https://docs.python.org)
  [GitHub](https://github.com/...)

4 links (3 internal, 1 external)
```

```bash
$ nb backlinks projects/myproject

Notes linking to projects/myproject.md:

  daily/2025-11-27.md:15 ([[...]])
  daily/2025-11-28.md:8 ([[...]])
  meetings/standup.md:23 ([...](...))

3 backlinks
```

### Knowledge Graph (CLI)

Visualize note connections in the terminal:

```bash
# Overview of entire knowledge graph
nb graph                    # Stats: nodes, edges, most connected notes

# Graph for a specific note
nb graph today              # Show connections for today's note
nb graph myproject          # Show connections for myproject
nb graph projects/idea -d 2 # Show 2 levels of connections

# Options
nb graph --no-tags          # Don't show tag connections
nb graph --links-only       # Only show note-to-note links
```

#### Example Output

```bash
$ nb graph projects/myproject

Graph for myproject

┌─ myproject ─┐

↓ Links to:
  ├── api-docs (wiki)
  ├── config (markdown)
  └── roadmap (wiki)

↑ Linked from:
  ├── 2025-11-27:15 (wiki)
  └── standup:23 (markdown)

# Tags:
  ├── #project (5 other notes)
  └── #active (3 other notes)

3 outgoing, 2 incoming, 2 tags
```

### Related Notes

Find notes related to a given note by combining multiple signals:

```bash
# Find related notes
nb related today              # Related to today's note
nb related myproject          # Related to myproject
nb related today -l 5         # Show top 5 related

# Filter by signal type
nb related today --links-only     # Only by direct links
nb related today --tags-only      # Only by shared tags
nb related today --semantic-only  # Only by content similarity
```

The `related` command combines three signals with weighted scoring:
- **Direct links** (weight: 1.0 outgoing, 0.9 backlinks) - notes you link to or that link to you
- **Shared tags** (weight: 0.3 per tag) - notes with common tags
- **Semantic similarity** (weight: 0.5 × score) - notes with similar content

#### Example Output

```bash
$ nb related projects/myproject

Notes related to myproject

 1. ██████████ api-docs
    projects/api-docs.md
    linked to, shared tags: #project, #docs

 2. ████████   roadmap
    projects/roadmap.md
    linked to, similar content (78%)

 3. ██████     2025-11-27
    daily/2025/Nov25-Dec01/2025-11-27.md
    links here, shared tags: #project

 4. ████       config-guide
    projects/config-guide.md
    shared tags: #project, #docs, similar content (65%)
```

### Web Clipping

Clip content from URLs or convert local files to markdown notes:

```bash
# Clip from URLs
nb clip https://example.com/article           # Append to today's note
nb clip https://example.com/article -n bookmarks  # Create note in notebook
nb clip https://example.com/article --to projects/research  # Append to note
nb clip https://example.com/article --section "Installation"  # Extract section
nb clip https://example.com/article --tag research --tag python

# Convert local files (PDF, DOCX, PPTX, etc.)
nb clip ~/Documents/report.pdf               # Convert PDF to markdown
nb clip ./meeting-notes.docx -n work         # DOCX to work notebook
nb clip presentation.pptx --title "Q4 Deck"  # Custom title
```

Supported file types: PDF, DOCX, DOC, PPTX, XLSX, ODT, EPUB, RTF, HTML, and more.

### Raindrop Inbox

Pull bookmarks from Raindrop.io and clip them as markdown notes.

#### Setup

1. Get a Raindrop API token from https://app.raindrop.io/settings/integrations
2. Set `RAINDROP_API_KEY` environment variable
3. Create an "nb-inbox" collection in Raindrop (or configure a different one)

```bash
# PowerShell
$env:RAINDROP_API_KEY = "your-token-here"

# Bash/Zsh
export RAINDROP_API_KEY="your-token-here"
```

#### Commands

```bash
nb inbox list                    # Show pending items (already-clipped hidden)
nb inbox list -l 50              # Show up to 50 items
nb inbox list -c reading         # List from 'reading' collection
nb inbox list --all              # Include already-clipped items

nb inbox pull                    # Interactive: clip each item (with AI summary)
nb inbox pull --auto             # Clip all to default notebook
nb inbox pull -n bookmarks       # Clip all to 'bookmarks' notebook
nb inbox pull -l 5               # Process only 5 items
nb inbox pull -t research        # Add #research tag to all
nb inbox pull --all              # Include already-clipped items
nb inbox pull --no-ai            # Disable AI summary generation

nb inbox clear                   # Archive all without clipping
nb inbox clear -f                # Skip confirmation

nb inbox history                 # Show previously clipped items
```

#### Interactive Mode

When running `nb inbox pull` without `--auto`, you can use these commands at each prompt:

| Command | Action |
|---------|--------|
| `Enter` | Clip to default/specified notebook |
| `<name>` | Clip to different notebook |
| `s` | Skip this item |
| `d` | Mark as duplicate and skip |
| `q` | Quit processing |

#### AI Summaries

By default, `nb inbox pull` generates a brief AI summary for each clipped article and stores it in the note's frontmatter. This requires an LLM API key (see AI Assistant section).

If no API key is configured or the LLM is unavailable, clipping continues gracefully without summaries.

```bash
nb inbox pull                    # Generates AI summary (default)
nb inbox pull --no-ai            # Skip AI summary generation
nb inbox pull --ai               # Force AI summary (overrides config)
```

#### Configuration

```bash
nb config set inbox.default_notebook reading
nb config set inbox.auto_summarize false       # Disable AI summaries globally
nb config set inbox.raindrop.collection my-inbox
nb config set inbox.raindrop.auto_archive false
```

Or in `config.yaml`:

```yaml
inbox:
  default_notebook: reading
  auto_summarize: true            # Generate AI summary when clipping (default: true)
  raindrop:
    collection: nb-inbox
    auto_archive: true
```

### Git Integration

Version control your notes and sync with GitHub. Git integration provides auto-commit after note changes and manual sync commands.

#### Setup

```bash
# Initialize git repository in notes directory
nb git init

# Add a remote (e.g., GitHub)
nb git remote --add git@github.com:user/notes.git

# Enable auto-commits
nb config set git.enabled true

# Push existing notes
nb git push
```

#### Commands

```bash
nb git init              # Initialize git repo and create .gitignore
nb git init --remote URL # Initialize and add remote in one step

nb git status            # Show modified/staged/untracked files
nb git status -v         # Verbose: list all files

nb git commit "message"  # Manually commit all changes
nb git commit -a         # Commit with default message

nb git push              # Push to remote
nb git push --force      # Force push (use with caution)

nb git pull              # Pull from remote (aborts on conflict)

nb git sync              # Pull then push (convenience command)

nb git log               # Show commit history
nb git log -n 20         # Show last 20 commits
nb git log --oneline     # Compact one-line format

nb git remote            # Show configured remote
nb git remote --add URL  # Add remote origin
nb git remote --remove   # Remove remote origin
```

#### Auto-Commit

When enabled, git automatically commits after:
- Creating a new note (`nb new`, `nb today`)
- Editing a note (after closing editor)
- Deleting a note (`nb delete`)
- Moving a note (`nb mv`)

Auto-commits use a configurable message template (default: `Update {path}`).

#### Configuration

```bash
nb config set git.enabled true              # Enable git integration
nb config set git.auto_commit false         # Disable auto-commits
nb config set git.commit_message_template "nb: {path}"  # Custom message
```

Or in `config.yaml`:

```yaml
git:
  enabled: true
  auto_commit: true
  commit_message_template: "Update {path}"  # Supports {path}, {notebook}, {title}, {date}
```

#### Conflict Handling

When pulling encounters conflicts, nb aborts the merge and provides instructions:

```
Merge conflicts detected. Please resolve manually:
  cd ~/notes
  git pull origin main
  # Resolve conflicts, then: git add . && git commit
```

The `.gitignore` created by `nb git init` excludes:
- `.nb/` directory (database, vectors, config)
- Common temporary files (`.DS_Store`, `*.swp`, etc.)

### Background Daemon

The optional background daemon watches for file changes and keeps the index updated automatically, making CLI commands near-instant.

**Requires optional dependency:**

```bash
uv sync --extra daemon
# or: uv pip install watchdog
```

#### Commands

```bash
nb daemon start           # Start background watcher (daemonized)
nb daemon start -f        # Run in foreground (useful for debugging)
nb daemon stop            # Stop the daemon
nb daemon status          # Check if running, show stats
nb daemon restart         # Restart the daemon
nb daemon log             # View daemon log
nb daemon log -f          # Follow log output (like tail -f)
```

#### What Gets Watched

- All notebooks under `notes_root`
- External notebook paths
- Linked todo files
- Linked note files/directories

When the daemon is running, commands like `nb todo` and `nb search` skip the indexing step, making them significantly faster.

#### Running as a System Service

The daemon automatically loads configuration from `~/notes/.nb/config.yaml` when run without arguments.

**Finding the executable path:**

If you installed nb with `uv`, find the executable path:

```bash
# If installed as a tool
uv tool run --from nb-cli which nb-daemon

# If installed in a project
uv run which nb-daemon   # Unix/macOS
uv run where nb-daemon   # Windows
```

**Windows (Task Scheduler):**

1. Open Task Scheduler and create a new task
2. Set trigger: "At log on"
3. Set action: Start a program
   - Program: Full path to `nb-daemon.exe` (e.g., `C:\Users\yourname\.local\bin\nb-daemon.exe`)
   - Or use `pythonw.exe` with arguments: `-m nb.daemon`
4. Under Settings, check "Run task as soon as possible after a scheduled start is missed"

Or import this XML (save as `nb-daemon.xml`, update the path):

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>C:\Users\yourname\.local\bin\nb-daemon.exe</Command>
    </Exec>
  </Actions>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
</Task>
```

Then import: `schtasks /create /tn "nb-daemon" /xml nb-daemon.xml`

**macOS (launchd):**

Create `~/Library/LaunchAgents/com.nb.daemon.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nb.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/yourname/.local/bin/nb-daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/nb-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/nb-daemon.err</string>
</dict>
</plist>
```

Load the service:

```bash
launchctl load ~/Library/LaunchAgents/com.nb.daemon.plist
```

To unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.nb.daemon.plist
```

**Linux (systemd user service):**

Create `~/.config/systemd/user/nb-daemon.service`:

```ini
[Unit]
Description=nb indexing daemon
After=default.target

[Service]
Type=simple
ExecStart=/home/yourname/.local/bin/nb-daemon
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable nb-daemon
systemctl --user start nb-daemon
```

Check status:

```bash
systemctl --user status nb-daemon
journalctl --user -u nb-daemon -f  # Follow logs
```

**Custom config:** If your config is not at `~/notes/.nb/config.yaml`, pass the path: `nb-daemon /path/to/config.yaml`

### Attachments

Attach files and URLs to notes and todos. Attachments are indexed in the database for fast queries.

```bash
# Attach files
nb attach file ./doc.pdf              # Attach to today's note
nb attach file ./img.png --to note.md # Attach to specific note
nb attach file ./ref.pdf --copy       # Copy to .nb/attachments/
nb attach file report.pdf --to abc123 --title "Q4 Report"  # Attach to todo

# Attach URLs
nb attach url https://example.com
nb attach url https://docs.api.com --title "API Docs"

# List attachments
nb attach list                        # Attachments in today's note
nb attach list work/project           # Attachments in specific note
nb attach list --all                  # All attachments (from database)
nb attach list --all --type file      # Only file attachments
nb attach list --all --type url       # Only URL attachments
nb attach list --all --notebook work  # Filter by notebook

# Open attachments
nb attach open note.md --line 15      # Open attachment at line 15

# Statistics
nb attach stats                       # Show attachment statistics

# Find orphaned files
nb attach orphans                     # List files in attachments/ not referenced
nb attach orphans --delete            # Delete orphan files
```

Attachments are automatically indexed when notes are indexed (`nb index`).

### Index & Maintenance

```bash
nb index              # Rebuild notes and todos index
nb index --force      # Force full reindex
nb index -n daily     # Only reindex a specific notebook
nb index --rebuild    # Drop and recreate database (for schema changes)
nb index --embeddings # Rebuild search embeddings
nb index --vectors-only  # Rebuild only vectors (skip file indexing)
nb index --reset-vectors --vectors-only  # Clear and rebuild vectors (after changing provider)
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
- Full-text search across all notes (with notebook scoping)
- **Clickable links**: Wiki links `[[note]]` and internal markdown links navigate between notes
- **Backlinks panel**: See which notes link to the current note
- **Knowledge graph**: Interactive D3.js visualization of note connections
- **Kanban board**: Drag-and-drop todo management with customizable columns
- Todo management: add new todos, toggle completion, view by section
- Todo sections: Overdue, In Progress, Due Today, Due This Week, Due Later, No Due Date
- Sort todos by status, notebook, due date, priority, or created date
- Dark theme, mobile responsive
- Zero additional dependencies (stdlib HTTP server + CDN for markdown/highlighting/D3)

#### Graph View

Access the interactive knowledge graph from the "Graph" link in the navigation sidebar, or directly at `http://localhost:3000/#graph`.

The graph shows three types of nodes:
- **Notes** (colored by notebook) - click to view the note
- **Tags** (purple) - toggle visibility with checkbox
- **Notebooks** (larger, notebook color) - click to browse

Edge types:
- **Solid lines**: Direct note-to-note links
- **Dashed lines**: Note-to-tag associations
- **Dotted lines**: Note-to-notebook membership

Controls:
- Drag nodes to rearrange the layout
- Scroll to zoom, or use the zoom slider
- Toggle tags/notebooks visibility with checkboxes
- Click "Reset View" to restore default zoom

Press `Ctrl+C` to stop the server.

### Meeting Recording

Record meetings and automatically transcribe them with speaker diarization.

**Requires optional dependencies:**

```bash
uv sync --extra recorder
```

**Also requires:**
- WASAPI-capable audio devices (Windows)
- Deepgram API key (set `DEEPGRAM_API_KEY` environment variable)

#### Commands

```bash
# Recording
nb record start                     # Start recording (Ctrl+C to stop)
nb record start --name standup      # Name the recording
nb record start -n work             # Save transcript to 'work' notebook
nb record start --audio-only        # Record without auto-transcription
nb record start --mic-only          # Record microphone only (no system audio)
nb record start --system-only       # Record system audio only (no microphone)
nb record start --dictate           # Dictation mode: mic-only, optimized transcription
nb record start --delete-audio      # Delete WAV file after transcription
nb record devices                   # List available audio devices
nb record start --mic 1 --loopback 3  # Use specific devices

# Transcribing existing audio files
nb transcribe ~/Downloads/meeting.wav           # Transcribe any audio file
nb transcribe meeting.mp3 --name client-call    # With custom name
nb transcribe recording.wav -n work             # Save to specific notebook
nb transcribe meeting.wav --speakers "0:Me,1:Client"  # Name speakers
nb transcribe meeting.wav --copy                # Copy file to .nb/recordings/

# Managing recordings
nb record list                      # List all recordings
nb record list --status pending     # Show only untranscribed recordings
nb record transcribe 2025-12-01_standup  # Re-transcribe a recording
nb record transcribe --all               # Transcribe all pending
nb record purge                     # Delete transcribed WAV files
nb record purge --older-than 30     # Delete recordings older than 30 days
nb record purge --all               # Delete all WAV files (including pending)
nb record purge --dry-run           # Preview what would be deleted
```

#### Recording Flow

1. **Record**: `nb record start --name meeting-name`
   - Audio is captured from microphone and/or system audio (configurable)
   - Saved as WAV: stereo when both sources (left=mic, right=system), mono otherwise
   - Use `--mic-only` or `--system-only` to capture from a single source
   - Press Ctrl+C to stop

2. **Transcribe**: Automatically runs after recording (unless `--audio-only`)
   - Uploads to Deepgram for transcription with speaker diarization
   - Saves structured JSON to `.nb/recordings/`
   - Saves human-readable Markdown to your notebook

3. **Result**: Transcript note is indexed by nb
   - Appears in searches
   - Todos extracted (if transcript contains checkboxes)
   - Tags from frontmatter

#### Output Files

| File | Location | Description |
|------|----------|-------------|
| `{date}_{time}_{name}.wav` | `.nb/recordings/` | Raw audio file |
| `{date}_{time}_{name}.json` | `.nb/recordings/` | Structured transcript data |
| `{date}_{time}_{name}.md` | `{notebook}/...` | Human-readable transcript |

Example: `2025-12-01_1430_standup.wav` for a recording started at 2:30 PM.

#### Transcript Format

The Markdown transcript includes:
- YAML frontmatter with date, tags, and duration
- Meeting metadata (date, duration)
- Speaker-attributed utterances with timestamps

```markdown
---
date: 2025-12-01
tags: [meeting, transcript]
duration: 30:45
---

# Meeting: Standup

**Date:** 2025-12-01 09:00
**Duration:** 30:45

---

**Speaker 0** [0:00]: Good morning everyone, let's start the standup.

**Speaker 1** [0:05]: Sure. Yesterday I worked on the API integration...
```

Use `--speakers "0:Alice,1:Bob"` during transcription to replace generic speaker labels with names.

#### Dictation Mode

Use `--dictate` for voice notes and dictation:
- Records mic only (no system audio)
- Optimized transcription for single-speaker dictation
- Spoken phrases like "new todo item:" are converted to `- [ ]` checkboxes
- Tagged as `voice-note`, `dictation` instead of `meeting`, `transcript`

#### Recorder Configuration

Configure default device settings in `config.yaml`:

```yaml
recorder:
  mic_device: 1              # Microphone device index (null for default)
  loopback_device: 3         # System audio device index (null for default)
  sample_rate: 48000         # Sample rate in Hz (48000 for WASAPI, 16000 for MME)
  auto_delete_audio: false   # Automatically delete WAV after transcription
  mic_speaker_label: "You"   # Label for microphone speaker in transcripts
```

Use `nb record devices` to find device indices for your system. WASAPI devices typically require 48000 Hz sample rate.

**Speaker labeling**: When recording with both microphone and system audio, speakers are automatically distinguished by channel. Your microphone is labeled with `mic_speaker_label` (default: "You"), while remote participants from system audio are labeled "Speaker 100", "Speaker 101", etc. Override with `--speakers "0:Me,100:Alice,101:Bob"`.

### AI Review & Standup

Generate AI-powered daily/weekly reviews and morning standups.

```bash
# Daily review - reflect on completed work
nb review day                     # End of day review
nb review day -n work             # Filter to work notebook
nb review day -o today            # Save to today's note

# Weekly review - comprehensive week reflection
nb review week                    # End of week review
nb review week -o work/reviews    # Save to specific note
nb review week --prompt "Focus on wins"  # Custom instructions

# Morning standup - plan the day ahead
nb standup                        # Morning briefing
nb standup -o today               # Save to today's note
nb standup --notebook work        # Filter to work notebook
nb standup --no-calendar          # Skip calendar integration
```

**Review sections:**
- **Completed** - What got done, grouped by project/notebook
- **Carrying Over** - Pending items moving forward with context
- **Wins** - Notable achievements or milestones
- **Improvements** (weekly) - Process improvement suggestions

**Standup sections:**
- **Yesterday** - Brief summary of completed work
- **Today's Schedule** - Calendar events to be aware of
- **Focus Areas** - Top priorities based on due dates and overdue items
- **Needs Attention** - Blockers or stale tasks requiring action

### AI Assistant

An interactive AI agent that can analyze your todos and notes, and take action on your behalf.
Write operations require confirmation before executing.

```bash
# Start interactive assistant
nb assistant

# Start with an initial query
nb assistant "add 3 todos for the quarterly review"

# Include a file as context
nb assistant -f plan.md "Review this plan and add todos"

# Include clipboard content
nb assistant --paste "Here's my plan for today"

# Include specific notes as context
nb assistant -N work/project "Summarize the current status"

# Focus on specific notebook
nb assistant -n work

# Preview changes without executing
nb assistant --dry-run

# Use fast model (cheaper)
nb assistant --fast
```

**Features:**

- **Read operations**: Search notes, read note content, query todos, get project stats, view calendar
- **Write operations**: Create/update todos, create notes, append to notes
- **Confirmation flow**: All write operations are queued and require explicit approval
- **Context injection**: Automatically includes overdue todos, calendar, and recent notes
- **File/clipboard input**: Include external files or clipboard content as context
- **Note selection**: Include specific notes for the assistant to reference

**Example interactions:**

```
> reschedule the todos for later this week to monday next week
> mark the API documentation todo as complete
> analyze the meeting notes and add action items as todos
> give me a status update on the Wijjit project
```

**Options:**

| Option | Description |
|--------|-------------|
| `QUERY` | Optional initial query to start the conversation |
| `-f, --file PATH` | Include file(s) as context (repeatable) |
| `--paste` | Include clipboard content as context |
| `-N, --note TEXT` | Include specific note(s) as context (repeatable) |
| `-n, --notebook TEXT` | Focus context on specific notebook |
| `--no-calendar` | Skip calendar integration |
| `--smart/--fast` | Use smart model (better) or fast model (cheaper) |
| `--dry-run` | Show proposed changes without executing |
| `--token-budget N` | Maximum tokens per session (default: 100000) |
| `--max-tools N` | Maximum tool calls per turn (default: 10) |

**Confirmation Flow:**

When the assistant proposes changes, you'll see:

```
===== Proposed Changes =====

[1] ADD TODO to daily/2025-12-21.md
    - [ ] Review API documentation @due(2025-12-22) #work

[2] UPDATE TODO abc123
    Status: pending -> completed

=============================
Apply changes? [y]es / [n]o / [1,2,3] select:
```

- Type `y` to apply all changes
- Type `n` to discard all changes
- Type `1,2` to apply only selected changes

### Configuration Commands

```bash
nb config                       # Open config file in editor
nb config edit                  # Same as above (explicit subcommand)
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
nb config set recorder.mic_speaker_label "Me"  # Mic speaker label in transcripts

# API keys (view detected keys)
nb config api-keys              # Show which API keys are configured

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

# Kanban board configurations (for CLI --kanban and web UI)
kanban_boards:
  - name: default
    columns:
      - name: Backlog
        filters: { status: pending, no_due_date: true }
        color: cyan
      - name: In Progress
        filters: { status: in_progress }
        color: green
      - name: Due Today
        filters: { due_today: true, status: pending }
        color: yellow
      - name: Done
        filters: { status: completed }
        color: dim

# Recording settings (optional feature)
recorder:
  mic_device: null        # Device index or null for default
  loopback_device: null   # Device index or null for default
  sample_rate: 48000      # 48000 for WASAPI devices, 16000 for MME
  auto_delete_audio: false

# Raindrop inbox settings (requires RAINDROP_API_KEY env var)
inbox:
  default_notebook: bookmarks   # Where clipped items go by default
  auto_summarize: true          # Generate AI summary when clipping (default: true)
  raindrop:
    collection: nb-inbox        # Raindrop collection to pull from
    auto_archive: true          # Move to archive after clipping

# Git integration (optional)
git:
  enabled: false                # Set to true to enable auto-commits
  auto_commit: true             # Commit automatically after note changes
  commit_message_template: "Update {path}"  # Supports {path}, {notebook}, {title}, {date}
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

General:
- `NB_NOTES_ROOT` - Override notes root directory
- `EDITOR` - Default editor

API Keys (never store in config.yaml):
- `ANTHROPIC_API_KEY` - API key for Anthropic Claude models (AI commands)
- `OPENAI_API_KEY` - API key for OpenAI models (AI commands, embeddings)
- `SERPER_API_KEY` - Serper API key for web search (research command)
- `DEEPGRAM_API_KEY` - Deepgram API key for meeting transcription
- `RAINDROP_API_KEY` - Raindrop.io API token for inbox feature

API keys can be set in environment or in a `.env` file at `~/notes/.nb/.env`.
Use `nb config api-keys` to see which keys are detected.

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
| `summary` | Brief summary of the note (auto-generated for clipped articles) |
| `tags` | List of tags for filtering |
| `links` | List of related notes/URLs (see Note Linking section) |
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
| Due date | `@due(...)` | `@due(friday)`, `@due(2025-12-01)`, `@due(next week)`, `@due(+7)` |
| Priority | `@priority(...)` | `@priority(1)`, `@priority(high)`, `@priority(low)` |
| Tags | `#tag` | `#work`, `#urgent`, `#project-alpha` |

Priority levels: `1` or `high`, `2` or `medium`, `3` or `low`

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
| `rec` | `record` |
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

### Testing

The test suite has several categories designed to balance fast feedback with thorough validation:

```bash
# Fast tests (no API keys required) - default for CI
pytest

# Exclude contract tests (same as above, explicit)
pytest -m "not contract and not vectorized"

# Run contract tests (requires API keys)
pytest -m contract

# Run vector/embeddings tests (requires OPENAI_API_KEY)
pytest -m vectorized

# Run a specific test file
pytest tests/test_cli.py -v
```

#### Test Categories

| Marker | Description | API Keys Required |
|--------|-------------|-------------------|
| (none) | Fast unit/integration tests | None |
| `contract` | Tests against real LLM/search APIs | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SERPER_API_KEY` |
| `vectorized` | Tests with real vector embeddings | `OPENAI_API_KEY` |
| `slow` | Long-running tests | Varies |

#### Setting Up API Keys for Contract Tests

Contract tests require real API keys. You can provide them via environment variables or a `.env` file:

**Option 1: Environment variables**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export SERPER_API_KEY=...
pytest -m contract
```

**Option 2: Use `NB_TEST_ENV_FILE`** (recommended)
```bash
# Point to your existing .env file
NB_TEST_ENV_FILE=~/.nb/.env pytest -m contract

# Or create a dedicated test env file
NB_TEST_ENV_FILE=~/secrets/test.env pytest -m contract
```

The `.env` file should contain:
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

#### Handling Non-Determinacy in Contract Tests

AI responses can vary even with `temperature=0.0`. Contract tests are designed to be resilient by:

1. **Using `temperature=0.0`** for maximum determinism
2. **Using simple, constrained prompts** that limit possible responses
3. **Asserting on structure, not exact content** (e.g., "has content", "has tokens")
4. **Flexible content assertions** (e.g., `"hello" in response.lower()`)
5. **Allowing alternative valid responses** (e.g., tool call OR text response)

If a contract test fails intermittently, make the assertion more flexible rather than removing the test.

#### Golden File Tests

API response parsing is tested against captured real responses in `tests/fixtures/`. These ensure our parsing code stays compatible with actual API formats:

- `anthropic_response.json` - Standard Claude response
- `anthropic_tool_response.json` - Tool-calling response
- `openai_response.json` - Standard GPT response
- `serper_web_response.json` - Web search results

To refresh golden files when APIs change:
```bash
python scripts/capture_api_responses.py
```

## License

MIT
