"""Pure-code tests for the 2026-09-17 policy: cover every JD point with strong
bullets, verbs sized to tenure, and never throw real base content away.
Run from backend/:  python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import tailor as t  # noqa: E402

BASE_5Y = """Jane Doe — Senior Data Engineer
jane@example.com

SUMMARY:
• Senior Data Engineer with 5+ years building data platforms.

SKILLS:
• Orchestration: Airflow, Dagster
• Warehouses: Snowflake, Redshift

EXPERIENCE:
Senior Data Engineer @ Cargill | Minneapolis, MN\tSep 2024 – Present
• Migrated Airflow DAGs to Dagster asset-based orchestration for commodity pricing and logistics feeds, cutting failed-run triage time from hours to under an hour.
• Integrated SageMaker as the ML training backend and served features through Feast, versioning embeddings in Pinecone across fine-tuning cycles for the data science team.
• Built Kafka streaming pipelines for procurement events, replacing nightly batch loads.
Technologies Used: Airflow, Dagster, Kafka, SageMaker, Feast

Data Engineer @ JPMorgan Chase | New York, NY\tDec 2018 – Dec 2020
• Migrated a legacy SQL Server warehouse to Snowflake for regulatory reporting, cutting storage cost and query latency for the finance teams.
• Built Spark pipelines processing hundreds of millions of daily transactions to a sub-2-hour SLA.
Technologies Used: Snowflake, Spark
"""


def test_fact_drift_catches_word_numbers_and_units():
    assert t._fact_drift("cutting incident resolution to under 2 hours",
                         "cutting incident resolution to under one hour") == "one"
    assert t._fact_drift("cutting full-refresh runtime from about 6 hours to under one hour",
                         "cutting full-refresh runtime to minutes") == "minutes"
    assert t._fact_drift("cutting ad-hoc requests 45%", "cutting ad-hoc requests to routine levels") == ""
    assert t._fact_drift("ran the job nightly for finance", "ran the job nightly for the finance team") == ""
    assert t._fact_drift("cut cost", "cut cost 30%") == "30%"
    assert t._fact_drift("cutting manual classification effort 60%", "eliminating manual classification effort") == "eliminating"
    assert t._fact_drift("halving provisioning time", "halving provisioning time per deployment") == ""


def test_verb_ladder_steps_led_down_at_five_years_and_never_on_foreign():
    text = BASE_5Y.replace("• Built Kafka streaming pipelines", "• Led Kafka streaming pipelines") \
                  .replace("• Migrated Airflow DAGs", "• Owned Airflow DAGs")
    text = text.replace("Technologies Used: Airflow, Dagster, Kafka, SageMaker, Feast",
                        "• Led adoption of AI-assisted development across the team using Amazon Q, Cursor, and Claude Code.\n"
                        "Technologies Used: Airflow, Dagster, Kafka, SageMaker, Feast")
    notes: list = []
    out = t._verb_ladder_guard(text, BASE_5Y, ["Claude Code", "Cursor", "Amazon Q"], notes)
    assert "• Drove Kafka streaming pipelines" in out          # Led at 5 years -> one rung down
    assert "• Delivered Airflow DAGs" in out                   # Owned at 5 years
    assert "Led adoption" not in out
    assert notes and "verb ladder" in notes[0]
    # a 10-year base keeps Led; a foreign-tool bullet still steps down
    base10 = BASE_5Y.replace("5+ years", "10+ years")
    out10 = t._verb_ladder_guard(text, base10, ["Claude Code"], [])
    assert "• Led Kafka streaming pipelines" in out10
    assert "Led adoption" not in out10


def test_restore_base_bullets_brings_back_dropped_jd_tool_lines():
    # the writer dropped the Airflow bullet at Cargill and the Snowflake one at JPMC
    lines = [ln for ln in BASE_5Y.split("\n") if "Airflow DAGs" not in ln and "SQL Server warehouse" not in ln]
    tailored = "\n".join(lines).replace("• Orchestration: Airflow, Dagster", "• Orchestration: Dagster")
    ctx = {"target_tools": ["Airflow", "Snowflake", "Kafka"], "target_cloud": "None"}
    notes: list = []
    restored: list = []
    out = t._restore_base_bullets(tailored, BASE_5Y, ctx, notes, restored)
    assert "Migrated Airflow DAGs to Dagster" in out and "SQL Server warehouse to Snowflake" in out
    assert len(restored) == 2 and any("Airflow" in n for n in notes)
    jobs = dict(t._split_jobs(out))
    assert "Airflow DAGs" in jobs["cargill"] and "Snowflake" in jobs["jpmorgan chase"]
    assert "Airflow DAGs" not in jobs["jpmorgan chase"]
    # nothing to restore when the tool is still evidenced in that job
    assert t._restore_base_bullets(BASE_5Y, BASE_5Y, ctx, [], []) == BASE_5Y
    # a tool the writer moved to ANOTHER job is not restored (it is still on the page)
    moved = tailored.replace("• Built Spark pipelines", "• Built Airflow and Spark pipelines")
    out2 = t._restore_base_bullets(moved, BASE_5Y, ctx, [], [])
    assert "Airflow DAGs" not in out2 and "SQL Server warehouse to Snowflake" in out2
    # a generic term never triggers a restore, and SKILLS rows after the last job are not bullets
    base_sk = BASE_5Y + "\nSKILLS:\n• Cloud: AWS Glue, Lambda, Kinesis, Athena, Lake Formation, EMR, Redshift, S3, Step Functions, Batch, ECS, CloudFormation, CDK\n"
    ctx2 = {"target_tools": ["SQL", "Glue", "Kafka"], "target_cloud": "None"}
    out3 = t._restore_base_bullets(BASE_5Y.replace("Kafka", "Kinesis"), base_sk, ctx2, [], [])
    assert "Cloud: AWS Glue" not in out3


def test_restore_base_bullets_skips_old_cloud_lines_under_a_swap():
    base = BASE_5Y.replace("• Built Kafka streaming pipelines for procurement events, replacing nightly batch loads.",
                           "• Built Kafka streaming pipelines on AWS EMR and S3 for procurement events, replacing nightly batch loads.")
    tailored = "\n".join(ln for ln in base.split("\n") if "Kafka streaming" not in ln)
    ctx = {"target_tools": ["Kafka"], "target_cloud": "Azure"}
    notes: list = []
    out = t._restore_base_bullets(tailored, base, ctx, notes, [])
    assert "Kafka streaming pipelines on AWS EMR" not in out and any("pre-swap cloud" in n for n in notes)


def test_gutted_bullets_come_back_from_the_base():
    tailored = BASE_5Y.replace(
        "• Integrated SageMaker as the ML training backend and served features through Feast, versioning embeddings in Pinecone across fine-tuning cycles for the data science team.",
        "• Integrated SageMaker backend with Feast feature serving across fine-tuning cycles.") \
        .replace("• Migrated a legacy SQL Server warehouse to Snowflake for regulatory reporting, cutting storage cost and query latency for the finance teams.",
                 "• Migrated SQL Server warehouse to Snowflake.")
    notes: list = []
    out = t._restore_gutted_bullets(tailored, BASE_5Y, {"target_cloud": "None"}, notes)
    assert "versioning embeddings in Pinecone" in out and "cutting storage cost and query latency" in out
    assert notes and "stub guard: 2" in notes[0]
    # a short bullet that is NOT a base rewrite is left alone
    other = BASE_5Y.replace("• Built Kafka streaming pipelines for procurement events, replacing nightly batch loads.",
                            "• Wrote the on-call runbook for the team.")
    assert t._restore_gutted_bullets(other, BASE_5Y, {"target_cloud": "None"}, []) == other


def test_duty_match_accepts_synonyms_and_two_neighbouring_bullets():
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Conducted peer code reviews, mentoring junior analysts on data modeling standards.\n"
            "• Designed dimensional models and Data Vault 2.0 structures in ERwin for reporting.\n"
            "• Built self-service tooling with layered bronze/silver/gold Medallion architecture.\n"
            "• Optimized PySpark ETL frameworks through partition tuning, saving cluster spend.\n")
    duties = ["Mentor and coach junior engineers",
              "Design dimensional models and medallion-style data layers",
              "Tune PySpark and Redshift performance for runtime and cost",
              "Lead technical pre-sales engagements with sellers"]
    missing = t._unevidenced(duties, text)
    assert missing == ["Lead technical pre-sales engagements with sellers"]


def test_figure_cap_scales_with_bullet_count_and_fix_text_cuts_on_words():
    assert t._figure_cap(11) == 6 and t._figure_cap(7) == 4 and t._figure_cap(5) == 3 and t._figure_cap(3) == 3
    bullets = "\n".join(f"• Built feed {i} on Spark, cutting load time {10 + i}%." for i in range(10))
    text = "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n" + bullets + "\n"
    assert len(t._figure_cap_plan(text, ["Spark"], t._FIGURES_PER_JOB[1])) == 10 - t._figure_cap(10)
    assert t._short("Design and build production-grade pipelines and reusable data assets", 40) == "Design and build production-grade…"
    assert t._short("short one", 40) == "short one"


def test_skill_rows_dedupe_and_placeholder_sections_go():
    text = ("Jane Doe — X\n\nSKILLS:\n• Orchestration: Apache Airflow, Dagster\n"
            "• Transformation: dbt, Apache Airflow, Glue Data Catalog\n• API and Integration: Kafka Connect\n"
            "• Streaming: Kafka Connect\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built things.\n\n"
            "CERTIFICATIONS:\n(none listed in base resume)\n")
    notes: list = []
    out = t._dedupe_skill_rows(text, notes)
    assert "• Transformation: dbt, Glue Data Catalog" in out and "• Streaming: Kafka Connect" not in out
    assert notes and "Apache Airflow" in notes[0]
    out, n = t._strip_junk_lines(out)
    assert n == 1
    out = t._strip_empty_sections(out)
    assert "CERTIFICATIONS" not in out


def test_plural_jd_terms_match_singular_bullets():
    body = ("EXPERIENCE:\nX @ Y | Z\n• Developed Azure Functions for REST API integrations and schema reconciliation.\n"
            "• Ingested SAP feeds and Kafka message queue events.\n")
    assert t._unevidenced(["REST APIs", "message queues", "SAP", "Azure Functions"], body) == []


def test_tense_drift_rejects_base_form_stubs():
    assert t._tense_drift("Migrated Airflow DAGs to Dagster", "Migrate DAGs to Dagster")
    assert t._tense_drift("Engineered entity-resolution logic", "Engineer entity-resolution logic in Python")
    assert not t._tense_drift("Migrated Airflow DAGs to Dagster", "Moved Airflow DAGs to Dagster")
    assert not t._tense_drift("Designs pipelines for finance", "Builds pipelines for finance")


def test_cap_guard_keeps_a_jd_tools_only_bullet():
    bullets = "\n".join(f"• Built feed {i} on Spark for the finance team." for i in range(12))
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n" + bullets
            + "\n• Moved Airflow DAGs to Dagster for the pricing feeds.\n")
    base = "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built feeds.\n"
    out = t._enforce_caps(text, base, [], bonus=1, keep_tools=["Airflow", "Spark"])
    assert "Airflow DAGs" in out and out.count("• ") == 12
    out2 = t._enforce_caps(text, base, [], bonus=1)
    assert "Airflow DAGs" not in out2                     # last in the job, no protection: trimmed


def test_truncated_analyze_json_is_repaired():
    raw = ('```json\n{"target_tools": ["Snowflake", "dbt", "Airflow"], "present": ["dbt"], '
           '"tool_facts": {"Snowflake": {"category": "warehouse", "release_year": 2014}, "dbt": {"category": "transform')
    ctx = t._loads_loose(raw)
    assert ctx.get("target_tools") == ["Snowflake", "dbt", "Airflow"] and ctx.get("present") == ["dbt"]
    assert "Snowflake" in ctx.get("tool_facts", {})
    assert t._loads_loose("no json here") == {}
    assert t._loads_loose('{"a": 1}') == {"a": 1}


def test_foreign_tool_bullet_is_demoted_out_of_impact_slots():
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Built a Trino query layer over the lakehouse for analytics teams.\n"
            "• Built Kafka pipelines cutting latency 40%.\n"
            "• Designed dbt models for finance.\n"
            "• Wrote runbooks.\n"
            "• Mentored engineers.\n")
    base = "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Kafka pipelines cutting latency 40%.\n"
    out = t._demote_bridge_bullets(text, [], foreign=["Trino"], base_resume=base)
    bl = [ln for ln in out.split("\n") if ln.startswith("•")]
    assert bl[0].startswith("• Built Kafka") and bl[-1].startswith("• Built a Trino")
