"""Outlook calendar integration for nb.

Provides access to Outlook calendar events via the pywin32 COM API,
with local file-based caching for performance.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Check if we're on Windows and can potentially use pywin32
IS_WINDOWS = sys.platform == "win32"


@dataclass
class CalendarEvent:
    """A calendar event from Outlook."""

    subject: str
    start: datetime
    end: datetime
    location: str | None = None
    body: str | None = None
    organizer: str | None = None
    attendees: list[str] = field(default_factory=list)
    is_all_day: bool = False
    is_recurring: bool = False
    categories: list[str] = field(default_factory=list)

    @property
    def duration_minutes(self) -> int:
        """Get the duration of the event in minutes."""
        delta = self.end - self.start
        return int(delta.total_seconds() / 60)

    @property
    def is_meeting(self) -> bool:
        """True if event has multiple attendees (is a meeting)."""
        return len(self.attendees) > 1

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "subject": self.subject,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "location": self.location,
            "body": self.body,
            "organizer": self.organizer,
            "attendees": self.attendees,
            "is_all_day": self.is_all_day,
            "is_recurring": self.is_recurring,
            "categories": self.categories,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CalendarEvent:
        """Create from dictionary."""
        return cls(
            subject=data["subject"],
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            location=data.get("location"),
            body=data.get("body"),
            organizer=data.get("organizer"),
            attendees=data.get("attendees", []),
            is_all_day=data.get("is_all_day", False),
            is_recurring=data.get("is_recurring", False),
            categories=data.get("categories", []),
        )


class CalendarCache:
    """File-based cache for calendar events.

    Stores events in a JSON file with TTL-based expiration.
    Cache is keyed by date range for efficient lookups.
    """

    def __init__(self, cache_path: Path, ttl_minutes: int = 15):
        """Initialize the cache.

        Args:
            cache_path: Path to the cache JSON file.
            ttl_minutes: Time-to-live for cached entries in minutes.
        """
        self.cache_path = cache_path
        self.ttl_minutes = ttl_minutes
        self._cache: dict | None = None

    def _load_cache(self) -> dict:
        """Load cache from disk."""
        if self._cache is not None:
            return self._cache

        if not self.cache_path.exists():
            self._cache = {"entries": {}}
            return self._cache

        try:
            with self.cache_path.open("r", encoding="utf-8") as f:
                self._cache = json.load(f)
                if "entries" not in self._cache:
                    self._cache = {"entries": {}}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load calendar cache: {e}")
            self._cache = {"entries": {}}

        return self._cache

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if self._cache is None:
            return

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save calendar cache: {e}")

    def _make_key(self, start: date, end: date) -> str:
        """Create a cache key from date range."""
        return f"{start.isoformat()}:{end.isoformat()}"

    def _is_expired(self, timestamp: str) -> bool:
        """Check if a cache entry has expired."""
        try:
            cached_time = datetime.fromisoformat(timestamp)
            age = datetime.now() - cached_time
            return age > timedelta(minutes=self.ttl_minutes)
        except ValueError:
            return True

    def get_events(self, start: date, end: date) -> list[CalendarEvent] | None:
        """Get cached events for a date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of cached events, or None if cache miss or expired.
        """
        cache = self._load_cache()
        key = self._make_key(start, end)

        entry = cache["entries"].get(key)
        if entry is None:
            return None

        if self._is_expired(entry.get("timestamp", "")):
            # Remove expired entry
            del cache["entries"][key]
            self._save_cache()
            return None

        try:
            return [CalendarEvent.from_dict(e) for e in entry.get("events", [])]
        except (KeyError, TypeError) as e:
            logger.warning(f"Failed to parse cached events: {e}")
            return None

    def set_events(self, start: date, end: date, events: list[CalendarEvent]) -> None:
        """Store events in cache.

        Args:
            start: Start date of the range.
            end: End date of the range.
            events: Events to cache.
        """
        cache = self._load_cache()
        key = self._make_key(start, end)

        cache["entries"][key] = {
            "timestamp": datetime.now().isoformat(),
            "events": [e.to_dict() for e in events],
        }

        self._save_cache()

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache = {"entries": {}}
        self._save_cache()


class OutlookCalendarClient:
    """Outlook calendar client using pywin32 COM API.

    Provides access to Outlook calendar events with optional caching.
    Gracefully handles non-Windows platforms and missing Outlook.
    """

    def __init__(self, cache: CalendarCache | None = None):
        """Initialize the client.

        Args:
            cache: Optional cache instance for caching fetched events.
        """
        self.cache = cache
        self._outlook = None
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Check if Outlook is installed and accessible.

        Returns:
            True if Outlook can be accessed, False otherwise.
        """
        if self._available is not None:
            return self._available

        if not IS_WINDOWS:
            self._available = False
            return False

        try:
            import win32com.client

            outlook = win32com.client.Dispatch("Outlook.Application")
            # Try to access the MAPI namespace to verify it works
            outlook.GetNamespace("MAPI")
            self._available = True
        except Exception as e:
            logger.debug(f"Outlook not available: {e}")
            self._available = False

        return self._available

    def get_events(
        self,
        start: date,
        end: date,
        use_cache: bool = True,
    ) -> list[CalendarEvent]:
        """Fetch calendar events for a date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).
            use_cache: Whether to use cached results if available.

        Returns:
            List of calendar events. Returns empty list if Outlook unavailable.
        """
        if not self.is_available():
            logger.debug("Outlook not available, returning empty event list")
            return []

        # Check cache first
        if use_cache and self.cache is not None:
            cached = self.cache.get_events(start, end)
            if cached is not None:
                logger.debug(f"Using cached calendar events for {start} to {end}")
                return cached

        # Fetch from Outlook
        events = self._fetch_from_outlook(start, end)

        # Update cache
        if self.cache is not None:
            self.cache.set_events(start, end, events)

        return events

    def _fetch_from_outlook(self, start: date, end: date) -> list[CalendarEvent]:
        """Fetch events directly from Outlook via COM API.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of calendar events.
        """
        if not IS_WINDOWS:
            return []

        try:
            import pywintypes
            import win32com.client

            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")

            # Get the default calendar folder (olFolderCalendar = 9)
            calendar = namespace.GetDefaultFolder(9)
            items = calendar.Items

            # Set up date range filter
            # Include the full end date by setting end time to end of day
            start_dt = datetime.combine(start, time.min)
            end_dt = datetime.combine(end, time.max)

            # Format dates for Outlook filter
            start_str = start_dt.strftime("%m/%d/%Y %H:%M %p")
            end_str = end_dt.strftime("%m/%d/%Y %H:%M %p")

            # Filter to date range
            # Use Restrict for better performance than iterating
            restriction = f"[Start] >= '{start_str}' AND [End] <= '{end_str}'"

            items.Sort("[Start]")
            items.IncludeRecurrences = True

            try:
                filtered_items = items.Restrict(restriction)
            except pywintypes.com_error:
                # Fallback: iterate and filter manually if Restrict fails
                filtered_items = items

            events = []
            for item in filtered_items:
                try:
                    # Get item start/end times
                    item_start = item.Start
                    item_end = item.End

                    # Handle pywintypes datetime objects
                    if hasattr(item_start, "Format"):
                        # It's a COM datetime, convert to Python datetime
                        item_start = datetime(
                            item_start.year,
                            item_start.month,
                            item_start.day,
                            item_start.hour,
                            item_start.minute,
                            item_start.second,
                        )
                        item_end = datetime(
                            item_end.year,
                            item_end.month,
                            item_end.day,
                            item_end.hour,
                            item_end.minute,
                            item_end.second,
                        )

                    # Manual date filtering as backup
                    if item_start.date() < start or item_start.date() > end:
                        continue

                    # Extract attendees
                    attendees = []
                    try:
                        recipients = item.Recipients
                        for i in range(recipients.Count):
                            recipient = recipients.Item(i + 1)  # 1-indexed
                            attendees.append(recipient.Name)
                    except Exception:
                        pass

                    # Extract categories
                    categories = []
                    try:
                        if item.Categories:
                            categories = [c.strip() for c in item.Categories.split(",")]
                    except Exception:
                        pass

                    event = CalendarEvent(
                        subject=str(item.Subject or ""),
                        start=item_start,
                        end=item_end,
                        location=str(item.Location or "") if item.Location else None,
                        body=(
                            str(item.Body or "")[:500] if item.Body else None
                        ),  # Truncate body
                        organizer=(
                            str(item.Organizer or "")
                            if hasattr(item, "Organizer")
                            else None
                        ),
                        attendees=attendees,
                        is_all_day=bool(item.AllDayEvent),
                        is_recurring=bool(item.IsRecurring),
                        categories=categories,
                    )
                    events.append(event)

                except Exception as e:
                    logger.debug(f"Failed to parse calendar item: {e}")
                    continue

            return events

        except Exception as e:
            logger.warning(f"Failed to fetch calendar events: {e}")
            return []


# Module-level client instance
_client: OutlookCalendarClient | None = None


def get_calendar_client() -> OutlookCalendarClient:
    """Get a calendar client instance with default caching.

    Returns:
        OutlookCalendarClient configured with file-based cache.
    """
    global _client

    if _client is None:
        from nb.config import get_config

        config = get_config()
        cache_path = config.notes_root / ".nb" / "calendar_cache.json"
        cache = CalendarCache(cache_path, ttl_minutes=15)
        _client = OutlookCalendarClient(cache=cache)

    return _client


def get_today_events() -> list[CalendarEvent]:
    """Get calendar events for today.

    Returns:
        List of today's calendar events.
    """
    today = date.today()
    return get_calendar_client().get_events(today, today)


def get_week_events(start: date | None = None) -> list[CalendarEvent]:
    """Get calendar events for a week.

    Args:
        start: Start date for the week. Defaults to next Monday
               (or today if today is Monday).

    Returns:
        List of calendar events for the week.
    """
    if start is None:
        today = date.today()
        # Start from Monday of this week
        days_since_monday = today.weekday()
        start = today - timedelta(days=days_since_monday)

    end = start + timedelta(days=6)  # Through Sunday
    return get_calendar_client().get_events(start, end)


def clear_calendar_cache() -> None:
    """Clear the calendar cache."""
    client = get_calendar_client()
    if client.cache:
        client.cache.clear()
