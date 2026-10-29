"""Fantastic.jobs scrape gates (2026-10-28): seniority is cut in the API request
(never billed) and again at insert time (never stored). Run from backend/:
python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone  # noqa: E402

from scrapers.fantasticjobs import (  # noqa: E402
    DEFAULT_FAMILIES_ON, LINK_CHECK_AFTER_DAYS, MAX_YEARS_ALLOWED, PLAN_RECHECK_DAYS, _dead_status,
    _experience_levels, _expiry_passed, _lacks_recent, _old_enough_for_link_check, _too_senior,
    compose_usa_filter,
)


def test_seniority_words_are_cut_inside_the_api_request():
    f = compose_usa_filter(set(DEFAULT_FAMILIES_ON))
    for word in ("principal", "staff", "manager", "director", "chief", "scientist"):
        assert word in f, word
    # the cut is a NOT clause, not a positive term
    assert "& !(" in f


def test_too_senior_drops_title_level_and_years():
    assert _too_senior("Principal Data Engineer", "", "") == "senior_title"
    assert _too_senior("Staff Data Engineer", "5-10", "") == "senior_title"
    assert _too_senior("Data Engineering Manager", "", "") == "senior_title"
    assert _too_senior("Head of Data Platform", "", "") == "senior_title"
    assert _too_senior("Senior Data Engineer", "10+", "") == "senior_10plus"
    assert _too_senior("Senior Data Engineer", "5-10", "Requires 9+ years of data engineering experience") == "senior_over_8yrs"
    assert _too_senior("Senior Data Engineer", "5-10", "10 years of experience required") == "senior_over_8yrs"


def test_too_senior_keeps_the_users_range():
    assert _too_senior("Senior Data Engineer", "5-10", "5+ years of experience with Spark") is None
    assert _too_senior("Senior Data Engineer", "2-5", "") is None
    assert _too_senior("Lead Data Engineer", "5-10", "7+ years") is None       # Lead is judged by qualify
    assert _too_senior("Senior Data Engineer", "5-10", "8+ years of experience") is None  # 8 is the user's ceiling, inclusive
    assert _too_senior("Junior Data Engineer", "0-2", "1+ years") is None     # no floor
    assert _too_senior("Data Engineer", "", "") is None                         # no years stated → keep
    assert _too_senior("AI Engineer", "5-10", "3 years with Python; 10 years total") is None  # min wins
    assert MAX_YEARS_ALLOWED == 8


def test_api_experience_filter_is_off_unless_env_set(monkeypatch):
    monkeypatch.delenv("FJ_EXPERIENCE_LEVELS", raising=False)
    assert _experience_levels() == []
    monkeypatch.setenv("FJ_EXPERIENCE_LEVELS", "0-2,2-5,5-10, bogus")
    assert _experience_levels() == ["0-2", "2-5", "5-10"]


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_expiry_passed_uses_the_postings_own_date():
    assert _expiry_passed("2026-10-27", NOW)                       # yesterday → gone
    assert not _expiry_passed("2026-10-28", NOW)                   # today → still live all day
    assert not _expiry_passed("2026-11-15", NOW)
    assert _expiry_passed("2026-10-28T09:00:00Z", NOW)             # exact moment passed
    assert not _expiry_passed("2026-10-28T18:00:00+00:00", NOW)
    assert not _expiry_passed("", NOW)                             # no date → nothing to judge
    assert not _expiry_passed("not a date", NOW)


def test_link_check_only_for_week_old_open_jobs():
    fresh = (NOW - timedelta(days=2)).isoformat()
    old = (NOW - timedelta(days=LINK_CHECK_AFTER_DAYS + 1)).isoformat()
    assert not _old_enough_for_link_check(fresh, "", NOW)
    assert _old_enough_for_link_check(old, "", NOW)
    assert _old_enough_for_link_check("", old, NOW)                # falls back to scraped_at
    assert not _old_enough_for_link_check("", "", NOW)


def test_only_404_and_410_count_as_dead():
    assert _dead_status(404) and _dead_status(410)
    for code in (200, 301, 403, 429, 500, 503, None):
        assert not _dead_status(code), code


def test_plan_feature_pause_expires_after_recheck_days():
    recent = (NOW - timedelta(days=1)).isoformat()
    stale = (NOW - timedelta(days=PLAN_RECHECK_DAYS + 1)).isoformat()
    assert _lacks_recent('{"expired": "%s"}' % recent, "expired", NOW)
    assert not _lacks_recent('{"expired": "%s"}' % stale, "expired", NOW)
    assert not _lacks_recent('{"expired": "%s"}' % recent, "modified", NOW)
    assert not _lacks_recent("", "expired", NOW)
    assert not _lacks_recent("{bad json", "expired", NOW)
