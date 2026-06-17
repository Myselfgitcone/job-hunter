"""
resume_lint.py — quality gate for tailored resumes BEFORE rendering.
Checks only what the LLM must fix (length, words, leaks).
Bullet COUNTS are handled deterministically by _enforce_limits() in tailor.py,
so they are intentionally NOT checked here (avoids wasteful retries).
"""
import re
import sys

WORD_LIMIT   = 22
WORD_TARGET  = 18
SUMMARY_MAX  = 6
BANNED_WORDS = ["utilized", "leveraged"]
META_LEAKS   = ["fabricat", "as per the jd", "as required", "[[", "note:",
                "lorem", "placeholder", "tbd"]


def _words(text):
    return len(re.findall(r"\S+", text))


def lint_resume(text: str):
    """Return a list of human-readable issue strings. Empty list = clean."""
    issues = []
    lines = [l.rstrip() for l in text.strip().split("\n")]

    section = None        # "SUMMARY" | "SKILL" | "EXPERIENCE" | other
    in_experience = False
    summary_count = 0
    long_bullets = []
    multi_idea = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # section header
        if line == line.upper() and line.endswith(":") and not line.startswith("•"):
            section = line.rstrip(":")
            in_experience = "EXPERIENCE" in section or "WORK" in section
            continue

        # job header (inside experience) — just confirms we're in job bullets
        if " @ " in line and not line.startswith("•") and not line.startswith("Technologies"):
            in_experience = True
            continue

        # bullets
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

            # experience bullets: word + multi-idea checks
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

    return issues


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 resume_lint.py resume.md"); sys.exit(1)
    found = lint_resume(open(sys.argv[1]).read())
    if not found:
        print("✓ CLEAN — no issues.")
    else:
        print(f"✗ {len(found)} issue(s):\n")
        for f in found:
            print("  " + f)
