import httpx
from bs4 import BeautifulSoup
from scrapers.base import JobData, is_relevant_title
import re

SEARCH_TERMS = ["data+engineer", "etl+engineer", "analytics+engineer"]
BASE_URL = "https://www.simplyhired.com/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch(settings: dict) -> list[dict]:
    jobs: list[JobData] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        for term in SEARCH_TERMS:
            try:
                resp = await client.get(BASE_URL, params={
                    "q": term.replace("+", " "),
                    "fdb": "1",   # last 24h
                })
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                cards = soup.select("article[data-jobkey]")
                for card in cards:
                    title_el = card.select_one("h2 a, h3 a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not is_relevant_title(title):
                        continue

                    href = title_el.get("href", "")
                    url = f"https://www.simplyhired.com{href}" if href.startswith("/") else href
                    if not url or url in seen_urls:
                        continue

                    company_el = card.select_one("[data-testid='companyName'], .company-name, span[class*='company']")
                    company = company_el.get_text(strip=True) if company_el else "Unknown"

                    location_el = card.select_one("[data-testid='searchSerpJobLocation'], span[class*='location']")
                    location = location_el.get_text(strip=True) if location_el else ""

                    desc_el = card.select_one("p[class*='jobDescription'], div[class*='snippet']")
                    description = desc_el.get_text(strip=True) if desc_el else ""

                    seen_urls.add(url)
                    jobs.append(JobData(
                        title=title,
                        company=company,
                        url=url,
                        source="SimplyHired",
                        description=description,
                        location=location,
                        remote="remote" in location.lower() or "remote" in title.lower(),
                        posted_at="",
                    ))
            except Exception as e:
                print(f"[SimplyHired] error for '{term}': {e}")

    return [j.to_dict() for j in jobs]
