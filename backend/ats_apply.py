"""
Auto-apply Phase 1 — Greenhouse / Lever / Ashby.

Reality (verified against vendor docs 2026-07-10):
  * All three OFFICIAL application-submit APIs require the COMPANY'S own API
    key (Greenhouse Job Board API POST, Lever Postings POST, Ashby
    applicationForm.submit). A third-party job tool never has those keys.
  * What IS public: form-schema reads (Greenhouse ?questions=true, Lever
    posting JSON, Ashby posting-api job info) and the same form endpoints a
    candidate's browser posts when they click Apply on the hosted board.
  * Some boards protect that public form with reCAPTCHA/hCaptcha. We NEVER
    bypass a captcha: if one is detected the job is returned as
    method="manual" and the UI sends the user to the ATS page with every
    field pre-filled for copy/paste.

Flow: detect_ats(url) → fetch_form(...) → prefill(...) → user reviews/edits
in the Apply panel → POST /api/jobs/{id}/apply with confirm=true → submit().
Submission is per-application and always user-confirmed — no bulk fire.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

_TIMEOUT = httpx.Timeout(20.0)
_UA = {"User-Agent": "Mozilla/5.0 (job-hunter apply; +https://thejobhunter.app)"}


# ── ATS detection ─────────────────────────────────────────────────────────────

@dataclass
class AtsRef:
    ats: str                    # "greenhouse" | "lever" | "ashby"
    board: str                  # board token / site slug / org slug
    posting_id: str             # job id / posting uuid / jobPosting id
    url: str                    # original job url


_PATTERNS = [
    # boards.greenhouse.io/{board}/jobs/{id} and job-boards.greenhouse.io/...
    ("greenhouse", re.compile(
        r"https?://(?:boards|job-boards)\.(?:eu\.)?greenhouse\.io/([^/?#]+)/jobs/(\d+)", re.I)),
    # company career sites embedding greenhouse: ...?gh_jid=123 with board in path is
    # not recoverable generically — skipped in phase 1.
    ("lever", re.compile(
        r"https?://jobs\.(?:eu\.)?lever\.co/([^/?#]+)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)),
    ("ashby", re.compile(
        r"https?://jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)),
]


def detect_ats(url: str) -> Optional[AtsRef]:
    """Return AtsRef when the job URL is a directly-appliable Phase-1 ATS."""
    if not url:
        return None
    for ats, pat in _PATTERNS:
        m = pat.search(url)
        if m:
            return AtsRef(ats=ats, board=m.group(1), posting_id=m.group(2), url=url)
    return None


# Company careers pages that EMBED a greenhouse board carry the job id in a
# ?gh_jid= param (217 live jobs, e.g. samsara.com/...?gh_jid=8039914) but hide
# the board token inside the page's embed markup. Token extraction is
# structural — scan the page for greenhouse embed references, then VERIFY each
# candidate against the public boards-api before trusting it.
_GH_JID = re.compile(r"[?&]gh_jid=(\d+)")
_GH_TOKEN_PATTERNS = [
    re.compile(r"boards\.greenhouse\.io/embed/job_board(?:/js)?\?[^\"'\s]*for=([A-Za-z0-9_-]+)", re.I),
    re.compile(r"(?:boards|job-boards)\.(?:eu\.)?greenhouse\.io/([A-Za-z0-9_-]+)/jobs", re.I),
    re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.I),
    re.compile(r"greenhouse\.io/embed/job_app\?[^\"'\s]*for=([A-Za-z0-9_-]+)", re.I),
]
# host → verified board token, so repeated jobs from one company cost one fetch
_gh_token_cache: dict[str, str] = {}


async def resolve_ats(url: str, company: str = "") -> Optional[AtsRef]:
    """detect_ats + embedded-board resolution. Async because embedded
    detection may fetch the careers page once (cached per host)."""
    ref = detect_ats(url)
    if ref:
        return ref
    m = _GH_JID.search(url or "")
    if not m:
        return None
    gh_jid = m.group(1)
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()

    async def _verified(token: str) -> bool:
        api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{gh_jid}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as cli:
                return (await cli.get(api)).status_code == 200
        except Exception:
            return False

    cached = _gh_token_cache.get(host)
    if cached and await _verified(cached):
        return AtsRef(ats="greenhouse", board=cached, posting_id=gh_jid, url=url)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA,
                                     follow_redirects=True) as cli:
            page = (await cli.get(url)).text
    except Exception:
        return None

    candidates: list[str] = []
    for pat in _GH_TOKEN_PATTERNS:
        candidates += pat.findall(page)
    # Structural fallback for JS-rendered pages with no embed URL in the raw
    # HTML: the board token is almost always the company's own slug. Guessing
    # is safe because every candidate is VERIFIED against boards-api — a wrong
    # guess just 404s and is discarded.
    sld = host.split(":")[0].split(".")[-2] if "." in host else ""
    if sld:
        candidates.append(sld)
    comp = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    if comp:
        candidates.append(comp)
    # de-dup, keep order; "embed" is a path segment, never a board token
    seen = set()
    for token in candidates:
        t = token.lower()
        if t in seen or t == "embed":
            continue
        seen.add(t)
        if await _verified(t):
            _gh_token_cache[host] = t
            return AtsRef(ats="greenhouse", board=t, posting_id=gh_jid, url=url)
    return None


# ── Normalized form schema ────────────────────────────────────────────────────
# Every ATS's questions are normalized to:
# {key, label, type, required, options?}   type ∈ text | textarea | select |
# multiselect | boolean | file | unsupported

@dataclass
class FormField:
    key: str
    label: str
    type: str
    required: bool
    options: list[dict] = field(default_factory=list)   # [{label, value}]

    def as_dict(self) -> dict:
        d = {"key": self.key, "label": self.label, "type": self.type,
             "required": self.required}
        if self.options:
            d["options"] = self.options
        return d


async def fetch_form(ref: AtsRef) -> dict:
    """
    Fetch the application form schema via the PUBLIC read endpoints.
    Returns {"fields": [FormField dicts], "apply_url": str, "meta": {...}}.
    Raises ValueError with a human-readable reason when unavailable.
    """
    if ref.ats == "greenhouse":
        return await _greenhouse_form(ref)
    if ref.ats == "lever":
        return await _lever_form(ref)
    if ref.ats == "ashby":
        return await _ashby_form(ref)
    raise ValueError(f"Unsupported ATS: {ref.ats}")


# ── Greenhouse ────────────────────────────────────────────────────────────────
# Docs: https://developers.greenhouse.io/job-board.html — job detail with
# ?questions=true is public, no auth.

_GH_TYPE = {
    "input_text": "text", "textarea": "textarea", "input_file": "file",
    "multi_value_single_select": "select", "multi_value_multi_select": "multiselect",
}


async def _greenhouse_form(ref: AtsRef) -> dict:
    api = (f"https://boards-api.greenhouse.io/v1/boards/{ref.board}"
           f"/jobs/{ref.posting_id}?questions=true")
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as cli:
        r = await cli.get(api)
    if r.status_code == 404:
        raise ValueError("Greenhouse posting not found (expired or board renamed)")
    r.raise_for_status()
    data = r.json()

    fields: list[FormField] = []
    # location_questions is a SEPARATE section with the same field shape —
    # skipping it hid a required "Location (City)" on Samsara-style boards and
    # dry-run passed forms that live submission would reject. Hidden
    # lat/long helper fields are not user questions — skipped.
    for q in list(data.get("questions", [])) + list(data.get("location_questions", [])):
        f0 = (q.get("fields") or [{}])[0]
        if f0.get("type") == "input_hidden":
            continue
        ftype = _GH_TYPE.get(f0.get("type", ""), "unsupported")
        opts = [{"label": v.get("label", ""), "value": str(v.get("value", ""))}
                for v in (f0.get("values") or [])]
        # Greenhouse encodes yes/no questions as single-selects with 2 options
        if ftype == "select" and len(opts) == 2 and \
                {o["label"].strip().lower() for o in opts} == {"yes", "no"}:
            ftype = "boolean"
        fields.append(FormField(
            key=f0.get("name", ""), label=q.get("label", ""),
            type=ftype, required=bool(q.get("required")), options=opts,
        ))
    # Demographic/EEOC block — included per explicit user decision
    #: answers come only from the user's own saved application
    # profile, are always rendered optional, and the user reviews before any
    # submit. Never auto-invented.
    demo = (data.get("demographic_questions") or {}).get("questions", [])
    for q in demo:
        opts = [{"label": o.get("label", ""), "value": str(o.get("id", ""))}
                for o in (q.get("answer_options") or [])]
        fields.append(FormField(
            key=f"demographic_answers[{q.get('id')}]",
            label="[Optional] " + (q.get("label") or ""),
            type="select" if opts else "text", required=False, options=opts,
        ))

    # Federal EEOC self-identification ("compliance") — a FIFTH schema
    # section, present on 39 of 59 boards sampled 2026-07-11. Same question
    # shape; labels are CamelCase codes (DisabilityStatus) → spaced for
    # display. Voluntary self-ID → always optional.
    for block in (data.get("compliance") or []):
        for q in block.get("questions", []):
            f0 = (q.get("fields") or [{}])[0]
            opts = [{"label": v.get("label", ""), "value": str(v.get("value", ""))}
                    for v in (f0.get("values") or [])]
            nice = re.sub(r"(?<!^)(?=[A-Z])", " ", q.get("label") or "")
            fields.append(FormField(
                key=f0.get("name", ""), label=f"[Optional] {nice}",
                type="select" if opts else "text", required=False, options=opts,
            ))

    return {
        "fields": [f.as_dict() for f in fields],
        "apply_url": data.get("absolute_url") or ref.url,
        "meta": {"title": data.get("title", ""), "location":
                 (data.get("location") or {}).get("name", "")},
    }


# ── Lever ─────────────────────────────────────────────────────────────────────
# The postings API (github.com/lever/postings-api) exposes the posting but NOT
# its custom questions. The hosted apply page, however, is server-rendered:
# custom question "cards" sit in hidden inputs named cards[UUID][baseTemplate]
# whose value is HTML-escaped JSON ({fields: [{text, required, options…}]}),
# and the answer inputs are cards[UUID][fieldN]. EEO selects (eeo[gender] etc.)
# and location/pronouns are plain form fields. We parse that page for the FULL
# schema and fall back to the standard fields when the fetch fails.

_LEVER_STANDARD = [
    ("name",     "Full name",        "text",     True),
    ("email",    "Email",            "text",     True),
    ("phone",    "Phone",            "text",     False),
    ("org",      "Current company",  "text",     False),
    ("urls[LinkedIn]", "LinkedIn URL", "text",   False),
    ("urls[GitHub]",   "GitHub URL",   "text",   False),
    ("urls[Portfolio]", "Portfolio / website", "text", False),
    ("comments", "Additional information / cover letter", "textarea", False),
    ("resume",   "Resume",           "file",     True),
]

_LEVER_CARD_TYPE = {
    "multiple-choice": "select", "dropdown": "select",
    "multiple-select": "multiselect", "checkboxes": "multiselect",
    "textarea": "textarea", "text": "text",
}
_LEVER_CARD_RE = re.compile(
    r'name="cards\[([0-9a-f-]+)\]\[baseTemplate\]"|'
    r'value="([^"]*)"[^>]+name="cards\[([0-9a-f-]+)\]\[baseTemplate\]"', re.I)


def _parse_lever_cards(html_text: str) -> list[FormField]:
    """Custom question cards from the server-rendered apply page."""
    import html as _html
    out: list[FormField] = []
    # hidden input: value=<escaped card JSON> name="cards[UUID][baseTemplate]"
    for m in re.finditer(
            r'<input[^>]+value="([^"]+)"[^>]+name="cards\[([0-9a-f-]+)\]\[baseTemplate\]"',
            html_text, re.I):
        raw, card_id = m.group(1), m.group(2)
        try:
            card = json.loads(_html.unescape(raw))
        except Exception:
            continue
        for i, f in enumerate(card.get("fields", [])):
            ftype = _LEVER_CARD_TYPE.get(f.get("type", ""), "text")
            opts = [{"label": o.get("text", ""), "value": o.get("text", "")}
                    for o in (f.get("options") or [])]
            if ftype == "select" and len(opts) == 2 and \
                    {o["label"].strip().lower() for o in opts} == {"yes", "no"}:
                ftype = "boolean"
            out.append(FormField(
                key=f"cards[{card_id}][field{i}]",
                label=f.get("text", ""), type=ftype,
                required=bool(f.get("required")), options=opts))
    return out


def _parse_lever_extras(html_text: str) -> list[FormField]:
    """EEO selects, location, pronouns — present only on some boards."""
    out: list[FormField] = []
    if 'name="location"' in html_text:
        out.append(FormField(key="location", label="Current location",
                             type="text", required=True))
    if 'name="pronouns"' in html_text:
        out.append(FormField(key="pronouns", label="Pronouns", type="text", required=False))
    for eeo_key, eeo_label in (("eeo[gender]", "[Optional] Gender (EEO survey)"),
                               ("eeo[race]", "[Optional] Race/Ethnicity (EEO survey)"),
                               ("eeo[veteran]", "[Optional] Veteran status (EEO survey)"),
                               ("eeo[disability]", "[Optional] Disability status (EEO survey)")):
        sel = re.search(
            rf'<select[^>]+name="{re.escape(eeo_key)}"[^>]*>(.*?)</select>',
            html_text, re.S | re.I)
        if not sel:
            continue
        opts = [{"label": re.sub(r"<[^>]+>", "", o).strip(), "value": v}
                for v, o in re.findall(r'<option[^>]+value="([^"]+)"[^>]*>(.*?)</option>',
                                       sel.group(1), re.S) if v]
        out.append(FormField(key=eeo_key, label=eeo_label, type="select",
                             required=False, options=opts))
    return out


async def _lever_form(ref: AtsRef) -> dict:
    api = f"https://api.lever.co/v0/postings/{ref.board}/{ref.posting_id}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as cli:
        r = await cli.get(api)
    if r.status_code == 404:
        raise ValueError("Lever posting not found (expired)")
    r.raise_for_status()
    data = r.json()

    fields = [FormField(key=k, label=l, type=t, required=req)
              for k, l, t, req in _LEVER_STANDARD]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True,
                                     headers={**_UA, "User-Agent": "Mozilla/5.0"}) as cli:
            page = await cli.get(f"https://jobs.lever.co/{ref.board}/{ref.posting_id}/apply")
        if page.status_code == 200:
            fields += _parse_lever_extras(page.text)
            fields += _parse_lever_cards(page.text)
    except Exception as e:
        print(f"[LEVER FORM] page parse skipped, standard fields only: {e}")

    return {
        "fields": [f.as_dict() for f in fields],
        "apply_url": data.get("applyUrl") or f"{data.get('hostedUrl', ref.url)}/apply",
        "meta": {"title": data.get("text", ""), "location":
                 (data.get("categories") or {}).get("location", "")},
    }


# ── Ashby ─────────────────────────────────────────────────────────────────────
# Public read: https://api.ashbyhq.com/posting-api/job-board/{org}
# (includeCompensation etc.). Per-posting application form questions are only
# available to the company's own API key, so Phase 1 exposes the standard
# fields and submits through the hosted board's public submit route; if that
# rejects (captcha / unknown required questions) → manual.

_ASHBY_STANDARD = [
    ("_systemfield_name",  "Full name", "text", True),
    ("_systemfield_email", "Email",     "text", True),
    ("_systemfield_phone", "Phone",     "text", False),
    ("_systemfield_resume", "Resume",   "file", True),
]

# The hosted board's own (unauthenticated) GraphQL endpoint returns the FULL
# per-posting application form — custom questions included — which the
# posting-api hides. `field` is a JSON scalar in their schema.
_ASHBY_GQL = (
    "query ApiJobPosting($organizationHostedJobsPageName: String!, "
    "$jobPostingId: String!) { jobPosting(organizationHostedJobsPageName: "
    "$organizationHostedJobsPageName, jobPostingId: $jobPostingId) { id title "
    "locationName applicationForm { sections { title fieldEntries "
    "{ field isRequired } } } } }"
)

_ASHBY_TYPE = {
    "String": "text", "Email": "text", "Phone": "text", "Number": "text",
    "Location": "text", "Date": "text", "LongText": "textarea",
    "File": "file", "Boolean": "boolean",
    "ValueSelect": "select", "MultiValueSelect": "multiselect",
}


async def _ashby_form(ref: AtsRef) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT,
                                 headers={**_UA, "User-Agent": "Mozilla/5.0"}) as cli:
        r = await cli.post("https://jobs.ashbyhq.com/api/non-user-graphql", json={
            "operationName": "ApiJobPosting",
            "variables": {"organizationHostedJobsPageName": ref.board,
                          "jobPostingId": ref.posting_id},
            "query": _ASHBY_GQL})
    jp = ((r.json().get("data") or {}).get("jobPosting")
          if r.status_code == 200 else None)
    if not jp:
        raise ValueError("Ashby posting not found (expired or board renamed)")

    fields: list[FormField] = []
    for sec in (jp.get("applicationForm") or {}).get("sections", []):
        for fe in sec.get("fieldEntries", []):
            f = fe.get("field") or {}
            ftype = _ASHBY_TYPE.get(f.get("type", ""), "text")
            opts = [{"label": o.get("label", ""), "value": str(o.get("value", ""))}
                    for o in (f.get("selectableValues") or [])]
            fields.append(FormField(
                key=f.get("path") or f.get("id", ""),
                label=(f.get("title") or "").replace(" ", " ").strip(),
                type=ftype, required=bool(fe.get("isRequired")), options=opts))
    if not fields:
        fields = [FormField(key=k, label=l, type=t, required=req)
                  for k, l, t, req in _ASHBY_STANDARD]

    return {
        "fields": [f.as_dict() for f in fields],
        "apply_url": f"https://jobs.ashbyhq.com/{ref.board}/{ref.posting_id}/application",
        "meta": {"title": jp.get("title", ""), "location": jp.get("locationName") or ""},
    }


# ── Prefill ───────────────────────────────────────────────────────────────────

def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:]) or parts[0]


def _norm_label(label: str) -> str:
    """Normalize a question label so the same question matches across
    companies despite punctuation/spacing/casing differences."""
    # fold hyphenated words first ("on-site" == "onsite"), then punctuation
    s = re.sub(r"(?<=\w)-(?=\w)", "", (label or "").lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Filler words carrying no meaning for question identity. Universal English
# function words only — never domain terms (same minimal-skip-list rule as the
# JD extractor).
_QSTOP = frozenset(
    "a an the are is was were be been am do does did you your we our us i me "
    "my to of in on at for with and or if will would can could should shall "
    "have has had this that these those it its there here please any what "
    "which when how many much old currently".split())


def _content_tokens(label: str) -> frozenset:
    """Distinctive tokens of a question: normalized words minus filler and
    bare numbers ('3 days/week' and 'days/week' are the same ask)."""
    return frozenset(t for t in _norm_label(label).split()
                     if t not in _QSTOP and not t.isdigit())


def _memory_lookup(label: str, memory: dict) -> str:
    """Find a stored answer for this question. Exact normalized match first;
    then fuzzy: if one question's content-token set contains the other's
    ('willing to work onsite' ⊆ 'willing to work onsite 3 days week'), they
    are the same ask worded differently. Distinct content words ('onsite' vs
    'weekends') never match. Ties go to the largest overlap."""
    k = _norm_label(label)
    if k in memory:
        return memory[k]
    mine = _content_tokens(label)
    if not mine:
        return ""
    best, best_overlap = "", 0
    for stored_q, ans in memory.items():
        theirs = _content_tokens(stored_q)
        if not theirs:
            continue
        small, big = (mine, theirs) if len(mine) <= len(theirs) else (theirs, mine)
        if small <= big and len(small) > best_overlap:
            best, best_overlap = ans, len(small)
    return best


def _pick_option(options: list[dict], want: str) -> str:
    """Match a stored answer (an option LABEL from some earlier form) to this
    form's options. Exact normalized match first, then WORD-level containment
    (one label's token set inside the other's). Never raw substring — 'no'
    must not match the 'no' inside 'another'. Returns the option VALUE, or ''
    when nothing matches."""
    if not want:
        return ""
    w = _norm_label(want)
    for o in options:
        if _norm_label(o["label"]) == w:
            return o["value"]
    wt = frozenset(w.split())
    for o in options:
        ot = frozenset(_norm_label(o["label"]).split())
        if wt and ot and (wt <= ot or ot <= wt):
            return o["value"]
    return ""


_NEG_HEADS = ("no", "none", "never")


def _pick_yes_no(options: list[dict], yes: bool) -> str:
    """Yes/No onto option lists. Head-word match first; for 'No', options
    phrased as denials ('I have never worked at…', 'None of the above') are
    accepted when exactly one option reads as a denial. No fuzzy fallback —
    a blank the user fills beats a confidently wrong claim."""
    want = "yes" if yes else "no"
    for o in options:
        head = _norm_label(o["label"]).split()[:1]
        if head and head[0] == want:
            return o["value"]
    if not yes:
        denials = [o for o in options
                   if any(t in _NEG_HEADS or t == "not"
                          for t in _norm_label(o["label"]).split()[:4])]
        if len(denials) == 1:
            return denials[0]["value"]
    return ""


_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)")
_PLUS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+|more than\s*(\d+)|(\d+)\s*or more", re.I)


def _pick_years_bucket(options: list[dict], years: float) -> str:
    """Pick the option whose numeric bucket contains `years`. Works on any
    company's ranges ('0-4 years', '5–10', '8+ years') — no fixed lists."""
    plus_best: tuple[float, str] | None = None
    for o in options:
        lab = o["label"]
        m = _RANGE_RE.search(lab)
        if m and float(m.group(1)) <= years <= float(m.group(2)):
            return o["value"]
        p = _PLUS_RE.search(lab)
        if p:
            floor = float(next(g for g in p.groups() if g))
            if years >= floor and (plus_best is None or floor > plus_best[0]):
                plus_best = (floor, o["value"])
    return plus_best[1] if plus_best else ""


# Question classes: (label pattern, apply_profile key, kind).
# kind: "yesno" (map Yes/No to options), "option" (containment-match stored
# label), "text" (free text), "years" (numeric bucket).
# Order matters — first match wins, so put the more specific patterns first.
_CLASS_RULES: list[tuple[re.Pattern, str, str]] = [
    # Inverted sponsorship phrasing ("authorized to work WITHOUT requiring
    # sponsorship?") — the truthful answer is the OPPOSITE of
    # need_sponsorship. Must sit BEFORE the plain sponsor rule, which would
    # otherwise fill the un-inverted value ("Yes" = "I never need
    # sponsorship" — a misrepresentation for visa holders).
    (re.compile(r"without\s+(requiring|needing)?\s*(visa\s+)?sponsor", re.I),
     "need_sponsorship_inverted", "yesno"),
    (re.compile(r"sponsor|immigration case|visa\b", re.I), "need_sponsorship", "yesno"),
    (re.compile(r"authoriz\w* to work|work authorization|eligible to work|legally.{0,30}work"
                r"|legal(?:ly)?\s+(?:right|entitled)\s+to\s+(?:live\s+and\s+)?work|right\s+to\s+work\b",
                re.I),
     "work_authorized", "yesno"),
    (re.compile(r"relocat", re.I), "relocation", "yesno"),
    # Willingness to be on-site / hybrid / commute — a very common gate.
    (re.compile(r"willing.{0,25}(on-?site|in-?office|in[- ]person|hybrid|commut)|able to commute|work on-?site|come in(to)? (the )?office|report to (the )?office", re.I),
     "onsite_ok", "yesno"),
    # Consents that recur on nearly every US application.
    (re.compile(r"background\s+(check|screen|investigation)", re.I), "background_check", "yesno"),
    (re.compile(r"drug\s+(test|screen)", re.I), "drug_test", "yesno"),
    (re.compile(r"convicted|criminal\s+(record|history|conviction|background)|felon", re.I), "convicted", "yesno"),
    (re.compile(r"salary.{0,20}negotiab|negotiable\s*\??", re.I), "negotiable", "yesno"),
    (re.compile(r"salary|compensation|pay expectation", re.I), "salary", "text"),
    (re.compile(r"\bzip\b|postal code", re.I), "zip", "text"),
    # A "Degree" / "Highest level of education" SELECT wants the level bucket
    # (derived from profile education in prefill) — must sit BEFORE the yes/no
    # do-you-have-a-degree rule, which the bare word "degree" also matches.
    (_DEGREE_LEVEL_RE := re.compile(
        r"^\s*(highest\s+)?(level\s+of\s+)?(education|degree)"
        r"(\s+(level|earned|obtained|completed|attained))?\s*\*?\s*$", re.I),
     "degree_level", "text"),
    (re.compile(r"bachelor|higher education|degree\b", re.I), "degree", "yesno"),
    (re.compile(r"(how many|years of).{0,60}experience|experience.{0,30}years", re.I),
     "years_experience", "years"),
    (re.compile(r"how did you (hear|learn)|where.{0,30}(hear|learn)\w* about", re.I),
     "how_heard", "option"),
    (re.compile(r"previously (worked|employed)|ever worked (at|for)|worked .{0,25} before", re.I),
     "previously_worked", "yesno"),
    (re.compile(r"preferred first name", re.I), "preferred_first", "text"),
    (re.compile(r"preferred last name", re.I), "preferred_last", "text"),
    (re.compile(r"pronoun", re.I), "pronouns", "text"),
    (re.compile(r"18 years|at least 18|age of 18", re.I), "age_18", "yesno"),
    (re.compile(r"(which|what).{0,25}state.{0,30}(locat|resid|based)|state of residence", re.I),
     "state", "text"),
    (re.compile(r"currently employed", re.I), "currently_employed", "yesno"),
    (re.compile(r"citizenship status", re.I), "citizenship", "option"),
    (re.compile(r"security clearance", re.I), "clearance", "option"),
    (re.compile(r"when.{0,30}(start|join)|notice period|earliest.{0,20}start|available to start", re.I),
     "start_date", "text"),
    (re.compile(r"non.?compet|non.?solicit", re.I), "noncompete", "yesno"),
    (re.compile(r"referred by.{0,30}employee|referral", re.I), "referral", "text"),
    # ── Safe truthful constants / derived answers (taxonomy sweep) ───────────
    (re.compile(r"related to.{0,30}(current|any)?\s*employee|relative.{0,20}(work|employ)", re.I),
     "related_employee", "yesno"),
    (re.compile(r"former|other|maiden.{0,15}names?\s+(used|known)", re.I), "former_names", "yesno"),
    (re.compile(r"mailing address.{0,20}same", re.I), "mailing_same", "yesno"),
    (re.compile(r"phone\s+type|type\s+of\s+phone", re.I), "phone_type", "text"),
    (re.compile(r"not\s+a\s+(recruiter|staffing|agency)|confirm.{0,25}(recruiter|agency)", re.I),
     "not_recruiter", "yesno"),
    (re.compile(r"meet.{0,25}(minimum|basic)\s+qualifications", re.I), "meets_min_quals", "yesno"),
    (re.compile(r"read.{0,20}job\s+description", re.I), "read_jd", "yesno"),
    (re.compile(r"willing.{0,30}(assessment|skills?\s+test|take-?home)", re.I),
     "willing_assessment", "yesno"),
    (re.compile(r"willing.{0,30}in-?person\s+interview|attend.{0,20}interview", re.I),
     "willing_interview", "yesno"),
    (re.compile(r"reliable\s+transport", re.I), "reliable_transport", "yesno"),
    (re.compile(r"reliable\s+(internet|wifi|connection)|home\s+(office|internet)", re.I),
     "reliable_internet", "yesno"),
    (re.compile(r"did you graduate|degree\s+(completed|conferred|awarded)", re.I),
     "graduated", "yesno"),
    (re.compile(r"currently\s+enrolled", re.I), "currently_enrolled", "yesno"),
    (re.compile(r"planned\s+(time\s+off|vacation|pto).{0,30}(90|ninety|first)", re.I),
     "planned_time_off", "yesno"),
    (re.compile(r"full.?time.{0,20}(preference|position|role|employment)?\s*\??$"
                r"|employment\s+type\s+preference|seeking\s+(full|part).?time", re.I),
     "employment_type", "text"),
    (re.compile(r"hours\s+(available|per week|weekly)|weekly\s+hours", re.I),
     "hours_per_week", "text"),
    (re.compile(r"willing.{0,20}overtime", re.I), "overtime_ok", "yesno"),
    (re.compile(r"country\s+code|dial(ing)?\s+code", re.I), "country_code", "text"),
    (re.compile(r"confirm\s+e-?mail|re-?enter.{0,10}e-?mail|e-?mail\s+confirmation", re.I),
     "confirm_email", "text"),
    (re.compile(r"languages?\s+(spoken|you\s+speak)|spoken\s+languages", re.I),
     "languages", "text"),
    (re.compile(r"gender identity|identify.{0,20}gender|\bgender\b", re.I), "demo_gender", "option"),
    (re.compile(r"race|ethnicit", re.I), "demo_race", "option"),
    (re.compile(r"veteran", re.I), "demo_veteran", "option"),
    (re.compile(r"disabilit|impairment", re.I), "demo_disability", "option"),
]

# Consent/acknowledgement questions (privacy notice, AI policy, T&C read).
# Auto-picked ONLY as a prefill the user still reviews in the modal before
# any submit — clicking submit is the actual act of consent.
_CONSENT_LABEL = re.compile(
    r"consent|acknowledge|agree|policy|privacy|terms|personal data|"
    r"do you confirm|confirm that", re.I)
_CONSENT_OPTION = re.compile(r"acknowledge|confirm|agree|yes", re.I)

# Conditional follow-ups ("If you selected 'Other'…") depend on another
# answer — never auto-filled from class rules.
_CONDITIONAL_LABEL = re.compile(r"if you (selected|answered|chose)|if other", re.I)

# Fields that must NEVER be auto-filled — not from rules, not from learned
# memory. Sensitive identifiers a legitimate application never needs pre-offer;
# leaking one from memory onto the wrong form would be far worse than a blank.
_NEVER_FILL = re.compile(
    r"\bssn\b|social\s+security|bank\s+(account|routing)|routing\s+number"
    r"|date\s+of\s+birth|\bdob\b|birth\s*date"
    r"|(driver'?s?\s+license|passport)\s*(number|no\.?|#)"
    r"|salary\s+history|previous\s+(salary|compensation)|current\s+salary"
    r"|mother'?s\s+maiden|security\s+question", re.I)

# ── Years-of-experience question shapes ──────────────────────────────────────
# A "years" class match is one of three shapes; treat them very differently.
# Universal generic-experience words (not a specific tool/domain) — a minimal
# always-true list, per the no-hardcoding rule.
_GENERIC_EXP_WORDS = frozenset(
    "experience work working professional relevant overall total related "
    "industry field role a an the your our paid full similar equivalent "
    "combined cumulative hands on".split())

# threshold: "at least 6 years", "6+ years", "minimum of 4 years", "6 or more"
_THRESHOLD_RE = re.compile(
    r"(?:at least|minimum of|min\.?|no less than)\s+(\d+(?:\.\d+)?)|"
    r"(\d+(?:\.\d+)?)\s*\+|(\d+(?:\.\d+)?)\s+or more", re.I)


def _years_threshold(label: str):
    m = _THRESHOLD_RE.search(label or "")
    if not m:
        return None
    return float(next(g for g in m.groups() if g))


def _years_is_specific(label: str) -> bool:
    """True when the years question is about a SPECIFIC tool/skill/domain
    ('years with Salesforce', 'years of Looker'), not generic total
    experience ('years of experience in analytics'). Specific questions are
    left blank for the resume-grounded AI draft — the profile's total-years
    number must never be claimed as tool-specific experience."""
    for m in re.finditer(r"years?\s+(?:of|with|in|using)\s+([a-z]+)", label or "", re.I):
        if m.group(1).lower() not in _GENERIC_EXP_WORDS:
            return True
    # "experience with/using X" where X isn't a generic word
    for m in re.finditer(r"experience\s+(?:with|using|in)\s+([a-z]+)", label or "", re.I):
        if m.group(1).lower() not in _GENERIC_EXP_WORDS:
            return True
    return False


def _start_date_answer(stored: str, label: str, ftype: str,
                       options: list[dict]) -> str:
    """'15 days' stays text for a text question — but a DATE field gets a real
    computed date: today + notice period, rolled forward to a MONDAY (nobody
    starts a job on Fri/Sat/Sun)."""
    from datetime import date, timedelta
    wants_date = (ftype == "date"
                  or re.search(r"mm[/\-]dd|dd[/\-]mm|yyyy|start\s+date\b|date\s+available"
                               r"|available\s+(start\s+)?date|earliest\s+(start\s+)?date",
                               label or "", re.I) is not None)
    if not wants_date:
        if options:
            return _pick_option(options, stored)
        return stored
    s = stored.lower()
    m = re.search(r"(\d+)\s*(day|week|month)", s)
    if m:
        n = int(m.group(1))
        days = n * (7 if m.group(2).startswith("week") else 30 if m.group(2).startswith("month") else 1)
    elif re.search(r"immediat|asap|now|any\s*time", s):
        days = 3
    else:
        days = 14
    d = date.today() + timedelta(days=days)
    while d.weekday() != 0:          # roll forward to the next Monday
        d += timedelta(days=1)
    if ftype == "date":
        return d.isoformat()         # <input type=date> takes YYYY-MM-DD
    return d.strftime("%m/%d/%Y")


def _class_answer(label: str, ftype: str, options: list[dict],
                  ap: dict) -> str:
    """Answer one question from the saved application profile. '' = no match."""
    if _CONDITIONAL_LABEL.search(label):
        return ""
    for pat, key, kind in _CLASS_RULES:
        if not pat.search(label):
            continue
        if key == "need_sponsorship_inverted":
            # derived, not stored: flip the saved need_sponsorship answer
            base = str(ap.get("need_sponsorship") or "").strip().lower()
            if base not in ("yes", "no"):
                return ""
            stored = "No" if base == "yes" else "Yes"
        else:
            stored = ap.get(key)
        if stored in (None, ""):
            return ""
        if kind == "years":
            try:
                yrs = float(stored)
            except (TypeError, ValueError):
                return ""
            # Skill/tool-specific ("years with Salesforce", "years of Looker")
            # → never fill from the profile's TOTAL years; the AI draft answers
            # it truthfully from the resume.
            if _years_is_specific(label):
                return ""
            thr = _years_threshold(label)
            if thr is not None:
                # "Do you have at least N years…?" is a yes/no gate, not a
                # number field. Compare total years to the threshold.
                meets = yrs >= thr
                if options:
                    return _pick_yes_no(options, meets)
                return "Yes" if meets else "No"
            # Generic "how many years of experience" → range bucket or number.
            if options:
                return _pick_years_bucket(options, yrs)
            if ftype in ("text", "textarea"):
                return str(stored)
            return ""
        if kind == "yesno" and options:
            s = str(stored).strip().lower()
            if s in ("yes", "no", "true", "false"):
                return _pick_yes_no(options, s in ("yes", "true"))
            return _pick_option(options, str(stored))
        if kind == "option":
            if not options:
                return ""   # option-kind answers never fill free-text fields
            picked = _pick_option(options, str(stored))
            if not picked:
                # Phrasing drift ("do not" vs "don't"): when the stored answer
                # leads with a yes/no word, fall back to that.
                lead = _norm_label(str(stored)).split(",")[0].split()[:1]
                if lead and lead[0] in ("yes", "no"):
                    picked = _pick_yes_no(options, lead[0] == "yes")
            return picked
        if key == "start_date":
            return _start_date_answer(str(stored), label, ftype, options)
        if key == "degree_level" and options:
            picked = _pick_option(options, str(stored))
            if picked:
                return picked
            # "Masters" vs "Master's" vs "Master of Science" — match on the
            # level keyword alone.
            lvl = re.search(r"master|bachelor|doctor|associate", str(stored), re.I)
            if lvl:
                for o in options:
                    if re.search(lvl.group(0), o["label"], re.I):
                        return o["value"]
            return ""
        if not options:   # free-text field
            return str(stored)
        return _pick_option(options, str(stored))
    if _CONSENT_LABEL.search(label) and options:
        for o in options:
            if _CONSENT_OPTION.search(o["label"]):
                return o["value"]
    return ""


def prefill(fields: list[dict], profile: dict,
            apply_profile: dict | None = None,
            memory: dict | None = None) -> dict:
    """
    Deterministically map saved values onto form fields. Priority per field:
      1. exact key map (contact basics)
      2. answer memory — the user's own past answer to this exact question
      3. class rules — the one-time application profile (sponsorship,
         relocation, salary, years, demographics…)
      4. label rules — free-text contact fallbacks
    Unknown questions stay blank for the user; NOTHING is invented. Answers
    the user types get remembered server-side, so each unique question is
    answered once ever.
    """
    ap = apply_profile or {}
    mem = memory or {}
    # Application Answers is the AUTHORITATIVE source for application data —
    # its Contact/Education fields override the resume Profile whenever set,
    # so the user maintains ONE form instead of editing the resume profile.
    _apv = lambda k: str(ap.get(k) or "").strip()
    # Derived: canonical degree level from the profile's education entries —
    # ATS "Degree" dropdowns want a bucket ("Master's Degree"), not the full
    # program name ("Master of Science in Information Systems").
    if not ap.get("degree_level"):
        deg_txt = " ".join(str(e.get("degree", ""))
                           for e in (profile.get("education") or [])).lower()
        if re.search(r"ph\.?d|doctor", deg_txt):
            ap = {**ap, "degree_level": "Doctorate"}
        elif re.search(r"master|m\.?s\.?\b|mba", deg_txt):
            ap = {**ap, "degree_level": "Master's Degree"}
        elif re.search(r"bachelor|b\.?s\.?\b|b\.?tech|b\.?e\.?\b", deg_txt):
            ap = {**ap, "degree_level": "Bachelor's Degree"}
        elif re.search(r"associate", deg_txt):
            ap = {**ap, "degree_level": "Associate's Degree"}
    # Safe truthful defaults for near-universal questions — only where the
    # honest answer is the same for essentially every applicant. Anything
    # judgment-dependent (shifts, overtime, languages, travel %) stays blank
    # until the user answers it once (Application Answers or learned memory).
    _defaults = {
        "related_employee": "No", "former_names": "No", "mailing_same": "Yes",
        "phone_type": "Mobile", "not_recruiter": "Yes", "meets_min_quals": "Yes",
        "read_jd": "Yes", "willing_assessment": "Yes", "willing_interview": "Yes",
        "reliable_transport": "Yes", "reliable_internet": "Yes",
        "graduated": "Yes", "currently_enrolled": "No", "negotiable": "Yes",
        "planned_time_off": "No", "employment_type": "Full-time",
        "hours_per_week": "40", "country_code": "+1",
        "confirm_email": _apv("email") or profile.get("email", ""),
    }
    for _k, _v in _defaults.items():
        if _v and not ap.get(_k):
            ap = {**ap, _k: _v}
    # First education entry feeds the standard School/Discipline/Year fields.
    _edu = (profile.get("education") or [{}])[0] or {}
    _edu_school = _apv("school_name") or str(_edu.get("school") or "").strip()
    _edu_year = _apv("edu_end_year") or str(_edu.get("year") or "").strip()
    _edu_start = _apv("edu_start_year")
    # Discipline = the "in <field>" tail of the degree name ("Master of
    # Science in Information Systems" → "Information Systems").
    _m_disc = re.search(r"\bin\s+([A-Z][\w&/ ]{2,60})$", str(_edu.get("degree") or ""))
    _edu_discipline = _apv("discipline") or (_m_disc.group(1).strip() if _m_disc else "")
    _pf, _pl = _split_name(profile.get("name", ""))
    first = _apv("first_name") or _pf
    last = _apv("last_name") or _pl
    middle = _apv("middle_name")
    full_name = (f"{first} {last}".strip()
                 if (_apv("first_name") or _apv("last_name"))
                 else profile.get("name", ""))
    email = _apv("email") or profile.get("email", "")
    phone = _apv("phone") or profile.get("phone", "")
    linkedin = _apv("linkedin") or profile.get("linkedin", "")
    github = _apv("github") or profile.get("github", "")
    website = _apv("website") or profile.get("website", "")
    city = _apv("city") or profile.get("location", "")
    street = _apv("street_address")
    apt = _apv("apt_unit")
    full_address = (", ".join(x for x in (street, apt) if x)
                    or profile.get("address", ""))
    country = _apv("country") or "United States"
    # Preferred names default to the legal name — no separate fields to fill.
    if first and not ap.get("preferred_first"):
        ap = {**ap, "preferred_first": first}
    if last and not ap.get("preferred_last"):
        ap = {**ap, "preferred_last": last}
    by_key = {
        "first_name": first, "last_name": last,
        "email": email, "phone": phone,
        "name": full_name,
        "location": city,
        "org": profile.get("current_company", ""),
        "urls[LinkedIn]": linkedin,
        "urls[GitHub]": github,
        "urls[Portfolio]": website,
        "_systemfield_name": full_name,
        "_systemfield_email": email,
        "_systemfield_phone": phone,
    }
    # Label rules also cover name fields, so generic-keyed callers (the
    # browser extension, which keys fields f0/f1/… not first_name) still get
    # contact basics filled by matching the visible label. Order matters:
    # "preferred first name" is handled by class rules, so the plain-name
    # rules below deliberately exclude "preferred".
    _label_rules = [
        (re.compile(r"(?<!preferred )\bfirst name\b|\bgiven name\b|\bfore.?name\b", re.I), first),
        (re.compile(r"\bmiddle\s+(name|initial)\b", re.I), middle),
        (re.compile(r"(?<!preferred )\blast name\b|\bsurname\b|\bfamily name\b", re.I), last),
        (re.compile(r"\bfull name\b|^name$|\byour name\b|\blegal name\b", re.I), full_name),
        (re.compile(r"\blocation\b|\bcity\b", re.I), city),
        (re.compile(r"\bstreet\b|address\s+line\s*1", re.I), street or full_address),
        (re.compile(r"\bapt\b|apartment|unit|suite|address\s+line\s*2", re.I), apt),
        (re.compile(r"\bmailing\b|\baddress\b", re.I), full_address),
        (re.compile(r"^\s*country\s*(of\s+residence)?\s*\*?\s*$", re.I), country),
        (re.compile(r"\blinkedin\b", re.I), linkedin),
        (re.compile(r"\bgithub\b", re.I), github),
        (re.compile(r"\b(website|portfolio)\b", re.I), website),
        (re.compile(r"\bphone\b|\bmobile\b|\bcell\b", re.I), phone),
        (re.compile(r"\bemail\b|\be-?mail\b", re.I), email),
        (re.compile(r"(current|present).{0,20}(company|employer)", re.I),
         profile.get("current_company", "")),
        # Education basics — Application Answers first, resume profile second.
        # Anchored so "School" matches but "school district" questions don't.
        (re.compile(r"^\s*(school|university|college|institution)(\s+name)?\s*\*?\s*$", re.I),
         _edu_school),
        (re.compile(r"discipline|\bmajor\b|field\s+of\s+study", re.I), _edu_discipline),
        (re.compile(r"grad(uation)?\s+year|year\s+(of\s+)?graduat|end\s+date\s+year", re.I),
         _edu_year),
        (re.compile(r"start\s+date\s+year", re.I), _edu_start),
        (re.compile(r"\bgpa\b|grade\s+point", re.I), _apv("gpa")),
    ]

    answers: dict[str, Any] = {}
    for f0 in fields:
        key, label, ftype = f0["key"], f0["label"], f0["type"]
        opts = f0.get("options") or []
        if ftype == "file":
            continue    # resume/cover handled separately server-side

        # Sensitive identifiers: hard-refused before any source can answer —
        # including learned memory, which must never leak an SSN/DOB/bank
        # detail typed elsewhere onto a new form.
        if _NEVER_FILL.search(label or ""):
            continue

        val = by_key.get(key, "")

        # Application Answers education years OVERRIDE learned memory — the
        # user set them deliberately; a 2024/2024 pair learned from an old
        # form must not outrank them.
        if not val:
            for _pat, _v in ((re.compile(r"start\s+date\s+year", re.I), _edu_start),
                             (re.compile(r"end\s+date\s+year|grad(uation)?\s+year", re.I), _edu_year)):
                if _v and _pat.search(label or ""):
                    val = _pick_option(opts, _v) if opts else _v
                    break

        # Answer memory: stored as option LABEL (portable across companies
        # whose option ids differ) or raw text for free-text questions.
        # Lookup is fuzzy — rewordings of the same ask match (see _memory_lookup).
        if not val:
            remembered = _memory_lookup(label, mem)
            # A degree-LEVEL field must never take a remembered discipline —
            # fuzzy lookup matched "…field of study for your degree" (answer:
            # "Information Systems") onto a plain "Degree" dropdown (live bug).
            if (remembered and _DEGREE_LEVEL_RE.search(label or "")
                    and not re.search(r"master|bachelor|doctor|associate|diploma|high school",
                                      str(remembered), re.I)):
                remembered = ""
            if remembered:
                val = _pick_option(opts, remembered) if opts else remembered

        if not val:
            val = _class_answer(label or "", ftype, opts, ap)

        # Label-rule fallback: free-text fields, and option-LESS selects — the
        # extension reports async typeahead comboboxes (School/City) as
        # type=select with no options; they take a text value and resolve the
        # matching option at fill time in the browser.
        if not val and (ftype in ("text", "textarea")
                        or (ftype == "select" and not opts)):
            for pat, candidate in _label_rules:
                if candidate and pat.search(label or ""):
                    val = candidate
                    break
        if val:
            answers[key] = val
    return answers


# Known-question keys whose learned answers belong in the STRUCTURED
# Application Answers profile, not the flat memory pile — a rephrased race /
# salary / relocation question routes back to its one canonical slot.
# Sponsorship/work-auth stay out: inverted phrasings would store a flipped
# meaning. Degree stays out: it has its own guarded mapping.
_PROMOTABLE_KEYS = frozenset({
    "demo_gender", "demo_race", "demo_veteran", "demo_disability",
    "salary", "start_date", "relocation", "onsite_ok", "how_heard",
    "state", "zip", "years_experience", "pronouns", "clearance",
    "citizenship", "currently_employed", "referral", "phone_type",
    "background_check", "drug_test", "convicted", "noncompete",
    "previously_worked", "age_18",
})


def classify_label(label: str) -> str:
    """The structured-profile key a question belongs to, when it's a known
    promotable type — '' otherwise."""
    if _CONDITIONAL_LABEL.search(label or "") or _NEVER_FILL.search(label or ""):
        return ""
    for pat, key, _kind in _CLASS_RULES:
        if pat.search(label or ""):
            return key if key in _PROMOTABLE_KEYS else ""
    return ""


def extract_memory(fields: list[dict], answers: dict) -> dict:
    """Turn one submission's answers into memory entries: normalized question
    label → option LABEL (selects) or raw text. Option labels — not values —
    so the memory transfers to other companies' forms."""
    out: dict[str, str] = {}
    for f0 in fields:
        key, label, ftype = f0["key"], f0["label"], f0["type"]
        if ftype == "file":
            continue
        # Sensitive identifiers are never MEMORIZED either — a form that
        # forced an SSN/DOB out of the user must not seed the answer bank.
        if _NEVER_FILL.search(label or ""):
            continue
        val = str(answers.get(key, "") or "").strip()
        if not val:
            continue
        opts = f0.get("options") or []
        if opts:
            match = next((o["label"] for o in opts if str(o["value"]) == val), "")
            if match:
                out[_norm_label(label)] = match
        else:
            out[_norm_label(label)] = val
    return out


# ── Submit ────────────────────────────────────────────────────────────────────

class CaptchaRequired(Exception):
    """Board demands a captcha — we never solve/bypass these. Manual apply."""


class ManualApplyRequired(Exception):
    """Submission path unavailable/rejected — send user to the ATS page."""


_CAPTCHA_MARKERS = ("recaptcha", "g-recaptcha", "hcaptcha", "h-captcha",
                    "captcha_token", "turnstile")


def _looks_captcha(text_: str) -> bool:
    low = (text_ or "").lower()
    return any(m in low for m in _CAPTCHA_MARKERS)


async def submit(ref: AtsRef, answers: dict, resume_bytes: bytes,
                 resume_filename: str, dry_run: bool = True,
                 cover_bytes: bytes | None = None,
                 cover_filename: str = "cover_letter.pdf") -> dict:
    """
    Submit one application through the same public endpoint the hosted
    board's own Apply form posts to. Returns
      {"status": "submitted" | "dry_run", "detail": ...}
    Raises CaptchaRequired / ManualApplyRequired for graceful UI fallback.

    dry_run=True builds and validates the payload but sends NOTHING.
    """
    if ref.ats == "greenhouse":
        return await _greenhouse_submit(ref, answers, resume_bytes,
                                        resume_filename, dry_run,
                                        cover_bytes, cover_filename)
    if ref.ats == "lever":
        return await _lever_submit(ref, answers, resume_bytes,
                                   resume_filename, dry_run)
    # Ashby's hosted-board submit route is an unversioned internal GraphQL
    # endpoint — too unstable to ship in phase 1. Manual with prefill.
    raise ManualApplyRequired("Ashby submission requires the company's API "
                              "key — use the pre-filled manual flow")


async def _greenhouse_submit(ref: AtsRef, answers: dict, resume: bytes,
                             fname: str, dry_run: bool,
                             cover: bytes | None = None,
                             cover_fname: str = "cover_letter.pdf") -> dict:
    # The embedded job board posts multipart form-data to the board host.
    post_url = f"https://boards.greenhouse.io/{ref.board}/jobs/{ref.posting_id}"
    data = {str(k): str(v) for k, v in answers.items() if v not in (None, "")}

    # Validate against the job's FULL schema, not just name/email — a
    # required question the UI never rendered (e.g. location_questions
    # before that section was merged) must fail the dry run, not the live
    # submit. Schema fetch failing shouldn't block: fall back to basics.
    missing: list[str] = []
    try:
        form = await _greenhouse_form(ref)
        missing = [f["label"] for f in form["fields"]
                   if f["required"] and f["type"] != "file"
                   and not data.get(f["key"], "").strip()]
        # Required FILE fields: resume is always attached; a required cover
        # letter blocks with a clear message when none was generated; any
        # other required upload (portfolio, transcript…) we can't produce.
        for f in form["fields"]:
            if f["type"] != "file" or not f["required"]:
                continue
            lab = (f["label"] or f["key"]).lower()
            if "resume" in lab or "cv" in lab:
                continue
            if "cover" in lab and cover is None:
                raise ManualApplyRequired(
                    "This job REQUIRES a cover letter — generate one on the "
                    "Cover Letter tab first, then apply")
            if "cover" not in lab:
                raise ManualApplyRequired(
                    f"This job requires an upload we can't provide ({f['label']}) "
                    "— finish on the ATS page")
    except ManualApplyRequired:
        raise
    except Exception:
        missing = [k for k in ("first_name", "last_name", "email")
                   if not data.get(k)]
    if missing:
        raise ManualApplyRequired("Missing required field(s): " + ", ".join(missing))

    files = {"resume": (fname, resume, "application/pdf")}
    if cover:
        files["cover_letter"] = (cover_fname, cover, "application/pdf")

    if dry_run:
        return {"status": "dry_run",
                "detail": {"post_url": post_url, "fields": sorted(data),
                           "resume": fname, "bytes": len(resume),
                           "cover_letter": cover_fname if cover else None,
                           "all_required_answered": True}}

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA,
                                 follow_redirects=True) as cli:
        # Probe the apply page first — if it embeds a captcha, stop before
        # sending anything (we never submit around one).
        probe = await cli.get(ref.url)
        if _looks_captcha(probe.text):
            raise CaptchaRequired("Greenhouse board uses a captcha")
        r = await cli.post(post_url, data=data, files=files)

    if r.status_code in (200, 201, 302) and not _looks_captcha(r.text):
        return {"status": "submitted", "detail": {"http": r.status_code}}
    if _looks_captcha(r.text):
        raise CaptchaRequired("Greenhouse rejected: captcha challenge")
    raise ManualApplyRequired(f"Greenhouse returned HTTP {r.status_code}")


async def _lever_submit(ref: AtsRef, answers: dict, resume: bytes,
                        fname: str, dry_run: bool) -> dict:
    post_url = f"https://jobs.lever.co/{ref.board}/{ref.posting_id}/apply"
    data = {str(k): str(v) for k, v in answers.items() if v not in (None, "")}
    for req_f in ("name", "email"):
        if not data.get(req_f):
            raise ManualApplyRequired(f"Missing required field: {req_f}")
    files = {"resume": (fname, resume, "application/pdf")}

    if dry_run:
        return {"status": "dry_run",
                "detail": {"post_url": post_url, "fields": sorted(data),
                           "resume": fname, "bytes": len(resume)}}

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA,
                                 follow_redirects=True) as cli:
        probe = await cli.get(f"https://jobs.lever.co/{ref.board}/{ref.posting_id}/apply")
        if _looks_captcha(probe.text):
            raise CaptchaRequired("Lever board uses a captcha")
        r = await cli.post(post_url, data=data, files=files)

    if r.status_code in (200, 201, 302) and not _looks_captcha(r.text):
        return {"status": "submitted", "detail": {"http": r.status_code}}
    if _looks_captcha(r.text):
        raise CaptchaRequired("Lever rejected: captcha challenge")
    if r.status_code == 429:
        raise ManualApplyRequired("Lever rate-limited the submission (429) — retry later")
    raise ManualApplyRequired(f"Lever returned HTTP {r.status_code}")
