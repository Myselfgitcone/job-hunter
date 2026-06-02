"""
Google Jobs — careers.google.com public JSON API.
No auth required. Searches for data engineer roles.
"""
import httpx
import asyncio
from scrapers.base import JobData, detect_country, is_relevant_title

BASE = "https://careers.google.com/api/jobs/jobs-v1/search/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://careers.google.com/",
}

SEARCH_TERMS = ["data engineer", "senior data engineer"]


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        for term in SEARCH_TERMS:
            for location in ["United States", "India"]:
                try:
                    resp = await client.get(BASE, params={
                        "q": term,
                        "hl": "en_US",
                        "jlo": "en_US",
                        "location": location,
                        "page_size": 50,
                    })
                    if resp.status_code != 200:
                        continue
                    data = resp.json()

                    for item in data.get("jobs", []):
                        title = item.get("title", "")
                        if not is_relevant_title(title):
                            continue

                        job_id = item.get("id", "")
                        if not job_id:
                            continue
                        job_url = f"https://careers.google.com/jobs/results/{job_id}"
                        if job_url in seen:
                            continue
                        seen.add(job_url)

                        locs = item.get("locations", [])
                        loc_str = ", ".join(
                            l.get("display", "") for l in locs if l.get("display")
                        ) if locs else location
                        country = detect_country(loc_str, default="USA")

                        # Google returns description as HTML
                        desc_html = item.get("description", "")
                        # Basic HTML strip
                        import re
                        desc = re.sub(r"<[^>]+>", " ", desc_html).strip()[:10000]

                        posted = item.get("publish_date", "")

                        is_remote = any(
                            "remote" in l.get("display", "").lower()
                            for l in locs
                        )

                        jobs.append(JobData(
                            title=title,
                            company="Google",
                            url=job_url,
                            source="Google",
                            description=desc,
                            location=loc_str,
                            country=country,
                            salary="",
                            remote=is_remote,
                            posted_at=posted,
                        ).to_dict())

                except Exception as e:
                    print(f"[Google] error for term='{term}' loc='{location}': {e}")
                    continue

                await asyncio.sleep(0.5)  # be polite to Google

    print(f"[Google] {len(jobs)} jobs")
    return jobs
