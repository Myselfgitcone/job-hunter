import httpx
from scrapers.base import JobData, is_relevant_title, is_recent
import html
import re

BASE_URL = "https://www.themuse.com/api/public/jobs"
CATEGORIES = ["Data Science", "Data Analytics", "Engineering"]


def _strip_html(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def fetch(settings: dict) -> list[dict]:
    jobs: list[JobData] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=20) as client:
        for category in CATEGORIES:
            try:
                for page in range(0, 3):
                    resp = await client.get(BASE_URL, params={
                        "category": category,
                        "page": page,
                        "descending": "True",
                    })
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("results", [])
                    if not items:
                        break

                    for item in items:
                        title = item.get("name", "")
                        if not is_relevant_title(title):
                            continue
                        refs = item.get("refs", {})
                        url = refs.get("landing_page", "")
                        if not url or url in seen_urls:
                            continue

                        posted = item.get("publication_date", "")
                        if not is_recent(posted):
                            continue

                        company = item.get("company", {}).get("name", "Unknown")
                        locations = item.get("locations", [])
                        location = locations[0].get("name", "") if locations else ""
                        levels = item.get("levels", [])
                        description_raw = item.get("contents", "")
                        description = _strip_html(description_raw)

                        seen_urls.add(url)
                        jobs.append(JobData(
                            title=title,
                            company=company,
                            url=url,
                            source="TheMuse",
                            description=description,
                            location=location,
                            remote="remote" in location.lower() or "remote" in title.lower(),
                            posted_at=posted,
                        ))
            except Exception as e:
                print(f"[TheMuse] error for '{category}': {e}")

    return [j.to_dict() for j in jobs]
