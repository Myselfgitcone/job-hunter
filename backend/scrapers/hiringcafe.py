"""
HiringCafe — Next.js SSR API scraper.
Fetches structured job data (tech stack, YOE, salary, location, workplace type)
directly from their _next/data endpoint. No auth required.

API returns 887+ data engineer jobs per 2-day window across 518 companies.
"""
import httpx
import asyncio
import re
import json
from scrapers.base import JobData, detect_country, is_relevant_title, CUTOFF_HOURS

# Semaphore for JD fetches — don't hammer company servers
_JD_SEM = asyncio.Semaphore(8)

async def _fetch_full_jd(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch full JD from company ATS URL. Handles Greenhouse, Lever, Ashby, Workday, generic HTML."""
    try:
        from jd_fetcher import fetch_full_jd
        async with _JD_SEM:
            result = await fetch_full_jd(url)
            if not result or len(result) < 100:
                return None
            
            # Reject bot-protection and unsupported browser pages
            bad_phrases = ["unsupported browser", "enable javascript", "access denied", "cloudflare", "security check", "please wait while we verify", "browser does not support"]
            lower_res = result.lower()
            if any(p in lower_res for p in bad_phrases):
                return None
                
            return result
    except Exception:
        return None

BASE_URL    = "https://hiring.cafe"
PAGE_SIZE   = 40   # their fixed page size
MAX_PAGES   = 25   # cap at 1000 jobs per scrape run

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Referer": "https://hiring.cafe/",
}

# Broad terms that cover all knowledge-work roles.
# HiringCafe searches title+description, so each term returns hundreds of relevant jobs.
# Exclusion filter in base.py blocks garbage (nurses, cashiers, plumbers, etc.)
SEARCH_TERMS = [
    "engineer",
    "developer",
    "analyst",
    "scientist",
    "architect",
    "designer",
    "manager",
    "consultant",
    "director",
    "administrator",
]


async def _get_build_id(client: httpx.AsyncClient) -> str | None:
    """Fetch the Next.js build ID from the homepage — changes on each deploy."""
    try:
        r = await client.get(BASE_URL, headers={**HEADERS, "Accept": "text/html"})
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', r.text)
        return m.group(1) if m else None
    except Exception as e:
        print(f"[HiringCafe] build_id fetch failed: {e}")
        return None


async def _fetch_page(
    client: httpx.AsyncClient,
    build_id: str,
    term: str,
    page: int,
    days: int = 4,
) -> dict:
    state = json.dumps({
        "searchQuery": term,
        "dateFetchedPastNDays": days,
        "page": page,
    })
    url = f"{BASE_URL}/_next/data/{build_id}/index.json"
    r = await client.get(url, params={"searchState": state}, timeout=20)
    r.raise_for_status()
    return r.json().get("pageProps", {})


def _parse_location(v5: dict) -> tuple[str, str, bool]:
    """Returns (location_str, country, is_remote)."""
    wtype = (v5.get("workplace_type") or "").lower()
    is_remote = "remote" in wtype

    cities = v5.get("workplace_cities") or []
    states = v5.get("workplace_states") or []
    countries = v5.get("workplace_countries") or []

    # Build readable location string
    if cities:
        loc = cities[0]
    elif states:
        loc = states[0]
    elif is_remote:
        loc = "Remote"
    else:
        loc = ""

    # Determine country for our filter
    if is_remote or not countries:
        country = "Remote"
    elif any("IN" == c or "India" in c for c in countries):
        country = "India"
    elif any(c in ("US", "USA", "United States") for c in countries):
        country = detect_country(loc, default="USA")
    else:
        country = detect_country(loc, default="")

    return loc, country, is_remote


def _parse_salary(v5: dict) -> str:
    lo = v5.get("salary_range_min")
    hi = v5.get("salary_range_max")
    if lo and hi:
        return f"${int(lo/1000)}k–${int(hi/1000)}k"
    if lo:
        return f"${int(lo/1000)}k+"
    return ""


def _has_clearance(v5: dict) -> bool:
    certs = [c.lower() for c in (v5.get("licenses_or_certifications") or [])]
    req_summary = (v5.get("requirements_summary") or "").lower()
    bad = ("secret clearance", "ts/sci", "top secret", "clearance", "polygraph", "public trust")
    return any(b in c for c in certs for b in bad) or any(b in req_summary for b in bad)


def _has_no_sponsorship(v5: dict, req_summary: str) -> bool:
    """Return True if job explicitly bans sponsorship / requires citizenship."""
    text = req_summary.lower()
    bad_phrases = (
        "no sponsorship", "not sponsor", "cannot sponsor", "unable to sponsor",
        "will not sponsor", "us citizen", "u.s. citizen", "green card",
        "permanent resident", "must be authorized",
    )
    return any(p in text for p in bad_phrases)


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        build_id = await _get_build_id(client)
        if not build_id:
            print("[HiringCafe] Could not get build_id — skipping")
            return []

        print(f"[HiringCafe] build_id={build_id}")
        
        search_terms = SEARCH_TERMS
        print(f"[HiringCafe] Searching broad terms: {search_terms}")

        for term in search_terms:
            page = 0
            while page < MAX_PAGES:
                try:
                    pp = await _fetch_page(client, build_id, term, page, days=7)
                    hits = pp.get("ssrHits") or []
                    if not hits:
                        break

                    for hit in hits:
                        apply_url = hit.get("apply_url") or hit.get("hc_apply_url") or ""
                        if not apply_url or apply_url in seen:
                            continue

                        job_info = hit.get("job_information") or {}
                        v5 = hit.get("v5_processed_job_data") or {}

                        title = (
                            v5.get("core_job_title")
                            or job_info.get("title")
                            or hit.get("hc_title")
                            or ""
                        ).strip()

                        if not title:
                            continue

                        # Country + remote filter
                        loc, country, is_remote = _parse_location(v5)
                        if country not in ("USA", "India", "Remote"):
                            continue

                        req_summary = v5.get("requirements_summary") or ""

                        seen.add(apply_url)

                        company_name = (
                            (hit.get("enriched_company_data") or {}).get("name")
                            or hit.get("board_token", "").replace("-", " ").title()
                        )

                        # Try to fetch full JD from the company's ATS URL
                        full_desc = await _fetch_full_jd(client, apply_url)

                        if full_desc:
                            description = full_desc
                        else:
                            # Fallback: build description from structured HiringCafe data
                            tech_tools = v5.get("technical_tools") or []
                            description_parts = [req_summary]
                            if tech_tools:
                                description_parts.append("Tech Stack: " + ", ".join(tech_tools))
                            role_activities = v5.get("role_activities") or []
                            if role_activities:
                                description_parts.append("Responsibilities: " + "; ".join(role_activities))
                            description = "\n\n".join(p for p in description_parts if p)

                        salary = _parse_salary(v5)
                        seniority = v5.get("seniority_level") or ""

                        # Enrich title with seniority if not already there
                        if seniority and seniority.lower() not in title.lower():
                            level_map = {
                                "Senior Level": "Senior",
                                "Mid Level": "Mid",
                                "Entry Level": "Entry",
                                "Lead": "Lead",
                                "Staff": "Staff",
                            }
                            lvl = level_map.get(seniority, "")
                            if lvl and lvl.lower() not in title.lower():
                                title = f"{lvl} {title}"

                        jobs.append(JobData(
                            title=title,
                            company=company_name,
                            url=apply_url,
                            source="HiringCafe",
                            description=description,
                            location=loc,
                            country=country,
                            salary=salary,
                            remote=is_remote,
                            posted_at="",
                        ).to_dict())

                    if pp.get("ssrIsLastPage"):
                        break
                    page += 1
                    await asyncio.sleep(0.4)

                except Exception as e:
                    print(f"[HiringCafe] Error page={page} term={term!r}: {e}")
                    break

    print(f"[HiringCafe] {len(jobs)} jobs")
    return jobs
