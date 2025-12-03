"""Date parsing and formatting utilities."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta

from dateutil import parser as dateutil_parser
from dateutil.relativedelta import FR, MO, SA, SU, TH, TU, WE, relativedelta, weekday

# Weekday name to dateutil weekday constant
WEEKDAYS: dict[str, weekday] = {
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

    # Plain weekday name - means most recent occurrence (past or today)
    if text in WEEKDAYS:
        weekday = WEEKDAYS[text]
        # Check if today is that weekday
        today = date.today()
        today_weekday = today.weekday()  # Monday=0, Sunday=6
        target_weekday = weekday.weekday  # MO=0, TU=1, ..., SU=6

        if today_weekday == target_weekday:
            # Today is that weekday
            return today
        else:
            # Return the most recent past occurrence
            return today + relativedelta(weekday=weekday(-1))

    # Try dateutil parser for everything else
    try:
        parsed = dateutil_parser.parse(text, fuzzy=True, dayfirst=False)
        return parsed.date()
    except (ValueError, TypeError):
        pass

    return None


# Keywords that indicate clearing/removing a due date
CLEAR_DATE_KEYWORDS = {"none", "clear", "remove"}


def parse_fuzzy_date_future(text: str) -> date | None:
    """Parse a fuzzy date expression with weekday names defaulting to NEXT occurrence.

    Unlike parse_fuzzy_date(), bare weekday names like "friday" return
    the NEXT Friday (future), not the most recent. This is more intuitive
    for setting due dates.

    Returns None if parsing fails or if text is a clear keyword ("none", "clear", "remove").
    Use is_clear_date_keyword() to check if the user wants to clear a due date.

    Supports the same formats as parse_fuzzy_date():
    - Named dates: "today", "yesterday", "tomorrow"
    - Weekday names: "friday" (next occurrence), "next friday", "last monday"
    - Relative: "next week", "last week"
    - Natural language: "nov 20", "november 20 2025"
    - ISO format: "2025-11-20"
    """
    if not text:
        return None

    text = text.strip().lower()

    # Check if user wants to clear the due date
    if text in CLEAR_DATE_KEYWORDS:
        return None

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
            weekday = WEEKDAYS[weekday_name]
            return date.today() + relativedelta(weekday=weekday(+1))

    if last_match:
        weekday_name = last_match.group(1)
        if weekday_name in WEEKDAYS:
            weekday = WEEKDAYS[weekday_name]
            return date.today() + relativedelta(weekday=weekday(-1))

    # Plain weekday name - means NEXT occurrence (future-oriented for due dates)
    if text in WEEKDAYS:
        weekday = WEEKDAYS[text]
        today = date.today()
        today_weekday = today.weekday()
        target_weekday = weekday.weekday

        if today_weekday == target_weekday:
            # Today is that weekday - return today (it's still the "next" occurrence)
            return today
        else:
            # Return the next future occurrence
            return today + relativedelta(weekday=weekday(+1))

    # Try dateutil parser for everything else
    try:
        parsed = dateutil_parser.parse(text, fuzzy=True, dayfirst=False)
        return parsed.date()
    except (ValueError, TypeError):
        pass

    return None


def is_clear_date_keyword(text: str) -> bool:
    """Check if the text is a keyword that means 'clear/remove the due date'."""
    return text.strip().lower() in CLEAR_DATE_KEYWORDS


# Keywords that are relative dates (should be auto-replaced with actual dates)
RELATIVE_DATE_KEYWORDS = {
    "today",
    "yesterday",
    "tomorrow",
    "next week",
    "last week",
}


def is_relative_date(text: str) -> bool:
    """Check if the text is a relative date that should be auto-replaced.

    Returns True for:
    - Named dates: "today", "yesterday", "tomorrow"
    - Relative: "next week", "last week"
    - Weekday names: "friday", "next friday", "last monday"
    - Any of the above with an optional time suffix
    """
    if not text:
        return False

    text = text.strip().lower()

    # Check for time suffix and strip it
    # Patterns like "today 14:30", "tomorrow 2pm", "friday 9am"
    time_pattern = re.compile(r"\s+\d{1,2}(:\d{2})?\s*(am|pm)?$", re.IGNORECASE)
    text_without_time = time_pattern.sub("", text).strip()

    # Check named dates
    if text_without_time in RELATIVE_DATE_KEYWORDS:
        return True

    # Check weekday patterns
    if text_without_time in WEEKDAYS:
        return True

    # Check "next <weekday>" or "last <weekday>"
    next_match = re.match(r"^next\s+(\w+)$", text_without_time)
    if next_match and next_match.group(1) in WEEKDAYS:
        return True

    last_match = re.match(r"^last\s+(\w+)$", text_without_time)
    if last_match and last_match.group(1) in WEEKDAYS:
        return True

    return False


def parse_time_suffix(text: str) -> tuple[str, time | None]:
    """Extract time suffix from a date expression.

    Args:
        text: Date expression that may contain a time suffix like "14:30" or "2pm"

    Returns:
        Tuple of (date_part, time_or_none)

    Examples:
        "today 14:30" -> ("today", time(14, 30))
        "friday 2pm" -> ("friday", time(14, 0))
        "2025-12-01 09:00" -> ("2025-12-01", time(9, 0))
        "tomorrow" -> ("tomorrow", None)
    """
    if not text:
        return text, None

    text = text.strip()

    # Pattern for time: HH:MM, H:MM, HHam/pm, Ham/pm
    # Must be at the end of the string, preceded by whitespace
    time_patterns = [
        # 24-hour format: 14:30, 9:00
        (
            r"^(.+?)\s+(\d{1,2}):(\d{2})$",
            lambda m: time(int(m.group(2)), int(m.group(3))),
        ),
        # 12-hour format with am/pm: 2pm, 11am, 2:30pm
        (
            r"^(.+?)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)$",
            lambda m: time(
                int(m.group(2)) % 12 + (12 if m.group(4).lower() == "pm" else 0),
                int(m.group(3)) if m.group(3) else 0,
            ),
        ),
    ]

    for pattern, time_extractor in time_patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            try:
                return match.group(1).strip(), time_extractor(match)
            except ValueError:
                # Invalid time (e.g., 25:00)
                pass

    return text, None


def parse_fuzzy_datetime(text: str) -> datetime | None:
    """Parse a fuzzy date expression into a datetime object.

    Like parse_fuzzy_date but returns datetime and supports time suffixes.

    Supports:
    - All formats from parse_fuzzy_date
    - Time suffixes: "today 14:30", "friday 2pm", "2025-12-01 09:00"

    Returns datetime with time if specified, or datetime at midnight (00:00:00) if not.
    Returns None if parsing fails.
    """
    if not text:
        return None

    # Extract time suffix if present
    date_part, time_value = parse_time_suffix(text)

    # Parse the date part
    parsed_date = parse_fuzzy_date(date_part)
    if parsed_date is None:
        return None

    # Combine date with time (default to midnight)
    if time_value is None:
        time_value = time.min
    return datetime.combine(parsed_date, time_value)


def parse_fuzzy_datetime_future(text: str) -> datetime | None:
    """Parse a fuzzy datetime expression with weekday names defaulting to NEXT occurrence.

    Like parse_fuzzy_date_future but returns datetime and supports time suffixes.

    Returns None if parsing fails or if text is a clear keyword.
    """
    if not text:
        return None

    text_lower = text.strip().lower()

    # Check if user wants to clear the due date
    if text_lower in CLEAR_DATE_KEYWORDS:
        return None

    # Extract time suffix if present
    date_part, time_value = parse_time_suffix(text)

    # Parse the date part using future-oriented parser
    parsed_date = parse_fuzzy_date_future(date_part)
    if parsed_date is None:
        return None

    # Combine date with time (default to midnight)
    if time_value is None:
        time_value = time.min
    return datetime.combine(parsed_date, time_value)


def format_datetime(dt: datetime, include_time: bool | None = None) -> str:
    """Format a datetime for display in @due() tags.

    Args:
        dt: The datetime to format
        include_time: If True, always include time. If False, never include time.
            If None (default), include time only if it's not midnight.

    Returns:
        ISO format date string, optionally with time (YYYY-MM-DD or YYYY-MM-DD HH:MM)
    """
    if include_time is None:
        # Auto-detect: include time if not midnight
        include_time = dt.time() != time.min

    if include_time:
        return dt.strftime("%Y-%m-%d %H:%M")
    else:
        return dt.strftime("%Y-%m-%d")


def datetime_to_date(dt: datetime | date | None) -> date | None:
    """Convert datetime to date, handling None and date inputs."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.date()
    return dt


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


def get_week_range(
        dt: date | None = None, week_start_day: str | None = None
) -> tuple[date, date]:
    """Get the start and end of the week containing dt.

    Args:
        dt: The date to get the week for (defaults to today).
        week_start_day: First day of week ("monday" or "sunday").
                       If None, reads from config.

    Returns:
        Tuple of (start_date, end_date) for the week.
    """
    if dt is None:
        dt = date.today()

    # Get week start day from config if not specified
    if week_start_day is None:
        from nb.config import get_config

        week_start_day = get_config().week_start_day

    if week_start_day == "sunday":
        # Sunday = 6, so we need (dt.weekday() + 1) % 7 days back
        days_since_sunday = (dt.weekday() + 1) % 7
        start = dt - timedelta(days=days_since_sunday)
    else:
        # Monday = 0 (default)
        start = dt - timedelta(days=dt.weekday())

    end = start + timedelta(days=6)
    return start, end


def get_week_folder_name(
        dt: date | None = None, week_start_day: str | None = None
) -> str:
    """Get the week folder name for a date (e.g., 'Nov25-Dec01').

    Uses configured week start day (Monday or Sunday).
    """
    if dt is None:
        dt = date.today()
    start, end = get_week_range(dt, week_start_day)
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
        since_date = parse_fuzzy_date(since_match.group(1))
        if since_date:
            return since_date, today

    # Handle "<date> to <date>"
    range_match = re.match(r"^(.+?)\s+to\s+(.+)$", text)
    if range_match:
        range_start = parse_fuzzy_date(range_match.group(1))
        range_end = parse_fuzzy_date(range_match.group(2))
        if range_start and range_end:
            return range_start, range_end

    # Try parsing as a single date (search that specific day)
    single_date = parse_fuzzy_date(text)
    if single_date:
        return single_date, single_date

    return None, None
