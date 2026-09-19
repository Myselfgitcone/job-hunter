"""Pure-code tests for the mirror pipeline (ai/tailor_mirror.py). No model call.
Run from backend/:  python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import tailor as t  # noqa: E402
from ai import tailor_mirror as m  # noqa: E402
from ai.tailor_mirror_prompt import ADD_DUTY_SYSTEM, TAILOR_SYSTEM_MIRROR  # noqa: E402

JD = """Role and Responsibilities
 * Design, build, and maintain data pipelines and integrations across enterprise systems (ERP, project management tools).
 * Maintain documentation for data models, pipelines, and reporting logic to ensure transparency and auditability.
 * Monitor database health and performance using tools such as Splunk, Datadog, and Grafana
A collaborative mindset, with openness to feedback and different perspectives
Bachelor's degree in Computer Science or a related field required.
3-7 years of experience in data engineering required.
$113,000 - $146,000 a year
Other duties as assigned.
"""

RESUME = """Jane Doe — Data Engineer
jane@example.com

SUMMARY:
• Data Engineer with 5+ years building pipelines.

SKILLS:
• Languages: Python, SQL

EXPERIENCE:
Senior Data Engineer @ Cargill | Minneapolis, MN\tSep 2024 – Present
• Built and maintained data pipelines and integrations across ERP and project management systems for supply chain reporting teams.
• Built Kafka streaming pipelines for procurement events used by logistics planners.
• Documented data models, pipelines and reporting logic in Confluence, giving auditors a record of every source-to-target mapping.
• Tuned Spark jobs for the nightly load.
• Wrote the on-call runbook for the platform team.
• Reviewed pull requests for the ingestion service.
Technologies Used: Kafka, Spark

Data Engineer @ JPMorgan Chase | New York, NY\tDec 2018 – Dec 2020
• Built and maintained data pipelines and integrations across ERP and project management systems for risk reporting teams.
• Built Spark pipelines for ten downstream teams.
• Migrated a SQL Server warehouse to Snowflake.
• Provisioned AWS infrastructure with CloudFormation.
• Configured IAM policies for customer data.
• Wrote ETL workflows in Informatica.
Technologies Used: Spark
"""


def test_duty_map_keeps_work_lines_only():
    d = m.jd_duties(JD)
    assert len(d) == 3
    assert d[0].startswith("Design, build, and maintain data pipelines")
    assert not any("mindset" in x or "Bachelor" in x or "$" in x or "years of" in x or "Other duties" in x for x in d)


def test_uncovered_duties_finds_the_gap():
    d = m.jd_duties(JD)
    miss = m.uncovered_duties(d, RESUME, job=None)
    assert [d[n] for n in miss] == [d[2]]                     # Splunk / Datadog / Grafana has no bullet
    covered = RESUME.replace("• Tuned Spark jobs for the nightly load.",
                             "• Monitored database health and performance in Datadog and Grafana dashboards for the platform team.")
    assert m.uncovered_duties(d, covered, job=None) == []


def test_hedges_and_filler_go():
    text = ("X\n\nEXPERIENCE:\nDE @ Acme | NY\t2021 – Present\n"
            "• Managed robust item master records for claims data, applying principles transferable to Bills of Material.\n"
            "• Built various seamless pipelines for the finance team.\n")
    notes: list = []
    out = m.strip_filler(m.strip_hedges(text, notes), notes)
    assert "transferable" not in out and "robust" not in out and "seamless" not in out and "various" not in out
    assert "• Managed item master records for claims data." in out
    assert "• Built pipelines for the finance team." in out and len(notes) == 2


def test_same_bullet_in_an_older_job_is_removed():
    notes: list = []
    out = m.dedupe_across_jobs(RESUME, notes)
    jobs = dict(t._job_bodies(out))
    assert "integrations across ERP" in jobs["cargill"]                   # Job 1 is never touched
    assert "integrations across ERP" not in jobs["jpmorgan chase"] and notes
    assert out.count("• ") == RESUME.count("• ") - 1


def test_figure_bullet_returns_to_its_job():
    base = ("Jane Doe — DE\njane@example.com\n\nEXPERIENCE:\n"
            "Senior Data Engineer @ Cargill | Minneapolis, MN\tSep 2024 – Present\n"
            "• Optimized PySpark ETL frameworks in Databricks, saving over $100K per year in cluster spend.\n"
            "• Built Kafka streaming pipelines for procurement events used by logistics planners.\n")
    notes: list = []
    restored: list = []
    out = m.restore_figure_bullets(RESUME, base, "Databricks pipelines", notes, restored)
    assert "$100K per year" in dict(t._job_bodies(out))["cargill"] and len(restored) == 1
    assert m.restore_figure_bullets(out, base, "Databricks pipelines", [], []) == out      # once only


def test_prompt_carries_the_users_rules():
    p = TAILOR_SYSTEM_MIRROR
    assert "6–7 bullets" in p                                          # summary length the user chose
    assert "Job 1: 10–12 · Job 2: 8–10 · Job 3: 7–9" in p and "1–2 more" in p
    assert "NEVER THE SAME BULLET TWICE" in p and "Invent NO figure" in p
    assert "transferable to" in p and "Spearheaded" in p              # named so they are never written
    assert "NO number of any kind" in ADD_DUTY_SYSTEM
    assert m.JOB_MAX == (14, 12, 11) and m.MAX_ADDS == 6
