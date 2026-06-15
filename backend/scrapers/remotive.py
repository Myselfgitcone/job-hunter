import httpx
from scrapers.base import JobData, is_relevant_title, is_recent, detect_country

BASE_URL = "https://remotive.com/api/remote-jobs"
SEARCH_TERMS = ["data engineer"]


async def fetch(settings: dict) -> list[dict]:
    jobs: list[JobData] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=20) as client:
        for term in SEARCH_TERMS:
            try:
                resp = await client.get(BASE_URL, params={"search": term, "limit": 100})
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("jobs", []):
                    url = item.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    title = item.get("title", "")
                    if not is_relevant_title(title):
                        continue
                    posted = item.get("publication_date", "")
                    if not is_recent(posted):
                        continue

                    seen_urls.add(url)
                    loc = item.get("candidate_required_location", "Remote") or "Remote"
                    jobs.append(JobData(
                        title=title,
                        company=item.get("company_name", "Unknown"),
                        url=url,
                        source="Remotive",
                        description=item.get("description", ""),
                        location=loc,
                        country=detect_country(loc, default="Remote"),
                        salary=item.get("salary", ""),
                        remote=True,
                        posted_at=posted,
                    ))
            except Exception as e:
                print(f"[Remotive] error for '{term}': {e}")

    return [j.to_dict() for j in jobs]
