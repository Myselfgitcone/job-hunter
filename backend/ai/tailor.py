"""
StackShift tailoring engine.

Replaces the legacy multi-pass engine (kept at ai/tailor_legacy.py.bak).

Pipeline — 4 AI calls:
  1. ANALYZE  (cheap model)  -> target cloud, company, JD tools, present/missing
  2. TAILOR   (main model)   -> the full rewritten resume
  3. QA FIXER (cheap model)  -> Technologies Used, metric de-stacking, junk
                                strip, dropped-cloud restoration
  4. SCORE    (cheap model)  -> ATS / recruiter / hiring-manager gates

Plus 3 deterministic (free) code steps:
  a. target-cloud guard   — a cloud swap only fires if the JD literally names it
  b. dropped-cloud detect — finds jobs whose real base cloud vanished
  c. cloud backstop       — last-resort restore into Technologies Used

CLOUD SWAP IS ALWAYS ON. There is no toggle. When the JD literally names
AWS / Azure / GCP, the two most recent jobs are both converted to that cloud.
When the JD names no cloud, every job keeps its real cloud and the JD's tools
are layered on top.

Output format is job-hunter's plain-text resume format (UPPERCASE section
headers with a colon, "•" bullets) so pdf_gen / docx_gen / ats keep working.
"""
import json
import re

from ai.llm import chat

# Cloud swap is a permanent behaviour, not a user toggle.
CLOUD_SWAP = True


# ═══════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

ANALYZE_SYSTEM = """You are a cloud-infrastructure recruiter analyst. In ONE pass
you read a resume and a job description and return the target cloud, the tools
the JD demands, and which of those tools the resume already has vs is missing.

Return ONLY a compact JSON object, no prose, no markdown fences:
{
  "target_cloud": "GCP" | "AWS" | "Azure" | "Multi" | "None",
  "company": "<the hiring company name from the JD, or '' if not stated>",
  "job_title": "<the clean, short job title exactly as the JD states it>",
  "target_tools": ["<concrete tool/service/framework named in the JD, e.g. 'Terraform', 'Kafka', 'Airflow', 'BigQuery', 'Dataflow'>"],
  "industry": "<the COMPANY's real industry sector, e.g. 'Energy / Oil & Gas', 'Healthcare', 'Financial Services', 'Retail' — NOT the job's role. If unclear, ''>",
  "role_domain": "<the role's technical domain, e.g. 'Data Engineering', 'MDM / Data Architecture'>",
  "metric_style": "<credible quantified results for this role, e.g. 'pipeline throughput, data freshness, cost, uptime'>",
  "present": ["<JD tool already clearly evidenced in the resume>"],
  "missing": ["<JD tool required but absent or weak in the resume>"]
}

Rules:
- target_cloud = a cloud ONLY if the JD text LITERALLY names it (the words "AWS"/
  "Amazon Web Services", "Azure", or "GCP"/"Google Cloud" must actually appear).
  If no cloud is explicitly named, target_cloud MUST be "None". Do NOT infer a
  cloud from the company, domain, or tools — a Spark/Flink/data role that names no
  cloud is "None". Use "Multi" only if two+ are named and weighted equally.
- target_tools: 4–12 concrete, resume-worthy items actually named in the JD (services, IaC, orchestration, streaming, warehouses, frameworks). No soft skills.
- NEVER list years-of-experience, seniority levels, or security clearances (e.g. "13+ years experience", "TS Clearance", "Secret", "Public Trust") as tools — these are NOT injectable and must not appear in target_tools/present/missing.
- present + missing together should cover target_tools: present = evidenced in resume, missing = not. Cap 'missing' at 12."""


TAILOR_SYSTEM = """You are StackShift, a professional resume writer. You rewrite a
resume so it MIRRORS a specific job description — echoing the JD's responsibilities
and required skills in the candidate's own voice, mapped onto their REAL jobs.
The goal is a clean, human, ATS-strong resume that reads like it was hand-written
for this exact role. Follow every rule EXACTLY.

You receive: the original resume, the JD, the detected TARGET CLOUD, and the
MISSING TOOLS list.

================================================================================
OUTPUT FORMAT (plain text — NOT markdown. No #, no **, no code fences.)
================================================================================
Line 1:  `<Candidate Full Name> - <Exact Job Title from the JD>`
         - Use ONLY the clean, short job title exactly as the JD states it
           (e.g. "Analytics Engineer", "Senior Database Developer", "Enterprise
           Database Consultant"). Do NOT append domains, tools, seniority, or extra
           qualifiers ("– Geospatial & ArcGIS", "| Snowflake", "(Senior)"). Just the title.
Line 2:  `<phone> | <email>`   (phone FIRST, then email; NO city/state, no linkedin)

Then these sections, in this exact order. Section headers are UPPERCASE with a
trailing colon on their own line. Every bullet starts with "• ".

SUMMARY:
• 4–6 bullets. Reframe the candidate AS the JD's role. Each bullet echoes the JD's
  core requirements/qualifications in the candidate's words, positioning them as
  the obvious match. Plain, confident, no invented metrics.

SKILLS:
• EXACTLY 4 category lines, each as `• <Dynamic Category Name>: skill, skill, ...`
• Category names derived from the JD's domain (e.g. "Cloud & Infrastructure",
  "Data Pipelines", "Languages", "Practices & Tools"). NEVER "Category 1".
• 4–7 skills per category. List ONLY skills/tools the candidate genuinely has
  (evidenced in the base resume) or that transfer closely from their real stack.
  Do NOT list a specialized platform the base shows ZERO evidence of (e.g. ArcGIS
  Enterprise, SAP HANA, a niche product the candidate never used) as an owned
  skill — that's not defensible. Such tools may only be acknowledged via BRIDGE
  language inside a bullet, never as an owned Skill and never in the title.
  No soft-skill padding.

PROFESSIONAL EXPERIENCE:
For each job, in this exact shape — the job header line is NOT a bullet:
`<Job Title> @ <Company> | <Location> <Month Year> – <Month Year or Present>`
then the LADDER bullets (STYLE below), each starting with "• ",
then ONE final line (not a bullet): `Technologies Used: <comma-separated tools for THAT job>`
EVERY job MUST end with its own Technologies Used line — never omit it, even when
trimming to fit two pages. No job may be left without one.

PROJECTS:
• ONLY if the base resume ALREADY lists real projects. If none, OMIT the whole
  section including its header. NEVER invent a project. If present: keep the real
  ones (up to 3), one polished bullet each, same bullet style.

EDUCATION:
`<Degree and Major>, <University/School>` on its own line (not a bullet).
Keep degree + school from the resume. If none, OMIT the section. Never invent one.

CERTIFICATIONS:
• ONLY if the resume lists them (one per line as `• <Cert>`). If none, OMIT
  entirely — no header. NEVER invent a certification.

================================================================================
BULLET STYLE — plain JD-mirroring (this is the heart of the resume)
================================================================================
Each Experience bullet = take ONE responsibility or skill from the JD and rewrite
it as something the candidate DID at that real job, in plain professional English.

  Shape:  [Action verb] + [the JD duty, reworded] + [tool/skill] + [brief context]
  Length: 18–24 words. One clean past-tense sentence.

DO:
- REWRITE the JD's requirement — never paste the JD sentence verbatim. Change the
  words, convert "you will…" (employer wish) into a past achievement, and anchor it
  to the job's real context.
- Cover the JD's key responsibilities across the bullets; weave in the JD's tools.
- Vary wording so the SAME duty phrased in two jobs never reads identically.

VERB REGISTER — match the JD's seniority (critical):
- Read the verbs the JD uses and mirror that LEVEL. Do not default to builder verbs.
- If the JD is ARCHITECT / LEAD / STRATEGY level (uses define, architect, govern,
  establish, oversee, drive, lead, act as authority, mentor, influence): lead at
  least 2–3 bullets PER JOB with those verbs — Defined, Architected, Governed,
  Established, Led, Directed, Oversaw, Standardized, Mentored — NOT "Built /
  Implemented / Configured / Provisioned" (those read builder-level, too junior).
  e.g. "Engineered entity resolution logic to deduplicate…" →
       "Architected an entity-resolution framework that deduplicated…".
- If the JD is an IC / hands-on engineer role: builder verbs (Built, Developed,
  Implemented, Optimized) are correct — do not force architect verbs.
- Either way, vary the opening verbs so bullets don't read repetitively.

DO NOT:
- Do NOT copy JD lines word-for-word.
- Do NOT append measurement-tool clauses ("as measured in PagerDuty", "tracked via
  CloudWatch", "confirmed via billing dashboards"). Ever.
- Do NOT use vague intensifiers (significantly, substantially, measurably, greatly).
- Do NOT metric-stuff.

================================================================================
METRIC POLICY — numbers are the exception, never invented
================================================================================
- Use a number ONLY when (a) the JD itself states one (mirror it — e.g. JD says
  "100+ pipelines" → "supported over 100 data pipelines"), or (b) the candidate's
  BASE RESUME already contains that number (keep it).
- NEVER invent a percentage, count, dollar, or time figure. If you have no real
  number, end the bullet on a plain qualitative outcome instead.
- At most ONE number per bullet. Expect 0–3 numbers in the WHOLE resume.

================================================================================
"NOT IN THE JD" LOGIC (fill order)
================================================================================
1. Cover every JD responsibility first (reworded onto real jobs).
2. Then top up remaining bullets with the candidate's genuine everyday work
   (documentation, code reviews, monitoring, collaboration, troubleshooting).
3. Invention is the LAST resort and only via BRIDGE WORDS (see Cloud/Bridging).
4. Skills the candidate has but the JD ignores: drop from bullets; a few may stay
   in the Skills section for range.

================================================================================
EXPERIENCE BULLET LADDER (by recency) — hard counts
================================================================================
- Job 1 (most recent): 6–8 · Job 2: 5–6 · Job 3: 4–5 · Job 4: 2–3 · Job 5+: 1–2
Merge if the source has too many; expand with real everyday work if too few.
Keep the ENTIRE resume within 2 pages.

================================================================================
CLOUD & TOOL REFRAMING  (cloud swap is ALWAYS ACTIVE — there is no toggle)
================================================================================
TOOLS/DUTIES (Kafka, Terraform, Airflow, dbt, ETL, governance, etc.): mirror the
JD's tools and responsibilities across ALL jobs, ALWAYS.

CLOUD PROVIDER swap (AWS ↔ Azure ↔ GCP and their native services):
Cross-cloud equivalence: EC2↔Azure VM↔Compute Engine · Lambda↔Functions↔Cloud
Functions · S3↔Blob↔Cloud Storage · Redshift↔Synapse↔BigQuery · Glue↔ADF↔Dataflow ·
EMR↔HDInsight↔Dataproc · EKS↔AKS↔GKE · Kinesis↔Event Hubs↔Pub/Sub · RDS↔Azure
SQL↔Cloud SQL · DynamoDB↔Cosmos DB↔Firestore/Bigtable.
Cloud-neutral tools (Terraform, Kafka, Airflow, Spark, dbt) are NEVER translated.

- IF a TARGET CLOUD is detected (the JD literally names AWS, Azure, or GCP):
  BOTH Job 1 AND Job 2 (the two most recent) MUST be fully converted to the TARGET
  cloud — this is mandatory for EACH of the two, not just Job 1.
  * For EACH of Job 1 and Job 2: take whatever cloud that job currently uses (even
    if it differs from the other job) and rewrite ALL its cloud provider names and
    native services into the target cloud's equivalents. Its Technologies Used line
    and bullets must show the TARGET cloud, with NO leftover mention of the old one.
  * Example — target = AWS: if Job 2 was on Azure, convert it — Azure Data Factory
    → AWS Glue, Synapse → Redshift, ADLS → S3, Event Hubs → Kinesis, Azure SQL →
    RDS, Purview → Lake Formation. After conversion Job 2 reads as native AWS.
  * Do NOT leave Job 2 on its original cloud just because it already had a real one.
    Both of the top two jobs end on the SAME target cloud.
  Leave Job 3, 4, 5… on their real native clouds for authenticity. If there is only
  ONE job, convert just Job 1.
- IF NO target cloud is detected (e.g. a Snowflake/dbt analytics role, or an
  Oracle/SQL-Server role, that names no AWS/Azure/GCP):
  * Do NOT swap or remove any cloud. KEEP the candidate's real cloud/platform
    tech from the base resume in EVERY job (AWS, Azure, GCP, Databricks, Spark…).
  * MANDATORY: each job's `Technologies Used:` line MUST still contain the real
    cloud/platform that job used in the base resume. If the base shows AWS (S3,
    EMR, Glue) at a job, AWS MUST appear in that job's Technologies Used — you may
    ADD the JD's tools (e.g. Snowflake, dbt), but you may NEVER DROP the real cloud.
  * BLEND the JD's tools ON TOP of the real stack — never replace it. Show BOTH
    the genuine platform AND the JD tool together. Example (Snowflake/dbt JD, no
    cloud named): "On AWS and Databricks, modeled MART-layer data products in dbt
    and Snowflake…" → real AWS/Databricks kept + Snowflake/dbt added.
  * A JD not mentioning a cloud is NOT permission to hide the candidate's real
    cloud. Layer, never erase.

BRIDGING (honest stretch): when the JD wants hands-on experience the candidate's
base resume does NOT show, do not claim it as a standalone past job duty. Anchor it
to the REAL work using bridge language — "using SQL/PL-SQL patterns transferable to
Oracle package development", "applying stored-procedure logic analogous to SSIS",
"integrating spatial datasets using patterns transferable to ArcGIS geodatabases".
The most recent job may lean more direct; older jobs stay bridged. A bridged tool
appears ONLY in bullet bridge phrasing — NEVER in the headline title and NEVER as
an owned entry in the Skills section.

================================================================================
GLOBAL RULES
================================================================================
- Preserve real employers, job titles, dates, education, and certifications.
- Do NOT invent employers, titles, dates, degrees, or certifications. (Projects MAY be invented.)
- YEARS OF EXPERIENCE: state exactly what the base resume supports. NEVER inflate
  to match the JD. If the resume shows 5+ years and the JD asks for 13+, write
  "5+ years" — do not bump it. Ignore any years/seniority value in the missing-tools list.
- SECURITY CLEARANCE: NEVER claim or imply a clearance (Top Secret, TS, TS/SCI,
  Secret, Public Trust, "TS-clearable", "clearance-eligible") unless the BASE
  resume explicitly states it. If the JD requires one and the resume lacks it,
  OMIT any clearance mention entirely. Same for citizenship claims.
- SCOPE vs TENURE: keep the number of major initiatives realistic for the role's
  duration and level. Do NOT cram 8 architect-level initiatives into a <2-year
  IC "Engineer" role, and do NOT imply Architect scope under an IC title.
- List each employer/role ONCE. Never output a duplicate job entry or a stub like
  "(See above)" / "consolidated under…". If the same company appears twice, merge
  into a single entry.
- If a field (location, dates) is unknown, OMIT it entirely. Never write filler
  like "Location Not Listed", "N/A", or "Not Specified".
- Output plain text only, in the format above. No markdown headers, no asterisks,
  no horizontal rules, no commentary, no code fences."""


QA_FIXER_SYSTEM = """You are a resume QA fixer. You receive a finished resume and
fix a fixed checklist of issues, then return the FULL corrected resume. This is a
surgical pass — do NOT rewrite good content.

HARD CONSTRAINTS (never violate):
- Keep EVERY bullet. Do NOT delete, merge, or split bullets. The bullet count per
  job must stay the same.
- Do NOT change names, job titles, companies, dates, education, or the section order.
- Do NOT add new numbers or new claims.
- Keep the exact same plain-text format: UPPERCASE section headers with a colon,
  "• " bullets, job headers as "Title @ Company | Location Dates". No markdown.

FIX THIS CHECKLIST:
1. TECHNOLOGIES USED: every job under PROFESSIONAL EXPERIENCE MUST end with a
   `Technologies Used: ...` line. If a job is missing one, ADD it — build the
   list from the tools already named in THAT job's own bullets (you may include a
   couple of closely-related tools from the resume's SKILLS section). Never remove
   an existing Technologies Used line.
2. NUMBERS: at most ONE number per bullet. If a bullet has two or more, keep the
   single strongest and reword the others as plain words. Do not invent numbers.
3. JUNK: delete any leaked/internal instruction text, placeholder text
   ("Location Not Listed", "N/A", "See above", "Fabricated…"), bulletless duplicate
   job stubs, stray horizontal rules (---), and any leftover markdown (#, **).
4. EMPTY SECTIONS: delete any section header that has nothing under it.
5. CLOUD RESTORATION (only if a note below names jobs + clouds): for each named
   job, WEAVE that cloud naturally into 1–2 of its existing bullets AND into its
   Technologies Used line, sitting alongside the tools already there (e.g. "on AWS
   and Databricks, built dbt models…"). Do NOT add or remove bullets — only reword
   existing ones. Do NOT touch jobs not named.

Output ONLY the corrected resume in the same plain-text format — no commentary,
no code fences."""


SCORE_SYSTEM = """You are a strict, experienced resume reviewer. Score a tailored
resume against its job description on THREE gates. Be critical and realistic —
most resumes score 70–85; reserve 90+ for genuinely excellent fit. Do NOT inflate.

Return ONLY compact JSON, no prose:
{
  "ats": {"score": <0-100>, "note": "<one short reason>"},
  "recruiter": {"score": <0-100>, "note": "<one short reason>"},
  "hiring_manager": {"score": <0-100>, "note": "<one short reason>"},
  "overall": <0-100>,
  "top_fixes": ["<specific fix 1>", "<specific fix 2>", "<specific fix 3>"]
}

Gate definitions:
- ats: keyword & tool coverage vs the JD, parseable single-column format. Penalize missing JD keywords.
- recruiter: 6-second scan — does the title match, does the summary show fit fast, is it clean and skimmable.
- hiring_manager: believability — no invented metrics, no inflated years/clearance, claims are defensible, bridged honestly.
overall = holistic, roughly the weakest-gate-weighted average.
top_fixes = the 3 highest-impact concrete improvements (empty list if truly none)."""


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_prompt(resume_text: str, jd_text: str) -> str:
    return (
        f"RESUME:\n{resume_text}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        "Analyze and return the single JSON object."
    )


def tailor_prompt(resume_text: str, jd_text: str, context: dict,
                  missing_tools: list, profile_skills: list | None = None) -> str:
    tools = ", ".join(missing_tools) if missing_tools else "(none detected)"
    extra = ""
    if profile_skills:
        extra = ("\nCANDIDATE'S OWN DECLARED SKILLS (treat as genuinely held):\n  "
                 + ", ".join(profile_skills) + "\n")
    return (
        f"TARGET CLOUD: {context.get('target_cloud', 'None')}\n"
        f"INDUSTRY:     {context.get('industry', '')}\n\n"
        "CLOUD SWAP: ALWAYS ON — if a target cloud is named above, convert BOTH "
        "Job 1 and Job 2 to it. If it is 'None', keep every job's real cloud and "
        "layer the JD's tools on top.\n\n"
        f"JD TOOLS TO MIRROR ACROSS ALL JOBS:\n  {tools}\n{extra}\n"
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"ORIGINAL RESUME:\n{resume_text}\n\n"
        "Produce the fully tailored resume in the plain-text format now: plain "
        "JD-mirroring bullets (18–24 words, no invented numbers, no 'measured via' "
        "clauses), the exact bullet ladder, and the cloud rule (provider swap in "
        "Job 1 & 2 when a target cloud exists; tools mirrored in all jobs)."
    )


def qa_fixer_prompt(tailored: str, cloud_directive: str = "") -> str:
    extra = f"\n\n{cloud_directive}" if cloud_directive else ""
    return (
        "Fix the checklist issues in this resume and return the full corrected "
        "text. Keep every bullet." + extra + "\n\n" + tailored
    )


def score_prompt(jd_text: str, tailored: str) -> str:
    return (
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"TAILORED RESUME:\n{tailored}\n\n"
        "Score the three gates and return the JSON."
    )


# ═══════════════════════════════════════════════════════════════════════════
# DETERMINISTIC GUARDS (free — no AI call)
# ═══════════════════════════════════════════════════════════════════════════

_CLOUD_SIG = {
    "AWS": ("aws", "amazon web", "redshift", "cloudformation", " emr", " s3", "ec2", "lambda"),
    "Azure": ("azure", "synapse", "adls", "data factory", "event hubs"),
    "GCP": ("gcp", "google cloud", "bigquery", "dataproc", "dataflow", "pub/sub"),
}

# The JD must literally contain one of these for that cloud to count as a target.
_CLOUD_TERMS = {
    "AWS": ("aws", "amazon web"),
    "Azure": ("azure",),
    "GCP": ("gcp", "google cloud"),
}

_JOB_HDR_RE = re.compile(r"@\s*([A-Za-z0-9&.\-]+)")
_BULLET_PREFIXES = ("• ", "- ", "* ", "•")


def _detect_cloud(text: str):
    """First cloud whose signature appears in the text, else None."""
    tl = text.lower()
    for cloud, sigs in _CLOUD_SIG.items():
        if any(s in tl for s in sigs):
            return cloud
    return None


def _is_job_header_line(ln: str) -> bool:
    return (bool(_JOB_HDR_RE.search(ln))
            and bool(re.search(r"@\s*[A-Z]", ln))
            and not ln.lstrip().startswith(_BULLET_PREFIXES))


def _split_jobs(text: str):
    """Yield (company_first_word_lower, body) per '@ Company' job header."""
    out, company, buf = [], None, []
    for ln in text.splitlines():
        if _is_job_header_line(ln):
            if company is not None:
                out.append((company, "\n".join(buf)))
            company = _JOB_HDR_RE.search(ln).group(1).strip().lower()
            buf = [ln]
        elif company is not None:
            buf.append(ln)
    if company is not None:
        out.append((company, "\n".join(buf)))
    return out


def _missing_native_clouds(tailored: str, base_resume: str, target: str) -> dict:
    """Return {company: real_cloud} for jobs that were NOT swapped but whose real
    base cloud is missing from the tailored output (so it needs restoring).

    Cloud swap is always on, so when a real target cloud exists the top two jobs
    are legitimately converted and are skipped here.
    """
    base_cloud = {c: _detect_cloud(b) for c, b in _split_jobs(base_resume)}
    swaps = target in ("AWS", "Azure", "GCP")
    missing = {}
    for idx, (company, body) in enumerate(_split_jobs(tailored), start=1):
        real = base_cloud.get(company)
        if not real or (swaps and idx <= 2):
            continue
        low = body.lower()
        if real.lower() in low or any(s in low for s in _CLOUD_SIG[real]):
            continue
        missing[company] = real
    return missing


def _cloud_directive(missing: dict) -> str:
    if not missing:
        return ""
    parts = "; ".join(f"{c.title()} used {cl}" for c, cl in missing.items())
    return ("CLOUD RESTORATION NOTE — these jobs used a real cloud the draft dropped; "
            "weave it into their bullets and Technologies Used per rule 5: " + parts + ".")


def _backstop_native_clouds(tailored: str, missing: dict) -> str:
    """Last resort: if a job still lacks its real cloud after the QA fixer, at
    least ensure it appears in that job's Technologies Used line."""
    if not missing:
        return tailored
    lines = tailored.splitlines()
    company = None
    for i, ln in enumerate(lines):
        if _is_job_header_line(ln):
            company = _JOB_HDR_RE.search(ln).group(1).strip().lower()
            continue
        if company in missing and re.match(r"\s*\*{0,2}technologies used", ln, re.I):
            real = missing[company]
            low = ln.lower()
            if real.lower() not in low and not any(s in low for s in _CLOUD_SIG[real]):
                lines[i] = ln.rstrip() + f", {real}"
    return "\n".join(lines)


def _bullet_count(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.lstrip().startswith(_BULLET_PREFIXES))


_KNOWN_SECTIONS = (
    "SUMMARY", "PROFESSIONAL SUMMARY", "SKILLS", "TECHNICAL SKILLS",
    "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE", "EXPERIENCE",
    "PROJECTS", "EDUCATION", "CERTIFICATIONS",
)


def _normalize_format(text: str) -> str:
    """Deterministic format guard. The model is told to emit plain text, but it
    occasionally slips into markdown. Convert whatever it produced into the
    format pdf_gen / docx_gen / resume_lint expect."""
    out = []
    for raw in text.splitlines():
        s = raw.rstrip().strip()
        if not s:
            out.append("")
            continue
        if s.startswith("```") or re.fullmatch(r"-{3,}|_{3,}|\*{3,}", s):
            continue  # code fence / horizontal rule
        # "## Professional Experience" / "# Name" -> strip the hashes
        s = re.sub(r"^#{1,6}\s*", "", s)
        # "- bullet" / "* bullet" -> "• bullet"
        if re.match(r"^[-*]\s+", s):
            s = "• " + s[2:].lstrip()
        # drop bold/italic markers anywhere
        s = s.replace("**", "").replace("__", "")
        # section headers: make them UPPERCASE with a trailing colon
        bare = s.rstrip(":").strip()
        if not s.startswith("•") and bare.upper() in _KNOWN_SECTIONS:
            s = bare.upper() + ":"
        out.append(s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _is_section_hdr(s: str) -> bool:
    s = s.strip()
    if not s or s.startswith(_BULLET_PREFIXES) or not s.endswith(":") or len(s) <= 4:
        return False
    bare = s.rstrip(":")
    return bare == bare.upper()


def _strip_empty_sections(text: str) -> str:
    """Drop any section header immediately followed by another header or EOF."""
    lines = text.splitlines()
    keep = [True] * len(lines)
    for i, ln in enumerate(lines):
        if not _is_section_hdr(ln):
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or _is_section_hdr(lines[j]):
            keep[i] = False
    kept = "\n".join(l for l, k in zip(lines, keep) if k)
    return re.sub(r"\n{3,}", "\n\n", kept)


def _loads_loose(text: str) -> dict:
    """Parse JSON from a model reply that may be fenced or prose-wrapped."""
    if not text:
        return {}
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()).strip()
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return {}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

async def tailor_resume(base_resume: str, job_description: str,
                        api_key: str, provider: str, model: str,
                        profile_skills: list[str] | None = None,
                        secondary_model: str = "",
                        user_job_roles: list[str] | None = None,
                        profile_projects: list[dict] | None = None,
                        company: str = "",
                        keys=None) -> tuple[str, dict]:
    """Tailor `base_resume` to `job_description`.

    Returns (tailored_text, review) where review has the keys main.py expects:
    needs_review (bool), reasons (list[str]), notes (list[str]).

    `user_job_roles` and `profile_projects` are accepted for call-site
    compatibility; the StackShift engine derives role register and project
    handling from the JD and the base resume instead.
    """
    notes: list[str] = []
    reasons: list[str] = []

    # JD may arrive as (double-)encoded HTML from some ATS feeds.
    try:
        from resume_lint import clean_jd_html
        job_description = clean_jd_html(job_description)
    except Exception:  # noqa: BLE001 — lint module optional for this path
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

    # ── 1. ANALYZE (cheap) ────────────────────────────────────────────────
    try:
        raw = await chat(ANALYZE_SYSTEM, analyze_prompt(base_resume, job_description),
                         max_tokens=1500, pass_name="analyze", **cheap_kw)
        context = _loads_loose(raw)
    except Exception as exc:  # noqa: BLE001 — retry once on the main model
        notes.append(f"analyze: cheap model failed ({exc}); retried on main model")
        try:
            raw = await chat(ANALYZE_SYSTEM, analyze_prompt(base_resume, job_description),
                             max_tokens=1500, pass_name="analyze", **main_kw)
            context = _loads_loose(raw)
        except Exception as exc2:  # noqa: BLE001
            notes.append(f"analyze: failed ({exc2}); continuing with empty context")
            context = {}

    if not context:
        context = {"target_cloud": "None", "target_tools": [], "industry": "",
                   "present": [], "missing": []}

    # Guard (a): a cloud swap only fires when the JD LITERALLY names that cloud.
    # Kills phantom swaps (e.g. GCP invented for a cloud-agnostic JD).
    tc = (context.get("target_cloud") or "").strip()
    jd_low = job_description.lower()
    if tc in _CLOUD_TERMS and not any(t in jd_low for t in _CLOUD_TERMS[tc]):
        notes.append(f"cloud guard: JD never names {tc} — target_cloud forced to None")
        context["target_cloud"] = "None"

    missing = context.get("missing") or []
    print(f"[TAILOR] target_cloud={context.get('target_cloud')!r} "
          f"missing_tools={len(missing)} company={company or context.get('company', '')!r}")

    # ── 2. TAILOR (main model) ────────────────────────────────────────────
    tailored = (await chat(
        TAILOR_SYSTEM,
        tailor_prompt(base_resume, job_description, context, missing, profile_skills),
        max_tokens=8000, pass_name="tailor", **main_kw,
    )).strip()
    tailored = _normalize_format(tailored)

    # Guard (b): which non-swapped jobs lost their real base cloud?
    target = context.get("target_cloud", "None")
    missing_clouds = _missing_native_clouds(tailored, base_resume, target)
    if missing_clouds:
        notes.append("cloud restore requested: "
                     + ", ".join(f"{c}={cl}" for c, cl in missing_clouds.items()))

    # ── 3. QA FIXER (cheap) ───────────────────────────────────────────────
    try:
        fixed = (await chat(
            QA_FIXER_SYSTEM,
            qa_fixer_prompt(tailored, _cloud_directive(missing_clouds)),
            max_tokens=8000, pass_name="qa_fix", **cheap_kw,
        )).strip()
        fixed = _normalize_format(fixed)
        if (fixed.count("\n") > 5
                and len(fixed) > 0.6 * len(tailored)
                and _bullet_count(fixed) == _bullet_count(tailored)):
            tailored = fixed
        else:
            notes.append("qa fixer output rejected (bullet count or length changed)")
    except Exception as exc:  # noqa: BLE001 — best effort
        notes.append(f"qa fixer skipped ({exc})")

    # Guard (c): still missing after the fixer -> force into Technologies Used.
    still_missing = _missing_native_clouds(tailored, base_resume, target)
    if still_missing:
        notes.append("cloud backstop applied: "
                     + ", ".join(f"{c}={cl}" for c, cl in still_missing.items()))
        tailored = _backstop_native_clouds(tailored, still_missing)

    tailored = _strip_empty_sections(tailored).strip()

    # ── 4. SCORE (cheap) ──────────────────────────────────────────────────
    scores: dict = {}
    try:
        raw = await chat(SCORE_SYSTEM, score_prompt(job_description, tailored),
                         max_tokens=1200, pass_name="score", **cheap_kw)
        scores = _loads_loose(raw) or {}
    except Exception as exc:  # noqa: BLE001 — scoring is best effort
        notes.append(f"score skipped ({exc})")

    overall = scores.get("overall")
    if isinstance(overall, (int, float)):
        notes.append(
            f"score: overall {overall} "
            f"(ats {(scores.get('ats') or {}).get('score')}, "
            f"recruiter {(scores.get('recruiter') or {}).get('score')}, "
            f"hiring_manager {(scores.get('hiring_manager') or {}).get('score')})"
        )
        if overall < 80:
            reasons.extend(str(f) for f in (scores.get("top_fixes") or [])[:3])

    review = {
        "needs_review": bool(reasons),
        "reasons": reasons,
        "notes": notes,
        "scores": scores,
        "context": context,
    }
    return tailored, review
