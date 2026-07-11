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
#   {key, label, type, required, options?}   type ∈ text | textarea | select |
#   multiselect | boolean | file | unsupported

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
    # (2026-07-10): answers come only from the user's own saved application
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

    return {
        "fields": [f.as_dict() for f in fields],
        "apply_url": data.get("absolute_url") or ref.url,
        "meta": {"title": data.get("title", ""), "location":
                 (data.get("location") or {}).get("name", "")},
    }


# ── Lever ─────────────────────────────────────────────────────────────────────
# Docs: https://github.com/lever/postings-api — GET posting JSON is public.
# Custom questions are NOT exposed publicly; standard fields only. If the
# hosted apply page carries extra required cards or a captcha we can't see,
# submit() detects that and degrades to manual.

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


async def _lever_form(ref: AtsRef) -> dict:
    api = f"https://api.lever.co/v0/postings/{ref.board}/{ref.posting_id}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as cli:
        r = await cli.get(api)
    if r.status_code == 404:
        raise ValueError("Lever posting not found (expired)")
    r.raise_for_status()
    data = r.json()

    fields = [FormField(key=k, label=l, type=t, required=req).as_dict()
              for k, l, t, req in _LEVER_STANDARD]
    return {
        "fields": fields,
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


async def _ashby_form(ref: AtsRef) -> dict:
    api = f"https://api.ashbyhq.com/posting-api/job-board/{ref.board}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as cli:
        r = await cli.get(api)
    if r.status_code == 404:
        raise ValueError("Ashby board not found")
    r.raise_for_status()
    jobs = (r.json() or {}).get("jobs", [])
    job = next((j for j in jobs if j.get("id") == ref.posting_id), None)
    if not job:
        raise ValueError("Ashby posting not found on board (expired)")

    fields = [FormField(key=k, label=l, type=t, required=req).as_dict()
              for k, l, t, req in _ASHBY_STANDARD]
    return {
        "fields": fields,
        "apply_url": job.get("jobUrl") or ref.url,
        "meta": {"title": job.get("title", ""), "location": job.get("location", "")},
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
    s = re.sub(r"[^a-z0-9 ]+", " ", (label or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _pick_option(options: list[dict], want: str) -> str:
    """Match a stored answer (an option LABEL from some earlier form) to this
    form's options. Exact normalized match first, containment either way
    second. Returns the option VALUE, or '' when nothing matches."""
    if not want:
        return ""
    w = _norm_label(want)
    for o in options:
        if _norm_label(o["label"]) == w:
            return o["value"]
    for o in options:
        ol = _norm_label(o["label"])
        if w and ol and (w in ol or ol in w):
            return o["value"]
    return ""


def _pick_yes_no(options: list[dict], yes: bool) -> str:
    want = "yes" if yes else "no"
    for o in options:
        head = _norm_label(o["label"]).split(",")[0].split()[:1]
        if head and head[0] == want:
            return o["value"]
    return _pick_option(options, want)


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
    (re.compile(r"sponsor|immigration case|visa\b", re.I), "need_sponsorship", "yesno"),
    (re.compile(r"authoriz\w* to work|legally.{0,30}work|work authorization|eligible to work", re.I),
     "work_authorized", "yesno"),
    (re.compile(r"relocat", re.I), "relocation", "yesno"),
    (re.compile(r"salary|compensation|pay expectation", re.I), "salary", "text"),
    (re.compile(r"\bzip\b|postal code", re.I), "zip", "text"),
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
    (re.compile(r"gender identity|identify.{0,20}gender", re.I), "demo_gender", "option"),
    (re.compile(r"race|ethnicit", re.I), "demo_race", "option"),
    (re.compile(r"veteran", re.I), "demo_veteran", "option"),
    (re.compile(r"disabilit|impairment", re.I), "demo_disability", "option"),
]

# Consent/acknowledgement questions (privacy notice, AI policy, T&C read).
# Auto-picked ONLY as a prefill the user still reviews in the modal before
# any submit — clicking submit is the actual act of consent.
_CONSENT_LABEL = re.compile(
    r"consent|acknowledge|agree|policy|privacy|terms|personal data", re.I)
_CONSENT_OPTION = re.compile(r"acknowledge|confirm|agree|yes", re.I)

# Conditional follow-ups ("If you selected 'Other'…") depend on another
# answer — never auto-filled from class rules.
_CONDITIONAL_LABEL = re.compile(r"if you (selected|answered|chose)|if other", re.I)


def _class_answer(label: str, ftype: str, options: list[dict],
                  ap: dict) -> str:
    """Answer one question from the saved application profile. '' = no match."""
    if _CONDITIONAL_LABEL.search(label):
        return ""
    for pat, key, kind in _CLASS_RULES:
        if not pat.search(label):
            continue
        stored = ap.get(key)
        if stored in (None, ""):
            return ""
        if kind == "years" and options:
            try:
                return _pick_years_bucket(options, float(stored))
            except (TypeError, ValueError):
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
    first, last = _split_name(profile.get("name", ""))
    by_key = {
        "first_name": first, "last_name": last,
        "email": profile.get("email", ""), "phone": profile.get("phone", ""),
        "name": profile.get("name", ""),
        "location": profile.get("location", ""),
        "org": profile.get("current_company", ""),
        "urls[LinkedIn]": profile.get("linkedin", ""),
        "urls[GitHub]": profile.get("github", ""),
        "urls[Portfolio]": profile.get("website", ""),
        "_systemfield_name": profile.get("name", ""),
        "_systemfield_email": profile.get("email", ""),
        "_systemfield_phone": profile.get("phone", ""),
    }
    _label_rules = [
        (re.compile(r"\blocation\b|\bcity\b", re.I), profile.get("location", "")),
        (re.compile(r"\blinkedin\b", re.I), profile.get("linkedin", "")),
        (re.compile(r"\bgithub\b", re.I), profile.get("github", "")),
        (re.compile(r"\b(website|portfolio)\b", re.I), profile.get("website", "")),
        (re.compile(r"\bphone\b", re.I), profile.get("phone", "")),
        (re.compile(r"\bemail\b", re.I), profile.get("email", "")),
        (re.compile(r"(current|present).{0,20}(company|employer)", re.I),
         profile.get("current_company", "")),
    ]

    answers: dict[str, Any] = {}
    for f0 in fields:
        key, label, ftype = f0["key"], f0["label"], f0["type"]
        opts = f0.get("options") or []
        if ftype == "file":
            continue    # resume/cover handled separately server-side

        val = by_key.get(key, "")

        # Answer memory: stored as option LABEL (portable across companies
        # whose option ids differ) or raw text for free-text questions.
        if not val:
            remembered = mem.get(_norm_label(label))
            if remembered:
                val = _pick_option(opts, remembered) if opts else remembered

        if not val:
            val = _class_answer(label or "", ftype, opts, ap)

        # Label-rule fallback fills FREE-TEXT fields only.
        if not val and ftype in ("text", "textarea"):
            for pat, candidate in _label_rules:
                if candidate and pat.search(label or ""):
                    val = candidate
                    break
        if val:
            answers[key] = val
    return answers


def extract_memory(fields: list[dict], answers: dict) -> dict:
    """Turn one submission's answers into memory entries: normalized question
    label → option LABEL (selects) or raw text. Option labels — not values —
    so the memory transfers to other companies' forms."""
    out: dict[str, str] = {}
    for f0 in fields:
        key, label, ftype = f0["key"], f0["label"], f0["type"]
        if ftype == "file":
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
