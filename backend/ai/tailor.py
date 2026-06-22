import re
from ai.llm import chat
from resume_lint import lint_resume, detect_role_type, BULLET_BUDGETS
from resume_lint import TECH, IB, FINANCE, CYBER, HEALTHCARE, CONSULTING, GENERAL

try:
    from resume_lint import skill_coverage_report, extract_jd_hard_skills
except ImportError:  # Backward compatibility if older resume_lint.py is used.
    skill_coverage_report = None
    extract_jd_hard_skills = None


# ── Hard limits enforced in Python (AI cannot count) ─────────────────────────
# Bullet limits are now role-type-aware. Loaded dynamically from resume_lint.
# BULLET_BUDGETS[role_type] = (most_recent, second, third, fourth_plus, summary, hard_total)
SUMMARY_LIMIT  = 5
SKILLS_LINE_LIMIT = 9

# Closing line prefixes per role type — what _enforce_limits passes through unchanged
_CLOSING_PREFIXES = {
    TECH:       "Technologies Used:",
    CYBER:      "Technologies & Platforms:",
    IB:         "Selected Transactions:",
    FINANCE:    "Key Tools:",
    HEALTHCARE: "Systems Used:",
    CONSULTING: None,
    GENERAL:    None,
}

# Skills section keywords per role type — used to detect skills section in enforce_limits
_SKILLS_SECTION_KEYWORDS = {
    TECH:       {"SKILL", "TECHNICAL"},
    IB:         {"COMPETENC", "SKILL"},
    FINANCE:    {"COMPETENC", "SKILL"},
    CYBER:      {"SKILL", "TECHNICAL", "CERTIF"},
    HEALTHCARE: {"SKILL", "EXPERTISE", "LICENS", "CERTIF"},
    CONSULTING: {"COMPETENC", "SKILL"},
    GENERAL:    {"SKILL", "COMPETENC"},
}


def _extract_education_section(text: str) -> str:
    """Return the content lines under the EDUCATION header (stripped, newline-joined)."""
    lines = text.split("\n")
    edu_lines: list[str] = []
    in_edu = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^EDUCATION:?\s*$', stripped, re.IGNORECASE):
            in_edu = True
            continue
        if in_edu:
            # Any new ALL-CAPS section header ends the block
            if stripped and stripped == stripped.upper() and len(stripped) > 3 and not stripped.startswith("•"):
                break
            if stripped:
                edu_lines.append(stripped)
    return "\n".join(edu_lines)


def _replace_education_section(text: str, correct_edu: str) -> str:
    """Splice correct_edu into text, replacing whatever the AI generated under EDUCATION."""
    lines = text.split("\n")
    out: list[str] = []
    in_edu = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^EDUCATION:?\s*$', stripped, re.IGNORECASE):
            in_edu = True
            out.append(line)
            for edu_line in correct_edu.split("\n"):
                if edu_line.strip():
                    out.append(edu_line)
            continue
        if in_edu:
            if stripped and stripped == stripped.upper() and len(stripped) > 3 and not stripped.startswith("•"):
                in_edu = False
                out.append(line)
            # else: discard AI-generated education content
            continue
        out.append(line)
    return "\n".join(out)


_EDU_WORDS = ("university", "college", "institute", "bachelor", "master", "phd", "degree")

def _is_job_header_line(s: str) -> bool:
    if " @ " not in s or s.startswith("•"):
        return False
    if any(d in s.lower() for d in _EDU_WORDS):
        return False
    return bool(re.search(r' @ .+? \|', s))


def _extract_job_companies(text: str) -> list[str]:
    """Return company names from job headers in document order."""
    companies = []
    for line in text.split("\n"):
        s = line.strip()
        if _is_job_header_line(s):
            m = re.search(r' @ (.+?) \|', s)
            if m:
                companies.append(m.group(1).strip())
    return companies


def _extract_job_block(text: str, company: str) -> str:
    """Extract the full text block (header + bullets) for a given company."""
    co_lo = company.lower()
    lines = text.split("\n")
    block: list[str] = []
    in_block = False
    for line in lines:
        s = line.strip()
        if _is_job_header_line(s):
            m = re.search(r' @ (.+?) \|', s)
            this_co = m.group(1).strip().lower() if m else ""
            if co_lo in this_co or this_co in co_lo:
                in_block = True
                block.append(line)
                continue
            elif in_block:
                break  # next job started
        if in_block:
            # Stop at any section header
            if s and s == s.upper() and s.endswith(":") and len(s) > 3 and not s.startswith("•"):
                break
            block.append(line)
    return "\n".join(block).strip()


def _parse_header_parts(s: str) -> dict:
    """Extract title, company, location, and year-list from a job header line."""
    m_ti = re.match(r'^(.+?) @ ', s)
    m_co = re.search(r' @ (.+?) \|', s)
    # Location: between '| ' and either 2+ spaces/tab or a month/year token
    m_lo = re.search(r'\|\s+(.+?)(?:\s{2,}|\t|\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4}))', s)
    return {
        "title":    m_ti.group(1).strip() if m_ti else "",
        "company":  m_co.group(1).strip() if m_co else "",
        "location": m_lo.group(1).strip() if m_lo else "",
        "years":    re.findall(r'\b(20\d{2}|19\d{2})\b', s),
    }


def _enforce_job_integrity(result: str, base_resume: str) -> tuple[str, list[str], list[str]]:
    """
    1. Remove hallucinated job blocks (company not in base_resume).
    2. Re-insert dropped real job blocks verbatim.
    3. Fix mismatched job headers (title, location, dates) per matched company.
    Returns (fixed_result, removed_companies, reinserted_companies).
    """
    def in_list(company: str, lst: list[str]) -> bool:
        co = company.lower()
        return any(co in b.lower() or b.lower() in co for b in lst)

    def norm(s: str) -> str:
        return re.sub(r'\s+', ' ', s.strip())

    base_cos   = _extract_job_companies(base_resume)
    result_cos = _extract_job_companies(result)

    hallucinated = [c for c in result_cos if not in_list(c, base_cos)]
    dropped      = [c for c in base_cos   if not in_list(c, result_cos)]

    # ── Phase 1: Remove hallucinated job blocks ──────────────────────────────
    if hallucinated:
        hall_lo = [h.lower() for h in hallucinated]
        lines   = result.split("\n")
        out: list[str] = []
        skip = False
        for line in lines:
            s = line.strip()
            if _is_job_header_line(s):
                m  = re.search(r' @ (.+?) \|', s)
                co = m.group(1).strip() if m else ""
                if any(co.lower() in h or h in co.lower() for h in hall_lo):
                    skip = True
                    continue
                else:
                    skip = False
            if skip:
                if s and s == s.upper() and s.endswith(":") and len(s) > 3 and not s.startswith("•"):
                    skip = False
                    out.append(line)
                continue
            out.append(line)
        result = "\n".join(out)

    # ── Phase 2: Re-insert dropped real jobs verbatim ────────────────────────
    reinserted: list[str] = []
    for company in dropped:
        block = _extract_job_block(base_resume, company)
        if not block:
            continue
        lines = result.split("\n")
        insert_at = len(lines)
        in_exp = False
        for i, line in enumerate(lines):
            s = line.strip()
            if "WORK EXPERIENCE" in s.upper():
                in_exp = True
                continue
            if in_exp and s and s == s.upper() and s.endswith(":") and len(s) > 3 and not s.startswith("•"):
                insert_at = i
                break
        lines.insert(insert_at, "")
        lines.insert(insert_at + 1, block)
        result = "\n".join(lines)
        reinserted.append(company)

    # ── Phase 3: Fix mismatched headers (title / location / dates) ───────────
    # Build company_lo -> canonical_header_line map from base_resume
    base_header_map: dict[str, str] = {}
    for line in base_resume.split("\n"):
        s = line.strip()
        if _is_job_header_line(s):
            m = re.search(r' @ (.+?) \|', s)
            if m:
                base_header_map[m.group(1).strip().lower()] = s

    lines = result.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if not _is_job_header_line(s):
            continue
        m = re.search(r' @ (.+?) \|', s)
        if not m:
            continue
        result_co = m.group(1).strip().lower()
        # Find matching base header
        for base_co, base_header in base_header_map.items():
            if base_co in result_co or result_co in base_co:
                if norm(s) != norm(base_header):
                    rp = _parse_header_parts(s)
                    bp = _parse_header_parts(base_header)
                    changes: list[str] = []
                    if rp["title"]    != bp["title"]:    changes.append(f"title '{rp['title']}' -> '{bp['title']}'")
                    if rp["location"] != bp["location"]: changes.append(f"location '{rp['location']}' -> '{bp['location']}'")
                    if rp["years"]    != bp["years"]:    changes.append(f"years {rp['years']} -> {bp['years']}")
                    if changes:
                        print(f"[HEADER MISMATCH] {bp['company']}: {'; '.join(changes)} -- reverted to original")
                        lines[i] = base_header
                break
    result = "\n".join(lines)

    return result, hallucinated, reinserted


def _enforce_limits(text: str, role_type: str = TECH) -> str:
    """
    Post-process AI output to hard-enforce bullet counts per section.
    Role-type-aware: uses the correct per-job limits for the detected role.
    Trims bullets from the bottom of each section (lowest relevance = last).
    """
    budget        = BULLET_BUDGETS[role_type]
    job_limits    = [budget[0], budget[1], budget[2], budget[3]]
    closing_prefix = _CLOSING_PREFIXES.get(role_type)
    skills_kw      = _SKILLS_SECTION_KEYWORDS.get(role_type, {"SKILL"})

    lines = text.split("\n")
    out   = []

    job_index    = -1
    in_section   = None   # "summary" | "job" | "skills" | "education" | "other"
    bullet_count = 0
    bullet_limit = 9999
    skills_count = 0

    def is_section_header(l):
        s = l.strip()
        return (s == s.upper() and len(s) > 3
                and s.endswith(":") and not s.startswith("•"))

    def is_job_header(l):
        s = l.strip()
        if " @ " not in s:
            return False
        if s.startswith("•"):
            return False
        # Guard: degree/education lines
        from resume_lint import DEGREE_SIGNALS
        if any(d in s.lower() for d in DEGREE_SIGNALS):
            return False
        return True

    def is_bullet(l):
        return l.strip().startswith("•")

    def is_closing_line(l):
        if closing_prefix is None:
            return False
        return l.strip().startswith(closing_prefix)

    def is_skills_section(sec_name: str) -> bool:
        if sec_name is None:
            return False
        upper = sec_name.upper()
        return any(kw in upper for kw in skills_kw)

    i = 0
    while i < len(lines):
        line    = lines[i]
        stripped = line.strip()

        # ── Section header ───────────────────────────────────────────────────
        if is_section_header(stripped):
            sec = stripped.rstrip(":").upper()
            if "SUMMARY" in sec or "PROFESSIONAL" in sec:
                in_section   = "summary"
                bullet_limit = SUMMARY_LIMIT
                bullet_count = 0
            elif is_skills_section(sec):
                in_section   = "skills"
                skills_count = 0
            elif "EDUC" in sec:
                in_section = "education"
            elif "EXPERIENCE" in sec or "WORK" in sec or "TRANSACTION" in sec:
                in_section = "other"
            else:
                in_section = "other"
            job_index = -1  # reset on every section boundary
            out.append(line)
            i += 1
            continue

        # ── Job / deal header ────────────────────────────────────────────────
        if is_job_header(stripped):
            in_section   = "job"
            job_index   += 1
            limit_idx    = min(job_index, len(job_limits) - 1)
            bullet_limit = job_limits[limit_idx]
            bullet_count = 0
            out.append(line)
            i += 1
            continue

        # ── Closing line (Technologies Used / Selected Transactions / etc.) ──
        if is_closing_line(stripped):
            out.append(line)
            i += 1
            continue

        # ── Bullet lines ─────────────────────────────────────────────────────
        if is_bullet(stripped):
            if in_section == "summary":
                if bullet_count < bullet_limit:
                    out.append(line)
                    bullet_count += 1
            elif in_section == "job":
                if bullet_count < bullet_limit:
                    out.append(line)
                    bullet_count += 1
            elif in_section == "skills":
                if skills_count < SKILLS_LINE_LIMIT:
                    out.append(line)
                    skills_count += 1
            else:
                out.append(line)
            i += 1
            continue

        # ── All other lines — pass through unchanged ──────────────────────────
        out.append(line)
        i += 1

    return "\n".join(out)


# ── Universal system prompt ───────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert resume writer. The candidate's real title and years of experience come from the resume — never invent or change them. Return ONLY the finished resume — no commentary, no plan block, no meta-text.

═══ STEP 0 — ROLE TYPE DETECTION (DO THIS FIRST, BEFORE ANYTHING ELSE) ═══
Read the JD and classify the role into ONE of these types. Every rule below that references ROLE TYPE uses this classification.

  TECH        — Software engineering, data engineering, data science, ML, DevOps, cloud, platform, SRE, QA
  FINANCE     — FP&A, corporate finance, accounting, financial analyst, treasury, PE/VC associate
  IB          — Investment banking, M&A, capital markets, deal execution, leveraged finance, ECM/DCM
  CYBER       — Cybersecurity, information security, SOC analyst, threat intelligence, GRC, penetration testing
  HEALTHCARE  — Clinical roles, nursing, physician, health informatics, clinical operations, public health
  CONSULTING  — Strategy consulting, management consulting, advisory, transformation
  GENERAL     — Sales, marketing, operations, HR, legal, product management, project management, and any role not cleanly fitting the above

Store this classification mentally. It controls: bullet limits, skills section label, closing line behavior, verb lists, and depth-check vocabulary.

═══ HARD GATES — BULLET BUDGET ═══
SUMMARY: exactly 5 bullets across ALL role types.

EXPERIENCE BULLETS PER ROLE — determined by ROLE TYPE:

  TECH:
    Most recent job:  11 bullets max
    Second job:        7 bullets max
    Third job:         5 bullets max
    Fourth+ job:       2 bullets max
    Hard total (summary + experience): 30

  IB / FINANCE:
    Most recent job:   5 bullets max
    Second job:        4 bullets max
    Third job:         3 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 19
    Rationale: IB and finance resumes are dense and screened in seconds. Every bullet must be a distinct transaction, model, or outcome — not a process description.

  CYBER:
    Most recent job:   7 bullets max
    Second job:        5 bullets max
    Third job:         4 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 23

  HEALTHCARE:
    Most recent job:   6 bullets max
    Second job:        4 bullets max
    Third job:         3 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 20

  CONSULTING:
    Most recent job:   6 bullets max
    Second job:        5 bullets max
    Third job:         3 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 21

  GENERAL:
    Most recent job:   7 bullets max
    Second job:        5 bullets max
    Third job:         4 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 23

BULLET ORDER: Within each job, highest-relevance bullets FIRST, lowest LAST.
If count is trimmed by post-processing, the last bullet is cut — put your weakest bullet last.

═══ STEP 1 — ROLE-SPECIFIC FORMAT RULES ═══

ALL ROLE TYPES — shared:
  Single column. "•" bullets only. Plain text — NO tables, columns, graphics, markdown, or HTML.
  HEADER line 1: Full Name — [JD Target Role Title]
    Extract the exact role title from the JD. Use it here as the candidate's brand.
    Job-level titles inside each role block are FACTUAL and NEVER change.
    One line, em-dash (—) separator. NEVER split across two lines.
  CONTACT line 2: phone | email
  JOB HEADER (one line per job):
    Title @ Company | City, State          Month YYYY – Month YYYY
    Location REQUIRED. Date right-aligned. Never split across two lines.
  EDUCATION: 1 line per degree. Include graduation year if present in the original resume.

SECTION HEADERS — choose based on ROLE TYPE:

  TECH:        PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TECHNICAL SKILLS:   EDUCATION:
  IB:          PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TRANSACTION EXPERIENCE:   EDUCATION:
  FINANCE:     PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   CORE COMPETENCIES:   EDUCATION:
  CYBER:       PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TECHNICAL SKILLS:   CERTIFICATIONS:   EDUCATION:
  HEALTHCARE:  PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   SKILLS & EXPERTISE:   LICENSES & CERTIFICATIONS:   EDUCATION:
  CONSULTING:  PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   CORE COMPETENCIES:   EDUCATION:
  GENERAL:     PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   SKILLS:   EDUCATION:

CLOSING LINE — end each job block with a role-appropriate line:

  TECH only → end each job with EXACTLY:
    Technologies Used: tool1, tool2, tool3, ...
    BANNED labels: ✗ Platform: ✗ Stack: ✗ Tools: ✗ Tools Used: ✗ Tech: ✗ Technologies:
    Copy "Technologies Used:" character for character. No substitutes.

  IB → end each deal-relevant job with:
    Selected Transactions: [deal name / type], [deal name / type], ...
    Only include real transactions from the original resume. Never fabricate deal names.

  FINANCE → end each job with (optional, only if meaningful):
    Key Tools: Excel, PowerPoint, [specific tools from resume]
    Omit entirely if tools are already clear from bullet content.

  CYBER → end each job with:
    Technologies & Platforms: tool1, tool2, ...

  HEALTHCARE → end each job with (only if role is health-informatics or clinical-tech hybrid):
    Systems Used: Epic, Cerner, [other EHR/systems from resume]
    Omit for purely clinical roles.

  CONSULTING / GENERAL → no closing line. Omit entirely.

Note on certifications: CYBER and HEALTHCARE must list every cert and license from the original resume verbatim. Never drop one.

═══ AUTHENTICITY — NEVER FABRICATE ═══
NEVER alter: name, phone, email, job titles, company names, employment dates, locations, degrees, certifications, licenses. These are externally verifiable — changing them is auto-reject.
NEVER change the years-of-experience claim. Copy the exact number from the base resume.
NEVER add a job that does not appear in the ORIGINAL RESUME.
NEVER drop any license, certification, or deal from the original resume.
ALWAYS include every education entry. Never drop a degree.
ALWAYS include graduation year if present in the original resume.
Header title = JD's target role title. Job block titles are factual and NEVER change.

EDUCATION SECTION — COPY VERBATIM:
The EDUCATION section must be copied character-for-character from the candidate's original resume.
Never alter, infer, regenerate, or replace the degree name, institution name, or graduation year under any circumstance.
Do not paraphrase, reorder, abbreviate, or reformat it in any way.
Even minor changes — dropping part of an institution name, shortening a degree title, swapping a year — are fabrications that cause immediate rejection.
If the original resume shows "Master of Science in Information Systems @ Saint Louis University | 2024", the output must show exactly "Master of Science in Information Systems @ Saint Louis University | 2024".

═══ STEP 2 — COMPANY STAGE CALIBRATION ═══
Infer the TARGET COMPANY's stage from signals in the JD:

  STARTUP SIGNALS: Series A/B/C, headcount <200, "wear many hats", "fast-moving", "small team", equity offered, broad single-person ownership, "build from scratch."
    → Individual ownership bullets. Direct personal impact. No org-scale inflation.
    → Summary fifth bullet: small-team autonomy, delivered-despite-ambiguity credibility.

  ENTERPRISE SIGNALS: Fortune 500, "global", "thousands of employees", heavy compliance, multi-team coordination, structured process language.
    → Cross-team coordination, governance, scale are credibility markers — include them.
    → Leadership verbs: "Led", "Drove", "Established", "Governed."

  UNKNOWN: Default to individual impact + some cross-functional context.

═══ STEP 3 — PRIMARY FUNCTION IDENTIFICATION ═══
Identify PRIMARY RESPONSIBILITIES in the JD — not nice-to-haves.

A function is PRIMARY if ANY of these are true:
  - It has its own named section in the JD
  - It uses ownership language: "Own", "You will be responsible for", "Make defensible"
  - It is listed first or described most extensively
  - It is the role's clear differentiator vs. a generic hire

PRIMARY FUNCTION RULE: Each primary function → minimum 2 dedicated bullets in the most recent role.

Examples across role types:
  TECH:       "Own the data platform end-to-end" → 2+ bullets on platform architecture and reliability
  FINANCE:    "Own the P&L model" → 2+ bullets on model design and stakeholder defensibility
  IB:         "Lead execution on M&A mandates" → 2+ bullets on deal process ownership and deliverables
  CYBER:      "Lead incident response" → 2+ bullets on IR process, runbooks, post-mortems
  HEALTHCARE: "Manage a patient panel" → 2+ bullets on panel outcomes and care coordination
  CONSULTING: "Drive client relationship" → 2+ bullets on engagement ownership and outcome delivery
  GENERAL:    "Own revenue target" → 2+ bullets on pipeline ownership and closed outcomes

═══ STEP 4 — OPERATIONAL / EXECUTION DEPTH CHECK ═══
When the JD requires a skill with operational specifics, verify that existing bullets demonstrate EXECUTION DEPTH, not just exposure.

  EXPOSURE BULLET (insufficient): "Used [tool/method] to [generic task]"
  DEPTH BULLET (sufficient): "[Tool/method] with [specific mechanic or decision] — [outcome under pressure or at scale]"

Apply by ROLE TYPE:
  TECH:       streaming (consumer groups, offset mgmt, DLQ), orchestration (retry, backfill, SLA alerting), warehouses (clustering, partition pruning, cost optimization), CI/CD (deployment gates, schema validation, rollback)
  IB:         deal execution (managed data room with X parties, led diligence workstream, coordinated across legal/tax/ops), modeling (3-statement, LBO, merger — not just "built financial models")
  FINANCE:    model ownership (scenario analysis, sensitivity tables, board-ready — not just "created forecasts"), close process (managed X-day close, reconciled $YM, caught material variance)
  CYBER:      detection (tuned N rules, reduced false positive rate by X%), incident response (contained within X hours, authored post-mortem), threat hunting (pivoted across Y sources, identified Z TTPs)
  HEALTHCARE: clinical outcomes (panel of X, outcome metric Y, adherence rate Z), care coordination (managed transitions across N care settings, reduced readmissions by X%)
  CONSULTING: engagement ownership (led workstream of N, delivered to C-suite, drove $XM impact), not just "supported analysis"
  GENERAL:    outcome ownership (owned metric, moved it from X to Y in Z timeframe) vs. activity description

If a bullet only shows exposure, rewrite it to surface the real execution mechanics.

═══ INFLUENCE-SIGNAL SURFACING RULE ═══
When the JD requires leadership, coaching, stakeholder influence, or team-direction signal,
scan the candidate's EXISTING bullets for these 5 patterns. If a pattern is genuinely
present, reframe the bullet to make the already-true influence visible — using the
candidate's own domain vocabulary. NEVER invent management titles, direct reports, formal
authority, or leadership experiences that do not exist in the original resume.

PATTERN 1 — STANDARD-SETTING:
  Work that became a pattern, template, or configuration that other people/teams now
  build on or must conform to.
  Signal words: "standardized", "established", "defined", "created template for",
  "adopted across", "configuration across teams/environments"
  Example (TECH): "Standardized Terraform config across dev, staging, prod"
  → "Established Terraform infrastructure standards adopted across 3 environments —
  eliminating environment drift for all engineers building on the platform."

PATTERN 2 — GATEKEEPING / QUALITY CONTROL:
  Work that controls, reviews, or blocks other people's output before it can proceed.
  The candidate's work sits between other people's work and its destination.
  Signal words: "blocked", "prevented", "validated before", "caught violations",
  "flagged before load", "enforced before deployment", "checks before"
  Example (FINANCE): "Built variance-check process flagging discrepancies before month-end close"
  → "Authored variance controls preventing reporting errors from reaching month-end close —
  protecting downstream financial statements from undetected discrepancies."

PATTERN 3 — DEPENDENCY / SLA RELATIONSHIPS:
  Other teams or people structurally depend on this candidate's output — uptime, data
  freshness, delivery cadence, or service availability.
  Signal words: "SLA", "uptime", "freshness", "supported N teams", "consumed by",
  "downstream", "relied on", "used by N"
  Example (IT / GENERAL): "Maintained uptime SLA for ticketing system used by 40-person team"
  → "Owned uptime SLA for the support team's primary ticketing platform — 40 staff depended
  on this system's availability for all daily operations."

PATTERN 4 — CROSS-STAKEHOLDER COORDINATION:
  Work that required gathering requirements, aligning schemas, or coordinating across
  multiple owners or business domains — even informally, without a formal PM role.
  Signal words: "across N source systems", "across N departments/domains/teams",
  "N clinical domains", "N business units", "multiple stakeholders"
  Example (HEALTHCARE): "Integrated data from 5 clinical departments into one model"
  → "Designed a unified data model spanning 5 clinical departments — translating
  divergent reporting requirements from multiple business owners into one governed structure."

PATTERN 5 — ORG-WIDE ENFORCEMENT:
  Compliance, governance, or policy that the candidate applied or enforced across multiple
  teams, environments, or business units — not just their own work.
  Signal words: "across N environments", "enforced across", "org-wide", "all teams",
  "entire organization", "across business units", "applied to all"
  Example (CYBER): "Enforced access control policy across 6 business units"
  → "Authored and enforced access control standards across 6 business units — ensuring
  org-wide compliance without per-team exceptions."

APPLICATION RULE:
  • Scan every bullet in every role for all 5 patterns regardless of detected ROLE TYPE.
  • When a pattern is found AND the JD asks for leadership/influence signal: surface the
    influence angle within the same existing bullet (≤22 words). Do not add new bullets.
  • When the JD does NOT require leadership/influence signal: skip this rule entirely.
    Apply only when JD explicitly names coaching, stakeholder engagement, team direction,
    standards ownership, client-facing influence, or "directing teams."

CRITICAL GUARDRAIL — DO NOT STRETCH:
  This reframing ONLY applies when the pattern is ALREADY genuinely present in the
  original resume text. If a candidate's bullets show pure isolated task execution —
  no standard-setting, gatekeeping, dependency, coordination, or enforcement language
  anywhere — leave every bullet as IC work. Do NOT reframe "Built X" as "Led team to
  build X." Do NOT imply direct reports, coaching, or formal management authority that
  didn't happen. The goal is to surface what is already true, not to promote the
  candidate into a role they have not held.

═══ JD RESPONSIBILITY VERB MIRRORING ═══
Read every line in the JD's responsibilities / job duties section.
Extract the primary action verb from each responsibility line — these are the EXACT verbs the hiring manager uses to describe the role's value.
At least 3 of these JD-native verbs MUST appear in the resume's experience bullets (not only in the summary, not only in the skills section).

This is fully dynamic — derive it from the actual JD, not from any preset list:
  • JD says "Evaluate and recommend data technologies" → at least one bullet uses "Evaluated and recommended [specific tool] for [reason] — [outcome]"
  • JD says "Define data architecture standards" → at least one bullet uses "Defined" or "Established [standard] adopted across [scope]"
  • JD says "Support strategic vision and roadmap" → at least one bullet frames a decision in strategic/roadmap language
  • JD says "Advise senior stakeholders" → at least one bullet uses advisory framing
  • JD says "Monitor and report on" → at least one bullet uses monitoring + reporting language
  • JD says "Detect, investigate, respond" → at least one bullet uses those exact verbs

If the JD has NO clear responsibility verb (poorly written or just a skills list), skip this rule.
Apply to any role type — the JD's own language is always stronger signal than a generic verb bank.

═══ EXPLICITLY NAMED TOOLS → BULLETS RULE ═══
If the JD contains a line in the form "Experience with X, Y, Z" or "Proficiency in X, Y, Z" or "Tools: X, Y, Z" — each named item must appear in at least one WORK EXPERIENCE BULLET, not only in Technologies Used or Technical Skills.

Why: skills section placement is zero signal. A recruiter reads bullets. ATS weights bullet context above skills rows.

Exception: if a named tool has no plausible connection to ANY role in the candidate's history, skills section is acceptable. But this must be the last resort — not the default.

Apply to any domain: "Experience with NoSQL, Kafka, Middleware" → all 3 in bullets. "Tools: Splunk, CrowdStrike, Nessus" → all 3 in bullets. "Proficiency in Excel, Hyperion, SAP" → all 3 in bullets.

═══ JD KEYWORD PLACEMENT — 3 CASES ═══
For every hard skill the JD names, determine which case applies and act accordingly:

CASE 1 — Skill exists in original resume: in skills list + used in a job bullet + in Technologies Used
  → Strengthen the existing bullet (make the usage more specific/impactful)
  → Keep in Technical Skills section
  → Keep in that job's Technologies Used line
  All 3 locations stay in sync. Do not remove from any of them.

CASE 2 — Skill exists in original resume skills only (no supporting bullet)
  → Write a real bullet in the most relevant job — specific action, real domain context, outcome
  → Add to that job's Technologies Used line
  → Keep in Technical Skills section
  All 3 locations now populated. Do not leave it as skills-only.

CASE 3 — Skill NOT in original resume at all (JD requires it, candidate has no exposure)
  PATH A: Skill fits a real job context (adjacent domain, related tool, plausible usage)
    → Write a real contextual bullet at that job — use the ADJACENT-STRETCH tier rules
    → Add to that job's Technologies Used
    → Add to Technical Skills under the correct category
  PATH B: Skill cannot fit any real job context naturally
    → Write ONE soft-framed bullet as the LAST bullet of the most recent job
      Allowed framing: "Applied [skill] to...", "Designed [skill]-based approach for...",
      "Implemented [skill] patterns for..." — never claim enterprise production ownership
    → Add to Technical Skills only — NOT to Technologies Used (no real production claim)
    → Exception for certifications: never create a work bullet for a cert the candidate
      does not hold. Skills/Certifications section only, or omit entirely.

CONSISTENCY RULE — enforced across all 3 cases:
  If a skill appears in ANY work experience bullet → it MUST also appear in:
    1. That job's Technologies Used line
    2. The Technical Skills section under the relevant category
  The reverse is also true: if a skill is in Technologies Used → it must have at least
  one supporting bullet in that same job. Never list a tool in Technologies Used with
  zero bullets mentioning it.

═══ COVERAGE — 80–90%, NOT 100% ═══
Cover every hard skill the JD names, every core responsibility, the seniority level, and the top 3–5 distinctive JD phrases.
Skip: soft skills, culture words, boilerplate, inflation keywords.
Each skill appears once or twice — never five times.

═══ MARKET COVERAGE / DEFENSIBLE STRETCH RULE ═══
Two separate targets — do not conflate them:
  VISIBILITY TARGET (the word appears somewhere on the resume, in any honest form): aim for 100% of JD hard skills when a defensible placement exists for each one.
  PRODUCTION-CLAIM TARGET (the word appears as something the candidate actually owned/operated/shipped in real employer work): caps at 85–95%. Never push this toward 100% by inventing production history.

A skill can satisfy VISIBILITY without ever touching PRODUCTION-CLAIM — that is the entire point of the SELF-IMPLEMENTABLE and HIGH-RISK tiers below. Visibility through skills/project wording is not a fallback or a consolation prize; it is a fully acceptable, fully honest way to cover a skill the candidate hasn't used in production.

For EVERY JD-required hard skill the base resume doesn't already support, classify it and apply exactly one rule:

  1. WORK-SUPPORTED — candidate used it in real work.
     → Add to an experience bullet AND the skills section. Counts toward both visibility and production-claim.

  2. ADJACENT-STRETCH — candidate used the same underlying pattern with a related tool, method, or domain.
     → Add ONE defensible stretch bullet in the most relevant job. Counts toward both visibility and production-claim — this is the only stretch tier allowed to touch production-claim coverage.

  3. SELF-IMPLEMENTABLE — candidate has not used it in employer production, but could implement it independently.
     → Add to the skills section. If format permits, add an optional project/prototype-style bullet.
     → Counts toward VISIBILITY ONLY. Do NOT attach it to an employer as production ownership. Do NOT count it toward the 85–95% production-claim target.

  4. HIGH-RISK / NO BASIS — no real exposure, true coverage gap.
     → Include ONLY as skills/project exposure, and only if the JD treats it as genuinely required (not just mentioned once).
     → Counts toward VISIBILITY ONLY. Never claim employer production ownership, enterprise scale, team leadership, or regulated/client usage.

Allowed safe wording for tiers 3 and 4 (visibility-only placements):
  "Built prototype...", "Configured local implementation...", "Developed proof-of-concept...",
  "Designed implementation pattern...", "Hands-on project with...", "Working knowledge of..."

Unsafe wording unless the skill is genuinely WORK-SUPPORTED or ADJACENT-STRETCH:
  "Owned production...", "Led enterprise rollout...", "Architected company-wide...",
  "Managed real-time platform...", "Processed X million events daily..."

Hard limits:
  • Maximum 2 stretch bullets (tier 2, ADJACENT-STRETCH) per resume.
  • Maximum 1 stretch bullet per job.
  • Tiers 3 and 4 are NOT bullet-capped in the same way — they live in skills/projects, not as new production claims, so they don't compete for the limited experience-bullet budget.
  • Never fabricate titles, companies, dates, degrees, certifications, licenses, transactions, clients, regulated experience, or production ownership — at any tier.

Targets, stated explicitly:
  • JD hard-skill VISIBILITY: 11/11 (100%) when each missing skill has a defensible placement at tier 1–4.
  • PRODUCTION-CLAIM coverage (tiers 1–2 only): 85–95% — this is the ceiling, not a floor to hit by force.
  • The gap between visibility and production-claim is filled by tiers 3–4 (skills/project/prototype wording) — that gap is expected and correct, not a shortfall.
  • Do not force a skill into tier 1 or 2 just to hit a number. If a skill only honestly qualifies for tier 3 or 4, leave it there — full visibility through honest skills/project wording beats inflated production-claim coverage every time.

═══ DOMAIN BRIDGE RULE ═══
When the target company's domain differs from the candidate's past employers:

STEP 1 — Identify the gap: what does the JD care about that doesn't appear in the candidate's history?

STEP 2 — Find the closest analog in the candidate's real work. The underlying skill is often identical; only the business label differs. Examples:
  Fraud signals → data quality anomalies, outlier detection, real-time event propagation
  M&A diligence → financial audit work, variance analysis, multi-party data coordination
  Threat intelligence → log analysis, anomaly detection, access pattern monitoring
  Clinical outcomes → operational KPIs, SLA metrics, quality scores
  Risk models → threshold models, predictive aggregates, scoring systems
  Build your own mappings from what's actually in the JD and the resume.

STEP 3 — Write the real bullet in the employer's vocabulary. Let the pattern speak for itself. Do NOT relabel the employer's domain.

STEP 4 — The summary may bridge domains explicitly — ONE bullet only. Factual, technical, not aspirational. Never repeat in experience bullets.

STEP 5 — Never inject the JD's industry vocabulary into a bullet about a different employer.

═══ SKILLS / COMPETENCIES SECTION ═══
Section label is determined by ROLE TYPE (see Step 1 format rules above).

TECH: All tools from candidate's declared skills. New JD tools only if supported by a bullet. Organize by JD-relevant categories (6–9 lines, ≤7 tools per line).
IB: Financial modeling types (LBO, DCF, merger, accretion/dilution), markets covered, product knowledge (M&A, ECM, DCM), key tools (Excel, Bloomberg, CapIQ, Pitchbook). No padding.
FINANCE: Financial tools (Excel, Hyperion, Anaplan, SAP, Oracle), modeling skills (3-statement, DCF, scenario analysis), reporting standards (GAAP, IFRS, SOX if applicable). 4–6 lines max.
CYBER: Tools by category — SIEM, EDR, Vuln Mgmt, Cloud Security, Identity, scripting. Certifications go in CERTIFICATIONS section.
HEALTHCARE: Clinical skills, EHR/systems if applicable, regulatory frameworks. No generic soft skills.
CONSULTING: Frameworks and methodologies, analytical tools, industry expertise areas. 4–6 lines max.
GENERAL: 4–6 lines. Only include skills that appear in or are directly supported by the work experience.

NEVER mirror the JD's exact qualification wording verbatim as a skills line.

═══ SCOPE CREDIBILITY ═══
Every recruiter knows what one person can realistically own at one company.
  TECH: No more than 2–3 major paradigms per role. 11 bullets should tell one coherent platform story.
  IB: No more than 3–4 deals per role. Quality over quantity.
  FINANCE: No single analyst "owned" the P&L AND redesigned the close AND led the ERP migration simultaneously.
  CYBER: A SOC analyst doesn't run red team, blue team, GRC, and cloud security all at once.
  HEALTHCARE: Scope is defined by specialty, setting, and licensure.
  CONSULTING: Distinguish "led" from "supported." Junior consultants run analyses, managers run workstreams.
70% credible coverage beats 100% unbelievable coverage every time.

═══ BULLET SCORING ═══
Score every bullet 1–5 by JD relevance:
  5 — skill/tool/credential explicitly named in JD
  4 — responsibility explicitly listed in JD
  3 — quantified impact (%, $, volume, time, headcount)
  2 — relevant experience but not in JD
  1 — generic process description or soft skill → CUT FIRST
Keep top bullets within budget. Cut lowest-scored first.

═══ GAP FILLING — CONDITIONAL, PRACTITIONER-LEVEL ═══
For each hard skill the JD names that is missing from the resume:
  "Can I satisfy ALL 5 anchors AND fit within this role's bullet budget?"
  → YES: write the bullet
  → NO: add to skills/competencies section only, or drop entirely

THE 5 ANCHORS:
  1. SPECIFIC ACTION — exact technique, process, or decision (not "did X" — say what you did WITH X and how)
  2. NAMED SKILL / TOOL / METHOD — the JD's exact term
  3. REAL DOMAIN CONTEXT — the employer's actual industry vocabulary, never the JD's if different
  4. CONCRETE OUTCOME — number, deal size, time saved, rate improved (bullet ≤22 words total)
  5. CONTINUITY CHECK — the skill/tool must appear in the declared skills list OR original resume text. If neither → skills section only.

QUALITY / CRAFT DEPTH ANCHOR:
  If the JD explicitly names quality attributes (code quality, model rigor, documentation standards, process maturity), at least one bullet MUST demonstrate those attributes explicitly.
  TECH: "modular, tested, idempotent, version-controlled" → show it in a bullet
  IB: "board-ready materials", "tight model assumptions" → show it in a bullet
  FINANCE: "audit-ready", "variance explained to CFO" → show it in a bullet
  CYBER: "zero false negatives on P1s", "post-mortem authored and actioned" → show it in a bullet
  HEALTHCARE: "chart completion rate X%", "audit-ready documentation" → show it in a bullet

TONE RULES:
  • Past tense. Confident. Zero hedging.
  • NEVER: "gained experience in", "assisted with", "helped with", "exposure to", "familiar with", "leveraged", "utilized"
  • One crisp idea per bullet — under 22 words
  • Verb variety — no two consecutive bullets open with the same verb

ROLE-SPECIFIC VERB BANKS:
  TECH senior:      Designed, Architected, Built, Implemented, Automated, Migrated, Optimized, Deployed
  IB:               Executed, Structured, Modeled, Advised, Diligenced, Coordinated, Prepared, Delivered
  FINANCE senior:   Owned, Built, Managed, Forecasted, Reconciled, Streamlined, Presented, Improved
  CYBER senior:     Detected, Investigated, Remediated, Hardened, Triaged, Authored, Deployed, Reduced
  HEALTHCARE:       Managed, Assessed, Coordinated, Educated, Implemented, Reduced, Maintained, Delivered
  CONSULTING:       Led, Developed, Analyzed, Recommended, Implemented, Facilitated, Presented, Drove
  GENERAL senior:   Led, Grew, Managed, Delivered, Launched, Negotiated, Reduced, Increased

PLACEMENT RULES:
  • Gap bullet goes at the role whose real domain best fits the JD skill
  • If the skill's only existing bullet is at an old role, write a new gap-fill at the most recent plausible role
  • Max 2–3 gap bullets per role
  • Displace the lowest-scoring existing bullet to make room
  • If a skill has no plausible connection to any role → skills section only

VOCABULARY MIRRORING TRAP:
  NEVER paste the JD's domain vocabulary into a bullet about a different-domain employer.
  Test: would a recruiter from the EMPLOYER's industry find this bullet's vocabulary natural?

COMPLIANCE / CREDENTIAL ESCAPE HATCH:
  If the JD requires a credential, license, or regulatory experience that is legally impossible in the candidate's real history → DROP IT ENTIRELY. Never write "[framework]-adjacent."
  SOX cannot apply to a private company. FedRAMP cannot apply to a non-federal contractor.

TECHNOLOGY TIMELINE CHECK (TECH ROLES ONLY):
  Before injecting a tool into a past role, verify it was enterprise-ready BEFORE that job's end date.
  Enterprise adoption lags ~18 months behind public release.
  • Kafka: 2015 | Spark: 2015 | Databricks: 2016 | Delta Lake: 2020 | Snowflake: 2016
  • dbt Core: 2017 | dbt Cloud GA: 2020 | Airflow: 2017 | Dagster: 2019 | Prefect GA: 2020
  • Kubernetes: 2017 | Terraform: 2016 | Docker enterprise: 2015
  • Iceberg: 2020 | Trino/Presto: 2017 | Flink enterprise: 2018
  • FastAPI: 2020 | MLflow: 2019 | LangChain: 2023 | Vector DBs: 2022
  Tool's adoption date AFTER job's end date → skills section only, never a historical bullet.

CENTRAL-SKILL RULE: If a skill appears 3+ times in the JD → include it at every role where plausible. Timeline check still applies.

THE UNIVERSAL FORMULA:
  [Strong verb] + [specific method/tool/technique] + [real domain anchor from employer's industry] + [concrete outcome]

DERIVE DOMAIN FROM RESUME — not from the JD:
  Read the candidate's actual employers. Use that industry's vocabulary in every bullet. Never substitute.
  • Healthcare / health-tech: patient records, claims, EHR, member eligibility, clinical workflows, readmissions
  • Agribusiness / commodity: grain prices, crop yields, supplier contracts, commodity trades, procurement
  • Financial services / banking: transactions, loans, risk scores, portfolios, ledgers, settlements, AUM
  • Insurance: policies, premiums, claims adjudication, underwriting, loss ratios, reserves
  • Investment banking: deal flow, mandates, pitch materials, data rooms, management presentations, CIM
  • Private equity / VC: portfolio companies, diligence, cap table, IRR, MOIC, hold period
  • Supply chain / logistics: inventory, shipments, procurement, vendor SLAs, warehouses, routes
  • Manufacturing / industrial: production runs, defect rates, equipment uptime, quality gates, work orders
  • SaaS / tech product: tenants, user events, feature flags, API calls, error rates, churn, MRR
  • Cybersecurity / defense: endpoints, threat feeds, alerts, access policies, incidents, vulnerabilities, TTPs
  • Retail / e-commerce: orders, SKUs, conversion rates, cart events, fulfillment, returns, GMV
  • Media / adtech: impressions, CPM, audience segments, attribution, campaigns, ROAS
  • Consulting: engagements, workstreams, clients, recommendations, implementation, impact delivered
  • Government / public sector: constituents, programs, grants, compliance, audits, policy
  • Any other — infer from the resume. Never invent. Never relabel.

═══ METRICS — NATURAL DENSITY ═══
Add numbers only where work naturally produces them.
  TECH / CYBER / FINANCE / IB: 60–70% of bullets carry a metric
  HEALTHCARE: 40–60% — clinical outcomes have metrics; care process bullets often don't
  CONSULTING: 50–65% — engagement impact where quantifiable; methodology bullets often don't
  GENERAL: 50–65%
Never force metrics onto process, documentation, or collaboration bullets.
Never 100% (fake). Never 0% (weak). Keep magnitudes plausible.

═══ SENIORITY — CALIBRATE VERBS AND SCOPE ═══
Detect seniority from JD signals: title words, years required, responsibility scope, ownership language.

JD seniority → verb register:
  Director / VP / Partner / C-suite:          Established, Defined, Governed, Owned, Transformed, Scaled
  Architect / Principal / Staff / Tech Lead:  Designed, Architected, Evaluated, Defined standards, Governed, Established, Recommended, Led adoption
  Senior / Lead / Manager:                    Designed, Led, Drove, Built, Architected, Managed
  Mid-level / Associate:                      Developed, Implemented, Created, Optimized, Delivered
  Junior / Analyst / Coordinator:             Supported, Contributed, Assisted, Prepared, Maintained

ARCHITECT / PRINCIPAL / STAFF tier — additional rules:
  These roles own technical decisions, not just execution. Bullets must include at minimum:
  • 1 bullet showing technology evaluation or selection ("Evaluated X vs Y, selected X because Z")
  • 1 bullet showing standards definition or adoption ("Defined [standard] adopted across [scope]")
  • 1 bullet showing cross-team or org-level impact (not just own ticket/project scope)
  These 3 are derived from the candidate's real work using the JD-RESPONSIBILITY-VERB-MIRRORING and INFLUENCE-SIGNAL-SURFACING rules — never fabricated.

Career progression within the resume:
  Oldest role → most junior language, narrowest scope, foundational tools
  Most recent role → most senior language, broadest scope, most sophisticated methods
  Never flatten all roles to the same tone.

═══ SUMMARY — EXACTLY 5 BULLETS ═══
First bullet: target title + seniority + years of experience + 1–2 JD phrases.
Bullets 2–4: core skill clusters matching the JD's primary functions. No copying from experience bullets.
Fifth bullet: company-stage signal.
  Startup → small-team ownership, shipped in ambiguity, end-to-end accountability
  Enterprise → governance maturity, cross-functional impact, organizational scale
Always exactly 5 bullets. Never a paragraph. Never 4, never 6.

DOMAIN BRIDGE (optional): If candidate's background ≠ target company's domain, one summary bullet may bridge explicitly. Factual and technical only. Never repeat in experience bullets.

═══ HUMAN VOICE — ANTI-AI TELLS ═══
  • NEVER "utilized" or "leveraged"
  • No two consecutive bullets open with the same verb
  • Vary structure: metric-first, action-first, tool-first, outcome-first
  • No empty intensifiers without a real number
  • Every bullet ≤ 22 words. Target 14–18. One idea only.
  • No distinctive JD word repeated 3+ times across the full resume

═══ CRITICAL REMINDERS ═══
✗ NEVER fabricate titles, companies, dates, locations, degrees, deals, or credentials
✗ NEVER write a gap bullet if all 5 anchors can't be satisfied
✗ NEVER mirror the JD's exact feature list as a skills line
✗ NEVER inject the JD's domain vocabulary into a different-domain employer's bullet
✗ NEVER drop a license, certification, or deal from the original resume
✗ NEVER exceed the bullet budget for this role type
✗ NEVER write an exposure bullet when the JD demands execution depth
✗ NEVER omit graduation year if present in the original resume
✗ NEVER apply a compliance framework outside its legally plausible domain
✓ ALWAYS use the correct section labels for the detected role type
✓ ALWAYS use the correct closing line format per role type (or omit if not applicable)
✓ ALWAYS include "| City, State" in every job header
✓ ALWAYS give PRIMARY FUNCTIONS dedicated 2+ bullet coverage
✓ ALWAYS calibrate summary fifth bullet to company stage
✓ ALWAYS ask: "Would this bullet survive a live interview challenge?" before keeping a gap fill
✓ ALWAYS preserve every license, certification, and deal from the original resume

═══ FINAL CHECK BEFORE OUTPUT ═══
1. Confirm role type detected: [TECH / IB / FINANCE / CYBER / HEALTHCARE / CONSULTING / GENERAL]
2. Confirm correct section labels used for that role type
3. Count all bullets — must be within the budget for this role type
4. Confirm word count ≤ 22 on every bullet
5. Confirm: no fabricated content, no domain vocabulary injection, no "utilized/leveraged", no repeated opening verbs, no missed licenses/certs/deals, execution depth demonstrated, PRIMARY FUNCTIONS have 2+ bullets, summary fifth bullet matches company stage
6. Output the finished resume. Nothing else."""


# ── Semantic reviewer ─────────────────────────────────────────────────────────
# Runs ONCE after _enforce_limits. Fixes semantic issues lint can't catch.
# Scope is intentionally narrow — only 3 checks, nothing else.
REVIEWER_PROMPT = """You are a resume quality reviewer — NOT a resume writer.
Fix exactly 3 semantic issues in the resume given to you. Change NOTHING outside
these 3 checks. Do NOT: add bullets, remove bullets, change bullet content,
change company names, dates, locations, titles, or bullet count.
Every bullet you write or rewrite must be ≤ 22 words. Return plain text only.

CHECK 1 — SKILLS ANTI-STUFFING:
If the skills/competencies section mirrors the JD's exact feature list verbatim
(e.g. copied qualification wording pasted as category names or line content),
regroup them organically by how the candidate actually works. Use natural category
names appropriate to the role type (e.g. "Distributed Processing", "Cloud
Warehousing" for tech; "Financial Modeling", "Planning Tools" for finance).
Max 6–7 items per line. Do NOT change any bullet in the experience section.
This includes soft-skill or leadership lines copied verbatim from JD requirements
(e.g. "Excellent leadership, communication, and interpersonal skills" appearing as
a skills line) — rewrite these as a concise factual competency line or remove if
they add no technical signal. A skills section lists capabilities, not JD quals.

CHECK 2 — SUMMARY TECH/SPEC DUMP:
If any summary bullet is a spec list (5+ tools or credentials with no candidate
context, no impact statement, no who-you-are signal), rewrite it as a single
crisp who-you-are statement. ≤ 22 words. One idea only.

CHECK 3 — UNSUPPORTED SKILLS ONLY:
If a tool or skill appears in the skills/competencies section but has zero
supporting bullets anywhere in the WORK EXPERIENCE section AND it does NOT appear
in the CANDIDATE'S DECLARED SKILLS list provided in this message, remove it from
that skills line entirely UNLESS it is explicitly listed as a hard requirement in
the JD. JD-required missing skills may remain in the skills section as market
coverage, but do NOT add employer production ownership or fake experience bullets.
Tools that ARE in the Declared Skills list are the candidate's own claims — keep
them regardless of bullet support.
Do NOT add any label — just delete unsupported, non-JD-required items.

CHECK 4 — SUMMARY UNSUPPORTED EXPERIENCE CLAIMS:
Read the PROFESSIONAL SUMMARY. For each summary bullet, check whether it claims
an experience TYPE (not a skill) that is completely absent from the WORK EXPERIENCE bullets below.

Specifically catch and correct:
  "client-facing advisory / consulting experience" — only valid if the work bullets
    show actual external client work or consultancy employment. If no such bullets exist,
    replace that claim with what the bullets actually show (e.g. "cross-functional
    stakeholder collaboration within enterprise data teams").
  "managed / led a team of N" / "direct reports" — only valid if the work bullets
    mention headcount, people management, or direct-report responsibility. Remove if absent.
  "advisory" or "trusted advisor" role framing — only valid if experience bullets
    show consulting or external advisory work with named clients.

Do NOT remove the entire summary bullet — only remove or rewrite the unsupported
portion within it. If the rest of the bullet is valid, keep it.
If no unsupported experience claims exist in the summary, leave all summary bullets unchanged.

CONSTRAINT — NOTHING ELSE:
Reproduce every other line exactly as given. No commentary. No plan blocks.
Return the complete corrected resume as plain text only."""


# ── Tier-compliance audit prompt ──────────────────────────────────────────────
# Second AI pass, narrow and specific: verify that skills added to close JD
# coverage gaps were placed at the tier the prompt actually allows for them.
# This is a TRUTH check, not a pattern-match — it reads the bullet and judges
# whether it reads as real employer production work vs. honest stretch/skills
# wording. Runs once, no retry, report-only — never silently edits the resume.
TIER_AUDIT_PROMPT = """You are a skeptical technical recruiter doing a final truth-audit on a tailored resume.

You will be given:
1. The CANDIDATE'S ORIGINAL RESUME (ground truth — what they actually did)
2. A list of SKILLS THAT WERE MISSING from the original resume but appear in the FINAL RESUME
3. The FINAL TAILORED RESUME

Your only job: for EACH skill in the missing-skills list, find where it appears in the final
resume and classify how it was placed. Do NOT rewrite, fix, or edit anything. Report only.

For each skill, decide:

  TIER 1/2 — WORK-SUPPORTED or ADJACENT-STRETCH (acceptable as a production claim):
    The skill appears in a bullet that reads as something the candidate actually did, at a real
    employer, doing real work. This is only legitimate if the original resume shows clear evidence
    the candidate did related real work this skill could plausibly extend from.

  TIER 3/4 — SELF-IMPLEMENTABLE or HIGH-RISK (visibility-only, should NOT read as production work):
    The skill appears only in the skills/competencies section, or in a bullet using safe non-production
    wording ("Built prototype...", "Working knowledge of...", "Hands-on project with...").

  VIOLATION — the skill was placed as if it were a real production claim (specific company context,
    metric, ownership verb like "Owned"/"Led"/"Architected", woven into an otherwise-real bullet)
    but the ORIGINAL RESUME shows no real or adjacent basis for it. This is the case you are
    specifically hunting for — a fabricated or unsupported claim dressed up to look real.

Return your findings as plain text, one line per skill, in exactly this format:
  SKILL_NAME | TIER_FOUND | VERDICT (OK or VIOLATION) | ONE-LINE REASON

If a skill from the missing-skills list does not appear anywhere in the final resume, report:
  SKILL_NAME | NOT_PRESENT | OK | skill was not added

After the per-skill lines, add a final line:
  SUMMARY: N skills audited, M violations found

Return ONLY this report. No commentary, no resume rewriting, no markdown formatting."""


def _parse_tier_audit(report: str) -> list[str]:
    """Parse the tier audit report and return only the VIOLATION lines as issue strings."""
    violations = []
    for line in report.strip().split("\n"):
        line = line.strip()
        if not line or line.upper().startswith("SUMMARY:"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4 and parts[2].upper() == "VIOLATION":
            skill, tier_found, _, reason = parts[0], parts[1], parts[2], parts[3]
            violations.append(
                f"[TIER VIOLATION] '{skill}' placed as {tier_found} but original resume "
                f"shows no real/adjacent basis — {reason}"
            )
    return violations


async def audit_tier_compliance(
    base_resume: str,
    final_resume: str,
    missing_skills: list[str],
    api_key: str, provider: str, model: str,
) -> tuple[list[str], str]:
    """
    Truth-audit pass: verifies skills added to close JD coverage gaps were placed
    at an honest tier (visibility-only vs. production-claim). Report-only — never
    edits the resume. Returns (violation_issues, raw_report).
    If missing_skills is empty, skips the call entirely (nothing to audit).
    """
    if not missing_skills:
        return [], ""

    msg = (
        f"=== SKILLS THAT WERE MISSING FROM THE ORIGINAL RESUME ===\n"
        f"{', '.join(missing_skills)}\n\n"
        f"=== CANDIDATE'S ORIGINAL RESUME (ground truth) ===\n{base_resume}\n\n"
        f"=== FINAL TAILORED RESUME ===\n{final_resume}"
    )

    report = await chat(
        system=TIER_AUDIT_PROMPT,
        user=msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=2048,
    )
    report = report.strip()
    violations = _parse_tier_audit(report)
    return violations, report


async def review_resume(tailored: str, job_description: str,
                        api_key: str, provider: str, model: str,
                        profile_skills: list[str] | None = None) -> str:
    """One-shot semantic review pass. Fires exactly once after _enforce_limits."""
    skills_ctx = ""
    if profile_skills:
        skills_ctx = (
            f"\n=== CANDIDATE'S DECLARED SKILLS (keep ALL in skills section) ===\n"
            f"{', '.join(profile_skills)}\n"
        )
    msg = (
        "Review and fix the 3 semantic issues per your instructions.\n"
        "Return the complete corrected resume as plain text only — no commentary, no plan block.\n"
        f"{skills_ctx}\n"
        f"=== JOB DESCRIPTION ===\n{job_description[:8000]}\n\n"
        f"=== TAILORED RESUME ===\n{tailored}"
    )

    reviewed = await chat(
        system=REVIEWER_PROMPT,
        user=msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=4096,
    )
    stripped = re.sub(r'<plan>.*?</plan>', '', reviewed, flags=re.DOTALL).strip()
    if stripped != reviewed:
        print("[WARN] Reviewer output contained <plan> block — may be over-thinking")
    return stripped


# ── Per-issue retry rules ─────────────────────────────────────────────────────
_RETRY_RULES = {
    "[MISSING CONTACT]":       "Line 2 must be 'phone | email' — add the contact line with real phone and email.",
    "[MISSING LOCATION]":      "Every job header must include '| City, State' after the company name.",
    "[MISSING CLOSING LINE]":  "Every job block must end with the correct closing line for this role type (e.g. 'Technologies Used:' for tech, 'Selected Transactions:' for IB, 'Technologies & Platforms:' for cyber).",
    "[BANNED CLOSING LABEL]":  "Use the exact closing line label required for this role type — no substitutes.",
    "[BANNED WORD]":           "Replace 'utilized' and 'leveraged' with active verbs: 'used', 'built', 'ran'.",
    "[META LEAK]":             "Remove all instruction text, placeholders, or commentary from the resume body.",
    "[TOO LONG]":              "Shorten to ≤22 words. One idea per bullet only. Split compound bullets.",
    "[MULTI-IDEA]":            "One accomplishment per bullet. Split into two or cut the weaker half.",
    "[SAME VERB]":             "No two consecutive experience bullets may open with the same verb — vary them.",
    "[SUMMARY]":               "PROFESSIONAL SUMMARY must have exactly 5 bullet lines — not 4, not 6.",
    "[BULLET OVERFLOW]":       "Total bullets exceed the limit for this role type. Cut lowest-relevance bullets first.",
    "[MISSING SECTION]":       "A required section is missing — check for output truncation and regenerate the full resume.",
    "[LOW METRICS]":           "Add quantified outcomes to more experience bullets to meet the role-appropriate target.",
    "[HIGH METRICS]":          "Remove forced numbers from process/collaboration bullets — looks artificial.",
    "[JD ECHO]":               "A JD word repeated 3+ times reads as keyword stuffing. Vary phrasing; keep ≤2 uses.",
    "[LOW JD SKILL VISIBILITY]": "Add 1–3 missing skills via the correct tier: WORK-SUPPORTED bullet, ADJACENT-STRETCH bullet (max 1/job, 2 total), or SELF-IMPLEMENTABLE/HIGH-RISK skills-project wording. Visibility-only placement is acceptable — never force a production claim.",
    "[YEARS MISMATCH]":          "Use the exact years-of-experience number from the ORIGINAL RESUME — do not inflate or deflate it.",
    "[YEARS FABRICATED]":        "The original resume has no years-of-experience claim in the summary. Remove the years number entirely — do not invent one.",
    "[UNSUPPORTED EXPERIENCE CLAIM]": "Remove or rewrite the summary claim to only reflect experience types supported by the work bullets below it.",
}


async def tailor_resume(base_resume: str, job_description: str,
                        api_key: str, provider: str, model: str,
                        profile_skills: list[str] | None = None) -> str:

    # Detect role type up front so _enforce_limits uses the right budget
    role_type = detect_role_type(job_description)
    budget    = BULLET_BUDGETS[role_type]
    hard_total = budget[5]
    exp_total  = hard_total - 5  # subtract summary

    jd_hard_skills = []
    if extract_jd_hard_skills is not None:
        jd_hard_skills = extract_jd_hard_skills(job_description, role_type)

    # Snapshot which JD hard skills are missing from the ORIGINAL resume —
    # this is the ground-truth list the tier-compliance audit checks against
    # later. Computed once, before any tailoring happens.
    skills_missing_from_original: list[str] = []
    if skill_coverage_report is not None and jd_hard_skills:
        original_coverage = skill_coverage_report(
            base_resume, job_description, role_type=role_type, profile_skills=profile_skills
        )
        skills_missing_from_original = original_coverage.get("missing", [])

    jd_skills_section = ""
    if jd_hard_skills:
        jd_skills_section = (
            "\n=== JD HARD SKILLS DETECTED ===\n"
            + ", ".join(jd_hard_skills)
            + "\nVISIBILITY target: 100% — every skill above should appear somewhere on the resume "
              "(experience bullet, stretch bullet, or skills/project section) when a defensible placement exists.\n"
            + "PRODUCTION-CLAIM target: 85–95% — only WORK-SUPPORTED and ADJACENT-STRETCH skills may read as "
              "real employer production work. SELF-IMPLEMENTABLE and HIGH-RISK skills satisfy visibility only, "
              "via skills/project/prototype wording — never as employer production claims.\n"
        )

    declared_section = ""
    if profile_skills:
        declared_section = (
            "\n=== CANDIDATE'S DECLARED SKILLS — include ALL in skills/competencies section ===\n"
            + ", ".join(profile_skills)
            + "\nOrganize by JD-relevant categories appropriate to the role type. Do NOT omit any declared skill.\n"
        )

    user_msg = (
        f"Tailor this resume to the JD. "
        f"Role type detected: {role_type}. "
        f"Hard bullet limit: {hard_total} total (5 summary + {exp_total} experience). "
        f"Output: plain text resume only.\n"
        f"{declared_section}"
        f"{jd_skills_section}\n"
        "STEP 1 — Open a <plan> block. Fill in EVERY field explicitly before writing a single resume line:\n"
        "  ROLE_TYPE: [detected role type and why — TECH / IB / FINANCE / CYBER / HEALTHCARE / CONSULTING / GENERAL]\n"
        "  COMPANY_STAGE: [startup / enterprise / unknown — key signals from JD]\n"
        "  SECTION_LABELS: [exact section header labels you will use for this role type]\n"
        "  CLOSING_LINE_FORMAT: [exact closing line format per role type, or 'none' if not applicable]\n"
        "  SUMMARY_TITLE: [JD target role title] → [exact text of summary bullet 1]\n"
        "  PRIMARY_FUNCTIONS: [list each JD primary function and which 2+ bullets will cover it]\n"
        "  JOB_HEADERS: [list every job header from the base resume exactly as written — confirm each appears UNCHANGED]\n"
        "  DOMAINS: [each company → its real industry; derive from resume text, never invent]\n"
        "  TIMELINE: [each role's start–end years + which JD tools were enterprise-ready by then]\n"
        "  TIMELINE_BLOCKS: [any JD tool failing timeline check → skills-only or dropped; 'none' if all clear]\n"
        "  JD_SKILL_COVERAGE: [JD hard skills detected → present in base resume / missing → target: 100% visibility, 85–95% production-claim]\n"
        "  MISSING_SKILL_PLACEMENT: [each missing hard skill → WORK-SUPPORTED / ADJACENT-STRETCH / SELF-IMPLEMENTABLE / HIGH-RISK, exact placement, and which target it counts toward (visibility-only vs. production-claim)]\n"
        "  GAP_FILLS: [for each JD hard skill absent from resume: market-coverage class + 5-anchor test result → role assignment / skills only / project / DROP]\n"
        "  WRONG_JOB_CHECK: [skills whose only bullet is at an older role → confirm gap-fill at most recent plausible role]\n"
        "  CUTS: [which existing bullets are displaced to make room, and from which role]\n"
        "  COMPLIANCE_DROPS: [frameworks skipped because legally impossible in candidate's domain; 'none' if all apply]\n"
        "  DEPTH_GAPS: [existing bullets that show only deployment/exposure for JD-critical skills → rewrite plan]\n"
        "Close </plan>.\n\n"
        "STEP 2 — Write the complete tailored resume following all system prompt rules.\n\n"
        "STEP 3 — Within each job, confirm bullets are ordered highest-JD-relevance first, lowest last. "
        "Count every bullet. Rewrite any over 22 words before finalizing.\n\n"
        f"=== JOB DESCRIPTION ===\n{job_description[:16000]}\n\n"
        f"=== ORIGINAL RESUME ===\n{base_resume}"
    )

    raw = await chat(
        system=SYSTEM_PROMPT,
        user=user_msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=6000,
    )

    # Strip <plan> block
    raw = re.sub(r'<plan>.*?</plan>', '', raw, flags=re.DOTALL).strip()

    # ── Quality gate: lint → up to 3 retries, best-of-N ────────────────────
    _best_raw         = raw
    _best_issue_count = len(lint_resume(raw, job_description, base_resume=base_resume))

    for attempt in range(3):
        issues = lint_resume(raw, job_description, base_resume=base_resume)

        if len(issues) <= _best_issue_count:
            _best_issue_count = len(issues)
            _best_raw = raw

        if not issues:
            break

        issue_lines = "\n".join(
            "  • {}\n    → {}".format(
                iss,
                _RETRY_RULES.get(
                    "[" + iss.split("]")[0].lstrip("[") + "]",
                    "Re-read the system prompt rules and fix this issue."
                )
            )
            for iss in issues
        )
        fix_msg = (
            f"TARGETED FIX — attempt {attempt + 2} of 3.\n"
            "Fix ONLY the specific issues listed below. "
            "Do NOT alter any other bullet, section, or line — surgical edits only.\n"
            "Return the COMPLETE resume as plain text with only these fixes applied.\n\n"
            f"ISSUES TO FIX:\n{issue_lines}\n\n"
            "=== RESUME TO FIX ===\n" + raw
        )
        raw = await chat(
            system=SYSTEM_PROMPT,
            user=fix_msg,
            api_key=api_key,
            provider=provider,
            model=model,
            max_tokens=6000,
        )
        raw = re.sub(r'<plan>.*?</plan>', '', raw, flags=re.DOTALL).strip()

    # Best-of-N final check
    final_issues = lint_resume(raw, job_description, base_resume=base_resume)
    if len(final_issues) < _best_issue_count:
        _best_raw = raw
        _best_issue_count = len(final_issues)
    if _best_issue_count > 0 and _best_raw is not raw:
        print(
            f"[RETRY] Best-of-N: using earlier attempt "
            f"({_best_issue_count} issues remaining vs {len(final_issues)} in last)"
        )
    raw = _best_raw

    # ── Enforce hard limits — role-type-aware ────────────────────────────────
    result = _enforce_limits(raw, role_type=role_type)

    # ── Job integrity safety net — deterministic, no AI involvement ──────────
    # Runs before review so the reviewer never sees hallucinated companies.
    result, removed_jobs, reinserted_jobs = _enforce_job_integrity(result, base_resume)
    if removed_jobs:
        print(f"[JOB HALLUCINATION] Removed {len(removed_jobs)} fake job block(s): {', '.join(removed_jobs)}")
    if reinserted_jobs:
        print(f"[JOB RESTORED] Re-inserted {len(reinserted_jobs)} real job(s) verbatim: {', '.join(reinserted_jobs)}")

    # ── Semantic review — 1 pass, no retry ──────────────────────────────────
    pre_review = result
    result = await review_resume(
        result, job_description, api_key, provider, model,
        profile_skills=profile_skills,
    )
    if result != pre_review:
        print("[REVIEW] Reviewer made changes")
    else:
        print("[REVIEW] No semantic violations found — resume passed all 3 checks")

    # ── Post-review lint — log WARN only, no retry ───────────────────────────
    post_issues = lint_resume(result, job_description, base_resume=base_resume)
    if post_issues:
        print(f"[WARN] post-review lint ({len(post_issues)}):")
        for iss in post_issues:
            print(f"  • {iss}")

    if skill_coverage_report is not None:
        coverage = skill_coverage_report(
            result, job_description, role_type=role_type, profile_skills=profile_skills
        )
        if coverage.get("jd_skills"):
            print(
                f"[VISIBILITY] JD hard skills visible on resume: {coverage['coverage_text']} "
                f"({coverage['coverage_ratio']:.0%}) — presence check only, "
                f"not a verification of production-claim tier."
            )
            if coverage.get("missing"):
                print("[VISIBILITY] Missing: " + ", ".join(coverage["missing"]))

    # ── Tier-compliance audit — second AI pass, truth check, report-only ─────
    # Checks only the skills that were genuinely missing from the ORIGINAL
    # resume. Never edits the resume — surfaces violations for human review
    # (or for a future hard-gate retry, if you decide to make this blocking).
    if skills_missing_from_original:
        try:
            violations, raw_report = await audit_tier_compliance(
                base_resume, result, skills_missing_from_original,
                api_key, provider, model,
            )
            if violations:
                print(f"[TIER AUDIT] {len(violations)} violation(s) found:")
                for v in violations:
                    print(f"  • {v}")
            else:
                print(f"[TIER AUDIT] Clean — {len(skills_missing_from_original)} gap-filled skill(s) audited, no violations.")
        except Exception as e:
            # Audit failure should never block resume delivery — log and move on.
            print(f"[TIER AUDIT] Audit pass failed to run: {e}")

    # ── Education section safety net — deterministic, no AI involvement ──────
    # Runs after all AI passes. Compares EDUCATION section of final output
    # against the original base resume. If the AI altered it (degree name,
    # institution, year), hard-replaces with the verbatim original content.
    original_edu = _extract_education_section(base_resume)
    result_edu   = _extract_education_section(result)
    if original_edu and result_edu != original_edu:
        print("[EDUCATION MISMATCH] AI altered education section — reverting to original.")
        print(f"  Original : {original_edu[:120]}")
        print(f"  AI had   : {result_edu[:120]}")
        result = _replace_education_section(result, original_edu)

    return result
