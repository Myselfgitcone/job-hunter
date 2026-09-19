"""SLIM tailoring pipeline: read the JD, write once, top up what is missing,
then let CODE guard the facts. No pass "improves" wording after the writer.

Why it exists (2026-09-18): three side-by-side reviews against single-pass
resumes showed that almost every defect in the full pipeline's output came
from its cheap-model rewrite passes, not from the writer:
  "SLA" -> "performance guarantees"          (phrase-echo rewrite)
  "Migrated Airflow DAGs to Dagster" -> "...to asset-based orchestration"
                                             (competing-tool rewrite)
  "hundreds of millions" -> "millions", stubs (compress / short-bullet rule)
  real figures stripped                       (figure-cap rewrite)
Here those passes do not run. What stays is additive or restoring:

  1. ANALYZE   cheap model, once                     (same as the full pipeline)
  2. WRITE     main model, once, TAILOR_SYSTEM_SLIM  (ai/tailor_slim_prompt.py)
  3. TOP UP    cheap model, only for JD tools / duties still without a bullet
  4. GUARD     code only: restore dropped base bullets and stubs, verb ladder,
               no certification the base lacks, magnitudes and money formats
               exactly as the base, caps, dedupe, headline, years, dashes.
               Two narrow model calls survive, each verified line by line and
               each skipped when nothing is flagged: a bullet over 32 words is
               shortened, and an invented / dropped figure is fixed.
  5. SCORE     the same deterministic _code_score.

ai/tailor.py (the full pipeline and its prompt) is kept intact as the rollback:
set TAILOR_PIPELINE=full to run it. This slim pipeline is the default. `tailor_resume_routed` is the app's entry point.
"""
from __future__ import annotations

import os
import re

from ai import tailor as t
from ai.tailor_slim_guards import (clean_skill_rows, dedupe_same_opening, ensure_practice_bullets,
                                   fix_pandas_placement, keep_base_specifics, restore_context,
                                   slim_score, strip_adjacent)
from ai.tailor_slim_prompt import TAILOR_SYSTEM_SLIM

from ai.tailor_slim_guards import core_tools  # noqa: E402
# imported late: tailor_slim_add imports the guards module, not this one
from ai.tailor_slim_add import add_core_bullets  # noqa: E402

_CERT_RE = re.compile(r"\bcertifi(?:ed|cation|cate)s?\b", re.I)
_SCALE_RE = re.compile(r"\b((?:hundreds|tens|dozens|thousands) of (?:millions|thousands|billions|feeds|tables|pipelines))\b", re.I)
_MONEY_RE = re.compile(r"\$\s?(\d[\d,.]*)\s?([KkMmBb])\b")


# ── code-only guards that exist only in the slim pipeline ───────────────────

def strip_unowned_certs(text: str, base_resume: str, notes: list) -> str:
    """A certification the base does not list appears nowhere. Live miss
    (EXL): the JD required two Databricks certifications and both were written
    into SKILLS as owned. SKILLS items and CERTIFICATIONS lines that name a
    certification absent from the base are removed; a summary or bullet
    sentence that claims one loses that clause's line entirely only when the
    whole line is the claim."""
    base_low = (base_resume or "").lower()
    lines = text.split("\n")
    removed: list[str] = []
    section = ""
    for i, ln in enumerate(lines):
        s = ln.strip()
        if t._is_section_hdr(s):
            section = s.lower()
            continue
        if not s or not _CERT_RE.search(s):
            continue
        if "skill" in section and s.startswith(("•", "-", "*")) and ":" in s:
            label, _, rest = s.partition(":")
            items = [x.strip() for x in t._split_list_items(rest) if x.strip()]
            kept = [x for x in items if not (_CERT_RE.search(x) and x.lower() not in base_low)]
            if len(kept) != len(items):
                removed.extend(x for x in items if x not in kept)
                indent = ln[: len(ln) - len(ln.lstrip())]
                lines[i] = f"{indent}{s[0]} {label.lstrip('•-* ').rstrip()}: {', '.join(kept)}" if kept else None
        elif "certif" in section:
            body = s.lstrip("•-* ").strip()
            if body.lower() not in base_low:
                removed.append(body)
                lines[i] = None
    if removed:
        notes.append("cert guard: removed certification(s) the base does not list: " + ", ".join(removed))
    return t._strip_empty_sections("\n".join(l for l in lines if l is not None))


def restore_magnitudes(text: str, base_resume: str, notes: list) -> str:
    """Scale phrases and money formats come through exactly as the base wrote
    them. Live misses (EXL): "hundreds of millions of daily records" shipped as
    "millions", "$100K" as "100k". For each base bullet carrying such a phrase,
    the tailored bullet that descends from it (same company, best word overlap)
    gets the base form back when it carries only the weakened one."""
    lines = text.split("\n")
    hdr = {}
    for i, ln in enumerate(lines):
        if t._is_job_header_line(ln):
            hdr.setdefault(t._company_key(ln), i)
    fixed: list[str] = []
    for company, body in t._job_bodies(base_resume):
        h = hdr.get(company)
        if h is None:
            continue
        end = t._job_block_end(lines, h)
        t_idx = [i for i in range(h + 1, end)
                 if lines[i].lstrip().startswith("•") and not t._TECH_LINE_RE.match(lines[i].strip())]
        for bl in body.splitlines():
            b = bl.strip()
            if not b.startswith(t._BULLET_PREFIXES):
                continue
            scales = [m.group(1) for m in _SCALE_RE.finditer(b)]
            monies = [m.group(0) for m in _MONEY_RE.finditer(b)]
            if not scales and not monies:
                continue
            bw = t._content_words(b)
            best, best_i = 0.0, None
            for i in t_idx:
                tw = t._content_words(lines[i])
                if bw and tw:
                    jac = len(bw & tw) / len(bw | tw)
                    if jac > best:
                        best, best_i = jac, i
            if best_i is None or best < 0.22:
                continue
            ln = lines[best_i]
            for sc in scales:
                unit = sc.split(" of ", 1)[1]
                if sc.lower() in ln.lower():
                    continue
                m = re.search(rf"\b{re.escape(unit)}\b", ln, re.I)
                if m:
                    ln = ln[:m.start()] + sc + ln[m.end():]
                    fixed.append(f"{unit} -> {sc}")
            for mo in monies:
                mm = _MONEY_RE.search(mo)
                num, suf = mm.group(1), mm.group(2)
                if mo in ln:
                    continue
                m = re.search(rf"(?<![$\d]){re.escape(num)}\s?{suf}\b", ln, re.I)
                if m:
                    ln = ln[:m.start()] + mo + ln[m.end():]
                    fixed.append(f"{m.group(0)} -> {mo}")
            lines[best_i] = ln
    if fixed:
        notes.append(f"magnitude guard: {len(fixed)} weakened quantity restored from the base: " + "; ".join(fixed[:5]))
    return "\n".join(lines)


async def fix_figures_only(tailored: str, base_resume: str, job_description: str,
                           notes: list, **cheap_kw) -> str:
    """The one number pass: an invented figure is removed and a base figure a
    descendant bullet lost comes back. Nothing else is asked of the model, each
    line is verified in code, anything unverified reverts. No call when the
    audit is clean."""
    invented, dropped, removed = t._number_audit(tailored, base_resume, job_description, floor=None)
    if removed:
        notes.append(f"number guard: {len(removed)} base bullet(s) with figures have no descendant: "
                     + " | ".join(removed[:4]))
    jobs: dict[int, str] = {}
    for i, figs in invented:
        jobs[i] = f"Remove the figure(s) {', '.join(sorted(figs))} (not in the base resume). Change nothing else."
    for i, figs in dropped:
        jobs[i] = (jobs.get(i, "") + f" Restore the base resume's figure(s) {', '.join(sorted(figs))} that this "
                   "bullet originally carried. Change nothing else.").strip()
    if not jobs:
        return tailored
    before = tailored.split("\n")
    fixed = await t._fix_lines(tailored, jobs, notes, "figure_fix",
                               allow_new_figures={i for i, _ in dropped}, **cheap_kw)
    after = fixed.split("\n")
    if len(after) != len(before):
        notes.append("figure fix rejected (line count changed)")
        return tailored
    allowed = t._num_tokens(base_resume) | t._num_tokens(job_description)
    ok, bad = 0, 0
    for i in jobs:
        good = True
        if any(i == x for x, _ in invented) and {f for f in t._num_tokens(after[i]) - allowed if not f.endswith("y")}:
            good = False
        for x, figs in dropped:
            if x == i and not (figs & t._num_tokens(after[i])):
                good = False
        if good:
            ok += 1
        else:
            after[i] = before[i]
            bad += 1
    notes.append(f"figure fix: {ok} line(s) repaired" + (f", {bad} reverted" if bad else ""))
    return "\n".join(after)



# ── the pipeline ─────────────────────────────────────────────────────────────

async def tailor_resume_slim(base_resume: str, job_description: str,
                             api_key: str, provider: str, model: str,
                             profile_skills: list[str] | None = None,
                             secondary_model: str = "",
                             user_job_roles: list[str] | None = None,
                             profile_projects: list[dict] | None = None,
                             company: str = "",
                             keys=None) -> tuple[str, dict]:
    """Same signature and return shape as ai.tailor.tailor_resume."""
    notes: list[str] = ["pipeline: slim"]
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

    base_resume = (base_resume or "").strip()
    job_description = (job_description or "").strip()
    if len(base_resume) < 40:
        raise ValueError("Resume text is too short — upload or paste your resume first.")
    if len(job_description) < 40:
        raise ValueError("Job description is too short. Paste the full posting.")

    cheap = secondary_model or model
    main_kw = {"api_key": api_key, "provider": provider, "model": model, "keys": keys}
    cheap_kw = {"api_key": api_key, "provider": provider, "model": cheap, "keys": keys}

    # ── 1. ANALYZE ───────────────────────────────────────────────────────
    context: dict = {}
    for attempt in (1, 2):
        err, raw = "", ""
        try:
            raw = await t.chat(t.ANALYZE_SYSTEM, t.analyze_prompt(base_resume, job_description),
                               max_tokens=6000, pass_name="analyze" if attempt == 1 else "analyze_retry",
                               **cheap_kw)
            context = t._loads_loose(raw)
        except Exception as exc:  # noqa: BLE001
            err, context = str(exc), {}
        if t._analysis_ok(context):
            break
        notes.append(f"analyze: attempt {attempt} " + (f"failed ({err})" if err else "returned no usable JSON"))
    if not t._analysis_ok(context):
        raise ValueError("Could not analyze this job description (the model returned no usable "
                         "analysis twice). Try again in a moment.")
    for k in ("present", "missing", "baseline_missing", "responsibilities"):
        context.setdefault(k, [])
    context.setdefault("target_cloud", "None")
    context.setdefault("industry", "")

    tc = (context.get("target_cloud") or "").strip()
    jd_low = job_description.lower()
    if tc in t._CLOUD_TERMS and not any(term in jd_low for term in t._CLOUD_TERMS[tc]):
        notes.append(f"cloud guard: JD never names {tc} — target_cloud forced to None")
        context["target_cloud"] = "None"

    job_description, cut = t._trim_jd_tail(job_description, context.get("jd_tail_starts"),
                                           context.get("target_tools") or [])
    if cut:
        notes.append(f"jd trimmed: dropped {cut} chars of pay/benefits/legal tail")
    context["responsibilities"] = [str(r).strip() for r in (context.get("responsibilities") or []) if str(r).strip()][:8]
    # a certification is a credential, never a tool to cover
    for k in ("target_tools", "present", "missing", "bridge_only", "equivalent"):
        context[k] = [x for x in (context.get(k) or [])
                      if not t._is_soft_skill(str(x)) and not _CERT_RE.search(str(x))]
    split_log = t._split_compound_labels(context, job_description, base_resume)
    if split_log:
        notes.append("analyze: split compound labels: " + "; ".join(split_log))
    not_literal = [str(x) for x in (context.get("target_tools") or []) if not t._phrase_in_jd(str(x), job_description)]
    if not_literal:
        context["target_tools"] = [x for x in context["target_tools"] if str(x) not in not_literal]
        for k in ("present", "missing", "bridge_only", "equivalent"):
            context[k] = [x for x in (context.get(k) or []) if str(x).split(" <-")[0] not in not_literal]
        notes.append("analyze: dropped labels the JD never says: " + ", ".join(not_literal))

    dom = t._dominant_jd_tool(job_description, context.get("target_tools") or [])
    if dom and dom.lower() in t._tool_facts(context):
        where = t._anchored_tools(base_resume, context).get(dom) or set()
        base_cos = [c for c, _ in t._split_jobs(base_resume)]
        dom_missing = dom.lower() in {str(x).lower() for x in (context.get("missing") or [])}
        dom_old = bool(where) and all(base_cos.index(w) >= 2 for w in where if w in base_cos)
        if dom_missing or dom_old:
            reasons.append(f"Low fit: JD's dominant tool '{dom}' is "
                           + ("absent from the base resume" if dom_missing else "only in an older job")
                           + "; interview depth on it is thin")
    missing = context.get("missing") or []
    print(f"[TAILOR-SLIM] target_cloud={context.get('target_cloud')!r} tools={len(context.get('target_tools') or [])} "
          f"present={len(context.get('present') or [])} missing={len(missing)} "
          f"duties={len(context.get('responsibilities') or [])} company={company or context.get('company', '')!r}")

    # ── 2. WRITE ─────────────────────────────────────────────────────────
    # the writer is told which JD tools a hiring manager will want PROOF of, so the one
    # write covers them and no second pass has to bend its sentences afterwards
    core = core_tools(context, job_description)
    core_block = ("\n\nCORE TOOLS: each of these MUST be proven by an experience bullet (not only listed in "
                  "SKILLS), in the most recent job where it plausibly fits, one or two per bullet, as real "
                  "work on that job's own projects: " + ", ".join(core)) if core else ""
    notes.append(f"core tools given to the writer: {', '.join(core) or 'none'}")
    tailored = (await t.chat(TAILOR_SYSTEM_SLIM,
                             t.tailor_prompt(base_resume, job_description, context, missing, profile_skills) + core_block,
                             max_tokens=8000, pass_name="tailor", **main_kw)).strip()
    tailored = t._contact_only(t._clean_header_title(t._ensure_header(t._normalize_format(tailored), base_resume)), base_resume)
    keep_tool = t._dominant_jd_tool(job_description, context.get("target_tools") or [])
    must_tools = [x for x in t._coverage_plan(context)[0] if t._looks_like_tool(str(x))]
    tailored = t._enforce_caps(tailored, base_resume, notes, keep_tool=keep_tool, keep_tools=must_tools)

    # ── 4a. GUARD, before the top-up (code only) ─────────────────────────
    tailored = t._restore_gutted_bullets(tailored, base_resume, context, notes)
    tailored, junk = t._strip_junk_lines(tailored)
    if junk:
        notes.append(f"removed {junk} junk/placeholder line(s)")
    tailored = t._cap_summary_lines(tailored, notes)
    tailored, tech_added = t._ensure_tech_lines(tailored)
    if tech_added:
        notes.append(f"built {tech_added} missing Technologies Used line(s) from the job's own bullets")
    target = context.get("target_cloud", "None")
    still_missing = t._missing_native_clouds(tailored, base_resume, target)
    if still_missing:
        notes.append("cloud backstop applied: " + ", ".join(f"{c}={cl}" for c, cl in still_missing.items()))
        tailored = t._backstop_native_clouds(tailored, still_missing)
    tailored = t._contact_only(t._clean_header_title(t._strip_empty_sections(tailored)), base_resume).strip()
    tailored = t._guard_title_inflation(tailored, base_resume, notes)
    tailored = t._headline_hybrid(tailored, base_resume, context.get("job_title", ""), notes)
    tailored = t._restore_present_tools(tailored, context.get("present") or [], base_resume, notes)
    restored: list = []
    tailored = t._restore_base_bullets(tailored, base_resume, restore_context(context, base_resume), notes, restored)
    tailored = keep_base_specifics(tailored, base_resume, job_description, context, notes, restored)
    tailored = t._strip_unowned_skills(tailored, base_resume, context, notes)
    tailored = strip_unowned_certs(tailored, base_resume, notes)

    # ── 3. TOP UP (only what still lacks a bullet) ───────────────────────
    # TAILOR_TOPUP: "add" (default) = the writer is given the core list; if a core tool still has no
    # bullet the main model writes NEW bullets only (no call when all are proven); "none" = never;
    # "add" = main model adds new bullets only; "haiku" / "sonnet" = weave top-up,
    # "none" = no model top-up (JD keywords still reach the SKILLS rows).
    # A bullet carrying a figure is locked: the top-up never rewrites it.
    inserted: list = []
    topup = os.getenv("TAILOR_TOPUP", "add").strip().lower()
    notes.append(f"top-up: {topup}")
    if topup == "add":
        # add-only: the main model writes NEW bullets for core tools; no existing sentence is touched
        tailored = await add_core_bullets(tailored, base_resume, job_description, context, notes, inserted, **main_kw)
        _, off_page = t._covered_anywhere([str(x) for x in (context.get("target_tools") or [])
                                           if t._looks_like_tool(str(x))], tailored)
        tailored = t._ensure_skills_row(tailored, off_page + t._coverage_plan(context)[1], notes)
    elif topup != "none":
        tailored = await t._ensure_skill_bullets(
            tailored, job_description, notes,
            jd_missing=(context.get("baseline_missing") or []) + (context.get("responsibilities") or []),
            inserted=inserted,
            present_tools=context.get("present") or [],
            jd_terms=(context.get("target_tools") or []) + (context.get("responsibilities") or []),
            must_tools=t._coverage_plan(context)[0],
            foreign=context.get("bridge_only") or [],
            skills_only=t._coverage_plan(context)[1],
            anchors=t._coverage_anchors(base_resume, context, tailored, job_description),
            lock_figures=True,
            **(main_kw if topup == "sonnet" else cheap_kw))
        tailored = t._ensure_skills_row(tailored, t._coverage_plan(context)[1], notes)
    else:
        # every JD tool is on the page for the ATS, in its SKILLS row, even without a bullet
        _, off_page = t._covered_anywhere([str(x) for x in (context.get("target_tools") or [])
                                           if t._looks_like_tool(str(x))], tailored)
        tailored = t._ensure_skills_row(tailored, off_page + t._coverage_plan(context)[1], notes)
    tailored = keep_base_specifics(tailored, base_resume, job_description, context, notes, restored)

    # ── 4b. GUARD, after the top-up ──────────────────────────────────────
    jd_keep_words = (context.get("target_tools") or []) + (context.get("responsibilities") or [])
    over = [i for _, bl in t._job_bullet_lines(tailored) for i in bl
            if len(tailored.split("\n")[i].split()) - 1 > 28]
    if over:            # the one length pass: only a bullet past 28 words is shortened
        tailored = await t._compress_long_bullets(tailored, notes, jd_keep_words,
                                                  max_words=28, target=24,
                                                  summary_max=10 ** 6, **cheap_kw)
    tailored = t._split_long_bullets(tailored, notes)
    tailored, tidied = t._clean_lists(tailored)
    if tidied:
        notes.append(f"tidied {tidied} over-long / duplicate list line(s)")
    tailored = t._trim_to_budget(tailored, inserted, base_resume, notes,
                                 protect=jd_keep_words, job_description=job_description)
    tailored = t._promote_tool_bullets(tailored, keep_tool, notes)
    tailored = t._demote_bridge_bullets(tailored, notes, foreign=context.get("bridge_only") or [],
                                        base_resume=base_resume)
    tailored = t._dedupe_bullets(tailored, notes)
    tailored = dedupe_same_opening(tailored, notes)
    tailored, dash = t._strip_dash_asides(tailored)
    if dash:
        notes.append(f"dash guard: rewrote {dash} dash construction(s)")
    tailored, yrs = t._clamp_years(tailored, base_resume)
    if yrs:
        notes.append("years guard: clamped inflated experience claim to base resume")
    tailored = await fix_figures_only(tailored, base_resume, job_description, notes, **cheap_kw)
    tailored = restore_magnitudes(tailored, base_resume, notes)
    tailored = t._restore_base_bullets(tailored, base_resume, restore_context(context, base_resume), notes, restored)
    tailored = strip_adjacent(tailored, notes)
    tailored = t._enforce_caps(tailored, base_resume, notes, keep_tool=keep_tool, bonus=1,
                               protect={b for _, _, b in inserted} | set(restored), keep_tools=must_tools)
    # after the cap guard, so these short must-have bullets are never its victims
    # (live: the Copilot bullet was added, then trimmed as the last line of a full job)
    tailored = fix_pandas_placement(tailored, context, notes, restored)
    tailored = ensure_practice_bullets(tailored, job_description, base_resume, notes, restored)
    tailored = t._verb_ladder_guard(tailored, base_resume, context.get("bridge_only") or [], notes)
    tailored, intens = t._strip_intensifiers(tailored)
    if intens:
        notes.append(f"intensifier guard: removed {intens} vague intensifier(s)")
    tailored, junk2 = t._strip_junk_lines(tailored)
    tailored = t._strip_empty_sections(tailored)
    # last word on facts: a shortening pass may not cost a bullet its JD words or scale phrase
    tailored = keep_base_specifics(tailored, base_resume, job_description, context, notes, restored,
                                   weakened_only=True)
    tailored = t._dedupe_skill_rows(tailored, notes)
    tailored = clean_skill_rows(tailored, notes)
    tailored = strip_unowned_certs(tailored, base_resume, notes)
    jd_keep = t._coverage_plan(context)[1] + [str(x) for x in (context.get("target_tools") or [])]
    tailored = t._drop_unevidenced_skills(tailored, notes, keep=jd_keep)

    # ── 5. SCORE ─────────────────────────────────────────────────────────
    scores: dict = {}
    try:
        scores = slim_score(tailored, base_resume, job_description, context, inserted)
        context["present"], context["missing"] = scores.get("present", []), scores.get("missing", [])
        ct = scores.get("coverage_target") or {}
        notes.append(f"coverage target: {ct.get('have')}/{ct.get('need')} ranked tools in bullets, "
                     f"{'met' if ct.get('met') else 'MISSED'}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"score skipped ({exc})")
    overall = scores.get("overall")
    if isinstance(overall, (int, float)):
        notes.append(f"score: overall {overall} (ats {(scores.get('ats') or {}).get('score')}, "
                     f"recruiter {(scores.get('recruiter') or {}).get('score')}, "
                     f"hiring_manager {(scores.get('hiring_manager') or {}).get('score')})")
        if overall < 70:
            reasons.extend(str(f) for f in (scores.get("top_fixes") or [])[:3])
    try:
        from ai.llm import get_run_usage
        usage = get_run_usage()
    except Exception:  # noqa: BLE001
        usage = {"cost": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": []}
    for n in notes:
        print(f"[TAILOR-SLIM GUARDS] {n[:300]}")
    return tailored, {"needs_review": bool(reasons), "reasons": reasons, "notes": notes,
                      "scores": scores, "context": context, "usage": usage}


async def tailor_resume_routed(*args, **kwargs) -> tuple[str, dict]:
    """The app's entry point. The slim pipeline is the default (live since
    2026-09-18); TAILOR_PIPELINE=full runs the previous pipeline in
    ai/tailor.py, which is kept intact as the rollback."""
    if os.getenv("TAILOR_PIPELINE", "").strip().lower() == "full":
        return await t.tailor_resume(*args, **kwargs)
    return await tailor_resume_slim(*args, **kwargs)
