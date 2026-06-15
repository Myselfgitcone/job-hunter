import httpx
from datetime import datetime, timezone
from scrapers.base import JobData, is_relevant_title, is_recent, detect_country, SEARCH_TERMS


def _normalize_dt(iso: str) -> str:
    """Parse any ISO datetime and return UTC ISO string with +00:00."""
    if not iso:
        return iso
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return iso

# USA + India only
COUNTRIES = [
    ("us", "USA"),
    ("in", "India"),
]


async def fetch(settings: dict) -> list[dict]:
    app_id  = settings.get("adzuna_app_id", "")
    app_key = settings.get("adzuna_app_key", "")
    if not app_id or not app_key:
        return []

    jobs: list[JobData] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=20) as client:
        for country_code, country_name in COUNTRIES:
            url_base = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
            for term in SEARCH_TERMS:
                try:
                    resp = await client.get(url_base, params={
                        "app_id": app_id,
                        "app_key": app_key,
                        "what": term,
                        "max_days_old": 2,
                        "results_per_page": 50,
                        "content-type": "application/json",
                    })
                    resp.raise_for_status()
                    data = resp.json()

                    for item in data.get("results", []):
                        url = item.get("redirect_url", "")
                        if not url or url in seen_urls:
                            continue
                        title = item.get("title", "")
                        if not is_relevant_title(title):
                            continue
                        posted = _normalize_dt(item.get("created", ""))
                        if not is_recent(posted):
                            continue

                        seen_urls.add(url)
                        location = item.get("location", {}).get("display_name", "")
                        salary_min = item.get("salary_min")
                        salary_max = item.get("salary_max")
                        salary = ""
                        if salary_min and salary_max:
                            sym = "$" if country_code in ("us", "ca", "au", "sg") else (
                                  "£" if country_code == "gb" else "€" if country_code in ("de","nl","fr","pl") else "₹" if country_code == "in" else "$")
                            salary = f"{sym}{int(salary_min):,} – {sym}{int(salary_max):,}"
                        elif salary_min:
                            salary = f"{int(salary_min):,}+"

                        jobs.append(JobData(
                            title=title,
                            company=item.get("company", {}).get("display_name", "Unknown"),
                            url=url,
                            source="Adzuna",
                            description=item.get("description", ""),
                            location=location,
                            country=country_name,
                            salary=salary,
                            remote="remote" in title.lower() or "remote" in item.get("description", "").lower(),
                            posted_at=posted,
                        ))
                except Exception as e:
                    print(f"[Adzuna/{country_code}] error for '{term}': {e}")

    return [j.to_dict() for j in jobs]
