"""
Fantastic.jobs Feed API scraper.
https://data.fantastic.jobs/v1/active-ats

Auth: Authorization: Bearer {API_KEY}
time_frame: 1h | 24h | 7d | 6m
Filters:  title_advanced (boolean: |/&/!), location_advanced, limit/offset

Paid plan target: $175/mo (≤50K jobs/mo).
Rate guard: 6h minimum between fetches.

Description priority:
  1. Raw `description` field from API (requested via description_format=text)
  2. AI-extracted fields: ai_requirements_summary + ai_core_responsibilities + ai_key_skills
  3. jd_fetcher.fetch_full_jd(url)  ← fallback for null-desc jobs only
"""
import os
import asyncio
from datetime import datetime, timezone, timedelta

import httpx

from scrapers.base import JobData, detect_country, is_relevant_title, CUTOFF_HOURS

BASE_ATS = "https://data.fantastic.jobs/v1/active-ats"

# USA + India, 1 page each = 2 API requests per scrape
LOCATIONS = ["United States", "India"]

_last_fetch_ts: datetime | None = None
MIN_FETCH_INTERVAL_H = 6

# Max concurrent jd_fetcher calls for null-description jobs
_JD_FALLBACK_CONCURRENCY = 5

# Boolean title filter — 5 roles, US+India
TITLE_FILTER = (
    "(devops | sre | 'site reliability' | 'platform engineer'"
    " | 'data engineer' | etl"
    " | 'data analyst' | 'data analytics'"
    " | 'security engineer' | 'security analyst' | 'soc analyst'"
    " | cybersecurity | infosec | 'application security'"
    " | 'business intelligence' | 'bi developer' | 'bi analyst' | 'power bi')"
    " & !(financial | marketing | sales | nurse)"
)


def _get_headers() -> dict:
    key = os.getenv("FANTASTIC_JOBS_API_KEY", "")
    if not key:
        raise RuntimeError("FANTASTIC_JOBS_API_KEY env var not set")
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def _fmt_salary(job: dict) -> str:
    mn   = job.get("ai_salary_min_value")
    mx   = job.get("ai_salary_max_value")
    curr = (job.get("ai_salary_currency") or "USD").upper()
    unit = (job.get("ai_salary_unit_text") or "").upper()
    sym  = "$" if curr == "USD" else f"{curr} "
    if unit == "HOUR":
        if mn and mx: return f"{sym}{mn:.0f}–{mx:.0f}/hr"
        if mn:        return f"{sym}{mn:.0f}+/hr"
    else:
        if mn and mx: return f"{sym}{int(mn/1000)}k–{int(mx/1000)}k"
        if mn:        return f"{sym}{int(mn/1000)}k+"
    sal = job.get("salary")
    if sal:
        v = (sal.get("value") or {})
        lo = v.get("minValue"); hi = v.get("maxValue")
        if lo and hi: return f"${int(lo/1000)}k–${int(hi/1000)}k"
    return ""


def _map_country(countries: list, arrangement: str) -> str:
    arr = (arrangement or "").lower()
    if "remote" in arr:
        return "Remote"
    if not countries:
        return ""
    c = countries[0].lower()
    if "united states" in c or "usa" in c:
        return "USA"
    if "india" in c:
        return "India"
    return ""


def _build_description(job: dict) -> str:
    """
    Priority:
      1. Raw description field (requested via description_format=text)
      2. AI-extracted fields
    Returns "" if nothing useful — caller will trigger jd_fetcher fallback.
    """
    # 1. Raw description from API
    raw = job.get("description") or ""
    if isinstance(raw, str) and len(raw.strip()) >= 80:
        return raw.strip()[:8000]

    # 2. AI-extracted fields
    parts  = []
    req    = job.get("ai_requirements_summary") or ""
    resp   = job.get("ai_core_responsibilities") or ""
    skills = job.get("ai_key_skills") or []
    if req:
        parts.append(req)
    if resp:
        parts.append("**Responsibilities:** " + resp)
    if skills:
        parts.append("**Skills:** " + ", ".join(skills))
    result = "\n\n".join(parts).strip()
    return result if len(result) >= 80 else ""


async def _fetch_page(client: httpx.AsyncClient, location: str, offset: int = 0) -> list:
    params = {
        "time_frame": "24h",
        "limit": 50,
        "offset": offset,
        "title_advanced": TITLE_FILTER,        # boolean role filter
        "location_advanced": f"'{location}'" if " " in location else location,
        "description_format": "text",          # request raw description
        "include_basic_organization_details": "true",  # org logo etc.
    }
    try:
        r = await client.get(BASE_ATS, params=params, timeout=30)
        if r.status_code == 403:
            detail = r.json().get("detail", "")
            print(f"[FantasticJobs] 403 {location}: {detail}")
            return []
        if r.status_code == 429:
            print("[FantasticJobs] Rate limited (429) — skipping")
            return []
        if r.status_code != 200:
            print(f"[FantasticJobs] HTTP {r.status_code} for {location}: {r.text[:200]}")
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[FantasticJobs] fetch error {location}: {e}")
        return []


async def _fill_descriptions(null_jobs: list[dict]) -> None:
    """
    For jobs with no description, fetch from ATS URL using jd_fetcher.
    Mutates the dicts in-place. Capped concurrency to avoid hammering ATS sites.
    """
    if not null_jobs:
        return
    try:
        from jd_fetcher import fetch_full_jd
    except ImportError:
        return

    sem = asyncio.Semaphore(_JD_FALLBACK_CONCURRENCY)
    fetched = 0

    async def _one(job: dict) -> None:
        nonlocal fetched
        async with sem:
            url = job.get("url", "")
            if not url:
                return
            try:
                result = await fetch_full_jd(url)
                desc = (result or {}).get("description", "")
                if desc and len(desc) >= 80:
                    job["description"] = desc
                    fetched += 1
            except Exception as e:
                pass  # silently skip — description just stays empty

    await asyncio.gather(*[_one(j) for j in null_jobs])
    print(f"[FantasticJobs] jd_fetcher filled {fetched}/{len(null_jobs)} null descriptions")


async def fetch(settings: dict) -> list[dict]:
    global _last_fetch_ts

    now = datetime.now(timezone.utc)

    if _last_fetch_ts and (now - _last_fetch_ts) < timedelta(hours=MIN_FETCH_INTERVAL_H):
        wait_min = int(
            (timedelta(hours=MIN_FETCH_INTERVAL_H) - (now - _last_fetch_ts)).total_seconds() / 60
        )
        print(f"[FantasticJobs] Skipping — next fetch in ~{wait_min}min")
        return []

    try:
        headers = _get_headers()
    except RuntimeError as e:
        print(f"[FantasticJobs] {e} — skipping")
        return []

    jobs: list[dict] = []
    seen: set[str]   = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        print(f"[FantasticJobs] Fetching (USA + India, title filter, desc+logo included)...")

        for location in LOCATIONS:
            hits = await _fetch_page(client, location)
            if not hits:
                continue

            kept = 0
            for job in hits:
                url = job.get("url") or ""
                if not url or url in seen:
                    continue

                title = (job.get("title") or "").strip()
                if not title or not is_relevant_title(title):
                    continue

                company = (job.get("organization") or "").strip()
                if not company:
                    continue

                countries   = job.get("countries_derived") or []
                arrangement = job.get("ai_work_arrangement") or ""
                country     = _map_country(countries, arrangement)
                if country not in ("USA", "India", "Remote"):
                    locs    = job.get("locations_derived") or []
                    loc_str = locs[0] if locs else ""
                    country = detect_country(loc_str, default="")
                    if country not in ("USA", "India", "Remote"):
                        continue

                posted_at = ""
                raw_date  = job.get("date_posted") or ""
                if raw_date:
                    try:
                        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if 0 <= (now - dt).days <= 30:
                            posted_at = dt.isoformat()
                    except Exception:
                        pass

                locs_derived = job.get("locations_derived") or []
                location_str = locs_derived[0] if locs_derived else ""

                # Logo from organization details
                logo_url = (job.get("org_logo_permalink") or "")

                seen.add(url)
                kept += 1

                # Build description (raw → AI fields → empty for now; fallback below)
                description = _build_description(job)

                jobs.append(JobData(
                    title=title,
                    company=company,
                    url=url,
                    source="FantasticJobs",
                    description=description,
                    location=location_str,
                    country=country,
                    salary=_fmt_salary(job),
                    remote="remote" in arrangement.lower(),
                    posted_at=posted_at,
                ).to_dict())

            print(f"[FantasticJobs] {location}: {len(hits)} raw → {kept} kept")
            await asyncio.sleep(0.3)

    # jd_fetcher fallback for jobs that have no description yet
    null_desc_jobs = [j for j in jobs if not j.get("description")]
    if null_desc_jobs:
        print(f"[FantasticJobs] {len(null_desc_jobs)} jobs need description fallback...")
        await _fill_descriptions(null_desc_jobs)

    desc_ok  = sum(1 for j in jobs if j.get("description"))
    desc_nil = len(jobs) - desc_ok
    print(f"[FantasticJobs] Done — {len(jobs)} jobs | desc OK: {desc_ok} | still null: {desc_nil}")
    return jobs
