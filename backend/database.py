from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, text, BigInteger
from datetime import datetime
import json

import os
import ssl

_raw_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./jobs.db")

# Railway gives postgres:// — SQLAlchemy needs postgresql+asyncpg://
if _raw_url.startswith("postgres://"):
    DATABASE_URL = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("postgresql://") and "+asyncpg" not in _raw_url:
    DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_url

_is_postgres = DATABASE_URL.startswith("postgresql")

# PostgreSQL on Railway external URL requires SSL; SQLite needs check_same_thread=False
if _is_postgres:
    _connect_args = {"ssl": "require"}
else:
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    pool_pre_ping=True,   # verify connections before use
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)




class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, default="")
    country = Column(String, default="")
    url = Column(String, unique=True, nullable=False)
    source = Column(String, default="")
    description = Column(Text, default="")
    salary = Column(String, default="")
    remote = Column(Boolean, default=False)
    posted_at = Column(String, default="")
    scraped_at = Column(String, default="")
    hc_original_date = Column(String, default="")  # HC estimated_publish_date (raw, unfiltered)
    status = Column(String, default="new")  # new / applied / skipped / interview / closed
    fj_id = Column(BigInteger, default=None)   # Fantastic.jobs internal ID

    # ── FJ enrichment fields ──────────────────────────────────────────────────
    visa_sponsorship  = Column(Boolean, default=None)   # ai_visa_sponsorship
    experience_level  = Column(String,  default="")     # "0-2","2-5","5-10","10+"
    employment_type   = Column(String,  default="")     # "Full-time","Contract", etc.
    benefits          = Column(Text,    default="")     # JSON list of benefit strings
    job_expiry        = Column(String,  default="")     # date_valid_through (ISO)
    logo_url          = Column(String,  default="")     # org_logo_permalink (S3)
    company_size      = Column(String,  default="")     # org_linkedin_size
    company_industry  = Column(String,  default="")     # org_linkedin_industry
    company_hq        = Column(String,  default="")     # org_linkedin_headquarters
    company_funding   = Column(BigInteger, default=None)# org_crunchbase_total_investment
    ai_keywords       = Column(Text,    default="")     # JSON list for ATS matching

    tailored_resume = Column(Text, default=None)
    tailored_at = Column(String, default=None)
    applied_at = Column(String, default=None)
    ats_score_before = Column(Integer, default=None)
    ats_score_after = Column(Integer, default=None)
    ats_keywords_matched = Column(Text, default=None)   # JSON list
    ats_keywords_missing = Column(Text, default=None)   # JSON list
    fit_analysis = Column(Text, default=None)
    interview_tips = Column(Text, default=None)          # JSON list
    cover_letter = Column(Text, default=None)
    notes = Column(Text, default="")
    deadline = Column(String, default=None)              # ISO date string
    interview_date = Column(String, default=None)        # ISO datetime string
    priority = Column(Integer, default=0)                # 0=normal, 1=high, 2=urgent
    qualify_result = Column(Text, default=None)          # JSON qualification analysis


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text, default="")


class User(Base):
    __tablename__ = "users"
    id            = Column(String, primary_key=True)
    email         = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name          = Column(String, default="")
    created_at    = Column(String, default="")
    last_seen_at  = Column(String, default="")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id         = Column(String, primary_key=True)
    user_id    = Column(String, nullable=False)
    token      = Column(String, unique=True, nullable=False)
    expires_at = Column(String, nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(String, default="")


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id              = Column(String, primary_key=True)  # references users.id
    resume               = Column(Text, default="")
    job_roles            = Column(Text, default='["Data Engineer"]')   # JSON array
    countries            = Column(Text, default='["USA", "Remote"]')   # JSON array
    visa_filter          = Column(Boolean, default=False)   # True = hide no-sponsorship
    level_filter         = Column(Boolean, default=False)   # True = hide overqualified
    ai_provider          = Column(String, default="openrouter")
    ai_api_key           = Column(String, default="")
    ai_model_parse       = Column(String, default="")
    ai_model_tailor      = Column(String, default="")
    ai_model_qualify     = Column(String, default="")
    ai_model_cover_letter= Column(String, default="")
    profile_name         = Column(String, default="")
    profile_visa         = Column(String, default="")  # display: "F1/OPT", "H1B", "Citizen"
    # Profile fields for auto-apply
    profile_phone        = Column(String, default="")
    profile_address      = Column(String, default="")
    profile_linkedin     = Column(String, default="")
    profile_github       = Column(String, default="")
    profile_website      = Column(String, default="")
    profile_summary      = Column(Text, default="")
    # Telegram bot
    telegram_bot_token   = Column(String, default="")
    telegram_chat_id     = Column(String, default="")


class UserJob(Base):
    __tablename__ = "user_jobs"
    id                   = Column(String, primary_key=True)
    user_id              = Column(String, nullable=False)   # references users.id
    job_id               = Column(String, nullable=False)   # references jobs.id
    status               = Column(String, default="new")    # new/applied/skipped/interview
    tailored_resume      = Column(Text, default=None)
    cover_letter         = Column(Text, default=None)
    ats_score_before     = Column(Integer, default=None)
    ats_score_after      = Column(Integer, default=None)
    ats_keywords_matched = Column(Text, default=None)
    ats_keywords_missing = Column(Text, default=None)
    fit_analysis         = Column(Text, default=None)
    interview_tips       = Column(Text, default=None)
    notes                = Column(Text, default="")
    deadline             = Column(String, default=None)
    interview_date       = Column(String, default=None)
    priority             = Column(Integer, default=0)
    qualify_result       = Column(Text, default=None)
    applied_at           = Column(String, default=None)
    tailored_at          = Column(String, default=None)
    saved_at             = Column(String, default="")


class Company(Base):
    __tablename__ = "companies"
    id          = Column(String, primary_key=True)
    name        = Column(String, nullable=False)
    ats         = Column(String, nullable=False)   # greenhouse/lever/ashby/workday
    slug        = Column(String, nullable=False)
    careers_url = Column(String, default="")
    active      = Column(Boolean, default=True)
    added_at    = Column(String, default="")
    source      = Column(String, default="jseek_csv")  # jseek_csv/manual


async def init_db():
    # 1. Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # 2. Migrations - jobs table columns
    # We run these in separate transactions because Postgres will abort the entire
    # transaction if an ALTER TABLE fails (e.g., if the column already exists).
    migrations = [
        "ALTER TABLE jobs ADD COLUMN country TEXT",
        "ALTER TABLE jobs ADD COLUMN cover_letter TEXT",
        "ALTER TABLE jobs ADD COLUMN notes TEXT",
        "ALTER TABLE jobs ADD COLUMN tailored_at TEXT",
        "ALTER TABLE jobs ADD COLUMN fj_id BIGINT",
        "ALTER TABLE jobs ADD COLUMN applied_at TEXT",
        "ALTER TABLE jobs ADD COLUMN deadline TEXT",
        "ALTER TABLE jobs ADD COLUMN interview_date TEXT",
        "ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN qualify_result TEXT",
        "ALTER TABLE jobs ADD COLUMN hc_original_date TEXT DEFAULT ''",
        # FJ enrichment
        "ALTER TABLE jobs ADD COLUMN visa_sponsorship BOOLEAN",
        "ALTER TABLE jobs ADD COLUMN experience_level TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN employment_type TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN benefits TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN job_expiry TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN logo_url TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN company_size TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN company_industry TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN company_hq TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN company_funding BIGINT",
        "ALTER TABLE jobs ADD COLUMN ai_keywords TEXT DEFAULT ''",
    ]
    for stmt in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception:
            pass  # column already exists or other error

    # Backfill country for existing jobs that have empty country
    await _backfill_country()


async def _backfill_country():
    """Detect + fill country from location for all jobs with missing country."""
    from scrapers.base import detect_country
    from sqlalchemy import select, update

    async with SessionLocal() as session:
        result = await session.execute(
            select(Job).where((Job.country == None) | (Job.country == ""))
        )
        jobs = result.scalars().all()
        updated = 0
        for job in jobs:
            loc    = job.location or ""
            source = job.source   or ""
            # Source-based defaults
            if source == "Arbeitnow":
                default = "Germany"
            elif source == "Remotive":
                default = "Remote"
            else:
                default = "USA"  # Adzuna, Dice, SimplyHired, TheMuse are US-heavy
            country = detect_country(loc, default=default)
            job.country = country
            updated += 1
        if updated:
            await session.commit()
            print(f"[DB] Backfilled country for {updated} jobs")

    async with SessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(Setting).where(Setting.key == "resume"))
        if not result.scalar_one_or_none():
            defaults = [
                Setting(key="resume", value=DEFAULT_RESUME),
                Setting(key="ai_provider", value="openrouter"),
                Setting(key="ai_api_key", value=""),
                Setting(key="ai_model", value="anthropic/claude-sonnet-4-5"),
                Setting(key="adzuna_app_id", value=""),
                Setting(key="adzuna_app_key", value=""),
            ]
            session.add_all(defaults)
            await session.commit()


DEFAULT_RESUME = """Jagadish Reddy Butukuri — Senior Data Engineer
(347) 695-1020 | jagadishbutukuri33@gmail.com

PROFESSIONAL SUMMARY:
• Over 5 years of experience as a Data Engineer with hands-on expertise in Big Data technologies and cloud platforms.
• Skilled in Big Data tools including Hadoop, Spark, Databricks, and Snowflake for large-scale data processing and analytics.
• Experienced with Cloud Technologies: AWS (S3, EMR, Glue, Lambda, Redshift, RDS), Azure (ADLS, Synapse, ADF), and GCP (BigQuery, Dataflow).
• Strong programming skills in Python and SQL, with advanced query development and data transformations.
• Proficient in ETL and data modeling with tools like Informatica, Ab Initio, and ERwin.
• Experienced in orchestration and scheduling tools: Airflow, Oozie, and Azure Data Factory.
• DevOps experience with Jenkins, Docker, and Kubernetes for CI/CD pipelines.
• Knowledge of data privacy, security, and governance: encryption, IAM policies, Ranger, GDPR compliance.
• Skilled in BI and visualization tools: Tableau, Power BI, and Looker.
• Excellent documentation and SDLC experience using Confluence, SharePoint, Jira, and Rally.

WORK EXPERIENCE:

Senior Data Engineer @ Cargill | Minneapolis, MN    Sep 2023 – Present
• Led full lifecycle development of data pipelines using Spark (PySpark) and Hadoop — from requirements gathering through build, deployment, and production monitoring via CloudWatch — processing food production, procurement, and supply chain data across global operations.
• Reduced data ingestion latency by optimizing multi-source ingestion from CSV, JSON, and XML into AWS S3 and Azure ADLS, enabling near-real-time food safety and logistics analytics.
• Developed ETL workflows in Informatica and Ab Initio to integrate structured and unstructured data from food manufacturing plants, warehouses, and distribution centers.
• Migrated on-premises Oracle and SQL Server databases to AWS S3 and Azure ADLS as part of Cargill's cloud modernization initiative.
• Implemented data quality frameworks using Spark and SQL to validate food supply chain data including inventory levels, shipment tracking, and supplier compliance.
• Built automated Airflow DAGs for scheduling and orchestration of ETL jobs processing daily food commodity pricing, demand forecasting, and logistics feeds.
• Enforced row-level security and IAM policies protecting sensitive trade and supplier contract data across multiple business units.
• Delivered Tableau dashboards tracking supply chain KPIs including on-time delivery rates and inventory turnover for supply chain managers and executives.
• Reduced pipeline failure rates through comprehensive Log4j logging and custom exception handling frameworks across high-volume food distribution data flows.
• Containerized data pipelines with Docker and deployed via Jenkins CI/CD, reducing release cycle time significantly.
Technologies Used: PySpark, Hadoop, AWS (S3, EMR, Glue, Lambda, CloudWatch), Azure (ADLS, ADF), Informatica, Ab Initio, Airflow, Oracle, SQL Server, Tableau, Log4j, Docker, Jenkins

Data Engineer @ Molina Healthcare | Long Beach, CA    Jan 2021 – Jul 2022
• Developed Spark (Scala) jobs for processing Medicaid and Medicare claims data, enabling risk analytics and member health outcome reporting.
• Leveraged AWS EMR and Redshift for large-scale aggregation and storage of healthcare enrollment and claims datasets.
• Performed advanced SQL queries and PL/SQL procedures for analysis of member demographics and provider billing data.
• Integrated APIs to ingest health plan and clinical data feeds into Snowflake for centralized analytics consumption.
• Designed and maintained data models using ERwin for relational and star schema structures supporting healthcare reporting.
• Implemented Airflow for workflow orchestration of ETL processes across multiple healthcare data sources.
• Built automated testing frameworks for data validation and quality checks on claims and eligibility datasets.
• Enabled data privacy via column masking, PHI de-identification, and HIPAA/GDPR compliance checks.
• Monitored pipelines using custom logging and exception handling to ensure SLA adherence for healthcare data delivery.
• Version controlled all code using GitHub and actively participated in peer code reviews.
Technologies Used: Spark (Scala), AWS (EMR, Redshift, S3), Snowflake, ERwin, Airflow, Oracle, PL/SQL, Python, GitHub, Jenkins

Data Engineer @ JPMorgan Chase | New York, NY    Dec 2018 – Dec 2020
• Built scalable data pipelines using Spark and Databricks to process retail banking transaction data and support financial analytics.
• Ingested semi-structured data from JSON and CSV sources into AWS S3 and Redshift for risk and compliance reporting.
• Conducted ETL transformations using Python and SQL to support fraud detection models and customer segmentation engines.
• Migrated legacy SQL Server data to Snowflake for modernized analytics and regulatory reporting.
• Implemented Power BI dashboards for executive-level financial performance and portfolio analytics.
• Applied encryption and IAM policies to secure sensitive customer PII and financial transaction data.
• Developed Kubernetes-based containers for scalable pipeline deployment and resource management.
• Collaborated with cross-functional teams using Jira for agile sprint planning and delivery tracking.
• Optimized query performance in Redshift and Snowflake using partitioning, clustering, and query profiling.
Technologies Used: Spark (PySpark), Databricks, AWS (S3, Redshift), Snowflake, Python, SQL Server, Power BI, Kubernetes, Jira

TECHNICAL SKILLS:
• Languages: Python, SQL, Scala, Java
• Big Data Tools: Hadoop, Spark, Databricks, Snowflake, Hive
• Databases: Oracle, SQL Server, Postgres, DynamoDB, MongoDB
• Cloud Platforms: AWS, Azure, GCP
• ETL Tools: Informatica, Ab Initio, SSIS
• BI & Visualization: Tableau, Power BI, Looker
• Version Control: Git, GitHub, GitLab
• Orchestration: Airflow, Oozie, Azure Data Factory
• DevOps: Jenkins, Docker, Kubernetes
• Data Formats: CSV, JSON, Parquet, Avro, ORC
• Methodologies: Agile (Scrum), SDLC

EDUCATION:
Master of Science in Information Systems @ Saint Louis University"""

async def mark_expired_jobs_closed(fj_ids: list[int]) -> int:
    """Marks all jobs in the given list of Fantastic.jobs IDs as closed."""
    if not fj_ids:
        return 0
    from sqlalchemy import update
    async with SessionLocal() as db:
        stmt = update(Job).where(Job.fj_id.in_(fj_ids)).where(Job.status == "new").values(status="closed")
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount


async def update_modified_jobs(job_updates: list[dict]) -> int:
    """
    Update existing DB jobs with fresh data from the modified-ats feed.
    Matches by fj_id (preferred) then URL. Only overwrites non-None values.
    Never changes: title, company, url, source, location, country, posted_at, status.
    """
    if not job_updates:
        return 0

    from sqlalchemy import select

    UPDATEABLE = [
        "description", "salary", "visa_sponsorship", "experience_level",
        "employment_type", "benefits", "job_expiry", "logo_url",
        "company_size", "company_industry", "company_hq", "company_funding",
        "ai_keywords",
    ]

    updated = 0
    async with SessionLocal() as db:
        for jdata in job_updates:
            fj_id = jdata.get("fj_id")
            url   = jdata.get("url")

            job = None
            if fj_id is not None:
                r = await db.execute(select(Job).where(Job.fj_id == fj_id))
                job = r.scalar_one_or_none()
            if not job and url:
                r = await db.execute(select(Job).where(Job.url == url))
                job = r.scalar_one_or_none()

            if not job:
                continue  # job not in our DB — skip (don't insert from modified feed)

            for field in UPDATEABLE:
                val = jdata.get(field)
                if val is not None:  # only overwrite when FJ provided a value
                    setattr(job, field, val)
            updated += 1

        if updated:
            await db.commit()

    return updated
