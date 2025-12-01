---
todo_exclude: true
---
# nb-cli Development Todo

## Completed

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
- [x] Unified search via localvectordb (keyword, semantic, hybrid)
- [x] Grep for regex pattern matching
- [x] Linked external todo files with bidirectional sync
- [x] Linked external note files/directories (`nb link note`)
- [x] Attachments (link + copy modes)
- [x] Basic interactive todo TUI (`nb todo -i`)
- [x] Embeddings configuration (Ollama default, OpenAI optional)

---

### Completed
- [x] Add a way to open the last viewed note `nb show --last` and `nb open --last`
- [x] For flat notebooks, should have a way to open latest note ^^
- [x] Collect recently viewed notes and allow viewing by recently viewed
- [x] How are indented lines following a todo item captured if they aren't todo items? Want to capture multiline if not an empty line after.
- [x] Need exclusion filters for todo list as well
- [x] For `nb todo`, sort by source, then date. Should have {Overdue, Due today, Due this week, Due next week, Due later, No due date.}
- [x] Add a command to open the source of a todo by id, `nb todo edit <ID>`
- [x] Need CLI command to configure notebooks and other settings
- [x] Allow toggling excluding a specific note from todo list in frontmatter.
- [x] Meetings?? This is probably best as a date-based notebook with some special metadata
    
## Phase 4: In Progress / Next Up
 
- [x] Associate todo list with section heading.
    Capture whatever the prior heading associated with the todo is (if exists)
  - [x] Need to skip this if the heading is the first heading in the document
  - [x] Reindexing doesn't appear to update sections, it needs to.
- [x] The `nb list` command is basically exactly the same as the `nb notebooks` command when no flags are used. Should list the latest 3 notes from each notebook unless a flag is given.
- [x] Need a way to toggle include/exclude of todo for specific notes from CLI
- [x] Allow defining a color (and/or icon?) for each notebook that is used in display listings (especially `nb todo`)
- [x] Do todos inherit the tag from the note? They probably should.
- [x] Refactor cli.py - split into submodules
- [x] Allow todo "views" to be defined with specific filters to be defined via `nb todo --create-view <VIEWNAME>` and then called from cli like `nb todo -v <VIEWNAME>`. Should probably have a way to list views
- [x] Fuzzy finding for notebooks and notes from cli input (if not a fuzzy date). E.g. `nb open <NOTE> -n <NOTEBOOK>` should give suggestions if similar note/notebook is found but not exact match (difflib has a fuzzy matcher I think)
- [x] Add a way to signal todo in progress, (I typically mark `[^]` for todos in progress) and update `nb todo` with a section for `IN PROGRESS`
- [x] Command Line completion!!
- [x] Add a way from command line to open with other editor (e.g. nb open <note> --notepad)
- [x] predefine a list of common emojis to set as icon from config for project
- [x] Templates for notes - allow to define templates and create from a template with `nb new ... --template <template_name>`
- [x] Note titles -- how to integrate and use them as a way to open notes too? Or at least display in list? This already seems to be the case.
- [x] `nb stats` command for overview statistics, especially usage stats and completion stats, some graphs?!
- [x] `nb tags` command to list all tags with counts, and allow batch replace/rename of tags
- [x] Improve formatting for `nb history` command - color code notebooks and sort by notebook, include aliases.
- [x] Should have stable relative ordering of todos from same list when same (or no) todo dates (and no other sorting specified)
- [x] Enhance `todo add` command to allow putting into specific notes, or adding to a specific section
- [x] Extend `nb todo` command to allow filtering from specific note
- [x] Dynamically check terminal width for output of `nb todo` and other commands to give nicer looking output. E.g. columns are not always aligned in `nb todo`
- [x] The command aliases aren't really aliases, they don't pass the flags or show the right `--help` text. They need to pass the flags too!
- [x] Add `nbt` command as alias to `nb todo`
- [x] Check that `nb todo --note <NOTE>` filter can accept `notebook/note::section` syntax, allow partial section match
- [x] Allow adding an alias for any note (not just linked notes)
- [x] enhance index command to allow specifying specific notebook
- [x] update `nb add` to allow to add to any note (but default to today's)
- [x] Add a flag (--full) for `nb list` to show full paths
- [x] Review code, check for DRY refactor opportunities and bugs
- [x] Address code review comments
- [x] Enhance `nb stream` to allow streaming recently viewed or recently modified notes
- [x] `nb history` shows linked notes under "@external" rather than in the notebook they're linked to
    Shows same file multiple times (should condense to one line with "+4" or something) 
- [x] Make `nb history` not group by notebook by default, instead have the notebook source colored in the same line as the history line. Allow grouping with a `--group` flag
- [x] If parent todo completed, auto complete child todos
- [x] What else should be configurable?

- [x] Must reindex file after 'nb todo add --note'
- [x] Add --note and --notebook filter to grep command
- [x] Need progress / spinners for long-running tasks (syncing and reindexing and search)
- [x] Review autocomplete and improve #improvement
- [x] Add a command to delete a todo or a note
- [x] Be able to define date format of note titles, and display, prefer day of week included in most cases
- [x] Interactive todo review function
- [x] Show id in second column in 'nb todo' rather than source. #UX
- [ ] Capture url and other file attachments as markdown using all2md #feature
- [x] Add more details about notes in 'nb list', e.g. todo count, last modified, etc.
- [x] Allow due dates to have times, and to auto parse @due(today) and other relative dates to fill the date on indexing
- [x] Update help command to launch real docs
- [x] Add command to change due-dates of todos from cli with fuzzy dates allowed
- [x] Add command to mark all todos in a note as complete
- [x] Add a `nb config edit` command to open the config file with the editor
- [x] When trying to open note that doesn't exist, prompt to create it
- [ ] Make the output of nbtodo sorted by due date within sections (then line number)

### Phase 5: Advanced TUI
- [ ] Full Wijjit-based todo list view with richer interactions #feature
- [ ] Full Wijjit based editor for notes #feature
- [x] Stream/continuous view (`nb stream`) with lazy loading
- [ ] Grep search within stream view #feature
- [ ] Interactive filtering UI #feature
- [ ] Navigation and links #feature

## Technical Debt
- [x] Add comprehensive test suite #testing
- [ ] Add type hints throughout (mypy strict mode) #polish
- [ ] Performance optimization for large note collections #performance
- [x] Better error messages and user feedback #polish
- [x] Documentation site with examples #docs
- [x] Refactor: Remove legacy config-based linked_todos/linked_notes storage
  - [x] Remove from DEFAULT_CONFIG_YAML template and parse/save functions
  - [x] Remove `linked_todos` and `linked_notes` fields from Config dataclass
  - [x] Remove `save_to_config` branches in links.py (add/remove functions)
  - [x] Simplify `list_linked_files()` and `list_linked_notes()` to DB-only
- [ ] Optimize imports and startup speed of cli #performance
- [x] Evaluate test suite and add e2e tests on actual CLI (if not existing) #testing


### Phase 6: Future Enhancements
- [ ] Recurring todos (`@recur(weekly)`) #feature
- [ ] Export to various formats (HTML, PDF) #feature
- [ ] Calendar view for due dates #feature
- [ ] Due date reminders (optional notifications) #feature
  These can use the `win11toast` library which is dead simple.
- [ ] Add '@startby' to todos #feature
