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
    out = m.dedupe_across_jobs(RESUME, notes, floor=0)
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
    assert "4–5 bullets, never a sixth" in p                            # summary length the user chose
    assert "Job 1: 10–12 · Job 2: 8–10 · Job 3: 7–9" in p
    assert "Never one more" in p        # the cap is the top of the range, no escape clause
    assert "NEVER THE SAME BULLET TWICE" in p
    assert "A base figure is never altered" in p and "never a headline figure" in p
    assert "20–30 words" in p and "23–30 items in TOTAL" in p
    assert "transferable to" in p and "Spearheaded" in p              # named so they are never written
    assert m.JOB_MAX == (12, 10, 9) and m.MAX_ADDS == 4
    assert m.BULLET_MAX == 30 and m.SUMMARY_MAX == 5 and m.SKILL_ITEMS_MAX == 30
    assert m.ALLOW_INVENTED_FIGURES is True          # the user's call, 2026-09-21
    assert ADD_DUTY_SYSTEM


def test_invented_employer_is_removed():
    fake = RESUME + ("\nSenior Data Analyst @ Sutherland Global Services | Hyderabad, India\tJun 2016 – Sep 2018\n"
                     "• Developed SQL and Python scripts to automate reporting pipelines for operations teams.\n"
                     "Technologies Used: Oracle, SQL\n")
    notes: list = []
    out = m.drop_invented_jobs(fake, RESUME, notes)
    assert "Sutherland" not in out and "Cargill" in out and "JPMorgan Chase" in out and notes
    assert m.drop_invented_jobs(RESUME, RESUME, []) == RESUME


def test_company_pitch_and_legal_text_never_become_duties():
    jd = ("Karoo's mission is to improve the lives of every cardiac patient in America.\n"
          "We're fanatical about simplifying everything about car buying.\n"
          "This position requires that the job be performed in the United States.\n"
          "Candidate must be able to obtain and maintain a Public Trust.\n"
          "Write Scala code to support the work on the Claims Cost Measures Team.\n"
          "Perform Data Validation and utilize SQL for data queries.\n"
          "Why Us:\nComprehensive medical, dental, and vision insurance for all employees\n")
    d = m.jd_duties(jd, "Karoo", ["Scala", "SQL"])
    assert d == ["Write Scala code to support the work on the Claims Cost Measures Team",
                 "Perform Data Validation and utilize SQL for data queries"]


def test_long_gerund_bullet_is_split_and_emr_is_not_a_cloud():
    text = ("X\n\nEXPERIENCE:\nDE @ Acme | NY\t2018 – 2020\n"
            "• Built real-time event streams with Kafka Connect and Confluent Schema Registry enforcing data contracts across "
            "15+ producer teams, routing hundreds of millions of daily events and cutting schema-related pipeline failures "
            "while storing fraud-signal data in Cassandra and Redis for sub-100ms risk scoring capabilities.\n")
    out = m.split_long(text, [])
    assert out.count("• ") == 2 and "hundreds of millions" in out and "sub-100ms" in out and "15+" in out
    assert all(len(b.split()) <= 40 for b in out.split("\n") if b.startswith("•"))
    assert not any(x.strip() == "emr" for x in m.CLOUD_SIG["AWS"])


def test_split_never_leaves_a_stub():
    text = ("X\n\nEXPERIENCE:\nDE @ Acme | NY\t2018 – 2020\n"
            "• Set up Azure Monitor for observability and service level agreement tracking across Azure Data Factory and "
            "Synapse Analytics workflows, cutting pipeline incident resolution from most of a workday to under 2 hours; "
            "deployed Soda validation to catch schema violations before load.\n")
    out = m.split_long(text, [])
    bl = [b for b in out.splitlines() if b.startswith("•")]
    assert len(bl) == 2 and all(len(b.split()) - 1 >= 12 for b in bl) and "under 2 hours" in out


def test_employer_listed_twice_becomes_one_job():
    twice = RESUME.replace("• Tuned Spark jobs for the nightly load.",
                           "Technologies Used: Kafka\n\nSenior Data Engineer @ Cargill | Minneapolis, MN\tSep 2024 – Present is listed above.\n"
                           "• Tuned Spark jobs for the nightly load.")
    notes: list = []
    out = m.merge_duplicate_jobs(twice, notes)
    assert out.count("@ Cargill") == 1 and notes
    assert [len(bl) for _, bl in t._job_bullet_lines(out)] == [6, 6]
    assert m.merge_duplicate_jobs(RESUME, []) == RESUME
