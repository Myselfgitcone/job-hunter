"""
Meta (Facebook) Jobs — metacareers.com public GraphQL API.
No auth required for public job listings.
"""
import httpx
import asyncio
import json
from scrapers.base import JobData, detect_country, is_relevant_title

GQL_URL = "https://www.metacareers.com/graphql"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://www.metacareers.com/jobs",
    "Origin": "https://www.metacareers.com",
}

SEARCH_TERMS = ["data engineer", "senior data engineer"]


async def _search(client: httpx.AsyncClient, term: str, results_per_page: int = 40) -> list[dict]:
    """POST to Meta's GraphQL to search jobs."""
    payload = {
        "variables": json.dumps({
            "search_input": {
                "q": term,
                "divisions": [],
                "offices": [],
                "roles": [],
                "leadership_levels": [],
                "saved_jobs": [],
                "saved_searches": [],
                "sub_teams": [],
                "teams": [],
                "is_leadership": False,
                "is_remote_only": False,
                "sort_by_new": True,
                "page": 0,
                "results_per_page": results_per_page,
            }
        }),
        "doc_id": "8807708415952871",   # public doc_id for job search
    }
    resp = await client.post(GQL_URL, data=payload)
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
        return data.get("data", {}).get("job_search", {}).get("jobs", [])
    except Exception:
        return []


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
        for term in SEARCH_TERMS:
            try:
                items = await _search(client, term)
                for item in items:
                    title = item.get("title", "")
                    if not is_relevant_title(title):
                        continue

                    job_id = item.get("id", "")
                    if not job_id:
                        continue
                    job_url = f"https://www.metacareers.com/jobs/{job_id}/"
                    if job_url in seen:
                        continue
                    seen.add(job_url)

                    # Locations
                    loc_list = item.get("locations", []) or []
                    loc_str = ", ".join(loc_list) if loc_list else ""
                    is_remote = item.get("is_remote", False) or "remote" in loc_str.lower()
                    country = detect_country(loc_str, default="USA" if (is_remote or not loc_str) else "")
                    if country not in ("USA", "India", "Remote"):
                        continue

                    desc = item.get("description", "") or ""
                    if isinstance(desc, dict):
                        desc = json.dumps(desc)
                    posted = item.get("posted_date", "") or item.get("post_date", "") or ""

                    jobs.append(JobData(
                        title=title,
                        company="Meta",
                        url=job_url,
                        source="Meta",
                        description=str(desc)[:10000],
                        location=loc_str,
                        country=country,
                        salary="",
                        remote=is_remote,
                        posted_at=str(posted),
                    ).to_dict())

            except Exception as e:
                print(f"[Meta] error for term='{term}': {e}")

            await asyncio.sleep(0.5)

    print(f"[Meta] {len(jobs)} jobs")
    return jobs
