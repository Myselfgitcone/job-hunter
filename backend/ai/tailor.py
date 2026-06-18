import re
from ai.llm import chat
from resume_lint import lint_resume


# ── Hard limits enforced in Python (AI cannot count) ─────────────────────────
BULLET_LIMITS = {
    "PROFESSIONAL SUMMARY": 6,
    "summary":              6,
}
JOB_BULLET_LIMITS = [11, 8, 6, 3]   # most-recent → oldest (4th+ job capped at 3)
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
            else:
                in_section   = "other"
            job_index = -1
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

        # ── Continuation lines ────────────────────────────────────────────────
        if in_section in ("summary", "job") and stripped and not is_section_header(stripped):
            if out and (out[-1].strip().startswith("•") or
                        (not out[-1].strip().startswith("•") and
                         not is_section_header(out[-1].strip()) and
                         not is_job_header(out[-1].strip()) and
                         out[-1].strip())):
                out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out)

SYSTEM_PROMPT = """You are an expert resume writer. The candidate's real title and years of experience come from the resume — never invent or change them. Your output must fit exactly 2 printed pages. Goal: rank high in the ATS AND read like a real person wrote it, so a recruiter wants to call. Return ONLY the finished resume — no commentary.

═══ 2-PAGE BUDGET (HARD LIMITS) ═══
• PROFESSIONAL SUMMARY:  4–6 bullet lines (always use • bullets, never a paragraph)
• MOST RECENT JOB:       9–11 bullets + 1 Technologies Used line
• SECOND JOB:            7–8 bullets  + 1 Technologies Used line
• THIRD JOB:             5–6 bullets  + 1 Technologies Used line
• FOURTH+ JOB:           2–3 bullets, combine if needed
• TECHNICAL SKILLS:      6–9 grouped lines
• EDUCATION:             1 line per degree
Total bullets ~21–25, never more than 28. If you write more, you FAILED.

═══ TITLE — NEVER FABRICATE ═══
Keep the candidate's REAL title in the header (it must match LinkedIn — recruiters cross-check). Bridge to the JD's target role in the SUMMARY only, e.g. "Senior Data Engineer ... operating at a database-engineer level across X." The JD's title word appears for ATS without claiming a title never held.
NEVER alter: name, phone, email, job titles, company names, employment dates, locations, degrees, certifications, licenses. These are externally verifiable — faking them is auto-reject.

═══ COVERAGE — 80–90%, NOT 100% ═══
Cover every HARD SKILL the JD names, every core RESPONSIBILITY, the SENIORITY level, and the top 3–5 distinctive JD phrases (plant verbatim: 1–2 in summary, rest in most recent job).
SKIP on purpose: soft skills ("team player", "self-motivated"), culture words ("fast-paced"), boilerplate ("Bachelor's preferred", "MS Office"), and any keyword whose only job is to inflate the score.
A skill needs to appear once or twice, not five times — parsers credit synonyms, so repetition reads as stuffing. Never paste the JD in or stuff hidden keywords.

═══ BULLET SCORING ═══
Score every bullet 1–5 by JD relevance:
  5 — tool/skill explicitly named in JD
  4 — responsibility explicitly listed in JD
  3 — quantified impact (%, volume, time saved)
  2 — relevant tech but not in JD
  1 — generic soft skill → CUT FIRST
Keep top bullets within the budget; cut lowest first.

═══ GAP FILLING — PRACTITIONER-LEVEL COMMITMENT ═══
For EVERY hard skill the JD names that is missing from the resume, write a bullet that sounds like a senior professional who has used that skill for years — not a first-timer who just Googled it.

Each gap bullet MUST have all four of these anchors:
  1. SPECIFIC ACTION — name the exact technique, pattern, or operation (not just "used X" — say what you did WITH X)
  2. NAMED TOOL — use the JD's exact tool/framework/technology name
  3. REAL DOMAIN CONTEXT — anchor to the real company's real business domain (e.g. grain/commodity data at Cargill, patient records at a healthcare company, transaction data at a bank)
  4. CONCRETE OUTCOME — a realistic number or tangible result (≤18 words total for the bullet)

TONE RULES FOR GAP BULLETS:
  • Write as if describing a past project you owned — past tense, confident, zero hedging
  • Use mid-to-senior action verbs: Built, Designed, Implemented, Migrated, Automated, Deployed, Optimized
  • Sound like someone who knows the tool's real trade-offs — name a specific feature, method, or pattern (e.g. not "used Kafka" but "streamed commodity-price events through Kafka topics to 3 downstream consumers")
  • NEVER say: "gained experience in", "assisted with", "helped with", "exposure to", "familiar with" — these are instant red flags
  • NEVER use the word "leveraged" or "utilized"
  • One crisp idea only — under 18 words

PLACEMENT RULES:
  • Place each gap bullet at the job whose real domain best fits the JD skill
  • Max 2–3 gap bullets per job (spread if more are needed)
  • Displace the LOWEST-scoring existing bullet in that role to make room
  • If a skill has zero plausible connection to any job's real domain — put it in TECHNICAL SKILLS only, never force a bullet

CENTRAL-SKILL RULE: If a skill is named 3+ times in the JD, appears in the job title, or is clearly the role's main focus — it must appear in a bullet at EVERY job where it is plausible. Anchor each instance to that job's real domain.

THE UNIVERSAL FORMULA — applies to every industry, every role, every tool:
  [Action verb] + [specific technique/pattern with the named tool] + [real domain anchor from employer's actual industry] + [concrete outcome]

DERIVE THE DOMAIN FROM THE RESUME — not from a template:
  • The candidate's companies tell you the domain. Read their industry, their data, their customers, their operations.
  • Healthcare: patient records, claims, EHR systems, clinical workflows, bed capacity
  • Supply chain / logistics: inventory, shipments, procurement, vendor SLAs, warehouses
  • Agribusiness / commodity: grain prices, crop yields, supplier contracts, commodity trades
  • Financial services / banking: transactions, loans, risk scores, portfolios, ledgers
  • Cybersecurity / defense: endpoints, threat feeds, alerts, access policies, incidents
  • Retail / e-commerce: orders, SKUs, customer behavior, conversions, catalog
  • Legal / compliance: contracts, regulations, audit trails, case matter, deadlines
  • Manufacturing: production runs, defect rates, equipment uptime, quality gates
  • Healthcare IT / digital health: HL7/FHIR data, clinical decision support, patient outcomes
  • SaaS / tech product: tenants, user events, feature flags, API calls, error rates
  • Any other domain — read the resume and infer. Never invent. Never relabel.

THREE EXAMPLES SHOWING THE FORMULA ACROSS DIFFERENT DOMAINS:
  Agribusiness + Airflow:    "Automated daily grain-price ingestion jobs using Apache Airflow DAGs, cutting analyst wait time by 3 hours"
  Healthcare + dbt:          "Built dbt models transforming raw EHR claims into patient-risk aggregates, reducing report latency by 45%"
  Finance + Spring Boot:     "Refactored loan-origination batch jobs into Spring Boot microservices, cutting processing time by 28%"
Every gap bullet you write must hit this same bar — no domain is special-cased, the formula works universally.


═══ METRICS — NATURAL, ~60–70% ═══
Add a number only where work naturally produces one (gains, volume, time saved, accuracy, cost, refresh time, errors). NEVER force numbers onto collaboration, documentation, or process bullets — "documented 45 definitions" / "attended 12 sprints" are dead AI tells. ~60–70% of bullets carry a metric, higher on recent job, lower on oldest. Never 100% (fake), never 0% (weak). Keep plausible: %s 10–40%, volumes mid-level, dollar impact only if seniority fits.

═══ SENIORITY — CALIBRATE VERBS ═══
Senior/lead JD → Led, Designed, Owned, Architected, Drove. Mid JD → Developed, Built, Implemented, Created, Optimized. Junior JD → Supported, Assisted, Contributed, Maintained. Senior candidate + junior JD → soften language so it doesn't look overqualified. Never change actual titles.

═══ SUMMARY — ALWAYS BULLETS ═══
Open with a bullet naming the target title + seniority + years of experience. Fold in 1–2 distinctive JD phrases across the bullets. Say who the candidate is — do NOT copy experience bullet lines into the summary. ALWAYS use 4–6 "•" bullet lines — never a paragraph, never prose.

═══ HUMAN VOICE — ANTI-AI-TELL ═══
BAN "utilized" and "leveraged" → use "used", "built", "ran". No two consecutive bullets start with the same verb. Vary structure (metric-first, action-first, tool-first, partner-first). No empty intensifiers ("significantly", "substantially") without a real number. Summary wording ≠ bullet wording. It should read like a skilled professional wrote it, not a tool.
EVERY bullet MUST be 22 words or fewer — target 14–18. One idea per bullet. If a bullet joins two accomplishments with "and" or an em-dash, split it or cut the weaker half. A bullet that would wrap past 2 printed lines is a FAILURE. Do not stack clauses or list 3+ items inside one bullet — name one example or generalize in fewer words.
DISTINCTIVE-WORD DISCIPLINE: The JD repeats certain signature words (e.g. "surfaces", "grounding", "semantic", "tenant"). Do NOT echo any single distinctive JD word more than TWICE across the whole resume — 3+ uses is the clearest fingerprint of AI tailoring to a human reviewer. Use natural, varied domain-standard terms instead. Never lift the JD’s verbatim signature phrases into the summary; paraphrase the concept in your own words. Only use a term where it genuinely fits the work (e.g. do not call standard BI work "grounding" — that is LLM vocabulary).

═══ FORMAT — ATS-SAFE ═══
Single column. "•" bullets. Plain text only — NO tables, columns, or graphics.

HEADER (line 1 of output): Must be exactly — Full Name — Job Title
  Example: Jagadish Reddy Butukuri — Senior Data Engineer
  Name and title on ONE line separated by em-dash (—). NEVER split across two lines.

SECTION HEADERS: Use exactly these labels followed by colon:
  PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TECHNICAL SKILLS:   EDUCATION:

JOB HEADER FORMAT (one line per job):
  Title @ Company | City, State          Month YYYY – Month YYYY
  Example: Senior Data Engineer @ Cargill | Minneapolis, MN          Sep 2023 – Present
  Location (City, State) is REQUIRED — never omit it.
  Date right-aligned on same line. Never split job header across two lines.

TECH LINE: End each job's bullet list with exactly:
  Technologies Used: tool1, tool2, ...
  Never use "Stack:", "Tools:", "Tech:", or any other label.

═══ CRITICAL REMINDERS — CHECK THESE BEFORE YOU TYPE THE FIRST CHARACTER ═══
✗ NEVER: "utilized" or "leveraged" — use "used", "built", "ran"
✗ NEVER: any bullet over 22 words — shorten or split every single one
✗ NEVER: two consecutive experience bullets starting with the same verb
✗ NEVER: meta-language, commentary, or instruction text anywhere in output
✗ NEVER: missing phone/email contact line (must be line 2 of the resume)
✗ NEVER: drop a JD-named hard skill without putting it somewhere (bullet or Skills)
✓ ALWAYS: end every job block with exactly "Technologies Used: tool1, tool2, ..."
✓ ALWAYS: every job header must include "| City, State"
✓ ALWAYS: metrics on ~60–70% of bullets — never 100% (fake), never 0% (weak)
✓ ALWAYS: gap bullets must sound like a seasoned practitioner — specific action + named tool + domain anchor + outcome

═══ FINAL CHECK BEFORE OUTPUT ═══
Remove any meta-text or instruction language from bullets. Restore any altered title/company/date/degree. Confirm domain not relabeled, budget not exceeded, metrics ~60–70%, no "utilized/leveraged", no repeated opening verbs, plain text only. Re-read every experience bullet and shorten any over 22 words; split any bullet that contains two separate accomplishments. Then output the finished resume and nothing else."""


async def tailor_resume(base_resume: str, job_description: str,
                        api_key: str, provider: str, model: str) -> str:
    user_msg = f"""Tailor this resume to the JD. HARD LIMIT: 2 printed pages. Goal: pass ATS ranking and get shortlisted by a human.

Steps:
1. Read the JD — extract hard skills, responsibilities, domain, seniority, tone, and the top 3–5 distinctive phrases.
2. Score every existing bullet 1–5 by JD relevance; keep top bullets per limits (9–11 / 7–8 / 5–6).
3. Cover 80–90% of the meaningful JD content. For missing hard skills, write committed gap bullets anchored to the real company's real domain. Never relabel a company's industry.
4. Keep the candidate's real title in the header; bridge to the JD's title in the summary. Apply the metrics, voice, and seniority rules.
5. Output the final resume only.

=== COMPANY DOMAINS (do not relabel — anchor gap skills to these real domains) ===
Derive company domains from the ORIGINAL RESUME below. Do not relabel any company's actual industry.

=== JOB DESCRIPTION ===
{job_description[:12000]}

=== ORIGINAL RESUME ===
{base_resume}

OUTPUT: complete tailored resume, plain text only, exact format preserved."""

    raw = await chat(
        system=SYSTEM_PROMPT,
        user=user_msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=4096,
    )

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
            max_tokens=4096,
        )

    return _enforce_limits(raw)