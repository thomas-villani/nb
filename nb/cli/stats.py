"""Statistics CLI commands and visualization helpers."""

from __future__ import annotations

from datetime import date, timedelta

import click
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table

from nb.cli.completion import complete_notebook
from nb.cli.utils import console
from nb.index.todos_repo import get_extended_todo_stats, get_tag_stats, get_todo_activity


def register_stats_commands(cli: click.Group) -> None:
    """Register all stats-related commands with the CLI."""
    cli.add_command(stats_cmd)


# Unicode block characters for sparklines (9 levels: empty to full)
SPARK_BLOCKS_UNICODE = " ▁▂▃▄▅▆▇█"
# ASCII fallback for terminals without Unicode support
SPARK_BLOCKS_ASCII = " _.,-~*#@"


def _can_use_unicode() -> bool:
    """Check if terminal can display Unicode sparkline characters."""
    import sys

    # Check if stdout encoding supports Unicode
    try:
        encoding = sys.stdout.encoding or "utf-8"
        "▁▂▃▄▅▆▇█".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def render_sparkline(values: list[int], width: int = 20) -> str:
    """Render a sparkline using block characters.

    Uses Unicode blocks if supported, ASCII fallback otherwise.

    Args:
        values: List of numeric values
        width: Target width (resamples if needed)

    Returns:
        String like "▁▂▄▆█▆▄▂▁" or "_.-~*#@" (ASCII fallback)
    """
    blocks = SPARK_BLOCKS_UNICODE if _can_use_unicode() else SPARK_BLOCKS_ASCII

    if not values:
        return blocks[0] * width

    # Resample to target width if needed
    if len(values) != width:
        values = _resample(values, width)

    max_val = max(values) if values else 1
    if max_val == 0:
        return blocks[1] * len(values)

    return "".join(
        blocks[min(8, max(1, int(v / max_val * 8)))] if v > 0 else blocks[0]
        for v in values
    )


def _resample(values: list[int], target_width: int) -> list[int]:
    """Resample values to target width using linear interpolation."""
    if not values:
        return [0] * target_width

    if len(values) == target_width:
        return values

    result = []
    ratio = len(values) / target_width

    for i in range(target_width):
        # Calculate which source values contribute to this bucket
        start = i * ratio
        end = (i + 1) * ratio

        # Sum values in this bucket
        total = 0
        for j in range(int(start), min(int(end) + 1, len(values))):
            total += values[j]

        result.append(total)

    return result


def render_bar(
    value: int, max_value: int, width: int = 20, char: str | None = None
) -> str:
    """Render a horizontal bar.

    Args:
        value: Current value
        max_value: Maximum value for scaling
        width: Bar width in characters
        char: Character to use for the bar (auto-selects based on Unicode support)

    Returns:
        String like "########----" or "████████░░░░" (if Unicode supported)
    """
    use_unicode = _can_use_unicode()

    if char is None:
        char = "█" if use_unicode else "#"
    empty_char = "░" if use_unicode else "-"

    if max_value == 0:
        return empty_char * width

    filled = int(value / max_value * width)
    return char * filled + empty_char * (width - filled)


def render_completion_bar(completed: int, total: int, width: int = 20) -> str:
    """Render a completion progress bar.

    Returns something like: ########---- 62% or ████████░░░░ 62% (if Unicode supported)
    """
    use_unicode = _can_use_unicode()
    fill_char = "█" if use_unicode else "#"
    empty_char = "░" if use_unicode else "-"

    if total == 0:
        return empty_char * width + "  0%"

    pct = completed / total
    filled = int(pct * width)
    bar = fill_char * filled + empty_char * (width - filled)
    return f"{bar} {pct * 100:3.0f}%"


@click.command("stats")
@click.option(
    "--notebook",
    "-n",
    "notebooks",
    multiple=True,
    help="Filter by notebook",
    shell_complete=complete_notebook,
)
@click.option(
    "--exclude",
    "-x",
    "exclude_notebooks",
    multiple=True,
    help="Exclude notebooks",
    shell_complete=complete_notebook,
)
@click.option("--days", "-d", default=30, help="Days for activity trends (default: 30)")
@click.option("--by-notebook", is_flag=True, help="Show breakdown by notebook")
@click.option("--by-priority", is_flag=True, help="Show breakdown by priority")
@click.option("--by-tag", is_flag=True, help="Show top tags by usage")
@click.option("--compact", "-c", is_flag=True, help="Compact single-panel view")
def stats_cmd(
    notebooks: tuple[str, ...],
    exclude_notebooks: tuple[str, ...],
    days: int,
    by_notebook: bool,
    by_priority: bool,
    by_tag: bool,
    compact: bool,
) -> None:
    """Show todo statistics dashboard.

    Displays completion metrics, activity trends, and breakdowns.

    \b
    Examples:
      nb stats                    Full dashboard
      nb stats --compact          Single panel summary
      nb stats --by-notebook      Breakdown by notebook
      nb stats --by-priority      Breakdown by priority
      nb stats -n work -n daily   Stats for specific notebooks
      nb stats --days 7           Week activity trends
    """
    # Get statistics
    stats = get_extended_todo_stats(
        notebooks=list(notebooks) if notebooks else None,
        exclude_notebooks=list(exclude_notebooks) if exclude_notebooks else None,
    )

    activity = get_todo_activity(
        days=days,
        notebooks=list(notebooks) if notebooks else None,
        exclude_notebooks=list(exclude_notebooks) if exclude_notebooks else None,
    )

    if compact:
        _render_compact_stats(stats, activity)
    else:
        _render_full_dashboard(stats, activity, by_notebook, by_priority, by_tag, days)


def _render_compact_stats(stats: dict, activity: dict) -> None:
    """Render compact single-panel stats view."""
    lines = []

    # Overview line
    total = stats["total"]
    completed = stats["completed"]
    rate = stats["completion_rate"]

    lines.append(
        f"[bold]Todos:[/bold] {total} total, {completed} completed ({rate:.0f}%)"
    )

    # Status breakdown
    status_parts = []
    if stats["in_progress"] > 0:
        status_parts.append(f"[yellow]{stats['in_progress']} in progress[/yellow]")
    if stats["pending"] > 0:
        status_parts.append(f"{stats['pending']} pending")
    if stats["overdue"] > 0:
        status_parts.append(f"[red]{stats['overdue']} overdue[/red]")
    if stats["due_today"] > 0:
        status_parts.append(f"[cyan]{stats['due_today']} due today[/cyan]")

    if status_parts:
        lines.append("  " + ", ".join(status_parts))

    # Activity sparklines
    created_values = _fill_daily_values(activity["created_by_day"], activity["days"])
    completed_values = _fill_daily_values(
        activity["completed_by_day"], activity["days"]
    )

    created_spark = render_sparkline(created_values, width=14)
    completed_spark = render_sparkline(completed_values, width=14)

    lines.append(f"\n[bold]Activity ({activity['days']}d):[/bold]")
    lines.append(f"  Created:   {created_spark} ({sum(created_values)})")
    lines.append(f"  Completed: {completed_spark} ({sum(completed_values)})")

    console.print(Panel("\n".join(lines), title="Todo Stats", border_style="blue"))


def _render_full_dashboard(
    stats: dict,
    activity: dict,
    show_notebook: bool,
    show_priority: bool,
    show_tag: bool,
    days: int,
) -> None:
    """Render full multi-panel dashboard."""
    panels = []
    breakdown_panels = []

    # Main overview panel
    overview = _build_overview_panel(stats, activity, days)
    panels.append(overview)

    # Determine which breakdowns to show
    # If no specific breakdown requested, show notebook and priority side-by-side
    show_default = not show_notebook and not show_priority and not show_tag

    if show_notebook or show_default:
        if stats["by_notebook"]:
            notebook_panel = _build_notebook_panel(stats["by_notebook"])
            breakdown_panels.append(notebook_panel)

    if show_priority or show_default:
        if stats["by_priority"]:
            priority_panel = _build_priority_panel(stats["by_priority"])
            breakdown_panels.append(priority_panel)

    if show_tag:
        tag_stats = get_tag_stats(include_sources=False)
        if tag_stats:
            tag_panel = _build_tag_panel(tag_stats[:10])  # Top 10 tags
            breakdown_panels.append(tag_panel)

    # Render panels
    console.print(panels[0])
    if breakdown_panels:
        if len(breakdown_panels) == 1:
            console.print(breakdown_panels[0])
        else:
            # Show breakdown panels side-by-side
            console.print(Columns(breakdown_panels, equal=True, expand=True))


def _build_overview_panel(stats: dict, activity: dict, days: int) -> Panel:
    """Build the main overview panel."""
    # Left side: Overview stats
    left_lines = []
    left_lines.append("[bold]Overview[/bold]")
    left_lines.append(f"  Total:       {stats['total']:>5}")
    left_lines.append(
        f"  Completed:   {stats['completed']:>5}  "
        f"[dim]({stats['completion_rate']:.0f}%)[/dim]"
    )
    if stats["in_progress"] > 0:
        left_lines.append(f"  In Progress: [yellow]{stats['in_progress']:>5}[/yellow]")
    left_lines.append(f"  Pending:     {stats['pending']:>5}")
    if stats["overdue"] > 0:
        left_lines.append(f"  Overdue:     [red]{stats['overdue']:>5}[/red]")
    if stats["due_today"] > 0:
        left_lines.append(f"  Due Today:   [cyan]{stats['due_today']:>5}[/cyan]")
    if stats["due_this_week"] > 0:
        left_lines.append(f"  Due Week:    {stats['due_this_week']:>5}")

    # Right side: Activity sparklines
    right_lines = []
    right_lines.append(f"[bold]Activity ({days}d)[/bold]")

    created_values = _fill_daily_values(activity["created_by_day"], days)
    completed_values = _fill_daily_values(activity["completed_by_day"], days)

    created_spark = render_sparkline(created_values, width=20)
    completed_spark = render_sparkline(completed_values, width=20)

    created_total = sum(created_values)
    completed_total = sum(completed_values)

    right_lines.append(f"  Created:   [green]{created_spark}[/green] {created_total}")
    right_lines.append(f"  Completed: [blue]{completed_spark}[/blue] {completed_total}")

    # Week summary
    week_created = (
        sum(created_values[-7:]) if len(created_values) >= 7 else sum(created_values)
    )
    week_completed = (
        sum(completed_values[-7:])
        if len(completed_values) >= 7
        else sum(completed_values)
    )

    right_lines.append("")
    right_lines.append("[bold]This Week[/bold]")
    right_lines.append(f"  +{week_created} created, +{week_completed} completed")

    # Combine into two columns
    left_text = "\n".join(left_lines)
    right_text = "\n".join(right_lines)

    table = Table.grid(expand=True, padding=(0, 4))
    table.add_column(ratio=1)
    table.add_column(ratio=1)
    table.add_row(left_text, right_text)

    return Panel(table, title="Todo Statistics", border_style="blue")


def _build_notebook_panel(by_notebook: dict[str, dict[str, int]]) -> Panel:
    """Build the notebook breakdown panel."""
    # Sort by total descending
    sorted_notebooks = sorted(by_notebook.items(), key=lambda x: -x[1]["total"])[:8]

    # Calculate max notebook name length for alignment
    max_name_len = (
        max(len(nb_name) for nb_name, _ in sorted_notebooks) if sorted_notebooks else 8
    )

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Notebook", width=max_name_len, no_wrap=True)
    table.add_column("Progress", justify="left", no_wrap=True)
    table.add_column("Count", justify="right")

    for nb_name, nb_stats in sorted_notebooks:
        total = nb_stats["total"]
        completed = nb_stats["completed"]
        rate = (completed / total * 100) if total > 0 else 0

        bar = render_bar(completed, total, width=12)
        rate_str = f"{rate:>4.0f}%"

        # Color overdue indicator
        if nb_stats.get("overdue", 0) > 0:
            nb_display = f"[red]{nb_name}[/red]"
        else:
            nb_display = nb_name

        table.add_row(nb_display, f"{bar}{rate_str}", str(total))

    return Panel(table, title="By Notebook", border_style="green")


def _build_priority_panel(by_priority: dict[int | None, dict[str, int]]) -> Panel:
    """Build the priority breakdown panel."""
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Priority", width=9, no_wrap=True)
    table.add_column("Progress", justify="left", no_wrap=True)
    table.add_column("Count", justify="right")

    priority_order = [1, 2, 3, None]
    priority_labels = {1: "!1 High", 2: "!2 Medium", 3: "!3 Low", None: "   None"}
    priority_colors = {1: "red", 2: "yellow", 3: "blue", None: "dim"}

    for p in priority_order:
        if p not in by_priority:
            continue

        p_stats = by_priority[p]
        total = p_stats["total"]
        completed = p_stats["completed"]
        rate = (completed / total * 100) if total > 0 else 0

        bar = render_bar(completed, total, width=12)
        label = priority_labels.get(p, str(p))
        color = priority_colors.get(p, "white")

        table.add_row(f"[{color}]{label}[/{color}]", f"{bar}{rate:>4.0f}%", str(total))

    return Panel(table, title="By Priority", border_style="yellow")


def _build_tag_panel(tag_stats: list[dict]) -> Panel:
    """Build the top tags panel."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Tag", style="cyan")
    table.add_column("Count", justify="right")

    max_count = tag_stats[0]["count"] if tag_stats else 1

    for tag_data in tag_stats:
        bar = render_bar(tag_data["count"], max_count, width=10)
        table.add_row(f"#{tag_data['tag']}", f"{bar} {tag_data['count']}")

    return Panel(table, title="Top Tags", border_style="magenta")


def _fill_daily_values(day_counts: list[tuple[str, int]], days: int) -> list[int]:
    """Fill in missing days with zeros for a complete daily series.

    Args:
        day_counts: List of (date_str, count) tuples
        days: Number of days to fill

    Returns:
        List of counts for each day, oldest first
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    # Create a map of date -> count
    count_map = dict(day_counts)

    # Fill in all days
    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        day_str = day.isoformat()
        result.append(count_map.get(day_str, 0))

    return result
