"""
Recruitee — per-company public API.
https://{company}.recruitee.com/api/offers/
No auth required for public boards.
Company slugs sourced from jobseek + public Recruitee directory.
"""
import httpx
import asyncio
from scrapers.base import JobData, is_relevant_title, is_recent, detect_country, CUTOFF_HOURS

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_SEM = asyncio.Semaphore(20)

COMPANIES = [
    "11-bit-studios", "agicap", "asm", "assembly", "atlys",
    "auditdata", "autopilot", "bamboohr", "artifact",
    "personio", "docplanner", "vinted", "bolt", "pipedrive",
    "revolut", "wise", "sumup", "contentful", "gorillas",
    "delivery-hero", "zalando", "hellofresh", "n26", "klarna",
    "spotify-ds", "schibsted", "tink", "northvolt", "einride",
    "epidemic-sound", "kry", "karma", "hedvig", "anyfin",
    "nelly", "qliro", "acast", "soundtrack-your-brand",
    "detectify", "planhat", "mentimeter", "quinyx",
    "teamtailor", "funnel", "precisely", "taxfix", "moss",
    "pleo", "lunar", "spiir", "billy", "leanpay",
    "mopinion", "keylane", "copernica", "sendcloud",
    "messagebird", "blendle", "snappet", "yellowbrick",
    "studytube", "procurios", "wunder-mobility", "tier",
    "omio", "thermondo", "getsafe", "clark", "billie",
    "mambu", "raisin", "deposit-solutions", "solarisbank",
    "auxmoney", "crosslend", "liqid", "scalable-capital",
    "flixbus", "lilium", "volocopter", "isar-aerospace",
    "celonis", "rohde-schwarz", "msg-group", "tuv-sud",
    "allianz-technology", "bmw-group", "continental",
    "deutsche-telekom-it", "sap", "siemens-healthineers",
    "trivago", "idealo", "aboutyou", "otto-group",
    "engelvoelkers", "haufe-group",
]


async def _fetch_company(client: httpx.AsyncClient, company: str) -> list[dict]:
    async with _SEM:
        try:
            url = f"https://{company}.recruitee.com/api/offers/"
            resp = await client.get(url)
            if resp.status_code in (404, 403, 410):
                return []
            resp.raise_for_status()
            data = resp.json()
            offers = data.get("offers", [])
            jobs = []
            for item in offers:
                title = item.get("title", "")
                if not is_relevant_title(title):
                    continue
                job_url = item.get("careers_url") or item.get("url", "")
                if not job_url or "recruitee.com" not in job_url:
                    job_url = f"https://{company}.recruitee.com/o/{item.get('slug','')}"
                location = ", ".join(filter(None, [
                    item.get("city", ""),
                    item.get("country", ""),
                ]))
                country = detect_country(location, default="")
                if country not in ("USA", "India"):
                    continue
                posted = item.get("created_at", "")
                if not is_recent(posted):
                    continue
                jobs.append(JobData(
                    title=title,
                    company=item.get("company_name") or company.replace("-", " ").title(),
                    url=job_url,
                    source="Recruitee",
                    description="",
                    location=location,
                    country=country,
                    salary="",
                    remote="remote" in (title + location).lower(),
                    posted_at=posted,
                ).to_dict())
            return jobs
        except Exception:
            return []


async def fetch(settings: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        tasks = [_fetch_company(client, co) for co in COMPANIES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    jobs: list[dict] = []
    seen: set[str] = set()
    for batch in results:
        if isinstance(batch, Exception):
            continue
        for j in batch:
            url = j.get("url", "")
            if url and url not in seen:
                seen.add(url)
                jobs.append(j)

    print(f"[Recruitee] {len(jobs)} jobs from {len(COMPANIES)} companies")
    return jobs
