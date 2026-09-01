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
  "missing": ["<JD tool required but absent or weak in the resume>"],
  "baseline_missing": ["<subset of missing that are UNIVERSAL BASELINE competencies>"]
}

Rules:
- target_cloud = a cloud ONLY if the JD text LITERALLY names it (the words "AWS"/
  "Amazon Web Services", "Azure", or "GCP"/"Google Cloud" must actually appear).
  If no cloud is explicitly named, target_cloud MUST be "None". Do NOT infer a
  cloud from the company, domain, or tools — a Spark/Flink/data role that names no
  cloud is "None". Use "Multi" only if two+ are named and weighted equally.
- target_tools: 12–24 concrete, resume-worthy skills the JD emphasises — tools,
  services, frameworks AND named technical competencies (e.g. "dimensional
  modeling", "semantic layer design", "data governance", "query optimization",
  "A/B experimentation", "data warehousing"). This is the checklist the resume's
  keyword coverage is scored against, so be thorough: include every hard skill a
  recruiter or ATS would scan for, not just brand-name products. Still NO soft
  skills (communication, collaboration, mentoring, stakeholder management).
  A universal competency the JD EXPLICITLY requires (an OS, CI/CD, on-call,
  testing, scripting, monitoring class of demand) always earns a slot — never
  crowd one out with a tenth product name.
- NEVER list years-of-experience, seniority levels, or security clearances (e.g. "13+ years experience", "TS Clearance", "Secret", "Public Trust") as tools — these are NOT injectable and must not appear in target_tools/present/missing.
- present + missing together should cover target_tools: present = evidenced in resume, missing = not.
- baseline_missing: from the missing list, pick ONLY the universal expected
  competencies — practices any engineer at this level genuinely performs
  regardless of employer or stack (the CI/CD, version-control, code-review,
  testing, monitoring, on-call, documentation, migration, tuning class of
  work). Judge each item yourself against that test: "would every competent
  engineer in this role have really done this, even if their resume never
  wrote it down?" Yes → baseline_missing. A product, platform, language, or
  domain tool the candidate may simply not know (Salesforce, Ruby, Snowflake,
  a vendor suite) is NEVER baseline, no matter how essential the JD calls it."""


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
Line 1:  `<Candidate Full Name> — <Exact Job Title from the JD>`
         - Separate the name and the title with an EM-DASH (—). Never a hyphen,
           en-dash, pipe, or colon — those are reserved for posting suffixes.
         - Use ONLY the clean, short job title exactly as the JD states it
           (e.g. "Analytics Engineer", "Senior Database Developer", "Enterprise
           Database Consultant"). Do NOT append domains, tools, seniority, or extra
           qualifiers ("– Geospatial & ArcGIS", "| Snowflake", "(Senior)"). Just the title.
         - Postings often pad the title ("Data Migration Engineer – SQL Server to
           Snowflake & Matillion"). Take only the part before the suffix:
           "Data Migration Engineer".
Line 2:  `<phone> | <email>`   (phone FIRST, then email; NO city/state, no linkedin)

Then these sections, in this exact order. Section headers are UPPERCASE with a
trailing colon on their own line. Every bullet starts with "• ".

SUMMARY:
• 4–6 bullets. Reframe the candidate AS the JD's role. Each bullet echoes the JD's
  core requirements/qualifications in the candidate's words, positioning them as
  the obvious match. Plain, confident, no invented metrics.

SKILLS:
• 5–7 category lines, each as `• <Dynamic Category Name>: skill, skill, ...`
  Choose the number that fits: use MORE categories (6–7) for a broad
  data/engineering skillset so each line stays tight and coherent; use fewer
  (5) only for a genuinely narrow role. Do NOT cram everything into 4 broad
  buckets — that overloads lines and drops whole domains.
• Category names come from the JD's domains and the candidate's real strengths,
  e.g. "Data Warehousing & Modeling", "Languages & Scripting", "ETL &
  Orchestration", "Business Intelligence & Analytics", "Cloud Platforms",
  "DevOps & Infrastructure", "Data Quality & Governance", "AI / ML Engineering".
  NEVER "Category 1". SPLIT any category that would exceed the item cap — e.g.
  break a bloated "Cloud, Linux & DevOps" into "Cloud Platforms" and "DevOps &
  Infrastructure" rather than piling 12 tools on one line.
• If the JD (or the candidate's real stack) involves a domain that deserves its
  own line, GIVE IT ONE. In particular, when the JD mentions business
  intelligence, reporting, dashboards, or analytics AND the candidate has BI
  tools (Power BI, Tableau, Looker, etc.), include a dedicated "Business
  Intelligence & Analytics" category — do not bury BI inside another line.
• 5–7 skills per category; hard ceiling 8. List ONLY skills/tools the candidate
  genuinely has (evidenced in the base resume) or that transfer closely from
  their real stack. Do NOT list a specialized platform the base shows ZERO
  evidence of (e.g. ArcGIS Enterprise, SAP HANA, a niche product never used) as
  an owned skill — that's not defensible; acknowledge such tools only via BRIDGE
  language in a bullet, never as an owned Skill and never in the title. No
  soft-skill padding.
• KEEP EVERY TOOL THAT APPEARS IN BOTH THE BASE RESUME AND THE JD. Those shared
  tools are your real, defensible keywords — never drop one to hit a count.
  With 5–7 categories there is room for all of them; that's the point.
• Never repeat the same tool across categories, and never list two names for one
  thing (e.g. "Data Warehouse" and "Data Warehousing" — pick one).
• TOTAL BUDGET: at most 30 skills across ALL categories. Priority order:
  (1) tools in BOTH the base resume and the JD, (2) JD-required tools,
  (3) closely-transferable JD-preferred tools. Drop peripheral "a plus" /
  mentioned-once items — a lean, defensible list beats a stuffed one.
• EVERY SKILL EARNS A BULLET: each tool you list in SKILLS must appear in at
  least one experience bullet, in the job where that work most plausibly
  happened. A skill with zero bullets behind it dies in the first screening
  question. One bullet may evidence up to THREE related tools (e.g. one
  observability bullet covering Datadog, Grafana, and alerting) — prefer that
  over three thin single-tool bullets. If a skill cannot earn a bullet within
  the per-job caps (see ladder), LEAVE IT OUT of SKILLS entirely.

PROFESSIONAL EXPERIENCE:
For each job, in this exact shape — the job header line is NOT a bullet:
`<Job Title> @ <Company> | <Location> <Month Year> – <Month Year or Present>`
then the LADDER bullets (STYLE below), each starting with "• ",
then ONE final line (not a bullet): `Technologies Used: <comma-separated tools for THAT job>`
EVERY job MUST end with its own Technologies Used line — never omit it, even when
trimming for length. No job may be left without one.

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
  Length: VARIED — one clean past-tense sentence, but bullet lengths must differ.
    Most bullets land 15–24 words. Every job with 4+ bullets MUST also contain at
    least one SHORT bullet (8–12 words — e.g. "Mentored two junior engineers on
    Spark tuning and code review.") and MAY run one longer bullet up to 30 words.
    Never write three consecutive bullets within ±2 words of the same length — a
    uniform wall of same-length bullets is the strongest machine-written tell.

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

HOW A BULLET MUST END (it is checked by an automated truncation detector):
- Never end on a bare "-ing" word: "...using adaptive query execution and
  caching." reads as cut off. Finish the thought — "...and caching strategies."
- If you close with a ", <verb>ing ..." clause, give it at least THREE words
  after the gerund. "...orchestration, improving pipeline reliability." trips
  the detector; "...orchestration, improving reliability across production
  workloads." does not.
- Never end on a preposition or connective (of, for, with, and, to, in, across).
- Every bullet ends on a complete noun phrase and reads as a finished sentence.

IMPACT LADDER — a few standout bullets per job, most are scope:
- Real strong resumes do NOT make every bullet a heroic achievement (that reads
  fake). Instead, the FIRST few bullets of each job lead with impact/ownership,
  and the rest describe genuine scope of work.
- How many lead with impact, by recency: Job 1 (most recent) → the top 2–3;
  Job 2 → top 2; Job 3 and older → top 1. The remaining bullets in each job are
  plain scope/responsibility bullets.
- An IMPACT bullet = ownership verb + WHAT IT ACHIEVED or ENABLED, e.g.
  "Built pipelines" → "Architected the ingestion platform that gave six business
  units self-service analytics". Close on a REAL outcome — a real number if the
  base resume/JD has one, otherwise a real qualitative result ("…eliminating
  recurring nightly batch failures"). NEVER invent a number to manufacture impact.
- Put the strongest impact bullets at the TOP of the most recent job — that's
  what a recruiter reads first.

LEAD WITH THE JD'S OWN VOCABULARY (recruiter-scan rule):
- Identify the JD's DOMINANT technology/discipline — the one it names most
  often (e.g. a JD that says "Informatica PowerCenter" ten times and never
  says AWS). The first TWO bullets of EVERY job must speak that vocabulary.
- A brand or platform the JD NEVER mentions must not open a bullet in the top
  two of any job. Say the work in the JD's terms and keep the unrelated
  product name later in the sentence, or in Technologies Used.
  BAD  (JD is Informatica/ETL): "Architected pipelines on AWS and Databricks…"
  GOOD: "Designed and delivered enterprise ETL workflows — source-to-target
         mappings, transformation logic, and performance tuning — across
         cloud and on-premise platforms."
- Where the candidate's REAL experience with the dominant tool sits in an
  older job, keep it there truthfully, but make sure the SUMMARY and that
  job's FIRST bullet both carry it. Never move a tool into a job that did
  not use it.

NEVER USE THESE (they read robotic / templated) — rephrase with a real verb:
- "Responsible for", "Tasked with", "Utilized", "Leveraged", "Spearheaded",
  "Worked on", "Helped with", "Involved in", "In charge of".
NO DASHES (the most recognizable AI-writing tell) — never put an em or en dash
(— or –) inside a bullet or summary line:
- No dash-wrapped asides: "on AWS — S3, Athena — with…" → "on AWS (S3, Athena) with…"
- No dash-before-payoff: "…lineage tracking — to catch anomalies" →
  "…lineage tracking to catch anomalies" or use a comma.
- Use a comma, colon, parentheses, "including", or "such as" instead.
- Dashes exist ONLY in the headline (Name — Title) and job-header date ranges.
Also avoid flowery editorial phrases no human writes on a resume: "with a
pragmatic eye toward", "with an emphasis on excellence", "seamlessly",
"cutting-edge", "robust and scalable" as a pair. Say the plain thing.
VARY THE WRITING so it reads human, not machine-generated:
- No two bullets in the SAME job may start with the same verb.
- Vary sentence shape across bullets — don't run the identical
  "[Verb] [noun] using [tool] to [result]" template down the whole job.
- Mix bullet LENGTHS per the Length rule above — short bullets are normal in
  real resumes; do not pad a naturally short point out to match its neighbors.
- Not every bullet needs a tool name. 1–2 bullets per job may be a plain duty
  or collaboration line with no technology in it at all.

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
A job may EXCEED its count when needed to give every listed Skill a supporting
bullet (see EVERY SKILL EARNS A BULLET), but NEVER past these hard caps:
Job 1 ≤ 12 · Job 2 ≤ 8 · Job 3 ≤ 6 · Job 4+ ≤ 3. A skill that cannot fit
within the caps is dropped from SKILLS, not crammed in. Aim for 2 pages;
running onto a 3rd page is acceptable when coverage needs it — never past 3.

================================================================================
CLOUD & TOOL REFRAMING  (cloud swap is ALWAYS ACTIVE — there is no toggle)
================================================================================
TOOLS/DUTIES (Kafka, Terraform, Airflow, dbt, ETL, governance, etc.): the tools
you DO choose to cover (see COVERAGE STRATEGY below) should be mirrored across the
relevant jobs — but you do NOT cover every tool the JD names; see that section.

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
- IF the TARGET CLOUD is "Multi" (the JD names several clouds with no clear
  primary), treat it exactly like "None" below — do NOT swap anything. Keep every
  job on its real cloud and layer the JD's tools on top. Swapping to a guessed
  "main" cloud when the JD weights several equally is worse than not swapping.
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
COVERAGE STRATEGY — cover everything real; leave out only what you'd have to fake
================================================================================
The goal is HONEST coverage, not a target percentage.

- COVER EVERY tool the candidate GENUINELY HAS or that TRANSFERS CLOSELY from
  their real stack. Never drop one of these — it is free, honest, defensible
  coverage. Use the JD's own wording for it so it matches (if the resume shows
  "RAG pipelines" and the JD says "Retrieval-Augmented Generation", write it so
  BOTH read; if the candidate uses containers and the JD says "Docker", name
  Docker). When you cover a skill through a sibling or framework name, ALSO
  write the JD's literal term at least once — Rails work IS Ruby, so a JD that
  says "Ruby" gets the words "Ruby on Rails", not just "Rails"; an ATS scans
  for the JD's exact token and a synonym scores zero. A candidate who truly matches the whole JD SHOULD score near-complete
  coverage — that is honest, not stuffing.

- ALSO COVER these three classes — they are honest and candidates lose easy,
  legitimate coverage when they are left out:
  * UNIVERSAL BASELINE skills the JD names that ANY engineer at this level
    genuinely does, even if the base resume never lists them as a "tool":
    Linux, high availability, on-call rotation / incident response, Agile,
    CI/CD, code review, monitoring/observability, performance tuning, data
    migration. If the JD asks for it and it's normal for the role, weave it in
    (e.g. the JD wants "high availability" → phrase existing SLA/uptime work as
    "high-availability"; "on-call rotation" → the candidate has supported
    production on call; "data migration" → their SQL Server→Snowflake move IS a
    migration). These are expected competencies, not fabrication.
  * CATEGORY-EQUIVALENT tools: when the JD names a specific product in a category
    the candidate ALREADY works in, include it. JD wants Splunk and the candidate
    uses Datadog/Grafana (same observability category) → include Splunk. JD wants
    a specific message queue and they use Kafka → fine. Same product family = fair
    to claim.
  * COMMON AI-DEV tools the candidate plausibly uses (GitHub Copilot) when the JD
    lists them — include. (Genuinely niche ones they don't use — Windsurf, a
    proprietary IDE — stay out.)

- The ONLY tools you leave out are ones the candidate does NOT have and cannot
  honestly bridge. For those:
  * Bridge at most 2–3 of the most important gaps (honest "transferable / analogous
    to" language, per BRIDGING above).
  * OMIT the rest — the low-importance, zero-adjacency ones (a niche proprietary
    product, a language they never touched that appears once as "a plus"). These
    simply do not appear, and show up honestly as gaps.

Judge a gap's importance from the JD: labels if present ("required" vs "preferred
/ a plus"), else frequency, whether it's in the title / summary / first
responsibilities vs buried in a list, wording ("strong / must / hands-on" = core;
"exposure to / a plus / or similar / or equivalent" = peripheral; in an
"X, Y, or equivalent" group one member covers the group), and role-centrality.

WHERE THE "DON'T LOOK 100% PERFECT" RULE APPLIES: it is about not FAKING or
bridging every foreign tool — never about dropping tools the candidate really
has. If the honest result covers 75% because the candidate lacks several JD
tools, that is correct. If it covers 95% because they genuinely match, that is
also correct. Do not manufacture gaps by omitting real skills.

================================================================================
GLOBAL RULES
================================================================================
- Preserve real employers, dates, locations, education, and certifications EXACTLY.
- JOB TITLES — EVERY job in PROFESSIONAL EXPERIENCE keeps its EXACT base-resume
  title, unchanged, on every application. Employment-history titles are verified
  in background checks; a mismatch rescinds offers. The JD's role belongs ONLY in
  the headline (Line 1) — never in any experience entry's title. Company,
  location, and dates never change either.
- Do NOT invent employers, dates, degrees, or certifications, and never fabricate
  or alter any experience title. (Projects MAY be invented.)
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
5. TRUNCATED-LOOKING ENDINGS: an automated detector flags any experience bullet
   that ends on a bare "-ing" word ("...and caching."), on a preposition or
   connective, or on a short ", <verb>ing <one or two words>." tail with no
   number in it. Rewrite ONLY the ending of such bullets so they close on a
   complete noun phrase — extend the closing clause to three or more words
   after the gerund, or reword it. Do not add numbers and do not change the
   bullet's meaning or its tools.
6. TEMPLATED WORDING: rewrite any bullet that starts with a cliché — "Responsible
   for", "Tasked with", "Utilized", "Leveraged", "Spearheaded", "Worked on",
   "Helped with", "Involved in", "In charge of" — to lead with a real action verb
   (Built, Designed, Architected, Migrated, Optimized, Automated, Led…). Also, if
   two bullets in the SAME job start with the same verb, change one so no verb
   repeats within a job. Reword only; keep the meaning, tools, and any number.
7. CLOUD RESTORATION (only if a note below names jobs + clouds): for each named
   job, WEAVE that cloud naturally into 1–2 of its existing bullets AND into its
   Technologies Used line, sitting alongside the tools already there (e.g. "on AWS
   and Databricks, built dbt models…"). Do NOT add or remove bullets — only reword
   existing ones. Do NOT touch jobs not named.
8. DASHES: if any bullet or summary line contains an em or en dash (— or –),
   rewrite that spot with a comma, colon, parentheses, "including", or "such as"
   so the sentence reads naturally. The headline (Name — Title) and job-header
   date ranges keep their dashes.

Output ONLY the corrected resume in the same plain-text format — no commentary,
no code fences."""


FRAGMENT_FIX_SYSTEM = """You are a resume line editor. Each input line is a
numbered experience bullet whose ENDING reads as cut off mid-thought.

Rewrite ONLY the ending of each bullet so it closes as a complete sentence:
- Never end on a bare "-ing" word ("...and caching." -> "...and caching strategies.")
- Never end on a preposition or connective (of, for, with, and, to, in, across)
- If the bullet closes with a ", <verb>ing ..." clause, that clause must have at
  least THREE words after the gerund ("...,improving pipeline reliability." ->
  "...,improving reliability across production workloads.")
- End on a complete noun phrase.

HARD RULES:
- Keep the bullet's meaning, its tools, and every number already present.
- Do NOT add any new number, metric, percentage, or claim.
- Change as few words as possible — only what the ending needs.

STRICT OUTPUT: return EXACTLY one rewritten bullet per input line, same order,
same numbering (1., 2., ...). No added, dropped, split, or merged lines. No
commentary."""


SCORE_SYSTEM = """You are a strict, experienced resume reviewer. Score a tailored
resume against its job description on THREE gates. Be critical and realistic —
most resumes score 70–85; reserve 90+ for genuinely excellent fit. Do NOT inflate.

Return ONLY compact JSON, no prose:
{
  "ats": {"score": <0-100>, "note": "<one short reason>"},
  "recruiter": {"score": <0-100>, "note": "<one short reason>"},
  "hiring_manager": {"score": <0-100>, "note": "<one short reason>"},
  "overall": <0-100>,
  "top_fixes": ["<specific fix 1>", "<specific fix 2>", "<specific fix 3>"],
  "present": ["<JD tool the resume DOES cover>"],
  "missing": ["<JD tool genuinely NOT covered>"]
}

Gate definitions:
- ats: keyword & tool coverage vs the JD, parseable single-column format. Penalize missing JD keywords.
- recruiter: 6-second scan — does the title match, does the summary show fit fast, is it clean and skimmable.
- hiring_manager: believability — no invented metrics, no inflated years/clearance, claims are defensible, bridged honestly.
overall = holistic, roughly the weakest-gate-weighted average.
top_fixes = the 3 highest-impact concrete improvements (empty list if truly none).

present / missing — you are given the JD's target tools. For EACH one, decide by
MEANING (not exact string) whether the resume covers it, and put it in exactly one
list. A tool is PRESENT if the resume expresses it in ANY form:
  * the exact name, an acronym or its spelled-out form (RAG = Retrieval-Augmented
    Generation; ML = Machine Learning; LLM = Large Language Models; CI/CD =
    continuous integration/deployment; OOP = object-oriented programming),
  * a synonym or near-equivalent (containers/Kubernetes covers "Docker";
    event-driven pipelines cover "event-driven architecture"; MLflow, fine-tuning
    or embeddings cover "Machine Learning"; Airflow covers an "Airflow or
    equivalent" orchestration requirement),
  * or an honest bridge phrase ("C#-adjacent…", "patterns transferable to…").
A tool is MISSING only if the resume genuinely does not cover it in any of those
ways. Judge by what the resume MEANS, exactly as a human reviewer would — never
by literal word-for-word matching. Every target tool goes in present OR missing,
never both, never neither."""


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
        "JD-mirroring bullets (varied lengths — mostly 15–24 words with a short "
        "8–12-word bullet in each job, no invented numbers, no 'measured via' "
        "clauses), the exact bullet ladder, and the cloud rule (provider swap in "
        "Job 1 & 2 when a target cloud exists; tools mirrored in all jobs)."
    )


def qa_fixer_prompt(tailored: str, cloud_directive: str = "") -> str:
    extra = f"\n\n{cloud_directive}" if cloud_directive else ""
    return (
        "Fix the checklist issues in this resume and return the full corrected "
        "text. Keep every bullet." + extra + "\n\n" + tailored
    )


def score_prompt(jd_text: str, tailored: str, target_tools: list | None = None) -> str:
    tools = ", ".join(str(t) for t in (target_tools or []) if str(t).strip())
    tools_block = f"JD TARGET TOOLS (classify each as present/missing):\n  {tools}\n\n" if tools else ""
    return (
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"{tools_block}"
        f"TAILORED RESUME:\n{tailored}\n\n"
        "Score the three gates, classify every target tool as present or missing, "
        "and return the JSON."
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


# Soft skills / non-technical terms that must never be scored as ATS keywords.
# Matched as substrings (lowercased) against a target tool, so "cross-functional
# collaboration" and "strong stakeholder management" both drop.
_SOFT_SKILL_MARKERS = (
    "collaboration", "collaborat", "communication", "communicat", "stakeholder",
    "mentoring", "mentorship", "leadership", "teamwork", "team player",
    "interpersonal", "problem solving", "problem-solving", "critical thinking",
    "attention to detail", "time management", "adaptability", "self-starter",
    "proactive", "ownership mindset", "cross-functional", "cross functional",
    "fast-paced", "work independently", "curiosity", "willingness to learn",
    "organizational skills", "presentation skills", "influencing", "consensus",
)


def _is_soft_skill(term: str) -> bool:
    t = term.lower().strip()
    return any(m in t for m in _SOFT_SKILL_MARKERS)


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


_DASH_PAIR_RE = re.compile(r"\s+[—–]\s+([^—–]{2,90}?)\s+[—–]\s+")


def _strip_dash_asides(text: str) -> tuple[str, int]:
    """Em/en dashes inside body text are the most recognizable AI-writing tell.
    The prompt and QA fixer both forbid them, but models still slip — this makes
    the guarantee deterministic. Paired dashes become a parenthetical, a lone
    dash becomes a comma. The headline (line 1) and job-header date ranges are
    left alone."""
    lines = text.split("\n")
    hits = 0
    for i, ln in enumerate(lines):
        if i == 0 or _is_job_header_line(ln) or not re.search(r"[—–]", ln):
            continue
        s = ln
        while _DASH_PAIR_RE.search(s):
            s = _DASH_PAIR_RE.sub(r" (\1) ", s, count=1)
            hits += 1
        remaining = len(re.findall(r"[—–]", s))
        if remaining:
            s = re.sub(r"\s*[—–]\s*", ", ", s)
            hits += remaining
        lines[i] = re.sub(r"[ \t]{2,}", " ", s).rstrip()
    return "\n".join(lines), hits


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


_HDR_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}")
_HDR_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Seniority/scope words that must never be added to a job title unless the base
# resume already uses them for that person (anti-inflation honesty net).
_SENIORITY_RE = re.compile(
    r"\b(senior|sr\.?|lead|staff|principal|manager|mgr\.?|director|head|chief|"
    r"vp|vice\s+president|architect|president)\b", re.IGNORECASE)


def _guard_title_inflation(result: str, base_resume: str, notes: list) -> str:
    """Employment-history titles must be EXACTLY the base resume's titles on
    every application. Deterministic
    backstop for the prompt rule: match each experience line to its base entry
    by company and restore the base title verbatim. Falls back to stripping
    unsupported seniority words for lines whose company can't be matched."""
    def _exp_lines(text: str) -> list[tuple[str, str]]:
        """[(title, company_key)] for 'Title @ Company | ...' lines."""
        out = []
        for ln in (text or "").splitlines():
            if " @ " not in ln or ln.lstrip().startswith(("•", "-", "*")):
                continue
            raw_title, rest = ln.split(" @ ", 1)
            title = raw_title.strip(" #*").strip()
            company = rest.split("|", 1)[0].strip(" #*").strip().lower()
            if title and company:
                out.append((title, company))
        return out

    # company → queue of base titles (handles repeat employers in order)
    base_map: dict[str, list[str]] = {}
    for title, comp in _exp_lines(base_resume):
        base_map.setdefault(comp, []).append(title)

    base_low = (base_resume or "").lower()
    lines = result.splitlines()
    for i, ln in enumerate(lines):
        if " @ " not in ln or ln.lstrip().startswith(("•", "-", "*")):
            continue
        raw_title = ln.split(" @ ", 1)[0]
        title = raw_title.strip(" #*").strip()
        comp = ln.split(" @ ", 1)[1].split("|", 1)[0].strip(" #*").strip().lower()
        queue = base_map.get(comp)
        if queue:
            base_title = queue.pop(0) if len(queue) > 1 else queue[0]
            if title != base_title:
                lines[i] = ln.replace(raw_title, raw_title.replace(title, base_title), 1)
                notes.append(f"experience title restored to base: {title!r} -> {base_title!r}")
            continue
        # Company not found in base — legacy anti-inflation strip as backstop.
        changed = False
        for m in list(_SENIORITY_RE.finditer(title)):
            word = m.group(0)
            if word.lower() not in base_low:
                title = _SENIORITY_RE.sub(lambda mm: "" if mm.group(0) == word else mm.group(0), title, count=0)
                changed = True
        if changed:
            new_title = re.sub(r"\s{2,}", " ", title).strip(" -–—|")
            lines[i] = ln.replace(ln.split(" @ ", 1)[0], new_title, 1)
            notes.append(f"title de-inflated: dropped unsupported seniority in {new_title!r}")
    return "\n".join(lines)


# Role families for the hybrid headline rule. Keyword hit → that family.
_FAMILY_KWS: list[tuple[str, list[str]]] = [
    ("Data Engineer",    ["data engineer", "etl", "elt", "databricks", "snowflake", "spark",
                          "mlops", "machine learning", "data platform", "data warehouse",
                          "data architect", "database engineer", "database developer", "big data"]),
    ("Data Analyst",     ["data analyst", "data analytics", "analytics engineer",
                          "reporting analyst", "product analyst", "quantitative analyst"]),
    ("BI",               ["business intelligence", "bi developer", "bi analyst", "bi engineer",
                          "power bi", "tableau", "looker"]),
    ("Cloud",            ["cloud engineer", "cloud infrastructure", "cloud operations", "cloudops",
                          "aws engineer", "azure engineer", "gcp engineer",
                          "infrastructure engineer", "kubernetes", "terraform"]),
    ("DevOps",           ["devops", "devsecops", "sre", "site reliability", "platform engineer",
                          "release engineer", "production engineer", "reliability engineer"]),
    ("Business Analyst", ["business analyst", "business systems analyst", "systems analyst",
                          "it business analyst", "process analyst", "requirements analyst",
                          "functional analyst"]),
]
_F_DATA = re.compile(r"\bdata\b", re.I)
_F_ANALYST = re.compile(r"\banalyst\b", re.I)
_F_ENGINEER = re.compile(r"\bengineer\b", re.I)


def _role_family(title: str) -> str:
    """Coarse family for a job/JD title. Empty string = unknown/off-domain."""
    t = (title or "").lower()
    for fam, kws in _FAMILY_KWS:
        if any(k in t for k in kws):
            return fam
    if _F_DATA.search(t) and _F_ANALYST.search(t):
        return "Data Analyst"
    if _F_DATA.search(t) and _F_ENGINEER.search(t):
        return "Data Engineer"
    return ""


def _headline_hybrid(result: str, base_resume: str, jd_title: str, notes: list) -> str:
    """Hybrid headline rule: mirror the JD role in the headline ONLY when it is
    the same role family as the candidate's real latest job title; otherwise fall
    back to that real title (avoids off-domain headlines like 'State Estimation
    Engineer' on a data-engineer resume). When mirroring, still de-inflate any
    seniority word the base resume doesn't support."""
    lines = result.splitlines()
    if not lines or "—" not in lines[0]:
        return result
    name, _, cur_title = lines[0].partition("—")
    cur_title = cur_title.strip()

    real_title = ""
    for ln in base_resume.splitlines():
        if " @ " in ln and not ln.lstrip().startswith(("•", "-", "*")):
            real_title = ln.split(" @ ", 1)[0].strip()
            break
    if not real_title:
        return result

    # Classify the CORE title only — drop the posting suffix after " - "/en-dash/
    # pipe/colon/paren so incidental words (e.g. "- Data Collection Systems")
    # don't false-match a family.
    jd_core = re.split(r"\s+–\s+|\s+-\s+|\s*\|\s*|\s*:\s+|\s*\(", (jd_title or cur_title), maxsplit=1)[0]
    fam_jd = _role_family(jd_core)
    fam_real = _role_family(real_title)

    if fam_jd and fam_jd == fam_real:
        # Same family → mirror is fine, but never inflate seniority in it.
        base_low = base_resume.lower()
        deinf = _SENIORITY_RE.sub(
            lambda m: m.group(0) if m.group(0).lower() in base_low else "", cur_title)
        deinf = re.sub(r"\s{2,}", " ", deinf).strip(" -–—|")
        if deinf and deinf != cur_title:
            lines[0] = f"{name.strip()} — {deinf}"
            notes.append(f"headline de-inflated: {cur_title!r} -> {deinf!r}")
        return "\n".join(lines)

    # Different family / off-domain JD → use the real latest job title.
    if cur_title.lower() != real_title.lower():
        lines[0] = f"{name.strip()} — {real_title}"
        notes.append(f"headline set to real title (JD fam={fam_jd or 'unknown'} != real fam={fam_real or 'unknown'}): {real_title!r}")
    return "\n".join(lines)


def _clean_header_title(result: str) -> str:
    """Deterministic: strip posting-title suffixes from the header title line.
    'Name — Data Migration Engineer – SQL Server to Snowflake & Matillion'
    → 'Name — Data Migration Engineer'
    The name/title separator is an em-dash (—); posting suffixes follow an
    en-dash (–), ' - ', pipe, colon, or opening parenthesis."""
    lines = result.splitlines()
    if not lines:
        return result
    first = lines[0]
    if "—" not in first:
        return result
    name, _, title = first.partition("—")
    cleaned = re.split(r"\s+–\s+|\s+-\s+|\s*\|\s*|\s*:\s+|\s*\(", title, maxsplit=1)[0].strip()
    if cleaned and cleaned != title.strip():
        lines[0] = f"{name.strip()} — {cleaned}"
        print(f"[HEADER TITLE] Cleaned posting suffix: {title.strip()!r} -> {cleaned!r}")
    return "\n".join(lines)


def _ensure_header(result: str, base_resume: str) -> str:
    """Deterministic safety net: if the model dropped the name/contact header,
    restore it from the base resume. Preserves any title the model chose."""
    stripped = result.strip()
    lines = stripped.splitlines()
    top3 = "\n".join(lines[:3])
    if _HDR_PHONE_RE.search(top3) and _HDR_EMAIL_RE.search(top3):
        return result  # header intact

    base_lines = [l for l in base_resume.strip().splitlines() if l.strip()]
    contact_line = next((l for l in base_lines[:4] if _HDR_PHONE_RE.search(l)), "")
    if not contact_line:
        return result  # nothing to restore from — give up

    first_hdr = next((m for m in re.finditer(r"^[A-Z][A-Z ]{3,}:?$", stripped, re.M)), None)
    body = stripped[first_hdr.start():] if first_hdr else stripped
    first_line = lines[0].strip() if lines else ""
    has_name_line = bool(first_hdr) and first_hdr.start() > len(first_line) and "—" in first_line

    if has_name_line:
        print("[HEADER MISSING] Contact line missing — restoring.")
        return first_line + "\n" + contact_line + "\n\n" + body
    print("[HEADER MISSING] Full header missing — restoring from base resume.")
    return (base_lines[0] if base_lines else "") + "\n" + contact_line + "\n\n" + body


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
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    # Never ship a "0 years" claim. It happens when the base resume's dates
    # couldn't be parsed (e.g. a table-layout docx), leaving no computable
    # tenure — the model then writes "0+ years", which reads as zero experience
    # on the resume. Replace the count with an honest, count-free phrase.
    result = re.sub(r"\b0\s*\+?\s*years?(?:\s+of\s+experience)?\b",
                    "hands-on experience", result, flags=re.IGNORECASE)
    return result


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


try:
    from resume_lint import find_fragment_bullets, is_fragment_bullet
except ImportError:  # pragma: no cover — lint module optional
    find_fragment_bullets = is_fragment_bullet = None


# A dangling participial tail the truncation detector rejects: ", improving
# pipeline reliability." — comma, gerund, one or two words, no digit.
_DANGLING_TAIL = re.compile(r",\s+\w+ing\b[^,;]{0,40}$")


def _trim_dangling_tail(bullet: str) -> str:
    """Deterministic last resort: drop the trailing participial clause. The
    sentence before the comma is already complete, so removing it can never
    invent content — it only sheds the part that reads as cut off."""
    stripped = bullet.rstrip()
    trailing_dot = stripped.endswith(".")
    core = stripped.rstrip(".")
    m = _DANGLING_TAIL.search(core)
    if not m:
        return bullet
    trimmed = core[: m.start()].rstrip(" ,;")
    if len(trimmed.split()) < 8:
        return bullet  # would leave a stub — worse than the dangle
    return trimmed + ("." if trailing_dot else "")


async def _fix_fragment_endings(resume: str, job_description: str,
                                notes: list, **cheap_kw) -> str:
    """Repair bullets whose endings the truncation detector flags.

    Prompt rules alone left survivors, so this measures with the same
    find_fragment_bullets() that drives the UI warning, sends ONLY the flagged
    bullets to the cheap model, and finishes with a deterministic trim for
    anything still flagged. The extra call fires only when something is
    actually broken — a clean draft costs nothing.
    """
    if find_fragment_bullets is None:
        return resume
    try:
        flagged = find_fragment_bullets(resume, context=job_description)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"fragment check skipped ({exc})")
        return resume
    if not flagged:
        return resume

    lines = resume.splitlines()
    flagged_set = {f.strip() for f in flagged}
    targets = [i for i, ln in enumerate(lines)
               if ln.lstrip().startswith("•") and ln.lstrip()[1:].strip() in flagged_set]
    if not targets:
        return resume

    payload = "\n".join(f"{n + 1}. {lines[i].lstrip()[1:].strip()}"
                        for n, i in enumerate(targets))
    try:
        out = (await chat(FRAGMENT_FIX_SYSTEM, payload, max_tokens=2000,
                          pass_name="fragment_fix", **cheap_kw)).strip()
        fixes = [re.sub(r"^\s*\d+[.)]\s*", "", ln).strip()
                 for ln in out.splitlines() if ln.strip()]
        if len(fixes) == len(targets):
            for i, fix in zip(targets, fixes):
                if fix:
                    lines[i] = "• " + fix
        else:
            notes.append("fragment fix rejected (line count mismatch)")
    except Exception as exc:  # noqa: BLE001 — best effort
        notes.append(f"fragment fix skipped ({exc})")

    # Deterministic backstop — the model is not allowed to be the last word.
    forced = 0
    for i in targets:
        body = lines[i].lstrip()[1:].strip()
        if is_fragment_bullet is not None and is_fragment_bullet(body, job_description):
            trimmed = _trim_dangling_tail(body)
            if trimmed != body:
                lines[i] = "• " + trimmed
                forced += 1

    fixed_resume = "\n".join(lines)
    try:
        left = len(find_fragment_bullets(fixed_resume, context=job_description))
    except Exception:  # noqa: BLE001
        left = -1
    notes.append(
        f"fragment endings: {len(targets)} flagged, "
        f"{forced} trimmed deterministically, {left} remaining"
    )
    return fixed_resume


_SKILLS_MAX = 8      # items per Skills category line (5-7 categories now, so keep each tight)
_TECH_MAX = 16       # items per job's Technologies Used line
_JUNK_ITEMS = {"and", "etc", "etc.", "", "-", "•"}


def _split_list_items(rest: str) -> list[str]:
    """Comma-split a list while keeping parenthesised groups intact, so
    'AWS (S3, EMR, Glue), Databricks' -> ['AWS (S3, EMR, Glue)', 'Databricks']."""
    items, buf, depth = [], [], 0
    for ch in rest:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf))
    return items


_CLOUD_PREFIXES = ("aws", "azure", "gcp", "google cloud")


def _tidy_items(rest: str, cap: int) -> tuple[str, bool]:
    """Dedup (case-insensitive), strip trailing 'and'/punctuation junk, drop a
    cloud prefix that duplicates a standalone cloud entry (AWS + 'AWS S3' ->
    AWS + S3), cap length. Returns (clean_string, changed?)."""
    raw = _split_list_items(rest)
    seen, out = set(), []
    for it in raw:
        it = it.strip().strip(".").strip()
        it = re.sub(r"^(and|&)\s+", "", it, flags=re.I).strip()
        if not it or it.lower() in _JUNK_ITEMS:
            continue
        key = re.sub(r"[^a-z0-9]", "", it.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)

    # If a bare cloud name (AWS/Azure/GCP) is present as its own item, strip that
    # prefix off any sibling like "AWS S3" -> "S3" (kills the "AWS, AWS S3" dup).
    lowers = {o.lower() for o in out}
    present = [p for p in _CLOUD_PREFIXES if p in lowers]
    if present:
        deduped, kept = [], set()
        for o in out:
            stripped = o
            for p in present:
                if o.lower().startswith(p + " ") and o[len(p):].strip("() "):
                    stripped = o[len(p):].strip("() ")
                    break
            k = re.sub(r"[^a-z0-9]", "", stripped.lower())
            if k in kept:
                continue
            kept.add(k)
            deduped.append(stripped)
        out = deduped

    # Cap items INSIDE a parenthetical group too, so "AWS (S3, EMR, Glue,
    # Lambda, Redshift, IAM, Lake Formation, Step Functions, ECS, AWS Batch)"
    # doesn't visually blow up a line that counts as one item.
    def _cap_group(item: str) -> str:
        m = re.match(r"^(.*?)\s*\((.+)\)\s*$", item)
        if not m:
            return item
        head, inner = m.group(1), _split_list_items(m.group(2))
        inner = [x.strip() for x in inner if x.strip()]
        if len(inner) <= 5:
            return item
        return f"{head} ({', '.join(inner[:5])})"

    out = [_cap_group(o) for o in out]
    capped = out[:cap]
    result = ", ".join(capped)
    return result, (result != rest.strip())


_TECH_LINE_RE = re.compile(r"^(\s*(?:\*\*)?technologies used:?\**)\s*(.*)$", re.I)


def _clean_lists(text: str) -> tuple[str, int]:
    """Deterministic tidy of Skills rows and Technologies Used lines: dedup,
    strip 'and'/period junk left by generation, cap length. Adds nothing."""
    lines = text.splitlines()
    changed = 0
    in_skills = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_section_hdr(s):
            in_skills = "skill" in s.lower()
            continue

        m = _TECH_LINE_RE.match(s)
        if m:
            body, hit = _tidy_items(m.group(2), _TECH_MAX)
            if hit:
                indent = ln[: len(ln) - len(ln.lstrip())]
                lines[i] = f"{indent}Technologies Used: {body}"
                changed += 1
            continue

        # Skills row: "• Label: a, b, c" (or "- **Label:** a, b")
        if in_skills and s.startswith(("•", "-", "*")) and ":" in s:
            prefix, _, rest = s.partition(":")
            body, hit = _tidy_items(rest, _SKILLS_MAX)
            if hit:
                indent = ln[: len(ln) - len(ln.lstrip())]
                marker = s[0]
                label = prefix.lstrip("•-* ").rstrip()
                lines[i] = f"{indent}{marker} {label}: {body}"
                changed += 1
    return "\n".join(lines), changed


# ── Guard: every claimed Skill must be evidenced by an experience bullet ──────

SKILL_BULLET_SYSTEM = """You write single resume bullets. You receive a numbered
job list and a list of skills that need evidence — each appears in the resume's
SKILLS section or in the job description's requirements, but in NO experience
bullet — plus the job description and full resume for context.

For EACH listed skill, output ONE line in EXACTLY this format:
<job number> :: <skill> :: <bullet text>

Rules:
- job number = the ONE job where that work most plausibly happened (match the
  job's era, industry, and stack).
- bullet text: one past-tense sentence, 10–24 words, naming the skill
  explicitly. A modest routine scope-of-work claim, NOT a headline achievement.
  NO numbers, no em/en dashes, and do not open with a verb that job already uses.
- GROUP aggressively: one line may prove up to THREE related skills (same
  category — BI tools together, quality tools together, scripting together).
  Put all grouped names in the skill field separated by " + ". Prefer few
  packed lines over many thin ones.
- Jobs have bullet caps (Job 1 ≤ 12, Job 2 ≤ 8, Job 3 ≤ 6, older ≤ 3, counting
  their existing bullets) — group enough that everything fits.
Output ONLY these lines — no commentary, no blank-line padding."""


def _skills_claimed(text: str) -> list[str]:
    """Items from the SKILLS section category lines."""
    items, in_skills = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if _is_section_hdr(s):
            in_skills = "skill" in s.lower()
            continue
        if in_skills and s.startswith(("•", "-", "*")) and ":" in s:
            _, _, rest = s.partition(":")
            items.extend(i.strip() for i in _split_list_items(rest) if i.strip())
    return items


def _experience_blob(text: str) -> str:
    """The evidence part of the resume: everything under EXPERIENCE / PROJECTS
    headers (bullets + Technologies Used lines), lowercased."""
    keep, active = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if _is_section_hdr(s):
            up = s.upper()
            active = "EXPERIENCE" in up or "PROJECT" in up
            continue
        if active and s:
            keep.append(s)
    return "\n".join(keep).lower()


# Vendor/generic words that can't stand in for a whole skill name — "Apache
# Kafka" is evidenced by "Kafka Connect", but "Microsoft Fabric" is NOT
# evidenced by some other "Microsoft" mention.
_SKILL_TOKEN_STOP = {
    "apache", "microsoft", "azure", "amazon", "google", "cloud", "data",
    "actions", "services", "service", "platform", "platforms", "tools",
    "core", "server", "studio", "suite", "enterprise", "analytics",
}


def _unevidenced(items: list[str], text: str) -> list[str]:
    """The subset of `items` with no supporting line in EXPERIENCE/PROJECTS."""
    try:
        from resume_lint import _dynamic_coverage_pattern
    except ImportError:  # pragma: no cover — lint module optional
        return []
    blob = _experience_blob(text)
    if not blob:
        return []
    out = []
    for item in items:
        core = re.sub(r"\s*\(.*\)\s*", " ", item).strip()
        if len(core) < 2:
            continue
        try:
            if re.search(_dynamic_coverage_pattern(core), blob):
                continue
        except re.error:
            continue
        # Fallback: a distinctive token of a multi-word name still counts —
        # "Apache Kafka" is covered by a "Kafka Connect" bullet.
        toks = [w for w in re.findall(r"[A-Za-z][\w+#.-]{4,}", core)
                if w.lower() not in _SKILL_TOKEN_STOP]
        if toks and any(re.search(rf"(?<![a-z0-9]){re.escape(w.lower())}(?![a-z0-9])", blob)
                        for w in toks):
            continue
        out.append(item)
    return out


def _orphan_skills(text: str) -> list[str]:
    """Skills-section items with no supporting line in EXPERIENCE/PROJECTS."""
    return _unevidenced(_skills_claimed(text), text)




def _job_block_end(lines: list[str], start: int) -> int:
    """Index one past the last line of the job whose header sits at `start`."""
    for i in range(start + 1, len(lines)):
        if _is_job_header_line(lines[i]) or _is_section_hdr(lines[i].strip()):
            return i
    return len(lines)


# Hard bullet ceilings by job recency (Job 1, Job 2, Job 3; older jobs 3).
_JOB_BULLET_CAPS = (12, 8, 6)


def _job_cap(j: int) -> int:
    return _JOB_BULLET_CAPS[j] if j < len(_JOB_BULLET_CAPS) else 3


def _insert_skill_bullets(resume: str, additions: dict) -> tuple[str, int]:
    """Deterministically place {job_index: [(skill, bullet), ...]} — each bullet
    goes just above that job's Technologies Used line (or at the block end), and
    the skill is appended to that Technologies Used line. Respects per-job
    bullet caps; additions past a cap are dropped (the skill is then trimmed
    from SKILLS by _drop_unevidenced_skills)."""
    lines = resume.split("\n")
    hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    added = 0
    for j in sorted(additions, reverse=True):   # bottom-up keeps indices valid
        if j >= len(hdr_idx):
            continue
        end = _job_block_end(lines, hdr_idx[j])
        existing = sum(1 for i in range(hdr_idx[j] + 1, end)
                       if lines[i].lstrip().startswith("•"))
        room = max(0, _job_cap(j) - existing)
        take = additions[j][:room]
        if not take:
            continue
        tech_i = next((i for i in range(hdr_idx[j] + 1, end)
                       if _TECH_LINE_RE.match(lines[i].strip())), None)
        at = tech_i if tech_i is not None else end
        new_lines = ["• " + b for _, b in take]
        lines[at:at] = new_lines
        added += len(new_lines)
        if tech_i is not None:
            ti = tech_i + len(new_lines)
            skills = ", ".join(s for pair in take
                               for s in re.split(r"\s*\+\s*", pair[0]) if s)
            lines[ti] = lines[ti].rstrip().rstrip(",") + ", " + skills
    return "\n".join(lines), added


def _drop_unevidenced_skills(text: str, notes: list) -> str:
    """Last resort for the no-orphan invariant: a skill that still has no
    experience bullet after the guard rounds is removed from the SKILLS lines —
    an unbacked keyword hurts more in a screen than its absence costs in ATS."""
    orphans = _orphan_skills(text)
    if not orphans:
        return text
    keys = {re.sub(r"[^a-z0-9]", "", o.lower()) for o in orphans}
    lines = text.split("\n")
    removed: list[str] = []
    in_skills = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_section_hdr(s):
            in_skills = "skill" in s.lower()
            continue
        if in_skills and s.startswith(("•", "-", "*")) and ":" in s:
            marker = s[0]
            label, _, rest = s.partition(":")
            items = [it.strip() for it in _split_list_items(rest) if it.strip()]
            kept = [it for it in items
                    if re.sub(r"[^a-z0-9]", "", it.lower()) not in keys]
            if len(kept) != len(items):
                removed.extend(it for it in items if it not in kept)
                indent = ln[: len(ln) - len(ln.lstrip())]
                label = label.lstrip("•-* ").rstrip()
                lines[i] = (f"{indent}{marker} {label}: {', '.join(kept)}"
                            if kept else "")
    if removed:
        notes.append("skills trimmed (no supporting bullet): " + ", ".join(removed))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return text


async def _ensure_skill_bullets(resume: str, job_description: str,
                                notes: list, jd_missing: list | None = None,
                                **cheap_kw) -> str:
    """A skill listed in SKILLS with zero experience bullets behind it dies in
    the first interview question. Detect orphans deterministically, have the
    cheap model write ONLY the new bullets (one line each, job-addressed), then
    insert them in code — the model never rewrites the resume, so nothing can
    drift. Only fires when orphans exist; a clean draft costs nothing.

    `jd_missing` — the analyze pass's `baseline_missing` list, i.e. the JD's
    universal expected competencies the model itself judged honest for any
    engineer at this level — is chased too, because leaving one out is pure
    lost coverage. Niche missing products never reach this list and stay out
    on purpose."""
    baseline = [str(m) for m in (jd_missing or []) if not _is_soft_skill(str(m))]
    if not _orphan_skills(resume) and not _unevidenced(baseline, resume):
        return resume
    total_added = 0
    try:
        # Two rounds: the model occasionally skips a line — the second round
        # re-measures and chases only what's still unevidenced.
        for _attempt in range(2):
            chased = _orphan_skills(resume) + [
                b for b in _unevidenced(baseline, resume)]
            # dedupe, cap
            seen: set = set()
            orphans = [o for o in chased
                       if not (o.lower() in seen or seen.add(o.lower()))][:16]
            if not orphans:
                break
            lines = resume.split("\n")
            hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
            if not hdr_idx:
                break
            jobs_list = "\n".join(f"{n + 1}. {lines[i].strip()}"
                                  for n, i in enumerate(hdr_idx))
            out = (await chat(
                SKILL_BULLET_SYSTEM,
                "JOBS:\n" + jobs_list
                + "\n\nORPHAN SKILLS (one output line each):\n"
                + "\n".join(f"- {o}" for o in orphans)
                + f"\n\nJOB DESCRIPTION (context):\n{job_description[:4000]}"
                + f"\n\nRESUME (context):\n{resume}",
                max_tokens=3000, pass_name="skill_bullets", **cheap_kw)).strip()
            additions: dict[int, list] = {}
            for ln in out.splitlines():
                m = re.match(r"^\s*(\d+)\s*::\s*(.+?)\s*::\s*(.+?)\s*$", ln)
                if not m:
                    continue
                j = int(m.group(1)) - 1
                skill = m.group(2).strip()
                bullet = m.group(3).strip().lstrip("•-* ").strip()
                bullet = re.sub(r"\s*[—–]\s*", ", ", bullet)   # belt and braces
                if not (0 <= j < len(hdr_idx)) or not bullet:
                    continue
                if not 6 <= len(bullet.split()) <= 34:
                    continue
                additions.setdefault(j, []).append((skill, bullet))
            if not additions:
                break
            resume, added = _insert_skill_bullets(resume, additions)
            total_added += added
        left = len(_orphan_skills(resume)) + len(_unevidenced(baseline, resume))
        notes.append(f"skill-bullet guard: {total_added} bullet(s) inserted"
                     + (f" (incl. JD baseline: {', '.join(baseline)})" if baseline else "")
                     + f", {left} still unevidenced")
    except Exception as exc:  # noqa: BLE001 — best effort
        notes.append(f"skill-bullet guard skipped ({exc})")
    # Whatever still lacks a bullet leaves the SKILLS list — no orphans, ever.
    return _drop_unevidenced_skills(resume, notes)


_YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*years?", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _base_years_claim(base_resume: str):
    """The candidate's real years-of-experience ceiling.
    Prefers an explicit 'N+ years' the base resume states (that IS the truth
    the candidate chose to present). Falls back to years elapsed since the
    earliest job start date. Returns (claim_string_or_None, ceiling_int)."""
    head = "\n".join(base_resume.splitlines()[:12])
    m = _YEARS_RE.search(head) or _YEARS_RE.search(base_resume)
    explicit = m.group(0) if m else None
    explicit_n = int(m.group(1)) if m else None

    years = [int(y) for y in _YEAR_RE.findall(base_resume)]
    derived = None
    if years:
        # crude but safe: span from earliest 4-digit year to the latest.
        derived = max(years) - min(years)
    ceiling = explicit_n if explicit_n is not None else derived
    return explicit, ceiling


def _clamp_years(result: str, base_resume: str) -> tuple[str, bool]:
    """Stop the summary inflating years to meet a JD minimum. If the tailored
    summary claims MORE years than the base supports, rewrite it down to the
    base's own claim. Deflation is left alone (never our problem)."""
    explicit, ceiling = _base_years_claim(base_resume)
    if ceiling is None:
        return result, False

    lines = result.splitlines()
    in_summary = False
    changed = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_section_hdr(s):
            in_summary = "summary" in s.lower()
            continue
        # Header line (line 0/1) can also carry a claim; check summary + top.
        if not (in_summary or i < 2):
            continue
        m = _YEARS_RE.search(ln)
        if not m:
            continue
        claimed = int(m.group(1))
        if claimed > ceiling:
            repl = explicit if explicit else f"{ceiling}+ years"
            lines[i] = ln[:m.start()] + repl + ln[m.end():]
            changed = True
    return "\n".join(lines), changed


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

    # Start a fresh token/cost accumulator for THIS run (see ai/llm.py). Every
    # chat() call below records its usage into it; we read the total before
    # returning so main.py can store the per-resume cost.
    try:
        from ai.llm import reset_usage
        reset_usage()
    except Exception:  # noqa: BLE001
        pass

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

    # Drop soft skills that leaked into the tool list — an ATS scans for hard
    # skills, not "collaboration", and soft terms are trivially "covered" so they
    # inflate the coverage score toward a suspicious 100. Prompt-only exclusion
    # slips, so filter deterministically here.
    for _k in ("target_tools", "present", "missing"):
        _orig = context.get(_k) or []
        _kept = [t for t in _orig if not _is_soft_skill(str(t))]
        if len(_kept) != len(_orig):
            context[_k] = _kept

    missing = context.get("missing") or []
    print(f"[TAILOR] target_cloud={context.get('target_cloud')!r} "
          f"missing_tools={len(missing)} company={company or context.get('company', '')!r}")

    # ── 2. TAILOR (main model) ────────────────────────────────────────────
    tailored = (await chat(
        TAILOR_SYSTEM,
        tailor_prompt(base_resume, job_description, context, missing, profile_skills),
        max_tokens=8000, pass_name="tailor", **main_kw,
    )).strip()
    tailored = _clean_header_title(_ensure_header(_normalize_format(tailored), base_resume))

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

    tailored = _clean_header_title(_strip_empty_sections(tailored)).strip()
    tailored = _guard_title_inflation(tailored, base_resume, notes)
    tailored = _headline_hybrid(tailored, base_resume, context.get("job_title", ""), notes)

    # Guard (c2): every skill claimed in SKILLS must have an experience bullet
    # behind it — orphans get a modest scope bullet written into the job where
    # that work plausibly happened. The JD's universal-baseline requirements
    # the draft left uncovered (as judged by the analyze pass, per JD — no
    # fixed list in code) are chased too.
    tailored = await _ensure_skill_bullets(tailored, job_description, notes,
                                           jd_missing=context.get("baseline_missing") or [],
                                           **cheap_kw)

    # Guard (c3): bullets whose endings read as truncated. Measured with the
    # same detector that drives the UI warning; only spends a call when the
    # draft actually has flagged bullets, and finishes deterministically.
    tailored = await _fix_fragment_endings(tailored, job_description, notes, **cheap_kw)

    # Guard (d): tidy the Skills rows and Technologies Used lines. Keyword
    # coverage is handled by the tailor prompt (which keeps every base+JD shared
    # tool); this pass only removes duplicates, strips list-punctuation junk, and
    # caps line length so nothing reads as stuffed. It never ADDS a keyword — the
    # old inject-to-cover approach produced 20-item lines and grammar like
    # "ERwin., Data Architecture", so it was removed.
    tailored, tidied = _clean_lists(tailored)
    if tidied:
        notes.append(f"tidied {tidied} over-long / duplicate list line(s)")

    # Guard (d2): no em/en dashes in body text — the classic AI-writing tell.
    tailored, dash_hits = _strip_dash_asides(tailored)
    if dash_hits:
        notes.append(f"dash guard: rewrote {dash_hits} dash construction(s)")

    # Guard (e): years-of-experience must never inflate to meet a JD minimum.
    # If the summary claims more years than the base resume supports, clamp it
    # back down. A code rule, not a prompt line — the model slips on small gaps
    # (5+ -> 6+ for a "6-8 years" JD), which is still fabrication.
    tailored, yrs_fixed = _clamp_years(tailored, base_resume)
    if yrs_fixed:
        notes.append("years guard: clamped inflated experience claim to base resume")

    # Guard (f): final no-orphan sweep. Guard (c2) already trimmed once, but the
    # tidy passes after it (list caps, dash rewrite) can erase a skill's last
    # piece of evidence — re-measure on the FINAL text so nothing unbacked ships.
    tailored = _drop_unevidenced_skills(tailored, notes)

    # ── 4. SCORE (cheap) ──────────────────────────────────────────────────
    # The score pass reads the FINAL resume + JD and also classifies each target
    # tool as present/missing BY MEANING (RAG = Retrieval-Augmented Generation,
    # containers cover Docker, MLflow covers Machine Learning…). This replaces the
    # old literal-match _recompute_coverage, which false-flagged covered tools as
    # missing whenever the wording differed — the Detected Context chips now come
    # from the model's semantic read, not string matching.
    _target_tools = context.get("target_tools") or []
    scores: dict = {}
    try:
        raw = await chat(SCORE_SYSTEM, score_prompt(job_description, tailored, _target_tools),
                         max_tokens=1400, pass_name="score", **cheap_kw)
        scores = _loads_loose(raw) or {}
    except Exception as exc:  # noqa: BLE001 — scoring is best effort
        notes.append(f"score skipped ({exc})")

    # Coverage chips from the score pass's semantic judgment. Only overwrite the
    # analyze-time (base-resume) present/missing when the score actually returned
    # a classification, and only keep tools that were in the JD target list.
    _sp = [str(x) for x in (scores.get("present") or [])]
    _sm = [str(x) for x in (scores.get("missing") or [])]
    if _sp or _sm:
        _valid = {str(t).lower(): str(t) for t in _target_tools}
        _norm = lambda xs: [_valid[x.lower()] for x in xs if x.lower() in _valid]
        _present, _missing = _norm(_sp), _norm(_sm)
        # any target tool the model forgot to classify → treat as missing
        _classified = {x.lower() for x in _present + _missing}
        _missing += [str(t) for t in _target_tools if str(t).lower() not in _classified]
        context["present"], context["missing"] = _present, _missing
        # ATS = semantic coverage of the JD's skills, judged by MEANING against
        # the final resume (so "governed" covers "data governance", "warehousing"
        # covers "data warehouse" — no literal-match undercount). This is the one
        # ATS number: it drives the panel gate AND the job-card badge, and it
        # agrees with the present/missing chips because it's computed from them.
        _tot = len(_present) + len(_missing)
        if _tot and scores:
            scores["ats"] = {"score": round(len(_present) / _tot * 100),
                             "note": f"{len(_present)}/{_tot} JD skills covered"}
            _g = [g.get("score") for g in (scores.get("ats"), scores.get("recruiter"),
                                           scores.get("hiring_manager")) if isinstance(g, dict)]
            _g = [g for g in _g if isinstance(g, (int, float))]
            if _g:
                scores["overall"] = round(sum(_g) / len(_g))
        if _missing:
            notes.append(f"final coverage: {len(_present)} present, {len(_missing)} missing "
                         f"(ATS {(scores.get('ats') or {}).get('score')})")

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

    try:
        from ai.llm import get_run_usage
        usage = get_run_usage()
    except Exception:  # noqa: BLE001
        usage = {"cost": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": []}

    review = {
        "needs_review": bool(reasons),
        "reasons": reasons,
        "notes": notes,
        "scores": scores,
        "context": context,
        "usage": usage,          # {cost, tokens_in, tokens_out, calls:[...]}
    }
    return tailored, review

