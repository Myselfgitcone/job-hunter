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

# OR-chain alternatives: "OR N years" within 60 chars — no-degree path
_OR_PREFIX_RE = re.compile(r"\bor\b", re.I)
# Degree-substitution context: "Bachelor's + 10 yrs OR Master's + 8 yrs" — the
# real bar is the LOWEST degree path, not the max.
_DEGREE_CTX_RE = re.compile(
    r"\b(bachelor|master|phd|doctorate|advanced\s+degree|graduate\s+degree)\b", re.I)
# Degree-alternative "N years work experience" when degree/equivalent precedes it
_DEGREE_PREFIX_RE = re.compile(r"\b(?:degree|equivalent)\b", re.I)
_WORK_EXP_SUFFIX_RE = re.compile(r"^\s*work\s+experience\b", re.I)
# Company-history noise: "voted employer for over/more than 15 years"
_FOR_OVER_RE = re.compile(r"\bfor\s+(?:over|more\s+than)\s*$", re.I)
# Grade-table header: "Data Engineer IV " immediately before a year mention
_GRADE_LABEL_RE = re.compile(
    r"\b(?:engineer|developer|analyst|scientist|architect|specialist|level)\s+"
    r"(?:IX|VIII|VII|VI|IV|V|III|II|I)\s*\d*\s*$",
    re.I,
)
# Semicolon-separated degree alternatives in grade tables: "in related field; N years"
_IN_FIELD_SEMI_RE = re.compile(r"\bin\s+related\s+field\s*;", re.I)

# Preferred / nice-to-have years must NOT inflate the required bar.
# Catches inline "(preferred)", "is a plus", "nice to have", and whole
# "Preferred Qualifications" sections — but never bare "plus" (that would
# wrongly kill "Bachelor's plus 5 years").
_PREFERRED_RE = re.compile(
    r"\b(preferred|nice[\s-]*to[\s-]*have|good[\s-]*to[\s-]*have|desired|ideally|bonus"
    r"|(?:is\s+|would\s+be\s+)?a\s+plus)\b", re.I)
_REQUIRED_RE = re.compile(r"\b(required|must\s+have|minimum\b)\b", re.I)


def _is_preferred_context(text: str, start: int, end: int) -> bool:
    """True if this year mention is a preferred/nice-to-have, not a hard requirement."""
    # Inline after the number: "10 years of leadership (preferred)" / "... is a plus".
    # Clip at the clause/sentence end so a LATER "Preferred:" sentence can't taint
    # a required number ("5 years experience. Preferred: 8 years" keeps the 5).
    suf = re.split(r"[.\n;•]", text[end:end + 50], 1)[0]
    mp = _PREFERRED_RE.search(suf)
    if mp:
        mr = _REQUIRED_RE.search(suf)
        if mr is None or mp.start() < mr.start():
            return True
    # Section/context: whichever qualifier appears most recently BEFORE the number
    # wins. A "Preferred Qualifications:" header within ~250 chars suppresses it,
    # unless a "Required" marker sits between the header and the number.
    before = text[:start]
    rpos = ppos = None
    for mm in _REQUIRED_RE.finditer(before):
        rpos = mm.start()
    for mm in _PREFERRED_RE.finditer(before):
        ppos = mm.start()
    if ppos is not None and (rpos is None or ppos > rpos) and (start - ppos) <= 250:
        return True
    return False

# "5+ years", "3-5 years", "3 to 5 years", "at least 4 years",
# "minimum of 6 years", "5 yrs", "seven (7) years", "5-plus years",
# "8 or more years"
_YEARS_RE = re.compile(
    r"(?:at least|minimum(?: of)?|min\.?)?\s*"
    r"(\d{1,2})(?!\d)\)?\s*"
    r"(?:\+|plus|or\s+more|(?:-|–|to)\s*(?:plus\s*)?(\d{1,2})?\s*(?:\+)?)?\s*\)?\s*"
    r"(?:years?|yrs?)\b(?!\s*\)?\s*(?:degree|college|program|university|bachelor|master|phd|old\b|ago\b))",
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
    degree_vals: list[int] = []
    for m in _YEARS_RE.finditer(text):
        try:
            lo = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if not (0 <= lo <= 15):
            continue
        prefix60 = text[max(0, m.start() - 60):m.start()]
        prefix80 = text[max(0, m.start() - 80):m.start()]
        prefix25 = text[max(0, m.start() - 25):m.start()]
        suffix = text[m.end():m.end() + 25]
        # Degree-substitution context: a degree named just before or after the
        # number ("Master's degree and 8 years" / "8 years with a Master's").
        deg_ctx = bool(_DEGREE_CTX_RE.search(prefix60)
                       or _DEGREE_CTX_RE.search(text[m.end():m.end() + 40]))
        # Company-history: "voted employer for over 15 years"
        if lo >= 10 and _FOR_OVER_RE.search(prefix25):
            continue
        # Grade-table header: "Data Engineer IV 9 years"
        if _GRADE_LABEL_RE.search(prefix25):
            continue
        # Grade-table semicolon alt: "Bachelors in related field; N years with Masters"
        if _IN_FIELD_SEMI_RE.search(prefix60):
            continue
        # No-degree OR-chain alternatives: "OR 7 years", "OR 11 years standalone".
        # Only when the OR sits IMMEDIATELY before the number — a wider window
        # ate real requirements ("...or equivalent experience in lieu of degree.
        # 7 years of experience..." lost the 7 → tray fell to a partial number).
        # Degree-context numbers are EXEMPT — "or Master's and 8 years" is a real
        # substitution path, not noise, and must survive to the min() rule below.
        if lo >= 4 and _OR_PREFIX_RE.search(text[max(0, m.start() - 12):m.start()]) and not deg_ctx:
            continue
        # "N years work experience" when degree/equivalent precedes it
        if _WORK_EXP_SUFFIX_RE.match(suffix) and _DEGREE_PREFIX_RE.search(prefix80):
            continue
        # Preferred / nice-to-have years don't set the required bar
        if _is_preferred_context(text, m.start(), m.end()):
            continue
        candidates.append(lo)
        if deg_ctx:
            degree_vals.append(lo)

    if not candidates:
        return ""
    # Degree-substitution JDs ("Bachelor's + 10 yrs OR Master's + 8 yrs") state
    # the SAME requirement at several degree levels — the real bar is the lowest
    # path. Only applies when 2+ distinct degree-context numbers exist.
    if len(degree_vals) >= 2 and min(degree_vals) < max(degree_vals):
        return bucket_for_years(min(degree_vals))
    # Otherwise: JDs mention several partials ("5+ years total, 2+ years cloud")
    # — the highest explicit number is the core requirement
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
                              api_key: str, provider: str, model: str,
                              keys=None) -> str:
    """Ask the AI to estimate minimum required years from title + JD.
    Returns a tray or "" on failure. Pass keys (ModelKeys) so the call
    routes to the direct provider API instead of OpenRouter (+5.5% fee)."""
    from ai.llm import chat
    text = _TAG_RE.sub(" ", description or "")[:6000]
    try:
        raw = await chat(
            system=("You estimate the minimum years of professional experience "
                    "a job requires, based on its title and description. "
                    "Consider seniority words (junior, senior, lead, principal) "
                    "and the scope of responsibilities. "
                    "Reply with ONLY a single integer (0-20). No other text."),
            user=f"Title: {title}\n\nDescription:\n{text}",
            api_key=api_key, provider=provider, model=model, max_tokens=8,
            keys=keys, pass_name="exp-sweep",
            # Tiny call (outputs one integer). A 90s-per-request × 3-retry stack
            # blew past the caller's 120s asyncio.wait_for cap and logged
            # "Timed out inferring exp". 25s × 3 attempts ≈ 79s < 120s cap.
            timeout=25,
        )
        m = re.search(r"\d{1,2}", raw or "")
        if not m:
            return ""
        n = int(m.group(0))
        return bucket_for_years(min(n, 20))
    except Exception:
        return ""
