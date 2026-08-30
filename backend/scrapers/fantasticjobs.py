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
# USA: ATS-only — Western ATS platforms cover USA well; JB = LinkedIn reposts
# India JB was disabled after it reached ~35% of all job credits (~8.5K of 24K).
# JB is re-enabled for USA but LEADERSHIP-ONLY + LinkedIn-only, so volume (and
# credits) stay tiny. Feeds the AI/DS Leadership family's LinkedIn coverage.
ACTIVE_FEEDS = [BASE_ATS, BASE_JB]
LOCATIONS_FOR_JB = {"United States"}  # only run JB feed for these locations

# India removed — USA-only hunting; halves job-credit burn.
# Re-enable: LOCATIONS = ["United States", "India"]
LOCATIONS = ["United States"]

# Pagination constants (module-level so fetch_modified can use them)
PAGE_SIZE = 100   # FJ recommends 100-1000; bigger pages = fewer request credits
MAX_PAGES = 200   # safety cap only; natural break = last page < PAGE_SIZE

# Credit guard: count endpoints are FREE (request credits only). We pre-check
# expected volume per feed+location; anything above the cap means a filter
# regression or window bug — skip rather than bill thousands of job credits.
# Caps scale with the window: hourly runs see <200 jobs in practice (500 is
# generous); a 24h catch-up after downtime can legitimately reach a few K.
MAX_EXPECTED_BY_WINDOW = {"1h": 500, "6h": 1500, "24h": 3000, "48h": 5000,
                          "2d": 6000, "3d": 9000, "4d": 12000, "5d": 14000, "7d": 18000}

# FantasticJobs accepts ONLY these time_frame values (confirmed via 400 error).
# Our UI/legacy windows (48h/2d/…) must be translated to the nearest valid frame
# that COVERS the request, else FJ 400s and returns zero jobs.
_FJ_VALID_TF = {"1h", "24h", "7d", "1m", "6m"}
_FJ_WINDOW_MAP = {"6h": "24h", "48h": "7d", "2d": "7d", "3d": "7d",
                  "4d": "7d", "5d": "7d"}
def _to_fj_window(w: str) -> str:
    if w in _FJ_VALID_TF:
        return w
    return _FJ_WINDOW_MAP.get(w, "24h")

# Rate guards
_last_fetch_ts: datetime | None = None
_FJ_DATE_KEYS_LOGGED = [False]   # one-time probe of FJ's date field names
_last_modified_ts: datetime | None = None
# 45min, not 60: a manual scrape mid-hour must not make the next hourly cron
# skip — a skipped cron leaves a permanent gap (its 1h window never re-covers
# the missed minutes). Small overlap re-bills a few jobs; a gap loses them.
MIN_FETCH_INTERVAL_H    = 0.75
MIN_MODIFIED_INTERVAL_H = 6


# Boolean title filter — USA + India
# Java: one broad expression catches all "java *" titles; !javascript avoids false positives.
# 'spring boot' and jakarta cover Java jobs where "java" doesn't appear in the title.
# 'data platform' catches Data Platform Engineer (missed by 'data engineer' alone).
# Exec/arch exclusions: never billed, never stored — saves credits globally.
# Common families: Data Engineer, Data Analyst, BI (scraped for ALL countries)
# DevOps/SRE + Security disabled — re-add their terms here to re-enable:
# devops | sre | 'site reliability' | 'platform engineer'
# 'security engineer' | 'security analyst' | 'soc analyst' | cybersecurity | infosec | 'application security'
# Per-family FJ term blocks: the admin can toggle each family's
# scraping on/off from Settings (Setting key "scrape_families"). The USA filter
# is composed at fetch time from the ENABLED families only, so a disabled
# family is cut out of the API request itself (zero credits spent on it).
# Family names MUST match telegram_bot._ROLE_FAMILIES / the app's ROLE_GROUPS.
_FAMILY_TERMS: dict[str, str] = {
    # Strict on purpose — NOT "any data + any engineer": that pulled Test/
    # Project/Process/Reliability engineers that merely mention "data".
    "Data Engineer": (
        "'data engineer'"
        " | (data & (platform | pipeline | warehouse | lakehouse | infrastructure | ingestion | modeling | modelling))"
        " | etl | elt | 'data platform' | 'data warehouse'"
        " | 'data architect' | 'database engineer' | 'database developer' | 'sql developer'"
        " | 'data modeler' | 'data modeller'"
        " | databricks"
        " | 'snowflake developer' | 'snowflake engineer' | 'spark engineer' | 'spark developer'"
        " | 'dbt developer' | 'airflow engineer' | 'kafka engineer'"
        # ML/MLOps REMOVED — not part of Data Engineer.
        " | ('software engineer' & ('data platform' | 'data infrastructure' | 'data pipeline' | 'data warehouse'))"
    ),
    "Data Analyst": (
        "(data & analyst) | 'data analytics' | 'analytics engineer' | 'reporting analyst' | 'product analyst'"
    ),
    "BI": (
        "'business intelligence' | 'bi developer' | 'bi analyst' | 'bi engineer'"
        " | 'power bi' | tableau | looker | 'data visualization'"
    ),
    "Cloud": (
        "'cloud engineer' | 'cloud infrastructure engineer' | 'cloud operations'"
        " | cloudops | 'cloud systems engineer' | 'cloud developer' | 'cloud native'"
        " | 'cloud migration engineer' | 'aws engineer' | 'azure engineer'"
        " | 'gcp engineer' | 'google cloud engineer' | 'infrastructure engineer'"
        " | kubernetes | terraform"
    ),
    "DevOps / SRE": (
        "devops | 'devops engineer' | devsecops | sre | 'site reliability'"
        " | 'platform engineer' | 'release engineer' | 'ci/cd' | 'build engineer'"
        " | 'production engineer' | 'reliability engineer' | 'observability engineer'"
    ),
    "Business Analyst": (
        "'business analyst' | 'business systems analyst' | 'technical business analyst'"
        " | 'systems analyst' | 'it business analyst' | 'business data analyst'"
        " | 'data business analyst' | 'process analyst' | 'requirements analyst'"
        " | 'functional analyst'"
    ),
    # ── Entry/mid-level family. Title-only, FJ quoted
    # phrases = contains matching ("Senior GRC Analyst II" still matches — the
    # group's seniority NOT below drops the seniors). It carries its
    # own !(senior…) cut; director/VP/chief already cut by _GLOBAL_NOT.
    # Security/SIEM, GenAI/RAG, and IAM families retired — hunting stopped.
    "GRC": (
        "(('grc analyst' | 'it risk analyst' | 'it compliance analyst' | 'compliance analyst'"
        " | 'risk analyst' | 'information security analyst' | 'security compliance analyst'"
        " | 'it auditor' | 'it audit analyst' | 'cyber risk analyst'"
        " | 'third party risk analyst' | 'vendor risk analyst' | 'tprm analyst')"
        " & !(senior | sr | staff | principal | lead))"
    ),
    # ── Niche families — specialist tool stacks with tiny, low-competition
    # job markets. Title-only, all seniority levels: the vocabulary is niche
    # enough that volume stays low without an experience gate.
    # Epic healthcare-analytics stack (Cogito is Epic's BI/reporting suite).
    "Niche - Epic Cogito": (
        "cogito | caboodle | 'epic clarity' | 'epic radar' | 'epic reporting'"
        " | 'epic bi' | 'epic business intelligence' | 'clarity report'"
        " | slicerdicer | 'slicer dicer' | 'reporting workbench'"
    ),
    # Connected-planning / EPM platforms (Anaplan + same-skill competitors).
    "Niche - Anaplan": (
        "anaplan | 'connected planning' | onestream"
        " | 'adaptive planning' | 'workday adaptive' | 'pigment planning'"
    ),
    # 'project manager' removed — re-add as a family to re-enable.
}
ALL_FAMILIES = list(_FAMILY_TERMS.keys()) + ["AI/DS Leadership"]

_TERMS_COMMON = " | ".join(_FAMILY_TERMS.values())
# Java family — USA only (India team doesn't hunt Java roles)
_TERMS_JAVA = "(java & !javascript) | 'spring boot' | 'spring framework' | jakarta | hibernate | 'jvm engineer'"

# AI / Data-Science LEADERSHIP family — for senior-profile users, kept separate.
# These are Director/Head/VP/Chief titles that _GLOBAL_NOT deliberately blocks,
# so they're OR'd in OUTSIDE the exec exclusion. Scoped to AI/DS/ML so it can't
# leak every director — the seniority word must co-occur with an AI/DS field.
_TERMS_LEADERSHIP = (
    "((director | 'senior director' | 'sr director' | head | 'vice president' | vp | chief | principal)"
    " & (ai | 'artificial intelligence' | 'data science' | 'machine learning'"
    " | 'ml engineering' | 'ai engineering' | 'applied ai' | 'ml platform'"
    " | 'ai platform' | 'ai governance' | 'responsible ai' | mlops"
    " | 'data platform' | 'data engineering'))"
    " | 'chief ai officer' | 'chief data scientist' | 'chief data officer'"
    " | 'principal machine learning' | 'principal data scientist' | 'principal ai engineer'"
    " | 'staff machine learning engineer' | 'staff data scientist'"
)

# Architect exclusion is surgical: Data Architect is a valid 6-8yr DE target,
# but system/org-level architect tracks are 10+ years — keep those out.
# financial/marketing/sales removed from NOT: they were killing valid roles
# (Financial Data Analyst, Marketing Data Analyst...). Positive terms are all
# data-anchored, so non-data financial/sales titles can't match anyway.
_GLOBAL_NOT = (
    " & !(nurse"
    # Non-DE engineering disciplines — physical/infrastructure roles
    " | 'data center'"             # Data Center Engineer (hardware)
    " | structural | mechanical"   # civil/mech engineering
    " | network"                   # Network Engineer (infra, not pipelines)
    " | 'process engineer' | 'process manager'"
    # Management / PM tracks
    " | 'operations manager' | 'program manager'"
    # Seniority: lead/staff/principal are now ALLOWED. The app is
    # multi-user with varying experience, and the AI qualify step scores
    # seniority-fit per person downstream — so pulling senior roles gives
    # experienced users real options without cluttering junior users' top
    # results. Only exec/architect tracks stay excluded below.
    # Executive / architect exclusions (existing)
    " | director | 'vice president' | vp | cto | chief"
    " | 'solutions architect' | 'enterprise architect' | 'cloud architect'"
    " | 'software architect' | 'technical architect' | 'application architect'"
    " | 'integration architect' | 'security architect')"
)

import re as _re
# Description-level skip — checked on raw JD text before storing.
# Matches clearance requirements and citizenship-only roles that can't
# be filtered by title alone.
_SKIP_DESC_RE = _re.compile(
    r"(security clearance|secret clearance|top.?secret|ts/sci|active clearance"
    r"|must be (a )?u\.?s\.? citizen|u\.?s\.? citizens? only"
    r"|citizenship required|citizen of the united states"
    r"|require.{0,30}citizenship|clearance required)",
    _re.IGNORECASE,
)

# ── Entry-level families (Security/SIEM, GenAI/RAG, GRC, IAM) — stricter
# description policy: DROP no-sponsorship/C2C jobs at
# scrape (other families keep them + show the red flag). Runs on already-
# fetched text — zero extra credits.
_ENTRY_FAM_TITLE_RE = _re.compile(
    r"\bgrc\b|it\s+risk|it\s+compliance|compliance\s+analyst|risk\s+analyst"
    r"|information\s+security|security\s+compliance|it\s+audit|cyber\s+risk"
    r"|third.?party\s+risk|vendor\s+risk|\btprm\b",
    _re.IGNORECASE,
)
_NOSPON_DESC_RE = _re.compile(
    r"(no\s+sponsorship|not\s+sponsor|unable\s+to\s+sponsor|cannot\s+sponsor"
    r"|will\s+not\s+sponsor|not\s+eligible\s+for.{0,30}sponsorship"
    # green card only in NEGATIVE context — "offers green card sponsorship" is
    # a top-tier positive and must NOT be dropped.
    r"|green\s+card\s+(holders?\s+)?(only|required)"
    r"|citizens?\s+or\s+green\s+card|must\s+(have|be).{0,30}green\s+card"
    r"|\bc2c\b|corp\s+to\s+corp|w-?2\s+only.{0,40}citizen)",
    _re.IGNORECASE,
)
# Positive sponsorship signal → flag as "Sponsors ✓" (only when no negative hit).
_SPON_POS_RE = _re.compile(r"(sponsor|h-?1\s?b|\bvisa\b|\bopt\b|\bcpt\b)", _re.IGNORECASE)

TITLE_FILTER_USA   = f"(({_TERMS_COMMON}){_GLOBAL_NOT}) | ({_TERMS_LEADERSHIP})"  # all families (static default)
TITLE_FILTER_INDIA = f"({_TERMS_COMMON})" + _GLOBAL_NOT
# Default (modified-ats sync etc.) — widest filter
TITLE_FILTER = TITLE_FILTER_USA

# JB (LinkedIn) feed for USA pulls ONLY AI/DS leadership titles — keeps LinkedIn
# volume/credits tiny (leadership titles are rare). The old JB flood was from
# pulling every family; leadership-only avoids that.
TITLE_FILTER_JB_USA = f"({_TERMS_LEADERSHIP})"

# Admin family toggles — set by fetch() from Setting "scrape_families" before
# each run. None = all enabled (default / setting unreadable).
_ENABLED_FAMILIES: set | None = None

def compose_usa_filter(enabled: set | None) -> str:
    """USA filter from the enabled families only. Empty string = fetch nothing."""
    if enabled is None:
        return TITLE_FILTER_USA
    common = " | ".join(_FAMILY_TERMS[f] for f in _FAMILY_TERMS if f in enabled)
    parts = []
    if common:
        parts.append(f"(({common}){_GLOBAL_NOT})")
    if "AI/DS Leadership" in enabled:
        parts.append(f"({_TERMS_LEADERSHIP})")
    return " | ".join(parts)

def title_filter_for(location: str, feed_url: str = BASE_ATS) -> str:
    if feed_url == BASE_JB and location != "India":
        return TITLE_FILTER_JB_USA
    if location == "India":
        return TITLE_FILTER_INDIA
    return compose_usa_filter(_ENABLED_FAMILIES)


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


# FJ's per-job `source` field → display name
_ATS_PRETTY = {
    "greenhouse": "Greenhouse", "greenhouse.io": "Greenhouse",
    "lever": "Lever", "lever.co": "Lever",
    "ashby": "Ashby", "ashbyhq": "Ashby",
    "workday": "Workday", "icims": "iCIMS", "adp": "ADP",
    "smartrecruiters": "SmartRecruiters", "bamboohr": "BambooHR",
    "workable": "Workable", "recruitee": "Recruitee", "jobvite": "Jobvite",
    "taleo": "Taleo", "successfactors": "SuccessFactors",
    "oraclecloud": "Oracle", "rippling": "Rippling", "jazzhr": "JazzHR",
    "breezy": "Breezy", "teamtailor": "Teamtailor", "personio": "Personio",
    "paylocity": "Paylocity", "paycom": "Paycom", "ukg": "UKG",
    "dayforce": "Dayforce", "eightfold": "Eightfold", "phenom": "Phenom",
}

# URL-domain fallback (also used to backfill existing DB rows)
ATS_URL_MAP = {
    "greenhouse.io":      "Greenhouse",
    "lever.co":           "Lever",
    "ashbyhq.com":        "Ashby",
    "myworkdayjobs":      "Workday",
    "workday":            "Workday",
    "icims.com":          "iCIMS",
    "adp.com":            "ADP",
    "workforcenow":       "ADP",
    "smartrecruiters":    "SmartRecruiters",
    "bamboohr.com":       "BambooHR",
    "workable.com":       "Workable",
    "recruitee.com":      "Recruitee",
    "jobvite.com":        "Jobvite",
    "taleo.net":          "Taleo",
    "successfactors":     "SuccessFactors",
    "oraclecloud.com":    "Oracle",
    "rippling.com":       "Rippling",
    "applytojob.com":     "JazzHR",
    "breezy.hr":          "Breezy",
    "teamtailor.com":     "Teamtailor",
    "personio":           "Personio",
    "paylocity.com":      "Paylocity",
    "paycomonline":       "Paycom",
    "ukg.com":            "UKG",
    "dayforcehcm":        "Dayforce",
    "eightfold.ai":       "Eightfold",
    "phenompeople":       "Phenom",
}

def detect_ats_from_url(url: str) -> str:
    lower = (url or "").lower()
    for domain, label in ATS_URL_MAP.items():
        if domain in lower:
            return label
    return ""

def resolve_source(fj_source: str, url: str, board_src: str) -> str:
    """Best display source: FJ's own source field > ATS by URL > board by URL."""
    s = (fj_source or "").lower().strip()
    if s:
        return _ATS_PRETTY.get(s, s.title())
    return detect_ats_from_url(url) or board_src


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
        "title_advanced": title_filter_for(location, base_url),
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
        "title_advanced": title_filter_for(location, base_url),
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

    # One-shot backfill override: admin sets Setting 'fj_force_window' (e.g.
    # "24h") to force a wider window on the NEXT run — used to backfill newly
    # added role families. Consumed immediately so it fires exactly once, and
    # it bypasses the min-interval guard below.
    force_window: str | None = None
    global _ENABLED_FAMILIES
    try:
        from database import SessionLocal, Setting
        async with SessionLocal() as db:
            frow = await db.get(Setting, "fj_force_window")
            if frow and frow.value and frow.value.strip():
                force_window = frow.value.strip()
                await db.delete(frow)
                await db.commit()
            # Admin family toggles — OFF families are cut from the API request.
            srow = await db.get(Setting, "scrape_families")
            if srow and srow.value:
                m = json.loads(srow.value)
                _ENABLED_FAMILIES = {f for f in ALL_FAMILIES if m.get(f, True)}
            else:
                _ENABLED_FAMILIES = None   # no setting → all on
    except Exception as e:
        print(f"[FantasticJobs] force-window/families read failed: {e}")
        _ENABLED_FAMILIES = None

    if _ENABLED_FAMILIES is not None and not _ENABLED_FAMILIES:
        print("[FantasticJobs] All families toggled OFF — skipping fetch")
        return []

    if not force_window and _last_fetch_ts and (now - _last_fetch_ts) < timedelta(hours=MIN_FETCH_INTERVAL_H):
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
    if force_window:
        # FantasticJobs only accepts 1h / 24h / 7d / 1m / 6m. Our legacy window
        # values (48h/2d/3d/4d/5d/6h) were sent verbatim and silently 400'd →
        # 0 jobs. Translate to the nearest valid frame that COVERS the request.
        time_frame = _to_fj_window(force_window)
        print(f"[FantasticJobs] FORCED window={force_window} → FJ time_frame={time_frame} (backfill)")
    else:
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
    # Cross-feed dedup by (title|company): ATS feed runs first and registers its
    # keys, so a LinkedIn repost of a job already pulled from an ATS is skipped
    # (keep the ATS original — direct apply). Within-feed dups also collapse.
    seen_jobkey: set[str] = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for feed_url in ACTIVE_FEEDS:
            feed_label  = "ATS" if feed_url == BASE_ATS else "JobBoard"
            org_details = feed_url == BASE_ATS  # only ATS supports include_basic_organization_details
            locations_label = "+".join(LOCATIONS) if feed_url == BASE_ATS else "+".join(LOCATIONS_FOR_JB)
            print(f"[FantasticJobs/{feed_label}] Fetching {locations_label} with title filter...")

            for location in LOCATIONS:
                if feed_url == BASE_JB and location not in LOCATIONS_FOR_JB:
                    continue
                # JB feed is leadership-only — skip it entirely when that family is OFF.
                if feed_url == BASE_JB and _ENABLED_FAMILIES is not None \
                        and "AI/DS Leadership" not in _ENABLED_FAMILIES:
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
                # Drop-reason funnel — one glance shows which filter eats jobs.
                from collections import Counter as _Counter
                drops = _Counter()

                for page in range(MAX_PAGES):
                    hits = await _fetch_page(client, location, offset=offset, base_url=feed_url, include_org_details=org_details, time_frame=time_frame)
                    if not hits:
                        break

                    total_raw += len(hits)

                    for job in hits:
                        url = job.get("url") or ""
                        if not url or url in seen:
                            drops["dup_url"] += 1
                            continue

                        title = (job.get("title") or "").strip()
                        if not title or not is_relevant_title(title):
                            drops["title_excluded"] += 1
                            continue

                        # ATS uses "organization"; job board may use "company" or "organization"
                        company = (job.get("organization") or job.get("company") or "").strip()
                        if not company:
                            drops["no_company"] += 1
                            continue
                        # Staffing/repost aggregator accounts — never real employers
                        if any(b in company.lower() for b in _JUNK_COMPANIES):
                            drops["staffing_junk"] += 1
                            continue

                        countries   = job.get("countries_derived") or []
                        arrangement = job.get("ai_work_arrangement") or ""
                        country     = _map_country(countries, arrangement)
                        # USA-only (India fully removed).
                        if country != "USA":
                            locs    = job.get("locations_derived") or []
                            loc_str = locs[0] if locs else ""
                            country = detect_country(loc_str, default="")
                            if country != "USA":
                                drops["non_usa"] += 1
                                continue

                        def _norm_dt(raw):
                            if not raw:
                                return ""
                            try:
                                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                if 0 <= (now - dt).days <= 60:
                                    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                            except Exception:
                                pass
                            return ""

                        posted_at = _norm_dt(job.get("date_posted"))
                        # FJ index time — finer than the often date-only date_posted.
                        # Field name isn't publicly documented, so try the likely ones.
                        indexed_at = _norm_dt(
                            job.get("date_created") or job.get("date_on_index")
                            or job.get("date_reposted") or job.get("date_validthrough_created") or "")
                        # One-time probe: log which date-ish keys FJ actually sends.
                        if kept == 0 and not _FJ_DATE_KEYS_LOGGED[0]:
                            _FJ_DATE_KEYS_LOGGED[0] = True
                            _dk = {k: job.get(k) for k in job.keys() if "date" in k.lower() or "created" in k.lower() or "index" in k.lower()}
                            print(f"[FantasticJobs] date-ish keys sample: {_dk}")

                        locs_derived = job.get("locations_derived") or []
                        location_str = locs_derived[0] if locs_derived else ""

                        enrich = _extract_enrichment(job)

                        # Detect actual hosting board by URL — the ATS feed also
                        # contains LinkedIn-hosted listings for companies w/o an ATS
                        board_src = _detect_jb_source(url)
                        if country == "USA":
                            if feed_url == BASE_JB:
                                # JB feed for USA is scoped to LinkedIn leadership only.
                                # FJ's JB `url` is often the employer apply
                                # URL, not a linkedin.com link — so detect LinkedIn from ANY
                                # signal: FJ source field, url, or the linkedin_url field.
                                _fj_src = (job.get("source") or "").lower()
                                is_linkedin = (
                                    "linkedin" in _fj_src
                                    or board_src == "LinkedIn"
                                    or "linkedin.com" in url.lower()
                                    or "linkedin.com" in (job.get("linkedin_url") or "").lower()
                                )
                                if not is_linkedin:
                                    drops["jb_not_linkedin"] += 1
                                    continue
                            else:
                                # ATS feed: direct career pages only — board-hosted posts
                                # (LinkedIn/Indeed/Dice) are reposts, dropped for USA.
                                if board_src != "FantasticJobs":
                                    drops["board_repost"] += 1
                                    continue
                        # Display source: actual ATS name (Greenhouse/iCIMS/ADP/...)
                        job_source = resolve_source(job.get("source") or "", url, board_src)
                        # JB-USA leadership jobs are the LinkedIn family — force a clean
                        # "LinkedIn" label so the frontend source gate matches exactly.
                        if feed_url == BASE_JB:
                            job_source = "LinkedIn"

                        # Description-level skip — clearance / citizenship-only roles.
                        # Check raw API text before building full description to avoid
                        # storing jobs the candidate can't legally apply to.
                        raw_desc_text = (
                            job.get("description_html") or job.get("description") or
                            job.get("ai_requirements_summary") or ""
                        )
                        if _SKIP_DESC_RE.search(raw_desc_text):
                            drops["clearance_citizen"] += 1
                            continue

                        # Entry-level families only: drop no-sponsorship/C2C at
                        # scrape; flag positive sponsorship language; drop roles
                        # requiring 5+ years (never stored). Jobs with NO stated
                        # years are kept — can't judge them.
                        if _ENTRY_FAM_TITLE_RE.search(title):
                            if _NOSPON_DESC_RE.search(raw_desc_text):
                                drops["niche_no_sponsor"] += 1
                                continue
                            fj_lvl = (job.get("ai_experience_level") or "").strip()
                            if fj_lvl in ("5-10", "10+"):
                                drops["niche_5plus_yrs"] += 1
                                continue
                            from scrapers.base import extract_min_years_required as _minyrs
                            _y = _minyrs(raw_desc_text)
                            if _y is not None and _y >= 5:
                                drops["niche_5plus_yrs"] += 1
                                continue
                            if enrich["visa_sponsorship"] is None and _SPON_POS_RE.search(raw_desc_text):
                                enrich["visa_sponsorship"] = True

                        # Cross-feed dedup — ATS original wins over a LinkedIn repost.
                        jobkey = f"{title.lower()}|{company.lower()}"
                        if jobkey in seen_jobkey:
                            drops["dup_title_company"] += 1
                            continue
                        seen_jobkey.add(jobkey)

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
                            indexed_at=indexed_at,
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

                _funnel = " ".join(f"{k}:{v}" for k, v in drops.most_common()) or "none"
                print(f"[FantasticJobs/{feed_label}] {location}: {total_raw} raw ({page+1} pages) → {kept} kept | drops: {_funnel}")

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
