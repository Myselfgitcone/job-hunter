"""The add-only top-up of the slim pipeline.

A CORE JD tool that no bullet proves gets a NEW bullet written by the main
model. Nothing that already exists is reworded, so this step cannot damage a
sentence the writer got right (the weave-style top-up bent good bullets to fit
a keyword: "Configured CDC loading with Debezium using Pandas and NumPy").
Every returned bullet is verified in code before it is inserted.
"""
from __future__ import annotations

import re

from ai import tailor as t
from ai.tailor_slim_guards import core_tools
from ai.tailor_slim_prompt import ADD_BULLETS_SYSTEM

# tolerant of list marks, bold and code ticks around the "N 2 ::" prefix (a run returned
# "- **N 1** :: tool :: bullet" and every line was silently skipped)
_LINE_RE = re.compile(r"^[\s>*`\-•]*(?:\d+[.)]?\s+)?(?:N\s*)?(?:JOB\s*)?(\d+)[\s*`]*::\s*(.+?)\s*::\s*(.+?)[\s*`]*$",
                      re.I)


async def add_core_bullets(tailored: str, base_resume: str, job_description: str, context: dict,
                           notes: list, inserted: list, **main_kw) -> str:
    """No call when every core tool already has a bullet. Checks per bullet:
    valid job, 12-38 words, no figure, past tense, names the tool, and the job
    the base anchors that tool to."""
    core = core_tools(context, job_description)
    need = t._unevidenced(core, tailored)
    notes.append(f"core tools: {len(core) - len(need)}/{len(core)} already proven in a bullet"
                 + (f"; adding: {', '.join(need)}" if need else ""))
    if not need:
        return tailored
    lines = tailored.split("\n")
    jobs = t._job_bullet_lines(tailored)
    hdr_idx = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    job_co = [t._company_key(lines[h]) for h in hdr_idx]
    anchors = {k.lower(): v for k, v in
               (t._coverage_anchors(base_resume, context, tailored, job_description) or {}).items()}
    shown: list[str] = []
    for j, bl in jobs:
        shown.append(f"\nJOB {j + 1}: {lines[hdr_idx[j]].strip()}")
        shown += [f"  - {lines[i].lstrip()[1:].strip()}" for i in bl]
    tagged = []
    for x in need:
        where = anchors.get(x.lower())
        js = sorted(j + 1 for j, co in enumerate(job_co) if where and co in where)
        tagged.append(f"- {x}" + (f"  [ONLY JOB {', '.join(map(str, js))}]" if js else ""))
    prompt = ("RESUME JOBS (read only):\n" + "\n".join(shown)
              + "\n\nCORE TOOLS WITHOUT A BULLET:\n" + "\n".join(tagged))
    try:
        raw = await t.chat(ADD_BULLETS_SYSTEM, prompt, max_tokens=1500, pass_name="add_bullets", **main_kw)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"add bullets: skipped ({exc})")
        return tailored

    additions: dict = {}
    ok, bad = [], []
    per_job: dict = {}
    for ln in raw.splitlines():
        m = _LINE_RE.match(ln)
        if not m:
            continue
        j = int(m.group(1)) - 1
        skill = m.group(2).strip()
        body = re.sub(r"^[\s•\-*]+", "", m.group(3)).strip()
        body = re.sub(r"\s*[—–]\s*", ", ", body)
        parts = [x.strip() for x in re.split(r"\s*\+\s*", skill) if x.strip()]
        first = re.match(r"[A-Za-z][A-Za-z-]*", body)
        why = ""
        if not 0 <= j < len(jobs):
            why = "bad job"
        elif not 12 <= len(body.split()) <= 38:
            why = f"{len(body.split())} words"
        elif t._bad_figures(body):
            why = "carries a figure"
        elif not first or t._verb_form(first.group(0)) != "past-tense":
            why = "not past tense"
        elif t._unevidenced([x for x in parts if x in need] or parts, "EXPERIENCE:\nX @ Y | Z\n• " + body):
            why = "does not name the tool"
        else:
            for x in parts:
                where = anchors.get(x.lower())
                if where and job_co[j] not in where:
                    why = "wrong job for " + x
        if why:
            bad.append(f"{skill} ({why})")
            continue
        # proof belongs where the reader looks: an older job takes at most two new bullets,
        # the rest go to the most recent job unless the base anchors the tool elsewhere
        if j > 0 and per_job.get(j, 0) >= 2 and not any(anchors.get(x.lower()) for x in parts):
            j = 0
        per_job[j] = per_job.get(j, 0) + 1
        additions.setdefault(j, []).append((skill, body))
        ok.append(skill)
    if additions:
        tailored, _ = t._insert_skill_bullets(tailored, additions, log=inserted, bonus=4)
    if not ok and not bad:
        notes.append("add bullets: reply had no parsable line; it began: " + re.sub(r"\s+", " ", raw[:160]))
    notes.append(f"add bullets: {len(ok)} new bullet(s) for {', '.join(ok) or 'none'}"
                 + (f"; rejected {len(bad)}: " + "; ".join(bad) if bad else ""))
    return tailored
