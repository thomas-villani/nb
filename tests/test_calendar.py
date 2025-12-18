"""Tests for Outlook calendar integration."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from nb.core.calendar import (
    CalendarCache,
    CalendarEvent,
    OutlookCalendarClient,
)


class TestCalendarEvent:
    """Tests for CalendarEvent dataclass."""

    def test_duration_minutes(self):
        """Test duration calculation."""
        event = CalendarEvent(
            subject="Meeting",
            start=datetime(2025, 1, 15, 10, 0),
            end=datetime(2025, 1, 15, 11, 30),
        )
        assert event.duration_minutes == 90

    def test_is_meeting_with_attendees(self):
        """Test is_meeting property with multiple attendees."""
        event = CalendarEvent(
            subject="Team Sync",
            start=datetime(2025, 1, 15, 10, 0),
            end=datetime(2025, 1, 15, 11, 0),
            attendees=["Alice", "Bob"],
        )
        assert event.is_meeting is True

    def test_is_meeting_without_attendees(self):
        """Test is_meeting property without attendees."""
        event = CalendarEvent(
            subject="Focus Time",
            start=datetime(2025, 1, 15, 10, 0),
            end=datetime(2025, 1, 15, 11, 0),
            attendees=[],
        )
        assert event.is_meeting is False

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        original = CalendarEvent(
            subject="Test Event",
            start=datetime(2025, 1, 15, 10, 0),
            end=datetime(2025, 1, 15, 11, 0),
            location="Room 101",
            attendees=["Alice", "Bob"],
            is_all_day=False,
            is_recurring=True,
            categories=["work", "important"],
        )

        data = original.to_dict()
        restored = CalendarEvent.from_dict(data)

        assert restored.subject == original.subject
        assert restored.start == original.start
        assert restored.end == original.end
        assert restored.location == original.location
        assert restored.attendees == original.attendees
        assert restored.is_all_day == original.is_all_day
        assert restored.is_recurring == original.is_recurring
        assert restored.categories == original.categories


class TestCalendarCache:
    """Tests for calendar caching."""

    def test_cache_miss_returns_none(self, tmp_path: Path):
        """Cache returns None on cache miss."""
        cache = CalendarCache(tmp_path / "cache.json", ttl_minutes=15)
        result = cache.get_events(date(2025, 1, 15), date(2025, 1, 21))
        assert result is None

    def test_cache_hit_returns_events(self, tmp_path: Path):
        """Cache returns stored events on hit."""
        cache = CalendarCache(tmp_path / "cache.json", ttl_minutes=15)

        events = [
            CalendarEvent(
                subject="Event 1",
                start=datetime(2025, 1, 15, 10, 0),
                end=datetime(2025, 1, 15, 11, 0),
            ),
            CalendarEvent(
                subject="Event 2",
                start=datetime(2025, 1, 16, 14, 0),
                end=datetime(2025, 1, 16, 15, 0),
            ),
        ]

        start = date(2025, 1, 15)
        end = date(2025, 1, 21)

        cache.set_events(start, end, events)
        result = cache.get_events(start, end)

        assert result is not None
        assert len(result) == 2
        assert result[0].subject == "Event 1"
        assert result[1].subject == "Event 2"

    def test_cache_expiry(self, tmp_path: Path, monkeypatch):
        """Cache respects TTL and expires old entries."""
        cache_path = tmp_path / "cache.json"
        cache = CalendarCache(cache_path, ttl_minutes=1)

        events = [
            CalendarEvent(
                subject="Old Event",
                start=datetime(2025, 1, 15, 10, 0),
                end=datetime(2025, 1, 15, 11, 0),
            )
        ]

        start = date(2025, 1, 15)
        end = date(2025, 1, 21)

        # Store events
        cache.set_events(start, end, events)

        # Manually modify timestamp to be old
        with cache_path.open() as f:
            data = json.load(f)

        old_time = datetime.now() - timedelta(minutes=5)
        key = f"{start.isoformat()}:{end.isoformat()}"
        data["entries"][key]["timestamp"] = old_time.isoformat()

        with cache_path.open("w") as f:
            json.dump(data, f)

        # Create new cache instance to reload
        cache2 = CalendarCache(cache_path, ttl_minutes=1)
        result = cache2.get_events(start, end)

        assert result is None  # Expired entry should return None

    def test_cache_clear(self, tmp_path: Path):
        """Cache can be cleared."""
        cache = CalendarCache(tmp_path / "cache.json", ttl_minutes=15)

        events = [
            CalendarEvent(
                subject="Event",
                start=datetime(2025, 1, 15, 10, 0),
                end=datetime(2025, 1, 15, 11, 0),
            )
        ]

        start = date(2025, 1, 15)
        end = date(2025, 1, 21)

        cache.set_events(start, end, events)
        cache.clear()
        result = cache.get_events(start, end)

        assert result is None


class TestOutlookClient:
    """Tests for Outlook client (mocked)."""

    def test_is_available_false_on_non_windows(self, monkeypatch):
        """Returns False on non-Windows platforms."""
        monkeypatch.setattr("nb.core.calendar.IS_WINDOWS", False)

        client = OutlookCalendarClient()
        assert client.is_available() is False

    def test_get_events_empty_on_unavailable(self, monkeypatch):
        """Returns empty list when Outlook is unavailable."""
        monkeypatch.setattr("nb.core.calendar.IS_WINDOWS", False)

        client = OutlookCalendarClient()
        result = client.get_events(date(2025, 1, 15), date(2025, 1, 21))

        assert result == []

    def test_get_events_uses_cache(self, tmp_path: Path, monkeypatch):
        """Uses cached events when available."""
        monkeypatch.setattr("nb.core.calendar.IS_WINDOWS", False)

        cache = CalendarCache(tmp_path / "cache.json", ttl_minutes=15)
        events = [
            CalendarEvent(
                subject="Cached Event",
                start=datetime(2025, 1, 15, 10, 0),
                end=datetime(2025, 1, 15, 11, 0),
            )
        ]

        start = date(2025, 1, 15)
        end = date(2025, 1, 21)
        cache.set_events(start, end, events)

        client = OutlookCalendarClient(cache=cache)
        # Force available to return True for this test
        client._available = True

        result = client.get_events(start, end, use_cache=True)

        assert len(result) == 1
        assert result[0].subject == "Cached Event"
