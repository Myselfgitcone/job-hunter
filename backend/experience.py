"""
Extract required years-of-experience from a job description.

FantasticJobs supplies AI-extracted experience_level buckets
("0-2", "2-5", "5-10", "10+"); other sources don't. This regex layer
fills the same field from JD text so the years filter works everywhere.
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


def _bucket(min_years: int) -> str:
    if min_years < 2:
        return "0-2"
    if min_years < 5:
        return "2-5"
    if min_years < 10:
        return "5-10"
    return "10+"


def extract_experience_level(description: str) -> str:
    """Return an experience bucket ("0-2"/"2-5"/"5-10"/"10+") or "" if no
    years requirement is stated in the text."""
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
    return _bucket(max(candidates))
