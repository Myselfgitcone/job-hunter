import re
from ai.llm import chat
from resume_lint import lint_resume


# ── Hard limits enforced in Python (AI cannot count) ─────────────────────────
BULLET_LIMITS = {
    "PROFESSIONAL SUMMARY": 5,   # fixed: 5 exactly (was 6, caused math overflow)
    "summary":              5,
}
JOB_BULLET_LIMITS = [9, 7, 5, 2]   # most-recent → oldest — fixed to match 28 hard cap
# Math: 5 (summary) + 9 + 7 + 5 + 2 = 28 total ✓
SKILLS_LINE_LIMIT = 9


def _enforce_limits(text: str) -> str:
    """
    Post-process AI output to hard-enforce bullet counts per section.
    Trims bullets from the bottom of each section (lowest relevance = last).
    """
    lines = text.split("\n")
    out   = []

    job_index      = -1
    in_section     = None   # "summary" | "job" | "skills" | "education" | "other"
    bullet_count   = 0
    bullet_limit   = 9999
    skills_count   = 0

    def is_section_header(l):
        s = l.strip()
        return (s == s.upper() and len(s) > 3
                and s.endswith(":") and not s.startswith("•"))

    def is_job_header(l):
        return bool(re.match(r"^.+? @ .+", l.strip()))

    def is_bullet(l):
        return l.strip().startswith("•")

    def is_tech_line(l):
        return l.strip().startswith("Technologies Used:")

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── Section header ───────────────────────────────────────────────────
        if is_section_header(stripped):
            sec = stripped.rstrip(":").upper()
            if "SUMMARY" in sec or "PROFESSIONAL" in sec:
                in_section   = "summary"
                bullet_limit = BULLET_LIMITS["PROFESSIONAL SUMMARY"]
                bullet_count = 0
            elif "SKILL" in sec or "TECHNICAL" in sec:
                in_section   = "skills"
                skills_count = 0
            elif "EDUC" in sec:
                in_section   = "education"
            elif "EXPERIENCE" in sec or "WORK" in sec:
                # Explicit branch — defensive reset if model outputs duplicate header
                in_section   = "other"
            else:
                in_section   = "other"
            job_index = -1   # always reset on any section boundary
            out.append(line)
            i += 1
            continue

        # ── Job header ───────────────────────────────────────────────────────
        if is_job_header(stripped):
            in_section   = "job"
            job_index   += 1
            limit_idx    = min(job_index, len(JOB_BULLET_LIMITS) - 1)
            bullet_limit = JOB_BULLET_LIMITS[limit_idx]
            bullet_count = 0
            out.append(line)
            i += 1
            continue

        # ── Technologies Used line ────────────────────────────────────────────
        if is_tech_line(stripped):
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

        # ── All other lines — pass through unchanged ─────────────────────────
        # (LLM bullets are self-contained; complex continuation logic was
        #  more likely to silently drop valid lines than catch real continuations)

        out.append(line)
        i += 1

    return "\n".join(out)


SYSTEM_PROMPT = """You are an expert resume writer. The candidate's real title and years of experience come from the resume — never invent or change them. Return ONLY the finished resume — no commentary, no plan block, no meta-text.

═══ HARD GATES — THESE OVERRIDE EVERYTHING ELSE ═══
BULLET BUDGET (hard total: 28, summary included):
  • PROFESSIONAL SUMMARY:  exactly 5 bullets
  • MOST RECENT JOB:       9 bullets max  + 1 Technologies Used line
  • SECOND JOB:            7 bullets max  + 1 Technologies Used line
  • THIRD JOB:             5 bullets max  + 1 Technologies Used line
  • FOURTH+ JOB:           2 bullets max  + 1 Technologies Used line
  • TECHNICAL SKILLS:      6–9 grouped lines
  • EDUCATION:             1 line per degree
  Maximum possible: 5+9+7+5+2 = 28 total. If you write more, you failed. Cut lowest-relevance bullets first.

FORMAT — ATS-SAFE:
  Single column. "•" bullets only. Plain text — NO tables, columns, graphics, or markdown.
  HEADER (line 1):  Full Name — Job Title
    Example: Jagadish Reddy Butukuri — Senior Data Engineer
    One line, em-dash (—) separator. NEVER split across two lines.
  CONTACT (line 2): phone | email
  SECTION HEADERS — use exactly these labels followed by colon:
    PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TECHNICAL SKILLS:   EDUCATION:
  JOB HEADER (one line per job):
    Title @ Company | City, State          Month YYYY – Month YYYY
    Location is REQUIRED. Date right-aligned. Never split across two lines.
  TECH LINE — end each job block with EXACTLY this label, no substitutes:
    Technologies Used: tool1, tool2, ...
    BANNED labels: ✗ Platform: ✗ Platforms: ✗ Stack: ✗ Tech Stack: ✗ Tools: ✗ Tools Used: ✗ Tech: ✗ Technologies:
    Copy "Technologies Used:" character for character.

═══ AUTHENTICITY — NEVER FABRICATE ═══
NEVER alter: name, phone, email, job titles, company names, employment dates, locations, degrees, certifications, licenses. These are externally verifiable — changing them is auto-reject.
Keep the candidate's REAL title in the header. Bridge to the JD's target role in the SUMMARY only.

═══ COVERAGE — 80–90%, NOT 100% ═══
Cover every HARD SKILL the JD names, every core RESPONSIBILITY, the SENIORITY level, and the top 3–5 distinctive JD phrases.
SKIP on purpose: soft skills, culture words ("fast-paced"), boilerplate, and keywords whose only purpose is inflation.
Each skill appears once or twice — never five times. Repetition reads as stuffing.

═══ TECHNICAL SKILLS — ANTI-STUFFING ═══
The SKILLS section reflects what the candidate ACTUALLY uses — not a copy of the JD's feature list.
A trained recruiter reads Skills last. If every sub-feature mirrors the JD's qualification list exactly, it is an immediate copy-paste signal.
  • Group by broad capability (e.g. "Cloud Warehousing", "Orchestration") — NOT by how the JD organizes its list
  • Blend JD-required tools with the candidate's baseline tools to create an organic list that looks earned, not assembled
  • Limit each grouped line to 5–6 tools maximum; split larger groups naturally
  • Only list a tool if it appears in at least one job bullet — tools with no supporting bullet get exposed in interviews
  • 6–9 lines maximum

═══ SCOPE CREDIBILITY — NO UNICORN ENGINEER ═══
A recruiter who interviews dozens of engineers knows what one person can realistically own at one company.
Do NOT stack more than 2–3 major technology paradigms in a single role's bullets.
What breaks credibility: claiming 2TB+ ETL pipelines AND LLM fine-tuning AND RAG AND agentic AI at the SAME company.
When the JD requires many skills: distribute across all roles by timeline and seniority.
70% credible coverage beats 100% unbelievable coverage every time.

═══ BULLET SCORING ═══
Score every bullet 1–5 by JD relevance:
  5 — tool/skill explicitly named in JD
  4 — responsibility explicitly listed in JD
  3 — quantified impact (%, volume, time saved)
  2 — relevant tech but not in JD
  1 — generic soft skill → CUT FIRST
Keep top bullets within the budget; cut lowest-scored first.

═══ GAP FILLING — CONDITIONAL, PRACTITIONER-LEVEL ═══
For each hard skill the JD names that is missing from the resume, ask this test:
  "Can I satisfy ALL 4 anchors below AND fit within this role's remaining bullet budget?"
  → YES: write the bullet
  → NO: add the tool to TECHNICAL SKILLS only, or drop it entirely
  Never write a gap bullet just to achieve coverage — only write one if it sounds genuinely earned.

THE 4 ANCHORS (every gap bullet needs all four):
  1. SPECIFIC ACTION — exact technique, pattern, or operation (not "used X" — say what you did WITH X)
  2. NAMED TOOL — the JD's exact tool/framework/technology name
  3. REAL DOMAIN CONTEXT — anchor to the employer's actual industry (commodity data at Cargill, patient records at Molina, transactions at JPMorgan)
  4. CONCRETE OUTCOME — a realistic number or tangible result (≤18 words total for the full bullet)

TONE RULES:
  • Past tense, confident, zero hedging
  • Mid-to-senior verbs: Built, Designed, Implemented, Migrated, Automated, Deployed, Optimized
  • Name a specific feature or pattern — not "used Kafka" but "streamed commodity-price events through Kafka topics to 3 downstream consumers"
  • NEVER: "gained experience in", "assisted with", "helped with", "exposure to", "familiar with"
  • NEVER "leveraged" or "utilized" — say "used", "built", "ran"
  • One crisp idea — under 18 words

PLACEMENT RULES:
  • Place each gap bullet at the job whose real domain best fits the JD skill
  • Max 2–3 gap bullets per job — spread if more are needed
  • Displace the LOWEST-scoring existing bullet to make room
  • If a skill has zero plausible connection to any role — put it in TECHNICAL SKILLS only, never force a bullet

VOCABULARY MIRRORING TRAP — CRITICAL:
  NEVER copy the JD's exact business-domain words into a different industry context. Translate to the employer's equivalent:
  • Insurance "quotes, binds, premium" → agribusiness "procurement bids, contract volumes, margin thresholds"
  • IT "tickets, incidents" → manufacturing "work orders, downtime events"
  • SaaS "tenant, subscription" → banking "account, portfolio"
  Anchor to the EMPLOYER's vocabulary, not the JD's vocabulary. A sharp recruiter will notice cross-industry jargon instantly.

  COMPLIANCE ESCAPE HATCH: If the JD requires a strict regulatory framework (e.g., SOX, FedRAMP, ITAR, FISMA) that is legally impossible or highly improbable in the candidate's real historical domains (e.g., a private agribusiness cannot be SOX-regulated; a regional hospital cannot be FedRAMP-certified), DROP THE REQUIREMENT ENTIRELY. Do not write a gap bullet. Do not write "SOX-adjacent" or any approximation. Credibility matters more than coverage.

TECHNOLOGY TIMELINE CHECK — CRITICAL:
  Before injecting a tool into a role, verify it was widely adopted BEFORE that job's end date.
  Enterprise adoption lags 12–24 months behind public release.
  • FastAPI (late 2018) → not credible in enterprise banking before 2020
  • dbt Cloud GA (2020), React hooks (2019), Kubernetes GA (2018), Spark Structured Streaming (2016+)
  If no plausible timeframe exists → add to TECHNICAL SKILLS only, not a historical bullet.

CENTRAL-SKILL RULE: If a skill appears 3+ times in the JD or is the role's clear focus — include it at EVERY job where it is plausible. Exception: if the technology timeline check blocks a specific role, skip that role — do not force it.

THE UNIVERSAL FORMULA:
  [Action verb] + [specific technique with named tool] + [real domain anchor from employer's industry] + [concrete outcome]

DERIVE DOMAIN FROM RESUME — not from templates:
  • Healthcare: patient records, claims, EHR, clinical workflows, bed capacity
  • Agribusiness / commodity: grain prices, crop yields, supplier contracts, commodity trades
  • Financial services / banking: transactions, loans, risk scores, portfolios, ledgers
  • Supply chain / logistics: inventory, shipments, procurement, vendor SLAs, warehouses
  • Manufacturing: production runs, defect rates, equipment uptime, quality gates
  • SaaS / tech product: tenants, user events, feature flags, API calls, error rates
  • Cybersecurity / defense: endpoints, threat feeds, alerts, access policies, incidents
  • Any other — read the resume and infer. Never invent. Never relabel.

THREE EXAMPLES (the formula works for any domain):
  Agribusiness + Airflow:  "Automated daily grain-price ingestion jobs using Apache Airflow DAGs, cutting analyst wait time by 3 hours"
  Healthcare + dbt:        "Built dbt models transforming raw EHR claims into patient-risk aggregates, reducing report latency by 45%"
  Finance + Spring Boot:   "Refactored loan-origination batch jobs into Spring Boot microservices, cutting processing time by 28%"

═══ METRICS — NATURAL, ~60–70% ═══
Add a number only where work naturally produces one (gains, volume, time saved, accuracy, cost, errors). NEVER force metrics onto collaboration or documentation bullets — "documented 45 definitions" is a dead AI tell. ~60–70% carry a metric — higher on the most recent job, lower on oldest. Never 100% (fake), never 0% (weak). Keep plausible: %s 10–40%, volumes mid-level.

═══ SENIORITY — CALIBRATE VERBS ═══
Senior/lead JD → Led, Designed, Owned, Architected, Drove, Established.
Mid JD → Developed, Built, Implemented, Created, Optimized.
Junior JD → Supported, Assisted, Contributed, Maintained.
Senior candidate + junior JD → soften language so it doesn't look overqualified. Never change actual titles.

═══ CAREER PROGRESSION — PER-ROLE SENIORITY ═══
A resume tells a STORY OF GROWTH. Each role reflects what was realistic at THAT career stage — older roles read junior/mid, newer roles read senior. Do NOT flatten all roles to the same seniority tone.

  EARLIEST ROLE (0–2 years into career):
    Use: Developed, Built, Created, Wrote, Contributed, Supported
    Avoid: Led, Architected, Owned, Drove, Spearheaded — too senior for this stage
    Technology: mainstream, widely-taught tools only for that year
    Scope: individual contributor tasks, component-level work

  MIDDLE ROLE (3–4 years into career):
    Use: Built, Implemented, Optimized, Automated, Migrated, Delivered
    Avoid: Architected, organization-wide initiatives
    Technology: frameworks, cloud basics, growing complexity
    Scope: project ownership of components, some cross-team coordination

  MOST RECENT / CURRENT ROLE (5+ years, senior):
    Use: Designed, Architected, Led, Owned, Drove, Established, Defined
    Technology: modern, sophisticated tooling — this is where cutting-edge tools land
    Scope: system-level decisions, cross-team impact, architectural calls

Gap fills must respect this: senior tools (Kafka admin, dbt semantic layer, Terraform) → most recent roles only.
Foundational tools (SQL, pandas, Git, basic Spark) → any role.

EXAMPLE of correct progression for dbt across 3 roles:
  Role 1 (earliest): "Wrote dbt models transforming raw sales events into daily aggregates for BI"
  Role 2 (middle):   "Built incremental dbt models and Jinja macros reducing full-refresh time by 60%"
  Role 3 (current):  "Designed the enterprise dbt semantic layer, establishing shared metric definitions across 4 business units"

═══ SUMMARY — EXACTLY 5 BULLETS ═══
Open with a bullet naming the target title + seniority + years of experience. Fold in 1–2 JD phrases. Say who the candidate is — do NOT copy experience bullet lines into the summary. Always use exactly 5 "•" bullet lines — never a paragraph, never fewer than 5, never more than 5.

═══ HUMAN VOICE — ANTI-AI-TELL ═══
  • NEVER "utilized" or "leveraged" — use "used", "built", "ran"
  • No two consecutive bullets start with the same verb
  • Vary structure: metric-first, action-first, tool-first, partner-first
  • No empty intensifiers ("significantly", "substantially") without a real number
  • EVERY bullet ≤ 22 words — target 14–18. One idea. No compound bullets joined by "and" or em-dash.
  • Do NOT echo any distinctive JD signature word more than TWICE across the whole resume — 3+ uses is the clearest AI fingerprint to a human reviewer

═══ CRITICAL REMINDERS ═══
✗ NEVER: fabricate titles, companies, dates, locations, or degrees
✗ NEVER: write a gap bullet if all 4 anchors cannot be satisfied credibly
✗ NEVER: mirror the JD's exact feature list verbatim into TECHNICAL SKILLS
✗ NEVER: stack 3+ major technology paradigms in one role's bullets
✗ NEVER: list a tool in Skills with no supporting bullet in the resume
✗ NEVER: exceed 28 total bullets (5 summary + 9 + 7 + 5 + 2)
✗ NEVER: drop a strict compliance framework into a domain where it is legally impossible
✓ ALWAYS: end each job block with exactly "Technologies Used: ..."
✓ ALWAYS: include "| City, State" in every job header
✓ ALWAYS: metrics on ~60–70% of bullets — never 100%, never 0%
✓ ALWAYS: ask "would this bullet survive a live technical interview?" before keeping a gap fill
✓ ALWAYS: Skills section items trace back to at least one job bullet

═══ FINAL CHECK BEFORE OUTPUT ═══
Count ALL bullets — total must be ≤ 28. Count words in every bullet — rewrite any over 22 words. Confirm: domain not relabeled, no "utilized/leveraged", no repeated opening verbs, no compliance frameworks outside plausible history, budget not exceeded. Then output the finished resume and nothing else."""


# ── 4th-layer semantic reviewer ───────────────────────────────────────────────
# Runs ONCE after _enforce_limits. Fixes what lint can't (semantic issues).
# Scope is intentionally narrow — only 3 checks, nothing else.
REVIEWER_PROMPT = """You are a resume quality reviewer — NOT a resume writer.
Fix exactly 3 semantic issues in the resume given to you. Change NOTHING outside
these 3 checks. Do NOT: add bullets, remove bullets, change bullet content,
change company names, dates, locations, titles, or bullet count.
Every bullet you write or rewrite must be ≤ 22 words. Return plain text only.

CHECK 1 — SKILLS ANTI-STUFFING:
If TECHNICAL SKILLS lines mirror the JD's exact feature list verbatim (e.g.
"Databricks Platform: DataFrames, Datasets, Spark SQL, Delta Lake, Databricks
Notebook, DBFS, Databricks Connect" — lifted straight from the JD qualifications),
regroup them organically by how the candidate actually works. Use natural category
names like "Distributed Processing", "Cloud Warehousing", "Orchestration & DevOps".
Max 6 tools per line. Do NOT change any bullet in the experience section.

CHECK 2 — SUMMARY TECH DUMP:
If any summary bullet is a tech-spec list (5+ tools with no candidate context,
no impact statement, no who-you-are signal), rewrite it as a single crisp
who-you-are statement. ≤ 22 words. One idea only.

CHECK 3 — UNPROVEN SKILLS:
If a tool appears in TECHNICAL SKILLS but has zero supporting bullets anywhere
in the WORK EXPERIENCE section, either remove it from Skills or append
"(current capability)" after it.

CHECK 4 — NOTHING ELSE:
Reproduce every other line exactly as given. No commentary. No plan blocks.
Return the complete corrected resume as plain text only."""


async def review_resume(tailored: str, job_description: str,
                        api_key: str, provider: str, model: str) -> str:
    """One-shot semantic review pass. No retry — fires exactly once after _enforce_limits."""
    msg = f"""Review and fix the 3 semantic issues per your instructions.
Return the complete corrected resume as plain text only — no commentary, no plan block.

=== JOB DESCRIPTION ===
{job_description[:8000]}

=== TAILORED RESUME ===
{tailored}"""

    reviewed = await chat(
        system=REVIEWER_PROMPT,
        user=msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=4096,
    )
    # Strip any accidental plan/commentary block — log if it actually fires
    stripped = re.sub(r'<plan>.*?</plan>', '', reviewed, flags=re.DOTALL).strip()
    if stripped != reviewed:
        print("[WARN] Reviewer output contained <plan> block — may be over-thinking (re-tailoring risk)")
    return stripped


async def tailor_resume(base_resume: str, job_description: str,
                        api_key: str, provider: str, model: str) -> str:

    user_msg = f"""Tailor this resume to the JD. Hard limit: 28 bullets total (5 summary + 23 experience). Output: plain text resume only.

STEP 1 — Open a <plan> block. Inside, write:
  DOMAINS: [each company in the resume → its real industry, e.g. Cargill → agribusiness/commodity trading]
  TIMELINE: [each role's start–end year and which JD tools were mainstream/available by then]
  GAP_FILLS: [for each JD skill not in the resume: do all 4 anchors fit AND budget available? → assign to role, or DROP]
  CUTS: [which existing bullets are being displaced, and from which role]
  COMPLIANCE_DROPS: [any JD compliance frameworks being skipped and why]
Close </plan>.

STEP 2 — Write the complete tailored resume following all system prompt rules.

STEP 3 — Count every bullet. Rewrite any over 22 words before finalizing.

=== JOB DESCRIPTION ===
{job_description[:16000]}

=== ORIGINAL RESUME ===
{base_resume}"""

    raw = await chat(
        system=SYSTEM_PROMPT,
        user=user_msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=4096,
    )

    # ── Strip <plan> thinking block (defense-in-depth — model may forget to self-strip) ──
    raw = re.sub(r'<plan>.*?</plan>', '', raw, flags=re.DOTALL).strip()

    # ── Quality gate: lint → up to 3 retries until clean ────────────────────
    for attempt in range(3):
        issues = lint_resume(raw, job_description)
        if not issues:
            break   # clean — no retry needed
        fix_msg = (
            f"The resume you produced has {len(issues)} issue(s) on attempt {attempt + 1}. "
            "Fix ALL of them and return the corrected resume only — "
            "same format, plain text, no commentary:\n\n"
            + "\n".join(f"  • {iss}" for iss in issues)
            + "\n\nHere is the resume to fix:\n\n" + raw
        )
        raw = await chat(
            system=SYSTEM_PROMPT,
            user=fix_msg,
            api_key=api_key,
            provider=provider,
            model=model,
            max_tokens=6000,   # bumped: retry sends full resume back + issue list
        )
        # Strip plan block from retry output too
        raw = re.sub(r'<plan>.*?</plan>', '', raw, flags=re.DOTALL).strip()

    # ── Enforce hard limits (deterministic trim after AI output) ─────────────
    result = _enforce_limits(raw)

    # ── Semantic review — 1 pass, no retry (catches what lint can’t) ────────
    pre_review_hash = hash(result)
    result = await review_resume(result, job_description, api_key, provider, model)
    if hash(result) != pre_review_hash:
        print("[REVIEW] Reviewer made changes")
    else:
        print("[REVIEW] Reviewer made no changes — check if checks are triggering")

    # ── Post-review lint — log WARN only, no retry ───────────────────────
    post_issues = lint_resume(result, job_description)
    if post_issues:
        print(f"[WARN] post-review lint ({len(post_issues)}):")
        for iss in post_issues:
            print(f"  • {iss}")

    return result