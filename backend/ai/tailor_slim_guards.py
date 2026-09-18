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
