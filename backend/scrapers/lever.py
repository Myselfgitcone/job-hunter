"""
Lever — public postings API per company.
api.lever.co/v0/postings/{company}?mode=json
No auth required for public boards.

Company list sourced from jobseek (github.com/colophon-group/jobseek) — 150+ companies.
"""
import httpx
import asyncio
from scrapers.base import JobData, detect_country, CUTOFF_HOURS
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

BASE = "https://api.lever.co/v0/postings/{company}?mode=json"

COMPANIES = [
    "15five", "activecampaign", "aeva", "agicap", "agiloft", "aircall", "airslate", "ajax",
    "aledade", "aleph", "alloy", "alltrails", "alluxio", "anchorage", "anomali", "anybotics",
    "anyscale", "applydigital", "arbitalhealth", "artera", "atomcomputing", "belong", "belvederetrading", "beta",
    "binance", "blablacar", "bloom", "brilliant", "clari", "color", "contentsquare", "coupa",
    "cred", "crypto", "cx2", "cyngn", "daedalean", "dexterity", "dreamsports", "drivetrain",
    "dronedeploy", "everlywell", "evr", "exowatt", "factor", "farfetch", "finch", "finix",
    "form", "gate", "getzuma", "glide", "gopuff", "grailbio", "grand", "gravisrobotics",
    "greenlight", "hive", "indexventures", "jobandtalent", "kavak", "kepler", "keyloop", "kiddom",
    "knownwell", "kpmgnz", "kraken123", "lasenza", "ledger", "loadsmart", "lyrahealth", "marqvision",
    "metabase", "mistral", "mobileye", "morningbrew", "neon", "nomagic", "octoenergy", "onit",
    "osaro", "outreach", "palantir", "paytm", "pennylane", "people-ai", "pigment", "pipedrive",
    "pivotal", "plaid", "prosus", "protolabs", "q-ctrl", "qonto", "rai", "regrello",
    "relay", "rigetti", "rivr", "ro", "rover", "safe", "safetyculture-2", "sanctuary",
    "sandboxvr", "saronic", "saviynt", "secureframe", "sesame", "shieldai", "sila", "skillshare",
    "slate", "sonarsource", "sonatype", "spotify", "stackblitz", "stackhawk", "storiogroup", "sugarcrm",
    "swile", "swordhealth", "tinybird", "tomtom", "trendyol", "tryjeeves", "uncountable", "unify",
    "unlimit", "upstox", "uvcyber", "v0", "veepee", "veeva", "veo", "verygoodsecurity",
    "voleon", "vwgds", "wealthfront", "weride", "whereby", "whoop", "wingtra-2", "wpromote",
    "xm", "yuno", "zerion", "zoox", "zopa", "zushealth",
    # ── Additional high-value Data Engineering employers ───────────────────
    # Cloud / Data companies
    "databricks", "dbt-labs", "hex-technologies", "hightouch-data",
    "prefect", "dagster-labs", "monte-carlo-data", "bigeye-data",
    "athenaisai", "tinybird", "turntable-ai",
    # Major consumer / growth tech
    "airbnb", "lyft", "doordash", "instacart", "shipt",
    "robinhood", "coinbase-global", "kraken", "gemini",
    "notion", "figma", "airtable", "linear",
    "vercel", "retool", "hashicorp",
    # Fintech
    "brex", "ramp-financial", "chime", "stripe",
    "marqeta", "checkout-com", "adyen",
    # Indian / global IT
    "mphasis", "persistent-systems", "zensar-technologies",
    "mastech-digital", "niit-technologies",
]

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_SEM = asyncio.Semaphore(50)


def _is_relevant(title: str) -> bool:
    from scrapers.base import is_relevant_title
    return is_relevant_title(title)


def _is_recent(ts_ms) -> bool:
    if not ts_ms:
        return True
    try:
        dt = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    except Exception:
        return True


async def _fetch_company(client: httpx.AsyncClient, company: str) -> list[dict]:
    async with _SEM:
        try:
            resp = await client.get(BASE.format(company=company))
            if resp.status_code in (404, 403):
                return []
            resp.raise_for_status()
            postings = resp.json()
            if not isinstance(postings, list):
                return []

            jobs = []
            for item in postings:
                title = item.get("text", "")
                if not _is_relevant(title):
                    continue
                if not _is_recent(item.get("createdAt")):
                    continue

                job_url = item.get("hostedUrl") or item.get("applyUrl", "")
                if not job_url:
                    continue

                loc = item.get("categories", {}).get("location", "")
                country = detect_country(loc, default="USA" if not loc else "")
                if country not in ("USA", "India", "Remote"):
                    continue

                desc_parts = []
                for section in item.get("lists", []):
                    desc_parts.append(section.get("text", ""))
                    for li in section.get("content", []):
                        desc_parts.append("* " + BeautifulSoup(li, "lxml").get_text(strip=True))
                for section in item.get("additional", []):
                    html = section.get("content", "")
                    if html:
                        desc_parts.append(BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True))
                desc = "\n".join(p for p in desc_parts if p)

                jobs.append(JobData(
                    title=title,
                    company=item.get("company") or company.replace("-", " ").title(),
                    url=job_url,
                    source="Lever",
                    description=desc,
                    location=loc,
                    country=country,
                    salary="",
                    remote="remote" in (title + loc).lower(),
                    posted_at=datetime.fromtimestamp(
                        int(item.get("createdAt", 0)) / 1000, tz=timezone.utc
                    ).isoformat() if item.get("createdAt") else "",
                ).to_dict())
            return jobs
        except Exception:
            return []


async def fetch(settings: dict) -> list[dict]:
    companies = settings.get("_lever_slugs") or COMPANIES
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        tasks = [_fetch_company(client, co) for co in companies]
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

    print(f"[Lever] {len(jobs)} jobs from {len(companies)} companies")
    return jobs

