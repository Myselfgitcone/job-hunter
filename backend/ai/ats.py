import re

ALL_KEYWORDS = [
    # ── Java ecosystem ────────────────────────────────────────────────────────
    # Core language / JVM
    "java", "jvm", "kotlin", "groovy", "scala",
    # Spring family
    "spring", "spring boot", "spring mvc", "spring data", "spring security",
    "spring cloud", "spring batch", "spring integration",
    # Build / dependency
    "maven", "gradle", "ant",
    # ORM / persistence
    "hibernate", "jpa", "jdbc", "mybatis",
    # Jakarta / J2EE
    "jakarta", "jakarta ee", "j2ee", "jee", "ejb", "jndi",
    # Web / API
    "rest", "rest api", "restful", "soap", "graphql", "grpc",
    "servlet", "jsp", "jax-rs", "jax-ws",
    # App servers
    "tomcat", "jetty", "wildfly", "jboss", "weblogic", "websphere",
    # Messaging
    "activemq", "rabbitmq", "ibm mq",
    # Testing
    "junit", "junit5", "mockito", "testng", "selenium", "cucumber",
    # Patterns / architecture
    "microservices", "monolith", "event-driven", "cqrs", "domain-driven",
    "design patterns", "solid", "tdd", "bdd",
    # Frameworks / libs
    "quarkus", "micronaut", "dropwizard", "jersey", "camel", "apache camel",
    "lombok", "jackson", "gson",
    # ── Core big data ─────────────────────────────────────────────────────────
    "pyspark", "spark", "hadoop", "hive", "kafka", "flink", "storm",
    "databricks", "delta lake", "iceberg", "hudi",
    # Data warehouse / lakehouse
    "snowflake", "redshift", "bigquery", "synapse", "teradata",
    "data warehouse", "data lake", "data lakehouse",
    # Cloud
    "aws", "azure", "gcp", "s3", "emr", "glue", "lambda", "kinesis",
    "adls", "adf", "azure data factory", "dataflow", "pub/sub",
    "ec2", "rds", "dynamodb", "cosmos db",
    # Languages (non-Java)
    "python", "sql", "bash", "go", "typescript", "javascript", "r",
    # ETL / orchestration
    "etl", "elt", "airflow", "luigi", "prefect", "dagster", "dbt",
    "informatica", "ab initio", "ssis", "talend", "fivetran", "airbyte",
    "oozie", "nifi",
    # Data formats
    "parquet", "avro", "orc", "json", "xml", "csv",
    # Streaming
    "streaming", "real-time", "real time", "kafka streams", "spark streaming",
    "kinesis streams",
    # DevOps / infra
    "docker", "kubernetes", "k8s", "jenkins", "ci/cd", "terraform",
    "helm", "gitlab", "ansible", "chef", "puppet",
    # Databases
    "postgres", "postgresql", "mysql", "oracle", "sql server", "mongodb",
    "cassandra", "elasticsearch", "redis", "couchbase",
    # Data concepts
    "data modeling", "star schema", "dimensional modeling", "data governance",
    "data quality", "data lineage", "metadata", "data catalog",
    "data mesh", "lakehouse", "medallion",
    # BI
    "tableau", "power bi", "looker", "quicksight", "qlik",
    # Version control
    "git", "github", "bitbucket",
    # Methodology
    "agile", "scrum", "kanban", "jira",
]


def _normalize(text: str) -> str:
    return text.lower()


def score_ats(resume_text: str, job_description: str) -> dict:
    """
    ATS keyword coverage using dynamic JD keyword extraction.
    Delegates to skill_coverage_report() so it stays in sync with
    the tailor pipeline — both use extract_jd_keywords_dynamic()
    instead of a static keyword catalog.
    """
    from resume_lint import skill_coverage_report, find_fragment_bullets
    cov = skill_coverage_report(resume_text, job_description)
    total   = len(cov["jd_skills"])
    matched = cov["covered"]
    missing = cov["missing"]
    score   = round(len(matched) / total * 100) if total else 0
    # Readability surfacing — kept SEPARATE from the score on purpose:
    # blending would let coverage regressions hide behind readability (and
    # vice versa). Score stays pure keyword coverage; fragments are a
    # parallel signal the UI warns about.
    try:
        fragments = find_fragment_bullets(resume_text)
    except Exception:
        fragments = []
    return {
        "score":   score,
        "matched": matched,
        "missing": missing,
        "total":   total,
        "quality": {"fragments": fragments, "count": len(fragments)},
    }
