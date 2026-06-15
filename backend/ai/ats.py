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
    jd_lower = _normalize(job_description)
    resume_lower = _normalize(resume_text)

    # Extract keywords that appear in JD
    jd_keywords = [kw for kw in ALL_KEYWORDS if kw in jd_lower]

    # Deduplicate (preserve order)
    all_jd_keywords = list(dict.fromkeys(jd_keywords))
    if not all_jd_keywords:
        return {"score": 0, "matched": [], "missing": [], "total": 0}

    matched = [kw for kw in all_jd_keywords if kw in resume_lower]
    missing = [kw for kw in all_jd_keywords if kw not in resume_lower]

    score = round(len(matched) / len(all_jd_keywords) * 100)

    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "total": len(all_jd_keywords),
    }
