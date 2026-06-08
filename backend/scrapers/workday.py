"""
Workday — hidden JSON API per company.
POST https://{sub}.wd{n}.myworkdayjobs.com/wday/cxs/{sub}/{board}/jobs
No auth required. Returns JSON directly — no JS rendering needed.

Companies: major tech/finance firms known to use Workday.
"""
from zoneinfo import ZoneInfo
EST = ZoneInfo('America/New_York')
import httpx
import asyncio
import re
from scrapers.base import JobData, detect_country, is_relevant_title, SEARCH_TERMS

# Each entry: (subdomain, wd_number, board_path, company_display_name)
COMPANIES = [
    # ── Core tech (Workday) ──────────────────────────────────────────────────
    ("adobe",              "wd5",  "external_experienced",              "Adobe"),
    ("amazon",             "wd5",  "en-US/External_Career_Site",        "Amazon"),
    ("microsoft",          "wd5",  "Microsoft_Careers",                 "Microsoft"),
    ("walmart",            "wd5",  "WalmartExternal",                   "Walmart"),
    ("salesforce",         "wd12", "External_Career_Site",              "Salesforce"),
    ("intel",              "wd1",  "External",                          "Intel"),
    ("qualcomm",           "wd5",  "External",                          "Qualcomm"),
    ("cisco",              "wd5",  "Cisco",                             "Cisco"),
    ("micron",             "wd5",  "External",                          "Micron"),
    ("lamresearch",        "wd5",  "External",                          "Lam Research"),
    ("broadcom",           "wd5",  "External",                          "Broadcom"),
    ("ti",                 "wd5",  "external",                          "Texas Instruments"),
    ("hp",                 "wd5",  "JobsatHP",                          "HP"),
    ("dell",               "wd1",  "External",                          "Dell"),
    ("tmobile",            "wd5",  "External",                          "T-Mobile"),
    ("verizon",            "wd5",  "External",                          "Verizon"),
    ("nvidia",             "wd5",  "NVIDIAExternalCareerSite",          "NVIDIA"),
    ("servicenow",         "wd5",  "External",                          "ServiceNow"),
    ("intuit",             "wd5",  "jobs",                              "Intuit"),
    ("uber",               "wd5",  "Uber_External_Careers",             "Uber"),
    ("amat",               "wd1",  "External",                          "Applied Materials"),
    ("analogdevices",      "wd1",  "External",                          "Analog Devices"),
    ("aptiv",              "wd5",  "APTIV_CAREERS",                     "Aptiv"),
    ("astrazeneca",        "wd3",  "Careers",                           "AstraZeneca"),
    ("barclays",           "wd3",  "External_Career_Site_Barclays",     "Barclays"),
    ("abb",                "wd3",  "External_Career_Page",              "ABB"),
    ("ag",                 "wd3",  "en-US/Airbus",                      "Airbus"),
    # ── Finance / Banking ────────────────────────────────────────────────────
    ("goldmansachs",       "wd1",  "External",                          "Goldman Sachs"),
    ("jpmc",               "wd5",  "jpmc_ext",                          "JPMorgan Chase"),
    ("morganstanley",      "wd5",  "generalmorganstanley",              "Morgan Stanley"),
    ("wellsfargo",         "wd5",  "WellsFargoCareersUSA",              "Wells Fargo"),
    ("deloitte",           "wd1",  "DTUSAExternalCareers",              "Deloitte"),
    ("bofa",               "wd1",  "Global",                            "Bank of America"),
    ("citi",               "wd5",  "External",                          "Citigroup"),
    ("pwccareers",         "wd3",  "Global_Campus_And_Experienced",     "PwC"),
    ("kpmg",               "wd5",  "External",                          "KPMG"),
    ("ey",                 "wd5",  "External",                          "Ernst & Young"),
    ("mckinsey",           "wd5",  "External",                          "McKinsey"),
    ("accenture",          "wd3",  "AccentureCareers",                  "Accenture"),
    ("visa",               "wd5",  "External",                          "Visa"),
    ("mastercard",         "wd5",  "External",                          "Mastercard"),
    # ── Telecom / Enterprise ─────────────────────────────────────────────────
    ("att",                "wd5",  "External",                          "AT&T"),
    ("comcast",            "wd5",  "External",                          "Comcast"),
    ("charter",            "wd5",  "External",                          "Charter Communications"),
    ("ibm",                "wd5",  "External",                          "IBM"),
    ("sap",                "wd3",  "SAP",                               "SAP"),
    ("oracle",             "wd1",  "External",                          "Oracle"),
    # ── Healthcare ───────────────────────────────────────────────────────────
    ("uhg",                "wd5",  "External",                          "UnitedHealth Group"),
    ("medtronic",          "wd5",  "External",                          "Medtronic"),
    ("abbott",             "wd5",  "abbottcareers",                     "Abbott"),
    ("pfizer",             "wd5",  "PfizerCareers",                     "Pfizer"),
    ("jnj",                "wd5",  "JNJExternal",                       "Johnson & Johnson"),
    ("merck",              "wd5",  "External",                          "Merck"),
    ("humana",             "wd5",  "External",                          "Humana"),
    ("elevancehealth",     "wd5",  "External",                          "Elevance Health"),
    # ── Automotive / Manufacturing ────────────────────────────────────────────
    ("gm",                 "wd5",  "External",                          "General Motors"),
    ("ford",               "wd5",  "External",                          "Ford"),
    ("tesla",              "wd5",  "TeslaMotors",                       "Tesla"),
    ("rivian",             "wd5",  "External",                          "Rivian"),
    ("boeing",             "wd5",  "EXTERNAL_CAREER_SITE",              "Boeing"),
    ("lockheedmartin",     "wd5",  "External",                          "Lockheed Martin"),
    ("raytheon",           "wd5",  "External",                          "Raytheon"),
    # ── Retail / E-commerce ──────────────────────────────────────────────────
    ("target",             "wd5",  "careersUS",                         "Target"),
    ("homedepot",          "wd5",  "Careers_by_HD",                     "Home Depot"),
    ("cvs",                "wd5",  "External",                          "CVS Health"),
    ("walgreens",          "wd5",  "External",                          "Walgreens"),
    # ── India-heavy IT companies ─────────────────────────────────────────────
    ("infosys",            "wd5",  "Infosys",                           "Infosys"),
    ("wipro",              "wd5",  "External",                          "Wipro"),
    ("hcltech",            "wd5",  "External",                          "HCL Technologies"),
    ("tcs",                "wd5",  "External",                          "TCS"),
    ("techm",              "wd5",  "External",                          "Tech Mahindra"),
    ("ltimindtree",        "wd5",  "External",                          "LTIMindtree"),
    ("mphasis",            "wd5",  "External",                          "Mphasis"),
    ("persistent",         "wd5",  "External",                          "Persistent Systems"),
    ("hexaware",           "wd5",  "External",                          "Hexaware"),
    ("zensar",             "wd5",  "External",                          "Zensar"),
    # ── Cloud / Data ─────────────────────────────────────────────────────────
    ("pagerduty",          "wd5",  "External",                          "PagerDuty"),
    ("cloudera",           "wd5",  "External",                          "Cloudera"),
    ("informatica",        "wd5",  "External",                          "Informatica"),
    ("talend",             "wd5",  "External",                          "Talend"),
    ("qlik",               "wd5",  "External",                          "Qlik"),
    ("microstrategy",      "wd5",  "External",                          "MicroStrategy"),
    ("teradata",           "wd5",  "Global",                            "Teradata"),
    ("sas",                "wd5",  "External",                          "SAS Institute"),
    ("mathworks",          "wd5",  "External",                          "MathWorks"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

_SEM = asyncio.Semaphore(10)


def _parse_posted_days(posted_text: str) -> int:
    """Parse Workday relative date string → days ago. Returns 999 if old/unknown."""
    if not posted_text:
        return 0
    t = posted_text.lower()
    if "today" in t:
        return 0
    if "yesterday" in t:
        return 1
    m = re.search(r"(\d+)\s+day", t)
    if m:
        return int(m.group(1))
    if "30+" in t or "month" in t:
        return 999
    return 0  # unknown = assume recent


def _days_ago_to_iso(days: int) -> str:
    """Convert 'X days ago' to ISO timestamp at start of that calendar day.
    Using start-of-day matches how Workday labels posts (not exact hour).
    """
    from datetime import datetime, timezone, timedelta
    d = datetime.now(EST).replace(hour=0, minute=0, second=0, microsecond=0)
    d = d - timedelta(days=days)
    return d.isoformat()


async def _fetch_company(
    client: httpx.AsyncClient,
    sub: str, wdn: str, board: str, display: str
) -> list[dict]:
    async with _SEM:
        jobs = []
        seen: set[str] = set()

        for term in SEARCH_TERMS:
            try:
                api_url = f"https://{sub}.{wdn}.myworkdayjobs.com/wday/cxs/{sub}/{board}/jobs"
                payload = {
                    "limit": 20,
                    "offset": 0,
                    "searchText": term,
                    "appliedFacets": {},
                }
                resp = await client.post(api_url, json=payload)
                if resp.status_code in (404, 403, 400, 410):
                    break  # company slug wrong — skip all terms
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("jobPostings", []):
                    title = item.get("title", "")
                    if not is_relevant_title(title):
                        continue

                    from scrapers.base import CUTOFF_HOURS
                    days = _parse_posted_days(item.get("postedOn", ""))
                    # Allow up to 3 days on backend (frontend applies fine-grained filter)
                    # Using 3 days ensures '2 Days Ago' jobs always get through
                    if days > max(3, CUTOFF_HOURS // 24):
                        continue

                    ext_path = item.get("externalPath", "")
                    if not ext_path:
                        continue
                    job_url = f"https://{sub}.{wdn}.myworkdayjobs.com/{board}{ext_path}"
                    if job_url in seen:
                        continue

                    loc = item.get("locationsText", "")
                    country = detect_country(loc, default="USA" if not loc else "")
                    if country not in ("USA", "India", "Remote"):
                        continue

                    days = _parse_posted_days(item.get("postedOn", ""))
                    seen.add(job_url)
                    jobs.append(JobData(
                        title=title,
                        company=display,
                        url=job_url,
                        source="Workday",
                        description="",
                        location=loc,
                        country=country,
                        salary="",
                        remote="remote" in loc.lower(),
                        posted_at=_days_ago_to_iso(days),  # ✅ now stores actual date
                    ).to_dict())

            except Exception:
                break

        return jobs


async def fetch(settings: dict) -> list[dict]:
    wd_slugs = settings.get("_wd_slugs")
    if wd_slugs:
        # Build a lookup from DB slugs → COMPANIES entries so we keep wdn/board/display
        _lookup = {sub: (sub, wdn, board, display) for sub, wdn, board, display in COMPANIES}
        companies = [_lookup[s] for s in wd_slugs if s in _lookup]
        # Any DB slugs not in hardcoded list — use sensible defaults
        for s in wd_slugs:
            if s not in _lookup:
                companies.append((s, "wd5", "External", s.replace("-", " ").title()))
    else:
        companies = COMPANIES

    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        tasks = [
            _fetch_company(client, sub, wdn, board, display)
            for sub, wdn, board, display in companies
        ]
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

    print(f"[Workday] {len(jobs)} jobs from {len(companies)} companies")
    return jobs

