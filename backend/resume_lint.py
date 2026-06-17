"""
resume_lint.py — quality gate for tailored resumes BEFORE rendering.
Catches the things that make a resume look congested or AI-generated.

Usage:
    from resume_lint import lint_resume
    issues = lint_resume(resume_text)
    if issues:
        for i in issues: print(i)
    # decide: block render, or warn, or auto-send back to the model

Run standalone:
    python3 resume_lint.py path/to/resume.md
"""
import re
import sys

WORD_LIMIT      = 22      # hard cap per bullet
WORD_TARGET     = 18      # soft target
SUMMARY_MAX     = 6       # max summary bullets/lines
BANNED_WORDS    = ["utilized", "leveraged"]
META_LEAKS      = ["fabricat", "as per the jd", "as required", "[[", "note:",
                   "lorem", "placeholder", "tbd"]

# rough per-job bullet budgets (most-recent first)
JOB_BULLET_MAX  = [12, 9, 7, 4, 4, 4]


def _words(text):
    return len(re.findall(r"\S+", text))


def lint_resume(text: str):
    """Return a list of human-readable issue strings. Empty list = clean."""
    issues = []
    lines = [l.rstrip() for l in text.strip().split("\n")]

    section = None
    summary_count = 0
    job_index = -1
    cur_job_bullets = 0
    cur_job_name = None
    long_bullets = []
    multi_idea = []

    def close_job():
        nonlocal cur_job_bullets, cur_job_name, job_index
        if cur_job_name is not None:
            cap = JOB_BULLET_MAX[job_index] if job_index < len(JOB_BULLET_MAX) else 4
            if cur_job_bullets > cap:
                issues.append(
                    f"[BULLET COUNT] {cur_job_name}: {cur_job_bullets} bullets "
                    f"(max {cap}). Cut {cur_job_bullets - cap}."
                )

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # section header
        if line == line.upper() and line.endswith(":") and not line.startswith("•"):
            close_job()
            section = line.rstrip(":")
            continue

        # job header
        if " @ " in line and not line.startswith("•") and not line.startswith("Technologies"):
            close_job()
            job_index += 1
            cur_job_name = line.split(" @ ")[1].split(" | ")[0].strip()
            cur_job_bullets = 0
            continue

        # bullets
        if line.startswith("•"):
            body = line[1:].strip()

            # banned words
            low = body.lower()
            for w in BANNED_WORDS:
                if re.search(rf"\b{w}\b", low):
                    issues.append(f'[BANNED WORD] "{w}" found: "{body[:60]}..."')

            # meta leaks
            for m in META_LEAKS:
                if m in low:
                    issues.append(f'[META LEAK] "{m}" found: "{body[:60]}..."')

            if section and ("SUMMARY" in section):
                summary_count += 1
                continue  # summary lines aren't word-capped like bullets

            if section and ("SKILL" in section or "TECHNICAL" in section):
                continue  # skill lines exempt from word cap

            # experience bullets
            cur_job_bullets += 1
            wc = _words(body)
            if wc > WORD_LIMIT:
                long_bullets.append((wc, body))
            # multi-idea heuristic: long AND has " — " or " and " joining clauses
            if wc > WORD_TARGET and (" — " in body or re.search(r"\band\b", low)):
                # only flag if it looks like 2 accomplishments (2+ verbs)
                verbs = len(re.findall(
                    r"\b(built|designed|developed|implemented|created|led|ran|"
                    r"orchestrated|migrated|optimized|enforced|delivered|"
                    r"containerized|architected|established|reduced|cut)\b", low))
                if verbs >= 2:
                    multi_idea.append((wc, body))
            continue

    close_job()

    # summary length
    if summary_count > SUMMARY_MAX:
        issues.append(f"[SUMMARY] {summary_count} lines (max {SUMMARY_MAX}). Trim.")

    # long bullets
    for wc, body in long_bullets:
        issues.append(f"[TOO LONG] {wc} words (max {WORD_LIMIT}): \"{body[:70]}...\"")

    # multi-idea bullets
    for wc, body in multi_idea:
        issues.append(f"[MULTI-IDEA] {wc} words, 2+ accomplishments — split or cut: \"{body[:70]}...\"")

    return issues


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 resume_lint.py resume.md"); sys.exit(1)
    txt = open(sys.argv[1]).read()
    found = lint_resume(txt)
    if not found:
        print("✓ CLEAN — no issues.")
    else:
        print(f"✗ {len(found)} issue(s):\n")
        for f in found:
            print("  " + f)
