"""
Universal scraper — reads company lists from DB, runs all ATS scrapers.

Scraping order / priority (for dedup):
  1. Greenhouse (highest quality, direct ATS)
  2. Lever
  3. Ashby
  4. Workday
  5. SmartRecruiters / BambooHR / Workable / Recruitee
  6. HiringCafe (widest coverage, lowest priority)
"""
import asyncio
from collections import Counter
from scrapers import greenhouse, lever, ashby, workday, hiringcafe
from scrapers import smartrecruiters, bamboohr, workable, recruitee

SOURCE_PRIORITY = {
    "Greenhouse":      1,
    "Lever":           2,
    "Ashby":           3,
    "Workday":         4,
    "SmartRecruiters": 4,
    "BambooHR":        4,
    "Workable":        4,
    "Recruitee":       4,
    "Google":          4,
    "Apple":           4,
    "Meta":            4,
    "Netflix":         4,
    "HiringCafe":      5,
}


async def _get_slugs_for_ats(ats: str) -> list[str]:
    """Fetch active company slugs for an ATS from the companies table."""
    try:
        from database import SessionLocal, Company
        from sqlalchemy import select
        async with SessionLocal() as db:
            result = await db.execute(
                select(Company.slug).where(
                    Company.ats == ats,
                    Company.active == True
                )
            )
            slugs = [row[0] for row in result.fetchall()]
            if slugs:
                return slugs
    except Exception as e:
        print(f"[Scrapers] DB slug fetch failed for {ats}: {e}")
    return []  # falls back to hardcoded in each scraper


def _fingerprint(job: dict) -> str:
    title   = job.get("title",   "").lower().strip()
    company = job.get("company", "").lower().strip()
    return f"{title}|||{company}"


def _dedup(results, group_name: str = "") -> list[dict]:
    """Merge scraper batches, dedup by URL then fingerprint (source priority wins)."""
    raw: list[dict] = []
    for batch in results:
        if isinstance(batch, Exception):
            print(f"[Scrapers/{group_name}] batch error: {batch}")
            continue
        raw.extend(batch)

    seen_fp:  dict[str, dict] = {}
    seen_url: set[str] = set()

    for job in raw:
        url = job.get("url", "")
        if url and url in seen_url:
            continue
        fp = _fingerprint(job)
        src_priority = SOURCE_PRIORITY.get(job.get("source", ""), 99)
        if fp not in seen_fp:
            seen_fp[fp] = job
            if url:
                seen_url.add(url)
        else:
            existing_priority = SOURCE_PRIORITY.get(seen_fp[fp].get("source", ""), 99)
            if src_priority < existing_priority:
                old_url = seen_fp[fp].get("url", "")
                if old_url in seen_url:
                    seen_url.discard(old_url)
                seen_fp[fp] = job
                if url:
                    seen_url.add(url)

    all_jobs = list(seen_fp.values())
    by_src = Counter(j.get("source", "?") for j in all_jobs)
    print(f"[Scrapers/{group_name}] {len(all_jobs)} unique jobs (from {len(raw)} raw)")
    for src, n in by_src.most_common():
        print(f"  {src}: {n}")
    return all_jobs


# ── Group A: fast scrapers (~3-5 min) ────────────────────────────────────────
# Lever + Ashby + Workday + SmartRecruiters + Workable + BambooHR + Recruitee
async def run_group_fast(settings: dict) -> list[dict]:
    lever_slugs, ashby_slugs, wd_slugs = await asyncio.gather(
        _get_slugs_for_ats("lever"),
        _get_slugs_for_ats("ashby"),
        _get_slugs_for_ats("workday"),
    )
    s = {**settings, "_lever_slugs": lever_slugs, "_ashby_slugs": ashby_slugs, "_wd_slugs": wd_slugs}
    results = await asyncio.gather(
        lever.fetch(s),
        ashby.fetch(s),
        workday.fetch(s),
        smartrecruiters.fetch(settings),
        bamboohr.fetch(settings),
        workable.fetch(settings),
        recruitee.fetch(settings),
        return_exceptions=True,
    )
    return _dedup(results, "GroupA-Fast")


# ── Group B: Greenhouse (~5-10 min) ──────────────────────────────────────────
async def run_group_greenhouse(settings: dict) -> list[dict]:
    gh_slugs = await _get_slugs_for_ats("greenhouse")
    s = {**settings, "_gh_slugs": gh_slugs}
    results = await asyncio.gather(
        greenhouse.fetch(s),
        return_exceptions=True,
    )
    return _dedup(results, "GroupB-Greenhouse")


# ── Group C: HiringCafe (~8-15 min) ──────────────────────────────────────────
async def run_group_hiringcafe(settings: dict) -> list[dict]:
    results = await asyncio.gather(
        hiringcafe.fetch(settings),
        return_exceptions=True,
    )
    return _dedup(results, "GroupC-HiringCafe")


# ── Legacy: all scrapers at once (kept for backward compat) ──────────────────
async def run_all_scrapers(settings: dict) -> list[dict]:
    gh_slugs, lever_slugs, ashby_slugs, wd_slugs = await asyncio.gather(
        _get_slugs_for_ats("greenhouse"),
        _get_slugs_for_ats("lever"),
        _get_slugs_for_ats("ashby"),
        _get_slugs_for_ats("workday"),
    )
    settings_with_slugs = {
        **settings,
        "_gh_slugs":    gh_slugs,
        "_lever_slugs": lever_slugs,
        "_ashby_slugs": ashby_slugs,
        "_wd_slugs":    wd_slugs,
    }
    results = await asyncio.gather(
        greenhouse.fetch(settings_with_slugs),
        lever.fetch(settings_with_slugs),
        ashby.fetch(settings_with_slugs),
        workday.fetch(settings_with_slugs),
        smartrecruiters.fetch(settings),
        bamboohr.fetch(settings),
        workable.fetch(settings),
        recruitee.fetch(settings),
        hiringcafe.fetch(settings),
        return_exceptions=True,
    )
    return _dedup(results, "AllScrapers")
