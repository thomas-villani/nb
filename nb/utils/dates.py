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
