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
- [ ] Toml for config instead of yaml
- [ ] Note titles -- how to integrate and use them as a way to open notes too? Or at least display in list? This already seems to be the case.
- [ ] `nb stats` command for overview statistics, especially usage stats and completion stats, some graphs?!
- [ ] `nb tags` command to list all tags with counts, and allow batch replace/rename of tags
- [x] Improve formatting for `nb history` command - color code notebooks and sort by notebook, include aliases.
- [x] Should have stable relative ordering of todos from same list when same (or no) todo dates (and no other sorting specified)
- [x] Enhance `todo add` command to allow putting into specific notes, or adding to a specific section
- [x] Extend `nb todo` command to allow filtering from specific note
- [ ] Dynamically check terminal width for output of `nb todo` and other commands to give nicer looking output. E.g. columns are not always aligned in `nb todo`
- [ ] The command aliases aren't really aliases, they don't pass the flags or show the right `--help` text. They need to pass the flags too!
- [ ] Allow short alias for any note
- [ ] enhance index command to allow specifying specific notebook
- [ ] Add `nbt` command as alias to `nb todo`
- [ ] Check that `nb todo --note <NOTE>` filter can accept `notebook/note::section` syntax, allow partial section match

### Phase 5: Advanced TUI
- [ ] Full Wijjit-based todo list view with richer interactions
- [ ] Full Wijjit based editor for notes
- [x] Stream/continuous view (`nb stream`) with lazy loading
- [ ] Grep search within stream view
- [ ] Interactive filtering UI
- [ ] Navigation and links
- [ ] Integrate git and some kind of backup
- [ ] Capture url and other file attachments as markdown using all2md

## Technical Debt
- [x] Add comprehensive test suite
- [ ] Add type hints throughout (mypy strict mode)
- [ ] Performance optimization for large note collections
- [ ] Better error messages and user feedback
- [ ] Documentation site with examples

### Phase 6: Future Enhancements
- [ ] Recurring todos (`@recur(weekly)`)
- [ ] Export to various formats (HTML, PDF)
- [ ] Mobile companion app / sync story
- [ ] Calendar view for due dates
- [ ] Pomodoro timer integration?? What is this?
- [ ] Due date reminders (optional notifications)
- [ ] Watcher service in background for indexing.
- [ ] Would it be possible to integrate more directly into the email/calendar/outlook contacts? Is there any benefit?
- [ ] Web viewer - this would be easy with the all2md library.
- [ ] How do we make it available via the cloud?

---

## Backlog / Ideas

### From Original Notes
1. Add a way to return a range of notes (e.g., `nb "last week"`)
2. Same for todos (date range filtering)
3. Attachments searchable in vector database
4. DONE: Consider shorter IDs for display
5. Add TOML support as alternative to YAML config

---

A “Pomodoro timer integration” in the context of a notebook app means building a Pomodoro-style work timer into the notebook so users can run timed focus sessions that are directly        
associated with notes, tasks, or document sections. It’s not just a standalone timer — it’s linked to the notebook’s content, metadata, history and UX so users can start/stop sessions from
a note, track productive time per note/task, and use that data for planning and analytics.                                                                                                  

Below is a concise guide to what that entails, why it’s useful, recommended features, UX patterns, data model/events, platform considerations, and implementation notes.                    

What the Pomodoro technique is (brief)                                                                                                                                                      

 • Work in focused intervals (typically 25 minutes) separated by short breaks (5 minutes). After several cycles take a longer break (15–30 minutes).                                        
 • The technique emphasizes focus, regular rest, and measuring productive time.                                                                                                             

Why integrate it into a notebook app                                                                                                                                                        

 • Contextual focus: start a timer directly from the note or task you’re working on.                                                                                                        
 • Automatic time tracking per note/task/tag/project.                                                                                                                                       
 • Makes notes actionable (task → focused work session).                                                                                                                                    
 • Enables analytics: time spent on topics, productivity trends, session history.                                                                                                           
 • Reduces context switching between apps.     
