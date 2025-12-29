# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Install dependencies
uv sync              # Production dependencies
uv sync --dev        # Include dev tools (pytest, ruff, black, mypy)

# Run tests
.venv/Scripts/python.exe -m pytest        # All tests
.venv/Scripts/python.exe -m pytest tests/test_cli.py                  # Single file
.venv/Scripts/python.exe -m pytest tests/test_cli.py::test_today -v   # Single test, verbose

# Code quality
.venv/Scripts/python.exe -m ruff check nb/ --fix    # Lint and auto-fix
.venv/Scripts/python.exe -m black nb/               # Format
.venv/Scripts/python.exe -m mypy nb/                # Type check

# Run CLI locally
.venv/Scripts/nb.exe --help
```

## Architecture

```
nb/cli/         CLI commands (Click framework)
nb/core/        Business logic (note/todo operations)
nb/index/       SQLite database, file scanning, hybrid search
nb/tui/         Interactive terminal UI (Rich)
nb/utils/       Date parsing, markdown, hashing utilities
nb/models.py    Data models (Note, Todo, Attachment)
nb/config.py    Configuration management
```

**Data flow**: CLI commands → Core logic → Index layer → SQLite DB + markdown files

**Key principle**: Markdown files are the source of truth. The SQLite database (`notes_root/.nb/index.db`) is a cache that can be rebuilt anytime with `nb index --force`.

## Key Patterns

- **Todo extraction**: Parses `- [ ]`, `- [^]`, `- [x]` checkboxes with metadata (`@due()`, `@priority()`, `#tags`)
- **Change detection**: SHA256 hash per file for incremental indexing
- **Todo IDs**: First 8 chars of SHA256(path:content) - stable but changes if content/path changes (displayed as 6 chars in CLI for brevity)
- **Date-based notebooks**: Organize by week folders: `daily/2025/Nov25-Dec01/2025-11-27.md`
- **Hybrid search**: 70% semantic (vector embeddings) + 30% keyword (FTS5)

## API Key Configuration

API keys are **never stored in config.yaml** (which may be committed to VCS). They are loaded exclusively from environment variables.

**Priority order** (first found wins):
1. Shell environment variables (already set in your terminal)
2. Custom `.env` file (if `env_file` is set in config.yaml)
3. Default `.nb/.env` file in notes_root

**Supported API keys**:
| Environment Variable | Service | Used By |
|---------------------|---------|---------|
| `ANTHROPIC_API_KEY` | LLM (Claude) | AI commands (`nb ask`, `nb assistant`, etc.) when `llm.provider: anthropic` |
| `OPENAI_API_KEY` | LLM / Embeddings | AI commands when `llm.provider: openai`, or embeddings when `embeddings.provider: openai` |
| `SERPER_API_KEY` | Web Search | `nb research` command |
| `DEEPGRAM_API_KEY` | Transcription | `nb transcribe` command |
| `RAINDROP_API_KEY` | Inbox | `nb inbox` command |

**Example `.nb/.env` file**:
```
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=...
SERPER_API_KEY=...
```

**Useful commands**:
- `nb config api-keys` - Show detected API keys (masked) and their sources
- `nb config set env_file ~/secrets/nb.env` - Use a custom .env file path

## Testing

### Running Tests

```bash
# Fast tests (no API keys required) - default for CI
.venv/Scripts/python.exe -m pytest

# Contract tests (requires API keys in .env)
.venv/Scripts/python.exe -m pytest -m contract

# Vector/embeddings tests (requires OPENAI_API_KEY)
.venv/Scripts/python.exe -m pytest -m vectorized

# Exclude slow tests
.venv/Scripts/python.exe -m pytest -m "not contract and not vectorized"

# Run specific test file
.venv/Scripts/python.exe -m pytest tests/test_cli.py -v
```

### Test Categories

| Marker | Description | API Keys Required |
|--------|-------------|-------------------|
| (none) | Fast unit/integration tests | None |
| `contract` | Tests against real APIs | ANTHROPIC_API_KEY, OPENAI_API_KEY, SERPER_API_KEY |
| `vectorized` | Tests with real embeddings | OPENAI_API_KEY |
| `slow` | Long-running tests | Varies |

### Key Fixtures (`tests/conftest.py`)

- `temp_notes_root` - Creates temp directory with `.nb` folder
- `temp_config` - Config with 3 test notebooks (daily, projects, work)
- `mock_config` - Patches `get_config()` to return temp config
- `mock_cli_config` - Like mock_config but with vector indexing disabled (faster)
- `create_note` - Factory for creating test notes
- `indexed_note` - Factory that creates AND indexes a note
- `fixed_today` - Fixes `date.today()` to 2025-11-28 for deterministic tests
- `vectorized_config` - Config with vector indexing enabled (for contract tests)

### Skip Decorators

```python
from conftest import requires_anthropic_key, requires_openai_key, requires_serper_key

@pytest.mark.contract
@requires_anthropic_key
def test_real_llm_call():
    # Skipped if ANTHROPIC_API_KEY not set
    ...
```

### Golden File Tests

API response parsing is tested against real captured responses in `tests/fixtures/`:
- `anthropic_response.json` - Standard Claude response
- `anthropic_tool_response.json` - Tool-calling response
- `openai_response.json` - Standard GPT response
- `serper_web_response.json` - Web search results

## Inbox (Raindrop.io Integration)

The `nb inbox` command pulls bookmarks from Raindrop.io and clips them as notes.

### Multi-Collection Support

Configure multiple Raindrop collections, each mapping to a specific notebook:

```yaml
inbox:
  default_notebook: bookmarks
  auto_summarize: true
  raindrop:
    sync_tags: true        # Sync tag changes from Raindrop to notes
    sync_notes: true       # Sync note changes from Raindrop to notes
    collections:
      - name: nb-inbox
        notebook: bookmarks
      - name: research
        notebook: research
        auto_archive: false
      - name: work-reading
        notebook: work
        extra_tags: [work]
```

When running `nb inbox pull`, all configured collections are processed automatically.

### Syncing Changes

The `nb inbox sync` command checks previously-clipped items for changes in Raindrop:

- **Tag sync**: Updates note frontmatter tags (preserves user-added tags)
- **Note sync**: Updates the Raindrop note section in the note content

```bash
nb inbox sync              # Sync up to 50 items
nb inbox sync -l 100       # Sync up to 100 items
nb inbox sync --dry-run    # Preview changes without applying
```

### Key Commands

```bash
nb inbox list              # Show pending items from all collections
nb inbox pull              # Interactive: clip from all collections
nb inbox pull --auto       # Clip all without prompting
nb inbox pull -c research  # Only pull from 'research' collection
nb inbox sync              # Sync tag/note changes from Raindrop
nb inbox clear             # Archive all without clipping
nb inbox history           # Show clipping history
```

## Code Style

- Line length: 120 (configured in pyproject.toml)
- Python 3.13+ required
