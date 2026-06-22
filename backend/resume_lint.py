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
    TECH:       (11, 7, 5, 2, 5, 30),
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




# ── JD hard-skill extraction / coverage scoring ───────────────────────────────
# This is intentionally keyword-based. It does NOT prove real experience.
# It helps the tailoring layer identify whether the final resume covers enough
# recruiter-visible hard skills from the JD.
_ROLE_HARD_SKILLS: dict[str, dict[str, list[str]]] = {
    TECH: {
        # ── Languages ────────────────────────────────────────────────────────
        "Python":            [r"\bpython\b"],
        "SQL":               [r"\bsql\b", r"\bpl/sql\b", r"\bt-sql\b"],
        "Java":              [r"\bjava\b"],
        "Scala":             [r"\bscala\b"],
        "R":                 [r"\br\b", r"\br\s+programming\b"],
        "Shell Scripting":   [r"\bshell\s+script", r"\bbash\b"],
        # ── Distributed compute ──────────────────────────────────────────────
        "PySpark":           [r"\bpyspark\b"],
        "Spark":             [r"\bspark\b", r"\bapache\s+spark\b"],
        "Hadoop":            [r"\bhadoop\b", r"\bapache\s+hadoop\b"],
        "Hive":              [r"\bhive\b", r"\bapache\s+hive\b"],
        "HDFS":              [r"\bhdfs\b"],
        "Trino":             [r"\btrino\b", r"\bpresto\b"],
        "DuckDB":            [r"\bduckdb\b"],
        # ── Data architecture concepts ───────────────────────────────────────
        "ETL":               [r"\betl\b", r"\bextract.transform.load\b"],
        "ELT":               [r"\belt\b", r"\bextract.load.transform\b"],
        "Data Warehouse":    [r"\bdata\s+warehous", r"\bdwh\b", r"\bedw\b"],
        "Data Lake":         [r"\bdata\s+lake\b"],
        "Data Lakehouse":    [r"\blakehouse\b", r"\bdata\s+lakehouse\b"],
        "Data Pipeline":     [r"\bdata\s+pipeline", r"\bpipeline\b"],
        "Data Integration":  [r"\bdata\s+integration\b"],
        "Data Architecture": [r"\bdata\s+architect"],
        "Metadata Management": [r"\bmetadata\s+management\b", r"\bmetadata\b"],
        "Data Lineage":      [r"\bdata\s+lineage\b", r"\blineage\b"],
        "Data Catalog":      [r"\bdata\s+catalog\b"],
        "Middleware":        [r"\bmiddleware\b"],
        "Data Modeling":     [r"\bdata\s+model", r"\bdimensional\s+model", r"\bstar\s+schema\b", r"\bdata\s+vault\b"],
        "MDM":               [r"\bmdm\b", r"\bmaster\s+data\s+management\b"],
        "Medallion Architecture": [r"\bmedallion\b"],
        "Data Mesh":         [r"\bdata\s+mesh\b"],
        "Data Fabric":       [r"\bdata\s+fabric\b"],
        # ── Open table formats / file formats ────────────────────────────────
        "Delta Lake":        [r"\bdelta\s+lake\b", r"\bdelta\b"],
        "Apache Iceberg":    [r"\biceberg\b", r"\bapache\s+iceberg\b"],
        "Apache Hudi":       [r"\bhudi\b", r"\bapache\s+hudi\b"],
        "Parquet":           [r"\bparquet\b"],
        "Avro":              [r"\bavro\b"],
        "ORC":               [r"\borc\b"],
        # ── Cloud platforms ──────────────────────────────────────────────────
        "AWS":               [r"\baws\b", r"\bamazon\s+web\s+services\b"],
        "Azure":             [r"\bazure\b"],
        "GCP":               [r"\bgcp\b", r"\bgoogle\s+cloud\b"],
        # ── AWS services ─────────────────────────────────────────────────────
        "S3":                [r"\bs3\b"],
        "Glue":              [r"\bglue\b", r"\baws\s+glue\b"],
        "EMR":               [r"\bemr\b"],
        "Lambda":            [r"\blambda\b"],
        "Lake Formation":    [r"\blake\s+formation\b"],
        "Kinesis":           [r"\bkinesis\b", r"\baws\s+kinesis\b"],
        "DMS":               [r"\bdms\b", r"\bdatabase\s+migration\s+service\b"],
        "RDS":               [r"\brds\b", r"\brelational\s+database\s+service\b"],
        "MSK":               [r"\bmsk\b", r"\bmanaged\s+streaming\b"],
        "SageMaker":         [r"\bsagemaker\b", r"\baws\s+sagemaker\b"],
        "Athena":            [r"\bathena\b", r"\baws\s+athena\b"],
        "QuickSight":        [r"\bquicksight\b", r"\baws\s+quicksight\b"],
        "Redshift":          [r"\bredshift\b"],
        # ── Azure services ───────────────────────────────────────────────────
        "Synapse Analytics": [r"\bsynapse\b", r"\bazure\s+synapse\b"],
        "Azure DevOps":      [r"\bazure\s+devops\b"],
        "Azure Data Factory":[r"\bazure\s+data\s+factory\b", r"\badf\b"],
        "Event Hubs":        [r"\bevent\s+hubs\b"],
        "Stream Analytics":  [r"\bstream\s+analytics\b"],
        "Azure Key Vault":   [r"\bkey\s+vault\b", r"\bazure\s+key\s+vault\b"],
        "Azure Purview":     [r"\bpurview\b", r"\bazure\s+purview\b"],
        # ── GCP services ─────────────────────────────────────────────────────
        "BigQuery":          [r"\bbigquery\b"],
        "Pub/Sub":           [r"\bpub/sub\b", r"\bgcp\s+pub", r"\bgoogle\s+pub"],
        "Dataflow":          [r"\bdataflow\b", r"\bgoogle\s+dataflow\b"],
        "Vertex AI":         [r"\bvertex\s+ai\b"],
        "GCS":               [r"\bgcs\b", r"\bgoogle\s+cloud\s+storage\b"],
        "Cloud Composer":    [r"\bcloud\s+composer\b"],
        # ── Databases ────────────────────────────────────────────────────────
        "Databricks":        [r"\bdatabricks\b"],
        "Snowflake":         [r"\bsnowflake\b"],
        "PostgreSQL":        [r"\bpostgresql\b", r"\bpostgres\b"],
        "MySQL":             [r"\bmysql\b"],
        "Oracle":            [r"\boracle\b"],
        "SQL Server":        [r"\bsql\s+server\b", r"\bssms\b"],
        "DB2":               [r"\bdb2\b"],
        "NoSQL":             [r"\bnosql\b"],
        "Cassandra":         [r"\bcassandra\b"],
        "MongoDB":           [r"\bmongodb\b"],
        "Redis":             [r"\bredis\b"],
        "DynamoDB":          [r"\bdynamodb\b"],
        "Elasticsearch":     [r"\belasticsearch\b"],
        "CockroachDB":       [r"\bcockroachdb\b"],
        # ── Orchestration ────────────────────────────────────────────────────
        "Airflow":           [r"\bairflow\b", r"\bapache\s+airflow\b"],
        "Dagster":           [r"\bdagster\b"],
        "Prefect":           [r"\bprefect\b"],
        "Luigi":             [r"\bluigi\b"],
        "AWS Step Functions":[r"\bstep\s+functions\b"],
        "Databricks Workflows":[r"\bdatabricks\s+workflows\b"],
        # ── Transformation / ETL tools ───────────────────────────────────────
        "dbt":               [r"\bdbt\b"],
        "Informatica":       [r"\binformatica\b"],
        "Fivetran":          [r"\bfivetran\b"],
        "Airbyte":           [r"\bairbyte\b"],
        "SSIS":              [r"\bssis\b"],
        "Ab Initio":         [r"\bab\s+initio\b"],
        "Talend":            [r"\btalend\b"],
        "MuleSoft":          [r"\bmulesoft\b"],
        "Boomi":             [r"\bboomi\b"],
        # ── Streaming ────────────────────────────────────────────────────────
        "Kafka":             [r"\bkafka\b", r"\bapache\s+kafka\b"],
        "Flink":             [r"\bflink\b", r"\bapache\s+flink\b"],
        "Debezium":          [r"\bdebezium\b"],
        "Confluent":         [r"\bconfluent\b"],
        "Apache Pulsar":     [r"\bpulsar\b", r"\bapache\s+pulsar\b"],
        "Spark Streaming":   [r"\bspark\s+streaming\b", r"\bstructured\s+streaming\b"],
        # ── Data quality / observability ─────────────────────────────────────
        "Data Quality":      [r"\bdata\s+quality\b"],
        "Great Expectations":[r"\bgreat\s+expectations\b"],
        "Soda":              [r"\bsoda\b"],
        "Monte Carlo":       [r"\bmonte\s+carlo\b"],
        "Datafold":          [r"\bdatafold\b"],
        # ── Governance tools ─────────────────────────────────────────────────
        "Governance":        [r"\bgovernance\b"],
        "Collibra":          [r"\bcollibra\b"],
        "Apache Atlas":      [r"\bapache\s+atlas\b", r"\batlas\b"],
        "Unity Catalog":     [r"\bunity\s+catalog\b"],
        "Apache Ranger":     [r"\bapache\s+ranger\b", r"\branger\b"],
        # ── Compliance ───────────────────────────────────────────────────────
        "HIPAA":             [r"\bhipaa\b"],
        "GDPR":              [r"\bgdpr\b"],
        "SOC 2":             [r"\bsoc\s*2\b"],
        "RBAC":              [r"\brbac\b", r"\brole.based\s+access\b"],
        "PII":               [r"\bpii\b", r"\bpersonally\s+identifiable\b"],
        # ── BI / visualization ───────────────────────────────────────────────
        "Tableau":           [r"\btableau\b"],
        "Power BI":          [r"\bpower\s*bi\b"],
        "Looker":            [r"\blooker\b"],
        "Grafana":           [r"\bgrafana\b"],
        "Superset":          [r"\bsuperset\b", r"\bapache\s+superset\b"],
        # ── ML / AI adjacent ─────────────────────────────────────────────────
        "MLflow":            [r"\bmlflow\b"],
        "Feature Store":     [r"\bfeature\s+store\b"],
        "LangChain":         [r"\blangchain\b"],
        "Vector Database":   [r"\bvector\s+database\b", r"\bpinecone\b", r"\bweaviate\b"],
        # ── DevOps / infra ───────────────────────────────────────────────────
        "Terraform":         [r"\bterraform\b"],
        "Docker":            [r"\bdocker\b"],
        "Kubernetes":        [r"\bkubernetes\b", r"\bk8s\b"],
        "CI/CD":             [r"\bci/cd\b", r"\bjenkins\b"],
        "GitHub Actions":    [r"\bgithub\s+actions\b"],
        "GitLab":            [r"\bgitlab\b"],
        "Helm":              [r"\bhelm\b"],
        "ArgoCD":            [r"\bargocd\b", r"\bargo\s+cd\b"],
        "Pulumi":            [r"\bpulumi\b"],
        # ── Certifications ───────────────────────────────────────────────────
        "AWS Certified":     [r"\baws\s+certif", r"\bcertified\s+solutions\s+architect\b", r"\baws\s+saa\b", r"\baws\s+dea\b"],
        "GCP Certified":     [r"\bgcp\s+certif", r"\bgoogle\s+cloud\s+certif", r"\bprofessional\s+data\s+engineer\b"],
        "Azure Certified":   [r"\bazure\s+certif", r"\bdp-\d{3}\b", r"\baz-\d{3}\b"],
        "Databricks Certified": [r"\bdatabricks\s+certif"],
        "Snowflake Certified":  [r"\bsnowflake\s+certif"],
    },
    FINANCE: {
        "Excel":             [r"\bexcel\b"],
        "PowerPoint":        [r"\bpowerpoint\b"],
        "SQL":               [r"\bsql\b"],
        "Power BI":          [r"\bpower\s*bi\b"],
        "Tableau":           [r"\btableau\b"],
        "FP&A":              [r"\bfp&a\b", r"\bfinancial\s+planning\b"],
        "Forecasting":       [r"\bforecast"],
        "Budgeting":         [r"\bbudget"],
        "Variance Analysis": [r"\bvariance\s+analysis\b"],
        "Financial Modeling":[r"\bfinancial\s+model", r"\bthree[-\s]?statement\b", r"\b3[-\s]?statement\b"],
        "GAAP":              [r"\bgaap\b", r"\bus\s+gaap\b"],
        "IFRS":              [r"\bifrs\b"],
        "SOX":               [r"\bsox\b", r"\bsarbanes.oxley\b"],
        "DCF":               [r"\bdcf\b", r"\bdiscounted\s+cash\s+flow\b"],
        "LBO":               [r"\blbo\b"],
        "SAP":               [r"\bsap\b"],
        "Oracle":            [r"\boracle\b"],
        "Anaplan":           [r"\banaplan\b"],
        "Hyperion":          [r"\bhyperion\b"],
        "Adaptive Insights": [r"\badaptive\s+insights\b"],
        "NetSuite":          [r"\bnetsuite\b"],
        "Workday":           [r"\bworkday\b"],
        "QuickBooks":        [r"\bquickbooks\b"],
        "Concur":            [r"\bconcur\b"],
        "VBA":               [r"\bvba\b"],
        "Power Query":       [r"\bpower\s+query\b"],
    },
    IB: {
        "Excel":             [r"\bexcel\b"],
        "PowerPoint":        [r"\bpowerpoint\b"],
        "VBA":               [r"\bvba\b"],
        "DCF":               [r"\bdcf\b", r"\bdiscounted\s+cash\s+flow\b"],
        "LBO":               [r"\blbo\b", r"\bleveraged\s+buyout\b"],
        "Merger Model":      [r"\bmerger\s+model\b", r"\baccretion\b", r"\bdilution\b"],
        "M&A":               [r"\bm&a\b", r"\bmergers?\s+and\s+acquisitions?\b"],
        "Valuation":         [r"\bvaluation\b", r"\bcomparable\s+compan", r"\bprecedent\s+transaction"],
        "Capital Markets":   [r"\bcapital\s+markets\b", r"\becm\b", r"\bdcm\b"],
        "Pitch Books":       [r"\bpitch\s+book", r"\bpitchbook\b"],
        "Data Room":         [r"\bdata\s+room\b"],
        "Bloomberg":         [r"\bbloomberg\b"],
        "Capital IQ":        [r"\bcapital\s+iq\b", r"\bcapiq\b"],
        "FactSet":           [r"\bfactset\b"],
        "Refinitiv":         [r"\brefinitiv\b", r"\beikon\b"],
    },
    CYBER: {
        "SIEM":              [r"\bsiem\b"],
        "Splunk":            [r"\bsplunk\b"],
        "Microsoft Sentinel":[r"\bsentinel\b", r"\bmicrosoft\s+sentinel\b"],
        "QRadar":            [r"\bqradar\b"],
        "EDR":               [r"\bedr\b"],
        "CrowdStrike":       [r"\bcrowdstrike\b"],
        "Incident Response": [r"\bincident\s+response\b"],
        "Threat Hunting":    [r"\bthreat\s+hunting\b"],
        "Vulnerability Management": [r"\bvulnerability\s+management\b"],
        "Nessus":            [r"\bnessus\b"],
        "Qualys":            [r"\bqualys\b"],
        "Tenable":           [r"\btenable\b"],
        "IAM":               [r"\biam\b", r"\bidentity\s+and\s+access\b"],
        "Okta":              [r"\bokta\b"],
        "CyberArk":          [r"\bcyberark\b"],
        "Palo Alto":         [r"\bpalo\s+alto\b"],
        "Fortinet":          [r"\bfortinet\b"],
        "Cloud Security":    [r"\bcloud\s+security\b", r"\baws\s+security\b", r"\bazure\s+security\b"],
        "GRC":               [r"\bgrc\b", r"\brisk\s+compliance\b"],
        "NIST":              [r"\bnist\b"],
        "ISO 27001":         [r"\biso\s+27001\b"],
        "SOC 2":             [r"\bsoc\s*2\b"],
        "Zero Trust":        [r"\bzero\s+trust\b"],
        "MITRE ATT&CK":      [r"\bmitre\b", r"\batt&ck\b"],
        "Wireshark":         [r"\bwireshark\b"],
        "Metasploit":        [r"\bmetasploit\b"],
        "Burp Suite":        [r"\bburp\s+suite\b", r"\bburp\b"],
        "Python":            [r"\bpython\b"],
        "PowerShell":        [r"\bpowershell\b"],
        "KQL":               [r"\bkql\b"],
    },
    HEALTHCARE: {
        "Epic":              [r"\bepic\b"],
        "Cerner":            [r"\bcerner\b"],
        "EHR":               [r"\behr\b", r"\belectronic\s+health\s+record"],
        "EMR":               [r"\bemr\b", r"\belectronic\s+medical\b"],
        "HL7":               [r"\bhl7\b"],
        "FHIR":              [r"\bfhir\b"],
        "ICD-10":            [r"\bicd.10\b", r"\bicd\b"],
        "CPT Codes":         [r"\bcpt\b"],
        "HIPAA":             [r"\bhipaa\b"],
        "Medicare":          [r"\bmedicare\b"],
        "Medicaid":          [r"\bmedicaid\b"],
        "Clinical Documentation": [r"\bclinical\s+documentation\b"],
        "Care Coordination": [r"\bcare\s+coordination\b"],
        "Patient Care":      [r"\bpatient\s+care\b"],
        "Claims":            [r"\bclaims\b"],
        "SAS":               [r"\bsas\b"],
        "SQL":               [r"\bsql\b"],
        "Python":            [r"\bpython\b"],
        "Power BI":          [r"\bpower\s*bi\b"],
        "Snowflake":         [r"\bsnowflake\b"],
        "Redshift":          [r"\bredshift\b"],
    },
    CONSULTING: {
        "Excel":             [r"\bexcel\b"],
        "PowerPoint":        [r"\bpowerpoint\b"],
        "Tableau":           [r"\btableau\b"],
        "Power BI":          [r"\bpower\s*bi\b"],
        "Looker":            [r"\blooker\b"],
        "SQL":               [r"\bsql\b"],
        "Python":            [r"\bpython\b"],
        "R":                 [r"\br\b"],
        "Strategy":          [r"\bstrategy\b"],
        "Transformation":    [r"\btransformation\b"],
        "Process Improvement":[r"\bprocess\s+improvement\b"],
        "Change Management": [r"\bchange\s+management\b"],
        "Stakeholder Management":[r"\bstakeholder\s+management\b"],
        "Financial Modeling":[r"\bfinancial\s+model"],
        "Business Intelligence":[r"\bbusiness\s+intelligence\b", r"\bbi\b"],
        "Data Visualization":[r"\bdata\s+visual", r"\bvisuali"],
        "Six Sigma":         [r"\bsix\s+sigma\b", r"\bdmaic\b", r"\blean\b"],
        "Agile":             [r"\bagile\b", r"\bscrum\b", r"\bkanban\b"],
        "Confluence":        [r"\bconfluence\b"],
    },
    GENERAL: {
        "Excel":             [r"\bexcel\b"],
        "PowerPoint":        [r"\bpowerpoint\b"],
        "SQL":               [r"\bsql\b"],
        "Salesforce":        [r"\bsalesforce\b"],
        "Tableau":           [r"\btableau\b"],
        "Power BI":          [r"\bpower\s*bi\b"],
        "Jira":              [r"\bjira\b"],
        "ServiceNow":        [r"\bservicenow\b"],
        "CRM":               [r"\bcrm\b"],
        "Project Management":[r"\bproject\s+management\b"],
        "Agile":             [r"\bagile\b", r"\bscrum\b"],
        "Asana":             [r"\basana\b"],
        "Monday.com":        [r"\bmonday\.com\b", r"\bmonday\b"],
        "Slack":             [r"\bslack\b"],
        "Microsoft Office":  [r"\bmicrosoft\s+office\b", r"\bms\s+office\b"],
        "Google Workspace":  [r"\bgoogle\s+workspace\b", r"\bgoogle\s+docs\b"],
        "Zendesk":           [r"\bzendesk\b"],
        "HubSpot":           [r"\bhubspot\b"],
        "Workday":           [r"\bworkday\b"],
        "SharePoint":        [r"\bsharepoint\b"],
        "Power Automate":    [r"\bpower\s+automate\b"],
    },
}

# Skills universal enough to check across ALL role types.
_GLOBAL_HARD_SKILLS: dict[str, list[str]] = {
    "SQL":        [r"\bsql\b"],
    "Python":     [r"\bpython\b"],
    "Excel":      [r"\bexcel\b"],
    "Power BI":   [r"\bpower\s*bi\b"],
    "Tableau":    [r"\btableau\b"],
    "Salesforce": [r"\bsalesforce\b"],
    "SAP":        [r"\bsap\b"],
    "Oracle":     [r"\boracle\b"],
    "ServiceNow": [r"\bservicenow\b"],
    "Jira":       [r"\bjira\b"],
    "Java":       [r"\bjava\b"],
    "Scala":      [r"\bscala\b"],
    "Git":        [r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"],
    "Confluence": [r"\bconfluence\b"],
    "Agile":      [r"\bagile\b", r"\bscrum\b"],
}


def _skill_catalog_for_role(role_type: str) -> dict[str, list[str]]:
    catalog: dict[str, list[str]] = {}
    catalog.update(_GLOBAL_HARD_SKILLS)
    catalog.update(_ROLE_HARD_SKILLS.get(role_type, {}))
    return catalog


def extract_jd_hard_skills(job_description: str, role_type: Optional[str] = None) -> list[str]:
    """Return canonical hard skills explicitly visible in the JD."""
    if not job_description:
        return []
    role = role_type or detect_role_type(job_description)
    jd_low = job_description.lower()
    found: list[str] = []
    for skill, patterns in _skill_catalog_for_role(role).items():
        if any(re.search(p, jd_low) for p in patterns):
            found.append(skill)
    return found


def skill_coverage_report(
    resume_text: str,
    job_description: str,
    role_type: Optional[str] = None,
    profile_skills: Optional[list[str]] = None,
) -> dict:
    """
    Compare JD-visible hard skills against the final resume.
    This is an ATS/recruiter coverage heuristic, not a truth verifier.
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

    catalog = _skill_catalog_for_role(role)
    covered: list[str] = []
    missing: list[str] = []
    for skill in jd_skills:
        patterns = catalog.get(skill, [rf"\b{re.escape(skill.lower())}\b"])
        if any(re.search(p, resume_blob) for p in patterns):
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
        jd_skill_count = len(coverage["jd_skills"])
        if jd_skill_count >= 6 and coverage["coverage_ratio"] < 0.85:
            missing_preview = ", ".join(coverage["missing"][:6])
            issues.append(
                f"[LOW JD SKILL VISIBILITY] {coverage['coverage_text']} JD hard skills visible on resume "
                f"({coverage['coverage_ratio']:.0%}; target ~100% visibility). "
                f"For each missing skill below, add it via the appropriate tier — WORK-SUPPORTED bullet, "
                f"ADJACENT-STRETCH bullet, or SELF-IMPLEMENTABLE/HIGH-RISK skills-project wording. "
                f"Visibility through skills/project wording is acceptable; do not force production claims: {missing_preview}."
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
