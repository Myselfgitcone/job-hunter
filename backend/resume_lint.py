"""
resume_lint.py — quality gate for tailored resumes BEFORE rendering.
Checks what the LLM must fix: bullet length, multi-idea bullets, banned words,
meta-leaks, summary length, and JD-word echo (signature words copied too often).
Bullet COUNTS are handled deterministically by _enforce_limits() in tailor.py.
"""
import re
import sys

WORD_LIMIT   = 22
WORD_TARGET  = 18
SUMMARY_MAX  = 6
BANNED_WORDS = ["utilized", "leveraged"]
META_LEAKS   = ["fabricat", "as per the jd", "as required", "[[", "note:",
                "lorem", "placeholder", "tbd"]

# Echo check: a distinctive word lifted from the JD shouldn't appear 3+ times.
ECHO_MAX           = 2       # max times a JD signature word may appear in resume
ECHO_MIN_WORD_LEN  = 6       # only consider longer/distinctive words
# Common resume/data words that are fine to repeat — never flagged as "echo".
ECHO_STOPLIST = {
    "pipelines", "pipeline", "data", "across", "analytics", "reporting",
    "frameworks", "models", "datasets", "systems", "platform", "platforms",
    "engineering", "experience", "metrics", "governance", "quality",
    "building", "scalable", "operational", "business", "technical", "teams",
}


def _words(text):
    return len(re.findall(r"\S+", text))


def lint_resume(text: str, job_description: str = ""):
    """Return a list of issue strings. Empty = clean.
    Pass job_description to enable the JD-word-echo check (optional)."""
    issues = []
    lines = [l.rstrip() for l in text.strip().split("\n")]

    section = None
    summary_count = 0
    long_bullets = []
    multi_idea = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line == line.upper() and line.endswith(":") and not line.startswith("•"):
            section = line.rstrip(":")
            continue

        if " @ " in line and not line.startswith("•") and not line.startswith("Technologies"):
            continue

        if line.startswith("•"):
            body = line[1:].strip()
            low = body.lower()

            for w in BANNED_WORDS:
                if re.search(rf"\b{w}\b", low):
                    issues.append(f'[BANNED WORD] "{w}" found: "{body[:60]}..."')
            for m in META_LEAKS:
                if m in low:
                    issues.append(f'[META LEAK] "{m}" found: "{body[:60]}..."')

            if section and "SUMMARY" in section:
                summary_count += 1
                continue
            if section and ("SKILL" in section or "TECHNICAL" in section):
                continue

            wc = _words(body)
            if wc > WORD_LIMIT:
                long_bullets.append((wc, body))
            if wc > WORD_TARGET and (" — " in body or re.search(r"\band\b", low)):
                verbs = len(re.findall(
                    r"\b(built|designed|developed|implemented|created|led|ran|"
                    r"orchestrated|migrated|optimized|enforced|delivered|"
                    r"containerized|architected|established|reduced|cut)\b", low))
                if verbs >= 2:
                    multi_idea.append((wc, body))
            continue

    if summary_count > SUMMARY_MAX:
        issues.append(f"[SUMMARY] {summary_count} lines (max {SUMMARY_MAX}). Trim.")
    for wc, body in long_bullets:
        issues.append(f"[TOO LONG] {wc} words (max {WORD_LIMIT}): \"{body[:70]}...\"")
    for wc, body in multi_idea:
        issues.append(f"[MULTI-IDEA] {wc} words, 2+ accomplishments — split or cut: \"{body[:70]}...\"")

    # ── JD-word echo: flag distinctive JD words repeated too often in resume ──
    if job_description:
        jd_low = job_description.lower()
        res_low = text.lower()
        jd_words = set(re.findall(r"[a-z][a-z\-]{%d,}" % (ECHO_MIN_WORD_LEN - 1), jd_low))
        checked = set()
        for w in jd_words:
            if w in ECHO_STOPLIST or w in checked:
                continue
            checked.add(w)
            count = len(re.findall(rf"\b{re.escape(w)}\b", res_low))
            if count > ECHO_MAX:
                issues.append(
                    f'[JD ECHO] "{w}" appears {count}x in resume — a distinctive '
                    f'JD word repeated 3+ times reads as copied. Vary it; keep at most {ECHO_MAX}.'
                )

    return issues


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 resume_lint.py resume.md [jd.txt]"); sys.exit(1)
    txt = open(sys.argv[1]).read()
    jd = open(sys.argv[2]).read() if len(sys.argv) > 2 else ""
    found = lint_resume(txt, jd)
    if not found:
        print("✓ CLEAN — no issues.")
    else:
        print(f"✗ {len(found)} issue(s):\n")
        for f in found:
            print("  " + f)