# nb Roadmap & Idea Brainstorm

*A living wishlist. No idea is too wild — this is a fun, open-source-bound project, not a product plan.*
*Consolidates the open threads from `etc/brainstorm-claude.md`, `etc/claude-ideas-brainstorm.md`, `etc/ai-features.md`, and `etc/gemini-ideas-010526.md`, then pushes further.*

Legend: 🌙 moonshot · 🔌 integration · 🤖 AI · 🧠 knowledge · ⚡ quick win · 🛠 infra

---

## The North Star

`nb` is *plaintext-first with a brain*: markdown is the source of truth, SQLite + local embeddings are a rebuildable cache, and AI sits on top without ever owning your data. Every idea below should respect that — files stay portable, the index stays disposable, and intelligence is additive. The differentiator vs. Obsidian/Logseq/Notion is that `nb` is **terminal-native, scriptable, and AI-agentic from the ground up**, with zero lock-in.

Three big bets worth orienting the roadmap around:
1. **`nb` as an agent surface** — your notes become a tool other agents (Claude, etc.) can read and write via MCP.
2. **`nb` as ambient capture** — frictionless in (voice, mobile, share-sheet, email), structured out.
3. **`nb` as a thinking partner** — proactive, not just reactive, surfacing what you'd otherwise forget.

---

## 🌙 Moonshots (the wild ones)

### M1. `nb` as an MCP server — your notes as an agent tool
> 📐 **Designed in detail:** see [`etc/mcp-memory-spec.md`](etc/mcp-memory-spec.md) — pluggable cross-tool memory, tool schemas, `nb serve --mcp`, provenance, lint, and a 5-phase build plan.

Expose `nb` over the Model Context Protocol so Claude Code, Claude Desktop, or any MCP client can `search`, `read`, `create`, `complete-todo`, and `ask` against your notebooks. This flips the relationship: instead of `nb` calling an LLM, *agents call `nb`*. Suddenly "remember this", "what did I decide about X", and "add a todo" work from any AI surface, with your local files as the backing store. `fastmcp` is already a dependency — the plumbing is half there.
- Scoped/read-only tokens, per-notebook exposure, audit log of agent writes.
- Pairs with the daemon: a long-lived `nb serve --mcp`.

### M2. Autopilot daemon — a background agent that tends your garden
A `daemon.py` already exists. Grow it into an opt-in proactive agent that, on a schedule, does the boring maintenance you never get to:
- Triages `inbox.md` → suggests notebook/tags/links, queues for one-keystroke approval.
- Detects stale-but-open project notes ("30 days untouched, 4 open todos").
- Drafts the morning standup / evening wrap-up to today's note before you ask.
- Surfaces "you wrote about X and Y separately but never linked them."
- Everything lands as *proposals* in a review queue (`nb autopilot review`), never silent writes.

### M3. Time machine & memory resurfacing
Your notes are timestamped truth. Lean into time as a first-class axis:
- `nb on-this-day` — what you wrote/decided on this date in prior weeks/months/years.
- **Note decay & resurfacing**: spaced-repetition over *your own* notes — `nb resurface` pulls forgotten-but-important notes back up based on age × link-centrality × past-view frequency.
- `nb diff <note> --since "2 weeks ago"` — semantic diff of how a note evolved (git-backed, but rendered as meaning not lines).
- Scrub a notebook's state to any past date (read-only "as of" view via git).

### M4. Query language for notes & todos (`nbql`)
A real, composable query DSL that powers live views, the web UI, and saved searches:
```
todo where notebook=work and (due < +7d or priority=high) and not section=archived sort by due
note where tag=#research and modified > -30d and links-to "API design"
```
Saved as named views that auto-refresh, exportable as a markdown table embedded in a note (a "dynamic block" that re-renders on index). This is the unifying primitive under todo views, search, and stats.

### M5. Multiplayer notebooks
> ✅ **Phase 1 shipped:** shared notebooks (external notebook = its own git repo, registered
> per-machine via gitignored config), `nb team` identity, `@owner(handle)` todo ownership with
> `nb todo --mine`/`--owner`, and `nb share add/init/list/status/sync`. See CLAUDE.md
> "Multiplayer Notebooks" and `nb/core/share.py` + `nb/core/team.py`.

Shared notebooks over git (you already have git sync). Still to add:
- Per-note presence/attribution (who touched what, via git blame surfaced in the UI).
- `@mentions` that generate todos for the mentioned person on their next sync.
- Conflict-aware merge for daily notes (section-level, not line-level).
- A "team digest" — what the team shipped this week, generated across the shared repo.

### M6. Digital garden / publish pipeline
`nb publish` → a static site (or single self-contained HTML) of selected notes with working wiki-links, backlinks, and graph — your `nb web` viewer, frozen and shareable. Front-matter flag `publish: true` opts a note in. Bonus: `nb publish --share <note>` for a one-off expiring link.

---

## 🤖 AI & Agentic

- **Natural-language command bus** — `nb do "move all API todos to next week and tag them #q3"`: parse intent → show a concrete diff → confirm → execute. The assistant exists; this is the deterministic, reviewable version.
- **Auto-tagging / auto-filing** (carry-over, Gemini #4) — on `clip`/`inbox`/`import`, suggest 3–5 *existing* tags + best-fit notebook using the fast model, to fight tag sprawl.
- **Smart date & entity extraction** — `nb add "call John next tuesday about Acme renewal"` → `@due(tuesday)`, links to John/Acme notes if they exist.
- **Meeting prep** (carry-over) — `nb meeting prep "Call with Acme"`: pull calendar event + notes mentioning attendees + web search → briefing note.
- **Voice → structured** — extend recording/transcribe: dictate → LLM cleanup → polished prose or extracted bullets/actions.
- **Knowledge gaps** — "you write a lot about X but never Y, a related concept" from embedding-space analysis.
- **Concept clustering** — auto-group notes into emergent themes; visualize theme evolution over time.
- **Local-only AI mode** — full offline path (Ollama for both embeddings *and* generation) for privacy-sensitive notebooks, with a per-notebook `ai: local|cloud|off` policy.
- **Cost & token ledger** — `nb ai usage` showing spend by command/model over time.

## 🧠 Knowledge Management

- **Recurring todos** (carry-over, requested in 3 docs) — `@repeat(weekly)` / `@every(monday)`: on completion, roll `@due` forward instead of checking off; log completion history. *High-demand, ship early.*
- **Todo dependencies & blocking** (carry-over, in `todo.md`) — `@blocked-by(id)`, gantt/critical-path view, hide blocked items from active list with a `--blocked` reveal.
- **`@startby` dates** (carry-over, in `todo.md`) — distinct from due; powers "what can I start now."
- **Auto-cross-linking within a week** (carry-over, in `todo.md`) — chain daily notes linearly + suggest intra-week links.
- **Bi-directional link refactoring** (carry-over, Gemini #2) — on `nb mv`, find backlinks and offer to rewrite them so links never break.
- **Zettelkasten / atomic notes** — first-class fleeting vs. permanent vs. literature note types; note "maturity" tracking (draft → polished).
- **Smart connections** — "these two notes are semantically close but unlinked — connect?" inline while editing or as a daemon proposal.
- **Tag hierarchy** — `#project/subproject` with rollup counts; tag-rename/merge with similarity auto-suggest (carry-over, in `todo.md`).
- **Calendar view** (carry-over, in `todo.md`) — `nb calendar [month]` for due dates + daily-note coverage heatmap.

## ⚡ Capture & Quick Wins

- **Quick-capture hotkey / tray** — global shortcut → tiny input → appends to inbox without opening a terminal (Windows: `win11toast` already noted for reminders).
- **Due-date reminders** (carry-over, in `todo.md`) — optional `win11toast` notifications; morning briefing push.
- **Time tracking / Pomodoro** (carry-over, Gemini #5) — `nb todo start/pause` writes `time_entries`, appends `@spent(25m)`; `nb stats --time` by notebook/tag; focus timer tied to the in-progress `[^]` todo.
- **`nb scan`** — OCR an image/screenshot to a note (tesseract local, cloud OCR optional for handwriting).
- **Watch folder** — auto-clip files dropped into a directory.
- **`nb doctor`** (carry-over, spec'd in `ai-features.md`) — broken links, orphan attachments, untagged/isolated notes, invalid dates, index/FS mismatch.
- **`nb undo`** — reverse the last mutating operation (git-backed snapshot makes this cheap).
- **Archive notebooks/notes** (carry-over, in `todo.md`) — archived but still searchable.
- **`nb changelog`** (carry-over, in `todo.md`) — bundle CHANGELOG into the package, view from CLI.
- **Smart refile TUI** (carry-over, Gemini #3) — split-pane inbox-zero: items left, fuzzy notebook/note picker right, one key to refile.
- **Pinned notes in todos** (carry-over, in `todo.md`) — include pinned notes' todos while pinned.

## 🔌 Integrations

- **Calendar (two-way)** — read events into planning (Outlook via `pywin32`/Graph already scoped in `ai-features.md`); export `@due` items back as calendar entries.
- **Email-to-inbox** — forward an email → becomes a note/todo (parse subject/body, attach links).
- **GitHub/Linear/Jira bridge** — `nb` todos ↔ issues: complete locally, close upstream; pull assigned issues into a notebook.
- **Obsidian/Logseq compatibility** — parse their link/block-ref formats; import/export so people can try `nb` over an existing vault.
- **Importers** — bulk import from Notion/Evernote/Apple Notes/plain folders.
- **Shell prompt integration** — show current in-progress todo / today's note count in your shell prompt; `cd` into a repo → surface that repo's linked notes.

## 🛠 Platform & Infra

- **Plugin / hook system** (carry-over) — `nb hook pre-save <script>`, event bus (note-created, todo-completed) so users script their own automations. Turns `nb` into a platform.
- **Built-in scheduler** — `nb cron` to run `nb` commands on a schedule (daily standup, weekly review, autopilot pass) cross-platform.
- **REST API + mobile PWA** — the `nb web` viewer already exists; add a write API + offline-capable PWA for capture/todo-complete on the phone. (Architecture options sketched in `claude-ideas-brainstorm.md`: Lambda+git, home-server+Tailscale, cheap VPS.)
- **Dashboard TUI** — full-screen home: today's note, due todos, recent, stats, calendar — keyboard-driven.
- **Theming** — custom palettes beyond per-notebook colors; light/dark; export web UI themes.
- **Bulk operations** — multi-select in TUI for batch todo edits / note moves.

## 📊 Analytics & Delight

- **Activity heatmap** — GitHub-style contribution graph of note/todo activity (`nb activity`).
- **Velocity & patterns** — completion trends, "you finish 40% more on Tuesdays," burndown for project notebooks.
- **Writing streaks + gentle gamification** — don't-break-the-chain streaks, optional XP/badges (kept tasteful and opt-in).
- **Year in Review** — annual visual summary; auto weekly/monthly digests.
- **Word count / reading time** per note; most-frequent themes over time.

---

## Suggested Sequencing (rough, not binding)

| Horizon | Theme | Candidates |
|---|---|---|
| **Now** (quick, high-demand) | Todo power-ups | Recurring todos, `@startby`, dependencies, `nb doctor`, due reminders, calendar view |
| **Next** (differentiators) | Agentic + capture | MCP server, autopilot daemon (proposals), quick-capture hotkey, time tracking |
| **Later** (big builds) | Reach + scale | Mobile PWA + write API, nbql query language, two-way calendar, publish pipeline |
| **Someday** (moonshots) | Identity | Multiplayer notebooks, time machine / resurfacing, local-only AI mode |

---

## Open Questions to Chew On

- **MCP first or mobile first?** Both are "access from elsewhere" — MCP is cheaper and more on-brand; mobile reaches more daily moments.
- **How proactive should autopilot be?** Pure proposal-queue (safe) vs. trusted auto-actions for low-risk things (auto-tag, auto-link).
- **Is `nbql` worth it,** or do incremental flags on existing commands cover 90%? A real DSL pays off only if it unifies views + web + dynamic blocks.
- **Where's the line on gamification** before it feels gimmicky for a tool aimed at CLI power users?
- **Privacy posture:** ship a "this notebook never touches a cloud LLM" guarantee as a headline feature?
