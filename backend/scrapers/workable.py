"""
Workable — public job search API.
https://apply.workable.com/api/v3/jobs
No auth required. Searches ALL companies using Workable ATS at once.
"""
import httpx
import asyncio
from scrapers.base import JobData, is_relevant_title, is_recent, detect_country, SEARCH_TERMS

BASE = "https://apply.workable.com/api/v3/jobs"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        for term in SEARCH_TERMS:
            token = None
            page = 0
            while page < 5:  # max 5 pages per term
                body: dict = {"query": term, "location": "", "worktype": ""}
                if token:
                    body["token"] = token

                try:
                    resp = await client.post(BASE, json=body)
                    resp.raise_for_status()
                    data = resp.json()

                    results = data.get("results", [])
                    if not results:
                        break

                    for item in results:
                        title = item.get("title", "")
                        if not is_relevant_title(title):
                            continue

                        subdomain = item.get("account", {}).get("subdomain", "")
                        shortcode = item.get("shortcode", "")
                        if not subdomain or not shortcode:
                            continue

                        url = f"https://apply.workable.com/{subdomain}/j/{shortcode}/"
                        if url in seen:
                            continue

                        loc = item.get("location", {})
                        location = ", ".join(filter(None, [
                            loc.get("city", ""),
                            loc.get("region", ""),
                            loc.get("country", ""),
                        ]))

                        country = detect_country(location, default="")
                        if country not in ("USA", "India"):
                            continue

                        posted = item.get("published_on", "")
                        if not is_recent(posted):
                            continue

                        seen.add(url)
                        company = item.get("account", {}).get("name", subdomain.title())
                        remote = bool(item.get("remote", False))

                        jobs.append(JobData(
                            title=title,
                            company=company,
                            url=url,
                            source="Workable",
                            description="",
                            location=location,
                            country=country,
                            salary="",
                            remote=remote,
                            posted_at=posted,
                        ).to_dict())

                    token = data.get("token")
                    page += 1
                    if not token:
                        break
                    await asyncio.sleep(0.3)

                except Exception as e:
                    print(f"[Workable] error for '{term}' page {page}: {e}")
                    break

    print(f"[Workable] {len(jobs)} jobs")
    return jobs
