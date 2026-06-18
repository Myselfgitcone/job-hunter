"""
resume_lint.py — quality gate for tailored resumes BEFORE rendering.
Checks what the LLM must fix: bullet length, multi-idea bullets, banned words,
meta-leaks, summary count (exactly 5), total bullet overflow, Technologies Used
presence per job, banned tech labels, consecutive same-verb bullets, metrics
density, and JD-word echo (signature words copied too often).
"""
import re
import sys

WORD_LIMIT   = 22
WORD_TARGET  = 18
SUMMARY_MAX  = 5    # prompt requires EXACTLY 5 summary bullets
BULLET_MAX   = 28   # hard total: 5 summary + 9 + 7 + 5 + 2 experience
BANNED_WORDS = ["utilized", "leveraged"]
META_LEAKS   = ["fabricat", "as per the jd", "as required", "[[", "note:",
                "lorem", "placeholder", "tbd"]

# Degree-line guard: prevents education lines being tracked for tech-line presence.
# IMPORTANT: keep these specific — avoid words that appear in job titles or company names.
# Removed: 'science' (conflicts with 'Data Science @ Cargill'),
#           'arts' (conflicts with any 'Arts' company),
#           'master' (conflicts with 'Master Data Engineer' title)
DEGREE_SIGNALS = {
    "university", "college", "institute", "bachelor", "phd",
    "b.s.", "m.s.", "b.a.", "m.a.", "m.eng.", "degree",
}

# Banned tech-line labels — prompt requires EXACTLY "Technologies Used:"
BANNED_TECH_LABELS = [
    r"^platform:", r"^platforms:", r"^stack:", r"^tech stack:",
    r"^tools:", r"^tools used:", r"^tech:", r"^technologies:",
]

# Echo check: a distinctive word lifted from the JD shouldn't appear 3+ times.
ECHO_MAX           = 2       # max allowed repetitions of a JD signature word
ECHO_MIN_WORD_LEN  = 6       # only flag longer / distinctive words

# Words that are fine to repeat — never flagged as echo.
# Covers data engineering, Java/backend, cybersecurity, finance, data analyst.
ECHO_STOPLIST = {
    # Universal resume words
    "pipelines", "pipeline", "data", "across", "analytics", "reporting",
    "frameworks", "models", "datasets", "systems", "platform", "platforms",
    "engineering", "experience", "metrics", "governance", "quality",
    "building", "scalable", "operational", "business", "technical", "teams",
    # Data engineering — false-positives without these
    "processing", "ingestion", "transformation", "warehouse", "storage",
    "compute", "cluster", "workload", "consumption", "extraction", "loading",
    "orchestration", "partitioning", "indexing", "replication", "streaming",
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

# Multi-idea verb detection — covers all user fields
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

_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_VERB1_RE = re.compile(r"^([A-Za-z]+)")


def _words(text):
    return len(re.findall(r"\S+", text))


def lint_resume(text: str, job_description: str = ""):
    """Return a list of issue strings. Empty list = clean resume."""
    issues = []
    lines  = [l.rstrip() for l in text.strip().split("\n")]

    # ── Header integrity: contact line must exist in first 3 lines ────────────
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
    total_bullets       = 0       # computed after loop: summary_count + len(exp_bullets)
    exp_bullets         = []      # (body, has_metric) for metrics density check

    for raw in lines:
        line = raw.strip()
        if not line:
            prev_opening_verb = None
            continue

        # ── Banned tech-line labels (checked on every non-empty line) ─────────
        for pattern in BANNED_TECH_LABELS:
            if re.match(pattern, line.lower()):
                issues.append(
                    f'[BANNED TECH LABEL] Use "Technologies Used:" not "{line[:40]}"'
                )

        # ── Section header ────────────────────────────────────────────────────
        if line == line.upper() and line.endswith(":") and not line.startswith("•"):
            # Close the last open job before switching sections
            if current_job_header and not job_has_tech_line:
                jobs_missing_tech.append(current_job_header)
            current_job_header = None
            job_has_tech_line  = False
            prev_opening_verb  = None
            section = line.rstrip(":")
            continue

        # ── Job header ────────────────────────────────────────────────────────
        # Guard: degree lines like "M.S. @ Saint Louis University" must not be
        # treated as job headers — they would trigger a missing-tech-line flag.
        is_degree_line = any(d in line.lower() for d in DEGREE_SIGNALS)
        if (" @ " in line and not line.startswith("•")
                and not line.startswith("Technologies")
                and not is_degree_line
                and section and "EDUC" not in section):
            # Close previous job — check it had a Technologies Used line
            if current_job_header and not job_has_tech_line:
                jobs_missing_tech.append(current_job_header)
            current_job_header = line
            job_has_tech_line  = False
            prev_opening_verb  = None
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

        # ── Bullet lines ──────────────────────────────────────────────────────
        if line.startswith("•"):
            body = line[1:].strip()
            low  = body.lower()
            # NOTE: total_bullets is computed after the loop as summary_count + len(exp_bullets)
            # to exclude skills-section bullets from the 28-bullet overflow check.

            # Banned words & meta leaks (all sections)
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

            # Experience bullet — track for metrics density
            has_metric = bool(re.search(r"\d", body))
            exp_bullets.append((body, has_metric))

            # ── Consecutive same-verb check (experience only) ─────────────────
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

            # ── Word count & multi-idea checks ────────────────────────────────
            wc = _words(body)
            if wc > WORD_LIMIT:
                long_bullets.append((wc, body))

            # Em-dash = strong multi-idea signal → 2+ action verbs
            if wc > WORD_TARGET and " — " in body:
                verb_count = len(_MULTI_VERB_PATTERN.findall(low))
                if verb_count >= 2:
                    multi_idea.append((wc, body))
            # "and" alone = weak signal → require 3+ verbs to avoid false positives
            # e.g. "built and deployed X via Jenkins" is one idea with 2 verbs — skip
            elif wc > WORD_TARGET and re.search(r"\band\b", low):
                verb_count = len(_MULTI_VERB_PATTERN.findall(low))
                if verb_count >= 3:
                    multi_idea.append((wc, body))
            continue

        # Non-bullet, non-header content — reset consecutive verb tracking
        prev_opening_verb = None

    # Close the very last job in the file
    if current_job_header and not job_has_tech_line:
        jobs_missing_tech.append(current_job_header)

    # ── Aggregate collected issues ────────────────────────────────────────────

    # Total bullet overflow — fires BEFORE _enforce_limits silently trims.
    # Only counts summary + experience bullets (not skills), matching the 28-cap definition.
    total_bullets = summary_count + len(exp_bullets)
    if total_bullets > BULLET_MAX:
        issues.append(
            f"[BULLET OVERFLOW] {total_bullets} total bullets (max {BULLET_MAX}). "
            "Cut lowest-relevance bullets to reach 28."
        )

    # Summary count — must be EXACTLY 5 (not just ≤ 5)
    if summary_count != SUMMARY_MAX:
        direction = "Add more." if summary_count < SUMMARY_MAX else "Trim."
        issues.append(
            f"[SUMMARY] {summary_count} bullets (must be exactly {SUMMARY_MAX}). "
            f"{direction}"
        )

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

    # ── Metrics density check (experience bullets only) ───────────────────────
    if exp_bullets:
        metric_count = sum(1 for _, has_m in exp_bullets if has_m)
        ratio = metric_count / len(exp_bullets)
        if ratio < 0.55:
            issues.append(
                f"[LOW METRICS] Only {ratio:.0%} of experience bullets have numbers "
                f"(target 60–70%). Add quantified outcomes to more bullets."
            )
        elif ratio > 0.85:
            issues.append(
                f"[HIGH METRICS] {ratio:.0%} of experience bullets have numbers "
                f"(target 60–70%). Looks forced — remove metrics from process/collab bullets."
            )

    # ── JD-word echo check — run on BULLET TEXT ONLY ─────────────────────────
    # Avoids false positives from tools named in "Technologies Used:" lines
    # or from section headers repeating JD vocabulary.
    if job_description:
        bullet_text = "\n".join(body for body, _ in exp_bullets)
        jd_low   = job_description.lower()
        res_low  = bullet_text.lower()
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