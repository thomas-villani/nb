# v0.4.3 - 2025-12-23

Patch release that introduces AI-powered daily/weekly reviews and morning standups, plus stable note IDs for faster lookups. Includes CLI/TUI wiring, docs, and tests.

## New Features

- Add AI-powered review and standup flows
  - New CLI commands: `nb review` (group with `day` and `week`) and `nb standup`
  - Engines implemented at `nb/core/ai/review.py` and `nb/core/ai/standup.py` to gather todos/calendar context, build LLM prompts, and produce streaming or non-streaming outputs
  - Support saving outputs to notes: formatting/append to daily or specified notes, notebook/tag filtering, custom prompts, streaming, and model selection (`smart` / `fast`)
  - CLI wiring updated in `nb/cli/ai.py` to register commands and display contextual summaries before generation
  - Documentation and README examples added showing usage and available sections (e.g., Completed, Carrying Over, Wins, Improvements, Yesterday, Today's Schedule, Focus Areas)

- Stable note IDs for faster lookup and consistent behavior
  - Set `Note.id` using `make_note_id` in `nb/cli/search.py` for streamed and listed notes
  - Set `Note.id` using `make_note_id` in `nb/tui/search.py` when creating notes for the viewer
  - Enables quicker loading and consistent inclusion of notes across CLI and TUI flows; `todo.md` updated to mark related tasks completed

## Tests & Reliability

- Add tests `tests/test_cli_ai.py` covering CLI help output, option parsing, and graceful failure when LLM configuration (API key) is missing
- AI flows handle missing calendar integrations gracefully and surface LLM configuration errors with actionable hints for developers/users

## Other Changes

- Bumped package version 0.4.2 → 0.4.3

# v0.4.2 - 2025-12-23

This patch release adds pinned-note support, stable note IDs, a files-only search mode, and a DB schema bump to v17. It also introduces a breaking change for how API keys are loaded (moved to environment/.env-only) and includes a few maintenance fixes.

## New Features

- Add pin/unpin/pinned CLI commands and an nb.core.pinned module to manage pinned notes stored in the database; repinning updates the note timestamp. ([dafca5c])
- Introduce stable note IDs via make_note_id and add an id field to the Note model for stable lookups; note IDs are stored on upsert/index and used when rebuilding/syncing the search index. ([dafca5c])
- Add get_note_by_id API with prefix matching for fast resolution of notes by stable ID. ([dafca5c])
- Add --files-only (-l) option to search and grep to output file paths only (useful for external tooling and scripts). ([dafca5c])
- Change history/list behaviors:
  - history now defaults to recently modified notes; use --viewed / -v to show view history.
  - list now shows N recently modified notes per notebook with a new --limit / -l option (default 5). ([dafca5c])
- Bump DB schema to v17: add notes.id column, an index for id lookups, and a pinned_notes table with appropriate indices; include a migration script. ([dafca5c])

## Breaking Changes

- API key handling moved to environment/.env only — keys in config.yaml are now ignored. ([0f22574])
  - Recognized environment variables: OPENAI_API_KEY, ANTHROPIC_API_KEY, SERPER_API_KEY, DEEPGRAM_API_KEY, RAINDROP_API_KEY.
  - Added env_file support to config (Config.env_file) and dotenv loading priority:
    shell environment > custom env_file (config) > default .nb/.env (default loading uses override=False so shell vars are never overwritten).
  - New command: nb config api-keys — displays detected API keys (masked) and shows which env/.env sources exist.
  - Config/dataclass changes: embedding/llm/search/recorder/raindrop API keys are populated from environment at runtime; they are not persisted in config.yaml and cannot be configured via CLI/config set commands.
  - save_config now persists env_file and nb config exposes get/set for env_file.
  - Tests updated to assert API keys come from environment.

## Bug Fixes

- Fix issue in pyproject.toml and add an 'all' dependency group to simplify developer installs. ([0934028])
- Misc: update CHANGELOG.md. ([4398bb4])
- Bump package version to 0.4.2. ([8af88ab])

## Migration / Upgrade Notes (for developers)

- Database migration: schema bumped to v17. Run migrations (automatic if migration is enabled in your setup). If you manage migrations manually, apply the included migration script to add notes.id and the pinned_notes table before using pinned-note features or id lookups.
- API keys:
  - Ensure your API keys are provided via environment variables or a gitignored .env file.
  - To persist a custom .env path in config: nb config set env_file /path/to/.env
  - Example (bash):
    - export OPENAI_API_KEY="sk-..."
    - or create ~/.nb/.env with OPENAI_API_KEY=sk-... and then nb config set env_file ~/.nb/.env
  - Verify detected keys with: nb config api-keys
  - Note: any API keys present in config.yaml will be ignored after this release.
- If you rely on automated tooling or CI that previously read keys from config.yaml, update pipelines to set required env vars or reference an env_file.

# v0.4.1 - 2025-12-21

Patch release with optional AI-generated TL;DRs for inbox clipping, inbox/template detection fixes, tests and docs updates.

## New Features

- [3c8cdf3] Add AI-generated ultra-brief TL;DR summaries to inbox clipping flow
  - Add --ai / --no-ai flags to `nb inbox pull` (CLI flag overrides inbox.auto_summarize config)
  - Introduce inbox.auto_summarize config option (default: true) and wire CLI get/set behavior
  - Add `generate_content_tldr` helper in `nb.core.ai.summarize` to produce ultra-brief summaries with graceful fallback when an LLM or API key is unavailable
  - Generate and write summaries to note frontmatter during clipping; failures or missing keys do not block clipping
  - Update README to document AI summary behavior and CLI usage; bump dependency to released all2md package

## Bug Fixes

- [7703b8e] Fix inbox detection and date-based notebook templating
  - Ensure date-based templates are used when an explicit `dt` is provided (prevents filename-munged dates in templates even for non-date-based notebooks)
  - Update `nb today` CLI to pass both `dt` and `name` so templates can format dates correctly
  - Fix inbox detection in the indexer by comparing resolved full paths against `notes_root/todo` (prevents `todo.md` files in subdirectories from being treated as the global inbox)
  - Tweak completed-todo styles: reduce opacity, add left border color, dim meta text

## Tests & Documentation

- Add tests for inbox config handling and CLI config get/set behavior
- Add tests for `generate_content_tldr` including mocking and truncation behavior
- Add tests covering dt-driven templating and inbox detection edge cases to prevent regressions

# v0.4.0 - 2025-12-21

This minor release adds a broad set of AI features (assistant, research, planning/summarization, agentic/tool calling), a refactored web viewer/webserver, improved config/env key loading, and several refactors to note parsing and indexing. It contains 14 commits and introduces 4 breaking changes — see "Breaking Changes" for migration guidance.

## New Features

- Interactive AI assistant
  - New CLI: `nb assistant` with options for notebook focus, calendar integration, model selection (smart/fast), dry-run/token-budget controls, and max tool calls.
  - Implements assistant session context (todos, calendar, recent notes), an LLM loop with streaming support, tool routing (read/write), and a confirmation-based queue/execute flow for any filesystem writes.
  - Assistant tools implemented: search_notes, read_note, query_todos, get_project_stats, get_calendar_events, create_todo, update_todo, create_note, append_to_note.
  - Tests added for context gathering, action queuing, routing, and basic write execution flows.

- Research agent and `nb research`
  - New `nb research` command with streaming/non-streaming flows, web/news/scholar/patents search (Serper), fetch_url, optional local vector DB indexing, and reporting saved to notes.
  - Research agent supports max sources/strategy/vectordb/token-budget and will save reports to a specified notebook or daily note when requested.

- Planning, summarization, and TL;DR
  - New `plan` group (`plan week`, `plan today`) with interactive and streaming modes.
  - `summarize` and `tldr` commands supporting single- and multi-note (map-reduce) summarization, front-matter updates, and save-to-note options.

- Agentic ask / tool-calling
  - `nb ask` gains `--agentic` and `--max-tool-calls` to enable an agentic RAG loop that can call tools (search, read, todos, project stats, complete_answer) for complex queries.
  - Adds ToolDefinition/ToolCall/ToolResult support in the LLM client and exposes agentic helpers for programmatic use.

- LLM / RAG improvements
  - New LLM client abstraction with Anthropic/OpenAI support, streaming, and tool-call serialization/parsing.
  - RAG-based ask implementation with enhanced retrieval, context truncation, and token-budget handling.

- Web viewer refactor and webserver
  - Replaced single-file viewer with `nb.web` package (templates/static) and added `nb.webserver.run_server` to serve the assembled front-end.

- Embedding/indexing improvements
  - Strip markdown images before embedding to avoid large token usage and make indexing more robust; logs and falls back on failure.

- Config / .env support
  - Load API keys/config (SERPER_API_KEY, DEEPGRAM_API_KEY) from notes_root/.nb/.env using python-dotenv (config takes precedence over env). Keys are not persisted to config files for security.
  - Add config-backed key handlers and updated search/transcriber to prefer get_config().

## Breaking Changes (migration guidance)

- Unified output and notebook flags
  - CLI flags changed: use -n for notebook scope (was -b) and use --output / -o to save AI-generated content to notes (replaces previous --note / -N save behavior).
  - Migration: update scripts/aliases and automation to use `-n NOTEBOOK` and `--output <today|NOTEBOOK/NOTE|NOTE-PATH>`; `ask` still accepts -N for targeting a specific note in some contexts.

- Web viewer refactor
  - Removed old `nb/web.py` and `nb.web.TEMPLATE`.
  - Migration: update imports and server start code to use `nb.web.get_template()` where template access is needed, and use `nb.webserver.run_server()` to run the web server. Ensure packaging includes web static files (pyproject has been updated).

- Ask command exposed at top-level; old ai group removed
  - The `nb ai ask` group has been removed; use `nb ask` (top-level command) instead.
  - Migration: replace any `nb ai ask ...` invocations with `nb ask ...` and update documentation/scripts.

- Standardized CLI short flags
  - Many short flags were changed to avoid conflicts and improve consistency (notably: `-y` -> `-f` (force), `-f` -> `-F` (full paths), `-t` -> `-T` (tree display), `-l` -> `-L`, reassigned `-N` usages).
  - Migration: audit and update any scripts, shell completions, aliases, or automation that depend on previous single-letter short flags. Consult `nb --help` for the updated mappings.

## Bug Fixes & Tweaks

- Removed test reliance on max_tokens and stop injecting a default max_tokens into LLM request bodies unless explicitly provided.
- Improve todos.find_todo_line: increased search radius and full-file fallback for moved/edited files.
- Improved robustness when upserting documents: fallback logging if image-stripping transform fails.
- Normalize path handling across modules: replace ad-hoc backslash replacements with a centralized normalize_path helper.

## Internal / Refactors

- Extracted note parsing into nb/core/note_parser.py and consolidated regex patterns in nb/utils/patterns.py to break circular imports and centralize parsing helpers.
- Re-exported parsing helpers from nb/core/notes.py for compatibility.
- Reorganized model name mappings and updated default model names for Anthropic (legacy → new names).
- Exposed agentic helpers and types for convenient imports; reorganized CLI registration to reflect top-level commands.
- pyproject and lockfile updates: introduced dependency groups and optional extras (recorder, calendar, localvectordb), added python-dotenv and all2md extras, and kept uv.lock in sync.

## Tests

- Added/updated tests for assistant, agentic ask, research, planning, summarization, and calendar integration.
- Updated fixtures/tests to patch get_config() where modules import configuration at module level and added safeguards to avoid accidental deletion of real vector indexes during tests.

If you rely on CLI short flags, the ai command group, the old web template API, or the previous save-to-note flags, update your scripts and tooling as noted in the "Breaking Changes" section.

# v0.3.2 - 2025-12-16

Patch release adding Git integration for notes, recorder device testing/auto-config, combined tag views, and a handful of usability bug fixes. No breaking changes.

## New Features

- Add Git integration for notes
  - New nb.core.git module: init, status, commit, commit_all, push, pull, sync, log, remote, get_status plus helper types for conflicts/errors
  - CLI commands under `nb git ...`: init, status, commit, push, pull, sync, log, remote; commands registered in `nb.cli`
  - New GitConfig in `nb.config` with parse/save logic and CLI bindings (list/get/set)
  - Optional auto-commit hooks integrated into notes operations (create, edit, delete, move); configurable and non-blocking on errors
  - Defaults: `git.enabled = false` (off by default)
  - Adds gitpython dependency (pyproject.toml / lockfile entries)

- Add recorder device testing and auto-configuration
  - New `nb record test` CLI command to scan, test and recommend microphone / loopback devices and optionally persist working config
  - Helpers to detect device roles (`_is_microphone_device`, `_is_loopback_device`), `test_device()` to verify device openability, and `find_best_devices()` selection logic

- Combined tags view and tag filtering
  - Show tags aggregated from both notes and todos by default, with source breakdown (e.g., "18t/2n")
  - New CLI flags `--todos` (`-t`) and `--notes` to filter tag sources (mutually exclusive)
  - Enforce stricter tag format rules (start with a letter, allow letters/numbers/hyphens/underscores, stored lowercase) and exclude hex color codes from tags

## Improvements

- Tag handling and CLI presentation
  - Update tag parsing / cleaning to use `is_valid_tag` and avoid treating color codes as tags
  - `get_tag_stats` now aggregates todo and note tag counts and returns per-source breakdown when requested
  - CLI shows aggregated counts per notebook/note and top-3 notes per notebook; source breakdown shown only when both sources are displayed

- Recorder and device selection
  - `find_best_devices()` and improved `find_default_devices()` with API-priority logic (WASAPI / DirectSound / WDM-KS)
  - Persist device recommendations to YAML and surface user tips (e.g., enable Stereo Mix on Windows)
  - Validate devices in `start_recording()` and raise clear errors when a chosen device has no input channels to avoid silent failures

- Usability and behavior
  - Auto-commit behavior is configurable and non-blocking to avoid blocking note operations on VCS errors
  - Create `.gitignore` template generation when initializing git-aware notebooks

## Bug Fixes

- Fix review selection and navigation
  - Use highlighted index for current todo selection so arrow-key navigation reflects the highlighted item without requiring Enter
  - Replace id-based selection fallback with highlighted-index lookup and first-item fallback
  - Implement `remove_current` to delete the highlighted todo and update highlight (or quit when list becomes empty)
  - Ensure mark-started and skip actions remove the todo and update stats/messages
  - Simplify quit behavior and ensure the session exits when all todos are processed
  - Remove in-app summary view/navigation; print concise summary to stdout after the app quits

## Tests

- Add comprehensive tests for core git functions and CLI behavior (tests/test_git.py)
- Add device detection and recommendation tests for recorder helpers

## Chores

- Bumped package version to v0.3.2 and updated lockfile entries as needed

# v0.3.1 - 2025-12-15

Patch release with an interactive TUI search, attachment indexing and management, note/todo move & copy plus export capabilities, safer vector reinitialization for embedding provider changes, and config serialization improvements. Includes one breaking CLI change (todo aliases / flags).

## New Features

- Interactive TUI search
  - Added nb/tui/search.py: Wijjit-based interactive search UI with live filtering, notebook/tag dropdowns, recency boost, chunk preview, and keybindings for edit, open stream, copy path, and full-note view.
  - CLI: `nb search --interactive` / `-i` (optional QUERY) to launch TUI; non-interactive queries validated when TUI not requested.
  - Search internals: nb/index/search.py now supports async search_async(...) (date filters, score threshold, optional recency boost) and returns a chunk snippet in results. TUI ensures DB cleanup via reset_search().
  - Added pyperclip (and types-pyperclip) for clipboard support used by the TUI.

- Attachment indexing & management
  - Index attachments when notes are indexed; scanner hooks to delete/re-extract and batch upsert attachments.
  - New attachment DB layer: nb/index/attachments_repo.py with CRUD, querying, stats, orphan detection, and content extraction.
  - CLI: attachment management commands (attach --all/--type/--notebook, stats, orphans with --delete). Attachment DB operations are best-effort and do not block attaching.

- Note/todo move & copy, and export
  - CLI: `nb mv` / `nb cp` for moving and copying notes (with --force). `nb todo mv` / `nb todo cp` for moving/copying todos (single or many, supports note::Section syntax).
  - Core implementations: move_note, copy_note, move_todo, copy_todo, and batch variants that preserve raw markdown and regenerate todo IDs.
  - Export feature: nb/core/export.py and nb/cli/export.py to export single notes or entire notebooks to pdf/docx/html via all2md. Supports sorting, reversing, and notebook concatenation.

- Indexing: reset vectors option
  - Added `--reset-vectors` to `nb index` to clear existing vector index before rebuilding, enabling safe switching of embedding providers.
  - Validation: `--reset-vectors` cannot be used with `--rebuild`; it requires `--vectors-only` or `--embeddings`.

## Improvements & Refactorings

- Config serialization and boolean parsing
  - Added _serialize_dataclass_fields and _serialize_notebook helpers; save_config now introspects dataclass fields and writes concise YAML (only non-default/non-None values).
  - Sensitive tokens (e.g., raindrop.api_token) excluded from saved config; recommend providing API tokens via environment variables.
  - Added parse_bool_strict and used in set_config_value to reject ambiguous boolean strings and produce clearer errors.
  - Added get_default_transcript_notebook to choose sensible defaults for record/transcribe commands (daily → first date-based → first notebook).
  - Normalized note paths when recording views to avoid duplicate DB entries.
  - Added tests covering boolean parsing, dataclass serialization, and default transcript notebook selection.

- Misc developer-facing improvements
  - Use DATE(...) in todos_repo queries/stats to compare dates-only and avoid time-of-day comparison bugs.
  - Use shared DB helper (get_db) in web.get_alias_for_path to ensure consistent DB initialization.
  - Small TUI cleanup and todo.md updates marking interactive search as implemented.
  - Updated lockfile and dependency hashes as needed.

## Bug Fixes

- Fixed clip restore to always restore config.auto_tag_domain using try/finally.
- Swallow DB errors on attachment upsert during CLI attach so attach operations still succeed.
- Fixed minor formatting and test expectations after changes (todo ID display length, config tests clearing EDITOR env).
- Added helpful ImportError for missing all2md in export paths to guide installation when export is used.

## Breaking Changes

- CLI aliases and flags changed related to todos and ID display:
  - `td` alias renamed to `tdd`.
  - `--due-today` renamed to `--today` (short `-T`).
  - `--due-week` renamed to `--week` (short `-W`).
  - TODO ID display length standardized to 6 characters across listing/add/move/copy/status commands.
- Migration guidance
  - Update any scripts, aliases, shell completions, CI workflows, or third-party integrations that relied on `td`, `--due-today`, or `--due-week` to use the new names (`tdd`, `--today`/`-T`, `--week`/`-W`).
  - If your tooling parses todo IDs, ensure it accounts for 6-character displayed IDs.
  - When changing embedding providers, reinitialize vectors with:
    - nb index --reset-vectors --vectors-only
    - or nb index --reset-vectors --embeddings
    Note: `--reset-vectors` cannot be combined with `--rebuild`.
  - Export now validates presence of all2md and raises a clear ImportError when missing; install all2md in environments that use export features.

# v0.3.0 - 2025-12-13

This minor release adds a Raindrop-based inbox workflow, major TUI/stream improvements (including interactive search and continuous streaming), a Wijjit-powered TUI rewrite for todos/review/stream, and several developer-facing fixes and refactors (indexing progress, stream pipe mode, DB schema changes). Includes docs and unit tests for the new features.

## New Features

- Add Raindrop "inbox" integration and CLI group (nb inbox) with commands: list, pull, clear, history
  - Implement Raindrop API client and inbox core (list, archive/delete, duplicate detection)
  - New config types: InboxConfig / RaindropConfig; RAINDROP_API_KEY is read from environment (token is not persisted to disk)
  - Add DB migration/schema v16 to track inbox_items and clipping/skipped/archived history
  - Hook CLI flow to validate target notebook availability before clipping
  - Add docs, README examples, and unit tests covering config parsing, RaindropItem behavior, DB tracking, and CLI flows

- Replace legacy terminal UIs with a Wijjit-based TUI for todos, review and stream
  - Richer interactions: modals, dialogs, in-app editor, keyboard handlers, lazy loading
  - New shared utilities (nb/tui/wijjit_utils.py) for formatting due dates, sources, and common helpers
  - Add wijjit and related runtime deps to pyproject.toml and lock files

## Enhancements

- Stream / list / TUI improvements
  - Add interactive search to the TUI ("/" key, search bar, Find/Clear, on-demand content loading)
  - Add --continuous / -c (continuous mode) to nb stream for a maximized, scrollable flow with lazy loading and dividers
  - Add --by-date option to sort stream output by note date (default remains recently modified)
  - nb list now accepts an optional positional NOTEBOOK argument (positional takes precedence over -n/--notebook)
  - When nb stream output is piped (non-TTY), emit plain-text headers and content for downstream processing
  - Refactor stream internals: helpers to convert paths -> Note, dedicated output path for pipe-mode, improved deduping of recently viewed notes

- Indexing and progress
  - Fix progress callbacks in scanner/index routines to report incremental deltas (pass increments instead of cumulative totals)
  - Update index command to track and print concise summary counts (notes scanned, linked, search sync, removed)
  - Adjust progress labels for clarity (e.g. "Scanning" replaces "Indexing")

## Bug Fixes

- Fix progress reporting so progress bars advance correctly (callbacks now receive delta counts)
- Fix pyproject.toml issues and related packaging metadata

## Developer / Migration Notes

- DB migration to schema v16 added to track inbox_items; run your migration workflow (nb db migrate/upgrade) before using inbox features
- on_progress callback signature changed: callbacks now receive incremental deltas (int) instead of cumulative totals. Update any external callers or integrations that register progress callbacks.
- New runtime deps (wijjit) added — update your environment/lock files accordingly
- Stream TUI reads note content on demand for search; consider adding an index if working with very large collections to avoid I/O spikes
- Token handling for Raindrop: RAINDROP_API_KEY is read from the environment and tokens are deliberately not persisted to disk for privacy/security
- Tests and docs were added/updated for inbox, stream, and TUI features — consult docs/commands and README for usage and examples

## Internal

- Add tests covering config parsing, Raindrop items, DB tracking, CLI behaviors, and TUI flows
- Normalize note paths in todos_repo.query_todos to forward slashes for consistent DB filtering
- Misc: version bumps and housekeeping commits to align packaging and CI files

# 0.2.5 - 2025-12-13

## New Features

- **Named priority syntax**: Use `@priority(low)`, `@priority(medium)`, `@priority(high)` as alternatives to numeric `@priority(1/2/3)` syntax. Case-insensitive.

- **Relative date syntax (+N)**: Use `+7` for "7 days from now" in `nb todo due` and `@due()` metadata. Examples: `nb todo due abc +7`, `@due(+30)`.

- **Log command**: New `nb log` command appends timestamped content to notes using configured date/time formats.
  ```bash
  nb log "Started feature X"        # "2025-12-12 14:30: Started feature X"
  nb log "Note" --note project      # Log to specific note
  ```

- **File capture with all2md**: The `nb clip` command now supports local files in addition to URLs. Convert PDF, DOCX, PPTX, and other formats to markdown notes.
  ```bash
  nb clip ~/Documents/report.pdf
  nb clip ./meeting.docx -n work
  ```

## Improvements

- **Overdue by notebook stats**: The `nb stats --by-notebook` panel now displays an "Overdue" column showing the count of overdue todos per notebook (highlighted in red).

---

# v0.2.4 - 2025-12-04

Patch release with usability and CLI improvements: open notes by index from history, deterministic/tighter todo sorting, a shortcut to open the last-modified note, and various CLI/help updates. No breaking changes.

## New Features

- [629ee5b] Add --open INDEX to nb history
  - Open a note by its 1-based index from the history list (works with grouped and ungrouped views)
  - History entries are now numbered with consistent width and the index range is validated before opening in the editor
  - Preserves original indices when grouping by notebook so --open is stable in grouped view
  - Updated help and examples to document opening by index

- [6ce2cb5] Add support for "last" note reference in nb open
  - `nb open last` opens the most recently modified note (optionally constrained to a notebook)
  - Uses get_last_modified_note under the hood; prints user-friendly messages and exits when no notes are found

## Improvements

- [6ce2cb5] Revise todo sorting for deterministic, developer-friendly order
  - New sort precedence: due-section -> due date (soonest) -> created date (oldest) -> priority -> file/section -> line number
  - get_sorted_todos and CLI list sorting updated to follow this order
  - Removes entries for files that no longer exist by calling remove_deleted_notes() before listing todos

- [629ee5b] Improve note resolution behavior and scoping
  - When a single notebook is in scope, use it as context/hint for resolving todo-note references
  - Pass notebook hint to linked-note lookup to constrain resolved links (linked-file lookup remains unchanged)

- [6ce2cb5] CLI ergonomics and option changes
  - Introduce -xt for --exclude-tag and -xn for --exclude-notebook
  - Reassign -N to --note PATH (see updated help text)
  - Update todo.md with the new default sort note and future enhancement items
  - Note: CLI short flags changed — update any scripts or aliases accordingly

- [9a185e7] Remove artificial max terminal size of 150 so output can use full terminal dimensions

## Chore

- [f70dd99] Bump version: 0.2.3 → 0.2.4

# v0.2.3 - 2025-12-03

This patch release contains documentation and example asset additions, several developer-facing robustness and indexing improvements, a new Kanban/completed-todos flow (CLI + web), small CLI quality-of-life changes, and assorted refactors/tests/housekeeping. No breaking changes.

## New Features

- Add Kanban support to todos:
  - CLI flags: --kanban / -k and --board / -b; new command `nb todo completed`
  - Terminal kanban renderer with configurable boards/columns
  - Web UI kanban with client rendering, drag-and-drop, and API endpoints (/api/kanban/boards, /api/kanban/column, /api/todos/:id/status)
  - Kanban boards persisted via Config (KanbanBoard/KanbanColumn) with parsing/load/save support
  - Todo queries extended to support completed_date_start / completed_date_end filters
- CLI polish and aliases:
  - Added --about / -A to print an ASCII-rich About panel (uses rich.Panel)
  - Added aliases/shortcuts (ls → list, td → todo done, now → todo --today)
  - Prompt to open existing note when creating a note that already exists
  - Notebook path display changed to show ~/notes/<name> for local notebooks
  - When editing a todo, capture file mtime and re-sync/reindex after editor returns; print sync status

## Improvements

- Indexing and todo handling:
  - Normalize relative due dates before hashing/indexing and use future-oriented parsing so @due(Friday) resolves to the upcoming Friday (parse_fuzzy_datetime_future)
  - Consolidated re-index logic: call index_note(...) for full reindex on edits and added index_note_threadsafe for background/threaded indexing to avoid SQLite threading issues
  - Vector indexing made more resilient: added logging, thread lock, and failure handling to avoid crashing the indexer when embedding/searching fails
  - Compute mtime after due-date normalization and batch upsert todos for performance
- Web server and security:
  - Hardened path handling: validate absolute paths against configured allowed roots (_is_allowed_external_path) and always resolve relative paths against notes_root to prevent arbitrary file reads
  - get_alias_for_path now resolves paths against notes_root before comparison
  - Bind development web server to 127.0.0.1 by default
- Recorder and audio:
  - Rewrote recorder writer thread to incrementally flush audio to disk, reduce memory use, support stereo mix (mic left / loopback right), and handle missing channels; extracted stereo processing into _process_stereo_chunk
- CLI/help/docs tooling:
  - Docs example generation updated (docs/generate_examples.py) to set up a temporary notebook, invoke real CLI renderers, manage env/indexing, save SVG outputs, and improve logging/cleanup
  - Small CLI validation: warn on invalid week_start_day in stats
  - Remove web CSS max-width constraint and tweak todo markdown checklist rendering
- Other developer ergonomics:
  - Make rebuild_db more verbose on vector clear failures (debug logging)
  - Add ruff/pyproject excludes for common build/dev directories

## Bug Fixes

- Fixed broken test introduced by a changed flag and other test stabilizations
- Fixed tiny error in notes.py
- Minor fix to `nb todo -x` behavior
- Fixed version string in pyproject.toml and bumped package version to 0.2.3
- Updated CHANGELOG.md as part of release housekeeping

## Refactor / Code Quality

- Large-formatting and typing cleanup across the codebase:
  - Normalized function signature formatting, import ordering, and general whitespace
  - Added/refined type hints and mypy overrides for third-party libs in pyproject.toml
  - Replaced several lambda progress callbacks with direct callables, added defensive checks and assertions, and renamed variables to reduce shadowing risks
  - Cosmetic-only changes to prepare for stricter linting/type checks; no behavior changes intended

## Tests & CI

- Tests: reset global config and database singletons in fixtures to avoid cross-test interference
- Adjusted tests to match refactors and improved deterministic behavior in indexing/mtime handling

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
