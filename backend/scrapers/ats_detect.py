"""
Detects which ATS a company uses from their careers page URL.
Supports: Greenhouse, Lever, Ashby, Workday, BambooHR, SmartRecruiters, Workable
"""
import re
import httpx
from typing import Optional


def detect_from_url(url: str) -> Optional[dict]:
    """
    Fast URL-pattern based detection (no network call).
    Returns: { ats, slug, name } or None
    """
    url = url.strip().rstrip("/")

    patterns = [
        # Greenhouse
        (r"boards\.greenhouse\.io/([^/?#]+)", "greenhouse"),
        (r"greenhouse\.io/jobs\?.*token=([^&]+)", "greenhouse"),
        (r"grnh\.se/", "greenhouse"),  # short URL, no slug
        # Lever
        (r"jobs\.lever\.co/([^/?#]+)", "lever"),
        # Ashby
        (r"([^.]+)\.ashbyhq\.com", "ashby"),
        (r"jobs\.ashbyhq\.com/([^/?#]+)", "ashby"),
        # Workday
        (r"([^.]+)\.myworkdayjobs\.com", "workday"),
        (r"myworkdayjobs\.com/([^/?#]+)", "workday"),
        # BambooHR
        (r"([^.]+)\.bamboohr\.com", "bamboohr"),
        # SmartRecruiters
        (r"jobs\.smartrecruiters\.com/([^/?#]+)", "smartrecruiters"),
        # Workable
        (r"apply\.workable\.com/([^/?#]+)", "workable"),
        (r"([^.]+)\.workable\.com", "workable"),
    ]

    for pattern, ats in patterns:
        m = re.search(pattern, url, re.IGNORECASE)
        if m:
            groups = m.groups()
            slug = groups[0] if groups else ""
            # Clean up slug
            slug = slug.strip("/").split("/")[0].split("?")[0]
            return {
                "ats": ats,
                "slug": slug,
                "name": slug.replace("-", " ").replace("_", " ").title(),
                "detected_from": "url_pattern",
            }
    return None


async def detect_from_page(url: str) -> Optional[dict]:
    """
    Fetches the careers page and looks for ATS embed scripts.
    Used when URL pattern detection fails.
    """
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url)
            html = resp.text.lower()

        # Greenhouse embed
        if "greenhouse.io" in html or "grnh.se" in html:
            m = re.search(r'boards\.greenhouse\.io/([a-z0-9_-]+)', html)
            if m:
                return {"ats": "greenhouse", "slug": m.group(1),
                        "name": m.group(1).replace("-", " ").title(), "detected_from": "page_html"}

        # Lever embed
        if "lever.co" in html:
            m = re.search(r'jobs\.lever\.co/([a-z0-9_-]+)', html)
            if m:
                return {"ats": "lever", "slug": m.group(1),
                        "name": m.group(1).replace("-", " ").title(), "detected_from": "page_html"}

        # Ashby embed
        if "ashbyhq.com" in html:
            m = re.search(r'(?:jobs\.ashbyhq\.com|ashbyhq\.com/posting-api)/([a-z0-9_-]+)', html)
            if m:
                return {"ats": "ashby", "slug": m.group(1),
                        "name": m.group(1).replace("-", " ").title(), "detected_from": "page_html"}

        # Workday
        if "myworkdayjobs.com" in html:
            m = re.search(r'([a-z0-9]+)\.myworkdayjobs\.com', html)
            if m:
                return {"ats": "workday", "slug": m.group(1),
                        "name": m.group(1).replace("-", " ").title(), "detected_from": "page_html"}

    except Exception as e:
        print(f"[ATSDetect] page fetch failed for {url}: {e}")
    return None


async def detect(url: str) -> Optional[dict]:
    """Try URL pattern first, fall back to page fetch."""
    result = detect_from_url(url)
    if result:
        return result
    return await detect_from_page(url)
