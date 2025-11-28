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

## In Progress / Next Up

### Phase 4: Advanced TUI
- [ ] Full Wijjit-based todo list view with richer interactions
- [ ] Stream/continuous view (`nb stream`) with lazy loading
- [ ] Grep search within stream view
- [ ] Interactive filtering UI

### Phase 5: Advanced Features
- [ ] Wiki-link navigation and backlinks
- [ ] Due date reminders (optional notifications)
- [ ] `nb stats` command for overview statistics
- [ ] `nb tags` command to list all tags with counts

---

## Backlog / Ideas

### From Original Notes
1. Add a way to return a range of notes (e.g., `nb "last week"`)
2. Same for todos (date range filtering)
3. Attachments searchable in vector database
4. Consider shorter IDs for display
5. Add TOML support as alternative to YAML config

### Future Enhancements
- [ ] Recurring todos (`@recur(weekly)`)
- [ ] Note templates for quick creation
- [ ] Export to various formats (HTML, PDF)
- [ ] Git integration for version history
- [ ] Mobile companion app / sync story
- [ ] Calendar view for due dates
- [ ] Pomodoro timer integration

---

## Technical Debt
- [ ] Add comprehensive test suite
- [ ] Add type hints throughout (mypy strict mode)
- [ ] Performance optimization for large note collections
- [ ] Better error messages and user feedback
- [ ] Documentation site with examples



Tom's Notes
-----------
1. Should have note templates
2. Add a command to add a todo to today's note.
3. Refactor the link command - linking todos and notes is basically the same, shouldn't really have them separately
4. I think all notebooks should be essentially date-based.
5. Add an `nb -s` command to show the notebook rather than edit
6. Allow linking notes into existing notebooks
7. 
