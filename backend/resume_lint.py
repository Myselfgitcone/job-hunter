"""
resume_lint_v2.py — universal quality gate for tailored resumes.

Supports: Tech, Investment Banking (IB), Finance, Cybersecurity (Cyber),
          Healthcare, Consulting, and General roles.

Role type is auto-detected from the job description. Every check —
bullet limits, section labels, closing-line presence, verb lists,
echo stoplist, metrics density — adapts to the detected role type.

Usage:
    issues = lint_resume(resume_text, job_description)
    # Returns list of issue strings. Empty = clean.

CLI:
    python3 resume_lint_v2.py resume.txt jd.txt
"""

import re
import sys
from typing import Optional


# ── Role type constants ────────────────────────────────────────────────────────
TECH        = "TECH"
IB          = "IB"
FINANCE     = "FINANCE"
CYBER       = "CYBER"
HEALTHCARE  = "HEALTHCARE"
CONSULTING  = "CONSULTING"
GENERAL     = "GENERAL"

# Map user-selected job role labels → resume role type.
# All data/tech/analytics roles map to TECH.
_USER_ROLE_MAP: dict[str, str] = {
    "data engineer":        TECH,
    "data analyst":         TECH,
    "business analyst":     TECH,
    "bi":                   TECH,
    "bi analyst":           TECH,
    "bi developer":         TECH,
    "analytics engineer":   TECH,
    "data scientist":       TECH,
    "data architect":       TECH,
    "ml engineer":          TECH,
    "software engineer":    TECH,
    "project manager":      TECH,
    "java":                 TECH,
    "investment banking":   IB,
    "ib":                   IB,
    "finance":              FINANCE,
    "fp&a":                 FINANCE,
    "cybersecurity":        CYBER,
    "cyber":                CYBER,
    "security":             CYBER,
    "healthcare":           HEALTHCARE,
    "consulting":           CONSULTING,
}


def user_roles_to_role_type(job_roles: list[str]) -> str | None:
    """
    Convert user-selected job role labels to a resume role type.
    - If all roles map to the same type → return that type.
    - If roles are set but map to multiple types → return the majority type,
      or TECH on tie (data users who also have one finance role still get TECH).
    - If no roles set → return None (caller falls back to JD detection).
    """
    if not job_roles:
        return None
    from collections import Counter
    counts: Counter = Counter()
    for r in job_roles:
        rt = _USER_ROLE_MAP.get(r.lower().strip())
        if rt:
            counts[rt] += 1
    if not counts:
        # Roles set but none in map — assume TECH (safe default for data roles)
        return TECH
    best = counts.most_common(1)[0][0]
    # TECH wins ties
    if counts[TECH] >= counts[best]:
        return TECH
    return best


# ── Bullet budget — same for every role type ───────────────────────────────────
# User only ever tailors for TECH/CYBER-family roles (data engineer, analyst,
# BI, PM, java, cybersecurity). A single shared budget means role_type can
# never disagree with itself on bullet count — the exact bug class that broke
# a live tailor run when lint's JD-auto-detected role_type (CONSULTING) diverged
# from the role_type the AI was actually told to write against (TECH).
# (most_recent, second, third, fourth_plus, summary, hard_total)
# Summary = 5 (synced 2026-07-13: SYSTEM_PROMPT said 5, this said 6, and the
# two RETRY_RULES copies disagreed — every run burned an augmenter call adding
# a 6th summary bullet the prompt forbade). hard_total drops with it so the
# experience budget stays 32.
_UNIFIED_BUDGET = (11, 8, 7, 6, 5, 37)
BULLET_BUDGETS: dict[str, tuple[int, int, int, int, int, int]] = {
    rt: _UNIFIED_BUDGET for rt in (TECH, IB, FINANCE, CYBER, HEALTHCARE, CONSULTING, GENERAL)
}

# Minimum bullets per job (same order: job1, job2, job3, job4+) — same for every role.
# Set BELOW the budget maxima so min-max is a real range. Equal min/max forced
# the model to pad thin jobs with filler bullets to hit an exact count — filler
# is the main fabrication-pressure source. max-2 keeps depth without padding.
_UNIFIED_MINIMUMS = (10, 7, 6, 5)
BULLET_MINIMUMS: dict[str, tuple[int, int, int, int]] = {
    rt: _UNIFIED_MINIMUMS for rt in (TECH, IB, FINANCE, CYBER, HEALTHCARE, CONSULTING, GENERAL)
}

SUMMARY_EXACT = 5
WORD_LIMIT    = 25
WORD_TARGET   = 20

BANNED_WORDS = ["utilized", "leveraged"]

# Universal corporate clichés — empty filler phrases that carry no verifiable
# signal regardless of role type (tech, IB, healthcare, consulting...). Same
# category as BANNED_WORDS: a small, stable, non-JD-specific list, not a
# per-case patch. Two entries have legitimate domain meanings and are
# exempted contextually below (mirrors the "leveraged finance" exemption).
CORPORATE_CLICHES = [
    "team player", "detail-oriented", "detail oriented", "results-driven",
    "results oriented", "hard worker", "hardworking", "go-getter",
    "think outside the box", "proven track record", "excellent communication skills",
    "strong work ethic", "passionate about", "wheelhouse", "highly motivated",
    "dynamic professional", "synergy", "synergies", "value add", "value-add",
]

META_LEAKS = [
    "fabricat", "as per the jd", "as required", "[[", "note:",
    "lorem", "placeholder", "tbd", "insert here", "your name",
]

DEGREE_SIGNALS = {
    "university", "college", "institute", "bachelor", "phd",
    "b.s.", "m.s.", "b.a.", "m.a.", "m.eng.", "degree",
}

# ── Summary unsupported-claim checks ──────────────────────────────────────────
# Each entry: (pattern_in_summary, [evidence_patterns_in_work_bullets], label)
# If a summary bullet matches the pattern but NO work bullet matches ANY evidence
# pattern, a [UNSUPPORTED EXPERIENCE CLAIM] lint issue is raised.
_SUMMARY_RISK_CLAIMS: list[tuple[str, list[str], str]] = [
    # client-facing: only valid if work bullets mention actual external clients/customers
    (
        r"\bclient[-\s]facing\b",
        [r"\bclient\b", r"\bcustomer\b", r"\bexternal (client|partner|stakeholder)\b"],
        "client-facing",
    ),
    # advisory / trusted advisor: only valid if advisory or consulting work exists in bullets
    (
        r"\badvisory\b|\btrusted advisor\b",
        [r"\badvisor\b", r"\bclient\b", r"\bconsultan", r"\bengagement\b"],
        "advisory / trusted advisor",
    ),
    # consulting experience as a claim: only valid if consulting work in bullets
    (
        r"\bconsulting experience\b|\bmanagement consult",
        [r"\bconsult", r"\bclient\b", r"\bengagement\b"],
        "consulting experience",
    ),
    # team management: only valid if managing-people language in bullets
    (
        r"\bmanaged (a |the )?(team|group|staff|people)\b|\bteam of \d+\b",
        [r"\bmanag\w*.{0,40}(team|people|staff|headcount|report)", r"\bdirect report", r"\bheadcount\b"],
        "team management",
    ),
    # direct reports: only valid if direct-report or headcount language in bullets
    (
        r"\bdirect reports?\b",
        [r"\bdirect report", r"\bmanag\w*.{0,40}(people|staff|headcount)"],
        "direct reports",
    ),
    # P&L ownership: only valid if budget/revenue ownership language in bullets
    (
        r"\bP&L (ownership|responsibility)\b|\bprofit.and.loss\b",
        [r"\bP&L\b", r"\bprofit\b.{0,30}(own|respon)", r"\bbudget\b.{0,30}own"],
        "P&L ownership",
    ),
]

# ── Role-type detection ────────────────────────────────────────────────────────

# Signals weighted by specificity. More specific signals scored higher.
_ROLE_SIGNALS: dict[str, list[tuple[str, int]]] = {
    IB: [
        (r"\bm&a\b", 3), (r"\binvestment bank", 3), (r"\bleveraged (finance|buyout)\b", 3),
        (r"\bdeal execution\b", 3), (r"\bpitch book\b", 2), (r"\bcim\b", 2),
        (r"\bdata room\b", 2), (r"\becm\b|dcm\b", 2), (r"\bbuy[-\s]?side\b", 2),
        (r"\bsell[-\s]?side\b", 2), (r"\btransaction (advisory|experience)\b", 2),
        (r"\blbo\b", 2), (r"\bmerger model\b", 2), (r"\bcapital markets\b", 2),
        (r"\bmanagement presentation\b", 1), (r"\bbulge bracket\b", 2),
    ],
    FINANCE: [
        (r"\bfp&a\b", 3), (r"\bfinancial planning\b", 2), (r"\bfinancial analyst\b(?!.*data)", 2),
        (r"\baccounting\b", 2), (r"\bgeneral ledger\b", 2), (r"\bclose process\b", 2),
        (r"\bvariance analysis\b", 2), (r"\bbudget(ing)?\b", 2), (r"\bforecast(ing)?\b", 2),
        (r"\btreasury\b", 2), (r"\bgaap\b", 2), (r"\bifrs\b", 2), (r"\bsox compliance\b", 2),
        (r"\bcfo\b", 1), (r"\bearnings\b", 1), (r"\bfinancial model(ing)?\b", 2),
    ],
    CYBER: [
        (r"\bcybersecur", 3), (r"\bsoc analyst\b", 3), (r"\bthreat (intel|hunting|detect)", 3),
        (r"\bincident response\b", 3), (r"\bpenetration test", 3), (r"\bvulnerability\b", 2),
        (r"\bsiem\b", 2), (r"\bedr\b", 2), (r"\bfirewall\b", 2), (r"\bgrc\b", 2),
        (r"\bzero trust\b", 2), (r"\bmitre att&ck\b", 3), (r"\bmalware\b", 2),
        (r"\bblue team\b", 2), (r"\bred team\b", 2), (r"\bsecurity operations\b", 2),
        (r"\binfosec\b", 2), (r"\bpki\b", 1), (r"\bdlp\b", 1),
    ],
    HEALTHCARE: [
        (r"\bpatient (care|outcome|panel|record)", 3), (r"\bclinical\b", 2),
        (r"\bregistered nurse\b", 3), (r"\bphysician\b", 3), (r"\bnurse practitioner\b", 3),
        (r"\behr\b", 2), (r"\bepic\b|cerner\b", 2), (r"\bhipaa\b", 2),
        (r"\bcare (coordination|management|plan)", 2), (r"\breadmission", 2),
        (r"\bhealth (informatics|system|care)", 2), (r"\bmedical record", 2),
        (r"\bclinical trial\b", 2), (r"\bpharmac", 1),
    ],
    CONSULTING: [
        (r"\bconsulting\b", 2), (r"\bmanagement consultant\b", 3), (r"\bstrategy consultant\b", 3),
        (r"\bengagement\b", 2), (r"\bclient[-\s](delivery|relationship|facing)\b", 2),
        (r"\btrusted advisor\b", 3), (r"\bstorytelling\b", 2),
        (r"\bbusiness valuation\b", 2), (r"\bproject scoping\b", 2),
        (r"\bworkstream\b", 2), (r"\bprocess improvement\b", 2), (r"\bchange management\b", 2),
        (r"\boperational excellence\b", 2), (r"\btransformation\b", 1),
        (r"\bcase team\b", 2), (r"\bmckinsey|bain|bcg|deloitte|accenture|kpmg|pwc|ey\b", 2),
    ],
    TECH: [
        # Role title signals — high weight, very specific
        (r"\bdata engineer", 3), (r"\bdata analyst\b", 3), (r"\bbusiness analyst\b", 2),
        (r"\bsoftware engineer", 2), (r"\bdevops\b", 2),
        (r"\bsre\b", 2), (r"\bplatform engineer", 2), (r"\bml engineer", 2),
        # Analytics & BI — data analyst JDs always mention these
        (r"\bdata (pipeline|platform|infrastructure|architecture|analytics|analysis)", 2),
        (r"\bbusiness intelligence\b", 3), (r"\banalytics engineer\b", 3),
        (r"\bpower bi\b|\btableau\b|\blooker\b|\bqlik\b", 2),
        # Data stack tools — score 2 (specific tech tools)
        (r"\bkafka\b|\bspark\b|\bdatabricks\b|\bairflow\b|\bdbt\b", 2),
        (r"\bkubernetes\b|\bdocker\b|\bterraform\b", 2),
        (r"\bsnowflake\b|\bbigquery\b|\bredshift\b", 2),
        # Generic languages — score 1 (can appear in many roles)
        (r"\bpython\b|\bsql\b|\bjava\b|\bscala\b", 1),
        (r"\bcloud (infrastructure|platform|architecture)", 2),
        (r"\bci/cd\b|\bgithub actions\b|\bjenkins\b", 2),
    ],
}

# Everything else → GENERAL
_GENERAL_THRESHOLD = 2   # minimum score to NOT fall back to GENERAL


# ── Title-based role detection ─────────────────────────────────────────────────
# Patterns matched ONLY against the job title (first 1-3 lines of JD).
# More reliable than body-scan because financial words in a DA JD body
# no longer override the title "Data Analyst".
# Order matters: IB/CYBER/HEALTHCARE are checked before FINANCE/TECH
# to catch "Investment Banking Analyst" before "Financial Analyst".
_TITLE_SIGNALS: list[tuple[re.Pattern, str]] = [
    # IB — very specific titles
    (re.compile(r"\binvestment bank|\bm&a\b|leveraged finance|capital markets|ecm\b|dcm\b|deal execut", re.I), IB),
    # CYBER
    (re.compile(r"\bcyber|infosec|security (analyst|engineer|architect|operations)|soc analyst|penetration|threat intel|grc analyst", re.I), CYBER),
    # HEALTHCARE
    (re.compile(r"\bnurse\b|\bphysician\b|\bclinical\b|nurse practitioner|health informatics|medical officer|pharmacist|therapist\b", re.I), HEALTHCARE),
    # CONSULTING
    (re.compile(r"\bconsultant\b|strategy (consultant|analyst)|management consult|advisory (analyst|associate)", re.I), CONSULTING),
    # FINANCE — only pure finance titles, NOT data analyst
    (re.compile(r"\bfp&a\b|financial planning|financial (controller|reporting|accountant)|accounting (analyst|manager)|treasurer\b|tax analyst", re.I), FINANCE),
    # TECH — data/software/analytics titles (broad but specific enough)
    (re.compile(
        r"\bdata (analyst|scientist|engineer|architect|steward|governance|quality|modeler)\b"
        r"|\banalytics (analyst|engineer|manager)\b"
        r"|\bbusiness (analyst|intelligence analyst|systems analyst)\b"
        r"|\bsoftware (engineer|developer|architect)\b"
        r"|\bml engineer|machine learning|devops|sre\b|platform engineer"
        r"|\bcloud (engineer|architect)|full.?stack|backend|frontend|mobile developer"
        r"|\bdata ops|mlops|bi (analyst|developer|engineer)\b",
        re.I), TECH),
    # FINANCE fallback — broader finance titles that didn't match above
    (re.compile(r"\bfinancial analyst|\bfinance (analyst|associate|manager)\b|equity analyst|credit analyst|portfolio analyst", re.I), FINANCE),
]


_TITLE_ROLE_RE = re.compile(
    r"\b(analyst|engineer|developer|architect|manager|specialist|coordinator|"
    r"associate|consultant|scientist|administrator|director|lead|officer|"
    r"designer|strategist|advisor)\b",
    re.I,
)

def _extract_jd_title(jd: str) -> str:
    """
    Extract the job title from the first 10 lines of the JD.

    Strategy (priority order):
    1. First short line (≤12 words) that contains a role-indicator word — catches
       JDs that open with a company name line before the actual job title.
    2. First short line regardless of content — fallback for unconventional formats.
    3. First 120 chars of the JD.
    """
    lines = [l.strip() for l in jd.strip().splitlines()[:10] if l.strip()]
    # Skip obvious boilerplate
    lines = [
        l for l in lines
        if not re.match(r"^(about|who we|our company|careers|apply|https?://)", l, re.I)
    ]
    # Pass 1: prefer a short line that looks like a job title (has role word)
    for line in lines:
        if len(line.split()) <= 12 and _TITLE_ROLE_RE.search(line):
            return line
    # Pass 2: any short line
    for line in lines:
        if len(line.split()) <= 12:
            return line
    # Pass 3: raw fallback
    return jd.strip()[:120]


def detect_role_type(jd: str) -> str:
    """
    Title-first role detection.

    Step 1: Extract job title from first few lines of JD and match against
            _TITLE_SIGNALS. Title match is authoritative — if we find one,
            return immediately without scanning the body.

    Step 2: If title is ambiguous (no match or title too generic), fall back
            to full-body keyword scoring via _ROLE_SIGNALS.

    This prevents financial words in a Data Analyst JD body from overriding
    the obvious title signal.
    """
    # ── Step 1: Title-first ───────────────────────────────────────────────────
    title = _extract_jd_title(jd)
    for pattern, role_type in _TITLE_SIGNALS:
        if pattern.search(title):
            return role_type

    # ── Step 2: Full-body keyword scoring (fallback) ──────────────────────────
    jd_low = jd.lower()
    scores: dict[str, int] = {rt: 0 for rt in _ROLE_SIGNALS}

    for role_type, signals in _ROLE_SIGNALS.items():
        for pattern, weight in signals:
            if re.search(pattern, jd_low):
                scores[role_type] += weight

    best_role = max(scores, key=lambda r: scores[r])
    best_score = scores[best_role]

    if best_score < _GENERAL_THRESHOLD:
        return GENERAL

    # IB beats FINANCE when both score high (IB is more specific)
    if scores[IB] > 0 and scores[FINANCE] > 0 and scores[IB] >= scores[FINANCE]:
        return IB

    # TECH beats FINANCE on ties — dict iteration order otherwise favors
    # FINANCE in max(), and finance-sounding words (budget, forecast,
    # reporting) are common in data/BI JD bodies for roles that are still
    # data/analytics roles, not corporate finance.
    if scores[TECH] > 0 and scores[FINANCE] > 0 and scores[TECH] >= scores[FINANCE]:
        return TECH

    return best_role


# ════════════════════════════════════════════════════════════════════════════
# Dynamic JD keyword extractor (primary method — no hardcoded catalog needed)
# ════════════════════════════════════════════════════════════════════════════

# Small seed list: compound phrases that are ambiguous as single words
_DYN_COMPOUND_PHRASES: list[tuple[str, str]] = [
    ("Data Warehouse",          r"\bdata\s+warehou"),
    ("Data Lake",               r"\bdata\s+lakes?\b"),
    ("Delta Lake",              r"\bdelta\s+lake\b"),
    ("Data Lakehouse",          r"\blakehouse\b"),
    ("Data Pipeline",           r"\bdata\s+pipelines?\b"),
    ("Data Modeling",           r"\bdata\s+model(?:ing|s)?\b"),
    ("Data Integration",        r"\bdata\s+integration\b"),
    ("Data Architecture",       r"\bdata\s+architect(?:ure)?\b"),
    ("Data Engineering",        r"\bdata\s+engineering\b"),
    ("Data Science",            r"\bdata\s+science\b"),
    ("Metadata Management",     r"\bmetadata\s+management\b"),
    ("Data Governance",         r"\bdata\s+governance\b"),
    ("Data Quality",            r"\bdata\s+quality\b"),
    ("Data Catalog",            r"\bdata\s+catalog\b"),
    ("Data Lineage",            r"\bdata\s+lineage\b"),
    ("Machine Learning",        r"\bmachine\s+learning\b"),
    ("Business Intelligence",   r"\bbusiness\s+intelligence\b"),
    ("Data Visualization",      r"\bdata\s+visuali"),
    ("Financial Modeling",      r"\bfinancial\s+model"),
    ("Process Improvement",     r"\bprocess\s+improvement\b"),
    ("Change Management",       r"\bchange\s+management\b"),
    ("Master Data Management",  r"\bmaster\s+data\s+management\b"),
    ("Risk Management",         r"\brisk\s+management\b"),
    ("Cloud Security",          r"\bcloud\s+security\b"),
    ("Incident Response",       r"\bincident\s+response\b"),
    ("Threat Hunting",          r"\bthreat\s+hunting\b"),
    ("Data Mesh",               r"\bdata\s+mesh\b"),
    ("Data Fabric",             r"\bdata\s+fabric\b"),
    ("Medallion Architecture",  r"\bmedallion\b"),
    ("Star Schema",             r"\bstar\s+schema\b"),
    ("Data Vault",              r"\bdata\s+vault\b"),
    ("Zero Trust",              r"\bzero\s+trust\b"),
    ("Change Data Capture",     r"\bchange\s+data\s+capture\b"),
    ("Middleware",              r"\bmiddleware\b"),
    ("Event-Driven",            r"\bevent[-\s]driven\b"),
]

# Multi-word vendor names -> canonical single form
_DYN_MULTI_WORD: list[tuple[str, str]] = [
    (r"\bapache\s+kafka\b",                     "Kafka"),
    (r"\bapache\s+spark\b",                     "Spark"),
    (r"\bapache\s+flink\b",                     "Flink"),
    (r"\bapache\s+airflow\b",                   "Airflow"),
    (r"\bapache\s+iceberg\b",                   "Iceberg"),
    (r"\bapache\s+hudi\b",                      "Hudi"),
    (r"\bapache\s+hadoop\b",                    "Hadoop"),
    (r"\bapache\s+hive\b",                      "Hive"),
    (r"\bapache\s+atlas\b",                     "Apache Atlas"),
    (r"\bapache\s+pulsar\b",                    "Pulsar"),
    (r"\bapache\s+superset\b",                  "Superset"),
    (r"\bgoogle\s+bigquery\b",                  "BigQuery"),
    (r"\bgoogle\s+cloud\s+platform\b",          "GCP"),
    (r"\bgoogle\s+cloud\b",                     "GCP"),
    (r"\bamazon\s+web\s+services\b",            "AWS"),
    (r"\bmicrosoft\s+azure\b",                  "Azure"),
    (r"\bmicrosoft\s+fabric\b",                 "Microsoft Fabric"),
    (r"\bmicrosoft\s+dynamics\b",               "Microsoft Dynamics"),
    (r"\bmicrosoft\s+dataverse\b",              "Dataverse"),
    (r"\bazure\s+synapse(?:\s+analytics)?\b",   "Synapse Analytics"),
    (r"\bazure\s+data\s+factory\b",             "Azure Data Factory"),
    (r"\bazure\s+devops\b",                     "Azure DevOps"),
    (r"\bazure\s+key\s+vault\b",                "Azure Key Vault"),
    (r"\bazure\s+purview\b",                    "Azure Purview"),
    (r"\bazure\s+functions?\b",                  "Azure Functions"),
    (r"\bazure\s+cloud(?:\s+platform)?\b",      "Azure Cloud Platform"),
    (r"\bazure\s+event\s+hubs?\b",              "Event Hubs"),
    (r"\bpower\s+bi\b",                         "Power BI"),
    (r"\bgithub\s+actions\b",                   "GitHub Actions"),
    (r"\bgitlab\s+ci(?:/cd)?\b",                "GitLab CI"),
    (r"\bdbt\s+(?:core|cloud)\b",               "dbt"),
    (r"\bsql\s+server\b",                       "SQL Server"),
    (r"\bcloud\s+composer\b",                   "Cloud Composer"),
    (r"\bstep\s+functions\b",                   "AWS Step Functions"),
    (r"\blake\s+formation\b",                   "Lake Formation"),
    (r"\bgreat\s+expectations\b",               "Great Expectations"),
    (r"\bmonte\s+carlo\b",                      "Monte Carlo"),
    (r"\bunity\s+catalog\b",                    "Unity Catalog"),
    (r"\bapache\s+ranger\b",                    "Apache Ranger"),
    (r"\bsix\s+sigma\b",                        "Six Sigma"),
    (r"\bburp\s+suite\b",                       "Burp Suite"),
    (r"\bcapital\s+iq\b",                       "Capital IQ"),
    (r"\bpalo\s+alto\s+networks?\b",             "Palo Alto Networks"),
    (r"\bvertex\s+ai\b",                        "Vertex AI"),
    (r"\bfeature\s+store\b",                    "Feature Store"),
    (r"\bvector\s+database\b",                  "Vector Database"),
    (r"\bmaster\s+data\s+management\b",         "MDM"),
    (r"\bnatural\s+language\s+processing\b",    "NLP"),
    (r"\bcertified\s+solutions?\s+architect\b", "AWS Certified"),
    (r"\baws\s+certif",                         "AWS Certified"),
    (r"\baws\s+certified\s+data\s+analytics\b", "AWS Certified"),
    (r"\bgcp\s+certif",                         "GCP Certified"),
    (r"\bgoogle\s+cloud\s+certif",              "GCP Certified"),
    (r"\bprofessional\s+data\s+engineer\b",     "GCP Certified"),
    (r"\bmicrosoft\s+sentinel\b",               "Microsoft Sentinel"),
    (r"\bpub/sub\b",                            "Pub/Sub"),
    # Degree field names — normalizing prevents standalone fragments ("Computer",
    # "Engineering", "Biomedical") from remaining after _dyn_remove_components
    (r"\bcomputer\s+science\b",                "Computer Science"),
    (r"\bbiomedical\s+informatics\b",          "Biomedical Informatics"),
    (r"\bbiomedical\s+engineering\b",          "Biomedical Engineering"),
    (r"\bhealth\s+informatics\b",              "Health Informatics"),
    # Ampersand-notation compound terms — must normalize before ALL-CAPS step splits them
    (r"\bfp\s*&\s*a\b",                         "FP&A"),
    (r"\bm\s*&\s*a\b",                          "M&A"),
    (r"\batt&ck\b",                             "ATT&CK"),
    (r"\bmitre\s+att&ck\b",                     "MITRE ATT&CK"),
    (r"\becm\b",                                "ECM"),
    (r"\bdcm\b",                                "DCM"),
]

# ── Minimal universal skip lists ─────────────────────────────────────────────
# These are NOT per-JD patches. They are truly universal words that can never
# be technical skills regardless of context. Keep this list stable and small.
# The high-signal zone extraction (below) handles the rest structurally.

_DYN_PROP_SKIP: set[str] = {
    # Articles/pronouns that appear capitalized in section titles
    "We","Our","You","Your","They","This","That","All","Both","Each","The","A","An",
    # Vendor name prefixes that split off as standalone words
    "Apache","Microsoft","Amazon","Google",
    # Degree types — appear even in requirements sections
    "Bachelor","Master","Phd","Msc","Bsc","Mba",
    # Role words that slip into skill lists
    "Engineer","Developer","Architect","Analyst","Manager","Director",
    "Lead","Senior","Junior","Principal","Staff",
    # Generic business nouns that can never be standalone skills
    "Solution","Solutions","System","Systems","Service","Services",
    "Application","Applications","Process","Processes","Platform","Platforms",
    "Environment","Environments","Product","Products","Team","Teams",
    "Organization","Company","Department","Business","Enterprise",
}
_DYN_PROP_SKIP_LOWER: set[str] = {w.lower() for w in _DYN_PROP_SKIP}

_DYN_ACRONYM_SKIP: set[str] = {
    # English function words that appear in ALL-CAPS for emphasis
    "THE","AND","OR","NOT","FOR","ARE","HAS","WITH","FROM","THAT","THIS",
    "THEY","ALSO","BOTH","EACH","HAVE","WILL","MUST","CAN","MAY","WHO","HOW",
    "WHAT","WHY","WHEN","ROLE","PERKS","YOULL",
    "YOU","WE","ALL","ANY","DO","WAS","ITS","BUT","NOW","END","NEW","INC","LLC",
    # Business model / org hierarchy — appear even in requirements sections
    "B2B","B2C","B2G","D2C","VP","SVP","EVP","CEO","CTO","CFO","COO","CIO",
    # Education qualifiers — appear in requirements ("BS/MS preferred")
    "BS","MS","MBA","PHD","BA","AA",
    # AI concepts used as company description jargon, not candidate skills
    "AGI","ASI",
    # US state abbreviations from location lines
    "USA","US","NYC","SF","LA","DC","UK","EU",
    "TX","CA","NY","FL","IL","WA","GA","MA","PA","OH","VA",
    "CO","OR","MN","WI","IN","MO","TN","MD","AZ","NV","UT",
    "CT","IA","KS","NE","NM","ID","MT","WY","ND","SD","WV","ME","NH","VT","RI","DE","AK","HI",
    # Slash notation fragment noise
    "CI","CD","IT","ASQ",
}

# ── Zone detection ────────────────────────────────────────────────────────────
# HIGH-SIGNAL: requirements/qualifications/skills — Steps 3-6 run here.
# MEDIUM-SIGNAL: duties/responsibilities — only Steps 5-6 (ALL-CAPS, alphanumeric)
# run here. Steps 3-4 (TitleCase/CamelCase) are suppressed to avoid extracting
# responsibility-sentence verbs ("Designs and develops", "Integrates, builds")
# as if they were technical skills.
# This is purely structural — no per-word blacklisting needed.

_HIGH_SIGNAL_ZONE_RE = re.compile(
    r"^(requirements?|qualifications?|"
    r"technical\s+skills?|skills?\s+required|required\s+skills?|"
    r"what\s+we.re?\s+looking|preferred(?:\s+qualifications?)?|"
    r"experience\s+required|what\s+you.ll\s+bring|what\s+you\s+bring|"
    r"who\s+you\s+are|"
    r"what\s+a\s+(great\s+)?candidate|additional\s+requirements?|"
    r"minimum\s+(?:job\s+)?requirements?)\b",
    re.IGNORECASE,
)

# Duties/responsibilities AND KSA sections — medium signal:
# ALL-CAPS acronyms are valid (EHR, HL7, ETL appear in both duties and KSA)
# TitleCase verbs and soft-skill adjectives are NOT extracted (Steps 3-4 suppressed)
_MEDIUM_SIGNAL_ZONE_RE = re.compile(
    r"^(responsibilities?|what\s+you.ll\s+do|what\s+you\s+will\s+do|"
    r"key\s+responsibilities?|job\s+specific\s+duties?|job\s+duties?|"
    r"essential\s+(?:job\s+)?(?:duties?|functions?)|"
    r"primary\s+(?:duties?|responsibilities?|functions?)|"
    r"position\s+(?:duties?|responsibilities?|summary)|"
    r"role\s+(?:duties?|responsibilities?)|"
    r"the\s+opportunity|about\s+the\s+role|"
    # KSA sections: soft-skill words (TitleCase) suppressed, but ALL-CAPS tech
    # acronyms (EHR, HL7, PeopleSoft via Step 8 on full text) still captured
    r"knowledge,?\s+skills,?\s+(and\s+)?abilities?|"
    r"knowledge\s+and\s+skills?|core\s+competencies?|"
    r"behavioral\s+(competencies?|requirements?))\b",
    re.IGNORECASE,
)

_END_HIGH_SIGNAL_RE = re.compile(
    r"^(success\s+metrics?|leadership\s+competencies?|physical|"
    r"compensation|salary\s+range?|benefits?|perks?|"
    r"culture|why\s+join|about\s+(us|the\s+company|nimble|quantifind|\w+)|"
    r"who\s+we\s+are|our\s+(mission|values|culture|story)|"
    r"will\s+you\s+join|apply|contact\s+us|"
    # KSA / behavioral sections — contain soft requirements, not technical skills
    r"knowledge,?\s+skills,?\s+(and\s+)?abilities?|"
    r"knowledge\s+and\s+skills?|core\s+competencies?|"
    r"behavioral\s+(competencies?|requirements?)|"
    r"additional\s+information)\b",
    re.IGNORECASE,
)


def _get_high_signal_text(jd_clean: str) -> str:
    """
    Extract only requirements/qualifications/skills section content.
    Runs AFTER _strip_jd_noise() — noise sections already removed.
    Falls back to full cleaned text for unstructured JDs with no clear headers.
    """
    lines = jd_clean.splitlines()
    high = []
    in_zone = False
    found_any = False

    for line in lines:
        stripped = line.strip()
        if _HIGH_SIGNAL_ZONE_RE.match(stripped):
            in_zone = True
            found_any = True
        elif _END_HIGH_SIGNAL_RE.match(stripped):
            in_zone = False

        if in_zone:
            high.append(line)

    # Unstructured JD (no clear headers) → use full cleaned text as fallback
    if not found_any:
        return jd_clean

    return "\n".join(high)


def _get_medium_signal_text(jd_clean: str) -> str:
    """
    Extract duties/responsibilities section content.
    Only ALL-CAPS and alphanumeric steps run on this text — TitleCase/CamelCase
    steps are suppressed to avoid extracting responsibility verbs as skills.
    Returns empty string if no duties section found.
    """
    lines = jd_clean.splitlines()
    medium: list[str] = []
    in_zone = False

    for line in lines:
        stripped = line.strip()
        if _MEDIUM_SIGNAL_ZONE_RE.match(stripped):
            in_zone = True
        elif _HIGH_SIGNAL_ZONE_RE.match(stripped) or _END_HIGH_SIGNAL_RE.match(stripped):
            in_zone = False  # requirements or KSA section starts = duties zone ends

        if in_zone:
            medium.append(line)

    return "\n".join(medium)


# These acronyms/tools are independent skills — never removed as sub-components
_DYN_NEVER_REMOVE: set[str] = {
    "AWS","GCP","Azure","SQL","ETL","ELT","MDM","HIPAA","GDPR","SOC",
    "RBAC","PII","Python","Java","Scala","Kafka","Spark","dbt",
    "Docker","Git","Hadoop","HDFS","NoSQL","DB2",
}

_DYN_SIGNAL_RE = re.compile(
    r"(?:experience\s+(?:with|in|using|building|implementing)|"
    r"proficien(?:t|cy)\s+in|knowledge\s+of|familiarity\s+with|"
    r"hands.on\s+(?:with|in|experience\s+with)|expertise\s+in|"
    r"working\s+(?:with|knowledge\s+of)|background\s+in|"
    r"exposure\s+to|such\s+as|e\.g\.|including|tools?:?)"
    r"[,:\s]+([^\n.;]{3,200})",
    re.IGNORECASE,
)


def _dyn_remove_components(items: list[str]) -> list[str]:
    """
    Remove items that are fragments of larger compound terms already in the set.
    Handles both space-separated compounds (Six Sigma -> Six, Sigma)
    and slash/ampersand compounds (FP&A -> FP, ATT&CK -> ATT/CK).
    """
    s = set(items)
    result = []
    for item in items:
        if item in _DYN_NEVER_REMOVE:
            result.append(item)
            continue
        is_component = any(
            item != other
            and (len(other.split()) > 1 or bool(re.search(r"[/&]", other)))
            and re.search(r"\b" + re.escape(item) + r"\b", other, re.IGNORECASE)
            for other in s
        )
        if not is_component:
            result.append(item)
    return result


_JD_NOISE_HEADERS = re.compile(
    r"^(benefits?[\s&+]*perks?|life\s+at\s+\w+|why\s+\w+|about\s+\w+|"
    r"equal\s+opportunity|eeo|diversity|culture\s+club|compensation|"
    r"what\s+we\s+offer|we\s+offer|perks?|our\s+benefits?|"
    r"employee\s+benefits?|what.s\s+in\s+it|working\s+at\s+\w+|"
    r"the\s+perks|why\s+join|join\s+us|"
    r"physical\s+environment|view\s+all\s+jobs?|"
    r"complies\s+with\s+all\s+applicable|equal\s+opportunity\s+employer|"
    r"all\s+qualified\s+applicants|"
    # Company description (safe to strip — no tech requirements)
    r"who\s+we\s+are|a\s+highlight\s+of|will\s+you\s+join|apply\s+now|"
    r"our\s+culture|our\s+values|our\s+mission|"
    r"about\s+the\s+(company|team))\b",
    re.IGNORECASE,
)

# Section headers that RE-ENABLE extraction after a noise section
_JD_CONTENT_HEADERS = re.compile(
    r"^(what\s+you.ll\s+do|what\s+you\s+will\s+do|responsibilities|"
    r"requirements?|qualifications?|what\s+we.re?\s+looking|"
    r"key\s+responsibilities|the\s+role|your\s+role|"
    r"what\s+you.ll\s+bring|what\s+you\s+bring|experience\s+required|"
    r"skills?\s+required|technical\s+requirements?|"
    r"the\s+opportunity|who\s+you\s+are|"
    r"what\s+a\s+(great\s+)?candidate|what\s+we.re\s+looking)\b",
    re.IGNORECASE,
)

# Line-level physical/legal signal — skip individual lines even mid-section
_PHYSICAL_SIGNALS = re.compile(
    r"\b(lift\s+and/or|push/pull|bend.*reach|noise\s+level|"
    r"qualified\s+applicants?\s+will\s+receive|"
    r"without\s+regard\s+to\s+race|bank\s+secrecy\s+act|"
    r"patriot\s+act|anti.money\s+laundering|"
    r"view\s+all\s+jobs?)\b",
    re.IGNORECASE,
)

def clean_jd_html(text: str) -> str:
    """
    Decode HTML-entity-encoded JDs and strip tags. Some ATS feeds deliver
    double-encoded HTML (&amp;lt;h3&amp;gt;Requirements:&amp;lt;/h3&amp;gt;) — section
    headers buried in tags break zone-based extraction (0 skills → ATS 0/0)
    and feed tag soup to the tailor model.
    """
    if not text:
        return text
    if "<" not in text and "&lt;" not in text and "&amp;" not in text and "&#" not in text:
        return text
    import html as _html
    # Unescape repeatedly — feeds are often double-encoded (&amp;lt; → &lt; → <)
    for _ in range(3):
        unescaped = _html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    # Drop script/style and embedded media (videos, players) wholesale —
    # keep only the JD text around them
    text = re.sub(r'<(script|style|video|audio|iframe|embed|object|svg)[^>]*>.*?</\1>',
                  ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Self-closing / unclosed media tags
    text = re.sub(r'<(video|audio|iframe|embed|source|track|img)[^>]*/?>', ' ',
                  text, flags=re.IGNORECASE)
    # Bare video-platform links left in plain text
    text = re.sub(r'https?://\S*(youtube\.com|youtu\.be|vimeo\.com|loom\.com|'
                  r'wistia\.com|vidyard\.com|brightcove\.com)\S*', ' ',
                  text, flags=re.IGNORECASE)
    # Structural tags → line breaks so section headers land on their own lines
    text = re.sub(r'<li[^>]*>', '\n• ', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(p|br|div|h[1-6]|ul|ol|tr|table)[^>]*/?>', '\n', text, flags=re.IGNORECASE)
    # Remaining tags → space
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse whitespace but keep line structure
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Sentence-level noise for single-paragraph blob JDs (no line structure):
# benefits, EEO/legal, recruiting-agency, and pay-disclosure sentences.
_BLOB_NOISE_RE = re.compile(
    r"\b(benefits?\s+include|medical\s+insurance|dental|vision\s+insurance|"
    r"401\s*\(?k\)?|paid\s+time\s+off|pto\b|paid\s+holidays?|perks?\b|"
    r"equal\s+opportunity|discriminat\w+|harassment|protected\s+characteristic|"
    r"accommodations?\s+to\s+applicants|search\s+firms?|unsolicited|"
    r"base\s+pay|salary\s+range|pay\s+position|total\s+rewards|"
    r"come\s+(check\s+us\s+out|grow)|#li-)",
    re.IGNORECASE,
)


def _strip_jd_noise(jd_text: str) -> str:
    """
    Remove benefits/culture/legal/physical sections from JD text before extraction.
    - Noise headers (benefits, EEO, company description) trigger skip=True
    - Content headers (requirements, responsibilities, opportunity) trigger skip=False
    - This lets the function handle JDs where requirements come AFTER company description
    - Individual physical/legal boilerplate lines are always dropped regardless
    """
    lines = jd_text.splitlines()
    # Zone logic is line-based. Scraped JDs sometimes arrive as one paragraph
    # blob (no newlines) — a leading "About Us ..." would then nuke the ENTIRE
    # JD, and downstream boilerplate detection would flag every requirements
    # word as noise (live run: 24 false [JD BOILERPLATE TERM] flags told
    # retries to delete 'conceptual'/'logical'/'canonical' from the resume).
    if len([l for l in lines if l.strip()]) < 5:
        # Sentence-level fallback: drop benefits/EEO/legal sentences inline,
        # keep requirements text intact.
        sentences = re.split(r"(?<=[.!?])\s+", jd_text)
        kept = [s for s in sentences if not _BLOB_NOISE_RE.search(s)]
        return " ".join(kept) if kept else jd_text
    result = []
    skip = False
    for line in lines:
        stripped = line.strip()
        # Re-enable if we hit a requirements/responsibilities section
        if _JD_CONTENT_HEADERS.match(stripped):
            skip = False
        # Disable if we hit a noise section
        elif _JD_NOISE_HEADERS.match(stripped):
            skip = True
        if skip:
            continue
        # Drop individual physical/legal lines even outside a noise section
        if _PHYSICAL_SIGNALS.search(stripped):
            continue
        result.append(line)
    out = "\n".join(result)
    # Stripped more than ~2/3 of the JD → headers misfired for this format;
    # extraction on the full text beats extraction on a gutted fragment.
    if len(out) < 0.35 * len(jd_text):
        return jd_text
    return out


def extract_jd_keywords_dynamic(jd_text: str) -> list[str]:
    """
    Extract technical keywords directly from JD text.

    Architecture: structural zone filtering, not word blacklisting.
      1. _strip_jd_noise() removes boilerplate sections (benefits, EEO, company desc).
      2. _get_high_signal_text() isolates requirements/qualifications/skills sections.
      3. Steps 3-6 (CamelCase, TitleCase, ALL-CAPS, alphanumeric) run ONLY on
         high-signal zones — eliminates garbage from company descriptions without
         needing per-word skip lists.
      4. Steps 1-2 (compound phrases, multi-word tools) and 7-10 run on full
         cleaned text — they are targeted enough to not need zone restriction.
    """
    found: set[str] = set()

    # Pass 0: decode HTML-encoded feeds (tags hide section headers from zones)
    jd_text = clean_jd_html(jd_text)

    # Pass 1: strip boilerplate (benefits, EEO, physical requirements, etc.)
    jd_clean = _strip_jd_noise(jd_text)

    # Pass 2a: requirements/qualifications zones → Steps 3-6 run here (all steps)
    jd_high = _get_high_signal_text(jd_clean)

    # Pass 2b: duties/responsibilities zones → only Steps 5-6 run here.
    # Suppressing Steps 3-4 (TitleCase/CamelCase) prevents responsibility-sentence
    # verbs ("Designs and develops", "Integrates, builds") from being extracted as skills.
    jd_medium = _get_medium_signal_text(jd_clean)

    lines_clean = jd_clean.strip().splitlines()
    # Skip first line (job title — common false positive source)
    text_full  = "\n".join(lines_clean[1:]) if len(lines_clean) > 1 else jd_clean

    lines_high = jd_high.strip().splitlines()
    # High-signal body: also skip first line if it's the JD title
    text_high   = "\n".join(lines_high[1:]) if len(lines_high) > 1 else jd_high
    # Medium-signal: duties text (no first-line skip needed — section headers are the first line)
    text_medium = jd_medium.strip()
    # Combined text for Steps 5-6 (ALL-CAPS/alphanumeric — safe on duties text too)
    text_caps   = text_high + ("\n" + text_medium if text_medium else "")

    # 1. Compound tech phrases — run on full cleaned text (targeted patterns)
    for display, pat in _DYN_COMPOUND_PHRASES:
        if re.search(pat, text_full, re.IGNORECASE):
            found.add(display)

    # 2. Multi-word vendor names → canonical — run on full cleaned text
    for pat, canonical in _DYN_MULTI_WORD:
        if re.search(pat, text_full, re.IGNORECASE):
            found.add(canonical)

    # 3-6: Run on HIGH-SIGNAL TEXT ONLY — zone filter eliminates company
    # description garbage without needing per-word blacklisting.

    # 3. CamelCase single-word tech terms (PySpark, BigQuery, MLflow, ClickHouse)
    for w in re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-zA-Z0-9]*)+\b", text_high):
        if w not in _DYN_PROP_SKIP and w.lower() not in _DYN_PROP_SKIP_LOWER:
            found.add(w)

    # 4. TitleCase words in comma-separated tech-list context
    # Use [^\S\n]* (not \s*) to prevent cross-line match: section headers ending
    # with ":" would otherwise bleed into the first word of the next line.
    for m in re.finditer(r"[,;:\(][^\S\n]*([A-Z][a-z]{2,18})\b", text_high):
        w = m.group(1)
        if w not in _DYN_PROP_SKIP and w.lower() not in _DYN_PROP_SKIP_LOWER:
            found.add(w)

    # 5. ALL-CAPS acronyms 2-6 chars (ETL, AWS, SQL, GCP, HDFS, MDM, HIPAA)
    # Run on text_caps (high + medium) — acronyms in duties text are valid skills
    for a in re.findall(r"\b[A-Z]{2,6}\b", text_caps):
        if a not in _DYN_ACRONYM_SKIP:
            found.add(a)

    # 6. Alphanumeric tool names: DB2, S3, H2O
    for a in re.findall(r"\b[A-Z]{1,4}\d[a-zA-Z0-9]*\b", text_caps):
        if a not in _DYN_ACRONYM_SKIP and a not in _DYN_PROP_SKIP:
            found.add(a)

    # 7. Slash / ampersand notation: CI/CD, ETL/ELT, FP&A, ATT&CK, M&A
    for s in re.findall(r"\b[A-Za-z]{1,8}[/&][A-Za-z]{1,8}\b", text_full):
        parts = re.split(r"[/&]", s)
        if len(parts) != 2:
            continue
        a, b = parts
        # Skip if both sides are identical (dbt/dbt, and/or, days/days)
        if a.lower() == b.lower():
            continue
        # Only keep if BOTH sides are ALL-CAPS (CI/CD, ETL/ELT, TCP/IP)
        # OR ampersand with at least one uppercase side (FP&A, M&A, ATT&CK)
        # OR known lowercase tech compound (pub/sub)
        is_both_caps = a.isupper() and b.isupper()
        is_amp_tech  = "&" in s and (a.isupper() or b.isupper())
        is_known     = s.lower() in {"pub/sub", "read/write", "r/w"}
        if not (is_both_caps or is_amp_tech or is_known):
            continue
        if s.upper() not in _DYN_ACRONYM_SKIP:
            found.add(s)

    # 7b. Single-letter-plus-hash language names: C#, F#. Every other step
    # requires a minimum token length (CamelCase needs an internal lowercase
    # run, ALL-CAPS needs 2+ letters, the signal-phrase step needs 4+ chars)
    # so a 2-character symbol token structurally can never surface — "C#"
    # was invisible to JD-skill extraction even when it was a JD's #1 named
    # requirement. Pattern-based (not a name list) so it generalizes to any
    # future single-letter+# language, not just these two.
    for m in re.finditer(r"(?<![A-Za-z0-9])([A-Za-z])#(?![A-Za-z0-9])", text_full):
        found.add(m.group(1).upper() + "#")

    # 8. Capitalized words after skill-signal phrases
    # Strip parenthetical expansions before scanning inner words — "(Data Build Tool)"
    # is an acronym expansion, not a list of independent skills.
    for m in _DYN_SIGNAL_RE.finditer(text_full):
        group_text = re.sub(r"\([^)]+\)", "", m.group(1))
        # Require ≥4 chars total to filter short generic words ("Use", "Web", "Go")
        for w in re.findall(r"\b[A-Z][a-zA-Z0-9+#.]{3,20}\b", group_text):
            if w not in _DYN_PROP_SKIP and w.lower() not in _DYN_PROP_SKIP_LOWER:
                found.add(w)

    # 9. Version-tagged tools: "Python 3", "Spark 3.x" -> extract tool name
    # Run on text_high to avoid "Lifts 10 lbs" type false positives from physical sections
    for v in re.findall(r"\b([A-Z][a-zA-Z0-9+#.]+)\s+\d+(?:\.\d+)*[x+]?\b", text_high):
        if v not in _DYN_PROP_SKIP and v.lower() not in _DYN_PROP_SKIP_LOWER:
            found.add(v)

    # 10. Always-lowercase canonical tools
    if re.search(r"\bdbt\b", text_full, re.IGNORECASE):
        found.add("dbt")

    filtered = sorted(
        f for f in found
        if len(f) > 1
        and f not in _DYN_PROP_SKIP
        and f.upper() not in _DYN_ACRONYM_SKIP
    )
    return _dyn_remove_components(filtered)


# Business-domain jargon that belongs to a specific role type — not transferable
# tools/technologies. When the candidate's role type is locked (from their job
# preference) and doesn't match the JD's natural domain, these get dropped from
# the "must cover" skill list so the AI isn't forced to inject finance/clinical
# KPI language into an unrelated resume (e.g. a Data Analyst applying to a
# healthcare-titled JD shouldn't get "Medicaid"/"FP&A" as required skills).
_DOMAIN_LOCKED_TERMS: dict[str, set[str]] = {
    FINANCE:    {"fp&a", "p&l", "accounting", "financial modeling", "budget variance",
                 "month-end close", "board-ready", "treasury", "variance analysis",
                 "reconciliation", "general ledger", "gaap"},
    HEALTHCARE: {"medicaid", "medicare", "cms", "claims adjudication", "care coordination",
                 "clinical operations", "patient panel", "ehr", "emr", "icd-10", "cpt"},
    IB:         {"m&a", "leveraged finance", "ecm", "dcm", "capital markets", "deal execution"},
}


_DOMAIN_LEAK_PHRASES: dict[str, list[str]] = {
    FINANCE:    ["fp&a", "p&l", "board-ready", "month-end close", "budget variance",
                 "variance analysis", "general ledger", "gaap", "treasury"],
    HEALTHCARE: ["medicaid", "medicare", "\\bcms\\b", "claims adjudication",
                 "care coordination", "patient panel", "\\behr\\b", "\\bemr\\b", "icd-10"],
    IB:         ["leveraged finance", "capital markets", "deal execution", "\\bm&a\\b"],
}


def detect_domain_leak(text: str, role_type: str, base_resume: str = "") -> list[str]:
    """
    Flags finance/healthcare/IB business-domain jargon that doesn't belong in a
    resume locked to a different role type — even when the JD's employer is in
    that domain. Catches phrasing the model echoes straight from JD body text
    (not just extracted "hard skills").

    base_resume exemption: a term already present in the candidate's ORIGINAL
    resume is real work history, not a JD leak — never flag it. Also fixes the
    'emr' false positive: AWS EMR in a tech stack is not Electronic Medical
    Records, and it lives in the base resume, so the exemption clears it.
    """
    issues: list[str] = []
    base_lo = (base_resume or "").lower()
    for domain, phrases in _DOMAIN_LEAK_PHRASES.items():
        if domain == role_type:
            continue
        for phrase in phrases:
            if re.search(phrase, text, re.IGNORECASE):
                if base_lo and re.search(phrase, base_lo, re.IGNORECASE):
                    continue  # candidate's own history — not a leak
                shown = phrase.replace("\\b", "")
                issues.append(f"[DOMAIN LEAK] '{shown}' is {domain}-specific jargon — not allowed when role type is {role_type}.")
    return issues


# ── JD artifact leaks + verbatim clone runs ───────────────────────────────────
# Fully derivational — no term lists. Three signals:
# 1. Tag payloads (#LI-YG1 → "YG1") that exist ONLY as tags in the JD.
# 2. Code-shaped identifiers (RMC-6236, CHTRJP00090270) present in both.
# 3. Boilerplate-only tokens: in raw JD but stripped by _strip_jd_noise(),
# i.e. they live in legal/benefits/EEO zones (CCPA, PAIR, E-Verify...).
# base_resume exemption throughout: candidate's own history is never a leak.

_JD_TAG_RE  = re.compile(r"#([A-Za-z]{2})-([A-Za-z0-9]{2,})")
_JD_CODE_RE = re.compile(r"\b([A-Z]{2,6}-\d{2,6}|[A-Z]{2,8}\d{3,10})\b")
_LEAK_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-+#]*")

_CLONE_STOPWORDS = frozenset(
    "the a an and or of to in for with on at by from as is are be will can "
    "you your our this that using use used data team teams work working "
    "experience across including such other more most".split()
)


def _leak_tokens(text: str) -> set[str]:
    return set(_LEAK_TOKEN_RE.findall(text.lower()))


def detect_jd_artifact_leak(text: str, job_description: str,
                            base_resume: str = "") -> list[str]:
    """Recruiter tags, internal codes, and legal-boilerplate terms that
    traveled JD → resume but were never in the candidate's base resume."""
    if not job_description:
        return []
    issues: list[str] = []
    seen: set[str] = set()
    res_lo    = text.lower()
    base_toks = _leak_tokens(base_resume) if base_resume else set()
    jd_clean  = _strip_jd_noise(clean_jd_html(job_description))
    body_toks = _leak_tokens(_JD_TAG_RE.sub(" ", jd_clean))

    def _flag(tok: str, tag: str, why: str):
        key = tok.lower()
        if key in seen or key in base_toks:
            return
        seen.add(key)
        issues.append(f"{tag} '{tok}' — {why}")

    # 1. tag payloads that exist only as tags
    for m in _JD_TAG_RE.finditer(job_description):
        payload = m.group(2)
        p_lo = payload.lower()
        if (len(payload) >= 3 and p_lo in res_lo
                and p_lo not in body_toks):
            _flag(payload, "[JD ARTIFACT LEAK]",
                  f"recruiter/tracking tag payload ({m.group(0)}) copied "
                  f"from the JD into the resume. Delete it.")

    # 2. code-shaped identifiers present in both JD and resume
    res_codes = set(_JD_CODE_RE.findall(text))
    for code in set(_JD_CODE_RE.findall(job_description)) & res_codes:
        _flag(code, "[JD ARTIFACT LEAK]",
              "internal code/identifier copied from the JD. Delete it.")

    # 3. boilerplate-only tokens (stripped zones), absent from base resume.
    # Two precision guards (live run flagged 24 requirements words as
    # "boilerplate" on a single-paragraph JD and retries deleted them):
    # a. If noise-stripping removed a large share of the JD vocabulary,
    # zoning failed for this JD format — skip the signal entirely.
    # b. Only identifier-shaped tokens qualify (contains digit/hyphen, or
    # never appears as a plain lowercase word in the JD): CCPA, E-Verify,
    # LI-Hybrid — never ordinary English words like 'major' or 'near'.
    jd_raw = clean_jd_html(job_description)
    raw_toks = _leak_tokens(jd_raw)
    if len(body_toks) >= 0.3 * len(raw_toks):   # skip only on catastrophic zone failure
        res_toks = _leak_tokens(text)
        for tok in (raw_toks - body_toks) & res_toks:
            if len(tok) < 4 or tok in _CLONE_STOPWORDS or tok.isdigit():
                continue
            occ = re.findall(rf"\b{re.escape(tok)}\b", jd_raw, re.IGNORECASE)
            identifier_like = occ and all(
                "-" in o or any(c.isdigit() for c in o)
                or o.isupper() or o[1:] != o[1:].lower()   # CCPA, E-Verify, LangChain — not sentence-start 'Major'
                for o in occ
            )
            if identifier_like:
                _flag(tok, "[JD BOILERPLATE TERM]",
                      "this term appears only in the JD's legal/benefits "
                      "boilerplate, not its requirements. Remove it unless it "
                      "exists in the original resume.")
    return issues


def detect_jd_clone_runs(bullet_text: str, job_description: str,
                         base_resume: str = "",
                         min_words: int = 6, min_content: int = 4,
                         max_reports: int = 5) -> list[str]:
    """Verbatim word runs (≥min_words) shared between JD and resume bullets.
    Runs already present in the base resume are the candidate's own phrasing."""
    if not job_description or not bullet_text:
        return []
    jd_toks  = _LEAK_TOKEN_RE.findall(
        _strip_jd_noise(clean_jd_html(job_description)).lower())
    res_join  = " " + " ".join(_LEAK_TOKEN_RE.findall(bullet_text.lower())) + " "
    base_join = (" " + " ".join(_LEAK_TOKEN_RE.findall(base_resume.lower())) + " "
                 if base_resume else "")
    issues: list[str] = []
    seen: set[str] = set()
    i, n = 0, len(jd_toks)
    while i <= n - min_words and len(issues) < max_reports:
        phrase = " ".join(jd_toks[i:i + min_words])
        if f" {phrase} " in res_join:
            run = min_words
            while (i + run < n and
                   f" {' '.join(jd_toks[i:i + run + 1])} " in res_join):
                run += 1
            phrase = " ".join(jd_toks[i:i + run])
            content = sum(1 for w in jd_toks[i:i + run]
                          if w not in _CLONE_STOPWORDS)
            if (content >= min_content and phrase not in seen
                    and not (base_join and f" {phrase} " in base_join)):
                seen.add(phrase)
                issues.append(
                    f'[JD CLONE] {run}-word verbatim JD run in bullets — '
                    f'"{phrase}". Reword: screeners spot mirrored JDs.')
            i += run
        else:
            i += 1
    return issues


_TOOL_TOKEN_RES = (
    re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-zA-Z0-9]*)+\b"),   # CamelCase: PySpark, LangChain
    re.compile(r"\b[A-Z]{1,4}\d[a-zA-Z0-9]*\b"),            # alnum tools: S3, DB2, H2O
    re.compile(r"\b[A-Z]{3,6}\b"),                          # acronyms: HIPAA, SIEM
)


def detect_fabricated_tools(text: str, base_resume: str,
                            job_description: str = "",
                            max_reports: int = 5) -> list[str]:
    """Tech-shaped tokens (CamelCase / alphanumeric / acronym) in experience
    bullets or Technologies Used lines that exist in NEITHER the candidate's
    original resume NOR the JD. Those can only come from model priors —
    the model naming tools the candidate never claimed and the JD never asked
    for. Fully derivational: the allowed vocabulary IS base resume + JD."""
    if not base_resume:
        return []
    allowed = (base_resume + "\n" + (job_description or "")).lower()
    issues: list[str] = []
    seen: set[str] = set()
    in_exp = False
    for raw in text.splitlines():
        line = raw.strip()
        if _is_section_header(line):
            in_exp = "EXPERIENCE" in line.upper()
            continue
        if not in_exp or not line:
            continue
        is_tech_line = bool(re.match(r"^Technolog", line, re.IGNORECASE))
        if not (line.startswith("•") or is_tech_line):
            continue
        for tok_re in _TOOL_TOKEN_RES:
            for tok in tok_re.findall(line):
                key = tok.lower()
                if (key in seen or tok in _DYN_ACRONYM_SKIP
                        or key in allowed):
                    continue
                seen.add(key)
                if len(issues) < max_reports:
                    where = "Technologies Used line" if is_tech_line else "bullet"
                    issues.append(
                        f"[FABRICATED TOOL] '{tok}' appears in a {where} but exists "
                        f"in neither the original resume nor the JD — the model "
                        f"invented it. Replace with a tool the candidate actually "
                        f"used, or delete."
                    )
    return issues


def find_base_only_skills(base_resume: str, jd_skills: list[str]) -> list[str]:
    """JD skills that appear SOMEWHERE in the base resume (so skill_coverage_report
    marks them 'covered') but never inside a WORK EXPERIENCE bullet — meaning the
    only 'evidence' is a self-declared summary sentence or skills-row entry, not
    real job-tied work. A summary bullet ('Strong cloud platform experience across
    ... Microsoft Fabric ...') is the same self-claim as a skills row — neither
    proves the candidate did real work with it at an employer. These are
    structurally identical to a truly-missing skill for tier-audit purposes: the
    model still has to decide how to place them, and self-declaration is not
    enough basis for a production bullet. Feeding these into the same audit list
    that already catches wholly-missing skills closes the gap deterministically —
    no new AI call, reuses the existing tier-audit + correction machinery."""
    if not base_resume or not jd_skills:
        return []
    exp_blocks = _split_into_job_blocks(base_resume)
    # Evidence includes job HEADER lines, not just bullets — a term that's part
    # of the candidate's own role title ("Data Engineer") is real, stronger-than-
    # a-bullet proof of that work, not a self-declared claim. Restricting to
    # bullet lines only made every job's own title read as "no job evidence"
    # for its own role-name terms, since headers were excluded.
    evidence_blob = "\n".join(exp_blocks).lower()
    base_lo = base_resume.lower()
    out = []
    for sk in jd_skills:
        pattern = _dynamic_coverage_pattern(sk)
        in_base_anywhere = bool(re.search(pattern, base_lo))
        in_job_evidence  = bool(re.search(pattern, evidence_blob))
        if in_base_anywhere and not in_job_evidence:
            out.append(sk)
    return out


def _split_into_job_blocks(text: str) -> list[str]:
    """Split resume text into per-job blocks (job header line through the line
    before the next job header or next section header), in document order.
    Used to compare 'which job used which tool' between base and tailored text."""
    lines = text.split("\n")
    blocks: list[str] = []
    current: list[str] = []
    section: Optional[str] = None
    in_exp = False
    job_open = False  # only start collecting once the first job header is seen —
    # the blank line most resumes place between "WORK EXPERIENCE:" and the first
    # job header must never become its own (empty) block, which would shift
    # every later block's index and break base<->tailored job alignment.
    for line in lines:
        s = line.strip()
        if _is_section_header(s):
            if current:
                blocks.append("\n".join(current))
                current = []
            section = s.rstrip(":").upper()
            in_exp = "EXPERIENCE" in section
            job_open = False
            continue
        if in_exp and _is_job_header(s, section):
            if current:
                blocks.append("\n".join(current))
            current = [line]
            job_open = True
            continue
        if in_exp and job_open:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def detect_job_scope_leak(text: str, base_resume: str,
                          max_reports: int = 5) -> list[str]:
    """A tool the candidate genuinely used — but only at a DIFFERENT job than
    where the tailored resume now places it. Catches timeline/employer
    relocation fabrications (e.g., 'Medallion Architecture' real at Job A,
    invented into Job B's bullet where the candidate never worked with it).
    Jobs are matched by ORDER (SYSTEM_PROMPT requires job headers copied
    verbatim in the same sequence — JOB_HEADERS plan step enforces this).
    Fully derivational: ground truth is which base job-block contains the tool."""
    base_blocks = _split_into_job_blocks(base_resume)
    tail_blocks = _split_into_job_blocks(text)
    if not base_blocks or not tail_blocks:
        return []

    def _toks(block: str) -> set:
        found: set = set()
        for tok_re in _TOOL_TOKEN_RES:
            found |= set(tok_re.findall(block))
        return {t for t in found if t not in _DYN_ACRONYM_SKIP}

    base_tok_sets = [_toks(b) for b in base_blocks]
    all_base_toks: set = set().union(*base_tok_sets) if base_tok_sets else set()

    issues: list[str] = []
    seen: set = set()
    for i, tb in enumerate(tail_blocks):
        if i >= len(base_blocks):
            break  # extra job blocks are the job-hallucination guard's territory
        this_job_toks  = base_tok_sets[i]
        other_job_toks = all_base_toks - this_job_toks
        for tok in _toks(tb):
            key = tok.lower()
            if key in seen or tok in this_job_toks:
                continue
            if tok in other_job_toks:
                seen.add(key)
                if len(issues) < max_reports:
                    issues.append(
                        f"[JOB TOOL MISMATCH] '{tok}' appears at job #{i+1} in the tailored "
                        f"resume, but the original resume only shows it at a DIFFERENT job. "
                        f"Move it to the job where the candidate actually used it, or remove it."
                    )
    return issues


def detect_skill_scatter(text: str, missing_skills: list[str] | None,
                         max_reports: int = 3) -> list[str]:
    """A JD skill with ZERO real-work basis anywhere in the base resume
    (missing_skills — the same ground-truth list the tier audit uses) may get
    at most ONE job-block placement as a production/stretch bullet. Live bug:
    'MongoDB' had no job-tied evidence anywhere in the base resume, yet the
    tailored output placed it as a production claim at 3 different employers
    (a dedicated fabricated bullet at one job, appended to a real bullet at
    another, listed in Technologies Used at a third) — scattering a never-used
    skill across a candidate's whole career reads as systemic experience that
    never existed, which is worse than one contained, honest stretch bullet.
    Fully derivational: ground truth is the tier-audit missing-skills list
    already computed from the base resume before tailoring starts."""
    if not missing_skills:
        return []
    blocks = _split_into_job_blocks(text)
    if len(blocks) < 2:
        return []
    issues: list[str] = []
    for sk in missing_skills:
        pattern = _dynamic_coverage_pattern(sk)
        hit_jobs = [i for i, b in enumerate(blocks) if re.search(pattern, b, re.IGNORECASE)]
        if len(hit_jobs) > 1 and len(issues) < max_reports:
            issues.append(
                f"[SKILL SCATTER] '{sk}' has no real-work basis anywhere in the original "
                f"resume, but appears as a claim at {len(hit_jobs)} different jobs "
                f"(#{', #'.join(str(i + 1) for i in hit_jobs)}). A skill with no real "
                f"history gets AT MOST ONE stretch placement, at the single most relevant "
                f"job — remove it from all other jobs' bullets and Technologies Used lines."
            )
    return issues


_METRIC_SCALE_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\+?\s*[MB]\+?\b")
_METRIC_UPTIME_RE = re.compile(r"\b(?:9[5-9](?:\.\d+)?)\s?%")


def _distinctive_metrics(block: str) -> set[str]:
    found = set()
    for m in _METRIC_SCALE_RE.finditer(block):
        found.add(re.sub(r"[,\s]", "", m.group(0)).upper())
    for m in _METRIC_UPTIME_RE.finditer(block):
        found.add(re.sub(r"\s", "", m.group(0)))
    return found


def detect_cross_job_metric_theft(text: str, base_resume: str,
                                  max_reports: int = 5) -> list[str]:
    """A distinctive metric (M+/B+ scale volume, or a ≥95% uptime/SLA figure)
    that belongs to exactly ONE job in the base resume, reappearing verbatim
    at a DIFFERENT job in the tailored resume. Live bug: JPMorgan's real
    '500M+ daily transaction records' and '99.8% uptime' were copied onto a
    fabricated Cargill bullet claiming MongoDB production work — the exact
    number lifted from one employer's real achievement and relocated to
    another employer's invented one. Fully derivational: ground truth is
    which base-resume job block each distinctive number actually belongs to."""
    base_blocks = _split_into_job_blocks(base_resume)
    tail_blocks = _split_into_job_blocks(text)
    if len(base_blocks) < 2 or not tail_blocks:
        return []

    base_metric_sets = [_distinctive_metrics(b) for b in base_blocks]
    issues: list[str] = []
    seen: set[str] = set()
    for i, tb in enumerate(tail_blocks):
        if i >= len(base_blocks):
            break
        this_job_metrics = base_metric_sets[i] if i < len(base_metric_sets) else set()
        for metric in _distinctive_metrics(tb):
            if metric in this_job_metrics or metric in seen:
                continue
            owner = next(
                (j for j, ms in enumerate(base_metric_sets) if j != i and metric in ms),
                None,
            )
            if owner is not None:
                seen.add(metric)
                if len(issues) < max_reports:
                    issues.append(
                        f"[METRIC RELOCATION] '{metric}' belongs to job #{owner + 1} in "
                        f"the original resume, but appears at job #{i + 1} in the tailored "
                        f"resume — a real achievement's number was copied onto a different "
                        f"employer's claim. Remove it or replace with a number grounded in "
                        f"that job's actual original bullets."
                    )
    return issues


def detect_cover_letter_fabrication(cover_letter: str, resume: str, job_description: str = "",
                                    max_reports: int = 5) -> list[str]:
    """Cover letters get a single one-shot AI call with no verification loop —
    the same 'never fabricate' prompt-only instruction that let the resume
    pipeline invent MongoDB production work despite an identical rule. Checks:
      1. Distinctive metrics (M+/B+ scale, near-100% percentages) in the letter
         that appear nowhere in the resume — an invented number.
      2. Tech-shaped tokens (tool names) in the letter that exist in neither
         the resume nor the JD — an invented tool/technology claim.
    Fully derivational: ground truth is the resume + JD text, same pattern as
    the resume-side fabrication checks."""
    if not cover_letter or not resume:
        return []
    issues: list[str] = []

    cl_metrics  = _distinctive_metrics(cover_letter)
    res_metrics = _distinctive_metrics(resume)
    for m in sorted(cl_metrics - res_metrics):
        if len(issues) < max_reports:
            issues.append(
                f"[CL FABRICATED METRIC] '{m}' appears in the cover letter but not "
                f"anywhere in the resume — invented number. Remove it or replace with "
                f"a number that actually appears in the resume."
            )

    allowed = (resume + "\n" + (job_description or "")).lower()
    seen: set[str] = set()
    for tok_re in _TOOL_TOKEN_RES:
        for tok in tok_re.findall(cover_letter):
            key = tok.lower()
            if key in seen or tok in _DYN_ACRONYM_SKIP or key in allowed:
                continue
            seen.add(key)
            if len(issues) < max_reports:
                issues.append(
                    f"[CL FABRICATED TOOL] '{tok}' appears in the cover letter but exists "
                    f"in neither the resume nor the job description — invented. Remove it "
                    f"or replace with a tool the candidate actually used."
                )
    return issues


def detect_unsupported_bullets(text: str, base_resume: str,
                               job_description: str = "",
                               role_type: Optional[str] = None,
                               min_overlap: float = 0.35,
                               max_reports: int = 3) -> list[str]:
    """Bullet provenance: every tailored experience bullet must be grounded
    in the base resume — sharing distinctive content words with at least one
    base-resume line. A bullet with near-zero overlap is an invented claim
    (live run: 'multi-tenant federated analytics' bullet with no basis).
    Exemptions:
      - bullets containing a JD hard skill (gap-fill placements — tier audit
        owns their honesty, not provenance)
      - short bullets (<5 distinctive tokens — too little signal to judge)
    Fully derivational: the ground truth IS the base resume text."""
    if not base_resume:
        return []
    # Exempt only GAP-FILL skills — JD skills the base resume LACKS. Bullets
    # placed for those are intentionally new (tier audit owns their honesty).
    # A JD skill the base already has ('Data Architecture') exempts nothing:
    # bullets about it must still trace back to real base content.
    jd_patterns = []
    if job_description:
        for sk in extract_jd_hard_skills(job_description, role_type):
            try:
                pat = re.compile(_dynamic_coverage_pattern(sk), re.IGNORECASE)
            except re.error:
                continue
            if not pat.search(base_resume):
                jd_patterns.append(pat)

    def _content_toks(s: str) -> set:
        return set(re.findall(r"[a-z][a-z0-9\-+#.]{3,}", s.lower())) - _CLONE_STOPWORDS

    base_sets = [
        _content_toks(l) for l in base_resume.splitlines() if len(l.strip()) > 20
    ]
    base_sets = [b for b in base_sets if b]
    if not base_sets:
        return []

    issues: list[str] = []
    in_exp = False
    for raw in text.splitlines():
        line = raw.strip()
        if _is_section_header(line):
            in_exp = "EXPERIENCE" in line.upper()
            continue
        if not in_exp or not line.startswith("•"):
            continue
        body = line[1:].strip()
        toks = _content_toks(body)
        if len(toks) < 5:
            continue
        if any(p.search(body) for p in jd_patterns):
            continue  # gap-fill bullet — tier audit territory
        best = max(len(toks & bs) / len(toks) for bs in base_sets)
        if best < min_overlap and len(issues) < max_reports:
            issues.append(
                f"[UNSUPPORTED BULLET] no basis in the original resume "
                f"(best overlap {best:.0%}): \"{body[:70]}...\" — rewrite it "
                f"grounded in a real original-resume accomplishment, or delete it."
            )
    return issues


# Terms the JD extractor grabs that are never injectable/checkable skills.
# Filtered at EXTRACTION so lint visibility, skill-inject, and keyword-inject
# all stop chasing them (live runs chased "Computer Science", "M1", "Finance").
# Env override — no deploy needed: LINT_EXTRACTION_JUNK='["new junk","m2"]'
def _env_set(name: str) -> set:
    import os, json
    raw = os.getenv(name, "")
    try:
        return {str(x).lower() for x in json.loads(raw)} if raw else set()
    except Exception:
        return set()

_EXTRACTION_JUNK = {
    "computer science", "information systems", "information technology",
    "business analytics", "data analytics degree", "related field",
    "finance", "healthcare", "insurance", "banking", "retail",
    "data science",  # degree/team name in JDs, not an injectable skill; live run burned 2 retries chasing it
    "erp",  # platform category, not a skill; specific ERPs (SAP, NetSuite) pass
    # Employment / logistics / compensation terms — universal JD noise that a
    # resume can never "match", so counting them only deflates the ATS score.
    # (Live: "C2C", "PTO", "REMOTE", "Program" showed as missing keywords.)
    "c2c", "w2", "1099", "corp to corp", "corp-to-corp", "corp2corp",
    "full-time", "part-time", "fulltime", "parttime", "contract", "contractor",
    "permanent", "temporary", "temp", "freelance", "internship", "intern",
    "remote", "hybrid", "onsite", "on-site", "in-office", "wfh", "relocation",
    "visa", "sponsorship", "h1b", "h-1b", "opt", "cpt", "green card", "citizen",
    "citizenship", "clearance", "security clearance",
    "salary", "compensation", "equity", "benefits", "bonus", "incentive",
    "pension", "401k", "pto", "paid time off", "insurance benefits",
    "program", "opportunity", "position", "opening", "candidate", "applicant",
    "eoe", "equal opportunity", "disability", "veteran",
} | _env_set("LINT_EXTRACTION_JUNK")

# Skill-context patterns: real skills sit near tool-context words in the JD.
# Positive validation — generalizes past any hardcoded junk list.
_SKILL_CTX_RE = (
    r"(?:using|with|in|via|like|include\w*|experience|expertise|proficien\w+|"
    r"knowledge of|hands-on|skills? (?:in|with)|tools?(?: like| such as)?|"
    r"stack|platforms?|technolog\w+|familiarity with)"
)

def _has_skill_context(s: str, jd: str) -> bool:
    """True if the term appears near tool-context wording anywhere in the JD."""
    esc = re.escape(s.strip())
    pat = (rf"{_SKILL_CTX_RE}[^.\n]{{0,80}}\b{esc}\b"
           rf"|\b{esc}\b[^.\n]{{0,50}}(?:experience|skills?|proficiency|"
           rf"tooling|preferred|required|a plus|strong plus)")
    return bool(re.search(pat, jd, re.IGNORECASE))

# Degree/education phrasing that precedes a field-of-study list:
# "Bachelor's or master's degree in computer science, engineering, or related field".
# A term whose EVERY JD occurrence sits inside such a phrase is a field of study,
# not a skill — fully derivational, catches Statistics/Mathematics/any field name
# without ever growing _EXTRACTION_JUNK.
_DEGREE_IN_RE = re.compile(
    r"\b(?:bachelor|master|b\.?s\.?c?|m\.?s\.?c?|b\.?a\.?|m\.?a\.?|mba|ph\.?d"
    r"|doctorate|degree|diploma|major(?:ing)?|educat\w+|graduate[ds]?)\b"
    r"(?:['’]s)?[^.\n;:]{0,60}?\bin\b[^.\n;:]{0,80}$",
    re.IGNORECASE,
)

def _is_degree_only_term(s: str, jd: str) -> bool:
    """True if every occurrence of the term in the JD is inside a degree
    phrase ('degree in X, Y, or related field'). One occurrence outside
    degree context rescues it — a JD can want both a CS degree and CS skills."""
    esc = re.escape(s.strip())
    found_any = False
    for m in re.finditer(rf"\b{esc}\b", jd, re.IGNORECASE):
        found_any = True
        window = jd[max(0, m.start() - 160):m.start()]
        if not _DEGREE_IN_RE.search(window):
            return False
    return found_any


# Certification-title phrasing: "Certifications such as Microsoft Certified:
# Azure Database Administrator Associate or similar credentials are a plus".
# Long-form vendor credential NAMES get shredded by the TitleCase/list-context
# extraction steps into individual words ("Administrator", "Associate") that
# read as skills but are really just words inside a credential's title — the
# candidate can't honestly claim "Administrator" as a standalone skill.
# Same derivational shape as the degree filter: a term whose EVERY JD
# occurrence sits inside a certified/certification/credential window is
# fabrication bait, not a skill — any word ALSO used elsewhere is rescued
# (e.g. a JD naming "Administrator" both as a cert title word and as a real
# responsibility keyword stays a valid skill).
_CERT_TITLE_RE = re.compile(
    r"\b(?:certifications?|certificates?|credentials?|certified)\b[^.\n;]{0,150}$",
    re.IGNORECASE,
)

def _is_cert_title_only_term(s: str, jd: str) -> bool:
    """True if every occurrence of the term in the JD sits inside a
    certification/credential-title phrase — a shredded fragment of a
    credential NAME, not an independent skill."""
    esc = re.escape(s.strip())
    found_any = False
    for m in re.finditer(rf"\b{esc}\b", jd, re.IGNORECASE):
        found_any = True
        window = jd[max(0, m.start() - 160):m.start()]
        if not _CERT_TITLE_RE.search(window):
            return False
    return found_any

def _is_junk_skill(s: str, jd: str = "") -> bool:
    s_ = s.lower().strip()
    if s_ in _EXTRACTION_JUNK:
        return True
    if len(s_) <= 2:                     # "M1", "BI"-style fragments
        return s_ not in {"r", "go", "c", "c#", "f#"}
    if re.fullmatch(r"[a-z]\d", s_):     # M1-style stray tokens
        return True
    if jd and _is_degree_only_term(s_, jd):
        return True
    if jd and _is_cert_title_only_term(s_, jd):
        return True
    # Context gate: single generic English words with no tool-context in the
    # JD are extraction noise ("Ownership", "Disciplined"). Multi-word terms
    # and anything with digits/symbols skip this (clearly technical).
    if jd and s_.isalpha() and " " not in s_ and len(s_) >= 5:
        if not _has_skill_context(s_, jd):
            return True
    # Ticker/acronym gate: short ALL-CAPS tokens (RKT, NYSE, BIE, DML) are
    # extraction noise unless the JD uses them in tool context. Two checks:
    # a. Stock-ticker syntax anywhere in the JD ("NYSE: RKT", "(RKT)",
    # "NASDAQ: ABCD") — always junk, it's a listing reference.
    # b. 3-5 char ALL-CAPS acronym with NO skill-context wording near any
    # occurrence — junk. Real tool acronyms (SQL, AWS, ETL, OLAP, SAS)
    # appear next to "experience with / proficiency in / tools" phrasing
    # or inside requirement lists, which _has_skill_context matches.
    if jd and s_.isalpha() and " " not in s_ and s.strip().isupper() and 2 <= len(s_) <= 5:
        esc = re.escape(s.strip())
        # Derived acronyms (initials the extractor built, e.g. "GCP" from
        # "Google Cloud Platform") never appear literally in the JD — the
        # occurrence-based checks below can't judge them, so skip.
        if re.search(rf"\b{esc}\b", jd):
            if re.search(rf"(?:NYSE|NASDAQ|ticker)\s*[:\-]?\s*{esc}\b|\(\s*{esc}\s*\)", jd):
                return True
            if len(s_) <= 4 and not _has_skill_context(s_, jd):
                return True
    # Prose-word gate: a single-word term whose JD occurrences are MOSTLY
    # plain lowercase ("general ledger accounting", "search for homes",
    # "best deals") is ordinary English used in sentences — not a tool name.
    # Real tools keep their casing everywhere (Python, Tableau, Databricks).
    # Live bug: finance/product JDs produced "General", "Center", "Orders",
    # "Search", "Price", "Deals" as hard skills, and the injector then wrote
    # resume bullets around them. Fully derivational — the JD's own usage is
    # the evidence.
    if jd and s_.isalpha() and " " not in s_ and len(s_) >= 4:
        occs = re.findall(rf"\b{re.escape(s_)}\b", jd, re.IGNORECASE)
        lower_n = sum(1 for o in occs if o.islower())
        if lower_n > len(occs) - lower_n:   # strict lowercase majority
            return True
    return False


def extract_jd_hard_skills(job_description: str, role_type: Optional[str] = None) -> list[str]:
    """
    Hybrid: dynamic extraction (primary) with catalog fallback for thin JDs.
    Returns deduplicated list of hard skills visible in the JD.
    """
    if not job_description:
        return []
    skills = extract_jd_keywords_dynamic(job_description)
    skills = [s for s in skills if not _is_junk_skill(s, job_description)]
    if role_type:
        blocked: set[str] = set()
        for rt, terms in _DOMAIN_LOCKED_TERMS.items():
            if rt != role_type:
                blocked |= terms
        skills = [s for s in skills if s.lower() not in blocked]
    return skills


def _dynamic_coverage_pattern(skill: str) -> str:
    r"""
    Build a word-boundary regex pattern dynamically from the skill name.
    No catalog lookup — derived entirely from the extracted skill string.

    Rules:
      Single-word: exact word boundary.
        "Kafka" -> r'\bkafka\b', "ETL" -> r'\betl\b'

      Multi-word, last word is a gerund (ends in 'ing', len > 4):
        Strip 'ing' to get the stem, then match stem + any word chars.
        This catches noun/plural/gerund variants of the same root concept.
        "Data Modeling"    -> r'\bdata\s+model\w*\b'
           matches: "data modeling", "data models", "data model" ✓
        "Data Warehousing" -> r'\bdata\s+warehous\w*\b'
           matches: "data warehousing", "data warehouse", "data warehouses" ✓
        "Machine Learning" -> r'\bmachine\s+learn\w*\b'
           matches: "machine learning", "machine learned" ✓

      Multi-word, last word is not a gerund:
        Match last word + optional plural 's'.
        "Data Warehouse" -> r'\bdata\s+warehouses?\b'
        "AWS Certified"  -> r'\baws\s+certifieds?\b'
    """
    s = skill.lower().strip()
    L, R = r"(?<![a-z0-9])", r"(?![a-z0-9])"     # word edges that also work for "kdb+", "c#", ".net"
    # Slash/ampersand notation (ETL/ELT, CI/CD, ELT/ETL): match either ordering
    if re.match(r'^[a-z]+[/&][a-z]+$', s):
        a, sep, b = re.split(r'([/&])', s)
        escaped_sep = re.escape(sep)
        return rf"{L}({re.escape(a)}{escaped_sep}{re.escape(b)}|{re.escape(b)}{escaped_sep}{re.escape(a)}){R}"
    # a hyphenated label matches the spaced spelling too: "Infrastructure-as-Code"
    # is also written "infrastructure as code", "near-real-time" as "near real time"
    esc = lambda w: re.escape(w).replace(r"\-", r"[-\s]?")
    words = s.split()
    product = (skill.strip()[:1].isupper() and " " not in skill.strip())   # "Kubernetes", "AWS": exact
    if len(words) == 1:
        w = words[0]
        if product:
            return rf"{L}{esc(w)}{R}"
        # a competency word is tolerant of its own forms: "alerting" -> alerts/alerted,
        # "lakehouses" -> lakehouse (live: woven as "lakehouse", scored missing as "lakehouses")
        if w.endswith("ing") and len(w) > 4:
            return rf"{L}{esc(w[:-3])}\w*{R}"
        if w.endswith("s") and not w.endswith("ss") and len(w) > 4:
            return rf"{L}{esc(w[:-1])}s?{R}"
        return rf"{L}{esc(w)}s?{R}"
    interior = r"\s+".join(esc(w) for w in words[:-1])
    last = words[-1]
    if last.endswith("ing") and len(last) > 4:
        # Gerund: strip 'ing' to get stem, match stem + any word chars
        # "modeling" -> "model", "warehousing" -> "warehous", "learning" -> "learn"
        stem = esc(last[:-3])
        return rf"{L}{interior}\s+{stem}\w*{R}"
    if last.endswith("s") and not last.endswith("ss") and len(last) > 4:
        return rf"{L}{interior}\s+{esc(last[:-1])}s?{R}"
    return rf"{L}{interior}\s+{esc(last)}s?{R}"


def skill_coverage_report(
    resume_text: str,
    job_description: str,
    role_type: Optional[str] = None,
    profile_skills: Optional[list[str]] = None,
) -> dict:
    """
    Compare JD-visible hard skills against the final resume.
    Uses dynamic patterns derived from extracted skill names — no hardcoded catalog.
    """
    role = role_type or detect_role_type(job_description)
    jd_skills = extract_jd_hard_skills(job_description, role)
    if not jd_skills:
        return {
            "role_type": role,
            "jd_skills": [],
            "covered": [],
            "missing": [],
            "coverage_ratio": 1.0,
            "coverage_text": "0/0",
        }

    resume_blob = (resume_text or "").lower()
    if profile_skills:
        resume_blob += "\n" + ", ".join(profile_skills).lower()

    covered: list[str] = []
    missing: list[str] = []
    for skill in jd_skills:
        pattern = _dynamic_coverage_pattern(skill)
        if re.search(pattern, resume_blob):
            covered.append(skill)
        else:
            missing.append(skill)

    ratio = len(covered) / len(jd_skills) if jd_skills else 1.0
    return {
        "role_type": role,
        "jd_skills": jd_skills,
        "covered": covered,
        "missing": missing,
        "coverage_ratio": ratio,
        "coverage_text": f"{len(covered)}/{len(jd_skills)}",
    }


# ── Valid section headers per role type ───────────────────────────────────────
# Maps role type → set of uppercase header names (without trailing colon) that are VALID.
# Any other UPPERCASE: line triggers an "unexpected header" warning.
_VALID_HEADERS: dict[str, set[str]] = {
    TECH: {
        "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "TECHNICAL SKILLS", "EDUCATION",
        "CERTIFICATIONS", "PROJECTS", "PUBLICATIONS",
    },
    IB: {
        "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "TRANSACTION EXPERIENCE",
        "EDUCATION", "CERTIFICATIONS", "SKILLS",
    },
    FINANCE: {
        "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "CORE COMPETENCIES",
        "EDUCATION", "CERTIFICATIONS", "SKILLS",
    },
    CYBER: {
        "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "TECHNICAL SKILLS",
        "CERTIFICATIONS", "EDUCATION", "PROJECTS",
    },
    HEALTHCARE: {
        "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "SKILLS & EXPERTISE",
        "LICENSES & CERTIFICATIONS", "EDUCATION", "CLINICAL EXPERIENCE",
    },
    CONSULTING: {
        "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "CORE COMPETENCIES",
        "EDUCATION", "CERTIFICATIONS", "PUBLICATIONS",
    },
    GENERAL: {
        "PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "SKILLS",
        "EDUCATION", "CERTIFICATIONS", "PROJECTS", "CORE COMPETENCIES",
    },
}

# Required sections (subset that MUST be present)
_REQUIRED_HEADERS: dict[str, set[str]] = {
    TECH:       {"PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "TECHNICAL SKILLS", "EDUCATION"},
    IB:         {"PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION"},
    FINANCE:    {"PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION"},
    CYBER:      {"PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "CERTIFICATIONS", "EDUCATION"},
    HEALTHCARE: {"PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION"},
    CONSULTING: {"PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION"},
    GENERAL:    {"PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION"},
}

# ── Closing line rules per role type ──────────────────────────────────────────
# role_type → (required: bool, valid_prefixes: list[str], banned_prefixes: list[str])
# "required" means every job block MUST have a closing line.
_CLOSING_LINE_RULES: dict[str, tuple[bool, list[str], list[str]]] = {
    TECH: (
        True,
        ["technologies used:"],
        ["platform:", "platforms:", "stack:", "tech stack:", "tools:", "tools used:", "tech:", "technologies:"],
    ),
    IB: (
        False,   # optional; only deal-execution jobs need it
        ["selected transactions:"],
        [],
    ),
    FINANCE: (
        False,   # optional
        ["key tools:"],
        [],
    ),
    CYBER: (
        True,
        ["technologies & platforms:"],
        ["tools:", "platforms:", "stack:", "tech:"],
    ),
    HEALTHCARE: (
        False,   # only for health-informatics hybrids
        ["systems used:"],
        [],
    ),
    CONSULTING: (
        False,   # no closing line for consulting
        [],
        [],
    ),
    GENERAL: (
        False,
        [],
        [],
    ),
}

# ── Echo stoplists — words fine to repeat, never flagged ──────────────────────
_BASE_STOPLIST = {
    # Universal resume words
    "pipelines", "pipeline", "data", "across", "analytics", "reporting",
    "frameworks", "models", "datasets", "systems", "platform", "platforms",
    "engineering", "experience", "metrics", "governance", "quality",
    "building", "scalable", "operational", "business", "technical", "teams",
    "processes", "process", "results", "performance", "support", "strategy",
    "initiatives", "projects", "stakeholders", "requirements",
    # Generic role nouns/verbs — live runs showed echo whack-a-mole on these:
    # fixing "workflows/reports/queries" surfaced "analysis/dashboards" at 3x.
    # They're unavoidable vocabulary, not keyword stuffing.
    "management", "workflows", "workflow", "reports", "queries", "query",
    "solutions", "solution", "analysis", "dashboards", "dashboard",
    "analytical", "gather", "validation", "financial", "efficiency",
    "insights", "visualizations", "visualization", "compliance",
}

_ROLE_ECHO_STOPLIST: dict[str, set[str]] = {
    TECH: _BASE_STOPLIST | {
        "processing", "ingestion", "transformation", "warehouse", "storage",
        "compute", "cluster", "workload", "consumption", "extraction", "loading",
        "orchestration", "partitioning", "indexing", "replication", "streaming",
        "services", "service", "microservices", "application", "applications",
        "deployment", "architecture", "development", "software", "backend",
        "database", "interfaces", "modules", "servers", "endpoints", "runtime",
        "dependencies", "testing", "integration",
    },
    IB: _BASE_STOPLIST | {
        "transaction", "transactions", "financial", "capital", "market", "markets",
        "client", "clients", "management", "process", "materials", "analysis",
        "valuation", "deal", "deals", "advisory", "equity", "debt", "acquisition",
        "merger", "leverage", "investment", "banking", "execution", "diligence",
        "offering", "proceeds", "financing", "billion", "million",
    },
    FINANCE: _BASE_STOPLIST | {
        "financial", "revenue", "budget", "forecast", "management", "investment",
        "portfolio", "accounting", "transactions", "reconciliation", "variance",
        "quarter", "annual", "analysis", "planning", "statements", "reporting",
        "balance", "income", "cash", "model", "modeling", "gaap", "ifrs",
        "close", "journal", "entries", "accrual", "consolidation",
    },
    CYBER: _BASE_STOPLIST | {
        "security", "network", "access", "monitoring", "controls", "threats",
        "policies", "compliance", "incident", "vulnerabilities", "identity",
        "detection", "response", "firewall", "encryption", "alerts", "logging",
        "privileged", "exposure", "endpoint", "threat", "malware", "phishing",
        "investigation", "remediation", "hardening", "patching", "scanning",
    },
    HEALTHCARE: _BASE_STOPLIST | {
        "patient", "patients", "clinical", "care", "health", "medical",
        "nursing", "physician", "treatment", "outcomes", "documentation",
        "assessment", "diagnosis", "medication", "discharge", "admission",
        "records", "provider", "members", "eligibility", "claims",
    },
    CONSULTING: _BASE_STOPLIST | {
        "client", "clients", "engagement", "workstream", "analysis", "findings",
        "recommendations", "implementation", "deliverables", "framework",
        "methodology", "stakeholders", "leadership", "team", "approach",
        "solution", "solutions", "impact", "outcomes", "program",
    },
    GENERAL: _BASE_STOPLIST | {
        "customers", "customer", "sales", "revenue", "growth", "team",
        "management", "operations", "budget", "planning", "execution",
        "communication", "collaboration", "relationships", "initiatives",
    },
}

# ── Multi-idea verb detection ─────────────────────────────────────────────────
_MULTI_VERB_PATTERN = re.compile(
    r"\b("
    r"built|designed|developed|implemented|created|led|ran|"
    r"orchestrated|migrated|optimized|enforced|delivered|"
    r"containerized|architected|established|reduced|cut|"
    r"deployed|automated|refactored|integrated|shipped|tested|"
    r"configured|upgraded|resolved|debugged|released|maintained|"
    r"detected|remediated|patched|hardened|investigated|triaged|"
    r"responded|assessed|audited|modeled|forecasted|reconciled|"
    r"analyzed|reviewed|managed|tracked|calculated|projected|"
    r"visualized|queried|transformed|validated|monitored|"
    r"documented|presented|identified|executed|structured|"
    r"advised|coordinated|prepared|facilitated|recommended|"
    r"educated|assessed|administered|supported|contributed"
    r")\b",
    re.IGNORECASE,
)

_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_VERB1_RE = re.compile(r"^([A-Za-z]+)")


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _is_section_header(line: str) -> bool:
    # Colon-optional: the tailoring pipeline's own output always adds a
    # trailing colon, but a candidate's raw uploaded base resume often
    # doesn't (e.g. a PDF-extracted "WORK EXPERIENCE" with no ":"). Requiring
    # the colon silently broke job-block splitting on base resumes in that
    # format — every base-resume-side check that depends on it
    # (find_base_only_skills, detect_job_scope_leak, detect_cross_job_metric_theft)
    # went blind. An all-caps line >3 chars, not a bullet/tech-line, is enough.
    s = line.strip().rstrip(":")
    return (s == s.upper() and len(s) > 3
            and not s.startswith("•") and not s.startswith("Technologies")
            and not s.startswith("Selected") and not s.startswith("Key Tools")
            and not s.startswith("Systems") and not s.startswith("Technologies &"))


def _is_job_header(line: str, section: Optional[str]) -> bool:
    s = line.strip()
    if " @ " not in s:
        return False
    if s.startswith("•"):
        return False
    if any(d in s.lower() for d in DEGREE_SIGNALS):
        return False
    if section and "EDUC" in section:
        return False
    return True


def _is_closing_line(line: str, role_type: str) -> bool:
    s = line.strip().lower()
    _, valid_prefixes, _ = _CLOSING_LINE_RULES[role_type]
    return any(s.startswith(p) for p in valid_prefixes)


def _has_banned_closing_label(line: str, role_type: str) -> Optional[str]:
    s = line.strip().lower()
    _, _, banned = _CLOSING_LINE_RULES[role_type]
    for b in banned:
        if s.startswith(b):
            return line.strip()[:50]
    return None


def _extract_years_claim(text: str) -> Optional[str]:
    """Return the first 'X+ years' or 'X years' token found in the summary section."""
    in_summary = False
    for line in text.split("\n"):
        s = line.strip()
        if "PROFESSIONAL SUMMARY" in s.upper():
            in_summary = True
            continue
        if in_summary:
            if s and s == s.upper() and s.endswith(":") and len(s) > 3:
                break
            m = re.search(r'\b(\d+)\+?\s*year', s, re.IGNORECASE)
            if m:
                return m.group(0).strip()
    return None


def lint_resume(text: str, job_description: str = "", base_resume: str = "",
                 role_type: Optional[str] = None) -> list[str]:
    """
    Lint a tailored resume against the job description.
    Pass role_type explicitly when the caller already knows it (e.g. from the
    user's job preference) — auto-detecting from job_description text here
    can disagree with the role_type the resume was actually written against,
    causing every bullet-count/metric-density check to grade against the
    wrong role's budget. Falls back to JD-text auto-detection only if
    role_type is not supplied (standalone/CLI use).
    Pass base_resume to enable years-of-experience drift check.
    Returns list of issue strings. Empty = clean.
    """
    issues: list[str] = []
    lines = [l.rstrip() for l in text.strip().split("\n")]

    # ── Role type detection ──────────────────────────────────────────────────
    if role_type is None:
        role_type = detect_role_type(job_description) if job_description else GENERAL
    budget = BULLET_BUDGETS[role_type]
    minimums = BULLET_MINIMUMS.get(role_type, (0, 0, 0, 0))
    job_limits = [budget[0], budget[1], budget[2], budget[3]]  # per-job max
    echo_stoplist = _ROLE_ECHO_STOPLIST[role_type]
    closing_required, _, _ = _CLOSING_LINE_RULES[role_type]

    # ── Header integrity ─────────────────────────────────────────────────────
    header_blob = "\n".join(lines[:3])
    if not _PHONE_RE.search(header_blob):
        issues.append("[MISSING CONTACT] No phone number found in the first 3 lines.")
    if not _EMAIL_RE.search(header_blob):
        issues.append("[MISSING CONTACT] No email address found in the first 3 lines.")

    # ── Parse pass ───────────────────────────────────────────────────────────
    section:              Optional[str] = None
    summary_count:        int = 0
    summary_bullets:      list[str] = []               # body_lo of each summary bullet
    exp_bullets:          list[tuple[str, bool]] = []   # (body, has_metric)
    long_bullets:         list[tuple[int, str]] = []
    multi_idea_bullets:   list[tuple[int, str]] = []
    job_index:            int = -1
    current_job_header:   Optional[str] = None
    job_has_closing_line: bool = False
    jobs_missing_closing: list[str] = []
    prev_verb:            Optional[str] = None
    found_headers:        set[str] = set()
    per_job_bullets:      list[int] = []   # bullet count per job block
    current_job_bullets:  int = 0
    _job_open:            bool = False  # bullets attribute to a job only while open

    for raw in lines:
        line    = raw.strip()
        if not line:
            prev_verb = None
            continue

        # ── Banned closing labels ────────────────────────────────────────────
        banned_label = _has_banned_closing_label(line, role_type)
        if banned_label:
            _, valid_prefixes, _ = _CLOSING_LINE_RULES[role_type]
            expected = valid_prefixes[0].title() if valid_prefixes else "correct label"
            issues.append(
                f'[BANNED CLOSING LABEL] Use "{expected}" not "{banned_label}"'
            )

        # ── Section header ───────────────────────────────────────────────────
        if _is_section_header(line):
            if current_job_header and closing_required and not job_has_closing_line:
                jobs_missing_closing.append(current_job_header)
            # Close job counting — bullets in later sections (PROJECTS etc.)
            # must not be attributed to the last job block.
            if _job_open and job_index >= 0:
                per_job_bullets.append(current_job_bullets)
                current_job_bullets = 0
                _job_open = False
            current_job_header   = None
            job_has_closing_line = False
            prev_verb            = None
            section = line.rstrip(":").upper()
            found_headers.add(section)
            continue

        # ── Job header ───────────────────────────────────────────────────────
        if _is_job_header(line, section):
            if current_job_header and closing_required and not job_has_closing_line:
                jobs_missing_closing.append(current_job_header)
            # Save bullet count for the job we're leaving
            if _job_open and job_index >= 0:
                per_job_bullets.append(current_job_bullets)
            current_job_bullets  = 0
            _job_open            = True
            current_job_header   = line
            job_has_closing_line = False
            prev_verb            = None
            job_index           += 1
            if "|" not in line:
                issues.append(
                    f'[MISSING LOCATION] Job header missing "| City, State": "{line[:60]}"'
                )
            continue

        # ── Closing line ─────────────────────────────────────────────────────
        if _is_closing_line(line, role_type):
            job_has_closing_line = True
            prev_verb            = None
            continue

        # ── Bullet lines ─────────────────────────────────────────────────────
        if line.startswith("•"):
            body   = line[1:].strip()
            body_lo = body.lower()

            # Banned words + meta leaks (all sections)
            for w in BANNED_WORDS:
                if re.search(rf"\b{w}\b", body_lo):
                    # "leveraged" is a valid IB/finance product noun in specific phrases
                    if w == "leveraged" and re.search(
                        r"\bleveraged\s+(finance|buyout|loan|credit|lending|capital)\b", body_lo
                    ):
                        continue
                    issues.append(f'[BANNED WORD] "{w}" in: "{body[:60]}..."')
            for c in CORPORATE_CLICHES:
                if re.search(rf"\b{re.escape(c)}\b", body_lo):
                    # "synergy/synergies" and "value add/value-add" are real M&A/PE/real-estate
                    # terms in IB and finance roles, not filler — only flag outside that domain.
                    if c in ("synergy", "synergies", "value add", "value-add") and role_type in (IB, FINANCE):
                        continue
                    issues.append(f'[CORPORATE CLICHE] "{c}" in: "{body[:60]}..."')
            for m in META_LEAKS:
                if m in body_lo:
                    issues.append(f'[META LEAK] "{m}" in: "{body[:60]}..."')

            if section and "SUMMARY" in section:
                summary_count += 1
                summary_bullets.append(body_lo)
                prev_verb = None
                continue

            # Skills / competencies / certs sections — pass through
            skills_sections = {
                "TECHNICAL SKILLS", "CORE COMPETENCIES", "SKILLS & EXPERTISE",
                "SKILLS", "CERTIFICATIONS", "LICENSES & CERTIFICATIONS",
            }
            if section and any(s in section for s in skills_sections):
                prev_verb = None
                continue

            # Experience bullet
            has_metric = bool(re.search(r"(?<![A-Za-z])\d", body))  # S3/HL7/2.0-in-name are not metrics
            exp_bullets.append((body, has_metric))
            current_job_bullets += 1

            # Consecutive same-verb check
            vm = _VERB1_RE.match(body)
            if vm:
                verb = vm.group(1).lower()
                if prev_verb and verb == prev_verb:
                    issues.append(
                        f'[SAME VERB] Consecutive bullets both start with '
                        f'"{verb.capitalize()}": "{body[:55]}..."'
                    )
                prev_verb = verb
            else:
                prev_verb = None

            # Word count — same +3 grace as the deterministic trimmer: a
            # 26-28-word bullet reads fine, and flagging it would send it to
            # a retry that re-cuts what the trimmer deliberately spared.
            wc = _words(body)
            if wc > WORD_LIMIT + 3:
                long_bullets.append((wc, body))

            # Multi-idea check
            if wc > WORD_TARGET and " — " in body:
                if len(_MULTI_VERB_PATTERN.findall(body_lo)) >= 2:
                    multi_idea_bullets.append((wc, body))
            elif wc > WORD_TARGET and re.search(r"\band\b", body_lo):
                if len(_MULTI_VERB_PATTERN.findall(body_lo)) >= 3:
                    multi_idea_bullets.append((wc, body))
            continue

        prev_verb = None

    # Close last job
    if current_job_header and closing_required and not job_has_closing_line:
        jobs_missing_closing.append(current_job_header)
    # Save the last job's bullet count
    if _job_open and job_index >= 0:
        per_job_bullets.append(current_job_bullets)

    # ── Aggregate checks ──────────────────────────────────────────────────────

    # Required sections present?
    for req in _REQUIRED_HEADERS[role_type]:
        # Flexible match — check if any found header contains the required phrase
        if not any(req in h for h in found_headers):
            issues.append(
                f"[MISSING SECTION] Required section not found: "
                f'"{req}:" — add it or check for truncation.'
            )

    # Summary count
    if summary_count != SUMMARY_EXACT:
        direction = "Add more." if summary_count < SUMMARY_EXACT else "Trim."
        issues.append(
            f"[SUMMARY] {summary_count} bullets in summary (must be exactly {SUMMARY_EXACT}). {direction}"
        )

    # Per-job minimum bullet check — enforce fixed counts, not just maximums
    for ji, actual in enumerate(per_job_bullets):
        min_req = minimums[min(ji, len(minimums) - 1)]
        max_req = job_limits[min(ji, len(job_limits) - 1)]
        job_label = f"job #{ji+1}"
        if actual < min_req:
            issues.append(
                f"[TOO FEW BULLETS] {job_label} has {actual} bullets (need at least {min_req}). "
                f"Add {min_req - actual} more specific, metric-backed bullets."
            )
        elif actual > max_req:
            issues.append(
                f"[BULLET OVERFLOW] {job_label} has {actual} bullets (max {max_req}). "
                f"Cut {actual - max_req} lowest-relevance bullets."
            )

    # Unsupported experience claims in summary
    # Checks whether high-risk claim phrases in summary bullets are backed by
    # any work experience bullet. Fires as a lint issue -> triggers retry loop.
    if summary_bullets and exp_bullets:
        summary_text = " ".join(summary_bullets)
        work_text    = " ".join(body.lower() for body, _ in exp_bullets)
        for claim_re, evidence_res, label in _SUMMARY_RISK_CLAIMS:
            if re.search(claim_re, summary_text, re.IGNORECASE):
                has_evidence = any(
                    re.search(ev, work_text, re.IGNORECASE) for ev in evidence_res
                )
                if not has_evidence:
                    issues.append(
                        f'[UNSUPPORTED EXPERIENCE CLAIM] Summary claims "{label}" '
                        f"but no supporting work bullet found. "
                        f"Remove or rewrite the claim to match actual experience."
                    )

    # Years-of-experience drift check (only when base_resume provided)
    if base_resume:
        orig_years = _extract_years_claim(base_resume)
        out_years  = _extract_years_claim(text)
        if orig_years and out_years and orig_years.lower() != out_years.lower():
            issues.append(
                f'[YEARS MISMATCH] Summary claims "{out_years}" but original resume '
                f'states "{orig_years}". Use the exact number from the original.'
            )
        elif out_years and not orig_years:
            issues.append(
                f'[YEARS FABRICATED] Summary claims "{out_years}" but the original '
                f'resume contains no years-of-experience statement to support this. '
                f'Remove the years claim or rephrase without a specific number.'
            )

    # Bullet budget
    total_bullets = summary_count + len(exp_bullets)
    hard_total    = budget[5]  # index 5 = hard_total
    if total_bullets > hard_total:
        issues.append(
            f"[BULLET OVERFLOW] {total_bullets} total bullets "
            f"(max {hard_total} for {role_type} role). "
            f"Cut {total_bullets - hard_total} lowest-relevance bullets."
        )

    # Per-job bullet overflow (check using job_limits and job_index)
    # Note: we track this approximately via job_index — exact per-job counts
    # would require a second parse pass. Flag overflow at the hard total level
    # and let _enforce_limits handle per-job trimming.

    # Missing closing lines
    for jh in jobs_missing_closing:
        _, valid_prefixes, _ = _CLOSING_LINE_RULES[role_type]
        expected = valid_prefixes[0].title() if valid_prefixes else "closing line"
        issues.append(
            f'[MISSING CLOSING LINE] No "{expected}" after job: "{jh[:60]}". '
            f"Add it as the last line of that job's bullets."
        )

    # Long bullets
    for wc, body in long_bullets:
        issues.append(f'[TOO LONG] {wc} words (max {WORD_LIMIT}): "{body[:70]}..."')

    # Multi-idea bullets
    for wc, body in multi_idea_bullets:
        issues.append(
            f'[MULTI-IDEA] {wc} words, 2+ accomplishments — cut the weaker half: "{body[:70]}..."'
        )

    # Metrics density
    if exp_bullets:
        metric_count = sum(1 for _, hm in exp_bullets if hm)
        ratio = metric_count / len(exp_bullets)

        # Target ratio varies by role type. Flags sit outside the target band
        # so near-misses don't trigger a full retry.
        if role_type == HEALTHCARE:
            target_label, low_threshold = "30–50%", 0.25
        elif role_type == CONSULTING:
            target_label, low_threshold = "40–45%", 0.30
        else:
            target_label, low_threshold = "40–50%", 0.35
        high_threshold = 0.60

        if ratio < low_threshold:
            issues.append(
                f"[LOW METRICS] {ratio:.0%} of experience bullets have numbers "
                f"(target {target_label}). Add quantified outcomes."
            )
        elif ratio > high_threshold:
            issues.append(
                f"[HIGH METRICS] {ratio:.0%} of experience bullets have numbers "
                f"(target {target_label}). "
                f"Remove forced metrics from process/collaboration bullets."
            )

    # Metric narration — bullets must assert outcomes, not present evidence.
    # "reduced runtime 35%" is a resume line; "reduced runtime 35%, measured by
    # comparing job durations before and after tuning" is audit-speak that
    # bloats bullets to 40+ words and reads as AI-generated.
    _NARRATION_PHRASES = (
        "measured by", "tracked via", "calculated by", "confirmed by",
        "as reported by", "was measured", "was calculated", "was confirmed",
        "based on stakeholder", "per billing dashboard", "logged in",
        "before and after",
    )
    for body, _ in exp_bullets:
        low = body.lower()
        hit = next((p for p in _NARRATION_PHRASES if p in low), None)
        if hit:
            issues.append(
                f'[METRIC NARRATION] "{hit}" — bullets state outcomes, never the '
                f'measurement method. Delete the justification clause: "{body[:60]}..."'
            )

    # JD echo check — experience bullets + summary bullets (summary is the
    # highest-echo zone: models mirror JD responsibility verbs there first)
    if job_description:
        bullet_text = " ".join(body for body, _ in exp_bullets)
        bullet_text += " " + " ".join(summary_bullets)
        jd_lo       = job_description.lower()
        res_lo      = bullet_text.lower()
        jd_words    = set(re.findall(r"[a-z][a-z\-]{5,}", jd_lo))
        # Words that ARE skills must never be echo-flagged: a Python/SQL-heavy
        # JD wants those words repeated. Live run: echo-fix on "python"
        # mangled bullets into "in code and SQL". Harvest from (a) extracted
        # JD hard skills and (b) the resume's own skills section + closing
        # lines — (b) makes this robust when extraction returns thin results.
        _skill_words = set()
        for sk in extract_jd_hard_skills(job_description, role_type):
            _skill_words.update(sk.lower().split())
        # Role-title words are expected to repeat — a "Data Architect" JD
        # legitimately produces Architected/Architects bullets. Derivational:
        # harvest from the JD title line AND any TitleCase role phrase in the
        # JD head ("...seeking a skilled Data Architect to support...") —
        # covers JDs whose first line is boilerplate like "Position Summary".
        _skill_words.update(_extract_jd_title(job_description).lower().split())
        # Whole JD, not just the head — single-paragraph blob JDs bury the
        # role title mid-text ("...the Sr Data Architect is the owner...")
        for m in re.finditer(
            r"\b((?:[A-Z][a-z]+\s+){0,3}[A-Z][a-z]+)\b", job_description
        ):
            phrase = m.group(1)
            if _TITLE_ROLE_RE.search(phrase.split()[-1]):
                _skill_words.update(phrase.lower().split())
        _in_skills = False
        for raw_l in lines:
            s = raw_l.strip()
            if _is_section_header(s):
                _in_skills = any(k in s.upper() for k in
                                 ("SKILL", "COMPETENC", "EXPERTISE"))
                continue
            if _in_skills or _is_closing_line(s, role_type):
                for tok in re.findall(r"[a-z][a-z\-#+.]{2,}", s.lower()):
                    _skill_words.add(tok)
        # Stem-fold both sides so inflections count as the same word:
        # JD "evaluate and recommend" + resume "Evaluated... recommended..."
        # is the same echo. Suffix-strip then drop trailing 'e' — cheap
        # stemmer, no dictionary, generalizes to any JD.
        def _stem(w: str) -> str:
            for suf in ("ing", "ed", "es", "s"):
                if w.endswith(suf) and len(w) - len(suf) >= 4:
                    w = w[: -len(suf)]
                    break
            return w[:-1] if w.endswith("e") and len(w) > 4 else w

        from collections import Counter as _Counter
        res_stem_counts: dict = _Counter(
            _stem(t) for t in re.findall(r"[a-z][a-z\-]{4,}", res_lo)
        )
        _skill_stems    = {_stem(w) for w in _skill_words}
        _stoplist_stems = {_stem(w) for w in echo_stoplist}
        checked     = set()
        for w in jd_words:
            st = _stem(w)
            if st in checked or st in _skill_stems or st in _stoplist_stems:
                continue
            checked.add(st)
            count = res_stem_counts.get(st, 0)
            if count > 2:
                issues.append(
                    f'[JD ECHO] "{w}" (incl. variants) appears {count}x in resume bullets — '
                    f"a distinctive JD word repeated 3+ times reads as copied. "
                    f"Vary phrasing; keep ≤2 uses."
                )


    # JD artifact leaks (tags/codes/boilerplate) + verbatim clone runs.
    # Clone scan covers summary bullets too — verbatim JD phrases land there
    # most often ("...with Data Strategists, Data Analysts, and Solutions
    # Developers" cloned into a summary bullet in a live run).
    if job_description:
        issues += detect_jd_artifact_leak(text, job_description, base_resume)
        bullet_blob = (" ".join(body for body, _ in exp_bullets)
                       + " " + " ".join(summary_bullets))
        issues += detect_jd_clone_runs(bullet_blob, job_description, base_resume)

    # Tools named in bullets/tech-lines that exist in neither base resume nor JD
    if base_resume:
        issues += detect_fabricated_tools(text, base_resume, job_description)
        # Bullet provenance — invented claims with no basis in the original
        issues += detect_unsupported_bullets(text, base_resume, job_description, role_type)
        # Job-scoped tool relocation — real tool, wrong employer's timeline
        issues += detect_job_scope_leak(text, base_resume)

    # JD hard-skill VISIBILITY check — this is a presence/absence check only.
    # It can confirm a skill word appears SOMEWHERE on the resume (bullet, stretch
    # bullet, or skills/project section). It CANNOT distinguish a WORK-SUPPORTED
    # claim from a SELF-IMPLEMENTABLE skills-only mention — that distinction lives
    # in the prompt's tier rules and is not mechanically verified here.
    # Target is visibility (100%), not production-claim coverage (85-95%, prompt-side only).
    if job_description:
        coverage = skill_coverage_report(text, job_description, role_type=role_type)
        jd_skill_count  = len(coverage["jd_skills"])
        tailored_missing = set(coverage.get("missing", []))

        # ── Ratio-based check: overall visibility too low ─────────────────────
        if jd_skill_count >= 6 and coverage["coverage_ratio"] < 0.90:
            missing_preview = ", ".join(list(tailored_missing)[:6])
            issues.append(
                f"[LOW JD SKILL VISIBILITY] {coverage['coverage_text']} JD hard skills visible on resume "
                f"({coverage['coverage_ratio']:.0%}; target ~100% visibility). "
                f"For each missing skill below, add it via the appropriate tier — WORK-SUPPORTED bullet, "
                f"ADJACENT-STRETCH bullet, or SELF-IMPLEMENTABLE/HIGH-RISK skills-project wording. "
                f"Visibility through skills/project wording is acceptable; do not force production claims: "
                f"{missing_preview}."
            )

        # ── Profile-backed dropout check: skills present in base resume but ───
        # dropped from tailored output — zero tolerance regardless of ratio.
        if base_resume and tailored_missing:
            base_cov     = skill_coverage_report(base_resume, job_description, role_type=role_type)
            base_covered = set(base_cov.get("covered", []))
            dropped      = sorted(base_covered & tailored_missing)
            if dropped:
                issues.append(
                    f"[PROFILE SKILL DROPPED] {', '.join(dropped)} — these skills exist in the original "
                    f"resume but are absent from the tailored output. They are WORK-SUPPORTED (Case 1): "
                    f"add each back via a real job bullet + Technologies Used + Technical Skills. "
                    f"Do not use JD 'or' phrasing as justification to omit them."
                )

    return issues


# ── Retry rule messages (same interface as before) ────────────────────────────
RETRY_RULES: dict[str, str] = {
    "[MISSING CONTACT]":       "Line 2 must be 'phone | email' — add the contact line.",
    "[MISSING LOCATION]":      "Every job header must include '| City, State' after the company name.",
    "[MISSING CLOSING LINE]":  "Every job block must end with the correct closing line for this role type.",
    "[BANNED CLOSING LABEL]":  "Use the exact closing line label required for this role type.",
    "[BANNED WORD]":           "Replace 'utilized' and 'leveraged' with active verbs: 'used', 'built', 'ran'.",
    "[CORPORATE CLICHE]":     "Delete the empty filler phrase. Replace it with a specific, concrete detail from the actual accomplishment (a tool, a metric, a real outcome) instead of a generic claim.",
    "[META LEAK]":             "Remove all instruction text, placeholders, or commentary from the resume body.",
    "[TOO LONG]":              "Shorten to ≤22 words. One idea per bullet only. Split compound bullets.",
    "[MULTI-IDEA]":            "One accomplishment per bullet. CUT the weaker half — never split into two bullets (splitting overflows the bullet budget).",
    "[SAME VERB]":             "No two consecutive experience bullets may open with the same verb — vary them.",
    "[SUMMARY]":               "PROFESSIONAL SUMMARY must have exactly 5 bullet lines — not 4, not 6.",
    "[TOO FEW BULLETS]":       "A job block has fewer bullets than required. Add more specific, metric-backed bullets to reach the exact required count.",
    "[BULLET OVERFLOW]":       "Total bullets exceed the limit for this role type. Cut lowest-relevance bullets first.",
    "[MISSING SECTION]":       "A required section is missing. Check for output truncation and regenerate.",
    "[LOW METRICS]":           "Add quantified outcomes to more experience bullets (role-appropriate target).",
    "[HIGH METRICS]":          "Remove forced numbers from process/collaboration bullets — looks artificial.",
    "[JD ECHO]":               "A JD word repeated 3+ times reads as keyword stuffing. Vary phrasing.",
    "[JD ARTIFACT LEAK]":      "Delete this token everywhere — it is a recruiter tag or internal code scraped from the JD, not a real term.",
    "[JD BOILERPLATE TERM]":   "Remove this term — it comes from the JD's legal/benefits boilerplate, not its requirements.",
    "[JD CLONE]":              "Reword this bullet so no 6+ consecutive words match the JD. Keep the skills, change the sentence.",
    "[FABRICATED TOOL]":       "Replace the invented tool with one the candidate actually lists in the original resume, or delete the mention.",
    "[LOW JD SKILL VISIBILITY]": "Add 1–3 missing skills via the correct tier: WORK-SUPPORTED bullet, ADJACENT-STRETCH bullet (max 1/job, 2 total), or SELF-IMPLEMENTABLE/HIGH-RISK skills-project wording. Visibility-only placement is acceptable — never force a production claim.",
    "[UNSUPPORTED BULLET]":   "This bullet has no basis in the original resume. Rewrite it as a rephrasing of a REAL original-resume accomplishment, or delete it entirely. Never invent new accomplishments.",
    "[JOB TOOL MISMATCH]":    "Move the flagged tool to the job where the candidate actually used it (per the original resume), or delete it from this job entirely. Never let a real tool from one employer bleed into a different employer's bullets or Technologies Used line.",
    "[PROFILE SKILL DROPPED]":   "These skills exist in the candidate's original resume — they are WORK-SUPPORTED. Add each back: write a real bullet in the most relevant job, add to that job's Technologies Used, add to Technical Skills. Do not omit them because the JD listed them as 'or' alternatives.",
}


# ── Fragment detection ────────────────────────────────────────────────────────
# Deterministic "does this bullet read as cut off?" check. Shared by score_ats
# (quality surfacing) and the tailor's end-of-pipeline compression trigger —
# the post-loop scissor passes (trim / narration-strip / density-strip) can
# amputate mid-phrase, and nothing else inspects their output.

_FRAG_TRAILING = re.compile(
    r"\b(?:and|or|with|from|to|of|in|on|for|by|via|across|per|than|the|a|an|"
    r"using|into|at|as|but|while|which|that|w)[\.\s]*$", re.IGNORECASE)

# Common irregular past-tense resume verbs that don't end in 'ed'
_FRAG_IRREGULAR_VERBS = frozenset(
    "built led ran cut drove oversaw wrote set kept held met won made grew "
    "took chose brought taught sold found rebuilt reran co-led spearhead "
    "sped shrank rose".split())


def is_fragment_bullet(text: str, context: str = "") -> bool:
    """True when an experience bullet looks cut off / mutilated:
    ends in a preposition or connective, has no verb, has unbalanced
    parens/quotes, or is a sub-8-word stub.

    `context` (JD and/or base resume text) enables one extra vocabulary-
    grounded check: a bullet ending in a bare gerund ("…Kafka Connect
    ingesting") is a fragment UNLESS its final two-word phrase exists in the
    context — which keeps legitimate endings like "Spark Structured
    Streaming" or "demand forecasting" from false-positiving. Without
    context the gerund check is skipped (conservative)."""
    t = text.strip().lstrip("•").strip()
    if not t:
        return False
    words = t.rstrip(".").split()
    if len(words) < 8:
        return True
    if _FRAG_TRAILING.search(t.rstrip(".")):
        return True
    # Trailing bare gerund, vocabulary-grounded (live miss: "…and Kafka
    # Connect ingesting" — no comma, verb present, so nothing else fired).
    if context:
        last = words[-1].strip(",;:()").lower()
        if last.endswith("ing") and len(last) > 5:
            bigram = f"{words[-2].strip(',;:()').lower()} {last}"
            if bigram not in context.lower():
                return True
        # Trailing bare adjective (live miss: "...to Snowflake for analytics
        # and regulatory." — base had 'regulatory reporting', the noun got
        # cut, 'regulatory' alone isn't a preposition so _FRAG_TRAILING
        # never fired). Scoped tight to -ary/-ory only: broader adjective
        # suffixes like -ive (effective, comprehensive, collaborative) are
        # common, GRAMMATICAL predicate-adjective endings after a linking
        # verb ('...was accurate and comprehensive.') and false-positived
        # here during testing. Also skip entirely when a linking verb sits
        # in the last few words — that's exactly the predicate-adjective
        # shape this must not touch. Vocabulary-grounded like the gerund
        # check: only flags when the trailing bigram isn't already
        # established in context.
        elif re.search(r"(ary|ory)$", last) and len(last) > 6 and not (
            {"was", "were", "is", "are", "been", "being"} & {w.lower() for w in words[-5:-1]}
        ):
            bigram = f"{words[-2].strip(',;:()').lower()} {last}"
            if bigram not in context.lower():
                return True
    # Dangling digit-free participle tail: ", bringing MTTR" — a gerund
    # clause whose object got cut. A digit-bearing tail ("cutting runtime
    # 40%") is a completed outcome and passes.
    m = re.search(r",\s+\w+ing\b([^,;]*)$", t.rstrip("."))
    if m and not re.search(r"\d", m.group(0)) and len(m.group(1).split()) <= 2:
        return True
    if t.count("(") != t.count(")") or t.count('"') % 2 == 1:
        return True
    lower = {w.strip(",;:().").lower() for w in words}
    has_verb = any(w.endswith("ed") and len(w) > 3 for w in lower) or \
        bool(lower & _FRAG_IRREGULAR_VERBS)
    if not has_verb:
        return True
    # A semicolon joins two independent clauses — each needs its own verb.
    # 'Implemented X; the 45% drop in Y.' has a verb ('Implemented') in the
    # first clause, satisfying the whole-bullet check above, while the
    # second clause is a bare noun phrase with no verb of its own (live
    # miss: a trim/rewrite pass leaves a dangling appositive after ';').
    if ";" in t:
        for clause in t.rstrip(".").split(";")[1:]:
            cw = [w.strip(",;:().").lower() for w in clause.split()]
            c_words = {w for w in cw if w}
            if not c_words:
                continue
            # A gerund counts as this clause's verb ONLY when it's not the
            # object of a preposition. 'reducing costs by 40%' — gerund-led,
            # a real independent-clause shape → verb. 'in provisioning time'
            # — 'provisioning' follows 'in', so it's a gerund-as-noun, NOT a
            # verb (live miss: 'the 50% reduction in provisioning time' has
            # no verb but 'provisioning' faked one). Plural nouns
            # ('requests', 'reports') are likewise never treated as verbs.
            _PREP = {"in", "of", "for", "with", "to", "on", "at", "by", "from"}
            gerund_verb = any(
                w.endswith("ing") and len(w) > 4 and
                (idx == 0 or cw[idx - 1] not in _PREP)
                for idx, w in enumerate(cw) if w
            )
            c_has_verb = any(w.endswith("ed") and len(w) > 3 for w in c_words) or \
                bool(c_words & _FRAG_IRREGULAR_VERBS) or gerund_verb
            if not c_has_verb:
                return True
    return False


def find_fragment_bullets(resume_text: str, context: str = "") -> list[str]:
    """All experience-section bullets in the resume that read as fragments.
    Summary bullets are excluded — they are sentence fragments by design.
    Pass the JD (and/or base resume) as `context` to enable the trailing-
    gerund check — see is_fragment_bullet."""
    out: list[str] = []
    skip_section = False
    for line in (resume_text or "").split("\n"):
        s = line.strip()
        if s and s.rstrip(":").isupper() and len(s) < 60:
            # Summary and Skills bullets are not sentences — a skills row is
            # "Label: a, b, c" with no verb, so the truncation test always
            # false-positives on them. Only scan Experience/Projects bullets.
            up = s.upper()
            skip_section = ("SUMMARY" in up or "SKILL" in up or "TECHNICAL" in up
                            or "COMPETEN" in up or "CERTIF" in up)
            continue
        if skip_section or not s.startswith("•"):
            continue
        # Defensive: even outside a detected skills section, a "Label: comma,
        # list" line (no sentence, no trailing period) is a skills/tech row,
        # never a cut-off sentence — don't flag it.
        body = s.lstrip("• ").strip()
        if _is_label_list_row(body):
            continue
        if is_fragment_bullet(s, context):
            out.append(body)
    return out


def _is_label_list_row(text: str) -> bool:
    """True for a 'Short Label: item, item, item' skills/tech row — a list,
    not a sentence, so it must not be judged as a truncated bullet."""
    if ":" not in text:
        return False
    label, _, rest = text.partition(":")
    if len(label.split()) > 6:          # a real sentence clause, not a label
        return False
    rest = rest.strip().rstrip(".")
    # A list row: multiple comma-separated items and no mid-sentence verb cues.
    return rest.count(",") >= 1 and not re.search(r"\b(the|a|an|to|with|for)\b", rest.lower())


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 resume_lint_v2.py resume.txt [jd.txt]")
        sys.exit(1)

    resume_text = open(sys.argv[1]).read()
    jd_text     = open(sys.argv[2]).read() if len(sys.argv) > 2 else ""

    detected = detect_role_type(jd_text) if jd_text else GENERAL
    print(f"Detected role type: {detected}")

    found = lint_resume(resume_text, jd_text)
    if not found:
        print("✓ CLEAN — no issues.")
    else:
        print(f"✗ {len(found)} issue(s):\n")
        for f in found:
            print("  " + f)