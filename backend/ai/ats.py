import re

DATA_ENGINEERING_KEYWORDS = [
    # Core big data
    "pyspark", "spark", "hadoop", "hive", "kafka", "flink", "storm",
    "databricks", "delta lake", "iceberg", "hudi",
    # Data warehouse / lakehouse
    "snowflake", "redshift", "bigquery", "synapse", "teradata",
    "data warehouse", "data lake", "data lakehouse",
    # Cloud
    "aws", "azure", "gcp", "s3", "emr", "glue", "lambda", "kinesis",
    "adls", "adf", "azure data factory", "dataflow", "pub/sub",
    "ec2", "rds", "dynamodb", "cosmos db",
    # Languages
    "python", "sql", "scala", "java", "bash",
    # ETL / orchestration
    "etl", "elt", "airflow", "luigi", "prefect", "dagster", "dbt",
    "informatica", "ab initio", "ssis", "talend", "fivetran", "airbyte",
    "oozie", "nifi",
    # Data formats
    "parquet", "avro", "orc", "json", "xml", "csv",
    # Streaming
    "streaming", "real-time", "real time", "kafka streams", "spark streaming",
    "kinesis streams",
    # DevOps
    "docker", "kubernetes", "k8s", "jenkins", "ci/cd", "terraform",
    "helm", "airflow", "gitlab",
    # Databases
    "postgres", "postgresql", "mysql", "oracle", "sql server", "mongodb",
    "cassandra", "elasticsearch",
    # Concepts
    "data modeling", "star schema", "dimensional modeling", "data governance",
    "data quality", "data lineage", "metadata", "data catalog",
    "data mesh", "lakehouse", "medallion",
    # BI
    "tableau", "power bi", "looker", "quicksight",
    # Version control
    "git", "github",
]


def _normalize(text: str) -> str:
    return text.lower()


def score_ats(resume_text: str, job_description: str) -> dict:
    jd_lower = _normalize(job_description)
    resume_lower = _normalize(resume_text)

    # Extract keywords that appear in JD
    jd_keywords = [kw for kw in DATA_ENGINEERING_KEYWORDS if kw in jd_lower]

    # Also extract any multi-word tech terms from JD not in our list
    extra = re.findall(r"\b(?:[a-z]+(?:\s[a-z]+)?)\b", jd_lower)

    # Deduplicate
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
