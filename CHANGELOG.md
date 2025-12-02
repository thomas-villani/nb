# v0.2.2 - 2025-12-02

Patch release addressing todo timestamp preservation during re-indexing and a few maintenance fixes.

## Bug Fixes

- [4eff321] Preserve todo created/completed dates during re-index
  - Capture created_date and completed_date for a file before deleting its todos to avoid resetting timestamps on re-index.
  - Added get_todo_dates_for_source helper to fetch date mappings for a source file.
  - Extended upsert_todo and upsert_todos_batch to accept preserved_dates and prefer preserved values when present, falling back to DB values or today's date as needed.
  - Updated scanner/indexing logic to preserve dates across multiple indexing flows (including linked files/notes and threaded indexing).
  - Added tests verifying:
    - created_date and completed_date are preserved across re-indexes.
    - new todos receive today's date when no prior date exists.

## Maintenance

- [05225a1] Fixed issue in pyproject.toml to correct packaging/metadata.
- [4f57e8e] Bump version: 0.2.1 → 0.2.2.
- [9590f4a] Updated conf.py version and adjusted bump-my-version settings to update pyproject.toml automatically in future.
- [7dcca86] Updated CHANGELOG.md.

# v0.2.1 - 2025-12-02

Patch release with several CLI and web UI improvements, todo-list UX enhancements, and two breaking DB-related changes (see "Breaking Changes" below). Developers should read the migration guidance before upgrading.

## New Features

- [cd210ff] Add --in-progress / -i option to `nb todo all-done` to only mark IN_PROGRESS todos as completed (leaves PENDING todos unchanged)
- [cd210ff] Add frontmatter "Properties" panel to the web UI and serialize frontmatter values (dates, lists) for safe JSON delivery and client-side rendering
- [cd210ff] Trigger background reindexing of a note after saving via the web UI so todos, tags, links and search stay up-to-date
- [cbbf7b8] Add `nb where` CLI to print full filesystem paths for notebooks, notes and aliases; supports `-n` notebook context and prints all matches (scripting/integration use)
- [cbbf7b8] Add title-based note search and interactive fallback in resolve_note_ref so notes can be opened by partial title match (single matches open directly; multiple matches prompt selection)
- [cbbf7b8] Add `--expand` / `-x` option to `nb todo` to prioritize todo content (up to ~80 chars) and progressively hide source/due columns for improved readability

## Improvements

- [cbbf7b8] When filtering todos to a single notebook (`-n`), omit notebook name from the source column to free space; update column-width calculations and formatting helpers to support hide_notebook/hide_source modes
- [cbbf7b8] Refactor todo source formatting and colored output functions to handle new hide/expand behaviors and improve truncation/alignment logic
- [8dbb6e5] Web UI: add clickable wiki/markdown links, backlinks panel, and interactive D3 knowledge-graph view; server APIs added: /api/resolve-link, /api/backlinks, /api/graph
- [efbc417] Add core note-linking APIs (NoteLink/Backlink/BrokenLink), CLI commands (`nb links`, `nb backlinks`) and indexer updates to extract/store link metadata (link_type, is_external, line_number)
- [cd210ff] Minor cleanup in note_links CLI, update todo.md to reflect completed items, and other documentation updates (README/CHANGELOG/todo.md)
- [0c30940] Add changelog.md for release history tracking

## Bug Fixes / Minor

- [e0fd07a] Minor todos and documentation updates
- [626fb5a] Bump package version to 0.2.1

## Breaking Changes

- [5119ef4] Add path-based sections, .nbignore, and web UI history
  - What changed: indexer now extracts path-based "sections" from note file paths and persists them to new DB tables (note_sections, todo_sections). CLI and web UI gained section filtering/display options; scanner supports .nbignore (fnmatch) to ignore files/dirs.
  - DB impact: schema bumped to v15. Migration required: run the provided migration to add section tables or reindex your notes to populate note_sections/todo_sections.
  - Upgrade guidance:
    - Backup your DB before upgrading.
    - Run the v15 migration script if you maintain schema migrations.
    - If you do not run migrations, reindex the repository (`nb index` / reindex procedure) to populate section tables.
    - Review any automation that parses note paths, and test CLI filters (--section / --exclude-section) and tree/grouped displays.

- [19393ef] Add per-notebook alias support and UI/todo improvements
  - What changed: aliases and linked_notes are now scoped per-notebook (composite primary keys). Alias/link operations accept notebook parameters; web UI/todo behaviors updated (todo due-date editor, notebook sorting/filtering).
  - DB impact: schema bumped to v13 and a migration was included to convert aliases and linked_notes to per-notebook composite keys.
  - Upgrade guidance:
    - Backup your DB before upgrading.
    - Run the included migration to convert alias/linked_note tables to composite PKs.
    - If you maintain external integrations that assume global alias uniqueness, update them to provide notebook context.
    - Verify alias-add/remove/update flows and any code that lists aliases across notebooks.

Note: There are other index/schema-related changes in recent releases (e.g., link metadata stored by the indexer). If you rely on DB schema stability, ensure you run all migrations in sequence and/or fully reindex when prompted by the upgrade logs.

# v0.2.0 - 2025-12-01

This release completes a large phase of development: it stabilizes the todos/workflow model, adds rich UIs (TUI + web), recorder + transcription support, vector search & attachments, and a broad set of CLI ergonomics and automation improvements. It also includes multiple database schema upgrades and several breaking changes — follow the migration guidance below before upgrading production deployments.

## Breaking Changes

Important: back up your index/database before migrating (copy the DB file shown in your config — e.g. .nb/index.db or the path configured in nb.config). When in doubt, run nb index --rebuild after upgrading to recreate a fresh index and re-run migrations.

- [75dba3a] Fix todo source sync by locating moved todos by content
  - What changed: Core file-modifying helpers that mutate note files (toggle, set_status, delete, update_due, etc.) now return the actual 1-based line number (int) on success or None on failure, instead of a bool.
  - Impact: any external code or plugins that call these helpers and expect True/False must be updated to accept int|None. Treat an int as success.
  - Migration guidance: Update callers to check for isinstance(returned, int) or returned is not None. If you consume these helpers from outside nb, update your integration to use the returned line number for more robust sync handling.

- [5046eb0], [cdc13fc] Move linked notes/todos handling fully to DB
  - What changed: The Config dataclass no longer exposes linked_todos or linked_notes; linked files are now stored and managed exclusively in the database via the links APIs.
  - Impact: Any workflows or automation that previously stored linked entries in config must migrate to the DB-backed links interface.
  - Migration guidance: Recreate linked entries using the CLI (nb link add ...) or the nb.core.links API. After moving links to the DB, run nb index --rebuild to ensure the index reflects DB-managed linked entries.

- [965afb4] DB schema bumped to v12 — completed_date tracking & stats
  - What changed: The database schema now adds completed_date to todos and includes new stats/tag APIs that rely on the additional column and indexes.
  - Impact: You must run the bundled migrations (or rebuild the index) before using the stats/tags CLIs. Pre-existing completed todos are backfilled but may have backfilled timestamps (completed_date set = created_date).
  - Migration guidance: Back up DB, then run nb index --rebuild or the packaged migration command to upgrade the schema. Verify get_todo_activity/get_tag_stats output after migration.

- [cd77892] Schema bumped to v9 — todo.section added
  - What changed: Todos now persist section context (markdown headings and "Label:"-style labels). Schema version increased to v9 (todos.section).
  - Impact: Run migrations or recreate the DB to add the new column; todo extraction and queries expect section to be present.
  - Migration guidance: Back up DB and run nb index --rebuild (or migrations) to add the section column and reindex notes so existing todos populate section info.

- [6830721] Schema bumped to v7 — note_views and todo_exclude
  - What changed: note_views tracking and note-level todo_exclude were added; schema v7 introduces the note_views table and notes.todo_exclude column.
  - Impact: After upgrade, run migrations/reindex so note views and exclusion flags are recorded and respected.
  - Migration guidance: Run nb index --rebuild or the provided migration path to upgrade the DB. Re-run any scripts that rely on note view/time metadata.

- [58d40a6] Todo IDs no longer include line numbers; schema added mtime column
  - What changed: Todo ID generation was made independent of line numbers (IDs are stable across edits). The index schema also added an mtime column and detection improvements.
  - Impact: Existing persisted IDs that included line numbers will no longer match the new IDs; any external references to old IDs will break.
  - Migration guidance: Rebuild the index (nb index --rebuild) to regenerate ID mappings. If you store external references to todo IDs, update them to use the new 6-char short IDs the CLI prints.

- [8ec8d7b] Config notebook format changed to objects (name/date_based)
  - What changed: When nb saves config it now writes notebook entries as objects {name, date_based}. Loading is backward compatible with legacy string lists.
  - Impact: External tooling that parses the config file should handle both string and object notebook formats.
  - Migration guidance: Check any scripts that consume the YAML config; they must accept both formats or migrate to using nb.config APIs.

- [17f0928] DB schema bumped to v4 — attachments, linked files and vector search
  - What changed: The index schema (v4) added content columns, external/source_alias fields, and new tables for linked notes and attachments. Local vector search integration was introduced.
  - Impact: You must run the migrations or rebuild the index to populate the new tables and to create embeddings when using vector search.
  - Migration guidance: Back up DB and run nb index --rebuild. If you plan to use vector search, reindexing will generate embeddings (may require external dependencies or long-running embedding jobs).

If you maintain integrations or automations that call nb internals, audit changes above (file-mutator return types, config layout, and DB-backed link management) and update accordingly. Always back up your DB before migrating.

---

## New Features

Below are the most significant user- and developer-facing additions grouped by area.

Core & CLI
- Restructure CLI into modular commands (nb.cli package) to make extension and testing easier; many focused subcommands (notes, todos, search, links, attachments, templates, notebooks, web, recorder, etc.).
- Add rich shell completion helpers and generated PowerShell completion; many CLI args now have shell_complete hooks for notebooks, tags, and views.
- Add stdin piping for nb add and nb todo add so you can echo "text" | nb add.

Todos, workflow, and TUI
- Add a full-featured interactive todo review TUI (nb todo review) and an integrated interactive todos view (TUI) to triage, reschedule, edit, delete, and navigate todos.
- Add advanced todo features: multi-line details persisting to DB, in-progress status (start/pause), saved todo views, pagination (limit/offset), per-todo section context, and better grouping by due date (OVERDUE, TODAY, NEXT WEEK, etc.).
- Add todo CLI ergonomics: batch operations (multiple IDs), nb todo due/clear, nb todo all-done, nb todo start/pause, nb todo delete (recursive removal of children), and --details for list output.
- Add fuzzy matching and improved note/section selection for add_todo_to_note; support for note::section syntax and auto-creation of missing sections.

Indexing, search & embeddings
- Add local vector search + hybrid search support (NoteSearch); support for configurable chunking, vector-only index mode, and recency boosting.
- Add batch indexing and batch todo upserts to reduce embedding calls and DB commits; add progress reporting hooks for long-running jobs.
- Add grep/keyword search improvements and score_threshold options to filter weak matches.

Recording & Transcription
- Add recorder package (nb.recorder) with recording CLI (nb record start/stop/list/transcribe) supporting microphone and WASAPI loopback capture and multi-channel diarization.
- Integrate Deepgram transcription support: transcribe recordings to JSON/Markdown and apply speaker labeling (configurable mic_speaker_label) and dictation post-processing.
- Recorder is optional extra — see docs and ensure DEEPGRAM_API_KEY is set to use Deepgram.

Web UI & API
- Add a single-file web viewer and a small API (nb web) to browse, view, edit notes, full-text search, and basic todo management from the browser (served via stdlib http.server). Includes endpoints for notebooks, notes, search, and todos.

Notebooks, templates & attachments
- Add notebook abstractions (date_based notebooks, week-based folders) and notebook management commands (nb notebooks).
- Add a templates engine and CLI (create notes from templates, per-notebook default templates).
- Add attachments and linked-file management subsystems (nb link / nb attach) with per-link options (todo_exclude, sync).

Stats, tags & history
- Add stats and tags CLI (summary dashboards, activity sparklines, breakdowns) and completed_date tracking in DB to support activity queries.
- Add note view tracking, nb last and nb history commands, and improved history displays.

Developer & extensibility features
- Expose core APIs: get_notebook_notes_with_metadata, NoteDetails, get_note_details_batch, links APIs, templates API, and other programmatic hooks to build integrations.
- Add many config options for search weighting, recency decay, todo defaults, and date/time formats.

Examples of CLI additions (non-exhaustive)
- nb todo review (interactive), nb todo start/pause, nb todo due, nb todo delete, nb record (recorder group), nb web (start viewer), nb templates, nb alias, nb stats, nb tags, nb link, nb attach, nb config edit/get/set.

## Bug Fixes

- Fix todo-source sync robustness: locate moved todos by content (find_todo_line) and recover when stored line numbers are stale.
- Prevent path traversal in web UI: _safe_note_path ensures note path resolution rejects attempts to escape notes_root and disallows unsafe writes.
- Normalize note paths across platforms (forward-slash normalize_path) to avoid DB misses and make index lookups stable.
- Fix reindex race conditions: use content-hash verification, thread-local DBs during parallel indexing, and atomically call delete/upsert with same DB connection.
- Fix linked-todo filtering bugs in queries (use source_alias and robust suffix matching) to avoid false matches when applying todo_exclude.
- Strengthen ID parsing for todo IDs to only accept 6-char hexadecimal short IDs to avoid false positives in CLI output parsing.

## Performance Improvements

- Batch embedding and indexing support to reduce calls to embedding providers (index_notes_batch).
- Batch todo upserts (upsert_todos_batch) and fewer DB commits during rebuilds to significantly shorten rebuild times.
- Thread-local DB connections and optional parallel indexing to speed indexing on multi-core machines.
- Add progress UI and non-blocking progress reporting (rich spinners/progress bar) during long operations.
- Configurable embedding chunk_size and chunking_method to tune embedding granularity and performance.

## Documentation

- Add and update README extensively (usage, examples, templates, recorder notes).
- Add TECHNICAL-OVERVIEW.md and Sphinx docs for recorder and developer docs.
- Add example outputs and SVGs for docs builds; update todo.md to reflect implemented items and remaining tasks.
- Document web viewer API, recorder configuration, and migration notes in README.

## Maintenance & Refactoring

- Split monolithic CLI into modular nb.cli package for maintainability and testability.
- Code cleanup: replace builtin open() with Path.open(), tighten typing imports, and suppress exception contexts where appropriate.
- Apply ruff/isort formatting, update pyproject with new dev dependencies (Sphinx, isort), and refresh the lockfile.
- Minor signature and import tidy-ups across core modules.

## Testing

- Add extensive unit and integration tests:
  - CLI tests (config, links, notebooks, notes, search, templates, todos).
  - Recorder formatting and transcriber datatypes tests.
  - Web handler and API tests.
  - Index/scanner/todos tests for race conditions and linked-note handling.
- Improve test fixtures and isolation (disable vector indexing during CLI tests) to make test suite faster and deterministic.

## Other Changes

- Add note aliases and command aliases (nb alias, nbt entrypoint).
- Many usability tweaks: short CLI flags for recording, improved CLI help text, editor launcher parsing with shlex, Unicode-safe stdout handling.
- Add notebook colors/icons and per-notebook config options (color, icon, todo_exclude).
- Bump package version to 0.2.0 and minor reformatting commits.
