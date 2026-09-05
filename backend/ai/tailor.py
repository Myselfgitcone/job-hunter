"""
StackShift tailoring engine.

Replaces the legacy multi-pass engine (kept at ai/tailor_legacy.py.bak).

Pipeline — 4 AI calls:
  1. ANALYZE  (cheap model)  -> target cloud, company, JD tools, present/missing
  2. TAILOR   (main model)   -> the full rewritten resume
  3. QA (code flags lines, cheap model rewrites only those) -> clichés,
                                repeated verbs, stacked figures, summary tense,
                                dropped-cloud restoration; junk strip and
                                Technologies Used lines are pure code
  4. SCORE    (code)         -> 100-point deterministic score + chips

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
  "baseline_missing": ["<subset of missing that are UNIVERSAL BASELINE competencies>"],
  "equivalent": ["<subset of missing that are a same-category swap for a tool the resume already shows, written as 'JD tool <- base tool', e.g. 'Splunk <- Datadog'>"],
  "bridge_only": ["<subset of missing with NO category match in the resume at all — may only be bridged inside a bullet, never owned>"],
  "responsibilities": ["<6–8 non-tool DUTIES the JD names, in the JD's own nouns>"],
  "jd_tail_starts": "<the first 6-10 words, copied EXACTLY from the JD, of the first paragraph where the posting stops describing the role and starts pay tables, benefits, EEO, legal, about-us or how-to-apply text; '' if the JD has no such tail>"
}

Rules:
- target_cloud = a cloud ONLY if the JD text LITERALLY names it (the words "AWS"/
  "Amazon Web Services", "Azure", or "GCP"/"Google Cloud" must actually appear).
  If no cloud is explicitly named, target_cloud MUST be "None". Do NOT infer a
  cloud from the company, domain, or tools — a Spark/Flink/data role that names no
  cloud is "None". Use "Multi" only if two+ are named and weighted equally.
- target_tools are the JD's OWN WORDS, copied verbatim ("ETL/ELT", "testing
  frameworks", "batch and real-time data architectures", "Git-based
  development"). Never a paraphrased label: no "Batch architecture" for a JD
  that says "batch and real-time data architectures", no "Infrastructure as
  Code" unless the JD says it. An ATS scans for the JD's tokens; a label the
  JD never used earns nothing and a code check removes it.
- target_tools is RANKED, most important first: required beats preferred,
  in the title or summary beats buried in a list, repeated beats mentioned
  once, "must / strong / hands-on" beats "exposure / a plus / or similar".
  The last entries are the ones a resume may skip.
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
  a vendor suite) is NEVER baseline, no matter how essential the JD calls it.
- equivalent vs bridge_only: split the rest of `missing` (after baseline) by
  whether the resume shows a tool of the SAME product category. Datadog ->
  Splunk is equivalent; Kafka -> a message queue is equivalent. A CAD tool,
  an ERP, a domain practice (bill of materials) for a data engineer has no
  category match: bridge_only. A bridge_only tool may be claimed in ONE
  modest bullet of one job and listed in SKILLS, never in the headline.
- responsibilities: what the JD says the person DOES, not what they use.
  Include a duty if it appears in the title, the summary, or the first three
  responsibility lines, or repeats twice anywhere. Use the JD's own nouns
  (e.g. "mentoring junior engineers", "peer code review", "clarifying
  requirements with analysts", "on-call incident response", "stakeholder
  demos", "technical documentation", "writing tests"). 6–8 items, most
  important first. These are tracked and verified like tools.
  Each item is a SHORT noun phrase of 2–6 words, never a whole JD sentence —
  a sentence can never be matched against a bullet.
- PROSE COUNTS AS MUCH AS BULLETS: a JD paragraph such as "you will be
  developing conceptual design, logical database, taxonomy, capacity
  planning, data loading plan, data maintenance plan and security policy"
  is a checklist in disguise. Split every comma-separated list inside prose
  into its items and treat each one exactly like a bullet-point requirement —
  tools go to target_tools, duties go to responsibilities."""


TAILOR_SYSTEM = """You are StackShift, a professional resume writer. You rewrite a
resume so it MIRRORS a specific job description — echoing the JD's responsibilities
and required skills in the candidate's own voice, mapped onto their REAL jobs.
The goal is a clean, human, ATS-strong resume that reads like it was hand-written
for this exact role. Follow every rule EXACTLY.

You receive: the original resume, the JD, and the ANALYSIS block — one shared
reading of the JD that every stage uses. Use each field:
- job_title      → headline (Line 1).
- target_cloud   → the cloud rules.
- industry       → the summary's domain phrase; emphasize base jobs in that industry.
- role_domain    → verb register and which duties lead each job.
- metric_style   → decides which REAL base numbers go first.
- present        → tools already in the resume that MUST keep their bullets. Never drop one.
- missing        → tools to cover via category-equivalent, bridge, or omit.
- baseline_missing → universal duties to weave in (CI/CD, code review, monitoring, on-call).
- responsibilities → EVERY RESPONSIBILITY EARNS A BULLET (below).

================================================================================
OUTPUT FORMAT (plain text — NOT markdown. No #, no **, no code fences.)
================================================================================
Line 1:  `<Candidate Full Name> — <Exact Job Title from the JD>` — em-dash between
         them; the clean, short title only (no suffix, tool, domain, or seniority
         the JD's posting title padded on).
Line 2:  `<phone> | <email> | <City, ST>`   (phone FIRST, then email, then the
         candidate's city and state from the base resume — omit the city part
         if the base has none. No street address, no linkedin.)

Then these sections, in this exact order. Section headers are UPPERCASE with a
trailing colon on their own line. Every bullet starts with "• ".

SUMMARY:
• 4 minimum, 6 maximum. Fixed SLOT ORDER, free sentence shape — vary the
  syntax from resume to resume; never the same sentence skeleton twice.
  Slot 1 (identity): the JD's title, the candidate's REAL years from base
    dates, the JD's most-repeated tools they genuinely have, and the industries
    from the base — in whatever natural sentence carries them.
  Slot 2 (proof): the single strongest REAL achievement from the base, with
    its number if the base has one.
  Slot 3 (lead duty): the top item from `responsibilities`, written as work
    the candidate has done, at their tenure level.
  Slots 4–6 (coverage): one remaining core JD requirement each. Skip a slot
    rather than pad it.
• No slot repeats a tool already named in slot 1. Plain, confident, no
  invented metrics.
• ONE TENSE PER SLOT TYPE: capability slots (1, 3–6) are present tense
  ("Designs…", "Partners…"); a proof slot about the CURRENT job is present
  tense too ("Maintains a 99% SLA at Cargill"); only a proof about a PAST
  employer is past tense. Never "Maintained … at <current employer>".
• SUMMARY IS A PREVIEW, NOT A CLAIM LIST: every tool, platform, or duty named
  in SUMMARY must appear in at least one experience bullet. Write the bullets
  first, then the summary from them. A summary item with no bullet behind it
  either gets its bullet (within the job caps) or leaves the summary.

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
• TOTAL BUDGET: at most 36 skills across ALL categories, and never fewer than
  every `present` tool plus the category-equivalent additions — a real JD
  match is never cut to hit a number; the cap only trims padding. Priority:
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
• EVERY RESPONSIBILITY EARNS A BULLET: each item in `responsibilities` (at most
  8) must appear in at least one experience bullet, in the job where it most
  plausibly happened, in the form the candidate's tenure allows (see VERB
  REGISTER). These are the no-tool bullets already permitted per job. One
  bullet may cover two related duties. A duty that cannot fit within the job
  caps, or has no credible form at this tenure, is dropped — and never
  appears in SUMMARY or SKILLS without a bullet.

PROFESSIONAL EXPERIENCE:
For each job, in this exact shape — the job header line is NOT a bullet:
`<Job Title> @ <Company> | <Location> <Month Year> – <Month Year or Present>`
then the LADDER bullets (STYLE below), each starting with "• ",
then ONE final line (not a bullet): `Technologies Used: <comma-separated tools for THAT job>`.

PROJECTS:
• ONLY if the base resume ALREADY lists real projects. If none, OMIT the whole
  section including its header. NEVER invent a project. If present: keep the real
  ones (up to 3), one polished bullet each, same bullet style.
• If the base has NO job history, PROJECTS becomes the main evidence section:
  keep up to 4 real projects, 2 bullets each, same bullet style as experience.
  Still never invent one.

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
  Length: one clean past-tense sentence, mostly 15–24 words, never past 30;
    every job with 4+ bullets carries one SHORT 8–12-word bullet, and lengths
    vary bullet to bullet.

DO:
- REWRITE the JD's requirement — never paste the JD sentence verbatim. Change the
  words, convert "you will…" (employer wish) into a past achievement, and anchor it
  to the job's real context.
- Cover the JD's key responsibilities across the bullets; weave in the JD's tools.
- Vary wording so the SAME duty phrased in two jobs never reads identically.
- The FIRST use of any acronym writes both forms — "Retrieval-Augmented
  Generation (RAG)", "continuous integration/continuous delivery (CI/CD)" —
  so the ATS matches whichever token the JD uses. After that, either form.

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
- TENURE CEILING: the register is the LOWER of the JD's level and what the
  candidate's real years support. Compute years from the base resume's
  earliest job start to latest end (internships at half weight). Roughly:
  ~1 year owns tasks, ~5 owns pipelines, ~10 owns platforms, ~15 owns strategy
  and teams. A 2-year candidate on a Senior JD gets the Senior HEADLINE and a
  2-year BODY — builder verbs, peer-level duties (onboarding, pairing) instead
  of "mentored the team". The JD's seniority never overrides tenure.
- Either way, vary the opening verbs so bullets don't read repetitively.

Every bullet ends on a complete noun phrase — never on a bare "-ing" word, a
preposition, or a two-word ", improving reliability." tail.

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

LEAD WITH THE JD'S OWN VOCABULARY: the first TWO bullets of every job speak the
JD's dominant technology/discipline (the one it names most); a brand the JD never
mentions does not open a top-two bullet. Where the candidate's real experience
with that dominant tool sits in an older job, keep it there truthfully and make
the SUMMARY and that job's first bullet carry it — never move a tool into a job
that did not use it.

WRITE LIKE A HUMAN:
- Open with a real action verb — never "Responsible for", "Tasked with",
  "Utilized", "Leveraged", "Spearheaded", "Worked on", "Helped with",
  "Involved in", "In charge of".
- No em or en dash inside a bullet or summary line (comma, colon, parentheses,
  "including", "such as" instead); dashes live only in the headline and date ranges.
- No flowery editorial phrases ("with a pragmatic eye toward", "seamlessly",
  "cutting-edge", "robust and scalable" as a pair). Say the plain thing.
- No two bullets in the SAME job start with the same verb; vary sentence shape
  rather than running one "[Verb] [noun] using [tool] to [result]" template.
- 1–2 bullets per job may be a plain duty or collaboration line with no tool in it.
- Do NOT copy JD lines word-for-word. Do NOT append measurement-tool clauses
  ("as measured in PagerDuty", "tracked via CloudWatch"). No vague intensifiers
  (significantly, substantially, meaningfully). Do NOT metric-stuff.

METRIC POLICY: keep EVERY number the base resume states, in its own bullet's
rewrite; invent NONE (no percentage, count, dollar, or time figure the base lacks,
and never a figure copied from the JD); one figure per bullet — a second one
becomes a scale word (terabytes, millions of rows, dozens of feeds). Each job's
strongest real number sits within its first three bullets, behind the JD's
dominant tool.

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
Job 1 ≤ 10 · Job 2 ≤ 7 · Job 3 ≤ 5 · Job 4+ ≤ 4. A skill that cannot fit
within the caps is dropped from SKILLS, not crammed in.
COVERAGE TARGET: at least 90% of `target_tools` (ranked, most important
first) must be named in an experience bullet; only the LAST 10% of the list
may be left out. When the JD names more tools than the ladder has bullets,
fill every job to its cap and let each bullet carry 2–3 JD tools ("Built
streaming pipelines with Kafka, Flink, and Spark Structured Streaming…") —
density beats count.
LENGTH FOLLOWS TENURE: 0–3 years → 1 page · 4–11 years → 2 pages · 12+ years
→ up to 3. If coverage needs more than that, trim in this order: generated
coverage bullets first, then the oldest jobs down to their minimum ladder
count. Never trim an impact bullet or a `present` tool to fit.

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

FOREIGN TOOLS (`bridge_only`): when the JD wants a tool the candidate's base
shows nothing close to, claim it ONCE — one modest scope-of-work bullet in the
single job where it is most plausible, builder verbs, no numbers ("Exposed
curated datasets to internal teams through Flask-based REST endpoints"), and list
it in SKILLS. Never in the headline, never in a second job, never as the lead
bullet of a job. Older bridge phrasing ("patterns transferable to…") is allowed
but no longer required.

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
    the candidate ALREADY works in, write the JD's product name DIRECTLY — in
    bullets and in SKILLS, no "similar to" / "transferable to" phrasing. JD wants
    Splunk and the candidate uses Datadog/Grafana (same observability category)
    → Splunk. JD wants a specific message queue and they use Kafka → fine. Same
    product family = fair to claim. CAP each swap at what the base's real work
    in that category supports: one observability bullet covers ONE observability
    product swap, not three. BRIDGE phrasing is reserved for tools with NO
    category match in the base at all.
  * COMMON AI-DEV tools the candidate plausibly uses (GitHub Copilot) when the JD
    lists them — include. (Genuinely niche ones they don't use — Windsurf, a
    proprietary IDE — stay out.)

- The ONLY tools you leave out are the LAST ~10% of the ranked `target_tools`
  list — the lowest-signal ones (mentioned once, "a plus", nothing close in the
  base). Everything above that line gets a bullet: owned tools directly,
  same-category swaps directly, foreign tools once (see FOREIGN TOOLS).

Judge a gap's importance from the JD: labels if present ("required" vs "preferred
/ a plus"), else frequency, whether it's in the title / summary / first
responsibilities vs buried in a list, wording ("strong / must / hands-on" = core;
"exposure to / a plus / or similar / or equivalent" = peripheral; in an
"X, Y, or equivalent" group one member covers the group), and role-centrality.

Never manufacture gaps by omitting skills the candidate really has; the only
honest gaps are tools they lack and cannot bridge.

================================================================================
GLOBAL RULES
================================================================================
- Preserve real employers, dates, locations, education, and certifications EXACTLY.
- EVERY experience entry keeps its EXACT base-resume title (background checks
  verify them); the JD's role belongs ONLY in the headline.
- Do NOT invent employers, dates, degrees, certifications, or projects.
- YEARS OF EXPERIENCE: state exactly what the base resume supports, never the
  JD's minimum.
- SECURITY CLEARANCE: NEVER claim or imply a clearance (Top Secret, TS, TS/SCI,
  Secret, Public Trust, "TS-clearable", "clearance-eligible") unless the BASE
  resume explicitly states it. If the JD requires one and the resume lacks it,
  OMIT any clearance mention entirely. Same for citizenship claims.
- SCOPE vs TENURE: keep the number of major initiatives realistic for the role's
  duration and level. Do NOT cram 8 architect-level initiatives into a <2-year
  IC "Engineer" role, and do NOT imply Architect scope under an IC title.
- List each employer/role ONCE; never a duplicate entry or a "(See above)" stub.
- If a field (location, dates) is unknown, OMIT it — never "Location Not
  Listed" / "N/A" filler.
- Output plain text only, in the format above. No markdown headers, no asterisks,
  no horizontal rules, no commentary, no code fences."""


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
    def _lst(k: str) -> str:
        v = context.get(k) or []
        return ", ".join(str(x) for x in v) if v else "(none)"
    return (
        "ANALYSIS (one shared reading of the JD — use every field as the rules say):\n"
        f"  job_title:         {context.get('job_title', '')}\n"
        f"  target_cloud:      {context.get('target_cloud', 'None')}\n"
        f"  industry:          {context.get('industry', '')}\n"
        f"  role_domain:       {context.get('role_domain', '')}\n"
        f"  metric_style:      {context.get('metric_style', '')}\n"
        f"  present (KEEP — never drop): {_lst('present')}\n"
        f"  missing:           {_lst('missing')}\n"
        f"  baseline_missing:  {_lst('baseline_missing')}\n"
        f"  equivalent (may be named directly, once): {_lst('equivalent')}\n"
        f"  bridge_only (claim ONCE: one modest bullet in one job + SKILLS; never headline): {_lst('bridge_only')}\n"
        f"  coverage target: name at least {_must_count(context)} of the {len(context.get('target_tools') or [])} ranked tools in bullets; only the last {len(context.get('target_tools') or []) - _must_count(context)} may be skipped\n"
        f"  responsibilities:  {_lst('responsibilities')}\n\n"
        + (("BASE NUMBERS TO KEEP (each stays in its own bullet's rewrite; a code "
            "check restores any you drop and removes any you invent):\n  "
            + "\n  ".join(_base_number_hints(resume_text)) + "\n\n")
           if _base_number_hints(resume_text) else "")
        + "CLOUD SWAP: ALWAYS ON — if a target cloud is named above, convert BOTH "
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

def _skills_claimed(text: str, expand: bool = False) -> list[str]:
    """Items from the SKILLS section category lines. With expand=True the
    members of a parenthesised group are claims too: 'Azure (ADF, Microsoft
    Fabric)' claims Azure, ADF and Microsoft Fabric — each must earn a bullet."""
    items, in_skills = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if _is_section_hdr(s):
            in_skills = "skill" in s.lower()
            continue
        if in_skills and s.startswith(("•", "-", "*")) and ":" in s:
            _, _, rest = s.partition(":")
            for it in _split_list_items(rest):
                it = it.strip()
                if not it:
                    continue
                items.append(it)
                if expand:
                    m = re.search(r"\((.*?)\)", it)
                    if m:
                        items.extend(x.strip() for x in _split_list_items(m.group(1)) if x.strip())
    return items


def _experience_blob(text: str, lower: bool = True) -> str:
    """The evidence part of the resume: the BULLETS under EXPERIENCE / PROJECTS
    headers, lowercased. Technologies Used lines are deliberately excluded —
    a tool that appears only in a tools list has no story behind it, which is
    exactly the orphan this check exists to catch (live miss: Java, Docker,
    Kubernetes "evidenced" by nothing but a Technologies Used mention)."""
    keep, active = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if _is_section_hdr(s):
            up = s.upper()
            active = "EXPERIENCE" in up or "PROJECT" in up
            continue
        if active and s.startswith(_BULLET_PREFIXES) and not _TECH_LINE_RE.match(s):
            keep.append(s)
    blob = "\n".join(keep)
    return blob.lower() if lower else blob


# Vendor/generic words that can't stand in for a whole skill name — "Apache
# Kafka" is evidenced by "Kafka Connect", but "Microsoft Fabric" is NOT
# evidenced by some other "Microsoft" mention.
_SKILL_TOKEN_STOP = {
    "apache", "microsoft", "azure", "amazon", "aws", "gcp", "google", "cloud", "data",
    "actions", "services", "service", "platform", "platforms", "tools",
    "core", "server", "studio", "suite", "enterprise", "analytics",
}


_STEM_STOP = {"and", "the", "for", "with", "from", "into", "across", "using",
              "all", "our", "any", "per", "via", "own"}


def _stems(core: str) -> list[str]:
    """Escaped word stems of a skill/duty phrase ("organizing" -> "organiz")."""
    words = [w for w in re.findall(r"[a-z0-9+#.]+", core.lower())
             if len(w) >= 3 and w not in _STEM_STOP]
    out = []
    for w in words:
        s = w
        for suf in ("ing", "ies", "es", "s"):
            if len(s) > 5 and s.endswith(suf):
                s = s[: -len(suf)]
                break
        out.append(re.escape(s))
    return out


def _stems_in_text(phrase: str, low_text: str) -> bool:
    """Every word stem of `phrase` occurs somewhere in `low_text` (any order,
    any distance). Single-token phrases fall back to a word-boundary match."""
    stems = _stems(phrase)
    if not stems:
        tok = re.escape(phrase.lower().strip())
        return bool(tok) and bool(re.search(rf"(?<![a-z0-9]){tok}(?![a-z0-9])", low_text))
    return all(re.search(rf"\b{st}", low_text) for st in stems)


def _phrase_in_jd(phrase: str, jd: str) -> bool:
    """The JD says this, in these words: literal or in-order loose match
    anywhere, or every word stem inside ONE sentence. A single token (or a
    slash form like PL/SQL) must appear as written."""
    low = jd.lower()
    try:
        from resume_lint import _dynamic_coverage_pattern
        if re.search(_dynamic_coverage_pattern(phrase), low):
            return True
    except Exception:  # noqa: BLE001
        pass
    if "/" in phrase or len(_stems(phrase)) < 2:
        tok = re.escape(phrase.lower().strip())
        return bool(re.search(rf"(?<![a-z0-9]){tok}(?![a-z0-9])", low))
    loose = _loose_pattern(phrase)
    if loose and re.search(loose, low):
        return True
    return any(_stems_in_text(phrase, sent) for sent in re.split(r"[.!?;\n•]", low))


def _loose_pattern(core: str) -> str:
    """Multi-word skill -> stems in order, up to two words apart."""
    stems = _stems(core)
    if len(stems) < 2:
        return ""
    return r"\b" + r"\W+(?:\w+\W+){0,2}".join(st + r"\w*" for st in stems)


def _unevidenced(items: list[str], text: str, strict: bool = False) -> list[str]:
    """The subset of `items` with no supporting line in EXPERIENCE/PROJECTS.
    strict=True keeps only the literal and in-order loose matches plus the
    acronym form ("MDM" proves "Master Data Management") — used for the
    ownership check, where a shared plain word must prove nothing."""
    try:
        from resume_lint import _dynamic_coverage_pattern
    except ImportError:  # pragma: no cover — lint module optional
        return []
    cased = _experience_blob(text, lower=False)
    blob = cased.lower()
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
            # Loose form: the same words with up to two others between them —
            # "Dimensional Modeling" is proven by "dimensional data models".
            loose = _loose_pattern(core)
            if loose and re.search(loose, blob):
                continue
            words = re.findall(r"[A-Za-z]+", core)
            if len(words) >= 3:
                acro = "".join(w[0] for w in words).upper()
                if re.search(rf"(?<![A-Za-z0-9]){re.escape(acro)}(?![A-Za-z0-9])", cased):
                    continue
            if strict:
                out.append(item)
                continue
            # A DUTY phrase ("cleansing, organizing and transforming data") is
            # proven by one bullet that carries all but one of its stems, in
            # any order — same line only, so scattered words never add up.
            stems = _stems(core)
            need = max(2, -(-len(stems) * 3 // 5))      # ceil(60%), at least 2
            if len(stems) >= 3 and any(
                    sum(1 for st in stems if re.search(rf"\b{st}", bl_line)) >= need
                    for bl_line in blob.split("\n")):
                continue
        except re.error:
            continue
        # Fallback: a distinctive token of a multi-word name still counts —
        # "Apache Kafka" is covered by a "Kafka Connect" bullet. Distinctive
        # means the bullets write it as a proper noun (Capitalised) somewhere;
        # a token that only ever appears as a plain English word ("schema" for
        # Star Schema, "management" for Metadata Management) proves nothing.
        # Only a VENDOR-prefixed name gets this fallback ("Apache Kafka",
        # "Microsoft Fabric"); "Key Vault" must not pass on "Data Vault".
        first = re.findall(r"[A-Za-z]+", core)
        vendor_led = bool(first) and first[0].lower() in _SKILL_TOKEN_STOP and len(first) > 1
        toks = [w for w in re.findall(r"[A-Za-z][\w+#.-]{3,}", core)
                if w.lower() not in _SKILL_TOKEN_STOP] if vendor_led else []
        if toks and any(
                re.search(rf"(?<![A-Za-z0-9]){re.escape(w[0].upper() + w[1:].lower())}(?![a-z0-9])", cased)
                or re.search(rf"(?<![A-Za-z0-9]){re.escape(w.upper())}(?![a-z0-9])", cased)
                for w in toks):
            continue
        out.append(item)
    return out


def _dominant_jd_tool(job_description: str, target_tools: list) -> str:
    """The tool the JD leans on hardest — most mentions, ties broken by the
    longer (more specific) name. Derived from the analyze pass's JD-extracted
    tool list, so nothing is hardcoded."""
    jd = (job_description or "").lower()
    best, best_n = "", 0
    for t in target_tools or []:
        name = str(t).strip()
        if len(name) < 3:
            continue
        n = len(re.findall(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", jd))
        if n > best_n or (n == best_n and n > 0 and len(name) > len(best)):
            best, best_n = name, n
    return best if best_n >= 3 else ""


def _promote_tool_bullets(text: str, tool: str, notes: list) -> str:
    """Recruiters scan the first two bullets of each job. If the JD's dominant
    tool is already evidenced further down a job, move that bullet to the top
    of its job. Pure REORDERING — no wording changes, nothing invented, and a
    job that never mentions the tool is left untouched."""
    if not tool:
        return text
    pat = re.compile(rf"(?<![a-z0-9]){re.escape(tool.lower())}(?![a-z0-9])")
    lines = text.split("\n")
    moved = 0
    hdrs = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    for h in hdrs:
        end = _job_block_end(lines, h)
        bullets = [i for i in range(h + 1, end) if lines[i].lstrip().startswith("•")]
        if len(bullets) < 3:
            continue
        if any(pat.search(lines[i].lower()) for i in bullets[:2]):
            continue                      # already up front
        hit = next((i for i in bullets[2:] if pat.search(lines[i].lower())), None)
        if hit is None:
            continue                      # this job genuinely never used it
        bullet = lines.pop(hit)
        lines.insert(bullets[0], bullet)  # becomes this job's first bullet
        moved += 1
        hdrs = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    if moved:
        notes.append(f"lead-bullet guard: promoted {moved} '{tool}' bullet(s) "
                     "to the top of their job")
    return "\n".join(lines)


def _restore_present_tools(text: str, present: list, base_resume: str,
                           notes: list) -> str:
    """`present` = tools the analyze pass saw in the BASE resume that the JD
    wants. They are the candidate's real, defensible keywords; a draft that
    drops one silently loses ATS credit. Restore any that vanished to the
    SKILLS row whose label/items share a word with it (else the last row).
    Only tools actually in the base resume qualify — this never adds a tool
    the candidate does not have."""
    if not present:
        return text
    try:
        from resume_lint import _dynamic_coverage_pattern
    except ImportError:  # pragma: no cover
        return text
    low_all = text.lower()
    base_low = (base_resume or "").lower()
    lost = []
    for t in present:
        name = str(t).strip()
        if len(name) < 2:
            continue
        try:
            pat = _dynamic_coverage_pattern(name)
            if re.search(pat, low_all):
                continue                         # still there
            if not re.search(pat, base_low):
                continue                         # analyze overclaimed — not ours to add
        except re.error:
            continue
        lost.append(name)
    if not lost:
        return text
    lines = text.split("\n")
    rows = []                                    # (index, label, items)
    in_skills = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_section_hdr(s):
            in_skills = "skill" in s.lower()
            continue
        if in_skills and s.startswith(("•", "-", "*")) and ":" in s:
            label, _, rest = s.partition(":")
            rows.append((i, label.lstrip("•-* ").strip(), rest))
    if not rows:
        return text
    _tok = lambda s: set(re.findall(r"[a-z0-9]{3,}", s.lower()))
    # The base resume's own skills row for this tool tells us its category —
    # its label and sibling tools ("ETL: Informatica, Ab Initio") are the
    # best hint for which tailored row it belongs in.
    base_rows = [ln.strip() for ln in base_low.split("\n")
                 if ln.strip().startswith(("•", "-", "*")) and ":" in ln]
    for name in lost:
        hint = _tok(name)
        for br in base_rows:
            if name.lower() in br:
                hint |= _tok(br)
                break
        best, best_n = None, 0
        for i, label, rest in rows:
            n = len(hint & _tok(label + " " + rest))
            if n > best_n:
                best, best_n = i, n
        i = best if best is not None else rows[-1][0]
        lines[i] = lines[i].rstrip().rstrip(",") + ", " + name
    notes.append("present guard: restored " + ", ".join(lost) + " to SKILLS")
    return "\n".join(lines)


def _orphan_skills(text: str) -> list[str]:
    """Skills-section items with no supporting line in EXPERIENCE/PROJECTS."""
    return _unevidenced(_skills_claimed(text, expand=True), text)




def _job_block_end(lines: list[str], start: int) -> int:
    """Index one past the last line of the job whose header sits at `start`."""
    for i in range(start + 1, len(lines)):
        if _is_job_header_line(lines[i]) or _is_section_hdr(lines[i].strip()):
            return i
    return len(lines)


# Hard bullet ceilings by job recency (Job 1, Job 2, Job 3; older jobs 4).
_JOB_BULLET_CAPS = (10, 7, 5)


_COVERAGE_TARGET = 0.90   # share of the ranked JD tool list that must earn a bullet


def _must_count(context: dict) -> int:
    n = len(context.get("target_tools") or [])
    return -(-n * 9 // 10) if n else 0          # ceil(90%)


def _coverage_plan(context: dict) -> tuple[list[str], list[str]]:
    """(must_cover, may_skip): the ranked JD tools split at the 90% line.
    The skip budget is spent on the lowest-ranked foreign tools first, then
    the lowest-ranked of the rest."""
    tools = [str(t) for t in (context.get("target_tools") or [])]
    skip_n = len(tools) - _must_count(context)
    if skip_n <= 0:
        return tools, []
    foreign = {str(x).lower() for x in (context.get("bridge_only") or [])}
    order = sorted(range(len(tools)),
                   key=lambda i: (tools[i].lower() in foreign, i), reverse=True)
    skip_idx = set(order[:skip_n])
    return [t for i, t in enumerate(tools) if i not in skip_idx], \
           [t for i, t in enumerate(tools) if i in skip_idx]


def _job_cap(j: int) -> int:
    return _JOB_BULLET_CAPS[j] if j < len(_JOB_BULLET_CAPS) else 4


def _insert_skill_bullets(resume: str, additions: dict,
                          log: list | None = None) -> tuple[str, int]:
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
        if log is not None:
            log.extend((j, s, b) for s, b in take)
        if tech_i is not None:
            ti = tech_i + len(new_lines)
            skills = ", ".join(s for pair in take
                               for s in re.split(r"\s*\+\s*", pair[0]) if s)
            lines[ti] = lines[ti].rstrip().rstrip(",") + ", " + skills
    return "\n".join(lines), added


def _rewrite_skill_lines(text: str, drop: set[str]) -> tuple[str, list[str]]:
    """Remove every SKILLS item (or parenthesised member) whose normalised
    key is in `drop`. Returns (text, removed_names)."""
    lines = text.split("\n")
    removed: list[str] = []
    in_skills = False
    norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_section_hdr(s):
            in_skills = "skill" in s.lower()
            continue
        if not (in_skills and s.startswith(("•", "-", "*")) and ":" in s):
            continue
        marker = s[0]
        label, _, rest = s.partition(":")
        kept: list[str] = []
        changed = False
        for it in _split_list_items(rest):
            it = it.strip()
            if not it:
                continue
            m = re.search(r"^(.*?)\s*\((.*?)\)\s*$", it)
            if m:
                head, inner = m.group(1).strip(), m.group(2)
                if norm(head) in drop:
                    removed.append(it); changed = True
                    continue
                members = [x.strip() for x in _split_list_items(inner) if x.strip()]
                keep_m = [x for x in members if norm(x) not in drop]
                if len(keep_m) != len(members):
                    removed.extend(x for x in members if x not in keep_m); changed = True
                kept.append(f"{head} ({', '.join(keep_m)})" if keep_m else head)
            elif norm(it) in drop:
                removed.append(it); changed = True
            else:
                kept.append(it)
        if changed:
            indent = ln[: len(ln) - len(ln.lstrip())]
            label = label.lstrip("•-* ").rstrip()
            lines[i] = f"{indent}{marker} {label}: {', '.join(kept)}" if kept else ""
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)), removed


def _drop_unevidenced_skills(text: str, notes: list) -> str:
    """Last resort for the no-orphan invariant: a skill that still has no
    experience bullet after the guard rounds is removed from the SKILLS lines —
    an unbacked keyword hurts more in a screen than its absence costs in ATS."""
    orphans = _orphan_skills(text)
    if not orphans:
        return text
    keys = {re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\(.*\)\s*", " ", o).lower()) for o in orphans}
    out, removed = _rewrite_skill_lines(text, keys)
    if removed:
        notes.append("skills trimmed (no supporting bullet): " + ", ".join(removed))
        return out
    return text


COVERAGE_SYSTEM = """You give resume skills the evidence they lack. You receive each
job's numbered bullets and a list of skills/duties that the resume claims (or
the JD requires) but that appear in NO experience bullet.

For EACH listed item, output ONE line — every item, no skipping. Priority:

  W <bullet number> :: <skill> :: <the full rewritten bullet>
      Weave the skill into an EXISTING bullet of the job where that work
      plausibly happened. Prefer the SHORTEST fitting bullet; never one
      marked FULL. Add as few words as the exact wording needs; keep every
      number, tool and claim already there. This is the default — prefer it.

  N <job number> :: <skill> :: <new bullet>
      Only when no existing bullet of the fitting job can carry it honestly
      AND that job still has ROOM (shown per job). A modest routine
      scope-of-work sentence, 10-22 words, no numbers. Group up to THREE
      related skills in one new bullet, names joined by " + ".

Rules:
- The item's EXACT words must appear in the bullet, verbatim (case may
  change): "data transformation" is proven by the words "data transformation",
  not by "transformed data". An ATS matches tokens, not meaning. Every
  listed item is ABSENT as an exact phrase right now, even when the idea is
  already there — "dbt models" does not contain "dbt Core"; write "dbt Core"
  ("dbt Core models…"). Returning a bullet unchanged is a failed line.
- An item marked NAMED IN THE JD must get a line. Only an unmarked item that
  is foreign to every job may be skipped.
- Match the job's era, industry, stack and verb level. A duty ("code review
  and debugging") is written as routine work, not a headline.
- A bullet number may appear in ONE W line only. To place several items in
  the same bullet, write ONE W line with the items joined by " + " in the
  skill field and all of them named in the text.
- No em or en dashes. No intensifiers. Do not open a new bullet with a verb
  that job already uses.
- Never return a bullet unchanged. If an item truly cannot be placed
  honestly, output exactly:  SKIP :: <item>
Output ONLY these lines."""


_COST_CAP = 0.080      # dollars; optional passes are skipped past this spend
_WEAVE_MAX_WORDS = 44  # a bullet already this long takes no more weaving


def _under_cost_cap(notes: list, label: str) -> bool:
    """Optional passes (second coverage round, line-fix retry, fragment fix)
    only run while the current run's spend is under the cap, so a cold run
    (rules block not cached) never drifts past ~8.5c."""
    try:
        from ai.llm import get_run_usage
        spent = float(get_run_usage().get("cost") or 0.0)
    except Exception:  # noqa: BLE001
        return True
    if spent >= _COST_CAP:
        notes.append(f"cost cap: skipped {label} (spent {spent * 100:.1f}c of {_COST_CAP * 100:.0f}c)")
        return False
    return True


async def _ensure_skill_bullets(resume: str, job_description: str,
                                notes: list, jd_missing: list | None = None,
                                inserted: list | None = None,
                                jd_terms: list | None = None,
                                must_tools: list | None = None,
                                foreign: list | None = None,
                                **cheap_kw) -> str:
    """A skill listed in SKILLS with zero experience bullets behind it dies in
    the first interview question. Orphans are detected in code; one cheap
    call weaves each into an existing bullet of the right job or, when no
    bullet fits and the job has room, writes a new one; code applies and
    verifies every line. `jd_missing` (the analyze pass's baseline duties and
    responsibilities) is chased the same way. JD-named items still lacking
    evidence after the first round get one more, smaller round (under the
    cost cap); whatever is left leaves SKILLS."""
    baseline = [str(m) for m in (jd_missing or []) if not _is_soft_skill(str(m))]
    long_items = [b for b in baseline if len(b.split()) > 14]
    if long_items:
        baseline = [b for b in baseline if b not in long_items]
        notes.append(f"coverage guard: {len(long_items)} duty item(s) too long to "
                     "verify, skipped: " + "; ".join(x[:60] for x in long_items))
    jd_low = [str(t).lower() for t in (jd_terms or [])]

    def _in_jd(o: str) -> bool:
        ol = o.lower()
        return any(ol in t or t in ol for t in jd_low)

    must = [str(t) for t in (must_tools or [])]
    rank = {t.lower(): i for i, t in enumerate(must)}
    foreign_low = {str(x).lower() for x in (foreign or [])}

    def _chase(text: str) -> list[str]:
        items = _unevidenced(must, text) + _orphan_skills(text) + _unevidenced(baseline, text)
        seen: set = set()
        items = [o for o in items if not (o.lower() in seen or seen.add(o.lower()))]
        # ranked JD tools first (in JD importance order), then duties, then
        # the writer's own SKILLS items that the JD never asked for
        items.sort(key=lambda o: rank.get(o.lower(), 10_000 if _in_jd(o) else 20_000))
        return items

    _placed = [0]           # items placed across rounds (closure counter)

    async def _round(text: str, chase: list[str], label: str, loud: bool = False) -> str:
        lines = text.split("\n")
        jobs = _job_bullet_lines(text)
        if not jobs:
            return text
        hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
        numbered, n_to_idx, n = [], {}, 0
        for j, bl in jobs:
            room = max(0, _job_cap(j) - len(bl))
            numbered.append(f"\nJOB {j + 1} (room for {room} new bullet(s)): {lines[hdr_idx[j]].strip()}")
            for i in bl:
                n += 1
                n_to_idx[n] = i
                body_txt = lines[i].lstrip()[1:].strip()
                full = "  [FULL: do not weave here]" if len(body_txt.split()) > _WEAVE_MAX_WORDS else ""
                numbered.append(f"{n}. {body_txt}{full}")
        try:
            out = (await chat(
                COVERAGE_SYSTEM,
                "BULLETS:" + "\n".join(numbered)
                + ("\n\nYOUR LAST ANSWER RETURNED EVERY BULLET UNCHANGED. None of these "
                   "phrases appears verbatim anywhere. Rewrite each chosen bullet so the "
                   "exact phrase is IN the text.\n" if loud else "")
                + "\n\nITEMS WITH NO BULLET:\n"
                + "\n".join(f"- {o}" + ("  (FOREIGN: one new bullet in one job, or weave into that job's scope bullet)"
                                        if o.lower() in foreign_low else
                                        "  (NAMED IN THE JD: must be placed)" if _in_jd(o) else "")
                            for o in chase[:16])
                + f"\n\nJOB DESCRIPTION (context):\n{job_description[:3000]}",
                max_tokens=3000, pass_name=label, **cheap_kw)).strip()
        except Exception as exc:  # noqa: BLE001 — best effort
            notes.append(f"{label} skipped ({exc})")
            return text

        woven, rejected = [], []
        used: dict[int, list] = {}
        originals: dict[int, str] = {}
        additions: dict[int, list] = {}
        for ln in out.splitlines():
            sk = re.match(r"^\s*SKIP\s*::\s*(.+?)\s*$", ln, re.I)
            if sk:
                for p in re.split(r"\s*\+\s*", sk.group(1)):
                    if p.strip():
                        given_up.add(p.strip().lower())
                rejected.append(f"{sk.group(1).strip()} (model skipped)")
                continue
            m = re.match(r"^\s*([WN])\s*(\d+)\s*::\s*(.+?)\s*::\s*(.+?)\s*$", ln, re.I)
            if not m:
                continue
            kind, num, skill, body = m.group(1).upper(), int(m.group(2)), m.group(3).strip(), m.group(4)
            body = re.sub(r"\s*[—–]\s*", ", ", body.strip().lstrip("•-* ").strip())
            if not body:
                rejected.append(f"{skill} (empty)")
                continue
            # one filler word must not cost four tools: strip it, keep the line
            body = re.sub(r"[ \t]{2,}", " ", re.sub(r"\s+([,.;])", r"\1", _INTENSIFIER_RE.sub("", body))).strip()
            if kind == "W":
                i = n_to_idx.get(num)
                if i is None:
                    rejected.append(f"{skill} (bad bullet number)")
                    continue
                # the ORIGINAL bullet is what the model rewrote; a second line
                # for the same bullet is accepted only if it also carries the
                # skills already woven there this round (a superset rewrite)
                old = originals.get(i) or lines[i].lstrip()[1:].strip()
                originals.setdefault(i, old)
                parts = [p.strip() for p in re.split(r"\s*\+\s*", skill) if p.strip()]
                need = parts + [p for p in used.get(i, []) if p not in parts]
                grew = len(body.split()) - len(old.split())
                same_nums = _num_tokens(old) == _num_tokens(body)
                # a product name must appear as written; a competency phrase
                # ("streaming architecture") is proven by its word stems in any
                # order ("streaming … architectures")
                proves = all(
                    not _unevidenced([p], "EXPERIENCE:\nX @ Y | Z\n• " + body)
                    or (not p[0].isupper() and _stems_in_text(p, body.lower()))
                    for p in need)
                room_ok = len(old.split()) <= _WEAVE_MAX_WORDS
                grow_ok = 0 <= grew <= max(6 * len(need) + 4, len(" ".join(need).split()) + 10)
                if room_ok and grow_ok and same_nums and proves:
                    lines[i] = "• " + body
                    used[i] = need
                    woven.append(skill)
                else:
                    if grew == 0:            # an echo: the model will not place this
                        for p in parts:
                            echoes[p.lower()] = echoes.get(p.lower(), 0) + 1
                            if echoes[p.lower()] >= 2:
                                given_up.add(p.lower())
                    rejected.append(f"{skill} (grew {grew}, nums {'ok' if same_nums else 'changed'}, "
                                    f"{'named' if proves else 'not named'})")
            else:
                j = num - 1
                if not (0 <= j < len(jobs)) or not 6 <= len(body.split()) <= 34 or _num_tokens(body):
                    rejected.append(f"{skill} (new bullet: bad job, length, or has a figure)")
                    continue
                additions.setdefault(j, []).append((skill, body))
        text = "\n".join(lines)
        added = 0
        if additions:
            text, added = _insert_skill_bullets(text, additions, log=inserted)
        left = len(_chase(text))
        _placed[0] += len(woven) + added
        notes.append(f"{label}: {len(chase)} chased, {len(woven)} woven"
                     + (" (" + ", ".join(woven) + ")" if woven else "")
                     + f", {added} new bullet(s), {left} still unevidenced"
                     + (f"; rejected {len(rejected)}: " + "; ".join(rejected) if rejected else ""))
        return text

    # Batches of 12 in importance order, as many rounds as the target needs.
    # Coverage is what the run is for, so these rounds are never cost-capped;
    # a batch that places nothing ends the loop.
    given_up: set = set()          # items the model skipped or echoed twice
    echoes: dict[str, int] = {}
    for rnd in range(1, 5):
        chase = [o for o in _chase(resume) if o.lower() not in given_up]
        if rnd > 1:
            chase = [o for o in chase if _in_jd(o)]
        if not chase:
            break
        placed_before = _placed[0]
        resume = await _round(resume, chase[:12], f"coverage_{rnd}" if rnd > 1 else "coverage")
        if _placed[0] == placed_before and rnd == 1:
            # The model sometimes hands every bullet back untouched because it
            # judged the idea "already there". One louder retry.
            chase = [o for o in chase if o.lower() not in given_up]
            if chase:
                resume = await _round(resume, chase[:12], "coverage_retry", loud=True)
        if _placed[0] - placed_before < 2:
            break                      # a round that barely moves is not worth another
    # Whatever still lacks a bullet leaves the SKILLS list — no orphans, ever.
    return _drop_unevidenced_skills(resume, notes)


def _enforce_caps(text: str, base_resume: str, notes: list, keep_tool: str = "") -> str:
    """The writer is told the per-job caps but overshoots; trim from the end
    of the job, keeping any bullet that carries a real base figure or names
    the JD's dominant tool as long as another one is available."""
    lines = text.split("\n")
    base_nums = _num_tokens(base_resume)
    gone: set[int] = set()

    def _precious(i: int) -> bool:
        if _num_tokens(lines[i]) & base_nums:
            return True
        return bool(keep_tool) and not _unevidenced([keep_tool], "EXPERIENCE:\nX @ Y | Z\n" + lines[i])
    for j, bl in _job_bullet_lines(text):
        cap = _job_cap(j)
        live = list(bl)
        while len(live) > cap:
            victim = next((i for i in reversed(live) if not _precious(i)), live[-1])
            gone.add(victim)
            live.remove(victim)
    if gone:
        notes.append(f"cap guard: trimmed {len(gone)} bullet(s) over the "
                     f"{'/'.join(str(c) for c in _JOB_BULLET_CAPS)}/{_job_cap(9)} caps")
    return "\n".join(ln for i, ln in enumerate(lines) if i not in gone)


# ── Score in code: no model call ─────────────────────────────────────────────

def _covered_anywhere(items: list[str], text: str) -> tuple[list[str], list[str]]:
    """Split items into (present, missing) against the WHOLE resume — a tool
    in SKILLS already has a bullet behind it after the orphan guard, so any
    mention counts here."""
    body = "EXPERIENCE:\nX @ Y | Z\n" + "\n".join(
        "• " + ln.strip().lstrip("• ") for ln in text.split("\n")
        if ln.strip() and not _is_section_hdr(ln.strip()) and not _is_job_header_line(ln))
    present, missing = [], []
    for it in items:
        (missing if _unevidenced([str(it)], body) else present).append(str(it))
    return present, missing


def _code_score(tailored: str, base_resume: str, job_description: str,
                context: dict, inserted: list) -> dict:
    """100-point deterministic score: tools 40, duties 15, title 5, orphans 10,
    numbers 10, readability 10, page fit 10. The three UI gates are views of
    the same points so the panel, badge and chips always agree."""
    fixes: list[str] = []
    tools = [str(t) for t in (context.get("target_tools") or [])]
    present, missing = _covered_anywhere(tools, tailored)
    must, may_skip = _coverage_plan(context)
    must_missing = [m for m in missing if m in must]
    # Tools are scored against the 90% list: the bottom 10% is skipped by
    # design and must not cost points.
    t_pts = 40 * (len(must) - len(must_missing)) / len(must) if must else 40
    target_met = not must_missing
    if missing:
        fixes.append(("Coverage target missed. " if not target_met else "")
                     + "Missing JD tools: " + ", ".join(missing[:6]))

    duties = [str(d) for d in (context.get("responsibilities") or []) if len(str(d).split()) <= 10]
    d_missing = _unevidenced(duties, tailored)
    d_pts = 15 * (len(duties) - len(d_missing)) / len(duties) if duties else 15
    if d_missing:
        fixes.append("JD duties without a bullet: " + "; ".join(x[:40] for x in d_missing[:4]))

    first = tailored.split("\n", 1)[0]
    head_title = first.partition("—")[2].strip().lower()
    jd_title = (context.get("job_title") or "").strip().lower()
    if jd_title and head_title == jd_title:
        ti_pts = 5
    elif jd_title and _role_family(head_title) and _role_family(head_title) == _role_family(jd_title):
        ti_pts = 3
    else:
        ti_pts = 0
        fixes.append("Headline does not carry the JD title")

    orphans = _orphan_skills(tailored)
    o_pts = max(0, 10 - 2 * len(orphans))
    if orphans:
        fixes.append("Skills without a bullet: " + ", ".join(orphans[:5]))

    invented, dropped, removed = _number_audit(tailored, base_resume, job_description)
    n_pts = max(0, 10 - 3 * len(invented) - 2 * len(dropped) - len(removed))
    if invented:
        fixes.append("Figures not in the base resume: " + ", ".join(sorted(set().union(*[f for _, f in invented])))[:80])
    if dropped:
        fixes.append(f"{len(dropped)} base figure(s) dropped from their bullets")

    lines = tailored.split("\n")
    r_pen, r_why = 0, []
    body_idx = _summary_lines(tailored) + [i for _, bl in _job_bullet_lines(tailored) for i in bl]
    n_int = sum(len(_INTENSIFIER_RE.findall(lines[i])) for i in body_idx)
    n_dash = sum(len(re.findall(r"[—–]", lines[i])) for i in body_idx)
    if n_int:
        r_pen += 2 * n_int; r_why.append(f"{n_int} intensifier(s)")
    if n_dash:
        r_pen += 2 * n_dash; r_why.append(f"{n_dash} dash(es) in body")
    for j, bl in _job_bullet_lines(tailored):
        wc = [len(lines[i].split()) - 1 for i in bl]
        if len(bl) >= 4 and min(wc) > _SHORT_MAX:
            r_pen += 2; r_why.append(f"job {j + 1}: no short bullet")
        r_pen += sum(1 for w in wc if w > 35)
        verbs = [re.match(r"[A-Za-z-]+", lines[i].lstrip()[1:].strip()) for i in bl]
        verbs = [v.group(0).lower() for v in verbs if v]
        r_pen += len(verbs) - len(set(verbs))
        r_pen += 2 * sum(1 for i in bl if _CLICHE_RE.match(lines[i].lstrip()[1:].strip()))
    r_pts = max(0, 10 - r_pen)
    if r_why:
        fixes.append("Readability: " + "; ".join(r_why[:3]))

    budget = _page_budget(base_resume) * _WORDS_PER_PAGE
    words = len(tailored.split())
    over = max(0.0, (words - budget) / budget)
    p_pts = max(0, 10 - int(over / 0.05))
    if p_pts < 10:
        fixes.append(f"{words} words for a {_page_budget(base_resume)}-page budget of {budget}")

    overall = round(t_pts + d_pts + ti_pts + o_pts + n_pts + r_pts + p_pts)
    ats = round((t_pts + d_pts) / 55 * 100)
    recruiter = round((r_pts + ti_pts + p_pts) / 25 * 100)
    hm = round((o_pts + n_pts) / 20 * 100)
    return {
        "overall": overall,
        "ats": {"score": ats, "note": f"{len(present)}/{len(tools)} JD tools, "
                                      f"{len(duties) - len(d_missing)}/{len(duties)} duties covered"},
        "recruiter": {"score": recruiter, "note": f"readability {r_pts}/10, title {ti_pts}/5, page fit {p_pts}/10"},
        "hiring_manager": {"score": hm, "note": f"orphans {o_pts}/10, figures {n_pts}/10"},
        "points": {"tools": round(t_pts, 1), "duties": round(d_pts, 1), "title": ti_pts,
                   "orphans": o_pts, "numbers": n_pts, "readability": r_pts, "page_fit": p_pts},
        "coverage_target": {"need": len(must), "have": len(must) - len(must_missing),
                            "met": target_met, "skipped_by_design": may_skip},
        "top_fixes": fixes[:5],
        "present": present,
        "missing": missing,
    }


# ── Guard: a SKILLS item must be something the candidate owns ────────────────

def _trim_jd_tail(jd: str, marker) -> tuple[str, int]:
    """Cut the JD at the analyze pass's tail marker, but only when the marker
    is a real quote sitting in the back half of the text — a mis-quote or a
    marker near the top leaves the JD untouched."""
    m = re.sub(r"\s+", " ", str(marker or "")).strip()
    if len(m.split()) < 2:
        return jd, 0
    words = [re.escape(w) for w in m.split()[:8]]
    hit = re.search(r"\s+".join(words), re.sub(r"[ \t]+", " ", jd), re.I)
    if not hit:
        return jd, 0
    pos = hit.start()
    if pos < len(jd) * 0.30 or pos < 1200 or len(jd) - pos < 200:
        return jd, 0
    return jd[:pos].rstrip(), len(jd) - pos


def _base_wrapped(base_resume: str) -> str:
    """Whole base resume as one evidence blob for _unevidenced (every
    non-header line counts, the base is the candidate's own truth)."""
    return "EXPERIENCE:\nX @ Y | Z\n" + "\n".join(
        "• " + ln.strip().lstrip("• ") for ln in base_resume.split("\n")
        if ln.strip() and not _is_section_hdr(ln.strip()) and not _is_job_header_line(ln))


def _strip_unowned_skills(text: str, base_resume: str, context: dict, notes: list) -> str:
    """The writer may bridge a JD tool inside a bullet ("analogous to BoM
    management") but may never list it as an owned skill. Live miss: an
    aerospace JD produced a SKILLS row of Engineering BoM, Manufacturing BoM,
    Change Management — none anywhere in the base. Allowed in SKILLS: what
    the base resume states, a universal baseline duty, or a same-category
    swap the analyze pass named. Everything else leaves SKILLS."""
    base_blob = _base_wrapped(base_resume)
    # Anything the JD asks for may be owned now (the user's 90% rule: a
    # foreign tool gets one modest bullet). What stays out of SKILLS is the
    # writer's own invention: neither in the base nor asked for by the JD.
    allowed_lists = [str(x).lower() for x in
                     (context.get("baseline_missing") or []) + (context.get("equivalent") or [])
                     + (context.get("target_tools") or []) + (context.get("bridge_only") or [])]
    drop: set[str] = set()
    names: list[str] = []
    for it in _skills_claimed(text, expand=True):
        core = re.sub(r"\s*\(.*\)\s*", " ", it).strip()
        if not core:
            continue
        if not _unevidenced([core], base_blob, strict=True):
            continue
        # "Amazon Redshift" is owned when the base says "Redshift": drop the
        # vendor prefix and look again.
        words = core.split()
        while len(words) > 1 and words[0].lower() in _SKILL_TOKEN_STOP:
            words = words[1:]
        if len(words) < len(core.split()) and not _unevidenced([" ".join(words)], base_blob, strict=True):
            continue
        cl = core.lower()
        if any(cl in a or a in cl for a in allowed_lists):
            continue
        drop.add(re.sub(r"[^a-z0-9]", "", core.lower()))
        names.append(core)
    if not drop:
        return text
    out, removed = _rewrite_skill_lines(text, drop)
    if removed:
        notes.append("owned-skill guard: removed from SKILLS (not in base, not baseline, "
                     "not an equivalent swap): " + ", ".join(removed))
    return out


# ── Guard: a tool stays in the jobs where the base says it was used ──────────

def _base_tool_list(base_resume: str) -> list[str]:
    """The base resume's own skills list — the flat comma list under its
    SKILLS header — plus any '• Category: a, b' rows it may use."""
    tools: list[str] = []
    in_skills = False
    for ln in base_resume.split("\n"):
        s = ln.strip()
        if _is_section_hdr(s):
            in_skills = "skill" in s.lower()
            continue
        if not in_skills or not s:
            continue
        rest = s.partition(":")[2] if (s.startswith(("•", "-", "*")) and ":" in s) else s
        for it in _split_list_items(rest):
            it = it.strip()
            if it:
                tools.append(it)
                m = re.search(r"\((.*?)\)", it)
                if m:
                    tools.extend(x.strip() for x in _split_list_items(m.group(1)) if x.strip())
    return tools


def _base_job_blocks(base_resume: str) -> dict[str, str]:
    """{company_key: lowercased bullets of that job} — stops at the next job
    or section header, so the skills list never counts as a job."""
    lines = base_resume.split("\n")
    out: dict[str, str] = {}
    for i, ln in enumerate(lines):
        if not _is_job_header_line(ln):
            continue
        m = _JOB_HDR_RE.search(ln)
        if not m:
            continue
        end = _job_block_end(lines, i)
        out[m.group(1).strip().lower()] = "\n".join(lines[i + 1:end]).lower()
    return out


def _scope_leaks(text: str, base_resume: str, context: dict,
                 jd_text: str = "") -> dict[int, list[str]]:
    """{tailored line index: [tools]} where a bullet names a tool the base
    resume uses at OTHER jobs but not at this one. Tools the base lists only
    in its skills section (no job) float freely. Under an active cloud swap
    the target cloud's services are exempt in the two swapped jobs."""
    base_jobs = _base_job_blocks(base_resume)
    if not base_jobs:
        return {}
    target = (context.get("target_cloud") or "None")
    swap = target in _CLOUD_SIG
    # the target cloud's own services, read from the base's "AWS (S3, EMR, …)"
    # style groups: legitimate in the two swapped jobs
    family: set[str] = set()
    if swap:
        for m in re.finditer(rf"\b{re.escape(target)}\b[^(\n]{{0,20}}\(([^)]*)\)", base_resume, re.I):
            family.update(x.strip().lower() for x in _split_list_items(m.group(1)) if x.strip())
    universe = {str(t) for t in (context.get("target_tools") or [])}
    universe.update(_base_tool_list(base_resume))
    universe.update(_skills_claimed(text, expand=True))

    def _hits(tool: str, blob: str) -> bool:
        try:
            from resume_lint import _dynamic_coverage_pattern
            return bool(re.search(_dynamic_coverage_pattern(tool), blob))
        except Exception:  # noqa: BLE001
            return tool.lower() in blob

    anchored: dict[str, set[str]] = {}
    for tool in universe:
        core = re.sub(r"\s*\(.*\)\s*", " ", tool).strip()
        if len(core) < 3 or _is_soft_skill(core):
            continue
        # Only proper nouns are products that belong to a job ("Snowflake",
        # "Data Vault 2.0"); a lowercase practice ("data contracts", "schema
        # enforcement") is vocabulary and may describe any job.
        if not core[0].isupper():
            continue
        where = {c for c, b in base_jobs.items() if _hits(core, b)}
        if where:
            anchored[core] = where
    lines = text.split("\n")
    hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    leaks: dict[int, list[str]] = {}
    for j, h in enumerate(hdr_idx):
        m = _JOB_HDR_RE.search(lines[h])
        company = m.group(1).strip().lower() if m else ""
        if company not in base_jobs:
            continue
        end = _job_block_end(lines, h)
        for i in range(h + 1, end):
            s = lines[i].strip()
            if not s.startswith("•") or _TECH_LINE_RE.match(s):
                continue
            low = s.lower()
            for tool, where in anchored.items():
                if company in where or not _hits(tool, low):
                    continue
                if swap and j < 2 and (any(sig.strip() in tool.lower() for sig in _CLOUD_SIG[target])
                                       or tool.lower() in family):
                    continue
                # A short all-caps acronym the JD itself uses is ambiguous
                # vocabulary, not a product (EMR = electronic medical records
                # in a hospital JD, RBAC = a practice): never a leak.
                if re.fullmatch(r"[A-Z0-9]{2,4}", tool) and re.search(rf"\b{re.escape(tool)}\b", jd_text):
                    continue
                leaks.setdefault(i, []).append(tool)
    # A foreign tool (nothing like it in the base) may be claimed in ONE job
    # only; every mention after the first job is a leak.
    for tool in (context.get("bridge_only") or []):
        core = re.sub(r"\s*\(.*\)\s*", " ", str(tool)).strip()
        if len(core) < 3:
            continue
        seen_job = None
        for j, h in enumerate(hdr_idx):
            end = _job_block_end(lines, h)
            for i in range(h + 1, end):
                s = lines[i].strip()
                if not s.startswith("•") or _TECH_LINE_RE.match(s) or not _hits(core, s.lower()):
                    continue
                if seen_job is None:
                    seen_job = j
                elif j != seen_job:
                    leaks.setdefault(i, []).append(core)
    return leaks


async def _fix_scope_leaks(text: str, base_resume: str, context: dict, notes: list,
                           jd_text: str = "", **cheap_kw) -> str:
    leaks = _scope_leaks(text, base_resume, context, jd_text)
    if not leaks:
        return text
    jobs = {i: ("Remove " + ", ".join(f"'{t}'" for t in ts)
                + " from this bullet: the candidate did not use "
                + ("it" if len(ts) == 1 else "them") + " in this job. Keep every other tool, "
                "number and claim; if the bullet was only about that tool, describe the "
                "same work with the tools that remain.")
            for i, ts in leaks.items()}
    before = text.split("\n")
    fixed = await _fix_lines(text, jobs, notes, "scope_fix", **cheap_kw)
    after = fixed.split("\n")
    if len(after) != len(before):
        notes.append("scope guard: fix rejected (line count changed)")
        return text
    claimed = _skills_claimed(text, expand=True)
    ok, bad = 0, []
    for i, ts in leaks.items():
        new = after[i]
        still = [t for t in ts if not _unevidenced([t], "EXPERIENCE:\nX @ Y | Z\n" + new)]
        gone_low = [t.lower() for t in ts]
        lost = [sk for sk in _line_skills(before[i], claimed)
                if sk not in _line_skills(new, claimed)
                and not any(g in sk.lower() or sk.lower() in g for g in gone_low)]
        nums_ok = _num_tokens(before[i]) == _num_tokens(new)
        # Truth outranks a keyword: a fix that removes the leak is kept even
        # if a woven skill went with it (the orphan guard trims that skill).
        if not still and nums_ok and len(new.split()) >= 6:
            ok += 1
            if lost:
                bad.append(f"line {i}: fixed, lost {', '.join(lost)}")
        else:
            after[i] = before[i]
            bad.append(f"line {i}: " + (f"still names {', '.join(still)}" if still else
                                        "figure changed" if not nums_ok else "too short"))
    notes.append(f"scope guard: {sum(len(v) for v in leaks.values())} tool mention(s) outside "
                 f"the job the base places them in; {ok} bullet(s) fixed"
                 + (f"; unresolved {len(bad)}: " + "; ".join(bad) if bad else "")
                 + " — " + "; ".join(f"line {i}: {', '.join(ts)}" for i, ts in leaks.items()))
    return "\n".join(after)


# ── Guard: numbers — every real base figure survives, no figure is invented ──

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_NUM_WORD_RE = re.compile(r"\b(" + "|".join(_NUM_WORDS) + r")\b(?=[\s-])", re.I)
_NUM_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.])(sub-)?(\$)?(\d[\d,]*(?:\.\d+)?)\s*"
    r"(%|\+|[kKmMbB](?![a-z])|[xX](?![a-z])|ms\b|TB\+?|GB\+?|PB\+?|"
    r"-?\s?(?:hours?|hrs?|hour)\b|-?\s?(?:minutes?|mins?|minute)\b|"
    r"-?\s?seconds?\b|-?\s?(?:days?|weeks?|months?)\b)?"
)
_UNIT_NORM = {
    "k": "k", "m": "m", "b": "b", "x": "x", "%": "%", "+": "+", "ms": "ms",
    "tb": "tb", "gb": "gb", "pb": "pb", "hour": "h", "hours": "h", "hr": "h",
    "hrs": "h", "minute": "min", "minutes": "min", "min": "min", "mins": "min",
    "second": "s", "seconds": "s", "day": "d", "days": "d", "week": "w",
    "weeks": "w", "month": "mo", "months": "mo",
}


def _num_tokens(text: str) -> set[str]:
    """Canonical numeric figures in `text` — '40%', '$100K', '2-hour', 'six
    hours' all become stable keys ('40%', '100k$', '2h', '6h') so a base
    figure and its tailored rewording compare equal. Years, phone numbers,
    version tags (Vault 2.0, SOC 2) and bare tiny counts are ignored: they are
    labels, not claims."""
    t = _NUM_WORD_RE.sub(lambda m: str(_NUM_WORDS[m.group(1).lower()]), text)
    t = _YEAR_RE.sub(" ", t)
    t = _HDR_PHONE_RE.sub(" ", t)
    out: set[str] = set()
    for m in _NUM_TOKEN_RE.finditer(t):
        sub, dollar, num, unit = m.groups()
        raw = num.replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        unit = (unit or "").strip().lstrip("-").strip().lower()
        unit = _UNIT_NORM.get(unit, unit)
        if not unit and not dollar and val <= 3:
            continue                      # "SOC 2", "Vault 2.0", "two teams"
        if val == 1 and unit not in ("%", "k", "m", "b", "x") and not dollar:
            continue                      # "under one hour" = "under an hour"
        key = (raw.rstrip("0").rstrip(".") if "." in raw else raw) + unit
        if sub:
            key = "sub" + key
        out.add(key)
    return out


def _content_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9+#.]{3,}", s.lower())
            if w not in {"with", "that", "from", "across", "using", "into",
                         "through", "over", "under", "their", "this", "data"}}


def _job_bullet_lines(text: str) -> list[tuple[int, list[int]]]:
    """[(job_index, [line indexes of that job's bullets])] — Technologies
    Used lines excluded."""
    lines = text.split("\n")
    hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    out = []
    for j, h in enumerate(hdr_idx):
        end = _job_block_end(lines, h)
        out.append((j, [i for i in range(h + 1, end)
                        if lines[i].lstrip().startswith("•")
                        and not _TECH_LINE_RE.match(lines[i].strip())]))
    return out


def _summary_lines(text: str) -> list[int]:
    lines, out, in_sum = text.split("\n"), [], False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_section_hdr(s):
            in_sum = "summary" in s.lower()
            continue
        if in_sum and s:
            out.append(i)
    return out


def _base_number_hints(base_resume: str) -> list[str]:
    """'Cargill: 40% (stale-data incidents)' style reminders for the tailor
    prompt — the writer sees every real figure it must carry over."""
    hints = []
    for company, body in _split_jobs(base_resume):
        for ln in body.splitlines():
            s = ln.strip()
            if not s.startswith(_BULLET_PREFIXES):
                continue
            nums = _num_tokens(s)
            if not nums:
                continue
            found = [m.group(0).strip() for m in _NUM_TOKEN_RE.finditer(
                _NUM_WORD_RE.sub(lambda m: str(_NUM_WORDS[m.group(1).lower()]), s))
                     if _num_tokens(m.group(0))]
            words = re.sub(r"^[•\-*\s]+", "", s).split()
            hints.append(f"{company.title()}: {', '.join(dict.fromkeys(found))} "
                         f"(bullet: \"{' '.join(words[:7])}…\")")
    return hints


def _number_audit(tailored: str, base_resume: str, job_description: str):
    """Deterministic read of the tailored text against the base and the JD.
    Returns (invented, dropped, removed_bullets):
      invented  — [(line_idx, {figures})]  figures in neither base nor JD
      dropped   — [(line_idx, {figures})]  base figures missing from the
                  tailored bullet that clearly descends from that base bullet
      removed   — [str] base bullets carrying figures with no descendant at all
    """
    allowed = _num_tokens(base_resume) | _num_tokens(job_description)
    base_all = _num_tokens(base_resume)
    lines = tailored.split("\n")
    body_idx = _summary_lines(tailored) + [i for _, bl in _job_bullet_lines(tailored) for i in bl]
    invented = []
    for i in body_idx:
        bad = _num_tokens(lines[i]) - allowed
        if bad:
            invented.append((i, bad))

    dropped, removed = [], []
    t_jobs = {c: b for c, b in _split_jobs(tailored)}
    # map company -> tailored line indexes of its bullets
    t_lines: dict[str, list[int]] = {}
    hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    for h in hdr_idx:
        c = _JOB_HDR_RE.search(lines[h]).group(1).strip().lower()
        end = _job_block_end(lines, h)
        t_lines[c] = [i for i in range(h + 1, end)
                      if lines[i].lstrip().startswith("•")
                      and not _TECH_LINE_RE.match(lines[i].strip())]
    for company, body in _split_jobs(base_resume):
        if company not in t_lines:
            continue
        job_nums = _num_tokens(t_jobs.get(company, ""))
        for ln in body.splitlines():
            s = ln.strip()
            if not s.startswith(_BULLET_PREFIXES):
                continue
            nums = _num_tokens(s) & base_all
            if not nums or nums <= job_nums:
                continue
            bw = _content_words(s)
            best, best_i = 0.0, None
            for i in t_lines[company]:
                tw = _content_words(lines[i])
                if not bw or not tw:
                    continue
                jac = len(bw & tw) / len(bw | tw)
                if jac > best:
                    best, best_i = jac, i
            missing = nums - job_nums
            if best >= 0.22 and best_i is not None:
                if not (_num_tokens(lines[best_i]) & allowed):
                    dropped.append((best_i, missing))
                # descendant already carries a figure: one-figure rule wins
            else:
                removed.append(re.sub(r"^[•\-*\s]+", "", s)[:90])
    return invented, dropped, removed


_INTENSIFIER_RE = re.compile(
    r"\s*\b(?:significantly|substantially|meaningfully|measurably|greatly|"
    r"drastically|dramatically|materially|considerably|tremendously|vastly)\b",
    re.I)


def _strip_intensifiers(text: str) -> tuple[str, int]:
    """Vague intensifiers are the filler a writer reaches for when it deleted
    a real number. Deleting the word alone leaves a grammatical sentence in
    every live case ("cut runtime significantly and…" -> "cut runtime and…"),
    so this is a pure deterministic strip on summary + bullet lines."""
    lines = text.split("\n")
    body_idx = set(_summary_lines(text)) | {i for _, bl in _job_bullet_lines(text) for i in bl}
    hits = 0
    for i in body_idx:
        s, n = _INTENSIFIER_RE.subn("", lines[i])
        if n:
            s = re.sub(r"\s+([,.;])", r"\1", s)
            s = re.sub(r"[ \t]{2,}", " ", s)
            lines[i] = s
            hits += n
    return "\n".join(lines), hits


_SHORT_MAX = 16          # a bullet at or under this many words counts as "short"
_LONG_RUN = 25           # three consecutive bullets over this = a wall


def _line_skills(line: str, claimed: list[str]) -> list[str]:
    """Claimed SKILLS items this one bullet evidences."""
    wrap = "EXPERIENCE:\nX @ Y | Z\n• " + line.lstrip("• ").strip()
    return [sk for sk in claimed if not _unevidenced([sk], wrap)]


def _length_flags(text: str, inserted_texts: set[str]) -> dict[int, str]:
    """Per job: if no bullet is short, pick one to compress (a guard-inserted
    bullet first, else the shortest number-free one); and break any run of
    three long bullets by trimming the middle one."""
    lines = text.split("\n")
    claimed = _skills_claimed(text)
    flags: dict[int, str] = {}
    for _, bl in _job_bullet_lines(text):
        if len(bl) < 4:
            continue
        wc = {i: len(lines[i].split()) - 1 for i in bl}
        if min(wc.values()) > _SHORT_MAX:
            cand = [i for i in bl if lines[i].lstrip()[1:].strip() in inserted_texts]
            if not cand:
                cand = [i for i in bl if not _num_tokens(lines[i])] or bl
            # the bullet carrying the fewest claimed skills is the safest to
            # shorten — compressing an evidence-heavy one loses skills
            tgt = min(cand, key=lambda i: (len(_line_skills(lines[i], claimed)), wc[i]))
            figs = _num_tokens(lines[tgt])
            keep = _line_skills(lines[tgt], claimed)
            flags[tgt] = ("Compress to 8-12 words: keep the core action, drop the "
                          "context clause."
                          + (f" Keep the figure {', '.join(sorted(figs))}." if figs else "")
                          + (f" These names must stay: {', '.join(keep)}." if keep else ""))
        # a bullet past 40 words is a paragraph, not a bullet: always trimmed
        for i in bl:
            if wc[i] > 40 and i not in flags:
                figs = _num_tokens(lines[i])
                flags[i] = ("Tighten to 22-30 words: keep the tools"
                            + (f" and the figure {', '.join(sorted(figs))}" if figs else "")
                            + ", remove the weakest clause.")
        # one wall-breaker per job: the model rewrites few lines, code verifies each
        for a, b, c in zip(bl, bl[1:], bl[2:]):
            if wc[a] > _LONG_RUN and wc[b] > _LONG_RUN and wc[c] > _LONG_RUN and b not in flags:
                flags[b] = ("Tighten to 15-20 words: keep the tools and the "
                            "figure if any, remove the weakest clause.")
                break
    return flags


_PHRASE_STOP = {"and", "the", "for", "with", "across", "from", "into", "that",
                "data", "using", "all", "our", "per", "over", "under", "of",
                "in", "on", "to", "a", "an", "by", "as", "at"}


def _overused_phrases(text: str, job_description: str, target_tools: list) -> dict[int, list[str]]:
    """Phrases the draft leans on: a hyphenated compound or a two-word phrase
    appearing 4+ times across SUMMARY + bullets while the JD itself uses it
    at most twice. Tool names are exempt (a Spark job is a Spark job). The
    first summary use and the first bullet use stay; the rest are flagged
    per line for rewording."""
    lines = text.split("\n")
    sum_idx = _summary_lines(text)
    bul_idx = [i for _, bl in _job_bullet_lines(text) for i in bl]
    counts: dict[str, list[int]] = {}
    cased: dict[str, int] = {}     # phrase -> occurrences written Title Case
    for i in sum_idx + bul_idx:
        raw = lines[i]
        low = raw.lower()
        seen_here = set()
        for m in re.finditer(r"\b[a-z]+(?:-[a-z]+)+\b", low):
            seen_here.add(m.group(0))
        toks = re.findall(r"[A-Za-z]+", raw)
        for a, b in zip(toks, toks[1:]):
            al, bl_ = a.lower(), b.lower()
            if al in _PHRASE_STOP or bl_ in _PHRASE_STOP or len(al) < 4 or len(bl_) < 4:
                continue
            p = f"{al} {bl_}"
            seen_here.add(p)
            if a[0].isupper() and b[0].isupper():
                cased[p] = cased.get(p, 0) + 1
        for p in seen_here:
            counts.setdefault(p, []).append(i)
    jd_low = job_description.lower()
    flags: dict[int, list[str]] = {}
    for p, idxs in counts.items():
        if len(idxs) < 4:
            continue
        # a product name is written Title Case ("Great Expectations", "Lake
        # Formation") — repeating a product is not an echo, skip it
        if cased.get(p, 0) * 2 >= len(idxs):
            continue
        # the JD's own drumbeat may be echoed; a phrase the JD says once may not
        if len(idxs) <= 2 * len(re.findall(re.escape(p), jd_low)):
            continue
        keep = set()
        first_sum = next((i for i in idxs if i in sum_idx), None)
        first_bul = next((i for i in idxs if i in bul_idx), None)
        keep.update(x for x in (first_sum, first_bul) if x is not None)
        for i in idxs:
            if i not in keep:
                flags.setdefault(i, []).append(p)
    return flags


LINE_FIX_SYSTEM = """You repair individual resume lines. Each input line is
numbered and followed by an instruction in [brackets]. Return EXACTLY one
output line per input line in the form:
<number> :: <fixed line text>

Rules:
- Obey the instruction for that line and change nothing else about its meaning.
- Keep every tool name that is already in the line.
- Never add a number the instruction did not give you. Never use an em or en
  dash. Never use vague intensifiers (significantly, substantially,
  meaningfully, greatly, dramatically).
- One numeric figure per line at most; when told to restore a figure into a
  line that has none, place it where the base wording had it ("cutting stale-data
  incidents by roughly 40%").
- When told to remove a figure, replace it with a plain qualitative outcome or a
  scale word (terabytes, millions of rows), not another number.
- When told to reword a phrase, use a natural synonym ("multi-tenant" ->
  "tenant-isolated", "per-client", "segregated"); do not repeat the phrase.
- Do not start the line with the bullet character; output the text only.
Output ONLY the numbered lines."""


async def _fix_lines(text: str, jobs: dict[int, str], notes: list, label: str,
                     **cheap_kw) -> str:
    """One cheap call that rewrites only the flagged lines; each result is
    accepted line-by-line by the caller's verifier (never by trust)."""
    if not jobs:
        return text
    lines = text.split("\n")
    order = sorted(jobs)
    payload = "\n".join(
        f"{n + 1}. {lines[i].lstrip()[1:].strip() if lines[i].lstrip().startswith('•') else lines[i].strip()}"
        f"  [{jobs[i]}]" for n, i in enumerate(order))
    try:
        out = (await chat(LINE_FIX_SYSTEM, payload, max_tokens=3000,
                          pass_name=label, **cheap_kw)).strip()
    except Exception as exc:  # noqa: BLE001 — best effort
        notes.append(f"{label}: skipped ({exc})")
        return text
    fixes: dict[int, str] = {}
    for ln in out.splitlines():
        m = re.match(r"^\s*(\d+)\s*(?:::|[.)])\s*(.+?)\s*$", ln)
        if m and 1 <= int(m.group(1)) <= len(order):
            body = m.group(2).lstrip("•-* ").strip()
            body = re.sub(r"\s*[—–]\s*", ", ", body)
            fixes[order[int(m.group(1)) - 1]] = body
    for i, body in fixes.items():
        if not body:
            continue
        lines[i] = ("• " + body) if lines[i].lstrip().startswith("•") else body
    return "\n".join(lines)


async def _polish_numbers_and_length(tailored: str, base_resume: str,
                                     job_description: str, target_tools: list,
                                     inserted: list, notes: list,
                                     **cheap_kw) -> str:
    """Guards measured in code, repaired by the cheap model, re-measured in
    code: invented figures out, dropped base figures back, one short bullet
    per job, no phrase echoed four times. Anything the model fails to fix is
    reverted line-by-line and reported."""
    invented, dropped, removed = _number_audit(tailored, base_resume, job_description)
    inserted_texts = {b for _, _, b in inserted}
    length = _length_flags(tailored, inserted_texts)
    phrases = _overused_phrases(tailored, job_description, target_tools)
    if removed:
        notes.append(f"number guard: {len(removed)} base bullet(s) with figures were "
                     "dropped by the writer: " + " | ".join(removed))

    jobs: dict[int, str] = {}
    for i, figs in invented:
        jobs[i] = f"Remove the figure(s) {', '.join(sorted(figs))} (not in the base resume)."
    for i, figs in dropped:
        jobs[i] = (jobs.get(i, "") + f" Restore the base resume's figure(s) "
                   f"{', '.join(sorted(figs))} that this bullet originally carried.").strip()
    numbered = {i for i, _ in invented} | {i for i, _ in dropped}
    length = {i: v for i, v in length.items() if i not in numbered}
    for i, instr in length.items():
        jobs[i] = (jobs.get(i, "") + " " + instr).strip()
    for i, ps in phrases.items():
        jobs[i] = (jobs.get(i, "") + " Reword so the phrase(s) "
                   + ", ".join(f"'{p}'" for p in ps) + " no longer appear.").strip()
    if not jobs:
        return tailored

    before = tailored.split("\n")
    fixed = await _fix_lines(tailored, jobs, notes, "line_fix", **cheap_kw)
    after = fixed.split("\n")
    if len(after) != len(before):
        notes.append("line fix rejected (line count changed)")
        return tailored

    allowed = _num_tokens(base_resume) | _num_tokens(job_description)
    claimed = _skills_claimed(tailored)
    ok: dict[str, int] = {"invented": 0, "restored": 0, "short": 0, "phrase": 0}
    bad: list[str] = []
    retry: dict[int, str] = {}
    for i in jobs:
        new = after[i]
        verdict = True
        if any(i == x for x, _ in invented):
            if _num_tokens(new) - allowed:
                verdict = False; bad.append(f"line {i}: invented figure still present")
            else:
                ok["invented"] += 1
        for x, figs in dropped:
            if x == i:
                if figs & _num_tokens(new):
                    ok["restored"] += 1
                else:
                    verdict = False; bad.append(f"line {i}: figure not restored")
        if i in length:
            wc = len(new.split()) - (1 if new.lstrip().startswith("•") else 0)
            lim = _SHORT_MAX if "8-12" in length[i] else 32 if "22-30" in length[i] else 21
            kept_figs = (_num_tokens(before[i]) & allowed) <= _num_tokens(new)
            lost = [sk for sk in _line_skills(before[i], claimed) if sk not in _line_skills(new, claimed)]
            if 5 <= wc <= lim and kept_figs and not lost:
                ok["short"] += 1
            else:
                verdict = False
                bad.append(f"line {i}: {wc} words after trim"
                           + ("" if kept_figs else ", figure lost")
                           + (f", dropped {', '.join(lost)}" if lost else ""))
        if i in phrases:
            if any(p in new.lower() for p in phrases[i]):
                verdict = False; bad.append(f"line {i}: phrase still present")
            else:
                ok["phrase"] += 1
        if not verdict:
            after[i] = before[i]
            if i in length and i not in phrases:
                figs = _num_tokens(before[i]) & allowed
                keep = _line_skills(before[i], claimed)
                retry[i] = ("HARD LIMIT 12 words. Keep only the verb, the object"
                            + (f", these names: {', '.join(keep)}" if keep else "")
                            + (f", and the figure {', '.join(sorted(figs))}" if figs else "")
                            + "; delete every other clause.")
    # One stricter pass for the length lines the model left too long.
    if retry and _under_cost_cap(notes, "line-fix retry"):
        text2 = await _fix_lines("\n".join(after), retry, notes, "line_fix_retry", **cheap_kw)
        after2 = text2.split("\n")
        if len(after2) == len(after):
            for i in retry:
                new = after2[i]
                wc = len(new.split()) - (1 if new.lstrip().startswith("•") else 0)
                if (5 <= wc <= _SHORT_MAX and (_num_tokens(before[i]) & allowed) <= _num_tokens(new)
                        and set(_line_skills(before[i], claimed)) <= set(_line_skills(new, claimed))):
                    after[i] = new
                    ok["short"] += 1
                    bad = [b for b in bad if not b.startswith(f"line {i}:")]
    notes.append("line fix: " + ", ".join(f"{k} {v}" for k, v in ok.items() if v)
                 + (f"; reverted {len(bad)}: " + "; ".join(bad) if bad else ""))
    return "\n".join(after)


# ── Guard: total length follows tenure ────────────────────────────────────────

_WORDS_PER_PAGE = 500   # what the exporter fits on one page at full type size


def _page_budget(base_resume: str) -> int:
    """Pages the tenure ladder allows (the prompt's LENGTH FOLLOWS TENURE
    rule): 0-3 years -> 1, 4-11 -> 2, 12+ -> 3."""
    _, years = _base_years_claim(base_resume)
    if years is None:
        return 2
    return 1 if years <= 3 else 2 if years <= 11 else 3


def _trim_to_budget(text: str, inserted: list, base_resume: str, notes: list,
                    protect: list | None = None, job_description: str = "") -> str:
    """When the draft runs past the tenure page budget, remove guard-inserted
    coverage bullets first (the prompt's own trim order), oldest job first.
    Base-derived bullets are never touched here — that is a writing decision,
    not a length one. Reports what is still over budget."""
    budget = _page_budget(base_resume) * _WORDS_PER_PAGE
    words = len(text.split())
    if words <= budget or not inserted:
        if words > budget:
            notes.append(f"length guard: {words} words vs {budget} budget "
                         f"({_page_budget(base_resume)} page(s)); nothing generated to trim")
        return text
    lines = text.split("\n")
    removed: list[str] = []
    gone: set[int] = set()
    # oldest job first (highest index), latest-inserted first within a job
    # Only a generated bullet that backs nothing the JD asks for is fair game
    # (a Scala or PL/SQL line written for a base-only skill). One that proves
    # a JD tool or duty is coverage — it stays even if the page runs long.
    prot = [str(p).lower() for p in (protect or [])]
    jd_low = (job_description or "").lower()

    def _named_in_jd(sk: str) -> bool:
        if not jd_low:
            return False
        try:
            from resume_lint import _dynamic_coverage_pattern
            if re.search(_dynamic_coverage_pattern(sk), jd_low):
                return True
        except Exception:  # noqa: BLE001
            pass
        head = next((w for w in re.findall(r"[a-z][a-z0-9+#.]{2,}", sk.lower())
                     if w not in _SKILL_TOKEN_STOP), "")
        return bool(head) and bool(re.search(rf"(?<![a-z0-9]){re.escape(head)}(?![a-z0-9])", jd_low))

    def _wanted(t):
        parts = [x.strip().lower() for x in re.split(r"\s*\+\s*", t[1]) if x.strip()]
        return any(sk in p or p in sk for sk in parts for p in prot)             or any(_named_in_jd(sk) for sk in parts)
    order = [t for _, t in sorted(enumerate(inserted), key=lambda p: (-p[1][0], -p[0]))
             if not _wanted(t)]
    kept_wanted = len(inserted) - len(order)
    for j, skill, bullet in order:
        live = " ".join(ln for i, ln in enumerate(lines) if i not in gone)
        if len(live.split()) <= budget:
            break
        for i, ln in enumerate(lines):
            if i in gone or not ln.lstrip().startswith("•"):
                continue
            if ln.lstrip()[1:].strip() != bullet:
                continue
            gone.add(i)
            removed.append(skill)
            # take the skill back out of that job's Technologies Used line
            for k in range(i, min(i + 20, len(lines))):
                m = _TECH_LINE_RE.match(lines[k].strip())
                if m:
                    items = [x.strip() for x in _split_list_items(m.group(2))]
                    drop = {s.strip().lower() for s in re.split(r"\s*\+\s*", skill)}
                    kept = [x for x in items if x.lower() not in drop]
                    lines[k] = f"{m.group(1).rstrip(':')}: {', '.join(kept)}"
                    break
            break
    out = "\n".join(ln for i, ln in enumerate(lines) if i not in gone)
    final = len(out.split())
    notes.append(f"length guard: {words} -> {final} words (budget {budget}, "
                 f"{_page_budget(base_resume)} page(s)); dropped generated bullet(s): "
                 + (", ".join(removed) if removed else "none")
                 + (f"; kept {kept_wanted} JD-coverage bullet(s)" if kept_wanted else "")
                 + ("" if final <= budget else
                    "; still over budget (JD-coverage and base bullets are never cut here)"))
    return out


# ── Guard: targeted QA — code finds the lines, the cheap model fixes only them ─

_JUNK_LINE_RE = re.compile(
    r"^\s*(?:•\s*)?(?:location not listed|n/?a|not specified|see above|"
    r"\(?consolidated under[^)]*\)?|fabricated[^\n]*|\[?end of resume\]?)\s*\.?\s*$", re.I)
_CLICHE_RE = re.compile(
    r"^(?:responsible for|tasked with|utilized|leveraged|spearheaded|worked on|"
    r"helped with|involved in|in charge of)\b", re.I)


def _strip_junk_lines(text: str) -> tuple[str, int]:
    lines = text.split("\n")
    kept = [ln for ln in lines if not _JUNK_LINE_RE.match(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)), len(lines) - len(kept)


def _ensure_tech_lines(text: str) -> tuple[str, int]:
    """A job without a Technologies Used line gets one built from the SKILLS
    items that its own bullets actually name — nothing the job never used."""
    lines = text.split("\n")
    skills = _skills_claimed(text)
    hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    added = 0
    for h in reversed(hdr_idx):
        end = _job_block_end(lines, h)
        block = lines[h + 1:end]
        if any(_TECH_LINE_RE.match(ln.strip()) for ln in block):
            continue
        bullets = "\n".join(ln for ln in block if ln.lstrip().startswith("•"))
        if not bullets:
            continue
        found = [sk for sk in skills
                 if not _unevidenced([sk], "EXPERIENCE:\nX @ Y | Z\n" + bullets)]
        if not found:
            continue
        # insert after the last non-empty line of the block
        at = end
        while at > h + 1 and not lines[at - 1].strip():
            at -= 1
        lines.insert(at, "Technologies Used: " + ", ".join(dict.fromkeys(found[:_TECH_MAX])))
        added += 1
    return "\n".join(lines), added


def _qa_flags(text: str, missing_clouds: dict) -> dict[int, str]:
    lines = text.split("\n")
    flags: dict[int, str] = {}

    def _add(i: int, instr: str) -> None:
        flags[i] = (flags.get(i, "") + " " + instr).strip()

    # cliché openers, repeated opening verbs, stacked figures — per job
    for _, bl in _job_bullet_lines(text):
        seen_verbs: dict[str, int] = {}
        for i in bl:
            body = lines[i].lstrip()[1:].strip()
            if _CLICHE_RE.match(body):
                _add(i, "Open with a real action verb instead of this templated phrase.")
            first = re.match(r"[A-Za-z][A-Za-z-]*", body)
            verb = first.group(0).lower() if first else ""
            if verb:
                if verb in seen_verbs:
                    _add(i, f"Start with a different verb than '{first.group(0)}' (already used in this job); keep the meaning.")
                else:
                    seen_verbs[verb] = i
            figs = _num_tokens(body)
            if len(figs) >= 2:
                _add(i, f"Keep only the strongest one of the figures {', '.join(sorted(figs))}; write the others as plain words.")
    # summary: past tense about the current employer
    hdr_idx = [i for i, ln in enumerate(lines) if _is_job_header_line(ln)]
    cur = ""
    if hdr_idx and re.search(r"\bpresent\b", lines[hdr_idx[0]], re.I):
        m = _JOB_HDR_RE.search(lines[hdr_idx[0]])
        cur = m.group(1).strip() if m else ""
    for i in _summary_lines(text):
        body = lines[i].lstrip("• ").strip()
        first = re.match(r"[A-Za-z]+", body)
        if cur and first and first.group(0).lower().endswith("ed") \
                and re.search(rf"\b{re.escape(cur)}\b", body, re.I):
            _add(i, f"Present tense: this describes the current employer ({cur}).")
    # dropped real cloud: weave into the job's first two bullets + its tools line
    for company, cloud in (missing_clouds or {}).items():
        for h in hdr_idx:
            m = _JOB_HDR_RE.search(lines[h])
            if not m or m.group(1).strip().lower() != company:
                continue
            end = _job_block_end(lines, h)
            bl = [i for i in range(h + 1, end) if lines[i].lstrip().startswith("•")
                  and not _TECH_LINE_RE.match(lines[i].strip())]
            for i in bl[:2]:
                _add(i, f"Weave {cloud} naturally into this bullet alongside the tools already there (e.g. 'on {cloud} and ...').")
            for i in range(h + 1, end):
                if _TECH_LINE_RE.match(lines[i].strip()):
                    _add(i, f"Add {cloud} to this list.")
    return flags


async def _targeted_qa(text: str, missing_clouds: dict, notes: list, **cheap_kw) -> str:
    flags = _qa_flags(text, missing_clouds)
    if not flags:
        return text
    before = text.split("\n")
    fixed = await _fix_lines(text, flags, notes, "qa_fix", **cheap_kw)
    after = fixed.split("\n")
    if len(after) != len(before):
        notes.append("qa fix rejected (line count changed)")
        return text
    kept, reverted = 0, []
    for i, instr in flags.items():
        old, new = before[i], after[i]
        ob = old.lstrip()[1:].strip() if old.lstrip().startswith("•") else old.strip()
        nb = new.lstrip()[1:].strip() if new.lstrip().startswith("•") else new.strip()
        ok = bool(nb)
        wc_old, wc_new = len(ob.split()), len(nb.split())
        if ok and not (0.5 * wc_old <= wc_new <= 1.6 * wc_old + 4):
            ok = False
        if ok and "templated" in instr and _CLICHE_RE.match(nb):
            ok = False
        if ok and "different verb" in instr:
            want = re.search(r"than '([^']+)'", instr)
            f_new = re.match(r"[A-Za-z][A-Za-z-]*", nb)
            if want and f_new and f_new.group(0).lower() == want.group(1).lower():
                ok = False
        if ok and "strongest one" in instr:
            if len(_num_tokens(nb)) > 1 or not _num_tokens(nb) <= _num_tokens(ob):
                ok = False
        if ok and "Present tense" in instr:
            f_new = re.match(r"[A-Za-z]+", nb)
            if f_new and f_new.group(0).lower().endswith("ed"):
                ok = False
        if ok and ("Weave" in instr or "Add " in instr):
            cloud = re.search(r"(?:Weave|Add) (\w+)", instr).group(1)
            if not any(t in nb.lower() for t in _CLOUD_TERMS.get(cloud, (cloud.lower(),))):
                ok = False
        if ok and _num_tokens(nb) - _num_tokens(ob) and "Weave" not in instr:
            ok = False                      # a fix never introduces a figure
        if ok:
            kept += 1
        else:
            after[i] = old
            reverted.append(f"line {i}: {instr[:40]}")
    notes.append(f"qa fix: {kept} line(s) repaired of {len(flags)} flagged"
                 + (f"; reverted {len(reverted)}: " + "; ".join(reverted) if reverted else ""))
    return "\n".join(after)


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
                   "present": [], "missing": [], "baseline_missing": [],
                   "responsibilities": []}

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
    # Duties are a checklist too — cap at 8 (most important first per the
    # analyze prompt) so they can't crowd the bullet caps; no soft-skill
    # filter here, a duty like "clarifying requirements with analysts" IS the
    # kind of thing recruiters search for.
    # The JD's pay tables, benefits, EEO and about-us tail is billed on every
    # later pass (Sonnet included) and teaches the writer nothing. The analyze
    # pass points at where it starts; cut there for everything downstream.
    job_description, _cut = _trim_jd_tail(job_description, context.get("jd_tail_starts"))
    if _cut:
        notes.append(f"jd trimmed: dropped {_cut} chars of pay/benefits/legal tail")

    _resp = [str(r).strip() for r in (context.get("responsibilities") or []) if str(r).strip()]
    context["responsibilities"] = _resp[:8]
    for _k in ("target_tools", "present", "missing"):
        _orig = context.get(_k) or []
        _kept = [t for t in _orig if not _is_soft_skill(str(t))]
        if len(_kept) != len(_orig):
            context[_k] = _kept
    # A tool label whose words the JD never uses is the analyzer's paraphrase,
    # not a keyword — an ATS would never match it and the coverage model can
    # only fail on it. Keep only labels whose word stems all occur in the JD.
    _not_literal = [str(t) for t in (context.get("target_tools") or [])
                    if not _phrase_in_jd(str(t), job_description)]
    if _not_literal:
        context["target_tools"] = [t for t in context["target_tools"] if str(t) not in _not_literal]
        for _k in ("present", "missing", "bridge_only", "equivalent"):
            context[_k] = [t for t in (context.get(_k) or []) if str(t).split(" <-")[0] not in _not_literal]
        notes.append("analyze: dropped labels the JD never says: " + ", ".join(_not_literal))

    missing = context.get("missing") or []
    print(f"[TAILOR] target_cloud={context.get('target_cloud')!r} "
          f"target_tools={len(context.get('target_tools') or [])} "
          f"present={len(context.get('present') or [])} missing_tools={len(missing)} "
          f"baseline_missing={len(context.get('baseline_missing') or [])} "
          f"responsibilities={len(context.get('responsibilities') or [])} "
          f"company={company or context.get('company', '')!r}")

    # ── 2. TAILOR (main model) ────────────────────────────────────────────
    tailored = (await chat(
        TAILOR_SYSTEM,
        tailor_prompt(base_resume, job_description, context, missing, profile_skills),
        max_tokens=8000, pass_name="tailor", **main_kw,
    )).strip()
    tailored = _clean_header_title(_ensure_header(_normalize_format(tailored), base_resume))
    tailored = _enforce_caps(tailored, base_resume, notes,
                             keep_tool=_dominant_jd_tool(job_description, context.get("target_tools") or []))

    # Guard (b): which non-swapped jobs lost their real base cloud?
    target = context.get("target_cloud", "None")
    missing_clouds = _missing_native_clouds(tailored, base_resume, target)
    if missing_clouds:
        notes.append("cloud restore requested: "
                     + ", ".join(f"{c}={cl}" for c, cl in missing_clouds.items()))

    # ── 3. QA (code flags the lines, cheap model rewrites only those) ────
    # Replaces the old whole-resume QA rewrite (2k output tokens per run):
    # junk lines and missing Technologies Used lines are fixed in code; cliché
    # openers, repeated verbs, stacked figures, past tense on the current
    # employer, and dropped-cloud restoration go to the line fixer, each
    # verified in code before it is kept.
    tailored, junk = _strip_junk_lines(tailored)
    if junk:
        notes.append(f"qa: removed {junk} junk/placeholder line(s)")
    tailored, tech_added = _ensure_tech_lines(tailored)
    if tech_added:
        notes.append(f"qa: built {tech_added} missing Technologies Used line(s) from the job's own bullets")
    tailored = await _targeted_qa(tailored, missing_clouds, notes, **cheap_kw)

    # Guard (c): still missing after the fixer -> force into Technologies Used.
    still_missing = _missing_native_clouds(tailored, base_resume, target)
    if still_missing:
        notes.append("cloud backstop applied: "
                     + ", ".join(f"{c}={cl}" for c, cl in still_missing.items()))
        tailored = _backstop_native_clouds(tailored, still_missing)

    tailored = _clean_header_title(_strip_empty_sections(tailored)).strip()
    tailored = _guard_title_inflation(tailored, base_resume, notes)
    tailored = _headline_hybrid(tailored, base_resume, context.get("job_title", ""), notes)

    # Guard (c1): `present` is a hard keep-list — a tool the analyze pass found
    # in the BASE resume and the JD asks for must not vanish from the tailored
    # text. If the writer dropped one, restore it to the fitting SKILLS row
    # (the parity guard below then earns it a bullet).
    tailored = _restore_present_tools(tailored, context.get("present") or [],
                                      base_resume, notes)

    # Guard (c1b): SKILLS may only claim what the base states, a universal
    # baseline duty, or a same-category swap — a bridged JD tool lives in a
    # bullet's bridge phrasing, never as an owned skill.
    tailored = _strip_unowned_skills(tailored, base_resume, context, notes)

    # Guard (c2): every skill claimed in SKILLS must have an experience bullet
    # behind it — orphans get a modest scope bullet written into the job where
    # that work plausibly happened. Also chased: the JD's universal-baseline
    # requirements and its RESPONSIBILITIES the draft left unevidenced (both
    # judged by the analyze pass, per JD — no fixed list in code).
    inserted: list = []          # (job_index, skill, bullet) the guard wrote
    tailored = await _ensure_skill_bullets(
        tailored, job_description, notes,
        jd_missing=(context.get("baseline_missing") or []) + (context.get("responsibilities") or []),
        inserted=inserted,
        jd_terms=(context.get("target_tools") or []) + (context.get("responsibilities") or []),
        must_tools=_coverage_plan(context)[0],
        foreign=context.get("bridge_only") or [],
        **cheap_kw)

    # Guard (c3): bullets whose endings read as truncated. Measured with the
    # same detector that drives the UI warning; only spends a call when the
    # draft actually has flagged bullets, and finishes deterministically.
    if _under_cost_cap(notes, "fragment fix"):
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

    # Guard (d0): length follows tenure. Generated coverage bullets are the
    # first thing to go when the draft outgrows its page budget (live miss:
    # a 5-year resume shipped at 0.92 type scale to squeeze into 2 pages).
    tailored = _trim_to_budget(
        tailored, inserted, base_resume, notes,
        protect=(context.get("target_tools") or []) + (context.get("responsibilities") or []),
        job_description=job_description)

    # Guard (d2): no em/en dashes in body text — the classic AI-writing tell.
    # Guard (d1): the JD's dominant tool must be visible in the first bullets
    # a recruiter reads. Live miss: an Informatica-heavy JD, with Informatica
    # genuinely in the candidate's current job, ended up at bullet 9 behind
    # cloud brands the JD never mentions. Reordering only — no rewriting.
    tailored = _promote_tool_bullets(
        tailored, _dominant_jd_tool(job_description, context.get("target_tools") or []), notes)

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

    # Guard (g): figures, bullet-length variety, phrase echo — measured in
    # code, repaired by the cheap model only where flagged, verified in code.
    # Live misses: "roughly 25%" and "40%" deleted from base bullets, no
    # short bullet in any job, "multi-tenant" four times.
    tailored = await _polish_numbers_and_length(
        tailored, base_resume, job_description, context.get("target_tools") or [],
        inserted, notes, **cheap_kw)
    tailored, dash_hits2 = _strip_dash_asides(tailored)
    if dash_hits2:
        notes.append(f"dash guard (post-fix): rewrote {dash_hits2} dash construction(s)")

    # Guard (h): vague intensifiers never ship — the prompt forbids them, the
    # fixer is told again, and this strip is the deterministic last word.
    # Guard (g0): a tool the base anchors to specific jobs must not migrate
    # into another job's bullets (live miss: Snowflake, real only at JPMC,
    # written into two Cargill bullets for a Snowflake JD). Runs after the
    # line fixes so nothing they reintroduce survives.
    tailored = await _fix_scope_leaks(tailored, base_resume, context, notes,
                                      jd_text=job_description, **cheap_kw)

    tailored, intens = _strip_intensifiers(tailored)
    if intens:
        notes.append(f"intensifier guard: removed {intens} vague intensifier(s)")

    # Guard (f): final no-orphan sweep. Guard (c2) already trimmed once, but the
    # tidy passes after it (list caps, dash rewrite) can erase a skill's last
    # piece of evidence — re-measure on the FINAL text so nothing unbacked ships.
    tailored = _drop_unevidenced_skills(tailored, notes)

    # ── 4. SCORE (code, no model call) ────────────────────────────────────
    # 100 points: tools 40, duties 15, title 5, orphans 10, numbers 10,
    # readability 10, page fit 10. present/missing chips come from the same
    # measurement, so the panel, the badge and the chips always agree.
    scores: dict = {}
    try:
        scores = _code_score(tailored, base_resume, job_description, context, inserted)
        context["present"], context["missing"] = scores.get("present", []), scores.get("missing", [])
        _ct = scores.get("coverage_target") or {}
        notes.append(f"coverage target: {_ct.get('have')}/{_ct.get('need')} ranked tools in bullets, "
                     f"{'met' if _ct.get('met') else 'MISSED'}"
                     + (f"; skipped by design: {', '.join(_ct.get('skipped_by_design') or [])}"
                        if _ct.get('skipped_by_design') else ""))
        if scores.get("missing"):
            notes.append(f"final coverage: {len(scores['present'])} present, "
                         f"{len(scores['missing'])} missing (ATS {scores['ats']['score']})")
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
        if overall < 70:          # code score is literal; 70 = review-worthy
            reasons.extend(str(f) for f in (scores.get("top_fixes") or [])[:3])

    try:
        from ai.llm import get_run_usage
        usage = get_run_usage()
    except Exception:  # noqa: BLE001
        usage = {"cost": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": []}

    # Every guard's verdict goes to the server log too, so a log-only review
    # can see what ran (the notes were UI-only before).
    for n in notes:
        print(f"[TAILOR GUARDS] {n[:300]}")

    review = {
        "needs_review": bool(reasons),
        "reasons": reasons,
        "notes": notes,
        "scores": scores,
        "context": context,
        "usage": usage,          # {cost, tokens_in, tokens_out, calls:[...]}
    }
    return tailored, review

