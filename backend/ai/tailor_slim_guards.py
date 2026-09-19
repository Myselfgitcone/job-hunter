"""Code-only guards for the writer-level leftovers the slim pipeline showed in
the 2026-09-18 review (no model call in this file):

  strip_adjacent           "insurance-adjacent agribusiness…" -> real industries
  fix_pandas_placement     Pandas / NumPy never inside a Spark-scale bullet
  ensure_practice_bullets  mentoring, AI coding tools, branching / change control
  clean_skill_rows         SKILLS rows hold tools, not duties; BI row holds BI
  restore_context          "Snowflake internals" still restores the Snowflake bullet
  slim_score               the deterministic score read with the slim rules
"""
from __future__ import annotations

import re

from ai import tailor as t

_ADJACENT_RE = re.compile(r"\b[A-Za-z]+-adjacent\s+(?:industries,?\s+(?:including|such as)\s+)?", re.I)


def strip_adjacent(text: str, notes: list) -> str:
    """"insurance-adjacent agribusiness, healthcare…" invents a link to the
    JD's industry. The phrase goes; the base's real industries stay."""
    out, n = _ADJACENT_RE.subn("", text)
    if n:
        notes.append(f"industry guard: removed {n} invented '-adjacent' phrase(s)")
    return out


_PANDAS_CLAUSE_RE = re.compile(
    r",?\s*(?:using|with|via|leveraging|through)\s+(?:Pandas|NumPy)(?:\s*(?:and|,)\s*(?:Pandas|NumPy))*"
    r"(?:\s+for\s+[A-Za-z][A-Za-z\s/-]{2,40}?)?(?=,|\.|;|\s+and\b|$)", re.I)
_PANDAS_OK_RE = re.compile(r"validat|reconcil|profil|pars|file|csv|fixed-width|json|excel|report|sample|notebook", re.I)
_BIG_ENGINE_RE = re.compile(r"pyspark|spark|terabyte|databricks|streaming|emr|kafka|petabyte", re.I)
_PD_RE = re.compile(r"\b(?:pandas|numpy)\b", re.I)


def insert_job1_bullet(text: str, bullet: str) -> str:
    """Place a bullet at the end of the most recent job, above its
    Technologies Used line."""
    lines = text.split("\n")
    hdr = next((i for i, ln in enumerate(lines) if t._is_job_header_line(ln)), None)
    if hdr is None:
        return text
    end = t._job_block_end(lines, hdr)
    tech = next((k for k in range(hdr + 1, end) if t._TECH_LINE_RE.match(lines[k].strip())), None)
    at = tech if tech is not None else end
    while at > hdr + 1 and not lines[at - 1].strip():
        at -= 1
    lines.insert(at, "• " + bullet)
    return "\n".join(lines)


def fix_pandas_placement(text: str, context: dict, notes: list, restored: list) -> str:
    """Pandas / NumPy belong on validation, reconciliation and file jobs, never
    inside a Spark-scale bullet ("Optimized PySpark ETL frameworks using
    Pandas and NumPy…"). The clause is cut from such a bullet; when the JD
    asks for them and no bullet is left, one plain bullet is added to Job 1."""
    lines = text.split("\n")
    cut = 0
    for _, bl in t._job_bullet_lines(text):
        for i in bl:
            ln = lines[i]
            if _PD_RE.search(ln) and _BIG_ENGINE_RE.search(ln) and not _PANDAS_OK_RE.search(ln):
                new = re.sub(r"[ \t]{2,}", " ", _PANDAS_CLAUSE_RE.sub("", ln))
                if new != ln and not _PD_RE.search(new):
                    lines[i] = new
                    cut += 1
    text = "\n".join(lines)
    wanted = [x for x in ("Pandas", "NumPy")
              if any(x.lower() == str(tt).lower() for tt in (context.get("target_tools") or []))]
    if wanted and t._unevidenced(wanted, text):
        bullet = (f"Built {' and '.join(wanted)} validation and reconciliation jobs for incoming source files, "
                  "checking record counts, schema and duplicates before each load.")
        text = insert_job1_bullet(text, bullet)
        restored.append(bullet)
        cut += 1
    if cut:
        notes.append(f"plausibility guard: moved Pandas/NumPy off Spark-scale work ({cut} change(s))")
    return text


_AI_TOOL_RE = re.compile(r"\b(vs\s?code copilot|github copilot|copilot|cursor|claude code|amazon q|codewhisperer)\b", re.I)
_MENTOR_JD_RE = re.compile(r"\bmentor|\bcoach|guidance\s+(?:to|for|as)\b|junior\s+(?:team|engineer)", re.I)
_BRANCH_RE = re.compile(r"branching strateg|change control|pull[- ]request", re.I)


def ensure_practice_bullets(text: str, job_description: str, base_resume: str,
                            notes: list, restored: list) -> str:
    """A must-have PRACTICE the JD names gets one bullet in Job 1 when no
    bullet carries it (live: Janus Henderson required mentoring, VS Code
    Copilot and branching strategies; the draft had none of them in a
    bullet). Plain wording, no figure; the verb follows tenure."""
    blob = t._experience_blob(text)
    _, years = t._base_years_claim(base_resume or "")
    senior = (years or 0) >= 4
    added: list[str] = []
    if _MENTOR_JD_RE.search(job_description) and not re.search(r"\bmentor|\bcoach", blob):
        b = ("Mentored junior engineers through code reviews and design reviews, setting standards other "
             "engineers adopted across the team." if senior else
             "Paired with newer engineers on code reviews and onboarding, sharing pipeline standards across the team.")
        text = insert_job1_bullet(text, b)
        restored.append(b)
        added.append("mentoring")
    tools = list(dict.fromkeys(m.group(1) for m in _AI_TOOL_RE.finditer(job_description)))
    if tools and not _AI_TOOL_RE.search(blob):
        names = ", ".join(tools[:3])
        b = (f"Used {names} in daily development to draft, test and document pipeline code, "
             "reviewing every suggestion before merge.")
        text = insert_job1_bullet(text, b)
        restored.append(b)
        added.append(names)
        text = t._ensure_skills_row(text, tools[:3], notes)
    if _BRANCH_RE.search(job_description) and not _BRANCH_RE.search(blob) and "branching" not in blob:
        b = ("Released production code through Git branching strategies, pull-request reviews and "
             "change control, keeping every deployment traceable.")
        text = insert_job1_bullet(text, b)
        restored.append(b)
        added.append("branching / change control")
    if added:
        notes.append("practice guard: added a bullet for must-have practice(s): " + "; ".join(added))
    return text


_SKILL_JUNK_RE = re.compile(
    r"^(?:performance|reliability|scalability|documentation|technical documentation|design documentation|"
    r"postmortems?|root cause analysis|cloud migration|incident response|stakeholder management|"
    r"communication|troubleshooting|problem[- ]solving|cost efficiency|cost optimi[sz]ation|"
    r"ai/llm risk.*|(?!rag\b)\S+(?:\s+\S+)+\s+pipelines)$", re.I)     # "real-time data pipelines", not "RAG pipelines"
_BI_OK_RE = re.compile(r"power ?bi|tableau|looker|quicksight|grafana|ssrs|ssas|excel|qlik|superset|metabase|"
                       r"semantic|metrics layer|dashboard|report", re.I)


def clean_skill_rows(text: str, notes: list) -> str:
    """SKILLS rows hold tools and methods. Duty phrases and outcomes leave
    ("performance", "technical documentation", "postmortems", "real-time data
    pipelines"), and the Business Intelligence row keeps only BI items: the
    rest moves to a "Tools and Formats" row."""
    lines: list = text.split("\n")
    in_skills, removed, moved = False, [], []
    bi_at = None
    for i, ln in enumerate(lines):
        s_ = ln.strip()
        if t._is_section_hdr(s_):
            in_skills = "skill" in s_.lower()
            continue
        if not (in_skills and s_.startswith(("•", "-", "*")) and ":" in s_):
            continue
        label, _, rest = s_.partition(":")
        items = [x.strip() for x in t._split_list_items(rest) if x.strip()]
        kept = [x for x in items if not _SKILL_JUNK_RE.match(x)]
        removed += [x for x in items if x not in kept]
        if "business intelligence" in label.lower():
            stay = [x for x in kept if _BI_OK_RE.search(x)]
            moved += [x for x in kept if x not in stay]
            kept, bi_at = stay, i
        if kept != items:
            indent = ln[: len(ln) - len(ln.lstrip())]
            lines[i] = f"{indent}{s_[0]} {label.lstrip('•-* ').rstrip()}: {', '.join(kept)}" if kept else None
    if moved and bi_at is not None:
        lines.insert(bi_at + 1, "• Tools and Formats: " + ", ".join(dict.fromkeys(moved)))
    if removed or moved:
        parts = []
        if removed:
            parts.append("removed non-tools: " + ", ".join(removed))
        if moved:
            parts.append("moved out of the BI row: " + ", ".join(moved))
        notes.append("skills guard: " + "; ".join(parts))
    return "\n".join(l for l in lines if l is not None)


def restore_context(context: dict, base_resume: str) -> dict:
    """The restore guard matches product names. A JD label such as "Snowflake
    internals" or "dbt architecture" must still bring back the base's Snowflake
    or dbt bullet, so the product word joins the list for that guard only."""
    tools = [str(x) for x in (context.get("target_tools") or [])]
    low = {x.lower() for x in tools}
    base_low = (base_resume or "").lower()
    extra = []
    for x in tools:
        head = x.split()[0] if " " in x else ""
        if head and head[0].isupper() and head.lower() not in low and head.lower() in base_low \
                and head.lower() not in t._SKILL_TOKEN_STOP:
            extra.append(head)
            low.add(head.lower())
    ctx = dict(context)
    ctx["target_tools"] = extra + tools          # ranked first so the 90% list keeps them
    return ctx


def slim_score(tailored: str, base_resume: str, job_description: str, context: dict, inserted: list) -> dict:
    """The same deterministic score, read with the slim pipeline's rules: a
    bullet is long past 28 words (not 26), no per-job figure cap, no
    "one short bullet" requirement. The constants are swapped for this call
    only and always put back."""
    old = (t._BULLET_MAX, t._figure_cap, t._SHORT_MAX)
    try:
        t._BULLET_MAX, t._figure_cap, t._SHORT_MAX = 28, (lambda n: 99), 99
        return t._code_score(tailored, base_resume, job_description, context, inserted)
    finally:
        t._BULLET_MAX, t._figure_cap, t._SHORT_MAX = old


# ── never lose what the base already had (2026-09-18, after the live logs) ───

_SCALE_PHRASE_RE = re.compile(
    r"\b(?:hundreds|tens|dozens|thousands) of (?:millions|thousands|billions)\b", re.I)
_JD_STOP = {"data", "experience", "team", "teams", "work", "working", "using", "ability", "strong", "skills",
            "years", "including", "across", "business", "solutions", "systems", "technical", "engineering",
            "engineer", "role", "support", "develop", "development", "build", "building", "design", "tools"}


def _stem5(words) -> set:
    """Crude stems so "migrated" meets "migration" and "claims" meets "claim"."""
    return {w[:5] for w in words if w not in _JD_STOP}


def _jd_vocab(job_description: str) -> set:
    return _stem5(t._content_words(job_description))


def keep_base_specifics(text: str, base_resume: str, job_description: str, context: dict,
                        notes: list, restored: list, per_job: int = 1, weakened_only: bool = False) -> str:
    """A base bullet that speaks the JD's own words, carries a real figure or
    a scale phrase may not vanish or come back weaker. Live misses the tool
    guard could not see because the words are not tool names: "member,
    provider, claims, and pharmacy datasets" cut on a healthcare JD, the SQL
    Server to Snowflake migration dropped on a "warehouse modernization" JD,
    the 45% dbt Mesh bullet dropped, "hundreds of millions" deleted.

      vanished  no tailored bullet descends from it, and it has a base figure,
                a JD tool, or three JD words            -> the base bullet returns
      weakened  its descendant lost a scale phrase or three JD words, and adds
                no JD tool the base bullet lacks        -> the base bullet replaces it

    Job 1 under a cloud swap is skipped for bullets naming the old cloud."""
    vocab = _jd_vocab(job_description)
    # only DISTINCTIVE JD words count: a stem that sits in a quarter of the base's own
    # bullets ("pipel", "platf") says nothing about which bullet this JD needs. Live
    # miss: ten irrelevant bullets (SageMaker, Elasticsearch) came back on three shared
    # generic words and the cap guard then trimmed seven at random.
    all_b = [bl for _, body in t._job_bodies(base_resume) for bl in body.splitlines()
             if bl.strip().startswith(t._BULLET_PREFIXES)]
    df: dict = {}
    for bl in all_b:
        for st in _stem5(t._content_words(bl)):
            df[st] = df.get(st, 0) + 1
    vocab = {st for st in vocab if df.get(st, 0) <= max(2, len(all_b) // 8)}
    tools = [str(x) for x in (context.get("target_tools") or []) if t._looks_like_tool(str(x))]
    base_nums = t._num_tokens(base_resume)
    target = str(context.get("target_cloud") or "None")
    swap_on = target in t._CLOUD_TERMS
    first_body = next((b for _, b in t._job_bodies(base_resume)), "")
    base_cloud0 = t._detect_cloud(first_body) if swap_on else None
    old_sigs = tuple(sg for c, sigs in t._CLOUD_SIG.items() if c == base_cloud0 for sg in sigs) \
        if base_cloud0 and base_cloud0 != target else ()

    lines: list = text.split("\n")
    back, swapped = [], []
    for j, (company, body) in enumerate(t._job_bodies(base_resume)):
        hdr = next((i for i, ln in enumerate(lines) if ln is not None and t._is_job_header_line(ln)
                    and t._company_key(ln) == company), None)
        if hdr is None:
            continue
        done = 0
        for bl in body.splitlines():
            b = bl.strip()
            if not b.startswith(t._BULLET_PREFIXES) or t._TECH_LINE_RE.match(b):
                continue
            core = re.sub(r"^[•\-*\s]+", "", b)
            if j == 0 and old_sigs and any(sg in core.lower() for sg in old_sigs):
                continue
            bw = t._content_words(core)
            jdw = _stem5(bw) & vocab
            figs = t._num_tokens(core) & base_nums
            scales = {m.group(0).lower() for m in _SCALE_PHRASE_RE.finditer(core)}
            b_tools = set(t._names_any(core, tools))
            if not (figs or scales or b_tools or len(jdw) >= 3):
                continue
            end = t._job_block_end(lines, hdr)
            idx = [i for i in range(hdr + 1, end) if lines[i] is not None and lines[i].lstrip().startswith("•")
                   and not t._TECH_LINE_RE.match(lines[i].strip())]
            best, best_i = 0.0, None
            for i in idx:
                tw = t._content_words(lines[i])
                if bw and tw:
                    jac = len(bw & tw) / len(bw | tw)
                    if jac > best:
                        best, best_i = jac, i
            if best_i is None or best < 0.22:                      # vanished
                # back only for a real figure, a JD tool, or three distinctive JD words, and
                # only while the job has room: a restore never pushes the writer's bullets out
                if weakened_only or done >= per_job or not (figs or b_tools or len(jdw) >= 3):
                    continue
                if len(idx) >= t._job_cap(j):
                    continue
                tech = next((k for k in range(hdr + 1, end) if lines[k] is not None
                             and t._TECH_LINE_RE.match(lines[k].strip())), None)
                at = tech if tech is not None else end
                lines.insert(at, "• " + core)
                restored.append(core)
                back.append(f"{t._short(core, 50)} (job {j + 1})")
                done += 1
                continue
            d = lines[best_i]
            dw = t._content_words(d)
            lost_words = jdw - _stem5(dw)
            lost_scale = {s_ for s_ in scales if s_ not in d.lower()}
            lost_figs = figs - t._num_tokens(d)
            adds_tool = set(t._names_any(d, tools)) - b_tools
            d_jd = _stem5(dw) & vocab
            poorer = len(d_jd) < len(jdw)
            hard_loss = bool(lost_scale or lost_figs)
            soft_loss = (not weakened_only) and len(lost_words) >= 3 and poorer
            if (hard_loss or soft_loss) and not adds_tool and len(d_jd) <= len(jdw) + 1:
                indent = d[: len(d) - len(d.lstrip())]
                lines[best_i] = f"{indent}• {core}"
                restored.append(core)
                why = ", ".join(sorted(lost_scale | lost_figs)) or ", ".join(sorted(lost_words)[:4])
                swapped.append(f"{t._short(core, 40)} (lost: {why})")
    if back:
        notes.append(f"specifics guard: {len(back)} base bullet(s) had vanished and came back: " + "; ".join(back[:5]))
    if swapped:
        notes.append(f"specifics guard: {len(swapped)} weakened bullet(s) replaced by the base wording: "
                     + "; ".join(swapped[:5]))
    return "\n".join(l for l in lines if l is not None)


def dedupe_same_opening(text: str, notes: list) -> str:
    """Two bullets in one job that open with the same four words ("Translated
    business requirements into…" twice) read as one thought repeated. The later
    one goes unless it carries a figure the earlier one lacks."""
    lines: list = text.split("\n")
    gone = 0
    for _, bl in t._job_bullet_lines(text):
        seen: dict = {}
        for i in bl:
            body = re.sub(r"^(?:independently|successfully)\s+", "", lines[i].lstrip()[1:].strip(), flags=re.I)
            key = " ".join(w.lower().strip(",.;") for w in body.split()[:4])
            if len(key.split()) < 4:
                continue
            if key in seen and not (t._num_tokens(lines[i]) - t._num_tokens(lines[seen[key]])):
                lines[i] = None
                gone += 1
            else:
                seen.setdefault(key, i)
    norm = lambda x: re.sub(r"[^a-z0-9 ]", "", x.lower()).strip()
    for _, bl in t._job_bullet_lines(text):
        live = [i for i in bl if lines[i] is not None]
        for i in live:
            a_ = norm(lines[i].lstrip()[1:])
            if len(a_.split()) < 5:
                continue
            if any(k != i and lines[k] is not None and a_ in norm(lines[k].lstrip()[1:]) and a_ != norm(lines[k].lstrip()[1:])
                   for k in live):
                lines[i] = None          # "Stored fraud-signal data…" also sits inside the longer bullet
                gone += 1
    if gone:
        notes.append(f"duplicate guard: removed {gone} bullet(s) that repeated another bullet in the same job")
    return "\n".join(l for l in lines if l is not None)


# ── core vs tail: which JD tools must be PROVEN in a bullet ─────────────────

_TAIL_TOOLS = {"json", "csv", "parquet", "avro", "orc", "xml", "fixed-width", "yaml", "git", "github", "gitlab",
               "bitbucket", "git cli", "source control", "version control", "jira", "confluence", "excel",
               "agile", "scrum", "sdlc", "linux", "sql", "python"}
_PREFERRED_SENT_RE = re.compile(r"nice[- ]to[- ]have|preferred|a plus|bonus|is a plus|ideally|familiarity|exposure to|"
                                r"desirable|interest in", re.I)


def core_tools(context: dict, job_description: str, limit: int = 12) -> list:
    """The JD tools a hiring manager will look for PROOF of: product-shaped,
    in the top 60% of the ranked list, named in at least one sentence that is
    not a nice-to-have, and not part of the everyday tail (file formats, Git,
    SQL, Python) that no one asks "where did you use it?" about. The tail
    still reaches the SKILLS rows; it just does not need its own bullet."""
    ranked = [str(x) for x in (context.get("target_tools") or [])]
    top = ranked[: max(1, -(-len(ranked) * 3 // 5))]
    sents = re.split(r"(?<=[.!?•\n])\s+|\n", job_description or "")
    out = []
    for x in top:
        if not t._looks_like_tool(x) or x.lower() in _TAIL_TOOLS:
            continue
        pat = re.compile(rf"(?<![a-z0-9]){re.escape(x.lower())}(?![a-z0-9])", re.I)
        hits = [s_ for s_ in sents if pat.search(s_)]
        if hits and all(_PREFERRED_SENT_RE.search(s_) for s_ in hits):
            continue
        out.append(x)
    return out[:limit]
