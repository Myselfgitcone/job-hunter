"""
Netflix Jobs — jobs.netflix.com public JSON API.
No auth required.
"""
import httpx
import asyncio
from scrapers.base import JobData, detect_country, is_relevant_title

SEARCH_URL = "https://jobs.netflix.com/api/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://jobs.netflix.com/",
}

SEARCH_TERMS = ["data engineer", "senior data engineer"]


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        for term in SEARCH_TERMS:
            for page in range(1, 4):
                try:
                    resp = await client.get(SEARCH_URL, params={
                        "q": term,
                        "page": page,
                    })
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    records = data.get("records", [])
                    if not records:
                        break

                    for item in records:
                        title = item.get("job_title", "")
                        if not is_relevant_title(title):
                            continue

                        ext_id = item.get("external_id", "")
                        if not ext_id:
                            continue
                        job_url = f"https://jobs.netflix.com/jobs/{ext_id}"
                        if job_url in seen:
                            continue
                        seen.add(job_url)

                        loc_str = item.get("location", "") or ""
                        if isinstance(loc_str, list):
                            loc_str = ", ".join(loc_str)
                        is_remote = "remote" in loc_str.lower()
                        country = detect_country(loc_str, default="USA" if (is_remote or not loc_str) else "")
                        if country not in ("USA", "India", "Remote"):
                            continue

                        posted = item.get("posted_at", "") or ""
                        desc = item.get("job_summary", "") or item.get("description", "") or ""

                        jobs.append(JobData(
                            title=title,
                            company="Netflix",
                            url=job_url,
                            source="Netflix",
                            description=str(desc)[:10000],
                            location=loc_str,
                            country=country,
                            salary="",
                            remote=is_remote,
                            posted_at=str(posted),
                        ).to_dict())

                except Exception as e:
                    print(f"[Netflix] error page={page} term='{term}': {e}")
                    break

                await asyncio.sleep(0.3)

    print(f"[Netflix] {len(jobs)} jobs")
    return jobs
