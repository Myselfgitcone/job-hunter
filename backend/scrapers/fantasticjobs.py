"""
Fantastic.jobs Feed API scraper.
https://data.fantastic.jobs/v1/active-ats
https://data.fantastic.jobs/v1/active-jb

Auth: Authorization: Bearer {API_KEY}
time_frame: 1h | 24h | 7d | 6m
Filters:  location, source, ai_work_arrangement
Pagination: offset

Trial limits: 500 jobs/week, 50 API requests/week
Rate guard: only fetches if > 6h since last call (saves trial budget)
"""
import os
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from scrapers.base import JobData, detect_country, is_relevant_title, CUTOFF_HOURS

API_KEY  = os.getenv("FANTASTIC_JOBS_API_KEY", "")
BASE_ATS = "https://data.fantastic.jobs/v1/active-ats"
BASE_JB  = "https://data.fantastic.jobs/v1/active-jb"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

# Rate guard — only one real API call every 6 hours (saves trial budget)
_last_fetch_ts: datetime | None = None
MIN_FETCH_INTERVAL_H = 6

# ATS sources we care about (skip irrelevant ones to save quota)
ALLOWED_SOURCES = {
    "greenhouse", "lever", "ashby", "workday", "adp", "bamboohr",
    "workable", "smartrecruiters", "icims", "taleo", "successfactors",
    "jobvite", "greenhouse", "recruitee", "pinpoint", "rippling",
    "personio", "jazz", "breezy", "polymer", "dover", "myworkday",
}

# Countries to fetch
LOCATIONS = ["United States", "India", "Remote"]


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
    # fallback to structured salary block
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
    parts = []
    req   = job.get("ai_requirements_summary") or ""
    resp  = job.get("ai_core_responsibilities") or ""
    skills = job.get("ai_key_skills") or []
    if req:
        parts.append(req)
    if resp:
        parts.append("**Responsibilities:** " + resp)
    if skills:
        parts.append("**Skills:** " + ", ".join(skills))
    return "\n\n".join(parts)


def _is_valid_date(date_str: str) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).days
        return 0 <= age <= CUTOFF_HOURS // 24 + 3  # small buffer
    except Exception:
        return False


async def _fetch_page(client: httpx.AsyncClient, endpoint: str, location: str, offset: int, limit: int = 50) -> list:
    params = {
        "time_frame": "24h",
        "limit": limit,
        "offset": offset,
    }
    if location != "Remote":
        params["location"] = location
    else:
        params["ai_work_arrangement"] = "Remote"
    try:
        r = await client.get(endpoint, params=params, timeout=30)
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


async def fetch(settings: dict) -> list[dict]:
    global _last_fetch_ts

    # Rate guard — skip if fetched recently (preserve trial budget)
    now = datetime.now(timezone.utc)
    if _last_fetch_ts and (now - _last_fetch_ts) < timedelta(hours=MIN_FETCH_INTERVAL_H):
        wait_min = int((timedelta(hours=MIN_FETCH_INTERVAL_H) - (now - _last_fetch_ts)).total_seconds() / 60)
        print(f"[FantasticJobs] Skipping — last fetch {int((now - _last_fetch_ts).total_seconds()/60)}min ago (next in ~{wait_min}min)")
        return []

    jobs: list[dict] = []
    seen: set[str]   = set()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        print(f"[FantasticJobs] Fetching... (trial budget: 500 jobs/week, 50 req/week)")

        for location in LOCATIONS:
            for offset in range(0, 101, 50):  # 2 pages × 50 = 100 jobs per location max
                hits = await _fetch_page(client, BASE_ATS, location, offset)
                if not hits:
                    break

                for job in hits:
                    url = job.get("url") or ""
                    if not url or url in seen:
                        continue

                    title = (job.get("title") or "").strip()
                    if not title or not is_relevant_title(title):
                        continue

                    countries = job.get("countries_derived") or []
                    arrangement = job.get("ai_work_arrangement") or ""
                    country = _map_country(countries, arrangement)
                    if country not in ("USA", "India", "Remote"):
                        # try from location string
                        locs = job.get("locations_derived") or []
                        loc_str = locs[0] if locs else ""
                        country = detect_country(loc_str, default="")
                        if country not in ("USA", "India", "Remote"):
                            if location == "Remote":
                                country = "Remote"
                            else:
                                continue

                    # Real ISO date from Fantastic.jobs (no more "34min ago" for old jobs)
                    posted_at = ""
                    raw_date  = job.get("date_posted") or ""
                    if raw_date:
                        try:
                            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            age_days = (now - dt).days
                            if 0 <= age_days <= 30:  # accept up to 30 days (FJ data reliable)
                                posted_at = dt.isoformat()
                        except Exception:
                            pass

                    locs_derived = job.get("locations_derived") or []
                    location_str = locs_derived[0] if locs_derived else ""

                    salary = _fmt_salary(job)
                    remote = "remote" in arrangement.lower()
                    description = _build_description(job)

                    company = (job.get("organization") or "").strip()
                    if not company:
                        continue

                    source_ats = job.get("source") or "unknown"

                    seen.add(url)
                    jobs.append(JobData(
                        title=title,
                        company=company,
                        url=url,
                        source=f"FantasticJobs",
                        description=description,
                        location=location_str,
                        country=country,
                        salary=salary,
                        remote=remote,
                        posted_at=posted_at,
                    ).to_dict())

                if len(hits) < 50:
                    break  # last page
                await asyncio.sleep(0.5)

    _last_fetch_ts = now
    print(f"[FantasticJobs] {len(jobs)} jobs (US+India+Remote, ATS only)")
    return jobs
