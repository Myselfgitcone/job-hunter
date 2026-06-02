"""
Oracle Jobs — careers.oracle.com public JSON API (ORC/Taleo).
No auth required for public listings.
"""
import httpx
import asyncio
from scrapers.base import JobData, detect_country, is_relevant_title

SEARCH_URL = "https://careers.oracle.com/en/sites/jobsearch/jobs"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://careers.oracle.com/",
}

SEARCH_TERMS = ["data engineer", "senior data engineer"]


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
        for term in SEARCH_TERMS:
            for offset in [0, 25]:
                try:
                    resp = await client.get(SEARCH_URL, params={
                        "keyword": term,
                        "mode": "location",
                        "lastSelectedFacet": "",
                        "offset": offset,
                        "limit": 25,
                    })
                    if resp.status_code != 200:
                        break

                    data = resp.json()
                    postings = data.get("requisitionList", []) or data.get("jobs", [])
                    if not postings:
                        break

                    for item in postings:
                        title = item.get("Title", "") or item.get("title", "")
                        if not is_relevant_title(title):
                            continue

                        req_id = item.get("Id", "") or item.get("id", "")
                        if not req_id:
                            continue
                        job_url = f"https://careers.oracle.com/en/sites/jobsearch/job/{req_id}"
                        if job_url in seen:
                            continue
                        seen.add(job_url)

                        # Location
                        loc_parts = []
                        city = item.get("PrimaryCity", "") or item.get("city", "")
                        state = item.get("PrimaryState", "") or item.get("state", "")
                        country_raw = item.get("PrimaryCountry", "") or item.get("country", "")
                        if city:
                            loc_parts.append(city)
                        if state:
                            loc_parts.append(state)
                        if country_raw:
                            loc_parts.append(country_raw)
                        loc_str = ", ".join(p for p in loc_parts if p)
                        country = detect_country(loc_str, default="USA")
                        if country not in ("USA", "India", "Remote"):
                            continue

                        is_remote = "remote" in loc_str.lower() or bool(item.get("IsRemote", False))
                        posted = item.get("PostedDate", "") or item.get("postedDate", "") or ""
                        desc = item.get("ShortDescription", "") or item.get("description", "") or ""

                        jobs.append(JobData(
                            title=title,
                            company="Oracle",
                            url=job_url,
                            source="Oracle",
                            description=str(desc)[:3000],
                            location=loc_str,
                            country=country,
                            salary="",
                            remote=is_remote,
                            posted_at=str(posted),
                        ).to_dict())

                except Exception as e:
                    print(f"[Oracle] error offset={offset} term='{term}': {e}")
                    break

                await asyncio.sleep(0.3)

    print(f"[Oracle] {len(jobs)} jobs")
    return jobs
