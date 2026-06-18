"""
resume_lint.py — quality gate for tailored resumes BEFORE rendering.
Checks what the LLM must fix: bullet length, multi-idea bullets, banned words,
meta-leaks, summary length, Technologies Used presence per job, consecutive
same-verb bullets, and JD-word echo (signature words copied too often).
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

# Common resume/domain words that are fine to repeat — never flagged as "echo".
# Covers ALL user fields: data engineering, Java/backend, cybersecurity, finance, data analyst.
ECHO_STOPLIST = {
    # Universal resume words
    "pipelines", "pipeline", "data", "across", "analytics", "reporting",
    "frameworks", "models", "datasets", "systems", "platform", "platforms",
    "engineering", "experience", "metrics", "governance", "quality",
    "building", "scalable", "operational", "business", "technical", "teams",
    # Java / backend / software engineering
    "services", "service", "microservices", "application", "applications",
    "performance", "testing", "integration", "deployment", "architecture",
    "development", "software", "backend", "frontend", "database",
    "interfaces", "threads", "modules", "packages", "classes", "servers",
    "endpoints", "runtime", "dependencies",
    # Cybersecurity
    "security", "network", "access", "monitoring", "controls", "threats",
    "policies", "compliance", "incident", "vulnerabilities", "identity",
    "detection", "response", "firewall", "encryption", "alerts", "logging",
    "privileged", "exposure",
    # Finance / FP&A / accounting
    "financial", "revenue", "budget", "forecast", "management", "investment",
    "portfolio", "accounting", "transactions", "reconciliation", "variance",
    "quarter", "annual", "analysis", "planning", "statements",
    # Data analyst / BI
    "insights", "dashboards", "dashboard", "visualization", "reports",
    "queries", "trends", "stakeholders", "requirements", "findings",
    "calculated", "measures",
}

# Multi-idea verb list — extended to cover ALL user fields
_MULTI_VERB_PATTERN = re.compile(
    r"\b("
    # Data engineering / DevOps / cloud
    r"built|designed|developed|implemented|created|led|ran|"
    r"orchestrated|migrated|optimized|enforced|delivered|"
    r"containerized|architected|established|reduced|cut|"
    r"deployed|automated|"
    # Java / software engineering
    r"refactored|integrated|shipped|tested|configured|upgraded|"
    r"resolved|debugged|released|published|maintained|extended|"
    # Cybersecurity
    r"detected|remediated|patched|hardened|investigated|"
    r"triaged|responded|assessed|audited|scoped|"
    # Finance / FP&A
    r"modeled|forecasted|reconciled|analyzed|reported|"
    r"reviewed|managed|tracked|calculated|projected|"
    # Data analyst / BI
    r"visualized|queried|transformed|validated|monitored|"
    r"documented|presented|identified"
    r")\b"
)

# Phone like (347) 695-1020 / 347-695-1020 / 3476951020
_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_VERB1_RE = re.compile(r"^([A-Za-z]+)")   # first word of a bullet body


def _words(text):
    return len(re.findall(r"\S+", text))


def lint_resume(text: str, job_description: str = ""):
    """Return a list of issue strings. Empty = clean.
    Pass job_description to enable the JD-word-echo check (optional)."""
    issues = []
    lines  = [l.rstrip() for l in text.strip().split("\n")]

    # ── Header integrity: contact line must exist in the first 3 lines ───────
    header_blob = "\n".join(lines[:3])
    if not _PHONE_RE.search(header_blob):
        issues.append("[MISSING CONTACT] No phone number in the header — "
                      "add the contact line 'phone | email' as line 2. "
                      "A resume with no phone gets ignored.")
    if not _EMAIL_RE.search(header_blob):
        issues.append("[MISSING CONTACT] No email in the header — "
                      "add the contact line 'phone | email' as line 2.")

    section             = None
    summary_count       = 0
    long_bullets        = []
    multi_idea          = []
    current_job_header  = None    # header string of the currently open job
    job_has_tech_line   = False   # did current job get a Technologies Used line?
    jobs_missing_tech   = []      # job header strings missing Technologies Used
    prev_opening_verb   = None    # for consecutive same-verb check

    for raw in lines:
        line = raw.strip()
        if not line:
            prev_opening_verb = None
            continue

        # ── Section header ───────────────────────────────────────────────────
        if line == line.upper() and line.endswith(":") and not line.startswith("•"):
            # Close the last open job before switching sections
            if current_job_header and not job_has_tech_line:
                jobs_missing_tech.append(current_job_header)
            current_job_header = None
            job_has_tech_line  = False
            prev_opening_verb  = None
            section = line.rstrip(":")
            continue

        # ── Job header ───────────────────────────────────────────────────────
        if (" @ " in line and not line.startswith("•")
                and not line.startswith("Technologies")
                and section and "EDUC" not in section):
            # Close previous job — check it had a Technologies Used line
            if current_job_header and not job_has_tech_line:
                jobs_missing_tech.append(current_job_header)
            current_job_header = line
            job_has_tech_line  = False
            prev_opening_verb  = None
            # Location check
            if " | " not in line:
                issues.append(
                    f'[MISSING LOCATION] Job header has no "| City, State": '
                    f'"{line[:55]}". Add the location after the company.'
                )
            continue

        # ── Technologies Used line ────────────────────────────────────────────
        if line.startswith("Technologies Used:"):
            job_has_tech_line = True
            prev_opening_verb = None
            continue

        # ── Bullet lines ─────────────────────────────────────────────────────
        if line.startswith("•"):
            body = line[1:].strip()
            low  = body.lower()

            # Banned words & meta leaks (checked across all sections)
            for w in BANNED_WORDS:
                if re.search(rf"\b{w}\b", low):
                    issues.append(f'[BANNED WORD] "{w}" found: "{body[:60]}..."')
            for m in META_LEAKS:
                if m in low:
                    issues.append(f'[META LEAK] "{m}" found: "{body[:60]}..."')

            if section and "SUMMARY" in section:
                summary_count    += 1
                prev_opening_verb = None
                continue
            if section and ("SKILL" in section or "TECHNICAL" in section):
                prev_opening_verb = None
                continue

            # ── Consecutive same-verb check (experience bullets only) ─────────
            vm = _VERB1_RE.match(body)
            if vm:
                verb = vm.group(1).lower()
                if prev_opening_verb and verb == prev_opening_verb:
                    issues.append(
                        f'[SAME VERB] Two consecutive bullets both start with '
                        f'"{verb.capitalize()}": "{body[:55]}..."'
                    )
                prev_opening_verb = verb
            else:
                prev_opening_verb = None

            # ── Word count & multi-idea checks ───────────────────────────────
            wc = _words(body)
            if wc > WORD_LIMIT:
                long_bullets.append((wc, body))
            if wc > WORD_TARGET and (" — " in body or re.search(r"\band\b", low)):
                verb_count = len(_MULTI_VERB_PATTERN.findall(low))
                if verb_count >= 2:
                    multi_idea.append((wc, body))
            continue

        # Non-bullet content — reset consecutive verb tracking
        prev_opening_verb = None

    # Close the very last job in the file
    if current_job_header and not job_has_tech_line:
        jobs_missing_tech.append(current_job_header)

    # ── Aggregate collected issues ────────────────────────────────────────────
    if summary_count > SUMMARY_MAX:
        issues.append(f"[SUMMARY] {summary_count} lines (max {SUMMARY_MAX}). Trim.")
    for wc, body in long_bullets:
        issues.append(f'[TOO LONG] {wc} words (max {WORD_LIMIT}): "{body[:70]}..."')
    for wc, body in multi_idea:
        issues.append(
            f'[MULTI-IDEA] {wc} words, 2+ accomplishments — split or cut: "{body[:70]}..."'
        )
    for jh in jobs_missing_tech:
        issues.append(
            f'[MISSING TECH LINE] No "Technologies Used:" after job: '
            f'"{jh[:60]}". Add it as the last line of that job\'s bullets.'
        )

    # ── JD-word echo: flag distinctive JD words repeated too often ───────────
    if job_description:
        jd_low   = job_description.lower()
        res_low  = text.lower()
        jd_words = set(re.findall(r"[a-z][a-z\-]{%d,}" % (ECHO_MIN_WORD_LEN - 1), jd_low))
        checked  = set()
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
    txt  = open(sys.argv[1]).read()
    jd   = open(sys.argv[2]).read() if len(sys.argv) > 2 else ""
    found = lint_resume(txt, jd)
    if not found:
        print("✓ CLEAN — no issues.")
    else:
        print(f"✗ {len(found)} issue(s):\n")
        for f in found:
            print("  " + f)