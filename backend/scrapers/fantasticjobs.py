"""
Fantastic.jobs Feed API scraper.

Endpoints used:
  /v1/active-ats    — new ATS jobs (hourly)
  /v1/active-jb     — new job-board jobs (hourly, same title filter)
  /v1/modified-ats  — updated ATS jobs — refreshes desc/salary in DB (every 6h)
  /v1/expired-ats   — expired ATS jobs — marks closed (daily midnight)
  /v1/expired-jb    — expired job-board jobs — marks closed (daily midnight)

Auth: Authorization: Bearer {FANTASTIC_JOBS_API_KEY}
Paid plan $175/mo: 50K jobs/mo, 25K requests/mo, description_html field.
"""
import os
import json
import asyncio
from datetime import datetime, timezone, timedelta

import httpx

from scrapers.base import JobData, detect_country, is_relevant_title, CUTOFF_HOURS

# ── Endpoint URLs ─────────────────────────────────────────────────────────────
BASE_ATS        = "https://data.fantastic.jobs/v1/active-ats"
BASE_JB         = "https://data.fantastic.jobs/v1/active-jb"
BASE_MODIFIED   = "https://data.fantastic.jobs/v1/modified-ats"
BASE_EXPIRED_ATS = "https://data.fantastic.jobs/v1/expired-ats"
BASE_EXPIRED_JB  = "https://data.fantastic.jobs/v1/expired-jb"

# ATS feed: direct career pages (Greenhouse, Lever, Workday, etc.) — both USA + India
# JB feed: job board aggregator (LinkedIn, Indeed, etc.)
#   USA: ATS-only — Western ATS platforms cover USA well; JB = LinkedIn reposts
#   India: ATS + JB — many Indian companies post on LinkedIn only, ATS coverage is thin
ACTIVE_FEEDS = [BASE_ATS, BASE_JB]
LOCATIONS_FOR_JB = {"India"}  # only run JB feed for these locations

LOCATIONS = ["United States", "India"]

# Pagination constants (module-level so fetch_modified can use them)
PAGE_SIZE = 100   # FJ recommends 100-1000; bigger pages = fewer request credits
MAX_PAGES = 200   # safety cap only; natural break = last page < PAGE_SIZE

# Credit guard: count endpoints are FREE (request credits only). We pre-check
# expected volume per feed+location; anything above the cap means a filter
# regression or window bug — skip rather than bill thousands of job credits.
# Caps scale with the window: hourly runs see <200 jobs in practice (500 is
# generous); a 24h catch-up after downtime can legitimately reach a few K.
MAX_EXPECTED_BY_WINDOW = {"1h": 500, "24h": 3000}

# Rate guards
_last_fetch_ts: datetime | None = None
_last_modified_ts: datetime | None = None
MIN_FETCH_INTERVAL_H    = 1
MIN_MODIFIED_INTERVAL_H = 6


# Boolean title filter — USA + India
# Java: one broad expression catches all "java *" titles; !javascript avoids false positives.
# 'spring boot' and jakarta cover Java jobs where "java" doesn't appear in the title.
# 'data platform' catches Data Platform Engineer (missed by 'data engineer' alone).
# Exec/arch exclusions: never billed, never stored — saves credits globally.
# Common families: Data Engineer, Data Analyst, BI (scraped for ALL countries)
# DevOps/SRE + Security disabled — re-add their terms here to re-enable:
#   devops | sre | 'site reliability' | 'platform engineer'
#   'security engineer' | 'security analyst' | 'soc analyst' | cybersecurity | infosec | 'application security'
_TERMS_COMMON = (
    "'data engineer' | etl | 'data platform'"
    " | 'data analyst' | 'data analytics' | 'analytics engineer' | 'reporting analyst'"
    " | 'business intelligence' | 'bi developer' | 'bi analyst' | 'power bi' | tableau"
)
# Java family — USA only (India team doesn't hunt Java roles)
_TERMS_JAVA = "(java & !javascript) | 'spring boot' | jakarta"

_GLOBAL_NOT = (
    " & !(financial | marketing | sales | nurse"
    " | director | 'vice president' | vp | cto | chief | architect)"
)

TITLE_FILTER_USA   = f"({_TERMS_COMMON} | {_TERMS_JAVA})" + _GLOBAL_NOT
TITLE_FILTER_INDIA = f"({_TERMS_COMMON})" + _GLOBAL_NOT
# Default (modified-ats sync etc.) — widest filter
TITLE_FILTER = TITLE_FILTER_USA

def title_filter_for(location: str) -> str:
    return TITLE_FILTER_INDIA if location == "India" else TITLE_FILTER_USA


_EMP_TYPE_MAP = {
    "FULL_TIME": "Full-time", "PART_TIME": "Part-time",
    "CONTRACT":  "Contract",  "INTERN":    "Internship",
    "PER_DIEM":  "Per Diem",  "TEMPORARY": "Temporary",
    "VOLUNTEER": "Volunteer", "OTHER":     "Other",
}


_JB_SOURCE_MAP = {
    "linkedin.com":   "LinkedIn",
    "indeed.com":     "Indeed",
    "glassdoor.com":  "Glassdoor",
    "ziprecruiter.":  "ZipRecruiter",
    "monster.com":    "Monster",
    "simplyhired.":   "SimplyHired",
    "careerbuilder.": "CareerBuilder",
    "dice.com":       "Dice",
    "jooble.":        "Jooble",
    "lensa.com":      "Lensa",
}

# Staffing/repost aggregator "companies" — they relist other employers' jobs
_JUNK_COMPANIES = (
    "jobs via dice", "hire feed", "lensa", "talentify", "jobgether",
    "get it recruit", "jobot", "actalent staffing", "jobs via",
)

# NOTE: organization_advanced is intentionally NOT sent — the FJ API consistently
# returns 400 for this parameter, wasting a retry call per page. The Python
# _JUNK_COMPANIES check below serves as the backstop filter instead.
# ORG_EXCLUDE_FILTER kept here for reference if the API ever supports it:
# ORG_EXCLUDE_FILTER = "!('jobs via dice' | 'hire feed' | lensa | talentify | jobgether | 'get it recruit' | jobot)"

def _detect_jb_source(url: str) -> str:
    """Detect the actual job board from URL for JB feed jobs."""
    lower = url.lower()
    for domain, label in _JB_SOURCE_MAP.items():
        if domain in lower:
            return label
    return "FantasticJobs"


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
    # NOTE: remote is a work arrangement, NOT a country. The remote flag is
    # carried separately on JobData.remote — country must stay the real one,
    # otherwise remote USA jobs dodge USA-only policies (e.g. the LinkedIn
    # repost guard) and pollute the country filter.
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


def _extract_enrichment(job: dict) -> dict:
    """Extract all FJ enrichment fields from a raw job dict. Shared by fetch + fetch_modified."""
    emp_raw  = job.get("ai_employment_type") or []
    emp_code = emp_raw[0] if emp_raw else ""

    benefits_list = job.get("ai_benefits") or []
    keywords_list = job.get("ai_keywords") or []

    funding_raw = job.get("org_crunchbase_total_investment")
    try:
        company_funding = int(funding_raw) if funding_raw is not None else None
    except (TypeError, ValueError):
        company_funding = None

    return {
        "visa_sponsorship":  job.get("ai_visa_sponsorship"),
        "experience_level":  job.get("ai_experience_level") or "",
        "employment_type":   _EMP_TYPE_MAP.get(emp_code, emp_code),
        "benefits":          json.dumps(benefits_list) if benefits_list else "",
        "job_expiry":        job.get("date_valid_through") or "",
        "logo_url":          job.get("org_logo_permalink") or "",
        "company_size":      job.get("org_linkedin_size") or "",
        "company_industry":  job.get("org_linkedin_industry") or "",
        "company_hq":        job.get("org_linkedin_headquarters") or "",
        "company_funding":   company_funding,
        "ai_keywords":       json.dumps(keywords_list) if keywords_list else "",
    }


async def _fetch_page(
    client: httpx.AsyncClient,
    location: str,
    offset: int = 0,
    base_url: str = BASE_ATS,
    include_org_details: bool = True,
    time_frame: str | None = "24h",
) -> list:
    params: dict = {
        "limit": PAGE_SIZE,
        "offset": offset,
        "title_advanced": title_filter_for(location),
        "location_advanced": f"'{location}'" if " " in location else location,
        "description_format": "html",
    }
    # time_frame is supported by active/JB feeds but NOT by modified-ats
    if time_frame is not None:
        params["time_frame"] = time_frame
    # ATS-only param — job board and modified endpoints reject it
    if include_org_details:
        params["include_basic_organization_details"] = "true"
    try:
        r = await client.get(base_url, params=params, timeout=30)
        if r.status_code == 403:
            print(f"[FantasticJobs] 403 {base_url.split('/')[-1]} {location}: {r.json().get('detail','')}")
            return []
        if r.status_code == 429:
            print(f"[FantasticJobs] Rate limited (429) on {base_url.split('/')[-1]}")
            return []
        if r.status_code != 200:
            print(f"[FantasticJobs] HTTP {r.status_code} {base_url.split('/')[-1]} {location}: {r.text[:200]}")
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[FantasticJobs] fetch error {base_url.split('/')[-1]} {location}: {e}")
        return []


async def _fetch_expected_count(client: httpx.AsyncClient, location: str,
                                base_url: str, time_frame: str) -> int | None:
    """Pre-flight volume check via the free *-count endpoint (request credits
    only, zero job credits). Returns None if the endpoint is unavailable."""
    params = {
        "time_frame": time_frame,
        "title_advanced": title_filter_for(location),
        "location_advanced": f"'{location}'" if " " in location else location,
    }
    try:
        r = await client.get(base_url + "-count", params=params, timeout=30)
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, (int, float)):
            return int(data)
        if isinstance(data, dict):
            for k in ("count", "total", "jobs", "result"):
                if k in data:
                    return int(data[k])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            vals = list(data[0].values())
            if vals:
                return int(vals[0])
    except Exception as e:
        print(f"[FantasticJobs] count check failed for {location}: {e}")
    return None


async def fetch(settings: dict) -> list[dict]:
    """Fetch new jobs from ATS + job-board feeds. Called every hour."""
    global _last_fetch_ts

    now = datetime.now(timezone.utc)

    # Restore last-fetch time from DB after a restart — otherwise every
    # redeploy triggers a 24h catch-up window and re-bills a day of jobs
    if _last_fetch_ts is None:
        try:
            from database import SessionLocal, Setting
            async with SessionLocal() as db:
                row = await db.get(Setting, "fj_last_fetch")
            if row and row.value:
                _last_fetch_ts = datetime.fromisoformat(row.value)
        except Exception as e:
            print(f"[FantasticJobs] last-fetch restore failed: {e}")

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

    # Credits are billed PER JOB RETURNED — hourly runs must use the 1h window
    # or every job gets re-fetched (and re-billed) up to 24 times a day.
    # 24h window only for catch-up (first run after restart / missed cycles).
    prev_fetch_ts = _last_fetch_ts
    time_frame = "1h" if prev_fetch_ts and (now - prev_fetch_ts) <= timedelta(hours=2) else "24h"
    print(f"[FantasticJobs] time_frame={time_frame} (last fetch: {prev_fetch_ts or 'never this boot'})")

    _last_fetch_ts = now  # record BEFORE fetch so concurrent calls skip
    try:
        from database import SessionLocal, Setting
        async with SessionLocal() as db:
            row = await db.get(Setting, "fj_last_fetch")
            if row:
                row.value = now.isoformat()
            else:
                db.add(Setting(key="fj_last_fetch", value=now.isoformat()))
            await db.commit()
    except Exception as e:
        print(f"[FantasticJobs] last-fetch persist failed: {e}")

    jobs: list[dict] = []
    seen: set[str]   = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for feed_url in ACTIVE_FEEDS:
            feed_label  = "ATS" if feed_url == BASE_ATS else "JobBoard"
            org_details = feed_url == BASE_ATS  # only ATS supports include_basic_organization_details
            locations_label = "+".join(LOCATIONS) if feed_url == BASE_ATS else "+".join(LOCATIONS_FOR_JB)
            print(f"[FantasticJobs/{feed_label}] Fetching {locations_label} with title filter...")

            for location in LOCATIONS:
                # JB feed only runs for India — USA ATS coverage is strong, JB = LinkedIn reposts
                if feed_url == BASE_JB and location not in LOCATIONS_FOR_JB:
                    continue

                # Credit guard: free pre-flight count before paying per job
                expected = await _fetch_expected_count(client, location, feed_url, time_frame)
                if expected is not None:
                    cap = MAX_EXPECTED_BY_WINDOW.get(time_frame, 500)
                    print(f"[FantasticJobs/{feed_label}] {location}: ~{expected} jobs expected ({time_frame}, cap {cap})")
                    if expected == 0:
                        continue  # nothing new — skip pagination entirely
                    if expected > cap:
                        print(f"[FantasticJobs/{feed_label}] {location}: {expected} > safety cap "
                              f"{cap} — SKIPPING to protect job credits "
                              f"(check TITLE_FILTER / time_frame for regressions)")
                        continue

                offset    = 0
                total_raw = 0
                kept      = 0

                for page in range(MAX_PAGES):
                    hits = await _fetch_page(client, location, offset=offset, base_url=feed_url, include_org_details=org_details, time_frame=time_frame)
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

                        # ATS uses "organization"; job board may use "company" or "organization"
                        company = (job.get("organization") or job.get("company") or "").strip()
                        if not company:
                            continue
                        # Staffing/repost aggregator accounts — never real employers
                        if any(b in company.lower() for b in _JUNK_COMPANIES):
                            continue

                        countries   = job.get("countries_derived") or []
                        arrangement = job.get("ai_work_arrangement") or ""
                        country     = _map_country(countries, arrangement)
                        if country not in ("USA", "India"):
                            locs    = job.get("locations_derived") or []
                            loc_str = locs[0] if locs else ""
                            country = detect_country(loc_str, default="")
                            if country not in ("USA", "India"):
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

                        enrich = _extract_enrichment(job)

                        # Detect actual hosting board by URL — the ATS feed also
                        # contains LinkedIn-hosted listings for companies w/o an ATS
                        job_source = _detect_jb_source(url)
                        # USA policy: direct career pages only — board-hosted posts
                        # (LinkedIn/Indeed/Dice) are reposts. India keeps them (thin ATS coverage).
                        if job_source != "FantasticJobs" and country == "USA":
                            continue

                        seen.add(url)
                        kept += 1

                        jobs.append(JobData(
                            title=title,
                            company=company,
                            url=url,
                            source=job_source,
                            description=_build_description(job),
                            location=location_str,
                            country=country,
                            salary=_fmt_salary(job),
                            remote="remote" in arrangement.lower(),
                            posted_at=posted_at,
                            fj_id=job.get("id"),
                            visa_sponsorship=enrich["visa_sponsorship"],
                            experience_level=enrich["experience_level"],
                            employment_type=enrich["employment_type"],
                            benefits=enrich["benefits"],
                            job_expiry=enrich["job_expiry"],
                            logo_url=enrich["logo_url"],
                            company_size=enrich["company_size"],
                            company_industry=enrich["company_industry"],
                            company_hq=enrich["company_hq"],
                            company_funding=enrich["company_funding"],
                            ai_keywords=enrich["ai_keywords"],
                        ).to_dict())

                    if len(hits) < PAGE_SIZE:
                        break  # last page
                    offset += PAGE_SIZE
                    await asyncio.sleep(0.4)  # polite pause between pages

                print(f"[FantasticJobs/{feed_label}] {location}: {total_raw} raw ({page+1} pages) → {kept} kept")

    desc_ok  = sum(1 for j in jobs if j.get("description"))
    desc_nil = len(jobs) - desc_ok
    print(f"[FantasticJobs] Done — {len(jobs)} total | desc OK: {desc_ok} | still null: {desc_nil}")
    return jobs


async def fetch_modified(settings: dict) -> list[dict]:
    """
    Fetch ATS jobs modified in last 24h and return update dicts for existing DB records.
    Called every 6 hours. Does NOT insert new jobs — only updates existing ones.
    """
    global _last_modified_ts

    now = datetime.now(timezone.utc)

    if _last_modified_ts and (now - _last_modified_ts) < timedelta(hours=MIN_MODIFIED_INTERVAL_H):
        print("[FantasticJobs/Modified] Skipping — ran recently")
        return []

    try:
        headers = _get_headers()
    except RuntimeError as e:
        print(f"[FantasticJobs/Modified] {e} — skipping")
        return []

    _last_modified_ts = now

    updates: list[dict] = []
    seen: set[str]      = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        print("[FantasticJobs/Modified] Fetching modified ATS jobs (24h)...")

        for location in LOCATIONS:
            offset = 0

            for page in range(MAX_PAGES):
                # modified-ats does NOT support time_frame — omit it
                hits = await _fetch_page(client, location, offset=offset, base_url=BASE_MODIFIED, include_org_details=False, time_frame=None)
                if not hits:
                    break

                for job in hits:
                    url = job.get("url") or ""
                    if not url or url in seen:
                        continue
                    seen.add(url)

                    enrich = _extract_enrichment(job)
                    desc   = _build_description(job)
                    salary = _fmt_salary(job)

                    updates.append({
                        "fj_id":             job.get("id"),
                        "url":               url,
                        # Only overwrite if FJ gave us a value
                        "description":       desc   if desc   else None,
                        "salary":            salary if salary else None,
                        "visa_sponsorship":  enrich["visa_sponsorship"],
                        "experience_level":  enrich["experience_level"] or None,
                        "employment_type":   enrich["employment_type"]  or None,
                        "benefits":          enrich["benefits"]         or None,
                        "job_expiry":        enrich["job_expiry"]       or None,
                        "logo_url":          enrich["logo_url"]         or None,
                        "company_size":      enrich["company_size"]     or None,
                        "company_industry":  enrich["company_industry"] or None,
                        "company_hq":        enrich["company_hq"]       or None,
                        "company_funding":   enrich["company_funding"],
                        "ai_keywords":       enrich["ai_keywords"]      or None,
                    })

                if len(hits) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
                await asyncio.sleep(0.4)

            print(f"[FantasticJobs/Modified] {location}: {len([u for u in updates])} updates so far")

    print(f"[FantasticJobs/Modified] Done — {len(updates)} modified jobs found")
    return updates


async def sync_expired_jobs(settings: dict) -> int:
    """
    Fetch expired jobs (ATS + job-board) from the last day and mark them closed.
    Runs daily at midnight.
    """
    print("[FantasticJobs] Fetching expired jobs (ATS + JobBoard) for last 1d...")
    try:
        headers = _get_headers()
    except RuntimeError as e:
        print(f"[FantasticJobs] {e} — skipping expired sync")
        return 0

    all_expired_ids: list = []

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        for expired_url in [BASE_EXPIRED_ATS, BASE_EXPIRED_JB]:
            feed_label = "expired-ats" if expired_url == BASE_EXPIRED_ATS else "expired-jb"
            try:
                r = await client.get(expired_url, params={"time_frame": "1d"})
                r.raise_for_status()
                ids = r.json()
                if isinstance(ids, list):
                    all_expired_ids.extend(ids)
                    print(f"[FantasticJobs] {feed_label}: {len(ids)} expired IDs")
                else:
                    print(f"[FantasticJobs] {feed_label}: unexpected response format")
            except Exception as e:
                print(f"[FantasticJobs] Error fetching {feed_label}: {e}")

    if not all_expired_ids:
        print("[FantasticJobs] No expired jobs to close.")
        return 0

    from database import mark_expired_jobs_closed
    closed_count = await mark_expired_jobs_closed(all_expired_ids)
    print(f"[FantasticJobs] Marked {closed_count} jobs as closed.")
    return closed_count
