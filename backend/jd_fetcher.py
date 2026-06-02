import httpx
import json
from bs4 import BeautifulSoup
import re


# ── ATS-specific fetchers ─────────────────────────────────────────────────────

async def _fetch_greenhouse(url: str, client: httpx.AsyncClient) -> str | None:
    """Greenhouse has a public JSON API — no scraping needed."""
    # Patterns:
    #   boards.greenhouse.io/{board}/jobs/{id}
    #   {company}.com/jobs?gh_jid={id}  (need board name from page)
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if m:
        board, job_id = m.group(1), m.group(2)
        api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        try:
            r = await client.get(api, headers={"Accept": "application/json"})
            r.raise_for_status()
            data = r.json()
            html = data.get("content", "")
            if html:
                soup = BeautifulSoup(html, "lxml")
                return _extract_clean(soup.get_text(separator="\n", strip=True))
        except Exception:
            pass
    return None


async def _fetch_lever(url: str, client: httpx.AsyncClient) -> str | None:
    """Lever exposes job JSON at {url}.json"""
    if "lever.co/" not in url:
        return None
    json_url = url.rstrip("/") + ".json"
    try:
        r = await client.get(json_url, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        # Lever structure: lists of {header, content} dicts
        parts = []
        for section in data.get("lists", []):
            parts.append(section.get("text", ""))
            for item in section.get("content", []):
                parts.append("* " + BeautifulSoup(item, "lxml").get_text(strip=True))
        for section in data.get("additional", []):
            parts.append(section.get("text", ""))
            parts.append(BeautifulSoup(section.get("content", ""), "lxml").get_text(separator="\n", strip=True))
        text = "\n".join(p for p in parts if p)
        if not text:
            # fallback: descriptionPlain
            text = data.get("descriptionPlain", "") or BeautifulSoup(data.get("description", ""), "lxml").get_text(separator="\n", strip=True)
        return _extract_clean(text) if text else None
    except Exception:
        return None


async def _fetch_workday(url: str, client: httpx.AsyncClient) -> str | None:
    """Workday embeds JSON-LD or structured job data in the page."""
    if "myworkdayjobs.com" not in url and "workday.com" not in url:
        return None
    try:
        r = await client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # Try JSON-LD first
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                desc = data.get("description", "")
                if desc and len(desc) > 100:
                    clean = BeautifulSoup(desc, "lxml").get_text(separator="\n", strip=True)
                    return _extract_clean(clean)
            except Exception:
                pass

        # Workday-specific selector
        for sel in ["[data-automation-id='jobPostingDescription']",
                    ".css-1ocdpjl", "[class*='jobDescription']"]:
            el = soup.select_one(sel)
            if el:
                text = _extract_clean(el.get_text(separator="\n", strip=True))
                if len(text) > 200:
                    return text
    except Exception:
        pass
    return None


async def _fetch_smartrecruiters(url: str, client: httpx.AsyncClient) -> str | None:
    """SmartRecruiters has a public API."""
    # careers.smartrecruiters.com/{company}/{job-id}
    m = re.search(r"smartrecruiters\.com/([^/]+)/(\d+)", url)
    if not m:
        return None
    company, job_id = m.group(1), m.group(2)
    api = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{job_id}"
    try:
        r = await client.get(api, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        sections = data.get("jobAd", {}).get("sections", {})
        parts = []
        for key in ["companyDescription", "jobDescription", "qualifications", "additionalInformation"]:
            html = sections.get(key, {}).get("text", "")
            if html:
                parts.append(BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True))
        text = "\n\n".join(parts)
        return _extract_clean(text) if text else None
    except Exception:
        return None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Stop extracting text when any of these lines appear
END_MARKERS = [
    "stats for this job",
    "salary comparison",
    "similar jobs",
    "receive similar jobs by email",
    "create alert",
    "by creating an alert",
    "jobs in each salary range",
    "follow us on linkedin",
    "get an inside look",
    "privacy notice",
    "as part of our job application process",
]

# Drop lines matching these patterns entirely
SKIP_PATTERNS = [
    r"^what\?$", r"^where\?$", r"^search$", r"^advanced$",
    r"adzuna logo", r"myadzuna", r"employers",
    r"back to last search", r"back to search",
    r"^apply for this job$",
    r"city, state or zip", r"job, company, title",
    r"^\d+ jobs?$",
]

# Per-source CSS selectors — tried in order
SELECTORS = [
    # Adzuna job description body
    ".job-description", ".jobDescription",
    "[class*='jobDesc']", "[class*='job-desc']",
    "[class*='job_desc']", "[data-testid='job-description']",
    # Indeed
    "[data-testid='jobDescriptionText']", ".jobsearch-jobDescriptionText",
    # Dice
    "[data-cy='jobDescriptionHtml']",
    # Greenhouse
    "#content", ".job__description", ".job-post",
    # Lever
    ".section-wrapper", ".posting-description",
    # Workday
    "[data-automation-id='jobPostingDescription']",
    # SmartRecruiters
    ".job-sections",
    # Generic fallbacks
    "#job-description", "#jobDescriptionText",
    "article", "main",
]


def _extract_redirect_url(soup: BeautifulSoup, base_url: str) -> str | None:
    """Extract real URL from intermediate redirect pages (Adzuna, etc.)."""
    # meta refresh: <meta http-equiv="refresh" content="5;url=...">
    meta = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"})
    if meta:
        content = meta.get("content", "")
        if "url=" in content.lower():
            real = content.split("url=", 1)[-1].strip().strip("'\"")
            if real.startswith("http"):
                return real

    # JS redirect: window.location = "..." or window.location.href = "..."
    for script in soup.find_all("script"):
        text = script.string or ""
        for pattern in [r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']',
                        r'location\.replace\(["\']([^"\']+)["\']\)']:
            m = re.search(pattern, text)
            if m:
                real = m.group(1)
                if real.startswith("http"):
                    return real

    # "view ad here" / "click here" fallback link
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = (a.get_text() or "").lower()
        if href.startswith("http") and any(kw in text for kw in ("view ad", "click here", "here", "view job")):
            if "adzuna" not in href:
                return href

    return None


def _adzuna_detail_url(url: str) -> str | None:
    """Convert Adzuna redirect/land URL → Adzuna detail page URL.
    e.g. https://www.adzuna.com/land/ad/4931234567?... → https://www.adzuna.com/details/4931234567
    """
    m = re.search(r"adzuna\.com/(?:land/ad|details)/(\d+)", url)
    if m:
        return f"https://www.adzuna.com/details/{m.group(1)}"
    return None


async def fetch_full_jd(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:

            # ── ATS-specific handlers (tried before generic scrape) ──
            for handler in [_fetch_greenhouse, _fetch_lever,
                            _fetch_workday, _fetch_smartrecruiters]:
                result = await handler(url, client)
                if result and len(result) > 150:
                    return result

            # ── Adzuna: fetch their own detail page (full JD, no JS wall) ──
            adzuna_url = _adzuna_detail_url(url)
            if adzuna_url:
                try:
                    resp = await client.get(adzuna_url)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "lxml")
                    # Adzuna detail page selector
                    for sel in [".job-description", "[class*='jobDesc']", "[class*='job-desc']",
                                "#job-description", "section.adp-body", "[itemprop='description']"]:
                        el = soup.select_one(sel)
                        if el:
                            text = _extract_clean(el.get_text(separator="\n", strip=True))
                            if len(text) > 300:
                                return text
                    # fallback: biggest block on adzuna detail page
                    candidates = soup.find_all(["div", "section"])
                    best = max(candidates, key=lambda e: len(e.get_text(strip=True)), default=None)
                    if best:
                        text = _extract_clean(best.get_text(separator="\n", strip=True))
                        if len(text) > 200:
                            return text
                except Exception:
                    pass  # fall through to generic fetch

            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Detect intermediate redirect page (Adzuna, etc.)
            body_text = soup.get_text(separator=" ", strip=True).lower()
            is_redirect_page = (
                "you are now being redirected" in body_text or
                "if you are not redirected" in body_text or
                ("every job" in body_text and "everywhere" in body_text)
            )
            if is_redirect_page:
                real_url = _extract_redirect_url(soup, str(resp.url))
                if real_url:
                    try:
                        resp = await client.get(real_url)
                        resp.raise_for_status()
                        soup = BeautifulSoup(resp.text, "lxml")
                    except Exception:
                        pass  # fall through to original page parse

            # Nuke obvious noise elements
            for tag in soup(["script", "style", "nav", "header", "footer",
                             "aside", "iframe", "noscript"]):
                tag.decompose()

            # Try targeted selectors first
            for selector in SELECTORS:
                el = soup.select_one(selector)
                if el:
                    text = _extract_clean(el.get_text(separator="\n", strip=True))
                    if len(text) > 300:
                        return text

            # Fallback: biggest block
            candidates = soup.find_all(["div", "section", "article"])
            best = max(candidates, key=lambda e: len(e.get_text(strip=True)), default=None)
            if best:
                text = _extract_clean(best.get_text(separator="\n", strip=True))
                if len(text) > 100:
                    return text

    except Exception as e:
        return f"[Could not load: {e}]"

    return "[Description not available — use Paste JD manually]"


def _extract_clean(raw: str) -> str:
    lines = raw.split("\n")
    kept = []

    for line in lines:
        line = line.strip()

        # Stop at end markers
        lower = line.lower()
        if any(lower.startswith(m) or m in lower for m in END_MARKERS):
            break

        # Skip noise lines
        if any(re.search(p, lower) for p in SKIP_PATTERNS):
            continue

        # Skip very short junk (single words, symbols)
        if len(line) < 3:
            continue

        kept.append(line)

    result = "\n".join(kept)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()[:8000]
