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

    
## In Progress / Next Up
 
- [ ] Associate todo list with section heading.
    Capture whatever the prior heading associated with the todo is (if exists)
- [ ] The `nb list` command is exactly the same as the `nb notebooks` command when no flags are used. Should list the last 5 notes from each notebook unless a flag is given.
- [ ] Watcher service in background for indexing.
- [ ] Allow defining a color for each notebook that is used in display listings (especially `nb todo`)
- [ ] Capture url and other file attachments as markdown using all2md
- [ ] Meetings?? This is probably best as a date-based notebook with some special metadata
- [ ] Templates for notes - allow to define templates and create from a template with `nb new ... --template <template_name>`
- [ ] Integrate git and some kind of backup
- [ ] Would it be possible to integrate more directly into the email/calendar/outlook contacts? Is there any benefit?
- [ ] Web viewer - this would be easy with the all2md library.
- [ ] How do we make it available via the cloud?
- [^] Command Line completion!!
- [ ] Fuzzy finding for notebooks and notes from cli input
- [ ] Toml for config instead of yaml
- [ ] Add a way from command line to open with other editor (e.g. nb open <note> --notepad)
- [ ] Note titles should be visible in listing notes if they say more than default.
- [ ] Add a way to signal todo in progress, e.g `[^]`

### Phase 4: Advanced TUI
- [ ] Full Wijjit-based todo list view with richer interactions
- [x] Stream/continuous view (`nb stream`) with lazy loading
- [ ] Grep search within stream view
- [ ] Interactive filtering UI
- [ ] Navigation and links
- [ ] Due date reminders (optional notifications)
- [ ] `nb stats` command for overview statistics
- [ ] `nb tags` command to list all tags with counts

## Technical Debt
- [x] Add comprehensive test suite
- [ ] Add type hints throughout (mypy strict mode)
- [ ] Performance optimization for large note collections
- [ ] Better error messages and user feedback
- [ ] Documentation site with examples

### Future Enhancements
- [ ] Recurring todos (`@recur(weekly)`)
- [ ] Export to various formats (HTML, PDF)
- [ ] Git integration for version history
- [ ] Mobile companion app / sync story
- [ ] Calendar view for due dates
- [ ] Pomodoro timer integration?? What is this?

---

## Backlog / Ideas

### From Original Notes
1. Add a way to return a range of notes (e.g., `nb "last week"`)
2. Same for todos (date range filtering)
3. Attachments searchable in vector database
4. DONE: Consider shorter IDs for display
5. Add TOML support as alternative to YAML config
