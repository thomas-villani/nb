"""Date parsing and formatting utilities."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Callable

from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta, MO, TU, WE, TH, FR, SA, SU

# Weekday name to dateutil weekday constant
WEEKDAYS: dict[str, int] = {
    "monday": MO,
    "tuesday": TU,
    "wednesday": WE,
    "thursday": TH,
    "friday": FR,
    "saturday": SA,
    "sunday": SU,
    "mon": MO,
    "tue": TU,
    "wed": WE,
    "thu": TH,
    "fri": FR,
    "sat": SA,
    "sun": SU,
}

# Named date shortcuts
NAMED_DATES: dict[str, Callable[[], date]] = {
    "today": lambda: date.today(),
    "yesterday": lambda: date.today() - timedelta(days=1),
    "tomorrow": lambda: date.today() + timedelta(days=1),
}


def parse_fuzzy_date(text: str) -> date | None:
    """Parse a fuzzy date expression into a date object.

    Supports:
    - Named dates: "today", "yesterday", "tomorrow"
    - Weekday names: "friday", "next friday", "last monday"
    - Relative: "next week", "last week"
    - Natural language: "nov 20", "november 20 2025"
    - ISO format: "2025-11-20"

    Returns None if parsing fails.
    """
    if not text:
        return None

    text = text.strip().lower()

    # Check named dates first
    if text in NAMED_DATES:
        return NAMED_DATES[text]()

    # Handle "next week" / "last week"
    if text == "next week":
        return date.today() + timedelta(weeks=1)
    if text == "last week":
        return date.today() - timedelta(weeks=1)

    # Handle weekday names (with optional "next" or "last" prefix)
    next_match = re.match(r"^next\s+(\w+)$", text)
    last_match = re.match(r"^last\s+(\w+)$", text)

    if next_match:
        weekday_name = next_match.group(1)
        if weekday_name in WEEKDAYS:
            # Next occurrence of this weekday (at least 1 day from now)
            weekday = WEEKDAYS[weekday_name]
            return date.today() + relativedelta(weekday=weekday(+1))

    if last_match:
        weekday_name = last_match.group(1)
        if weekday_name in WEEKDAYS:
            # Previous occurrence of this weekday
            weekday = WEEKDAYS[weekday_name]
            return date.today() + relativedelta(weekday=weekday(-1))

    # Plain weekday name - means next occurrence
    if text in WEEKDAYS:
        weekday = WEEKDAYS[text]
        target = date.today() + relativedelta(weekday=weekday(+1))
        # If today is that weekday, return today
        if target == date.today():
            return target
        # Otherwise return next occurrence
        return target

    # Try dateutil parser for everything else
    try:
        parsed = dateutil_parser.parse(text, fuzzy=True, dayfirst=False)
        return parsed.date()
    except (ValueError, TypeError):
        pass

    return None


def parse_date_from_filename(filename: str) -> date | None:
    """Extract date from YYYY-MM-DD pattern in filename.

    Example: "2025-11-26.md" -> date(2025, 11, 26)
    """
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


def format_date(dt: date, fmt: str | None = None) -> str:
    """Format a date using the given format string.

    Defaults to ISO format (YYYY-MM-DD) if no format specified.
    """
    if fmt is None:
        fmt = "%Y-%m-%d"
    return dt.strftime(fmt)


def get_relative_date_label(dt: date) -> str:
    """Get a human-readable label for a date relative to today.

    Returns "today", "yesterday", "tomorrow", or formatted date.
    """
    today = date.today()

    if dt == today:
        return "today"
    elif dt == today - timedelta(days=1):
        return "yesterday"
    elif dt == today + timedelta(days=1):
        return "tomorrow"
    else:
        # For dates within this week, show weekday name
        days_diff = (dt - today).days
        if -7 < days_diff < 7:
            return dt.strftime("%A")  # Full weekday name
        # Otherwise show formatted date
        return format_date(dt)


def is_date_in_range(dt: date, start: date | None, end: date | None) -> bool:
    """Check if a date falls within a range (inclusive)."""
    if start is not None and dt < start:
        return False
    if end is not None and dt > end:
        return False
    return True


def get_week_range(dt: date | None = None) -> tuple[date, date]:
    """Get the start (Monday) and end (Sunday) of the week containing dt."""
    if dt is None:
        dt = date.today()
    start = dt - timedelta(days=dt.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start, end


def get_week_folder_name(dt: date | None = None) -> str:
    """Get the week folder name for a date (e.g., 'Nov25-Dec01').

    Uses Monday-Sunday week boundaries.
    """
    if dt is None:
        dt = date.today()
    start, end = get_week_range(dt)
    # Format: Nov25-Dec01
    return f"{start.strftime('%b%d')}-{end.strftime('%b%d')}"


def parse_week_folder_name(folder_name: str, year: int) -> tuple[date, date] | None:
    """Parse a week folder name back to start and end dates.

    Args:
        folder_name: e.g., 'Nov25-Dec01'
        year: The year (from parent folder)

    Returns:
        Tuple of (start_date, end_date) or None if parsing fails.
    """
    match = re.match(r"^([A-Za-z]{3})(\d{1,2})-([A-Za-z]{3})(\d{1,2})$", folder_name)
    if not match:
        return None

    start_month_str, start_day_str, end_month_str, end_day_str = match.groups()

    try:
        # Parse start date
        start_date = dateutil_parser.parse(
            f"{start_month_str} {start_day_str} {year}"
        ).date()

        # Parse end date - might be in next year if week crosses year boundary
        end_date = dateutil_parser.parse(f"{end_month_str} {end_day_str} {year}").date()

        # If end is before start, it crosses year boundary
        if end_date < start_date:
            end_date = dateutil_parser.parse(
                f"{end_month_str} {end_day_str} {year + 1}"
            ).date()

        return start_date, end_date
    except (ValueError, TypeError):
        return None


def get_weeks_ago(n: int) -> tuple[date, date]:
    """Get the date range for N weeks ago.

    Args:
        n: Number of weeks ago (0 = this week, 1 = last week, etc.)

    Returns:
        Tuple of (start_date, end_date) for that week.
    """
    today = date.today()
    target = today - timedelta(weeks=n)
    return get_week_range(target)


def get_month_range(dt: date | None = None) -> tuple[date, date]:
    """Get the first and last day of the month containing dt."""
    if dt is None:
        dt = date.today()
    start = dt.replace(day=1)
    # Last day of month: go to next month, subtract a day
    if dt.month == 12:
        end = dt.replace(year=dt.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
    return start, end


def parse_date_range(text: str) -> tuple[date | None, date | None]:
    """Parse a fuzzy date range expression into start and end dates.

    Supports:
    - "today", "yesterday", "this week", "this month"
    - "last N days/weeks/months" (e.g., "last 3 months")
    - "past N days/weeks/months" (alias for "last N")
    - "since <date>" for open-ended ranges
    - "<date> to <date>" for explicit ranges

    Returns (start_date, end_date) tuple. Either can be None for open ranges.
    """
    if not text:
        return None, None

    text = text.strip().lower()
    today = date.today()

    # Handle "today"
    if text == "today":
        return today, today

    # Handle "yesterday"
    if text == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday

    # Handle "this week"
    if text == "this week":
        return get_week_range(today)

    # Handle "this month"
    if text == "this month":
        return get_month_range(today)

    # Handle "last week"
    if text == "last week":
        last_week = today - timedelta(weeks=1)
        return get_week_range(last_week)

    # Handle "last month"
    if text == "last month":
        last_month = today - relativedelta(months=1)
        return get_month_range(last_month)

    # Handle "last N days/weeks/months" or "past N days/weeks/months"
    last_n_match = re.match(
        r"^(?:last|past)\s+(\d+)\s+(day|days|week|weeks|month|months)$", text
    )
    if last_n_match:
        n = int(last_n_match.group(1))
        unit = last_n_match.group(2).rstrip("s")  # Normalize to singular

        if unit == "day":
            start = today - timedelta(days=n)
        elif unit == "week":
            start = today - timedelta(weeks=n)
        elif unit == "month":
            start = today - relativedelta(months=n)
        else:
            return None, None

        return start, today

    # Handle "since <date>"
    since_match = re.match(r"^since\s+(.+)$", text)
    if since_match:
        start = parse_fuzzy_date(since_match.group(1))
        if start:
            return start, today

    # Handle "<date> to <date>"
    range_match = re.match(r"^(.+?)\s+to\s+(.+)$", text)
    if range_match:
        start = parse_fuzzy_date(range_match.group(1))
        end = parse_fuzzy_date(range_match.group(2))
        if start and end:
            return start, end

    # Try parsing as a single date (search that specific day)
    single_date = parse_fuzzy_date(text)
    if single_date:
        return single_date, single_date

    return None, None
