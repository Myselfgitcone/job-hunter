import httpx
from bs4 import BeautifulSoup
import re

# Tags that are never part of the JD content
_JUNK_TAGS = ["script", "style", "nav", "header", "footer", "form", "button",
              "svg", "iframe", "noscript", "aside", "select", "input"]

# Selectors commonly wrapping the JD on ATS/career pages — first good match wins
_JD_SELECTORS = [
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


async def fetch_full_jd(url: str) -> dict | None:
    """
    Fetch the job page and return the JD as clean HTML (preserves headings,
    bullets, paragraphs — frontend renders it with .jd-html styles).
    Falls back to plain text if the page has no usable structure.
    Returns: {"description": str} or None.
    """
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
        text_len = len(node.get_text(strip=True))
        # Structured content present → return HTML so headings/bullets render
        if text_len >= 200 and re.search(r"<(h[1-6]|ul|ol|li|p)\b", html, re.I):
            return {"description": html[:25000]}

        # Fallback: plain text, minus obvious page chrome
        text = node.get_text(separator="\n", strip=True)
        lines = [ln for ln in text.split("\n") if not _CHROME_RE.match(ln.strip())]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        return {"description": text[:25000]} if text.strip() else None
    except Exception as e:
        print(f"[jd_fetcher] error fetching {url}: {e}")
        return None
