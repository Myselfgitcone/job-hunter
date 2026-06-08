import httpx
import json
from bs4 import BeautifulSoup
import re
import markdownify

def _to_markdown(html_str: str) -> str:
    """Convert HTML to clean Markdown preserving lists/headers."""
    md = markdownify.markdownify(html_str, heading_style="ATX", strip=["a", "img", "script", "style"])
    # clean up excess newlines
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()

# ── ATS-specific fetchers ─────────────────────────────────────────────────────

async def _fetch_greenhouse(url: str, client: httpx.AsyncClient) -> dict | None:
    """Greenhouse has a public JSON API — no scraping needed."""
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if m:
        board, job_id = m.group(1), m.group(2)
        api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        try:
            r = await client.get(api, headers={"Accept": "application/json"})
            r.raise_for_status()
            data = r.json()
            html = data.get("content", "")
            date = data.get("updated_at") or data.get("first_published") or ""
            if html:
                desc = _extract_clean(_to_markdown(html))
                return {"description": desc, "date": date}
        except Exception:
            pass
    return None

async def _fetch_lever(url: str, client: httpx.AsyncClient) -> dict | None:
    """Lever exposes job JSON at {url}.json"""
    if "lever.co/" not in url:
        return None
    json_url = url.rstrip("/") + ".json"
    try:
        r = await client.get(json_url, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        date = data.get("createdAt", "")
        parts = []
        for section in data.get("lists", []):
            parts.append("### " + section.get("text", ""))
            for item in section.get("content", []):
                parts.append("- " + BeautifulSoup(item, "lxml").get_text(strip=True))
        for section in data.get("additional", []):
            parts.append("### " + section.get("text", ""))
            parts.append(_to_markdown(section.get("content", "")))
        text = "\n".join(p for p in parts if p)
        if not text:
            # fallback
            desc_html = data.get("description", "")
            if desc_html:
                text = _to_markdown(desc_html)
            else:
                text = data.get("descriptionPlain", "")
        if text:
            return {"description": _extract_clean(text), "date": date}
    except Exception:
        pass
    return None

async def _fetch_workday(url: str, client: httpx.AsyncClient) -> dict | None:
    """Workday embeds JSON-LD or structured job data in the page."""
    if "myworkdayjobs.com" not in url and "workday.com" not in url:
        return None
    try:
        r = await client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # Try JSON-LD first
        date = ""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                date = data.get("datePosted", "")
                desc = data.get("description", "")
                if desc and len(desc) > 100:
                    clean = _to_markdown(desc)
                    return {"description": _extract_clean(clean), "date": date}
            except Exception:
                pass

        # Workday-specific selector
        for sel in ["[data-automation-id='jobPostingDescription']",
                    ".css-1ocdpjl", "[class*='jobDescription']"]:
            el = soup.select_one(sel)
            if el:
                text = _extract_clean(_to_markdown(str(el)))
                if len(text) > 200:
                    return {"description": text, "date": date}
    except Exception:
        pass
    return None

async def _fetch_smartrecruiters(url: str, client: httpx.AsyncClient) -> dict | None:
    """SmartRecruiters has a public API."""
    m = re.search(r"smartrecruiters\.com/([^/]+)/(\d+)", url)
    if not m:
        return None
    company, job_id = m.group(1), m.group(2)
    api = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{job_id}"
    try:
        r = await client.get(api, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        date = data.get("releasedDate", "")
        sections = data.get("jobAd", {}).get("sections", {})
        parts = []
        for key in ["companyDescription", "jobDescription", "qualifications", "additionalInformation"]:
            title = sections.get(key, {}).get("title", "")
            if title:
                parts.append(f"### {title}")
            html = sections.get(key, {}).get("text", "")
            if html:
                parts.append(_to_markdown(html))
        text = "\n\n".join(parts)
        if text:
            return {"description": _extract_clean(text), "date": date}
    except Exception:
        pass
    return None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

END_MARKERS = [
    "stats for this job", "salary comparison", "similar jobs",
    "receive similar jobs by email", "create alert",
    "by creating an alert", "jobs in each salary range",
    "follow us on linkedin", "get an inside look",
    "privacy notice", "as part of our job application process",
]

SKIP_PATTERNS = [
    r"^what\?$", r"^where\?$", r"^search$", r"^advanced$",
    r"adzuna logo", r"myadzuna", r"employers",
    r"back to last search", r"back to search",
    r"^apply for this job$", r"city, state or zip", r"job, company, title",
    r"^\d+ jobs?$",
]

SELECTORS = [
    ".job-description", ".jobDescription",
    "[class*='jobDesc']", "[class*='job-desc']",
    "[class*='job_desc']", "[data-testid='job-description']",
    "[data-testid='jobDescriptionText']", ".jobsearch-jobDescriptionText",
    "[data-cy='jobDescriptionHtml']",
    "#content", ".job__description", ".job-post",
    ".section-wrapper", ".posting-description",
    "[data-automation-id='jobPostingDescription']",
    ".job-sections",
    "#job-description", "#jobDescriptionText",
    "article", "main",
]

def _extract_redirect_url(soup: BeautifulSoup, base_url: str) -> str | None:
    meta = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"})
    if meta:
        content = meta.get("content", "")
        if "url=" in content.lower():
            real = content.split("url=", 1)[-1].strip().strip("'\"")
            if real.startswith("http"):
                return real
    for script in soup.find_all("script"):
        text = script.string or ""
        for pattern in [r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']',
                        r'location\.replace\(["\']([^"\']+)["\']\)']:
            m = re.search(pattern, text)
            if m:
                real = m.group(1)
                if real.startswith("http"):
                    return real
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = (a.get_text() or "").lower()
        if href.startswith("http") and any(kw in text for kw in ("view ad", "click here", "here", "view job")):
            if "adzuna" not in href:
                return href
    return None

def _adzuna_detail_url(url: str) -> str | None:
    m = re.search(r"adzuna\.com/(?:land/ad|details)/(\d+)", url)
    if m:
        return f"https://www.adzuna.com/details/{m.group(1)}"
    return None

async def fetch_full_jd(url: str) -> dict:
    """Returns dict: {'description': str, 'date': str}"""
    try:
        async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
            # ATS API Handlers
            for handler in [_fetch_greenhouse, _fetch_lever, _fetch_workday, _fetch_smartrecruiters]:
                res = await handler(url, client)
                if res and res.get("description") and len(res["description"]) > 150:
                    return res

            # Adzuna Detail Page
            adzuna_url = _adzuna_detail_url(url)
            if adzuna_url:
                try:
                    resp = await client.get(adzuna_url)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "lxml")
                    for sel in [".job-description", "[class*='jobDesc']", "[class*='job-desc']",
                                "#job-description", "section.adp-body", "[itemprop='description']"]:
                        el = soup.select_one(sel)
                        if el:
                            text = _extract_clean(_to_markdown(str(el)))
                            if len(text) > 300:
                                return {"description": text, "date": ""}
                    candidates = soup.find_all(["div", "section"])
                    best = max(candidates, key=lambda e: len(e.get_text(strip=True)), default=None)
                    if best:
                        text = _extract_clean(_to_markdown(str(best)))
                        if len(text) > 200:
                            return {"description": text, "date": ""}
                except Exception:
                    pass

            # Generic HTML scraper
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            body_text = soup.get_text(separator=" ", strip=True).lower()
            is_redirect = ("you are now being redirected" in body_text or "if you are not redirected" in body_text)
            if is_redirect:
                real_url = _extract_redirect_url(soup, str(resp.url))
                if real_url:
                    try:
                        resp = await client.get(real_url)
                        resp.raise_for_status()
                        soup = BeautifulSoup(resp.text, "lxml")
                    except Exception:
                        pass

            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]):
                tag.decompose()

            # Try targeted selectors first
            for selector in SELECTORS:
                el = soup.select_one(selector)
                if el:
                    text = _extract_clean(_to_markdown(str(el)))
                    if len(text) > 300:
                        return {"description": text, "date": ""}

            # Fallback: biggest block
            candidates = soup.find_all(["div", "section", "article"])
            best = max(candidates, key=lambda e: len(e.get_text(strip=True)), default=None)
            if best:
                text = _extract_clean(_to_markdown(str(best)))
                if len(text) > 100:
                    return {"description": text, "date": ""}

    except Exception as e:
        return {"description": f"[Could not load: {e}]", "date": ""}

    return {"description": "[Description not available — use Paste JD manually]", "date": ""}

_GARBAGE_LINES = re.compile(
    r"^(\*\*[:\-\*]*\*\*|[-\*]{1,3}|[:\-\|]{1,3}|\*+|_+)$"
)
_NA_VALUES = {"na", "n/a", "n.a.", "not available", "not applicable", "none", "tbd", "-", "—"}

def _extract_clean(raw: str) -> str:
    lines = raw.split("\n")
    kept = []
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if any(lower.startswith(m) or m in lower for m in END_MARKERS):
            break
        if any(re.search(p, lower) for p in SKIP_PATTERNS):
            continue
        # Drop lines that are pure markdown garbage (---, **:**, *, etc.)
        if _GARBAGE_LINES.match(stripped):
            continue
        kept.append(line)
    result = "\n".join(kept)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.strip()[:8000]

    # Reject if result is just an NA placeholder or too short to be useful
    if result.lower() in _NA_VALUES or len(result) < 80:
        return ""
    return result
