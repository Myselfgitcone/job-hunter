"""The app's calendar is America/Chicago (main.APP_TZ). Timestamps are stored in UTC; which DAY
one belongs to is decided by these helpers, never by slicing the UTC string.

The live fault: an application at 10pm on Sep 28 in Chicago is 03:00Z on Sep 29, and every
day-bucketing took the UTC date, so it was charted under Sep 29, the 45/day limits reset at
7pm, and the timeline showed a Sep 29 point while it was still Sep 28.

Run from backend/:  python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _local_day, _local_day_window_utc, _to_local  # noqa: E402


def test_late_evening_in_chicago_is_still_that_day():
    assert _local_day("2026-09-29T03:00:00Z") == "2026-09-28"       # 10pm CDT Sep 28
    assert _local_day("2026-09-29T04:59:59Z") == "2026-09-28"       # 11:59:59pm CDT
    assert _local_day("2026-09-29T05:00:00Z") == "2026-09-29"       # midnight CDT


def test_naive_and_offset_forms_are_read_as_utc():
    assert _local_day("2026-09-29T03:00:00") == "2026-09-28"        # old rows without the Z
    assert _local_day("2026-09-29T03:00:00+00:00") == "2026-09-28"
    assert _local_day("") == "" and _local_day(None) == ""
    assert _to_local("not a date") is None


def test_day_window_is_chicago_midnight_to_midnight_in_utc():
    assert _local_day_window_utc("2026-09-28") == ("2026-09-28T05:00:00Z", "2026-09-29T05:00:00Z")  # CDT
    assert _local_day_window_utc("2026-01-15") == ("2026-01-15T06:00:00Z", "2026-01-16T06:00:00Z")  # CST
    # the window and the day helper agree at both edges
    start, end = _local_day_window_utc("2026-09-28")
    assert _local_day(start) == "2026-09-28"
    assert _local_day(end) == "2026-09-29"


def test_window_strings_compare_chronologically_as_stored():
    # stored timestamps are 'YYYY-MM-DDTHH:MM:SSZ'; the window is compared as strings in SQL
    start, end = _local_day_window_utc("2026-09-28")
    assert start <= "2026-09-29T03:00:00Z" < end                     # 10pm CDT lands inside
    assert not (start <= "2026-09-29T05:00:00Z" < end)               # midnight CDT is the next day
