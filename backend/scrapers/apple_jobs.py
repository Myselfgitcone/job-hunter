"""
Apple Jobs — jobs.apple.com public JSON API.
No auth required.
"""
import httpx
import asyncio
from scrapers.base import JobData, detect_country, is_relevant_title

SEARCH_URL = "https://jobs.apple.com/api/role/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://jobs.apple.com/",
}

SEARCH_TERMS = ["data engineer", "senior data engineer"]


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        for term in SEARCH_TERMS:
            for page in range(1, 4):   # up to 3 pages = 60 results
                try:
                    resp = await client.get(SEARCH_URL, params={
                        "page": page,
                        "query": term,
                        "locale": "en-US",
                        "filters[postingcountry][]": "USA",
                    })
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    results = data.get("searchResults", [])
                    if not results:
                        break

                    for item in results:
                        title = item.get("postingTitle", "")
                        if not is_relevant_title(title):
                            continue

                        position_id = item.get("positionId", "")
                        if not position_id:
                            continue
                        job_url = f"https://jobs.apple.com/en-us/details/{position_id}"
                        if job_url in seen:
                            continue
                        seen.add(job_url)

                        locs = item.get("locations", [])
                        loc_str = ", ".join(
                            l.get("name", "") for l in locs if l.get("name")
                        ) if locs else ""
                        country = detect_country(loc_str, default="USA")

                        posted = item.get("dateCreated", "")
                        is_remote = item.get("homeOffice", False) or "remote" in loc_str.lower()

                        jobs.append(JobData(
                            title=title,
                            company="Apple",
                            url=job_url,
                            source="Apple",
                            description="",  # fetched later via fetch-jd
                            location=loc_str,
                            country=country,
                            salary="",
                            remote=is_remote,
                            posted_at=posted,
                        ).to_dict())

                except Exception as e:
                    print(f"[Apple] error page={page} term='{term}': {e}")
                    break

                await asyncio.sleep(0.3)

    # Also fetch India jobs
    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        for term in SEARCH_TERMS:
            try:
                resp = await client.get(SEARCH_URL, params={
                    "page": 1,
                    "query": term,
                    "locale": "en-US",
                    "filters[postingcountry][]": "IND",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("searchResults", []):
                        title = item.get("postingTitle", "")
                        if not is_relevant_title(title):
                            continue
                        position_id = item.get("positionId", "")
                        if not position_id:
                            continue
                        job_url = f"https://jobs.apple.com/en-us/details/{position_id}"
                        if job_url in seen:
                            continue
                        seen.add(job_url)
                        locs = item.get("locations", [])
                        loc_str = ", ".join(l.get("name", "") for l in locs if l.get("name"))
                        country = detect_country(loc_str, default="India")
                        jobs.append(JobData(
                            title=title,
                            company="Apple",
                            url=job_url,
                            source="Apple",
                            description="",
                            location=loc_str,
                            country=country,
                            salary="",
                            remote=False,
                            posted_at=item.get("dateCreated", ""),
                        ).to_dict())
            except Exception as e:
                print(f"[Apple India] error: {e}")

    print(f"[Apple] {len(jobs)} jobs")
    return jobs
