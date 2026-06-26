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
from dataclasses import dataclass, field
from typing import Optional


# ── Role type constants ────────────────────────────────────────────────────────
TECH        = "TECH"
IB          = "IB"
FINANCE     = "FINANCE"
CYBER       = "CYBER"
HEALTHCARE  = "HEALTHCARE"
CONSULTING  = "CONSULTING"
GENERAL     = "GENERAL"


# ── Per-role bullet budgets ────────────────────────────────────────────────────
# (most_recent, second, third, fourth_plus, summary, hard_total)
BULLET_BUDGETS = {
    TECH:       (11, 7, 6, 2, 5, 31),
    IB:         ( 5, 4, 3, 2, 5, 19),
    FINANCE:    ( 5, 4, 3, 2, 5, 19),
    CYBER:      ( 7, 5, 4, 2, 5, 23),
    HEALTHCARE: ( 6, 4, 3, 2, 5, 20),
    CONSULTING: ( 6, 5, 3, 2, 5, 21),
    GENERAL:    ( 7, 5, 4, 2, 5, 23),
}

SUMMARY_EXACT = 5
WORD_LIMIT    = 22
WORD_TARGET   = 18

BANNED_WORDS = ["utilized", "leveraged"]

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
        (r"\bfp&a\b", 3), (r"\bfinancial planning\b", 2), (r"\bfinancial analyst\b", 2),
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
        (r"\bdata engineer", 2), (r"\bsoftware engineer", 2), (r"\bdevops\b", 2),
        (r"\bsre\b", 2), (r"\bplatform engineer", 2), (r"\bml engineer", 2),
        (r"\bdata (pipeline|platform|infrastructure|architecture)", 2),
        (r"\bkafka\b|\bspark\b|\bdatabricks\b|\bairflow\b|\bdbt\b", 2),
        (r"\bkubernetes\b|\bdocker\b|\bterraform\b", 2),
        (r"\bsnowflake\b|\bbigquery\b|\bredshift\b", 2),
        (r"\bpython\b|\bsql\b|\bjava\b|\bscala\b", 1),
        (r"\bcloud (infrastructure|platform|architecture)", 2),
        (r"\bci/cd\b|\bgithub actions\b|\bjenkins\b", 2),
    ],
}

# Everything else → GENERAL
_GENERAL_THRESHOLD = 2   # minimum score to NOT fall back to GENERAL


def detect_role_type(jd: str) -> str:
    """Auto-detect role type from JD text. Returns one of the role type constants."""
    jd_low = jd.lower()
    scores: dict[str, int] = {rt: 0 for rt in _ROLE_SIGNALS}

    for role_type, signals in _ROLE_SIGNALS.items():
        for pattern, weight in signals:
            if re.search(pattern, jd_low):
                scores[role_type] += weight

    best_role = max(scores, key=lambda r: scores[r])
    best_score = scores[best_role]

    # IB beats FINANCE when both score high (IB is more specific)
    if scores[IB] > 0 and scores[FINANCE] > 0 and scores[IB] >= scores[FINANCE]:
        return IB

    if best_score < _GENERAL_THRESHOLD:
        return GENERAL

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
#   run here. Steps 3-4 (TitleCase/CamelCase) are suppressed to avoid extracting
#   responsibility-sentence verbs ("Designs and develops", "Integrates, builds")
#   as if they were technical skills.
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
#   ALL-CAPS acronyms are valid (EHR, HL7, ETL appear in both duties and KSA)
#   TitleCase verbs and soft-skill adjectives are NOT extracted (Steps 3-4 suppressed)
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

def _strip_jd_noise(jd_text: str) -> str:
    """
    Remove benefits/culture/legal/physical sections from JD text before extraction.
    - Noise headers (benefits, EEO, company description) trigger skip=True
    - Content headers (requirements, responsibilities, opportunity) trigger skip=False
    - This lets the function handle JDs where requirements come AFTER company description
    - Individual physical/legal boilerplate lines are always dropped regardless
    """
    lines = jd_text.splitlines()
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
    return "\n".join(result)


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


def extract_jd_hard_skills(job_description: str, role_type: Optional[str] = None) -> list[str]:
    """
    Hybrid: dynamic extraction (primary) with catalog fallback for thin JDs.
    Returns deduplicated list of hard skills visible in the JD.
    """
    if not job_description:
        return []
    return extract_jd_keywords_dynamic(job_description)


def _dynamic_coverage_pattern(skill: str) -> str:
    """
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
    # Slash/ampersand notation (ETL/ELT, CI/CD, ELT/ETL): match either ordering
    if re.match(r'^[a-z]+[/&][a-z]+$', s):
        a, sep, b = re.split(r'([/&])', s)
        escaped_sep = re.escape(sep)
        return rf"\b({re.escape(a)}{escaped_sep}{re.escape(b)}|{re.escape(b)}{escaped_sep}{re.escape(a)})\b"
    words = s.split()
    if len(words) == 1:
        return rf"\b{re.escape(s)}\b"
    interior = r"\s+".join(re.escape(w) for w in words[:-1])
    last = words[-1]
    if last.endswith("ing") and len(last) > 4:
        # Gerund: strip 'ing' to get stem, match stem + any word chars
        # "modeling" -> "model", "warehousing" -> "warehous", "learning" -> "learn"
        stem = re.escape(last[:-3])
        return rf"\b{interior}\s+{stem}\w*\b"
    return rf"\b{interior}\s+{re.escape(last)}s?\b"


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
    s = line.strip()
    return (s == s.upper() and len(s) > 3 and s.endswith(":")
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


def lint_resume(text: str, job_description: str = "", base_resume: str = "") -> list[str]:
    """
    Lint a tailored resume against the job description.
    Auto-detects role type from job_description.
    Pass base_resume to enable years-of-experience drift check.
    Returns list of issue strings. Empty = clean.
    """
    issues: list[str] = []
    lines = [l.rstrip() for l in text.strip().split("\n")]

    # ── Role type detection ──────────────────────────────────────────────────
    role_type = detect_role_type(job_description) if job_description else GENERAL
    budget = BULLET_BUDGETS[role_type]
    job_limits = [budget[0], budget[1], budget[2], budget[3]]  # per-job limits
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

    for raw in lines:
        line    = raw.strip()
        line_lo = line.lower()
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
            has_metric = bool(re.search(r"\d", body))
            exp_bullets.append((body, has_metric))

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

            # Word count
            wc = _words(body)
            if wc > WORD_LIMIT:
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

    # ── Aggregate checks ──────────────────────────────────────────────────────

    # Required sections present?
    text_upper = text.upper()
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
            f'[MULTI-IDEA] {wc} words, 2+ accomplishments — split or cut: "{body[:70]}..."'
        )

    # Metrics density
    if exp_bullets:
        metric_count = sum(1 for _, hm in exp_bullets if hm)
        ratio = metric_count / len(exp_bullets)

        # Target ratio varies by role type
        low_threshold  = 0.40 if role_type in (HEALTHCARE, CONSULTING) else 0.55
        high_threshold = 0.85

        if ratio < low_threshold:
            issues.append(
                f"[LOW METRICS] {ratio:.0%} of experience bullets have numbers "
                f"(target {'40–60%' if role_type in (HEALTHCARE, CONSULTING) else '60–70%'}). "
                f"Add quantified outcomes."
            )
        elif ratio > high_threshold:
            issues.append(
                f"[HIGH METRICS] {ratio:.0%} of experience bullets have numbers "
                f"(target {'40–60%' if role_type in (HEALTHCARE, CONSULTING) else '60–70%'}). "
                f"Remove forced metrics from process/collaboration bullets."
            )

    # JD echo check — on experience bullet text only
    if job_description:
        bullet_text = " ".join(body for body, _ in exp_bullets)
        jd_lo       = job_description.lower()
        res_lo      = bullet_text.lower()
        jd_words    = set(re.findall(r"[a-z][a-z\-]{5,}", jd_lo))
        checked     = set()
        for w in jd_words:
            if w in echo_stoplist or w in checked:
                continue
            checked.add(w)
            count = len(re.findall(rf"\b{re.escape(w)}\b", res_lo))
            if count > 2:
                issues.append(
                    f'[JD ECHO] "{w}" appears {count}x in resume bullets — '
                    f"a distinctive JD word repeated 3+ times reads as copied. "
                    f"Vary phrasing; keep ≤2 uses."
                )


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
    "[META LEAK]":             "Remove all instruction text, placeholders, or commentary from the resume body.",
    "[TOO LONG]":              "Shorten to ≤22 words. One idea per bullet only. Split compound bullets.",
    "[MULTI-IDEA]":            "One accomplishment per bullet. Split into two or cut the weaker half.",
    "[SAME VERB]":             "No two consecutive experience bullets may open with the same verb — vary them.",
    "[SUMMARY]":               "PROFESSIONAL SUMMARY must have exactly 5 bullet lines — not 4, not 6.",
    "[BULLET OVERFLOW]":       "Total bullets exceed the limit for this role type. Cut lowest-relevance bullets first.",
    "[MISSING SECTION]":       "A required section is missing. Check for output truncation and regenerate.",
    "[LOW METRICS]":           "Add quantified outcomes to more experience bullets (role-appropriate target).",
    "[HIGH METRICS]":          "Remove forced numbers from process/collaboration bullets — looks artificial.",
    "[JD ECHO]":               "A JD word repeated 3+ times reads as keyword stuffing. Vary phrasing.",
    "[LOW JD SKILL VISIBILITY]": "Add 1–3 missing skills via the correct tier: WORK-SUPPORTED bullet, ADJACENT-STRETCH bullet (max 1/job, 2 total), or SELF-IMPLEMENTABLE/HIGH-RISK skills-project wording. Visibility-only placement is acceptable — never force a production claim.",
    "[PROFILE SKILL DROPPED]":   "These skills exist in the candidate's original resume — they are WORK-SUPPORTED. Add each back: write a real bullet in the most relevant job, add to that job's Technologies Used, add to Technical Skills. Do not omit them because the JD listed them as 'or' alternatives.",
}


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
