import httpx
from scrapers.base import JobData, is_relevant_title, is_recent, SEARCH_TERMS

SEARCH_API = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json",
    "x-api-key": "1YAt0R9wBg4WfsF9VB2778F5CHLAPMVW3WAZcKd8",
}


async def fetch(settings: dict) -> list[dict]:
    jobs: list[JobData] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        for term in SEARCH_TERMS:
            try:
                resp = await client.get(SEARCH_API, params={
                    "q": term,
                    "countryCode2": "US",
                    "datePosted": "ONE",
                    "pageSize": 50,
                    "language": "en",
                })
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("data", []):
                    title = item.get("title", "")
                    if not is_relevant_title(title):
                        continue
                    url = item.get("applyUrl") or item.get("jobDetailUrl", "")
                    if not url:
                        job_id = item.get("id", "")
                        url = f"https://www.dice.com/job-detail/{job_id}" if job_id else ""
                    if not url or url in seen_urls:
                        continue

                    posted = item.get("postedDate", "")
                    if not is_recent(posted):
                        continue

                    seen_urls.add(url)
                    employment_details = item.get("employmentDetails", [])
                    remote = item.get("workplaceTypes", [])
                    is_remote = any("remote" in r.lower() for r in remote) if remote else False

                    jobs.append(JobData(
                        title=title,
                        company=item.get("hiringOrganization", {}).get("name", "Unknown"),
                        url=url,
                        source="Dice",
                        description=item.get("jobDescription", ""),
                        location=item.get("jobLocation", {}).get("displayLocation", ""),
                        country="USA",
                        remote=is_remote,
                        posted_at=posted,
                    ))
            except Exception as e:
                print(f"[Dice] error for '{term}': {e}")

    return [j.to_dict() for j in jobs]
