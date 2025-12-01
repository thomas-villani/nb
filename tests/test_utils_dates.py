"""Tests for nb.utils.dates module."""

from __future__ import annotations

from datetime import date, timedelta

from nb.utils.dates import (
    format_date,
    get_month_range,
    get_relative_date_label,
    get_week_folder_name,
    get_week_range,
    get_weeks_ago,
    is_date_in_range,
    parse_date_from_filename,
    parse_date_range,
    parse_fuzzy_date,
    parse_week_folder_name,
)


class TestParseFuzzyDate:
    """Tests for parse_fuzzy_date function."""

    def test_empty_string_returns_none(self):
        assert parse_fuzzy_date("") is None
        assert parse_fuzzy_date("   ") is None

    def test_today(self, fixed_today: date):
        result = parse_fuzzy_date("today")
        assert result == fixed_today

    def test_yesterday(self, fixed_today: date):
        result = parse_fuzzy_date("yesterday")
        assert result == fixed_today - timedelta(days=1)

    def test_tomorrow(self, fixed_today: date):
        result = parse_fuzzy_date("tomorrow")
        assert result == fixed_today + timedelta(days=1)

    def test_next_week(self, fixed_today: date):
        result = parse_fuzzy_date("next week")
        assert result == fixed_today + timedelta(weeks=1)

    def test_last_week(self, fixed_today: date):
        result = parse_fuzzy_date("last week")
        assert result == fixed_today - timedelta(weeks=1)

    def test_weekday_names_full(self, fixed_today: date):
        # fixed_today is a Friday (2025-11-28)
        result = parse_fuzzy_date("friday")
        assert result == fixed_today  # Today is Friday

        result = parse_fuzzy_date("monday")
        # Last Monday from Friday is 4 days ago (most recent occurrence)
        assert result == fixed_today - timedelta(days=4)

    def test_weekday_names_short(self, fixed_today: date):
        result = parse_fuzzy_date("fri")
        assert result == fixed_today

        result = parse_fuzzy_date("mon")
        # Last Monday from Friday is 4 days ago (most recent occurrence)
        assert result == fixed_today - timedelta(days=4)

    def test_next_weekday(self, fixed_today: date):
        # "next friday" on a Friday returns THIS Friday (same day)
        # because relativedelta(weekday=FR(+1)) returns the next occurrence ON OR AFTER today
        result = parse_fuzzy_date("next friday")
        assert result == fixed_today

        result = parse_fuzzy_date("next monday")
        assert result == fixed_today + timedelta(days=3)

    def test_last_weekday(self, fixed_today: date):
        # "last friday" on a Friday returns THIS Friday (same day)
        # because relativedelta(weekday=FR(-1)) returns the last occurrence ON OR BEFORE today
        result = parse_fuzzy_date("last friday")
        assert result == fixed_today

        result = parse_fuzzy_date("last monday")
        # Last Monday from Friday (4 days ago)
        assert result == fixed_today - timedelta(days=4)

    def test_iso_date(self):
        result = parse_fuzzy_date("2025-11-20")
        assert result == date(2025, 11, 20)

    def test_natural_language_date(self):
        result = parse_fuzzy_date("nov 20")
        assert result is not None
        assert result.month == 11
        assert result.day == 20

        result = parse_fuzzy_date("november 20 2025")
        assert result == date(2025, 11, 20)

    def test_case_insensitive(self, fixed_today: date):
        assert parse_fuzzy_date("TODAY") == fixed_today
        assert parse_fuzzy_date("Friday") == fixed_today
        assert parse_fuzzy_date("NEXT MONDAY") is not None

    def test_invalid_returns_none(self):
        assert parse_fuzzy_date("not a date") is None
        # Note: dateutil's fuzzy parser is lenient and may extract numbers as years
        # so "gibberish123" might parse to year 123. Test truly unparseable strings.
        assert parse_fuzzy_date("xyz abc") is None


class TestParseDateFromFilename:
    """Tests for parse_date_from_filename function."""

    def test_standard_format(self):
        result = parse_date_from_filename("2025-11-26.md")
        assert result == date(2025, 11, 26)

    def test_with_prefix(self):
        result = parse_date_from_filename("notes-2025-11-26.md")
        assert result == date(2025, 11, 26)

    def test_in_path(self):
        result = parse_date_from_filename("daily/2025/Nov25/2025-11-26.md")
        assert result == date(2025, 11, 26)

    def test_no_date(self):
        result = parse_date_from_filename("project-notes.md")
        assert result is None

    def test_invalid_date(self):
        # Invalid month
        result = parse_date_from_filename("2025-13-26.md")
        assert result is None

        # Invalid day
        result = parse_date_from_filename("2025-11-32.md")
        assert result is None


class TestFormatDate:
    """Tests for format_date function."""

    def test_default_iso_format(self):
        result = format_date(date(2025, 11, 26))
        assert result == "2025-11-26"

    def test_custom_format(self):
        result = format_date(date(2025, 11, 26), "%B %d, %Y")
        assert result == "November 26, 2025"

    def test_short_format(self):
        result = format_date(date(2025, 11, 26), "%m/%d/%y")
        assert result == "11/26/25"


class TestGetRelativeDateLabel:
    """Tests for get_relative_date_label function."""

    def test_today(self, fixed_today: date, monkeypatch):
        # Also need to patch date in dates module
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        result = get_relative_date_label(fixed_today)
        assert result == "today"

    def test_yesterday(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        result = get_relative_date_label(fixed_today - timedelta(days=1))
        assert result == "yesterday"

    def test_tomorrow(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        result = get_relative_date_label(fixed_today + timedelta(days=1))
        assert result == "tomorrow"

    def test_this_week_shows_weekday(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        # 3 days from now (Monday)
        result = get_relative_date_label(fixed_today + timedelta(days=3))
        assert result == "Monday"


class TestIsDateInRange:
    """Tests for is_date_in_range function."""

    def test_in_range(self):
        start = date(2025, 11, 1)
        end = date(2025, 11, 30)
        assert is_date_in_range(date(2025, 11, 15), start, end) is True

    def test_at_boundaries(self):
        start = date(2025, 11, 1)
        end = date(2025, 11, 30)
        assert is_date_in_range(start, start, end) is True
        assert is_date_in_range(end, start, end) is True

    def test_before_range(self):
        start = date(2025, 11, 1)
        end = date(2025, 11, 30)
        assert is_date_in_range(date(2025, 10, 31), start, end) is False

    def test_after_range(self):
        start = date(2025, 11, 1)
        end = date(2025, 11, 30)
        assert is_date_in_range(date(2025, 12, 1), start, end) is False

    def test_open_start(self):
        end = date(2025, 11, 30)
        assert is_date_in_range(date(2025, 1, 1), None, end) is True
        assert is_date_in_range(date(2025, 12, 1), None, end) is False

    def test_open_end(self):
        start = date(2025, 11, 1)
        assert is_date_in_range(date(2025, 12, 1), start, None) is True
        assert is_date_in_range(date(2025, 10, 1), start, None) is False


class TestGetWeekRange:
    """Tests for get_week_range function."""

    def test_returns_monday_to_sunday(self):
        # Wednesday
        dt = date(2025, 11, 26)
        start, end = get_week_range(dt)

        assert start == date(2025, 11, 24)  # Monday
        assert end == date(2025, 11, 30)  # Sunday
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday

    def test_monday_input(self):
        dt = date(2025, 11, 24)  # Monday
        start, end = get_week_range(dt)
        assert start == dt
        assert end == date(2025, 11, 30)

    def test_sunday_input(self):
        dt = date(2025, 11, 30)  # Sunday
        start, end = get_week_range(dt)
        assert start == date(2025, 11, 24)
        assert end == dt


class TestGetWeekFolderName:
    """Tests for get_week_folder_name function."""

    def test_same_month(self):
        dt = date(2025, 11, 26)  # Wed in week Nov24-Nov30
        result = get_week_folder_name(dt)
        assert result == "Nov24-Nov30"

    def test_cross_month(self):
        dt = date(2025, 11, 28)  # Fri in week Nov24-Nov30
        result = get_week_folder_name(dt)
        assert result == "Nov24-Nov30"

        # A week that crosses Dec
        dt = date(2025, 12, 1)  # Mon
        result = get_week_folder_name(dt)
        assert result == "Dec01-Dec07"


class TestParseWeekFolderName:
    """Tests for parse_week_folder_name function."""

    def test_same_month(self):
        result = parse_week_folder_name("Nov24-Nov30", 2025)
        assert result is not None
        start, end = result
        assert start == date(2025, 11, 24)
        assert end == date(2025, 11, 30)

    def test_cross_year(self):
        result = parse_week_folder_name("Dec29-Jan04", 2025)
        assert result is not None
        start, end = result
        assert start == date(2025, 12, 29)
        assert end == date(2026, 1, 4)

    def test_invalid_format(self):
        assert parse_week_folder_name("invalid", 2025) is None
        assert parse_week_folder_name("Nov-Dec", 2025) is None
        assert parse_week_folder_name("11-24-11-30", 2025) is None


class TestGetWeeksAgo:
    """Tests for get_weeks_ago function."""

    def test_this_week(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = get_weeks_ago(0)
        assert start <= fixed_today <= end

    def test_last_week(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = get_weeks_ago(1)
        assert end < fixed_today


class TestGetMonthRange:
    """Tests for get_month_range function."""

    def test_november(self):
        dt = date(2025, 11, 15)
        start, end = get_month_range(dt)
        assert start == date(2025, 11, 1)
        assert end == date(2025, 11, 30)

    def test_december(self):
        dt = date(2025, 12, 25)
        start, end = get_month_range(dt)
        assert start == date(2025, 12, 1)
        assert end == date(2025, 12, 31)

    def test_february_leap_year(self):
        dt = date(2024, 2, 15)  # 2024 is a leap year
        start, end = get_month_range(dt)
        assert start == date(2024, 2, 1)
        assert end == date(2024, 2, 29)

    def test_february_non_leap_year(self):
        dt = date(2025, 2, 15)  # 2025 is not a leap year
        start, end = get_month_range(dt)
        assert start == date(2025, 2, 1)
        assert end == date(2025, 2, 28)


class TestParseDateRange:
    """Tests for parse_date_range function."""

    def test_empty_string(self):
        start, end = parse_date_range("")
        assert start is None
        assert end is None

    def test_today(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("today")
        assert start == fixed_today
        assert end == fixed_today

    def test_yesterday(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("yesterday")
        assert start == fixed_today - timedelta(days=1)
        assert end == fixed_today - timedelta(days=1)

    def test_this_week(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("this week")
        assert start <= fixed_today <= end
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday

    def test_this_month(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("this month")
        assert start.month == fixed_today.month
        assert end.month == fixed_today.month

    def test_last_n_days(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("last 7 days")
        assert start == fixed_today - timedelta(days=7)
        assert end == fixed_today

    def test_last_n_weeks(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("last 2 weeks")
        assert start == fixed_today - timedelta(weeks=2)
        assert end == fixed_today

    def test_past_alias(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("past 3 days")
        assert start == fixed_today - timedelta(days=3)
        assert end == fixed_today

    def test_explicit_range(self, fixed_today: date, monkeypatch):
        class MockDate(date):
            @classmethod
            def today(cls):
                return fixed_today

        monkeypatch.setattr("nb.utils.dates.date", MockDate)

        start, end = parse_date_range("2025-11-01 to 2025-11-30")
        assert start == date(2025, 11, 1)
        assert end == date(2025, 11, 30)

    def test_single_date_returns_same_start_end(self):
        start, end = parse_date_range("2025-11-26")
        assert start == date(2025, 11, 26)
        assert end == date(2025, 11, 26)


class TestIsRelativeDate:
    """Tests for is_relative_date function."""

    def test_today_is_relative(self):
        from nb.utils.dates import is_relative_date

        assert is_relative_date("today") is True
        assert is_relative_date("TODAY") is True

    def test_tomorrow_is_relative(self):
        from nb.utils.dates import is_relative_date

        assert is_relative_date("tomorrow") is True

    def test_yesterday_is_relative(self):
        from nb.utils.dates import is_relative_date

        assert is_relative_date("yesterday") is True

    def test_weekday_is_relative(self):
        from nb.utils.dates import is_relative_date

        assert is_relative_date("friday") is True
        assert is_relative_date("Monday") is True
        assert is_relative_date("next friday") is True
        assert is_relative_date("last monday") is True

    def test_relative_with_time(self):
        from nb.utils.dates import is_relative_date

        assert is_relative_date("today 2pm") is True
        assert is_relative_date("tomorrow 14:30") is True
        assert is_relative_date("friday 9am") is True

    def test_iso_date_not_relative(self):
        from nb.utils.dates import is_relative_date

        assert is_relative_date("2025-12-01") is False
        assert is_relative_date("dec 15") is False

    def test_empty_not_relative(self):
        from nb.utils.dates import is_relative_date

        assert is_relative_date("") is False
        assert is_relative_date("   ") is False


class TestParseFuzzyDatetime:
    """Tests for parse_fuzzy_datetime function."""

    def test_date_only(self, fixed_today: date):
        from datetime import datetime

        from nb.utils.dates import parse_fuzzy_datetime

        result = parse_fuzzy_datetime("2025-12-01")
        assert result == datetime(2025, 12, 1, 0, 0)

    def test_relative_date(self, fixed_today: date):
        from datetime import datetime, time

        from nb.utils.dates import parse_fuzzy_datetime

        result = parse_fuzzy_datetime("today")
        assert result == datetime.combine(fixed_today, time.min)

    def test_with_time_24h(self, fixed_today: date):
        from datetime import datetime, time

        from nb.utils.dates import parse_fuzzy_datetime

        result = parse_fuzzy_datetime("today 14:30")
        assert result == datetime.combine(fixed_today, time(14, 30))

    def test_with_time_12h_pm(self, fixed_today: date):
        from datetime import datetime, time

        from nb.utils.dates import parse_fuzzy_datetime

        result = parse_fuzzy_datetime("today 2pm")
        assert result == datetime.combine(fixed_today, time(14, 0))

    def test_with_time_12h_am(self, fixed_today: date):
        from datetime import datetime, time

        from nb.utils.dates import parse_fuzzy_datetime

        result = parse_fuzzy_datetime("today 9am")
        assert result == datetime.combine(fixed_today, time(9, 0))

    def test_iso_date_with_time(self):
        from datetime import datetime

        from nb.utils.dates import parse_fuzzy_datetime

        result = parse_fuzzy_datetime("2025-12-01 09:30")
        assert result == datetime(2025, 12, 1, 9, 30)

    def test_empty_returns_none(self):
        from nb.utils.dates import parse_fuzzy_datetime

        assert parse_fuzzy_datetime("") is None
        assert parse_fuzzy_datetime("   ") is None


class TestFormatDatetime:
    """Tests for format_datetime function."""

    def test_date_only_midnight(self):
        from datetime import datetime

        from nb.utils.dates import format_datetime

        dt = datetime(2025, 12, 1, 0, 0)
        assert format_datetime(dt) == "2025-12-01"

    def test_with_time(self):
        from datetime import datetime

        from nb.utils.dates import format_datetime

        dt = datetime(2025, 12, 1, 14, 30)
        assert format_datetime(dt) == "2025-12-01 14:30"

    def test_force_include_time(self):
        from datetime import datetime

        from nb.utils.dates import format_datetime

        dt = datetime(2025, 12, 1, 0, 0)
        assert format_datetime(dt, include_time=True) == "2025-12-01 00:00"

    def test_force_exclude_time(self):
        from datetime import datetime

        from nb.utils.dates import format_datetime

        dt = datetime(2025, 12, 1, 14, 30)
        assert format_datetime(dt, include_time=False) == "2025-12-01"
