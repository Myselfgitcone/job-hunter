"""
Jobo.world — unified job search API.
GET https://connect.jobo.world/api/jobs
Covers 57+ ATS platforms: Workday, Greenhouse, Lever, Ashby, iCIMS, etc.
Requires API key from jobo.world (free tier available).
"""
from zoneinfo import ZoneInfo
EST = ZoneInfo('America/New_York')
import httpx
from datetime import datetime, timezone, timedelta
from scrapers.base import JobData, detect_country, is_relevant_title, SEARCH_TERMS, CUTOFF_HOURS

BASE = "https://connect.jobo.world/api/jobs"

LOCATIONS = ["United States"]
MAX_PAGES = 3   # up to 300 jobs per search term


async def fetch(settings: dict) -> list[dict]:
    # Hardcoded for immediate use
    api_key = "jbe_live_dHsv8OABhAt5bDAt0f8Vz_HnmxU1mG5thcZbz2u8WH9ovWaFApEKpeA9opxU0srXE"
    if not api_key:
        print("[Jobo] No API key configured — skipping")
        return []

    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    now_utc = datetime.now(timezone.utc)
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
                            "page_size": 100,
                            "page": page,
                        })
                        if resp.status_code == 401:
                            print("[Jobo] Invalid API key")
                            return jobs
                        if resp.status_code == 402:
                            print("[Jobo] Insufficient credits")
                            return jobs
                        resp.raise_for_status()
                        data = resp.json()

                        # Log credit usage
                        credits_left = resp.headers.get("X-Credits-Balance", "?")
                        credits_used = resp.headers.get("X-Credits-Deducted", "?")
                        print(f"[Jobo] term={term!r} page={page} credits_used={credits_used} balance={credits_left}")

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

                            # ── STRICT 14-DAY NUKE RULE ──
                            # If Jobo provides a date and it's older than 14 days,
                            # throw the entire job in the trash immediately.
                            posted_at = ""
                            raw_date = item.get("date_posted", "")
                            if raw_date:
                                try:
                                    pub_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                                    age_days = (now_utc - pub_dt).days
                                    if age_days > 14:
                                        continue  # NUKE — ghost job
                                    if 0 <= age_days <= 14:
                                        posted_at = pub_dt.isoformat()
                                except Exception:
                                    pass

                            # ── Location parsing ──
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

                            # ── Salary parsing ──
                            comp = item.get("compensation", {}) or {}
                            salary = ""
                            if comp.get("min") and comp.get("max"):
                                sym = "$" if comp.get("currency", "USD") == "USD" else comp.get("currency", "$")
                                salary = f"{sym}{int(comp['min']):,} – {sym}{int(comp['max']):,}"

                            # ── Description ──
                            desc = item.get("description", "") or ""

                            # ── Remote detection ──
                            work_model = item.get("work_model", "") or ""
                            is_remote = work_model.lower() in ("remote", "hybrid")

                            # ── ATS source tag ──
                            ats_source = item.get("source", "")

                            seen.add(apply_url)
                            jobs.append(JobData(
                                title=title,
                                company=item.get("company", {}).get("name", "Unknown") if isinstance(item.get("company"), dict) else str(item.get("company", "Unknown")),
                                url=apply_url,
                                source="Jobo",
                                description=desc,
                                location=loc_str,
                                country=country,
                                salary=salary,
                                remote=is_remote,
                                posted_at=posted_at,
                            ).to_dict())

                        total_pages = data.get("total_pages", 1)
                        if page >= total_pages or page >= MAX_PAGES:
                            break
                        page += 1

                    except Exception as e:
                        print(f"[Jobo] error term={term!r} page={page}: {e}")
                        break

    print(f"[Jobo] {len(jobs)} jobs (after 14-day filter)")
    return jobs
