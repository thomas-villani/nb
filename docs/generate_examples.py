#!/usr/bin/env python3
"""Generate SVG examples of CLI output for documentation.

This script creates a temporary notebook with sample data, runs actual CLI commands,
and captures the Rich console output as SVG files.

Usage:
    python docs/generate_examples.py

Output:
    docs/source/_static/examples/*.svg
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from rich.console import Console

# Output directory for SVG files
DOCS_DIR = Path(__file__).parent
OUTPUT_DIR = DOCS_DIR / "source" / "_static" / "examples"


def create_sample_notebook(root: Path) -> None:
    """Create a sample notebook structure with realistic data."""
    # Create .nb directory and config
    nb_dir = root / ".nb"
    nb_dir.mkdir(parents=True)

    config_content = """\
notes_root: {root}
editor: vim

notebooks:
  - name: daily
    date_based: true
    icon: "\U0001F4C5"
    color: blue
  - name: projects
    date_based: false
    icon: "\U0001F527"
    color: cyan
  - name: work
    date_based: true
    color: yellow
"""
    (nb_dir / "config.yaml").write_text(
        config_content.format(root=root.as_posix()), encoding="utf-8"
    )

    # Create daily notebook with date structure
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_folder = f"{week_start.strftime('%b%d')}-{week_end.strftime('%b%d')}"

    daily_dir = root / "daily" / str(today.year) / week_folder
    daily_dir.mkdir(parents=True)

    # Today's note
    today_note = daily_dir / f"{today.isoformat()}.md"
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    tomorrow = today + timedelta(days=1)
    today_note.write_text(
        f"""\
---
date: {today.isoformat()}
tags: [daily]
---

# {today.strftime('%A, %B %d')}

## Morning standup

Discussed sprint progress with the team.

## Tasks

- [^] Review pull request for auth module @priority(1) #code-review
- [ ] Update API documentation @due({friday.isoformat()}) @priority(2) #docs
- [ ] Schedule 1:1 with manager @due({tomorrow.isoformat()}) #meetings
- [x] Send weekly status report #communication

## Notes

Meeting notes from standup:
- Backend API is 80% complete
- Frontend needs design review
""",
        encoding="utf-8",
    )

    # Yesterday's note
    yesterday = today - timedelta(days=1)
    yesterday_note = daily_dir / f"{yesterday.isoformat()}.md"
    yesterday_note.write_text(
        f"""\
---
date: {yesterday.isoformat()}
tags: [daily]
---

# {yesterday.strftime('%A, %B %d')}

## Completed

- [x] Fix login bug #bugfix
- [x] Deploy to staging #devops

## Carried over

- [ ] Write unit tests for user service @due({today.isoformat()}) @priority(2) #testing
""",
        encoding="utf-8",
    )

    # Create projects notebook
    projects_dir = root / "projects"
    projects_dir.mkdir()

    next_week = today + timedelta(days=7)
    (projects_dir / "website-redesign.md").write_text(
        f"""\
---
title: Website Redesign
tags: [project, design]
---

# Website Redesign

## Goals

- Modern, responsive design
- Improved performance
- Better accessibility

## Tasks

- [ ] Create wireframes @priority(1) #design
- [ ] Review competitor sites @due({next_week.isoformat()}) #research
- [ ] Set up new hosting @priority(3) #devops
- [x] Gather stakeholder requirements #planning
""",
        encoding="utf-8",
    )

    (projects_dir / "api-v2.md").write_text(
        f"""\
---
title: API v2 Development
tags: [project, backend]
---

# API v2 Development

## Overview

Building the next generation API with improved performance.

## Tasks

- [ ] Design new endpoint structure @priority(1) #architecture
- [ ] Implement rate limiting @due({friday.isoformat()}) @priority(2) #backend
- [ ] Write migration guide @priority(3) #docs
""",
        encoding="utf-8",
    )

    # Create work notebook
    work_dir = root / "work" / str(today.year) / week_folder
    work_dir.mkdir(parents=True)

    work_note = work_dir / f"{today.isoformat()}.md"
    work_note.write_text(
        f"""\
---
date: {today.isoformat()}
tags: [work]
---

# Work Log - {today.strftime('%B %d')}

## In Progress

- [^] Refactor authentication module @priority(1) #backend
- [ ] Code review for PR #142 @due({today.isoformat()}) #code-review

## Blocked

- [ ] Deploy to production (waiting on QA) @priority(1) #devops #blocked
""",
        encoding="utf-8",
    )

    # Create todo inbox
    (root / "todo.md").write_text(
        """\
# Inbox

- [ ] Read article on Rust async @priority(3) #learning
- [ ] Update resume #personal
- [ ] Try new coffee shop #life
""",
        encoding="utf-8",
    )


def setup_environment(root: Path) -> None:
    """Set up the environment for running commands against the temp notebook."""
    os.environ["NB_NOTES_ROOT"] = str(root)

    # Clear any cached config
    from nb import config as config_module

    config_module._config = None

    # Force re-index
    from nb.index.scanner import index_all_notes

    index_all_notes(force=True)


def capture_with_function(
    root: Path,
    render_func: Callable[[Console], None],
    title: str,
    width: int = 100,
) -> Console:
    """Capture output from a custom render function.

    Args:
        root: Notes root directory
        render_func: Function that takes console and renders output
        title: Title for the SVG
        width: Console width

    Returns:
        The recording console with captured output
    """
    console = Console(
        record=True,
        force_terminal=True,
        width=width,
        color_system="truecolor",
    )
    render_func(console)
    return console


def render_todo_list(console: Console) -> None:
    """Render todo list by calling the actual CLI display function."""
    from nb.cli import utils as cli_utils
    from nb.cli.todos import _list_todos

    # Temporarily replace the console
    original = cli_utils.console
    cli_utils.console = console

    # Also patch in todos module
    from nb.cli import todos

    todos_original = todos.console
    todos.console = console

    try:
        _list_todos(focus=True)
    finally:
        cli_utils.console = original
        todos.console = todos_original


def render_stats(console: Console) -> None:
    """Render stats by calling the actual CLI display function."""
    from nb.cli import utils as cli_utils

    original = cli_utils.console
    cli_utils.console = console

    from nb.cli import stats as stats_module

    stats_original = stats_module.console
    stats_module.console = console

    try:
        # Call the actual stats rendering
        from nb.cli.stats import _render_full_dashboard
        from nb.index.todos_repo import get_extended_todo_stats, get_todo_activity

        stats = get_extended_todo_stats(notebooks=None, exclude_notebooks=None)
        activity = get_todo_activity(days=30, notebooks=None, exclude_notebooks=None)

        _render_full_dashboard(
            stats=stats,
            activity=activity,
            show_notebook=True,
            show_priority=False,
            show_tag=False,
            days=30,
        )
    finally:
        cli_utils.console = original
        stats_module.console = stats_original


def render_notebooks(console: Console) -> None:
    """Render notebooks list."""
    from nb.cli import utils as cli_utils

    original = cli_utils.console
    cli_utils.console = console

    from nb.cli import notebooks as notebooks_module

    nb_original = notebooks_module.console
    notebooks_module.console = console

    try:
        from nb.config import get_config

        config = get_config()

        console.print("[bold]Notebooks[/bold]\n")

        for nb in config.notebooks:
            color = nb.color or "magenta"
            icon = nb.icon or ""
            icon_str = f"{icon} " if icon else ""

            # Count notes
            nb_path = Path(config.notes_root) / nb.name
            if nb_path.exists():
                note_count = len(list(nb_path.rglob("*.md")))
            else:
                note_count = 0

            console.print(
                f"  [{color}]{icon_str}{nb.name}[/{color}] [dim]({note_count} notes)[/dim]"
            )
    finally:
        cli_utils.console = original
        notebooks_module.console = nb_original


def render_search_results(console: Console) -> None:
    """Render actual search results."""
    from nb.cli import utils as cli_utils

    original = cli_utils.console
    cli_utils.console = console

    try:
        from nb.index.search import get_search

        search = get_search()
        results = search.search("API", search_type="keyword", k=5)

        console.print('[bold]Search results for:[/bold] [cyan]"API"[/cyan]\n')

        if not results:
            console.print("[dim]No results found.[/dim]")
            return

        for result in results[:3]:
            title = result.title or Path(result.path).stem
            tags_str = " ".join(f"[cyan]#{t}[/cyan]" for t in (result.tags or [])[:3])
            rel_path = Path(result.path).name

            console.print(f"  [bold]{title}[/bold]")
            console.print(f"  [dim]{rel_path}[/dim]  {tags_str}")
            console.print()

    finally:
        cli_utils.console = original


def render_kanban(console: Console) -> None:
    """Render kanban board by calling the actual CLI display function."""
    from nb.cli import todos as todos_module
    from nb.cli import utils as cli_utils

    original = cli_utils.console
    cli_utils.console = console

    todos_original = todos_module.console
    todos_module.console = console

    try:
        from nb.cli.todos import _display_kanban

        _display_kanban(
            notebooks=None,
            exclude_notebooks=None,
            board_name="default",
        )
    finally:
        cli_utils.console = original
        todos_module.console = todos_original


def render_tags(console: Console) -> None:
    """Render tags list."""
    from nb.cli import utils as cli_utils

    original = cli_utils.console
    cli_utils.console = console

    try:
        from nb.index.todos_repo import get_tag_stats

        tag_stats = get_tag_stats(include_sources=False)

        console.print("[bold]Tags[/bold]\n")

        if not tag_stats:
            console.print("[dim]No tags found.[/dim]")
            return

        for stat in tag_stats[:10]:
            tag = stat["tag"]
            count = stat["count"]
            bar_width = min(count * 2, 20)
            bar = "█" * bar_width

            console.print(f"  [cyan]#{tag:<15}[/cyan] [dim]{bar}[/dim] {count}")

    finally:
        cli_utils.console = original


def render_note_list(console: Console) -> None:
    """Render note list with details."""
    from nb.cli import utils as cli_utils
    from nb.config import get_config
    from nb.core.notes import list_notes

    original = cli_utils.console
    cli_utils.console = console

    try:
        config = get_config()
        note_paths = list_notes()[:8]

        console.print("[bold]Recent Notes[/bold]\n")

        if not note_paths:
            console.print("[dim]No notes found.[/dim]")
            return

        for note_path in note_paths:
            # Determine notebook from path
            parts = note_path.parts
            notebook = parts[0] if parts else "inbox"
            title = note_path.stem

            # Get notebook color
            color, icon = cli_utils.get_notebook_display_info(notebook)
            icon_str = f"{icon} " if icon else ""

            console.print(f"  [{color}]{icon_str}{notebook}[/{color}] [bold]{title}[/bold]")

    finally:
        cli_utils.console = original


def cleanup_db_connections() -> None:
    """Close all database connections to allow temp dir cleanup on Windows."""
    try:
        from nb.index import db as db_module

        if hasattr(db_module, "_db") and db_module._db is not None:
            db_module._db.close()
            db_module._db = None
    except Exception:
        pass

    try:
        import gc

        gc.collect()
    except Exception:
        pass


def generate_all_examples() -> None:
    """Generate all SVG examples."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create temp directory manually for better cleanup control
    tmp = tempfile.mkdtemp()
    root = Path(tmp)

    try:
        print("Creating sample notebook...")
        create_sample_notebook(root)

        print("Setting up environment...")
        setup_environment(root)

        # Define examples to generate
        # Each tuple: (filename, title, render_function, width)
        examples: list[tuple[str, str, Callable[[Console], None], int]] = [
            ("todo-list", "nb todo -f", render_todo_list, 100),
            ("stats", "nb stats", render_stats, 80),
            ("notebooks", "nb notebooks", render_notebooks, 80),
            ("search", "nb search", render_search_results, 80),
            ("kanban", "nb todo -k", render_kanban, 120),
            ("tags", "nb tags", render_tags, 60),
            ("note-list", "nb list", render_note_list, 80),
        ]

        for filename, title, render_func, width in examples:
            print(f"Generating {filename}.svg...")
            try:
                console = capture_with_function(root, render_func, title, width)
                output_path = OUTPUT_DIR / f"{filename}.svg"
                console.save_svg(str(output_path), title=title)
                print(f"  ✓ Saved to {output_path}")
            except Exception as e:
                print(f"  ✗ Error: {e}")
                import traceback

                traceback.print_exc()

        print("\nDone!")

    finally:
        # Clean up database connections before removing temp dir
        cleanup_db_connections()

        # Clear cached config
        try:
            from nb import config as config_module

            config_module._config = None
        except Exception:
            pass

        # Try to remove temp directory, ignore errors on Windows
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            print(f"  [Note: Could not fully clean up {tmp}]")


if __name__ == "__main__":
    generate_all_examples()
