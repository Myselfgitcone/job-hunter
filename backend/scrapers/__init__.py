"""
Active scrapers — zero duplicates strategy:

  ── Direct ATS APIs (unique company coverage) ─────────────────────────────
  Greenhouse  — 2,550 boards. Covers companies HiringCafe misses.
  Lever       — 189 companies. Different set from HiringCafe.
  Ashby       — 911 companies. Different set from HiringCafe.

  ── HiringCafe ────────────────────────────────────────────────────────────
  HiringCafe  — 985+ DE/DA jobs / 4 days from 569 companies.
                Covers Taleo, iCIMS, SAP SuccessFactors, Paycom, Avature,
                Oracle Cloud — ATSes we can't scrape directly.

  ── Direct company pages ──────────────────────────────────────────────────
  Google / Apple / Meta / Netflix — direct career JSON APIs

Dropped (HiringCafe already covers these, dedup impossible via URL):
  Workday     — HiringCafe has workday source built-in
  BambooHR    — 0 jobs, HiringCafe covers it
  Recruitee   — 1 job, not worth it

Dedup strategy: title+company fingerprint (not URL).
  Same job posted on multiple ATSes → keep highest-priority source.
  Priority: Greenhouse > Lever > Ashby > Google/Apple/Meta/Netflix > HiringCafe
"""
import asyncio
from scrapers import (
    greenhouse, lever, ashby,
    google_jobs, apple_jobs, meta_jobs, netflix_jobs,
    hiringcafe,
)

# Source priority — lower number = kept when duplicate found
SOURCE_PRIORITY = {
    "Greenhouse": 1,
    "Lever":      2,
    "Ashby":      3,
    "Google":     4,
    "Apple":      4,
    "Meta":       4,
    "Netflix":    4,
    "HiringCafe": 5,
}


def _fingerprint(job: dict) -> str:
    """Normalized (title, company) key for cross-source dedup."""
    title   = job.get("title",   "").lower().strip()
    company = job.get("company", "").lower().strip()
    # Strip common seniority prefixes so "Senior Data Engineer" == "Data Engineer" doesn't merge
    # but "Senior Data Engineer @ Stripe" == "Senior Data Engineer @ Stripe" does
    return f"{title}|||{company}"


async def run_all_scrapers(settings: dict) -> list[dict]:
    results = await asyncio.gather(
        # ── Direct ATS (run first — higher priority) ───────────────────────
        greenhouse.fetch(settings),
        lever.fetch(settings),
        ashby.fetch(settings),
        # ── Direct company pages ───────────────────────────────────────────
        google_jobs.fetch(settings),
        apple_jobs.fetch(settings),
        meta_jobs.fetch(settings),
        netflix_jobs.fetch(settings),
        # ── HiringCafe last (lowest priority, but widest ATS coverage) ─────
        hiringcafe.fetch(settings),
        return_exceptions=True,
    )

    # Collect all jobs from all scrapers
    raw: list[dict] = []
    for batch in results:
        if isinstance(batch, Exception):
            print(f"[Scraper] batch error: {batch}")
            continue
        raw.extend(batch)

    print(f"[Scrapers] raw total before dedup: {len(raw)}")

    # ── Dedup by (title + company) fingerprint ─────────────────────────────
    # When duplicate: keep whichever source has higher priority (lower number)
    seen_fp:  dict[str, dict] = {}   # fp -> best job so far
    seen_url: set[str] = set()       # also dedupe exact URL matches

    for job in raw:
        url = job.get("url", "")
        if url and url in seen_url:
            continue  # exact URL duplicate

        fp = _fingerprint(job)
        src_priority = SOURCE_PRIORITY.get(job.get("source", ""), 99)

        if fp not in seen_fp:
            seen_fp[fp] = job
            if url:
                seen_url.add(url)
        else:
            existing_priority = SOURCE_PRIORITY.get(seen_fp[fp].get("source", ""), 99)
            if src_priority < existing_priority:
                # Current job is from a better source — replace
                old_url = seen_fp[fp].get("url", "")
                if old_url in seen_url:
                    seen_url.discard(old_url)
                seen_fp[fp] = job
                if url:
                    seen_url.add(url)

    all_jobs = list(seen_fp.values())

    # Count by source for logging
    from collections import Counter
    by_src = Counter(j.get("source", "?") for j in all_jobs)
    print(f"[Scrapers] after dedup: {len(all_jobs)} unique jobs")
    for src, n in by_src.most_common():
        print(f"  {src}: {n}")

    return all_jobs
