import html as _html_mod
import httpx
from bs4 import BeautifulSoup
import re

# Tags that are never part of the JD content
_JUNK_TAGS = ["script", "style", "nav", "header", "footer", "form", "button",
              "svg", "iframe", "noscript", "aside", "select", "input"]

# Selectors commonly wrapping the JD on ATS/career pages — first good match wins
_JD_SELECTORS = [
    # Greenhouse new format (job-boards.greenhouse.io)
    ".job__description",
    "[class*='job__description']",
    # Generic selectors
    "[class*='job-description']",
    "[class*='jobDescription']",
    "[class*='job_description']",
    "[data-testid*='description']",
    "[class*='posting-description']",
    "[class*='description']",
    "article",
    "main",
    "[role='main']",
]

# Lines of page chrome that survive extraction — drop them from text fallback
_CHROME_RE = re.compile(
    r"^(apply now|apply|share on:?|share|terms of service|privacy|cookies|"
    r"powered by .*|back to jobs|see all jobs|©.*)$", re.I)

# Bot-wall / JS-gate stubs — saving these would overwrite a real JD with junk
_JUNK_RE = re.compile(
    r"unsupported browser|supported browser listed|use a supported browser|"
    r"browser is not supported|update your browser|upgrade your browser|"
    r"enable javascript|javascript is (?:disabled|required|not enabled)|"
    r"download (?:firefox|chrome|internet explorer)", re.I)


def looks_like_junk(text: str) -> bool:
    """True when extracted content is a bot-wall stub or nav-only shell."""
    plain = re.sub(r"<[^>]+>", " ", text or "")
    if _JUNK_RE.search(plain[:5000]):
        return True
    if len(plain.strip()) < 200:
        return True
    # Nav-only shell: most lines are short link-style text (< 50 chars),
    # no substantial paragraph (no line > 120 chars).
    lines = [l.strip() for l in plain.splitlines() if l.strip()]
    if not lines:
        return True
    short = sum(1 for l in lines if len(l) < 50)
    has_paragraph = any(len(l) > 120 for l in lines)
    if short / len(lines) > 0.80 and not has_paragraph:
        return True
    return False


def _strip_attrs(node) -> None:
    """Remove all attributes (inline styles, classes) so site CSS can't leak in.
    Keep only href on links."""
    for tag in node.find_all(True):
        href = tag.get("href") if tag.name == "a" else None
        tag.attrs = {"href": href} if href else {}


def _pick_jd_node(soup):
    """Find the smallest container that holds the actual JD content."""
    for sel in _JD_SELECTORS:
        try:
            cands = soup.select(sel)
        except Exception:
            continue
        cands = [c for c in cands if len(c.get_text(strip=True)) >= 300]
        if cands:
            # Smallest qualifying container = most specific to the JD
            return min(cands, key=lambda c: len(c.get_text(strip=True)))
    return soup.body or soup


_GH_URL_RE   = re.compile(r"(?:job-)?boards\.greenhouse\.io/([^/]+)/jobs/(\d+)", re.I)
_LEVER_URL_RE = re.compile(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})", re.I)
_ASHBY_URL_RE = re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", re.I)


async def _fetch_lever_api(company: str, job_id: str) -> dict | None:
    """Lever public JSON API — returns full JD without JS rendering."""
    url = f"https://api.lever.co/v0/postings/{company}/{job_id}"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as c:
            r = await c.get(url, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None
            data = r.json()
        # Lever response: {"text": title, "descriptionPlain": "...", "lists": [...]}
        parts: list[str] = []
        desc = data.get("descriptionPlain") or data.get("description") or ""
        if desc:
            parts.append(desc)
        for lst in data.get("lists", []):
            title = lst.get("text", "")
            items = lst.get("content", "")
            if title:
                parts.append(f"\n{title}\n{items}")
        text = "\n\n".join(parts).strip()
        if len(text) < 200:
            return None
        return {"description": text[:25000]}
    except Exception as e:
        print(f"[jd_fetcher] Lever API error ({company}/{job_id}): {e}")
        return None


async def _fetch_ashby_api(company: str, job_id: str) -> dict | None:
    """Ashby public API — returns structured job data."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}/posting/{job_id}"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as c:
            r = await c.get(url, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None
            data = r.json()
        job = data.get("job", data)
        desc = job.get("descriptionHtml") or job.get("descriptionPlain") or job.get("description") or ""
        if not desc or len(desc.strip()) < 200:
            return None
        return {"description": desc[:25000]}
    except Exception as e:
        print(f"[jd_fetcher] Ashby API error ({company}/{job_id}): {e}")
        return None


async def _fetch_greenhouse_api(company: str, job_id: str) -> dict | None:
    """Use Greenhouse public JSON API — no JS rendering needed.
    Tries both API endpoints: boards-api (classic) and job-boards-api (new format)."""
    endpoints = [
        f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}",
        f"https://job-boards.greenhouse.io/{company}/jobs/{job_id}",  # new embed URL
    ]
    for api_url in endpoints:
        try:
            async with httpx.AsyncClient(follow_redirects=True) as c:
                r = await c.get(api_url, timeout=15.0,
                                headers={"User-Agent": "Mozilla/5.0",
                                         "Accept": "application/json, text/html"})
                if r.status_code != 200:
                    continue
                # JSON response (boards-api)
                if "application/json" in r.headers.get("content-type", ""):
                    data = r.json()
                    content = data.get("content", "")
                    if not content or len(content) < 200:
                        continue
                    html = _html_mod.unescape(content)
                    plain = re.sub(r"<[^>]+>", " ", html)
                    if len(plain.strip()) < 200:
                        continue
                    return {"description": html[:25000]}
        except Exception as e:
            print(f"[jd_fetcher] Greenhouse API error ({company}/{job_id}) at {api_url}: {e}")
    return None


async def fetch_full_jd(url: str) -> dict | None:
    """
    Fetch the job page and return the JD as clean HTML (preserves headings,
    bullets, paragraphs — frontend renders it with .jd-html styles).
    Greenhouse: uses public JSON API (no JS rendering needed).
    Others: HTML scrape with BeautifulSoup.
    Returns: {"description": str} or None.
    """
    # ATS-specific JSON APIs — much more reliable than HTML scraping
    # Greenhouse
    m = _GH_URL_RE.search(url or "")
    if m:
        result = await _fetch_greenhouse_api(m.group(1), m.group(2))
        if result:
            return result

    # Lever
    m = _LEVER_URL_RE.search(url or "")
    if m:
        result = await _fetch_lever_api(m.group(1), m.group(2))
        if result:
            return result

    # Ashby
    m = _ASHBY_URL_RE.search(url or "")
    if m:
        result = await _fetch_ashby_api(m.group(1), m.group(2))
        if result:
            return result

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(_JUNK_TAGS):
            tag.decompose()

        node = _pick_jd_node(soup)

        # Kill page-chrome elements (footer links, share rows, apply buttons)
        for tag in node.find_all(["a", "p", "span", "div", "li"]):
            txt = tag.get_text(strip=True)
            if txt and len(txt) <= 40 and _CHROME_RE.match(txt):
                tag.decompose()

        _strip_attrs(node)

        html = str(node).strip()
        plain = node.get_text(separator="\n", strip=True)

        # Bot-wall stub or nav-only shell → fail loudly, never save junk
        if looks_like_junk(plain):
            print(f"[jd_fetcher] junk/bot-wall page detected for {url}")
            return None

        # Structured content present → return HTML so headings/bullets render
        if len(plain) >= 200 and re.search(r"<(h[1-6]|ul|ol|li|p)\b", html, re.I):
            return {"description": html[:25000]}

        # Fallback: plain text, minus obvious page chrome
        lines = [ln for ln in plain.split("\n") if not _CHROME_RE.match(ln.strip())]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        return {"description": text[:25000]} if len(text.strip()) >= 200 else None
    except Exception as e:
        print(f"[jd_fetcher] error fetching {url}: {e}")
        return None
