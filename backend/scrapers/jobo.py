"""
Jobo.world — unified job search API.
GET https://connect.jobo.world/api/jobs
Covers 50+ ATS platforms: Workday, Taleo, iCIMS, SuccessFactors, Greenhouse, etc.
Requires API key from jobo.world (free tier available).
"""
import httpx
from datetime import datetime, timezone, timedelta
from scrapers.base import JobData, detect_country, is_relevant_title, SEARCH_TERMS, CUTOFF_HOURS

BASE = "https://connect.jobo.world/api/jobs"

LOCATIONS = ["United States"]
MAX_PAGES = 2   # 200 jobs/combo max → ~800 credits per full scrape


async def fetch(settings: dict) -> list[dict]:
    api_key = settings.get("jobo_api_key", "")
    if not api_key:
        return []

    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)).isoformat()
    jobs: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        for term in SEARCH_TERMS:
            for location in LOCATIONS:
                page = 1
                while page <= MAX_PAGES:
                    try:
                        resp = await client.get(BASE, params={
                            "q": term,
                            "location": location,
                            "posted_after": cutoff,
                            "page_size": 100,
                            "page": page,
                        })
                        if resp.status_code == 401:
                            print("[Jobo] Invalid API key")
                            return []
                        resp.raise_for_status()
                        data = resp.json()

                        items = data.get("jobs", [])
                        if not items:
                            break

                        for item in items:
                            title = item.get("title", "")
                            if not is_relevant_title(title):
                                continue

                            apply_url = item.get("apply_url", "")
                            if not apply_url or apply_url in seen:
                                continue

                            locs = item.get("locations", [{}])
                            loc0 = locs[0] if locs else {}
                            loc_str = ", ".join(filter(None, [
                                loc0.get("city", ""),
                                loc0.get("region", ""),
                                loc0.get("country", ""),
                            ]))
                            country = detect_country(loc_str, default="USA" if location == "United States" else "India")
                            if country not in ("USA", "India", "Remote"):
                                continue

                            comp = item.get("compensation", {})
                            salary = ""
                            if comp.get("min") and comp.get("max"):
                                sym = "$" if comp.get("currency", "USD") == "USD" else comp.get("currency", "$")
                                salary = f"{sym}{int(comp['min']):,} – {sym}{int(comp['max']):,}"

                            seen.add(apply_url)
                            jobs.append(JobData(
                                title=title,
                                company=item.get("company", {}).get("name", "Unknown"),
                                url=apply_url,
                                source="Jobo",
                                description="",
                                location=loc_str,
                                country=country,
                                salary=salary,
                                remote=item.get("work_model", "") == "remote",
                                posted_at=item.get("date_posted", ""),
                            ).to_dict())

                        total_pages = data.get("total_pages", 1)
                        if page >= total_pages or page >= MAX_PAGES:
                            break
                        page += 1

                    except Exception as e:
                        print(f"[Jobo] error: {e}")
                        break

    print(f"[Jobo] {len(jobs)} jobs")
    return jobs
