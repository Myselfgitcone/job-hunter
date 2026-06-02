"""
IBM Jobs — ibm.com/careers public search API.
No auth required for public listings.
"""
import httpx
import asyncio
from scrapers.base import JobData, detect_country, is_relevant_title

SEARCH_URL = "https://www.ibm.com/careers/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.ibm.com/careers/",
}

SEARCH_TERMS = ["data engineer", "senior data engineer"]


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
        for term in SEARCH_TERMS:
            for start in [0, 25, 50]:
                try:
                    resp = await client.get(SEARCH_URL, params={
                        "field_keyword": term,
                        "field_country": "United States",
                        "start": start,
                        "sort": "dcdate_desc",
                    })
                    if resp.status_code != 200:
                        break

                    data = resp.json()
                    items = (
                        data.get("items", [])
                        or data.get("jobs", [])
                        or data.get("results", [])
                    )
                    if not items:
                        break

                    for item in items:
                        title = item.get("title", "")
                        if not is_relevant_title(title):
                            continue

                        job_url = item.get("url", "") or item.get("apply_url", "")
                        if not job_url:
                            continue
                        if not job_url.startswith("http"):
                            job_url = "https://www.ibm.com" + job_url
                        if job_url in seen:
                            continue
                        seen.add(job_url)

                        loc_str = item.get("location", "") or item.get("city", "") or ""
                        country = detect_country(loc_str, default="USA")
                        if country not in ("USA", "India", "Remote"):
                            continue

                        is_remote = "remote" in loc_str.lower()
                        posted = item.get("date", "") or item.get("posted_date", "") or ""
                        desc = item.get("description", "") or item.get("summary", "") or ""

                        jobs.append(JobData(
                            title=title,
                            company="IBM",
                            url=job_url,
                            source="IBM",
                            description=str(desc)[:3000],
                            location=loc_str,
                            country=country,
                            salary="",
                            remote=is_remote,
                            posted_at=str(posted),
                        ).to_dict())

                except Exception as e:
                    print(f"[IBM] error start={start} term='{term}': {e}")
                    break

                await asyncio.sleep(0.3)

        # Also try India
        for term in SEARCH_TERMS:
            try:
                resp = await client.get(SEARCH_URL, params={
                    "field_keyword": term,
                    "field_country": "India",
                    "start": 0,
                    "sort": "dcdate_desc",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", []) or data.get("jobs", []) or data.get("results", [])
                    for item in items:
                        title = item.get("title", "")
                        if not is_relevant_title(title):
                            continue
                        job_url = item.get("url", "") or item.get("apply_url", "")
                        if not job_url:
                            continue
                        if not job_url.startswith("http"):
                            job_url = "https://www.ibm.com" + job_url
                        if job_url in seen:
                            continue
                        seen.add(job_url)
                        loc_str = item.get("location", "") or ""
                        country = detect_country(loc_str, default="India")
                        jobs.append(JobData(
                            title=title,
                            company="IBM",
                            url=job_url,
                            source="IBM",
                            description="",
                            location=loc_str,
                            country=country,
                            salary="",
                            remote=False,
                            posted_at="",
                        ).to_dict())
            except Exception as e:
                print(f"[IBM India] error: {e}")

    print(f"[IBM] {len(jobs)} jobs")
    return jobs
