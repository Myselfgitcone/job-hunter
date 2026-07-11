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
    for q in data.get("questions", []):
        f0 = (q.get("fields") or [{}])[0]
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


def prefill(fields: list[dict], profile: dict) -> dict:
    """
    Deterministically map profile values onto form fields by key/label.
    profile keys: name, email, phone, address, linkedin, github, website,
    visa, current_company. Unknown questions stay blank for the user to fill —
    NOTHING is invented (same zero-fabrication rule as the resume pipeline).
    """
    first, last = _split_name(profile.get("name", ""))
    by_key = {
        "first_name": first, "last_name": last,
        "email": profile.get("email", ""), "phone": profile.get("phone", ""),
        "name": profile.get("name", ""),
        "org": profile.get("current_company", ""),
        "urls[LinkedIn]": profile.get("linkedin", ""),
        "urls[GitHub]": profile.get("github", ""),
        "urls[Portfolio]": profile.get("website", ""),
        "_systemfield_name": profile.get("name", ""),
        "_systemfield_email": profile.get("email", ""),
        "_systemfield_phone": profile.get("phone", ""),
    }
    _label_rules = [
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
        if ftype == "file":
            continue    # resume/cover handled separately server-side
        val = by_key.get(key, "")
        # Label-rule fallback fills FREE-TEXT fields only. Booleans/selects
        # (visa, relocation, consent…) are decisions — the user answers them.
        if not val and ftype in ("text", "textarea"):
            for pat, candidate in _label_rules:
                if candidate and pat.search(label or ""):
                    val = candidate
                    break
        if val:
            answers[key] = val
    return answers


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
                 resume_filename: str, dry_run: bool = True) -> dict:
    """
    Submit one application through the same public endpoint the hosted
    board's own Apply form posts to. Returns
      {"status": "submitted" | "dry_run", "detail": ...}
    Raises CaptchaRequired / ManualApplyRequired for graceful UI fallback.

    dry_run=True builds and validates the payload but sends NOTHING.
    """
    if ref.ats == "greenhouse":
        return await _greenhouse_submit(ref, answers, resume_bytes,
                                        resume_filename, dry_run)
    if ref.ats == "lever":
        return await _lever_submit(ref, answers, resume_bytes,
                                   resume_filename, dry_run)
    # Ashby's hosted-board submit route is an unversioned internal GraphQL
    # endpoint — too unstable to ship in phase 1. Manual with prefill.
    raise ManualApplyRequired("Ashby submission requires the company's API "
                              "key — use the pre-filled manual flow")


async def _greenhouse_submit(ref: AtsRef, answers: dict, resume: bytes,
                             fname: str, dry_run: bool) -> dict:
    # The embedded job board posts multipart form-data to the board host.
    post_url = f"https://boards.greenhouse.io/{ref.board}/jobs/{ref.posting_id}"
    data = {str(k): str(v) for k, v in answers.items() if v not in (None, "")}
    for req_f in ("first_name", "last_name", "email"):
        if not data.get(req_f):
            raise ManualApplyRequired(f"Missing required field: {req_f}")
    files = {"resume": (fname, resume, "application/pdf")}

    if dry_run:
        return {"status": "dry_run",
                "detail": {"post_url": post_url, "fields": sorted(data),
                           "resume": fname, "bytes": len(resume)}}

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
