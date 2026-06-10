"""
Fantastic.jobs Feed API scraper — Data jobs only (budget-optimised).
https://data.fantastic.jobs/v1/active-ats

Auth: Authorization: Bearer {API_KEY}
time_frame: 1h | 24h | 7d | 6m
Filters:  location, source, ai_work_arrangement
Pagination: offset

Trial limits: 500 jobs/week, 50 API requests/week
Budget plan: USA + India only, 1 page each = 2 requests/scrape
Rate guard: 6h minimum between fetches
"""
import os
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from scrapers.base import JobData, detect_country, is_relevant_title, CUTOFF_HOURS

BASE_ATS = "https://data.fantastic.jobs/v1/active-ats"

# Only USA + India — 1 request each = 2 API calls per scrape
LOCATIONS = ["United States", "India"]

# Rate guard
_last_fetch_ts: datetime | None = None
MIN_FETCH_INTERVAL_H = 6


# ── Data-job title filter ─────────────────────────────────────────────────────
_DATA_KEYWORDS = {
    "data engineer", "data engineering",
    "analytics engineer",
    "data architect",
    "data platform",
    "data infrastructure",
    "data pipeline",
    "etl", "elt",
    "data warehouse",
    "data lake",
    "data ops", "dataops",
    "data integration",
    "bi engineer", "bi developer", "business intelligence",
    "ml engineer", "machine learning engineer",
    "mlops", "ml ops",
    "ai engineer",
    "data scientist",        # close enough to data eng roles
    "data analyst",          # include — user group is 4 people
    "analytics",
    "dbt", "spark", "airflow", "kafka", "snowflake", "databricks",
}

def _is_data_job(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in _DATA_KEYWORDS)


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
    return "\n\n".join(parts)


async def _fetch_page(client: httpx.AsyncClient, location: str) -> list:
    """Single page, 50 jobs, 7-day window — 1 API request."""
    params = {
        "time_frame": "7d",   # 7-day window → more variety per request
        "limit": 50,
        "offset": 0,
        "location": location,
    }
    try:
        r = await client.get(BASE_ATS, params=params, timeout=30)
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

    now = datetime.now(timezone.utc)

    # Rate guard
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
        print(f"[FantasticJobs] Fetching data jobs (USA + India, 1 page each = 2 API requests)...")

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
                if not title:
                    continue

                # Strict data-job filter (saves quota — skip irrelevant titles early)
                if not _is_data_job(title):
                    continue

                # General title sanity (blocks school intern, etc.)
                if not is_relevant_title(title):
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

                # Date
                posted_at = ""
                raw_date  = job.get("date_posted") or ""
                if raw_date:
                    try:
                        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        age_days = (now - dt).days
                        if 0 <= age_days <= 30:
                            posted_at = dt.isoformat()
                    except Exception:
                        pass

                locs_derived = job.get("locations_derived") or []
                location_str = locs_derived[0] if locs_derived else ""

                seen.add(url)
                kept += 1
                jobs.append(JobData(
                    title=title,
                    company=company,
                    url=url,
                    source="FantasticJobs",
                    description=_build_description(job),
                    location=location_str,
                    country=country,
                    salary=_fmt_salary(job),
                    remote="remote" in arrangement.lower(),
                    posted_at=posted_at,
                ).to_dict())

            print(f"[FantasticJobs] {location}: {len(hits)} total → {kept} data jobs kept")
            await asyncio.sleep(0.3)

    _last_fetch_ts = now
    print(f"[FantasticJobs] Done — {len(jobs)} data jobs (USA+India)")
    return jobs
