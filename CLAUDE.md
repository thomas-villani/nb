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

## Testing

Tests use temporary directories via pytest fixtures in `tests/conftest.py`:
- `temp_notes_root` - Creates temp directory with `.nb` folder
- `temp_config` - Config with 3 test notebooks (daily, projects, work)
- `mock_config` - Patches `get_config()` to return temp config
- `create_note` - Factory for creating test notes
- `fixed_today` - Fixes `date.today()` to 2025-11-28 for deterministic tests

## Code Style

- Line length: 120 (configured in pyproject.toml)
- Python 3.13+ required
