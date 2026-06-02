"""
SmartRecruiters — public search API, no auth required.
https://api.smartrecruiters.com/v1/postings?q=...
"""
import httpx
from datetime import datetime, timezone, timedelta
from scrapers.base import JobData, detect_country, CUTOFF_HOURS, SEARCH_TERMS

BASE = "https://api.smartrecruiters.com/v1/postings"
COUNTRIES = [("us", "USA"), ("in", "India")]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def _is_recent(date_str: str) -> bool:
    if not date_str:
        return True
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    except Exception:
        return True


async def fetch(settings: dict) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        for country_code, country_label in COUNTRIES:
            for term in SEARCH_TERMS:
                try:
                    resp = await client.get(BASE, params={
                        "q": term,
                        "limit": 50,
                        "country": country_code.upper(),
                    })
                    resp.raise_for_status()
                    data = resp.json()

                    def _is_relevant(title: str) -> bool:
                        from scrapers.base import is_relevant_title
                        return is_relevant_title(title)

                    for item in data.get("content", []):
                        job_id  = item.get("id", "")
                        url     = f"https://jobs.smartrecruiters.com/oneclick-apply?token={job_id}"
                        ref_url = item.get("ref", url)
                        if not ref_url or ref_url in seen:
                            continue

                        title_check = item.get("name", "")
                        if not _is_relevant(title_check):
                            continue

                        posted = item.get("releasedDate", "")
                        if not _is_recent(posted):
                            continue

                        seen.add(ref_url)
                        company  = item.get("company", {}).get("name", "Unknown")
                        title    = item.get("name", "")
                        loc_data = item.get("location", {})
                        location = ", ".join(filter(None, [
                            loc_data.get("city", ""),
                            loc_data.get("region", ""),
                            loc_data.get("country", ""),
                        ]))
                        remote   = item.get("typeOfEmployment", {}).get("id", "") == "temporary" or \
                                   "remote" in (item.get("name","") + location).lower()

                        country = detect_country(location, default=country_label)
                        if country not in ("USA", "India"):
                            continue

                        jobs.append(JobData(
                            title=title,
                            company=company,
                            url=ref_url,
                            source="SmartRecruiters",
                            description="",
                            location=location,
                            country=country,
                            salary="",
                            remote=remote,
                            posted_at=posted,
                        ).to_dict())

                except Exception as e:
                    print(f"[SmartRecruiters/{country_code}/{term}] error: {e}")

    print(f"[SmartRecruiters] {len(jobs)} jobs")
    return jobs
