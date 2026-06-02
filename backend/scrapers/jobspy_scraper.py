"""
JobSpy scraper — DISABLED.

Indeed and LinkedIn are the primary ghost-job sources: companies leave listings
up for months after roles are filled. Removed to prevent stale/dead job links.
Google Jobs / Glassdoor / ZipRecruiter are blocked/broken in current jobspy.

Replaced by: direct ATS scraping (Greenhouse, Lever, Ashby, Dice, SmartRecruiters).
"""
from .base import JobData, detect_country, CUTOFF_HOURS

async def fetch(settings: dict) -> list[dict]:
    """Disabled — returns empty. See module docstring."""
    return []
