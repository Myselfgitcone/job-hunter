"""PROTECT pipeline (2026-10-29): tailor a strong base resume without damaging it.

    TAILOR_PIPELINE=protect        (ai/tailor_slim.tailor_resume_routed)

The base is the product. One cheap analyze pass finds the posting's tools and title;
the posting's must-have lines are capped at MAX_DUTIES; the writer may reorder,
re-word and emphasise, and may add at most MAX_NEW_BULLETS; code then enforces what
the prompt promised: the base's headline and contact line (city kept), every base
figure, no tool the base does not own, no invented figure, per-job caps, PROJECTS /
EDUCATION / CERTIFICATIONS carried verbatim (projects ordered by the posting's family).

Same signature and return shape as ai.tailor.tailor_resume, so the app, the gate and
the live checker call it exactly like the mirror.
"""
from __future__ import annotations

import re

from ai import tailor as t
from ai import tailor_mirror as m
from ai.tailor_protect_prompt import PROTECT_SYSTEM
from ai.tailor_slim import fix_figures_only
from ai.tailor_slim_guards import slim_score, trim_vague_endings

# ── Rules (Kevin Landuchi / ApplyPass, 2026-10-29) ────────────────────────────
JOB_MAX = (7, 5, 4)          # bullets by recency; job 4 and older: 3
JOB_MIN = (5, 3, 2)
SUMMARY_LINES_MAX = 3
SKILL_ITEMS_SLACK = 4        # the writer may add this many items over the base's own count
MAX_DUTIES = 10              # must-haves the writer is shown
MAX_NEW_BULLETS = 3
BULLET_MAX = 30
COVERAGE_REVIEW_BELOW = 70   # % of must-haves with a bullet; lower → needs_review

_SECTION_ORDER = ("SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS")
_SECTION_ALIASES = {"PROFESSIONAL SUMMARY": "SUMMARY", "TECHNICAL SKILLS": "SKILLS",
                    "PROFESSIONAL EXPERIENCE": "EXPERIENCE", "WORK EXPERIENCE": "EXPERIENCE"}
_AI_FAMILY_RE = re.compile(r"\b(ai|ml|llm|genai|gen ai|generative|machine learning|mlops|rag|agent\w*|nlp)\b", re.I)
_AI_PROJECT_RE = re.compile(r"\b(rag|llm|mcp|agent\w*|langgraph|langchain|embedding\w*|evaluation suite|claude|openai)\b", re.I)
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_ROLE_LINE_RE = re.compile(r"\b(engineer|developer|architect|analyst|scientist|manager|lead|consultant|specialist|administrator)\b", re.I)


def _cap(j: int) -> int:
    return JOB_MAX[j] if j < len(JOB_MAX) else 3


# ── Section split / rebuild ───────────────────────────────────────────────────
def split_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """(header lines before the first section, {SECTION: lines}). Section names are
    normalised to _SECTION_ORDER; headers are the engine's UPPERCASE[:] lines."""
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    cur: str | None = None
    for raw in text.split("\n"):
        s = raw.strip()
        bare = s.rstrip(":").strip()
        if s and bare == bare.upper() and bare in (_SECTION_ORDER + tuple(_SECTION_ALIASES)) and not s.startswith("•"):
            cur = _SECTION_ALIASES.get(bare, bare)
            sections.setdefault(cur, [])
            continue
        if cur is None:
            if s:
                header.append(s)
        else:
            sections[cur].append(raw.rstrip())
    return header, sections


def _bulletize(lines: list[str], keep_plain) -> list[str]:
    """Upload text carries no bullet glyphs (python-docx drops them). Inside EXPERIENCE,
    PROJECTS and SKILLS everything that is not a header/title keeps a "• " prefix."""
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if s.startswith(("•", "-", "*")):
            out.append("• " + s.lstrip("•-* ").strip())
        elif keep_plain(s):
            out.append(s)
        else:
            out.append("• " + s)
    return out


def normalize_base(base: str) -> str:
    """The base exactly as the app's upload produced it, made engine-shaped: known
    section headers with colons, job headers normalised, bullets prefixed."""
    text = t._normalize_format(t.normalize_job_headers((base or "").strip()))
    header, sec = split_sections(text)
    is_job = lambda s: t._is_job_header_line(s)
    is_title = lambda s: " — " in s and not s.startswith("•")          # project title line
    is_tech = lambda s: s.lower().startswith("technologies used")
    if "EXPERIENCE" in sec:
        sec["EXPERIENCE"] = _bulletize(sec["EXPERIENCE"], lambda s: is_job(s) or is_tech(s))
    if "PROJECTS" in sec:
        sec["PROJECTS"] = _bulletize(sec["PROJECTS"], is_title)
    if "SKILLS" in sec:
        sec["SKILLS"] = _bulletize(sec["SKILLS"], lambda s: False)
    return rebuild(header, sec)


def rebuild(header: list[str], sec: dict[str, list[str]]) -> str:
    parts = ["\n".join(header).strip()]
    for name in _SECTION_ORDER:
        body = [ln for ln in sec.get(name, []) if ln.strip()]
        if body:
            parts.append(f"{name}:\n" + "\n".join(body))
    return "\n\n".join(p for p in parts if p).strip() + "\n"


def base_identity(header: list[str], base_text: str) -> tuple[str, str, str]:
    """(name, title line, contact line) from the base's own top lines. The title is the
    header line that is neither the name nor the contact line; failing that, the real
    title of the first job."""
    name = header[0].strip() if header else ""
    contact = next((h for h in header if t._HDR_PHONE_RE.search(h) or t._HDR_EMAIL_RE.search(h)), "")
    title = next((h for h in header[1:] if h != contact and _ROLE_LINE_RE.search(h) and len(h.split()) <= 8), "")
    if not title:
        for ln in base_text.splitlines():
            if t._is_job_header_line(ln):
                title = ln.split(" @ ", 1)[0].strip()
                break
    return name, title, contact


# ── Ownership: what the base really has ───────────────────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9+#./ ]", " ", (s or "").lower()).strip()


def owned_terms(base_text: str, profile_skills: list[str] | None) -> set[str]:
    terms = {_norm(x) for x in (profile_skills or []) if x}
    for ln in base_text.splitlines():
        s = ln.strip()
        if s.startswith("•") and ":" in s and len(s.partition(":")[0]) < 60:
            terms.update(_norm(x) for x in t._split_list_items(s.partition(":")[2]) if x.strip())
    return {x for x in terms if x}


_STOP = {"and", "or", "the", "of", "for", "with", "in", "on", "to", "a", "an", "apis", "api", "tools", "tool"}


def is_owned(term: str, base_low: str, owned: set[str]) -> bool:
    """Owned when the base (or the profile) names it: as a whole phrase, or when every
    real word of it is a word the base uses ("OpenAI and Anthropic APIs" vs the base's
    "Anthropic and OpenAI APIs"; "Spark Streaming" vs "Spark Structured Streaming")."""
    n = _norm(term)
    if not n:
        return False
    if n in owned or re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", base_low):
        return True
    words = [w for w in re.findall(r"[a-z0-9+#.]+", n) if len(w) >= 3 and w not in _STOP]
    return bool(words) and all(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", base_low) for w in words)


def is_product(term: str) -> bool:
    """A product, language or platform (BigQuery, dbt, Looker); not a concept phrase
    ("data quality frameworks", "fact/dim tables"). Concepts are covered by must-haves."""
    x = str(term).strip()
    return bool(re.search(r"[A-Z0-9+#]", x)) or len(x.split()) == 1


def split_tools(target_tools: list, base_text: str, profile_skills: list[str] | None) -> tuple[list[str], list[str]]:
    base_low = _norm(base_text)
    owned = owned_terms(base_text, profile_skills)
    have, gaps = [], []
    for x in target_tools or []:
        if is_owned(str(x), base_low, owned):
            have.append(str(x))
        elif is_product(str(x)):
            gaps.append(str(x))
    return have, gaps


_PITCH_RE = re.compile(r"^(in this role|this role|you will|you'll|you would|we are|we're|our team|join us|if (you|leading))", re.I)
_REQ_RE = re.compile(r"(experience|expertise|proficien\w*|hands-on|years|degree|ability to|knowledge of|familiar\w*)", re.I)
_VERB_RE = re.compile(r"^(build|design|develop|own|implement|maintain|create|write|deliver|partner|lead|drive|define|operate|optimi[sz]e|monitor|automate|migrate|model|ship|scale)", re.I)
_PAY_RE = re.compile(r"(pay|salary|compensation|bonus|equity|benefits?)", re.I)


def select_must_haves(duties: list[str], tools: list, limit: int = MAX_DUTIES) -> list[str]:
    """The posting's core requirements, not its pitch: lines that name a tool, state a
    requirement or describe concrete work rank first; intro prose and pay lines are out.
    Order among the chosen stays the posting's."""
    tool_low = [_norm(str(x)) for x in (tools or []) if _norm(str(x))]
    scored = []
    for i, d in enumerate(duties):
        low = _norm(d)
        if _PAY_RE.search(d) or _PITCH_RE.search(d.strip()):
            continue
        score = 0
        score += 3 * min(2, sum(1 for x in tool_low if re.search(r"(?<![a-z0-9])" + re.escape(x) + r"(?![a-z0-9])", low)))
        score += 2 if _REQ_RE.search(d) else 0
        score += 2 if _VERB_RE.search(d.strip()) else 0
        score -= 2 if len(d.split()) > 35 else 0
        scored.append((score, i, d))
    top = sorted(scored, key=lambda x: (-x[0], x[1]))[:limit]
    return [d for _, _, d in sorted(top, key=lambda x: x[1])]


# ── Guards on the writer's output ─────────────────────────────────────────────
def strip_unowned_skills(skills_lines: list[str], base_text: str, profile_skills: list[str] | None,
                         notes: list) -> list[str]:
    base_low = _norm(base_text)
    owned = owned_terms(base_text, profile_skills)
    out, dropped, total = [], [], 0
    for ln in skills_lines:
        s = ln.strip()
        if not s.startswith("•") or ":" not in s:
            continue
        label, _, items = s.lstrip("• ").partition(":")
        keep = []
        for it in t._split_list_items(items):
            it = it.strip(" ,;")
            if not it:
                continue
            if is_owned(it, base_low, owned):
                if it not in keep:
                    keep.append(it)
            else:
                dropped.append(it)
        if keep:
            out.append(f"• {label.strip()}: {', '.join(keep)}")
            total += len(keep)
    if dropped:
        notes.append(f"skills guard: removed {len(dropped)} item(s) the base does not own: {', '.join(dropped[:8])}")
    return out


def _figures(text: str) -> set[str]:
    return {f for f in t._num_tokens(text) if not _YEAR_RE.match(f)}


def drop_foreign_bullets(exp_text: str, base_text: str, jd: str, gaps: list[str], notes: list) -> str:
    """A bullet that names a GAP tool, or carries a figure the base never stated, is
    removed: that is exactly the fabrication this pipeline exists to stop."""
    base_figs = _figures(base_text)
    lines = exp_text.split("\n")
    gap_rx = [re.compile(r"(?<![a-z0-9])" + re.escape(_norm(g)) + r"(?![a-z0-9])") for g in gaps if _norm(g)]
    drop: set[int] = set()
    why: list[str] = []
    for _, bl in t._job_bullet_lines(exp_text):
        for i in bl:
            body = lines[i].lstrip()[1:].strip()
            low = _norm(body)
            hit = next((g for g, rx in zip(gaps, gap_rx) if rx.search(low)), None)
            if hit:
                drop.add(i); why.append(f"names {hit!r}")
                continue
            new = _figures(body) - base_figs
            if new:
                drop.add(i); why.append(f"invented {sorted(new)}")
    if drop:
        notes.append(f"foreign guard: removed {len(drop)} bullet(s): " + "; ".join(why[:5]))
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def enforce_caps(exp_text: str, notes: list, jd_words: set, tools: list) -> str:
    lines = exp_text.split("\n")
    drop: set[int] = set()
    for j, bl in t._job_bullet_lines(exp_text):
        extra = len(bl) - _cap(j)
        if extra <= 0:
            continue
        body = lambda i: lines[i].lstrip()[1:].strip()
        rank = sorted(bl, key=lambda i: m.jd_strength(body(i), jd_words, tools))
        weak = [i for i in rank if not t._num_tokens(body(i))]
        for i in (weak + [i for i in rank if i not in weak])[:extra]:
            drop.add(i)
    if drop:
        notes.append(f"cap guard: trimmed {len(drop)} bullet(s) past the {JOB_MAX} caps")
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def order_projects(project_lines: list[str], job_title: str, jd: str) -> list[str]:
    """Projects travel verbatim; for an AI-family posting the AI projects lead."""
    blocks, cur = [], []
    for ln in project_lines:
        if ln.strip() and not ln.strip().startswith("•") and cur:
            blocks.append(cur); cur = []
        if ln.strip():
            cur.append(ln)
    if cur:
        blocks.append(cur)
    ai_posting = bool(_AI_FAMILY_RE.search(job_title or "")) or len(_AI_FAMILY_RE.findall(jd or "")) >= 6
    key = lambda b: 0 if bool(_AI_PROJECT_RE.search(" ".join(b))) == ai_posting else 1
    ordered = sorted(blocks, key=key)
    out: list[str] = []
    for b in ordered:
        out.extend(b); out.append("")
    return out[:-1] if out else out


_YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*years?\b", re.I)


def fix_years(summary_lines: list[str], base_summary: list[str], notes: list) -> list[str]:
    """The writer must not inflate tenure: every "N+ years" in the summary becomes the
    base's own phrase (live: "5+ years" came back as "6+ years" and "7+ years")."""
    base_phrase = next((m.group(0) for ln in base_summary for m in [_YEARS_RE.search(ln)] if m), "")
    base_n = {m.group(1) for ln in base_summary for m in _YEARS_RE.finditer(ln)}
    out, fixed = [], 0
    for ln in summary_lines:
        def swap(m):
            nonlocal fixed
            if m.group(1) in base_n:
                return m.group(0)
            fixed += 1
            return base_phrase or m.group(0)
        out.append(_YEARS_RE.sub(swap, ln))
    if fixed:
        notes.append(f"summary guard: reset {fixed} inflated years claim(s) to the base's {base_phrase!r}")
    return out


def restore_lost_figures(exp_text: str, base_exp: str, notes: list) -> str:
    """Every base bullet whose figures are absent from the tailored job comes back as
    written, replacing that job's weakest numberless bullet when the job is at its cap."""
    lines = exp_text.split("\n")
    have = _figures(exp_text)
    base_jobs = dict(t._job_bodies(base_exp))
    restored = 0
    for j, h in enumerate([i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]):
        hdr_now = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
        h = hdr_now[j]
        co = t._company_key(lines[h])
        for b in base_jobs.get(co, "").splitlines():
            b = b.strip()
            if not b.startswith("•"):
                continue
            figs = _figures(b)
            if not figs or figs & have:
                continue
            jobs = dict(t._job_bullet_lines("\n".join(lines)))
            bl = jobs.get(j, [])
            numberless = [i for i in bl if not t._num_tokens(lines[i])]
            if len(bl) >= _cap(j) and numberless:
                lines[numberless[-1]] = b
            else:
                lines.insert((bl[-1] + 1) if bl else h + 1, b)
            have |= figs
            restored += 1
    if restored:
        notes.append(f"figure guard: restored {restored} base bullet(s) whose figures had been lost")
    return "\n".join(lines)


def trim_skills(skills_lines: list[str], cap: int, notes: list) -> list[str]:
    rows = []
    for ln in skills_lines:
        label, _, items = ln.lstrip("• ").partition(":")
        rows.append([label.strip(), [x.strip() for x in t._split_list_items(items) if x.strip()]])
    total = sum(len(r[1]) for r in rows)
    cut = 0
    while total > cap:
        r = max((r for r in rows if len(r[1]) > 2), key=lambda r: len(r[1]), default=None)
        if r is None:
            break
        r[1].pop(); total -= 1; cut += 1
    if cut:
        notes.append(f"skills guard: trimmed {cut} item(s) to the base's count + {SKILL_ITEMS_SLACK}")
    return [f"• {label}: {', '.join(items)}" for label, items in rows if items]


def settle_long_bullets(exp_text: str, base_exp: str, notes: list, limit: int = BULLET_MAX + 2) -> str:
    """Last resort after split and compress: a bullet still past `limit` words is swapped
    for the base bullet that carries the same figure (the compress pass was reverted for
    changing it), or trimmed at its last clause break when no base bullet matches."""
    lines = exp_text.split("\n")
    base_bullets = [b.strip() for b in base_exp.splitlines() if b.strip().startswith("\u2022")]
    fixed = 0
    for _, bl in t._job_bullet_lines(exp_text):
        for i in bl:
            body = lines[i].lstrip()[1:].strip()
            if len(body.split()) <= limit:
                continue
            figs = _figures(body)
            twin = next((b for b in base_bullets if figs and _figures(b) & figs), None)
            if twin:
                lines[i] = twin
            else:
                head = " ".join(body.split()[:limit])
                cut = max(head.rfind(", "), head.rfind("; "))
                lines[i] = "\u2022 " + ((head[:cut].rstrip(" ,;") + ".") if cut > 40 else (head.rstrip(" ,;") + "."))
            fixed += 1
    if fixed:
        notes.append(f"length guard: settled {fixed} bullet(s) still past {limit} words")
    return "\n".join(lines)


def _terms_in(text: str, terms: list[str]) -> list[str]:
    low = _norm(text)
    return [x for x in terms if re.search(r"(?<![a-z0-9])" + re.escape(_norm(x)) + r"(?![a-z0-9])", low)]


def uncovered_must_haves(duties: list[str], tailored: str, tools: list[str]) -> list[int]:
    """A must-have is covered when the resume names every tool it names (and it names at
    least one), or when a quarter of its distinctive stems sit in one bullet or summary
    line, or half of them anywhere. Looser than the mirror's rule on purpose: the
    protect writer re-words the candidate's work, it does not echo the posting."""
    lines = tailored.split("\n")
    units = [lines[i].lower() for _, bl in t._job_bullet_lines(tailored) for i in bl] + \
            [lines[i].lower() for i in t._summary_lines(tailored)]
    blob = "\n".join(units)
    missing = []
    for n, d in enumerate(duties):
        named = _terms_in(d, tools)
        if named and len(_terms_in(tailored, named)) == len(named):
            continue
        stems = m._duty_stems(d)
        if not stems:
            continue
        hit = lambda text: sum(1 for st in stems if re.search(rf"\b{st}", text)) / len(stems)
        if max((hit(u) for u in units), default=0.0) >= 0.25 or hit(blob) >= 0.50:
            continue
        missing.append(n)
    return missing


def headline_for(title: str, job_title: str, jd: str) -> str:
    """The base title line, with its halves swapped for the posting's family when it
    carries two titles ("Senior Data Engineer | AI Engineer" -> AI first for an AI
    posting). Both titles are the candidate's own; nothing from the posting is pasted."""
    parts = [x.strip() for x in re.split(r"\s*\|\s*", title or "") if x.strip()]
    if len(parts) != 2:
        return title
    ai_posting = bool(_AI_FAMILY_RE.search(job_title or "")) or len(_AI_FAMILY_RE.findall(jd or "")) >= 6
    ai_first = bool(_AI_FAMILY_RE.search(parts[0]))
    if ai_posting != ai_first:
        parts.reverse()
    return " | ".join(parts)


def summary_ok(summary_lines: list[str], base_summary: list[str]) -> bool:
    text = " ".join(summary_lines)
    if not text.strip() or len(summary_lines) > SUMMARY_LINES_MAX:
        return False
    base_figs = _figures(" ".join(base_summary))
    return len(_figures(text) & base_figs) >= min(2, len(base_figs))


# ── The pipeline ──────────────────────────────────────────────────────────────
async def tailor_resume_protect(base_resume: str, job_description: str,
                                api_key: str, provider: str, model: str,
                                profile_skills: list[str] | None = None,
                                secondary_model: str = "",
                                user_job_roles: list[str] | None = None,
                                profile_projects: list[dict] | None = None,
                                company: str = "",
                                job_title: str = "",
                                keys=None) -> tuple[str, dict]:
    notes: list[str] = ["pipeline: protect"]
    reasons: list[str] = []
    try:
        from ai.llm import reset_usage
        reset_usage()
    except Exception:  # noqa: BLE001
        pass
    try:
        from resume_lint import clean_jd_html
        job_description = clean_jd_html(job_description)
    except Exception:  # noqa: BLE001
        pass
    job_description = (job_description or "").strip()
    if len((base_resume or "").strip()) < 40:
        raise ValueError("Resume text is too short — upload or paste your resume first.")
    if len(job_description) < 40:
        raise ValueError("Job description is too short. Paste the full posting.")

    base = normalize_base(base_resume)
    header, bsec = split_sections(base)
    name, title, contact = base_identity(header, base)
    cheap = secondary_model or model
    main_kw = {"api_key": api_key, "provider": provider, "model": model, "keys": keys}
    cheap_kw = {"api_key": api_key, "provider": provider, "model": cheap, "keys": keys}

    # ── 1. ANALYZE (cheap) ───────────────────────────────────────────────
    context: dict = {}
    for attempt in (1, 2):
        try:
            raw = await t.chat(t.ANALYZE_SYSTEM, t.analyze_prompt(base, job_description),
                               max_tokens=6000, pass_name="analyze" if attempt == 1 else "analyze_retry", **cheap_kw)
            context = t._loads_loose(raw)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"analyze: attempt {attempt} failed ({exc})")
            context = {}
        if t._analysis_ok(context):
            break
    if not t._analysis_ok(context):
        raise ValueError("Could not analyze this job description (the model returned no usable analysis twice).")
    for k in ("present", "missing", "baseline_missing", "responsibilities", "target_tools"):
        context.setdefault(k, [])
    context["target_cloud"] = "None"                      # protect never swaps a cloud
    context["target_tools"] = [x for x in context["target_tools"]
                               if not t._is_soft_skill(str(x)) and t._phrase_in_jd(str(x), job_description)]
    if (job_title or "").strip():
        context["job_title"] = job_title.strip()
    job_description, cut = t._trim_jd_tail(job_description, context.get("jd_tail_starts"), context["target_tools"])
    if cut:
        notes.append(f"jd trimmed: dropped {cut} chars of pay/benefits/legal tail")

    # ── 2. MUST-HAVES, OWNED TOOLS, GAPS ────────────────────────────────
    duties = select_must_haves(
        m.jd_duties(job_description, company or str(context.get("company") or ""), context["target_tools"]),
        context["target_tools"])
    have, gaps = split_tools(context["target_tools"], base, profile_skills)
    notes.append(f"must-haves: {len(duties)} | owned tools: {len(have)} | gaps: {len(gaps)}"
                 + (f" ({', '.join(gaps[:6])})" if gaps else ""))

    # ── 3. WRITE (one pass) ──────────────────────────────────────────────
    hints = t._base_number_hints(base)
    system = PROTECT_SYSTEM.format(max_new=MAX_NEW_BULLETS, cap1=JOB_MAX[0], cap2=JOB_MAX[1], cap3=JOB_MAX[2])
    writer_input = rebuild([], {k: bsec.get(k, []) for k in ("SUMMARY", "SKILLS", "EXPERIENCE")})
    prompt = (
        f"POSTING TITLE: {context.get('job_title', '')}\n\n"
        "MUST-HAVES (cover with existing bullets first; at most "
        f"{MAX_NEW_BULLETS} new bullets in total):\n" + "\n".join(f"  M{n + 1}: {d}" for n, d in enumerate(duties)) + "\n\n"
        f"OWNED TOOLS the posting names (use these words): {', '.join(have) or '(none)'}\n"
        f"GAPS (never write these): {', '.join(gaps) or '(none)'}\n\n"
        + (("BASE FIGURES (each stays exactly as written, in its own job):\n  " + "\n  ".join(hints) + "\n\n") if hints else "")
        + f"JOB DESCRIPTION:\n{job_description}\n\nBASE RESUME SECTIONS:\n{writer_input}\n\n"
        "Return SUMMARY, SKILLS and EXPERIENCE now, in the plain-text format.")
    raw = (await t.chat(system, prompt, max_tokens=6000, pass_name="tailor", **main_kw)).strip()
    _, osec = split_sections(t._normalize_format(raw))

    # ── 4. GUARDS ────────────────────────────────────────────────────────
    # summary
    summary = fix_years([ln for ln in osec.get("SUMMARY", []) if ln.strip()],
                        [ln for ln in bsec.get("SUMMARY", []) if ln.strip()], notes)
    if not summary_ok(summary, [ln for ln in bsec.get("SUMMARY", []) if ln.strip()]):
        notes.append("summary guard: writer's summary lost the base figures; base summary kept")
        summary = [ln for ln in bsec.get("SUMMARY", []) if ln.strip()]
    # skills
    skills = strip_unowned_skills(osec.get("SKILLS", []), base, profile_skills, notes)
    if not skills:
        skills = [ln for ln in bsec.get("SKILLS", []) if ln.strip()]
        notes.append("skills guard: writer's rows unusable; base rows kept")
    base_items = sum(len(t._split_list_items(ln.partition(":")[2])) for ln in bsec.get("SKILLS", []) if ":" in ln)
    skills = trim_skills(skills, base_items + SKILL_ITEMS_SLACK, notes)
    # experience
    exp = "EXPERIENCE:\n" + "\n".join(ln for ln in osec.get("EXPERIENCE", []) if ln.strip())
    base_exp = "EXPERIENCE:\n" + "\n".join(ln for ln in bsec.get("EXPERIENCE", []) if ln.strip())
    exp = t.normalize_job_headers(exp)
    exp = m.drop_invented_jobs(exp, base_exp, notes)
    exp = m.merge_duplicate_jobs(exp, notes)
    if not t._job_bodies(exp) or {c for c, _ in t._job_bodies(exp)} != {c for c, _ in t._job_bodies(base_exp)}:
        notes.append("experience guard: employers changed or missing; base experience kept")
        exp = base_exp
    exp = m.strip_hedges(exp, notes)
    exp = m.strip_filler(exp, notes)
    exp, intens = t._strip_intensifiers(exp)
    if intens:
        notes.append(f"intensifier guard: removed {intens}")
    exp = await fix_figures_only(exp, base_exp, job_description, notes, **cheap_kw)
    exp = drop_foreign_bullets(exp, base_exp, job_description, gaps, notes)
    restored: list = []
    exp = m.restore_figure_bullets(exp, base_exp, job_description, notes, restored)
    exp = t._dedupe_bullets(exp, notes)
    exp = m.dedupe_across_jobs(exp, notes)
    exp = m.dedupe_within_job(exp, notes)
    exp = m.split_long(exp, notes)
    over = [i for _, bl in t._job_bullet_lines(exp) for i in bl if len(exp.split("\n")[i].split()) - 1 > BULLET_MAX]
    if over:
        exp = await t._compress_long_bullets(exp, notes, [str(x) for x in have], max_words=BULLET_MAX,
                                             target=BULLET_MAX - 4, summary_max=10 ** 6, **main_kw)
        exp = drop_foreign_bullets(exp, base_exp, job_description, gaps, notes)
    exp = await t._fix_fragment_endings(exp, job_description, notes, **cheap_kw)
    exp = trim_vague_endings(exp, notes)
    jd_words = t._content_words(" ".join(duties)) | t._content_words(job_description)
    exp = enforce_caps(exp, notes, jd_words, have)
    exp = settle_long_bullets(exp, base_exp, notes)
    exp = restore_lost_figures(exp, base_exp, notes)
    exp = t._verb_ladder_guard(exp, base_exp, [], notes)
    exp_lines = [ln for ln in exp.split("\n")[1:] if ln.strip()]
    for j, bl in t._job_bullet_lines(exp):
        if j < len(JOB_MIN) and len(bl) < JOB_MIN[j]:
            notes.append(f"job {j + 1} has {len(bl)} bullets, under the {JOB_MIN[j]} minimum")

    # ── 5. REBUILD ───────────────────────────────────────────────────────
    shown = headline_for(title, context.get("job_title", ""), job_description)
    if shown != title:
        notes.append(f"headline: titles reordered for this family: {shown!r}")
    out_header = [f"{name} — {shown}" if shown else name, contact]
    tailored = rebuild(out_header, {
        "SUMMARY": summary,
        "SKILLS": skills,
        "EXPERIENCE": exp_lines,
        "PROJECTS": order_projects([ln for ln in bsec.get("PROJECTS", [])], context.get("job_title", ""), job_description),
        "EDUCATION": bsec.get("EDUCATION", []),
        "CERTIFICATIONS": bsec.get("CERTIFICATIONS", []),
    })
    tailored = t._strip_empty_sections(tailored).strip()

    # ── 6. SCORE / REVIEW ────────────────────────────────────────────────
    miss = uncovered_must_haves(duties, tailored, [str(x) for x in context["target_tools"]])
    jobs = t._job_bullet_lines(tailored)
    mirror = {
        "duties": len(duties),
        "duty_coverage_any_job": round(100 * (len(duties) - len(miss)) / max(1, len(duties))),
        "duty_coverage_job1": round(100 * (len(duties) - len(miss)) / max(1, len(duties))),
        "duties_missing": [duties[n] for n in miss],
        "tool_bullet_coverage": round(100 * (len(have) - len(t._unevidenced(have, tailored))) / max(1, len(have))),
        "tools_without_bullet": t._unevidenced(have, tailored),
        "gaps": gaps,
        "bullets_per_job": [len(bl) for _, bl in jobs],
        "summary_lines": len(summary),
        "words": len(tailored.split()),
        "figures_kept": sorted(_figures(tailored) & _figures(base)),
        "figures_lost": sorted(_figures(base_exp) - _figures(tailored)),
    }
    notes.append(f"protect: must-haves {mirror['duty_coverage_any_job']}% (Job 1 {mirror['duty_coverage_job1']}%), "
                 f"owned tools in bullets {mirror['tool_bullet_coverage']}%, bullets {mirror['bullets_per_job']}, "
                 f"{mirror['words']} words, figures lost {mirror['figures_lost'] or 'none'}")
    scores: dict = {}
    try:
        scores = slim_score(tailored, base, job_description, context, [])
    except Exception as exc:  # noqa: BLE001
        notes.append(f"score skipped ({exc})")
    scores["mirror"] = mirror
    if mirror["duty_coverage_any_job"] < COVERAGE_REVIEW_BELOW:
        reasons.append("Must-haves without a bullet: " + "; ".join(d[:60] for d in mirror["duties_missing"][:3]))
    if gaps:
        notes.append("gaps (shown to the user, never written): " + ", ".join(gaps[:8]))
    try:
        from ai.llm import get_run_usage
        usage = get_run_usage()
    except Exception:  # noqa: BLE001
        usage = {"cost": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": []}
    for n in notes:
        print(f"[TAILOR-PROTECT] {n[:300]}")
    return tailored, {"needs_review": bool(reasons), "reasons": reasons, "notes": notes,
                      "scores": scores, "context": context, "usage": usage}
