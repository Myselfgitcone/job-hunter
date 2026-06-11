"""
Extract required years-of-experience from a job description.

Buckets (fine-grained trays):
  0-2, 2-4, 4-5, 5-6, 6-7, 7-8, 8-10, 10-13, 13-15, 15+

Resolution order per job:
  1. Regex over JD text ("5+ years", "3-6 years", ...) — free, precise
  2. FJ's coarse AI value ("0-2"/"2-5"/"5-10"/"10+") mapped to a tray
  3. AI inference from title + JD when nothing is stated (background sweep)
"""
import re

_TAG_RE = re.compile(r"<[^>]+>")

# "5+ years", "3-5 years", "3 to 5 years", "at least 4 years",
# "minimum of 6 years", "5 yrs", "seven (7) years"
_YEARS_RE = re.compile(
    r"(?:at least|minimum(?: of)?|min\.?)?\s*"
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*"
    r"(?:\+)?\s*(?:years?|yrs?)\b",
    re.I,
)

TRAYS = ["0-2", "2-4", "4-5", "5-6", "6-7", "7-8", "8-10", "10-13", "13-15", "15+"]

# FJ coarse buckets → nearest tray (by minimum of the coarse range)
COARSE_MAP = {"0-2": "0-2", "2-5": "2-4", "5-10": "5-6", "10+": "10-13"}


def bucket_for_years(n: int) -> str:
    if n < 2:   return "0-2"
    if n < 4:   return "2-4"
    if n == 4:  return "4-5"
    if n == 5:  return "5-6"
    if n == 6:  return "6-7"
    if n == 7:  return "7-8"
    if n < 10:  return "8-10"
    if n < 13:  return "10-13"
    if n < 15:  return "13-15"
    return "15+"


def extract_experience_level(description: str) -> str:
    """Return a tray ("0-2".."15+") from stated years, or "" if none found."""
    if not description:
        return ""
    text = _TAG_RE.sub(" ", description)

    candidates: list[int] = []
    for m in _YEARS_RE.finditer(text):
        try:
            lo = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if 0 < lo <= 20:  # "30 years" etc. = company age, not a requirement
            candidates.append(lo)

    if not candidates:
        return ""
    # JDs mention several ("5+ years total", "2+ years cloud") — the highest
    # explicit number is the core requirement
    return bucket_for_years(max(candidates))


def resolve_experience_level(current: str, description: str) -> str:
    """Best non-AI answer: regex from JD, else mapped coarse value, else
    keep current if it's already a valid tray, else ""."""
    rx = extract_experience_level(description or "")
    if rx:
        return rx
    cur = (current or "").strip()
    if cur in COARSE_MAP:
        return COARSE_MAP[cur]
    if cur in TRAYS:
        return cur
    return ""


async def infer_experience_ai(title: str, description: str,
                              api_key: str, provider: str, model: str) -> str:
    """Ask the AI to estimate minimum required years from title + JD.
    Returns a tray or "" on failure."""
    from ai.llm import chat
    text = _TAG_RE.sub(" ", description or "")[:1500]
    try:
        raw = await chat(
            system=("You estimate the minimum years of professional experience "
                    "a job requires, based on its title and description. "
                    "Consider seniority words (junior, senior, lead, principal) "
                    "and the scope of responsibilities. "
                    "Reply with ONLY a single integer (0-20). No other text."),
            user=f"Title: {title}\n\nDescription:\n{text}",
            api_key=api_key, provider=provider, model=model, max_tokens=8,
        )
        m = re.search(r"\d{1,2}", raw or "")
        if not m:
            return ""
        n = int(m.group(0))
        return bucket_for_years(min(n, 20))
    except Exception:
        return ""
