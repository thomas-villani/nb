#!/usr/bin/env python3
"""Generate SVG examples of CLI output for documentation.

This script creates a temporary notebook with sample data, runs key commands,
and captures the Rich console output as SVG files.

Usage:
    python docs/generate_examples.py

Output:
    docs/source/_static/examples/*.svg
"""

from __future__ import annotations

import tempfile
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
- [ ] Update API documentation @due(friday) @priority(2) #docs
- [ ] Schedule 1:1 with manager @due(tomorrow) #meetings
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

    (projects_dir / "website-redesign.md").write_text(
        """\
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
- [ ] Review competitor sites @due(next week) #research
- [ ] Set up new hosting @priority(3) #devops
- [x] Gather stakeholder requirements #planning
""",
        encoding="utf-8",
    )

    (projects_dir / "api-v2.md").write_text(
        """\
---
title: API v2 Development
tags: [project, backend]
---

# API v2 Development

## Overview

Building the next generation API with improved performance.

## Tasks

- [ ] Design new endpoint structure @priority(1) #architecture
- [ ] Implement rate limiting @due(friday) @priority(2) #backend
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
- [ ] Code review for PR #142 @due(today) #code-review

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


def capture_command_output(
    root: Path,
    title: str,
    render_func: callable,
    width: int = 100,
) -> Console:
    """Capture command output to a recording console.

    Args:
        root: Notes root directory
        title: Title for the SVG
        render_func: Function that takes (console, root) and renders output
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
    render_func(console, root)
    return console


def render_todo_list(console: Console, root: Path) -> None:
    """Render the todo list output."""
    # We need to import and configure nb to use our temp root
    import os

    os.environ["NB_NOTES_ROOT"] = str(root)

    # Clear any cached config
    from nb import config as config_module

    config_module._config = None

    # Force re-index
    from nb.index.scanner import index_all_notes

    index_all_notes(force=True)

    # Now get todos and render them
    from datetime import date, timedelta

    from nb.cli.utils import get_notebook_display_info
    from nb.index.todos_repo import get_sorted_todos

    todos = get_sorted_todos(completed=False)

    if not todos:
        console.print("[dim]No todos found.[/dim]")
        return

    today_date = date.today()
    week_start = today_date - timedelta(days=today_date.weekday())
    week_end = week_start + timedelta(days=6)
    next_week_end = week_end + timedelta(days=7)

    # Group todos
    groups: dict[str, list] = {
        "OVERDUE": [],
        "IN PROGRESS": [],
        "DUE TODAY": [],
        "DUE THIS WEEK": [],
        "DUE NEXT WEEK": [],
        "DUE LATER": [],
        "NO DUE DATE": [],
    }

    for t in todos:
        if t.in_progress:
            groups["IN PROGRESS"].append(t)
        elif t.due_date is None:
            groups["NO DUE DATE"].append(t)
        elif t.due_date < today_date:
            groups["OVERDUE"].append(t)
        elif t.due_date == today_date:
            groups["DUE TODAY"].append(t)
        elif t.due_date <= week_end:
            groups["DUE THIS WEEK"].append(t)
        elif t.due_date <= next_week_end:
            groups["DUE NEXT WEEK"].append(t)
        else:
            groups["DUE LATER"].append(t)

    # Render output
    for group_name, group_todos in groups.items():
        if not group_todos:
            continue

        console.print(f"\n[bold yellow]{group_name}[/bold yellow]")

        for t in group_todos:
            # Format todo line
            checkbox = "[bold green]\u2713[/bold green]" if t.completed else "[dim]\u2610[/dim]"
            if t.in_progress:
                checkbox = "[bold cyan]\u25b6[/bold cyan]"

            content = t.content[:50] + "..." if len(t.content) > 50 else t.content

            # Get notebook color - t.notebook is the notebook name
            notebook = t.notebook or "inbox"
            color, icon = get_notebook_display_info(notebook)
            icon_str = f"{icon} " if icon else ""

            source_str = f"[{color}]{icon_str}{notebook}[/{color}]"

            # Priority
            priority_str = ""
            if t.priority:
                prio_colors = {1: "red", 2: "yellow", 3: "blue"}
                priority_str = f"[{prio_colors.get(t.priority.value, 'white')}]!{t.priority.value}[/]"

            # Due date
            due_str = ""
            if t.due_date:
                if t.due_date < today_date:
                    due_str = f"[red]{t.due_date.strftime('%b %d')}[/red]"
                elif t.due_date == today_date:
                    due_str = f"[yellow]{t.due_date.strftime('%b %d')}[/yellow]"
                else:
                    due_str = f"[dim]{t.due_date.strftime('%b %d')}[/dim]"

            # Tags
            tags_str = " ".join(f"[cyan]#{tag}[/cyan]" for tag in t.tags[:2])

            # Build the line
            line_parts = [f"  {checkbox} {content}"]
            if tags_str:
                line_parts.append(tags_str)
            line_parts.append(source_str)
            if due_str:
                line_parts.append(due_str)
            if priority_str:
                line_parts.append(priority_str)
            line_parts.append(f"[dim]{t.id[:6]}[/dim]")

            console.print("  ".join(line_parts))


def render_note_list(console: Console, root: Path) -> None:
    """Render the note list output."""
    import os

    os.environ["NB_NOTES_ROOT"] = str(root)

    from nb import config as config_module

    config_module._config = None

    from nb.config import get_config

    config = get_config()

    console.print("[bold]Notebooks[/bold]\n")

    for nb in config.notebooks:
        color = nb.color or "magenta"
        icon = nb.icon or ""
        icon_str = f"{icon} " if icon else ""

        # Count notes
        nb_path = root / nb.name
        if nb_path.exists():
            note_count = len(list(nb_path.rglob("*.md")))
        else:
            note_count = 0

        console.print(f"  [{color}]{icon_str}{nb.name}[/{color}] [dim]({note_count} notes)[/dim]")

        # Show recent notes
        if nb_path.exists():
            notes = sorted(nb_path.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:2]
            for note in notes:
                rel_path = note.relative_to(nb_path)
                console.print(f"    [dim]\u2514\u2500[/dim] {rel_path.stem}")


def render_stats(console: Console, root: Path) -> None:
    """Render the stats dashboard output."""
    import os

    os.environ["NB_NOTES_ROOT"] = str(root)

    from nb import config as config_module

    config_module._config = None

    from nb.index.scanner import index_all_notes

    index_all_notes(force=True)

    from nb.index.todos_repo import query_todos

    all_todos = query_todos(completed=None)
    open_todos = [t for t in all_todos if not t.completed]
    completed_todos = [t for t in all_todos if t.completed]
    in_progress = [t for t in open_todos if t.in_progress]

    today = date.today()
    overdue = [t for t in open_todos if t.due_date and t.due_date < today]
    due_today = [t for t in open_todos if t.due_date == today]

    total = len(all_todos)
    completed_count = len(completed_todos)
    completion_rate = (completed_count / total * 100) if total > 0 else 0

    from rich.panel import Panel
    from rich.table import Table

    # Overview panel
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Total", f"[bold]{total}[/bold]")
    table.add_row("Completed", f"[green]{completed_count}[/green] ({completion_rate:.0f}%)")
    table.add_row("In Progress", f"[cyan]{len(in_progress)}[/cyan]")
    table.add_row("Pending", f"[white]{len(open_todos) - len(in_progress)}[/white]")
    table.add_row("Overdue", f"[red]{len(overdue)}[/red]")
    table.add_row("Due Today", f"[yellow]{len(due_today)}[/yellow]")

    console.print(Panel(table, title="[bold]Todo Statistics[/bold]", border_style="blue"))


def render_search_results(console: Console, root: Path) -> None:
    """Render search results output."""
    console.print("[bold]Search results for:[/bold] [cyan]\"API\"[/cyan]\n")

    results = [
        ("projects/api-v2.md", "API v2 Development", ["project", "backend"]),
        ("daily/2024-01-15.md", "Update API documentation", ["daily"]),
        ("work/2024-01-15.md", "Code review for PR #142", ["work"]),
    ]

    for path, title, tags in results:
        tags_str = " ".join(f"[cyan]#{t}[/cyan]" for t in tags)
        console.print(f"  [bold]{title}[/bold]")
        console.print(f"  [dim]{path}[/dim]  {tags_str}")
        console.print()


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

        # Force garbage collection to close any open handles
        import gc

        gc.collect()
    except Exception:
        pass


def generate_all_examples() -> None:
    """Generate all SVG examples."""
    import shutil

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create temp directory manually for better cleanup control
    tmp = tempfile.mkdtemp()
    root = Path(tmp)

    try:
        create_sample_notebook(root)

        examples = [
            ("todo-list", "nb todo", render_todo_list, 100),
            ("notebooks", "nb notebooks", render_note_list, 80),
            ("stats", "nb stats", render_stats, 60),
            ("search", "nb search", render_search_results, 80),
        ]

        for filename, title, render_func, width in examples:
            print(f"Generating {filename}.svg...")
            try:
                console = capture_command_output(root, title, render_func, width)
                output_path = OUTPUT_DIR / f"{filename}.svg"
                console.save_svg(str(output_path), title=title)
                print(f"  \u2713 Saved to {output_path}")
            except Exception as e:
                print(f"  \u2717 Error: {e}")
                import traceback

                traceback.print_exc()

    finally:
        # Clean up database connections before removing temp dir
        cleanup_db_connections()

        # Try to remove temp directory, ignore errors on Windows
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            print(f"  [Note: Could not fully clean up {tmp}]")


if __name__ == "__main__":
    generate_all_examples()
