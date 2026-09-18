"""
Per-job qualification — hybrid: code decides what code can decide, the model
decides only what needs reading.

Six criteria, same names and output shape as before (the UI reads them):

  experience   code   required years from the JD (experience.py) vs the
                      candidate's real years; one year of slack
  sponsorship  code   the JD's own words (same patterns as the frontend's
                      visaCheck) plus the feed's visa flag; waived when the
                      candidate needs no sponsorship
  location     code   remote / US / country field; a non-US on-site job fails
  seniority    code   title level vs years (principal/staff/director need
                      8-10, lead 6, senior 4; intern/entry fail past 5)
  job_category model  is this one of the target roles
  skills_match model  does the stack fit, given a computed keyword overlap
                      (resume_lint's JD hard-skill extractor vs profile
                      skills) as a hint; the overlap alone decides when the
                      model is unavailable

score is weighted (category 30, skills 30, experience 15, sponsorship 10,
location 10, seniority 5) rounded to 5; qualified = score >= 60 AND every
check except seniority passes.  Before 2026-09-17 all six went to a
cheap model with the first 2,000 characters of the JD: it guessed years,
missed "no sponsorship" lines below the cut, and judged skills from the intro.
"""
from ai.llm import chat
from datetime import datetime
import json
import re


_DATE_FMTS = ("%b %Y", "%B %Y", "%m/%Y", "%Y")


def _parse_month(s: str):
    s = (s or "").strip()
    if not s:
        return None
    if s.lower() in ("present", "current", "now"):
        return datetime.now()
    for f in _DATE_FMTS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _derive_total_years(exp: list) -> float:
    """Sum per-entry durations from start/end date strings. Live bug: admin
    profile entries had years=0/missing, so every job was scored against
    'Candidate has 0 years of experience' and 10k+ jobs auto-disqualified
    on the experience/seniority criteria."""
    total = 0.0
    for e in exp:
        a = _parse_month(e.get("start_date", ""))
        b = _parse_month(e.get("end_date", ""))
        if a and b and b > a:
            total += (b - a).days / 365.25
    return round(total, 1)


def _candidate_years(profile: dict) -> float | None:
    exp = profile.get("experience", []) or []
    total = sum(float(e.get("years", 0) or 0) for e in exp)
    if not total and exp:
        total = _derive_total_years(exp)
    return round(total, 1) if total else None


# ── sponsorship / clearance walls: the frontend's visaCheck patterns, in Python ──
_WALL_PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), why) for p, why in [
    (r"\bus\s*citizen(?:ship)?\s*(?:only|required|must)\b", "US citizenship required"),
    (r"\bu\.s\.?\s*citizen(?:ship)?\s*(?:only|required|must)\b", "US citizenship required"),
    (r"must\s+be\s+a?\s*u\.?s\.?\s*citizen", "US citizenship required"),
    (r"requires?\s+u\.?s\.?\s*citizenship", "US citizenship required"),
    (r"united\s+states\s+citizen(?:ship)?\s*(?:only|required)", "US citizenship required"),
    (r"\bgreen\s*card\s*(?:holder|required|only)\b", "Green Card / PR required"),
    (r"permanent\s+residen(?:t|ce)\s*(?:only|required|status)\b", "Permanent residency required"),
    (r"no\s+(?:visa\s+)?sponsorship", "No visa sponsorship"),
    (r"(?:unable|not\s+able|cannot|can'?t)\s+to\s+(?:provide|offer|sponsor|support)\s+(?:visa\s+|immigration\s+)?sponsorship", "No visa sponsorship"),
    (r"(?:unable|not\s+able)\s+to\s+sponsor", "No visa sponsorship"),
    (r"sponsorship\s+(?:is\s+)?(?:not\s+available|unavailable)", "No visa sponsorship"),
    (r"(?:does|do|will)\s+not\s+(?:provide|offer|sponsor|support)\s+(?:visa\s+|immigration\s+)?sponsorship", "No visa sponsorship"),
    (r"will\s+not\s+sponsor", "No visa sponsorship"),
    (r"visa\s+sponsorship\s+(?:is\s+)?not\s+(?:available|provided|offered)", "No visa sponsorship"),
    (r"not\s+eligible\s+for\s+(?:immigration\s+|visa\s+|employment\s+)?sponsorship", "No visa sponsorship"),
    (r"\bauthorized\s+to\s+work\s+without\s+(?:any\s+)?sponsorship\b", "Must work without sponsorship"),
    (r"without\s+(?:requiring\s+)?(?:visa\s+)?sponsorship\s+(?:now|in\s+the\s+future|at\s+any)", "No sponsorship now or later"),
    (r"\bno\s+(?:h-?1b1?|h-?4|stem\s*opt|opt|cpt|ead|gc)\b(?!\s*[-–]\s*out)(?!\s+(?:required|needed|necessary|expected|mentioned))", "No H1B / OPT (explicit)"),
    (r"(?:do(?:es)?\s*n[o']?t|will\s+not|cannot|can'?t|unable\s+to)\s+(?:accept|consider|hire|sponsor)\s+(?:h-?1b1?|opt|cpt|f-?1|visa|international)", "H1B / OPT not accepted"),
]]
_CLEARANCE_PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), why) for p, why in [
    (r"\btop\s*secret\b", "Top Secret clearance"),
    (r"\bts\/sci\b", "TS/SCI clearance"),
    (r"\bpolygraph\b", "Polygraph"),
    (r"(?:active|current|must\s+hold\s+(?:an?\s+)?(?:active\s+)?|with\s+(?:a\s+)?)(?:security|dod|secret)\s+clearance", "Security clearance"),
    (r"\b(?:security|secret|dod)\s+clearance\s+(?:is\s+)?required\b", "Security clearance"),
    (r"\bclearance\s+required\b", "Clearance required"),
    (r"position\s+of\s+public\s+trust|\bpublic\s+trust\s+(?:clearance|required|eligibility)|(?:hold|obtain)\s+(?:a\s+)?public\s+trust", "Public Trust"),
]]
_NEEDS_NO_SPONSOR_RE = re.compile(r"citizen|green\s*card|\bgc\b|permanent|lpr|no\s+sponsorship\s+needed|not\s+required", re.I)
_HAS_CLEARANCE_RE = re.compile(r"clearance|ts/sci|secret", re.I)


def _sponsorship_check(jd: str, profile: dict, job_meta: dict | None) -> tuple[bool, str]:
    visa = str(profile.get("visa_status") or "")
    needs_none = bool(_NEEDS_NO_SPONSOR_RE.search(visa))
    text = jd or ""
    for pat, why in _CLEARANCE_PATTERNS:
        if pat.search(text):
            if needs_none and _HAS_CLEARANCE_RE.search(visa):
                return True, f"{why} required; candidate holds clearance"
            return False, f"{why} required"
    walls = [why for pat, why in _WALL_PATTERNS if pat.search(text)]
    if walls:
        if needs_none:
            return True, f"{walls[0]}; candidate needs no sponsorship"
        return False, walls[0]
    if job_meta and job_meta.get("visa_sponsorship") is False and not needs_none:
        return False, "Feed marks the posting as no sponsorship"
    return True, "No citizenship, clearance or no-sponsorship wall found"


# ── location ─────────────────────────────────────────────────────────────────
_NON_US_RE = re.compile(
    r"\b(canada|india|united kingdom|\buk\b|england|london|germany|berlin|france|paris|netherlands|amsterdam|"
    r"ireland|dublin|spain|madrid|portugal|lisbon|poland|warsaw|italy|sweden|stockholm|denmark|norway|finland|"
    r"switzerland|zurich|austria|belgium|brazil|s[aã]o paulo|mexico|argentina|colombia|chile|australia|sydney|"
    r"melbourne|new zealand|singapore|japan|tokyo|korea|china|hong kong|taiwan|philippines|vietnam|indonesia|"
    r"malaysia|israel|tel aviv|uae|dubai|saudi|egypt|nigeria|kenya|south africa|bengaluru|bangalore|hyderabad|"
    r"pune|chennai|mumbai|delhi|noida|gurgaon|toronto|vancouver|montreal|serbia|belgrade|romania|bucharest|"
    r"ukraine|czech|prague|hungary|budapest|greece|turkey|istanbul)\b", re.I)
_REMOTE_RE = re.compile(r"\bremote\b|work\s+from\s+home|\bwfh\b|anywhere", re.I)
_US_RE = re.compile(r"\b(usa|u\.s\.a?\.?|united states|us[- ]based|us only)\b|\b[A-Z]{2}\b", re.I)


def _location_check(location: str, jd: str, profile: dict, job_meta: dict | None) -> tuple[bool, str]:
    loc = location or ""
    country = str((job_meta or {}).get("country") or "").strip()
    remote = bool((job_meta or {}).get("remote")) or bool(_REMOTE_RE.search(loc))
    pref = str(profile.get("location") or "").strip()
    if country:
        if country.upper() in ("USA", "US", "UNITED STATES"):
            return True, f"US posting ({loc or country})"
        if remote and not _NON_US_RE.search(loc):
            return True, f"Remote ({loc or country})"
        return False, f"Posted for {country}"
    if _NON_US_RE.search(loc):
        # "Remote Poland", "Remote Canada (ON, BC)": remote within that country,
        # not remote for a US candidate, unless the line also names the US
        if remote and _US_RE.search(loc) and not re.search(r"\b(only|based)\b", loc, re.I):
            return True, f"Remote, US included ({loc})"
        return False, (f"Remote restricted to {loc}" if remote else f"On-site outside the US ({loc})")
    return True, (f"Remote ({loc})" if remote else f"US posting ({loc or pref or 'location not stated'})")


# ── seniority ────────────────────────────────────────────────────────────────
_LEVEL_RULES: list[tuple[re.Pattern, float | None, float | None, str]] = [
    # (title pattern, min years, max years, label)
    (re.compile(r"\b(?:intern|internship|co-?op)\b", re.I), None, 1, "internship"),
    (re.compile(r"\b(?:entry[- ]level|new\s+grad|graduate|junior|jr\.?|associate)\b", re.I), None, 4, "entry-level"),
    (re.compile(r"\b(?:vp|vice\s+president|chief|head\s+of|director|fellow|distinguished)\b", re.I), 10, None, "executive"),
    (re.compile(r"\b(?:principal|staff)\b", re.I), 8, None, "principal/staff"),
    (re.compile(r"\bmanager\b", re.I), 6, None, "manager"),
    (re.compile(r"\b(?:lead|architect)\b", re.I), 5, None, "lead/architect"),
    (re.compile(r"\b(?:senior|sr\.?)\b", re.I), 4, None, "senior"),
]


def _seniority_check(title: str, years: float | None, profile: dict) -> tuple[bool, str]:
    t = title or ""
    held = " ".join(str(e.get("role") or "") for e in (profile.get("experience") or [])).lower()
    for pat, lo, hi, label in _LEVEL_RULES:
        if not pat.search(t):
            continue
        if years is None:
            return True, f"{label} title; candidate years unknown, not failed on that alone"
        if label == "manager" and re.search(r"\bmanager\b", held):
            return True, "Manager title; candidate has held a manager role"
        if lo is not None and years < lo - 1:
            return False, f"{label} title needs ~{lo}+ years; candidate has {years:g}"
        if hi is not None and years > hi:
            return False, f"{label} title; candidate has {years:g} years (overqualified)"
        return True, f"{label} title fits {years:g} years"
    return True, "Mid-level title" if years is None else f"Mid-level title fits {years:g} years"


# ── experience ───────────────────────────────────────────────────────────────
_TRAY_MIN = {"0-2": 0, "2-4": 2, "4-5": 4, "5-6": 5, "6-7": 6, "7-8": 7, "8-10": 8, "10-13": 10, "13-15": 13, "15+": 15}


_TRAY_MAX = {"0-2": 1, "2-4": 3, "4-5": 4, "5-6": 5, "6-7": 6, "7-8": 7, "8-10": 9, "10-13": 12, "13-15": 14, "15+": 40}


def _required_years(jd: str, job_meta: dict | None) -> int | None:
    """The JD's years bar. experience.py picks the tray with all its
    filtering (preferred lines, degree alternatives, company history); the
    exact number is then read back from the JD inside that tray, so "3+"
    is 3, not the tray's floor of 2 (live: a 1.5-year profile passed a 3+ ask)."""
    try:
        from experience import extract_experience_level, COARSE_MAP, _YEARS_RE, _is_preferred_context
        tray = extract_experience_level(jd or "")
        if tray:
            lo, hi = _TRAY_MIN[tray], _TRAY_MAX[tray]
            exact = []
            for m in _YEARS_RE.finditer(jd or ""):
                try:
                    n = int(m.group(1))
                except (TypeError, ValueError):
                    continue
                if lo <= n <= hi and not _is_preferred_context(jd, m.start(), m.end()):
                    exact.append(n)
            return max(exact) if exact else lo
        if job_meta:
            cur = str(job_meta.get("experience_level") or "")
            tray = COARSE_MAP.get(cur, cur if cur in _TRAY_MIN else "")
            return _TRAY_MIN.get(tray) if tray else None
        return None
    except Exception:  # noqa: BLE001
        return None


def _experience_check(jd: str, years: float | None, job_meta: dict | None) -> tuple[bool, str]:
    need = _required_years(jd, job_meta)
    if need is None:
        return True, "JD states no years requirement"
    if years is None:
        return True, f"JD asks {need}+ years; candidate years unknown, not failed on that alone"
    if years + 1 >= need:
        return True, f"{years:g} years vs {need}+ required"
    return False, f"JD asks {need}+ years; candidate has {years:g}"


# ── skills overlap (deterministic hint for the model, and the fallback) ──────
_OVERLAP_NOISE = {"linkedin", "know", "base", "ops", "role", "team", "company", "remote", "hybrid", "onsite",
                  "model", "cloud", "language", "languages", "platform", "data engineering", "data pipeline",
                  "data pipelines", "engineering", "software", "systems", "dns", "jvm", "office", "in-office"}


def _skill_overlap(jd: str, profile: dict, company: str = "", location: str = "") -> tuple[list[str], list[str]]:
    try:
        from resume_lint import extract_jd_hard_skills, _dynamic_coverage_pattern
    except Exception:  # noqa: BLE001
        return [], []
    skills = [str(s) for s in (profile.get("skills") or []) if str(s).strip()]
    blob = (" | ".join(skills) + " | " + str(profile.get("summary") or "")).lower()
    # the extractor also returns the employer, city and a few stray words
    # ("Austin", "LinkedIn", "Know"); those are not skills anyone lacks
    noise = set(_OVERLAP_NOISE)
    noise.update(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z.&'-]+", f"{company} {location}") if len(w) > 2)
    jd_skills = [s for s in extract_jd_hard_skills(jd or "") if s.lower() not in noise]
    have, miss = [], []
    for sk in jd_skills:
        try:
            (have if re.search(_dynamic_coverage_pattern(sk), blob) else miss).append(sk)
        except re.error:
            miss.append(sk)
    return have, miss


def _requirements_text(jd: str, limit: int = 12000) -> str:
    """The JD minus benefits/EEO tails, requirements first when the headers
    are recognisable; the whole (cleaned) text otherwise."""
    try:
        from resume_lint import clean_jd_html, _strip_jd_noise, _get_high_signal_text
        raw = clean_jd_html(jd or "")
        clean = _strip_jd_noise(raw)
        # a stripper that took more than a third of the posting mis-zoned it:
        # feed the whole cleaned text rather than trust the cut
        if len(clean) < 0.65 * len(raw):
            clean = raw
        high = _get_high_signal_text(clean)
        text = high if high and high != clean and len(high) > 300 else clean
        if text != clean and len(text) < limit:
            text = text + "\n\n[rest of posting]\n" + clean[: limit - len(text)]
        return text[:limit]
    except Exception:  # noqa: BLE001
        return (jd or "")[:limit]


_MODEL_SYSTEM = """You screen ONE job posting for ONE candidate. Two questions only.

Return ONLY this JSON, no markdown:
{"job_category": {"pass": true, "note": "<=15 words"},
 "must_have_missing": ["<tool or skill the posting REQUIRES that the candidate lacks>"],
 "nice_to_have_missing": ["<preferred / bonus item the candidate lacks>"],
 "summary": "one sentence: why this is or is not a fit"}

job_category: is this posting one of the candidate's TARGET ROLES, judged by the
title AND what the work is? Titles in the same family count: Analytics Engineer
counts for a Data Analyst or Data Engineer target; BI Developer for a Data
Analyst; "Software Engineer, Data Platform" for a Data Engineer; SRE for DevOps.
A different family does not: a Data Analyst posting is not a DevOps target, a
Product Manager posting is not an engineering target. Judge the ROLE only:
years, seniority, visa and location are checked separately by code and must
not influence this answer.
must_have_missing: ONLY items the requirements section states as required /
must / strong, that appear nowhere in the candidate's skills or the "candidate
has" list. A same-category tool the candidate has (AWS for a GCP ask, Redshift
for a Snowflake ask, Airflow for a Dagster ask) is NOT missing. Empty list when
the required core is covered. Code decides pass/fail from your lists."""


_PREFERRED_CTX_RE = re.compile(r"nice[- ]to[- ]have|preferred|a plus|bonus|plus:|ideally|familiarity|exposure|"
                               r"would be|is a plus|desirable|or similar|or equivalent|interest in", re.I)


def _alternatives_of(head: str, sentence: str) -> list[str]:
    """The other options in the "X, Y, or Z" group that names `head` inside
    `sentence` (a parenthesised list or the clause around it), lowercased.
    Live miss: "AI-assisted development tools (e.g., Claude Code, Cursor, or
    Amazon Q)" was demoted to nice-to-have because the sentence also
    contained an owned word elsewhere; only the listed alternatives count."""
    low = sentence.lower()
    h = head.lower()
    pos = low.find(h)
    if pos < 0:
        return []
    # the innermost parenthesis or clause that contains the head
    start = max(low.rfind("(", 0, pos), low.rfind(";", 0, pos), low.rfind(":", 0, pos), -1) + 1
    end_cands = [i for i in (low.find(")", pos), low.find(";", pos), low.find(".", pos)) if i >= 0]
    end = min(end_cands) if end_cands else len(low)
    group = re.sub(r"\b(?:e\.g\.|i\.e\.|such as|including|like)\s*,?\s*", "", low[start:end])
    opts = [o.strip(" .") for o in re.split(r",\s*|\s+or\s+|\s+and/or\s+|/|\s+and\s+", group)]
    return [o for o in opts if len(o) >= 2 and o != h and h not in o]


_YEARS_ITEM_RE = re.compile(r"\byears?\b|\byrs\b|experience\s*\(candidate", re.I)


def _required_only(item: str, jd: str) -> bool:
    """The JD names `item` and never inside a nice-to-have sentence."""
    core = re.sub(r"\s*\(.*?\)\s*", " ", item).strip()
    head = core.split(" or ")[0].split(",")[0].strip()
    if len(head) < 2:
        return False
    pat = re.compile(rf"(?<![a-z0-9]){re.escape(head.lower())}(?![a-z0-9])", re.I)
    hits = [s for s in re.split(r"(?<=[.!?•\n])\s+|\n", jd or "") if pat.search(s)]
    return bool(hits) and not any(_PREFERRED_CTX_RE.search(s) for s in hits)


def _confirm_required(items: list[str], jd: str, owned_terms: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Keep only items the JD literally names in a sentence that is not a
    nice-to-have; the rest are demoted (returned second). A years-of-
    experience line is not a skill (the experience check owns it). An item
    named in an "X or Y" sentence where the candidate owns another option in
    that sentence ("Go or Scala", candidate has Scala) is demoted too."""
    keep, demoted = [], []
    sentences = re.split(r"(?<=[.!?•\n])\s+|\n", jd or "")
    owned = [o.lower() for o in (owned_terms or []) if len(o.strip()) >= 2]
    for it in items:
        if _YEARS_ITEM_RE.search(it):
            continue
        core = re.sub(r"\s*\(.*?\)\s*", " ", it).strip()
        head = core.split(" or ")[0].split(",")[0].strip()
        if len(head) < 2:
            continue
        pat = re.compile(rf"(?<![a-z0-9]){re.escape(head.lower())}(?![a-z0-9])", re.I)
        hits = [s for s in sentences if pat.search(s)]
        if not hits:
            continue                                  # never named: dropped outright
        if all(_PREFERRED_CTX_RE.search(s) for s in hits):
            demoted.append(it)
            continue
        alt_covered = any(
            re.search(r"\bor\b|/", s, re.I) and any(
                o == alt or (len(o) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(o)}(?![a-z0-9])", alt))
                for alt in _alternatives_of(head, s) for o in owned)
            for s in hits)
        if alt_covered:
            demoted.append(it)                        # the posting accepts an alternative the candidate has
        else:
            keep.append(it)
    return keep, demoted


def _title_matches(title: str, roles: list) -> bool:
    t = (title or "").lower()
    for r in roles or []:
        term = str(r or "").lower().strip()
        if not term:
            continue
        if term == "data engineer" and (("data" in t and "engineer" in t) or "databricks" in t or "analytics engineer" in t or "mlops" in t):
            return True
        if term in t:
            return True
    return False


def _round5(x: float) -> int:
    return int(round(x / 5.0) * 5)


_WEIGHTS = {"job_category": 30, "skills_match": 30, "experience": 15, "sponsorship": 10, "location": 10, "seniority": 5}
_HARD_GATES = ("job_category", "skills_match", "experience", "sponsorship", "location")


async def qualify_job(
    profile: dict,
    job_title: str,
    job_description: str,
    company: str,
    location: str,
    api_key: str,
    provider: str,
    model: str,
    candidate_roles: list | None = None,
    keys=None,
    job_meta: dict | None = None,
) -> dict:
    """`job_meta` (optional): {"remote": bool, "country": str,
    "visa_sponsorship": bool|None, "experience_level": str} from the jobs row;
    the feed's own fields beat regex when present."""
    if candidate_roles:
        roles = [str(r) for r in candidate_roles]
    else:
        roles = [e.get("role", "") for e in profile.get("experience", []) if e.get("role")][:3]
    roles_str = ", ".join(roles) if roles else "any relevant professional role"

    years = _candidate_years(profile)
    jd = job_description or ""

    # ── the four code-decided criteria ──
    exp_ok, exp_note = _experience_check(jd, years, job_meta)
    sp_ok, sp_note = _sponsorship_check(jd, profile, job_meta)
    loc_ok, loc_note = _location_check(location, jd, profile, job_meta)
    sen_ok, sen_note = _seniority_check(job_title, years, profile)
    have, miss = _skill_overlap(jd, profile, company, location)
    ratio = len(have) / (len(have) + len(miss)) if (have or miss) else None

    # ── the two model-decided criteria ──
    held = [e.get("role", "") for e in profile.get("experience", []) if e.get("role")]
    skills = [str(s) for s in (profile.get("skills") or [])]
    user_msg = (
        f"Job: {job_title} at {company} ({location})\n\n"
        f"=== REQUIREMENTS (from the posting) ===\n{_requirements_text(jd)}\n\n"
        f"=== CANDIDATE ===\n- Target roles: {roles_str}\n"
        f"- Years: {years if years is not None else 'unknown'}\n"
        f"- Roles held: {', '.join(held[:3])}\n"
        f"- Skills: {', '.join(skills[:40])}\n\n"
        f"=== KEYWORD OVERLAP (computed) ===\n"
        f"- posting requirement words the candidate has ({len(have)}): {', '.join(have[:25]) or 'none'}\n"
        f"- posting requirement words the candidate lacks ({len(miss)}): {', '.join(miss[:25]) or 'none'}\n"
        f"- coverage: {f'{ratio:.0%}' if ratio is not None else 'n/a'}\n\n"
        "Answer the two questions. JSON only."
    )
    cat_ok = cat_note = sk_ok = sk_note = summary = None
    must_missing: list[str] | None = None
    nice_missing: list[str] = []
    try:
        # temperature 0: a screening verdict must not flip between runs
        text = await chat(system=_MODEL_SYSTEM, user=user_msg, api_key=api_key, provider=provider,
                          model=model, max_tokens=300, keys=keys, pass_name="qualify", temperature=0)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        jc = data.get("job_category") or {}
        if isinstance(jc, dict) and "pass" in jc:
            cat_ok, cat_note = bool(jc.get("pass")), str(jc.get("note") or "")
        if isinstance(data.get("must_have_missing"), list):
            must_missing = [str(x).strip() for x in data["must_have_missing"] if str(x).strip()]
            nice_missing = [str(x).strip() for x in (data.get("nice_to_have_missing") or []) if str(x).strip()]
        summary = str(data.get("summary") or "") or None
    except Exception as exc:  # noqa: BLE001 — the code path below still answers
        cat_note = sk_note = f"model unavailable ({str(exc)[:60]})"

    if cat_ok is None:
        cat_ok = _title_matches(job_title, roles)
        cat_note = cat_note or ("Title matches a target role" if cat_ok else "Title matches no target role")
    if must_missing is not None:
        # the candidate's own skills are ground truth: a "missing" item the
        # profile or the overlap already carries is struck (live: Haiku called
        # Airflow missing with Airflow in the HAS list, twice)
        owned = " | ".join(skills + have).lower()
        real_missing = [x for x in must_missing if x.lower() not in owned
                        and not re.search(rf"(?<![a-z0-9]){re.escape(x.lower())}(?![a-z0-9])", owned)]
        # and the posting itself must say it, in a required sentence: a
        # "must-have" the JD never names is the model's invention, one it names
        # only under "nice to have / plus / preferred" is not a gate
        real_missing, demoted = _confirm_required(real_missing, jd, skills + have)
        # the model's own nice-to-have list is checked the same way: an item
        # the JD names only in required sentences is a required gap (live:
        # "AI-assisted development tools" under "We're Excited About You
        # Because" was filed as nice-to-have)
        nice_owned = [x for x in nice_missing if x.lower() not in owned]
        promoted, _ = _confirm_required(nice_owned, jd, skills + have)
        promoted = [p for p in promoted if p not in real_missing and _required_only(p, jd)]
        real_missing = real_missing + promoted
        nice_missing = [x for x in nice_missing if x not in promoted] + [d for d in demoted if d not in nice_missing]
        # one confirmed gap inside a mostly-covered stack ("Spark, Airflow,
        # Trino, Iceberg" with three of four) is not a fail; two gaps, or one
        # with under half the named stack covered, is
        sk_ok = (not real_missing) or (len(real_missing) == 1 and ratio is not None and ratio >= 0.5)
        sk_note = ("Required core covered" if not real_missing else
                   ("One required gap, stack mostly covered: " if sk_ok else "Missing required: ")
                   + ", ".join(real_missing[:5]))
        if nice_missing:
            sk_note += "; nice-to-have gaps: " + ", ".join(nice_missing[:4])
    if sk_ok is None:
        sk_ok = ratio is None or ratio >= 0.35
        sk_note = sk_note or (f"Keyword overlap {ratio:.0%}" if ratio is not None else "No requirement keywords found")
    if ratio is not None:
        sk_note = f"{sk_note} (overlap {ratio:.0%})".strip()

    criteria = {
        "job_category": {"pass": cat_ok, "note": cat_note},
        "experience":   {"pass": exp_ok, "note": exp_note},
        "skills_match": {"pass": sk_ok, "note": sk_note},
        "sponsorship":  {"pass": sp_ok, "note": sp_note},
        "location":     {"pass": loc_ok, "note": loc_note},
        "seniority":    {"pass": sen_ok, "note": sen_note},
    }
    # Weighted: the two "is this the job for this person" checks carry most of
    # the score, so a wrong-family posting whose years/visa/location happen to
    # fit reads ~40, not 65. Qualified = every hard gate passes (seniority is
    # the one soft check: titles inflate) and the score clears 60.
    score = _round5(sum(w for k, w in _WEIGHTS.items() if criteria[k]["pass"]))
    qualified = score >= 60 and all(criteria[k]["pass"] for k in _HARD_GATES)
    if not sen_ok and "internship" in sen_note:
        qualified = False              # a professional is not an intern; the one hard seniority case
    if not summary:
        fails = [k for k, c in criteria.items() if not c["pass"]]
        summary = ("Fits the target role and core stack" if not fails else
                   "Fails: " + ", ".join(fails))
    return {
        "qualified": bool(qualified),
        "score": score,
        "summary": summary,
        "criteria": criteria,
        "overlap": {"have": have[:40], "missing": miss[:40]},
    }
