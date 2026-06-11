"""
Fantastic.jobs Feed API scraper.
https://data.fantastic.jobs/v1/active-ats

Auth: Authorization: Bearer {API_KEY}
time_frame: 1h | 24h | 7d | 6m
Filters:  title_advanced (boolean: |/&/!), location_advanced, limit/offset

Paid plan target: $175/mo (≤50K jobs/mo).
Rate guard: 6h minimum between fetches.

Description priority:
  1. `description_html` field from API (paid plan feature)
  2. AI-extracted fields: ai_requirements_summary + ai_core_responsibilities + ai_key_skills (absolute fallback)
"""
import os
import json
import asyncio
from datetime import datetime, timezone, timedelta

import httpx

from scrapers.base import JobData, detect_country, is_relevant_title, CUTOFF_HOURS

BASE_ATS = "https://data.fantastic.jobs/v1/active-ats"

LOCATIONS = ["United States", "India"]

_last_fetch_ts: datetime | None = None
MIN_FETCH_INTERVAL_H = 1


# Boolean title filter — 5 roles, US+India
TITLE_FILTER = (
    "(devops | sre | 'site reliability' | 'platform engineer'"
    " | 'data engineer' | etl"
    " | 'data analyst' | 'data analytics'"
    " | 'security engineer' | 'security analyst' | 'soc analyst'"
    " | cybersecurity | infosec | 'application security'"
    " | 'business intelligence' | 'bi developer' | 'bi analyst' | 'power bi'"
    " | 'java developer' | 'java software engineer' | 'backend java' | 'java engineer')"
    " & !(financial | marketing | sales | nurse)"
)


_EMP_TYPE_MAP = {
    "FULL_TIME": "Full-time", "PART_TIME": "Part-time",
    "CONTRACT":  "Contract",  "INTERN":    "Internship",
    "PER_DIEM":  "Per Diem",  "TEMPORARY": "Temporary",
    "VOLUNTEER": "Volunteer", "OTHER":     "Other",
}


def _get_headers() -> dict:
    key = os.getenv("FANTASTIC_JOBS_API_KEY", "")
    if not key:
        raise RuntimeError("FANTASTIC_JOBS_API_KEY env var not set")
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def _fmt_salary(job: dict) -> str:
    try:
        mn = float(job.get("ai_salary_min_value")) if job.get("ai_salary_min_value") else None
        mx = float(job.get("ai_salary_max_value")) if job.get("ai_salary_max_value") else None
    except ValueError:
        mn, mx = None, None

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
        try:
            lo = float(v.get("minValue")) if v.get("minValue") else None
            hi = float(v.get("maxValue")) if v.get("maxValue") else None
            if lo and hi: return f"${int(lo/1000)}k–${int(hi/1000)}k"
        except ValueError:
            pass
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
      1. Full HTML JD from API (description_format=html → stored in `description` key;
         paid plan may also expose `description_html` — check both)
      2. AI-extracted fields as minimal fallback
    """
    html = job.get("description_html") or job.get("description") or ""
    if html and len(html.strip()) >= 100:
        return html[:25000]

    # AI-extracted fallback
    parts = []
    req    = job.get("ai_requirements_summary") or ""
    resp   = job.get("ai_core_responsibilities") or ""
    skills = job.get("ai_key_skills") or []
    if req:
        parts.append(req)
    if resp:
        parts.append("**Responsibilities:** " + resp)
    if skills:
        parts.append("**Skills:** " + ", ".join(skills))
    return "\n\n".join(parts).strip()


async def _fetch_page(client: httpx.AsyncClient, location: str, offset: int = 0) -> list:
    params = {
        "time_frame": "24h",
        "limit": 50,
        "offset": offset,
        "title_advanced": TITLE_FILTER,
        "location_advanced": f"'{location}'" if " " in location else location,
        "description_format": "html",
        "include_basic_organization_details": "true",
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

    _last_fetch_ts = now  # record BEFORE fetch so concurrent calls skip

    jobs: list[dict] = []
    seen: set[str]   = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        print(f"[FantasticJobs] Fetching (USA + India, title filter, desc+logo included)...")

        PAGE_SIZE = 50
        MAX_PAGES = 30  # safety cap: 30 × 50 = 1,500 jobs per location max

        for location in LOCATIONS:
            offset      = 0
            total_raw   = 0
            kept        = 0

            for page in range(MAX_PAGES):
                hits = await _fetch_page(client, location, offset=offset)
                if not hits:
                    break

                total_raw += len(hits)

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

                    # ── FJ enrichment ─────────────────────────────────────
                    visa_sponsorship = job.get("ai_visa_sponsorship")  # bool|None

                    emp_raw = job.get("ai_employment_type") or []
                    emp_code = emp_raw[0] if emp_raw else ""
                    employment_type = _EMP_TYPE_MAP.get(emp_code, emp_code)

                    benefits_list = job.get("ai_benefits") or []
                    benefits = json.dumps(benefits_list) if benefits_list else ""

                    keywords_list = job.get("ai_keywords") or []
                    ai_keywords = json.dumps(keywords_list) if keywords_list else ""

                    funding_raw = job.get("org_crunchbase_total_investment")
                    try:
                        company_funding = int(funding_raw) if funding_raw is not None else None
                    except (TypeError, ValueError):
                        company_funding = None

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
                        fj_id=job.get("id"),
                        visa_sponsorship=visa_sponsorship,
                        experience_level=job.get("ai_experience_level") or "",
                        employment_type=employment_type,
                        benefits=benefits,
                        job_expiry=job.get("date_valid_through") or "",
                        logo_url=job.get("org_logo_permalink") or "",
                        company_size=job.get("org_linkedin_size") or "",
                        company_industry=job.get("org_linkedin_industry") or "",
                        company_hq=job.get("org_linkedin_headquarters") or "",
                        company_funding=company_funding,
                        ai_keywords=ai_keywords,
                    ).to_dict())

                if len(hits) < PAGE_SIZE:
                    break  # last page — no more results
                offset += PAGE_SIZE
                await asyncio.sleep(0.4)  # polite pause between pages

            print(f"[FantasticJobs] {location}: {total_raw} raw ({page+1} pages) → {kept} kept")

    desc_ok  = sum(1 for j in jobs if j.get("description"))
    desc_nil = len(jobs) - desc_ok
    print(f"[FantasticJobs] Done — {len(jobs)} jobs | desc OK: {desc_ok} | still null: {desc_nil}")
    return jobs

async def sync_expired_jobs(settings: dict) -> int:
    """Fetch expired jobs from the last day and mark them closed in the database."""
    print("[FantasticJobs] Fetching expired jobs feed for the last 1d...")
    try:
        headers = _get_headers()
    except RuntimeError as e:
        print(f"[FantasticJobs] {e} — skipping expired sync")
        return 0

    url = "https://data.fantastic.jobs/v1/expired-ats"
    params = {"time_frame": "1d"}
    
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            expired_ids = r.json()
            if not expired_ids or not isinstance(expired_ids, list):
                print("[FantasticJobs] No expired jobs returned.")
                return 0
                
            from database import mark_expired_jobs_closed
            closed_count = await mark_expired_jobs_closed(expired_ids)
            print(f"[FantasticJobs] Marked {closed_count} jobs as closed from the 1d expired feed.")
            return closed_count
        except Exception as e:
            print(f"[FantasticJobs] Error fetching expired jobs: {e}")
            return 0
