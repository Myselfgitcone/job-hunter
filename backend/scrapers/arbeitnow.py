import httpx
from scrapers.base import JobData, is_relevant_title, is_recent, detect_country
from datetime import datetime, timezone

BASE_URL = "https://www.arbeitnow.com/api/job-board-api"


async def fetch(settings: dict) -> list[dict]:
    jobs: list[JobData] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            page = 1
            while page <= 3:
                resp = await client.get(BASE_URL, params={"page": page})
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                if not items:
                    break

                for item in items:
                    url = item.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    title = item.get("title", "")
                    if not is_relevant_title(title):
                        continue

                    # arbeitnow uses unix timestamp
                    created_ts = item.get("created_at", 0)
                    if created_ts:
                        posted_iso = datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()
                    else:
                        posted_iso = ""
                    if not is_recent(posted_iso):
                        continue

                    seen_urls.add(url)
                    loc = item.get("location", "") or ""
                    jobs.append(JobData(
                        title=title,
                        company=item.get("company_name", "Unknown"),
                        url=url,
                        source="Arbeitnow",
                        description=item.get("description", ""),
                        location=loc,
                        country=detect_country(loc, default="Germany"),  # Arbeitnow is mostly Germany
                        remote=item.get("remote", False),
                        posted_at=posted_iso,
                    ))
                page += 1
        except Exception as e:
            print(f"[Arbeitnow] error: {e}")

    return [j.to_dict() for j in jobs]
