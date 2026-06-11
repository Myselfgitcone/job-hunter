import httpx
from bs4 import BeautifulSoup
import re

async def fetch_full_jd(url: str) -> dict | None:
    """
    Basic HTML-to-text fallback fetcher.
    Returns: {"description": str} or None.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            
            # Simple text extraction
            soup = BeautifulSoup(resp.text, "lxml")
            
            # Remove scripts and styles
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.decompose()
                
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            
            return {"description": text[:25000]}
    except Exception as e:
        print(f"[jd_fetcher] error fetching {url}: {e}")
        return None
