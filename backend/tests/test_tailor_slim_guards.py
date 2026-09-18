"""Pure-code tests for the slim pipeline's writer-leftover guards.
Run from backend/:  python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import tailor as t  # noqa: E402
from ai import tailor_slim_guards as g  # noqa: E402

RESUME = """Jane Doe — Data Engineer II
jane@example.com

SUMMARY:
• Data Engineer with 5+ years building pipelines across insurance-adjacent agribusiness, healthcare, and financial services domains.

SKILLS:
• Languages: Python, SQL
• DevOps and Infrastructure: CDK, CloudFormation, technical documentation, performance
• Business Intelligence and Analytics: Power BI, Parquet, JSON, NumPy, Pandas, postmortems

EXPERIENCE:
Senior Data Engineer @ Cargill | Minneapolis, MN\tSep 2024 – Present
• Optimized PySpark ETL frameworks in Databricks using Pandas and NumPy for data transformation, adaptive query execution, partitioning, and caching, saving over $100K per year in cluster spend.
• Built Kafka streaming pipelines for procurement events.
Technologies Used: PySpark, Databricks, Kafka

Data Engineer @ JPMorgan Chase | New York, NY\tDec 2018 – Dec 2020
• Built Spark pipelines for ten downstream teams.
Technologies Used: Spark
"""


def test_adjacent_phrase_goes_and_real_industries_stay():
    notes: list = []
    out = g.strip_adjacent(RESUME, notes)
    assert "adjacent" not in out and "across agribusiness, healthcare, and financial services" in out
    assert notes
    alt = g.strip_adjacent("pipelines across insurance-adjacent industries, including agribusiness and healthcare", [])
    assert alt == "pipelines across agribusiness and healthcare"


def test_pandas_leaves_the_spark_bullet_and_gets_its_own():
    notes: list = []
    restored: list = []
    out = g.fix_pandas_placement(RESUME, {"target_tools": ["Pandas", "NumPy", "PySpark"]}, notes, restored)
    spark_line = next(ln for ln in out.split("\n") if ln.startswith("• Optimized PySpark"))
    assert "Pandas" not in spark_line and "$100K" in spark_line and "adaptive query execution" in spark_line
    assert "• Built Pandas and NumPy validation and reconciliation jobs" in out
    assert len(restored) == 1 and notes
    # a bullet where Pandas is plausible is left alone
    ok = RESUME.replace("• Built Kafka streaming pipelines for procurement events.",
                        "• Built Pandas validation jobs for supplier CSV files.")
    ok = ok.replace(" using Pandas and NumPy for data transformation,", ",")
    assert g.fix_pandas_placement(ok, {"target_tools": ["Pandas"]}, [], []) == ok


def test_practice_bullets_added_once_and_only_when_the_jd_asks():
    jd = ("Mentor junior engineers and run design reviews. Must be able to use vscode copilot for development work. "
          "Deep understanding of branching strategies and change control.")
    notes: list = []
    restored: list = []
    out = g.ensure_practice_bullets(RESUME, jd, RESUME, notes, restored)
    assert "• Mentored junior engineers" in out
    assert "vscode copilot" in out.lower() and "branching strategies" in out
    assert len(restored) == 3
    jobs = dict(t._job_bodies(out))
    assert "Mentored junior engineers" in jobs["cargill"] and "Mentored" not in jobs["jpmorgan chase"]
    # second pass adds nothing; a JD without those asks adds nothing
    assert g.ensure_practice_bullets(out, jd, RESUME, [], []) == out
    assert g.ensure_practice_bullets(RESUME, "Build pipelines on Spark.", RESUME, [], []) == RESUME


def test_skill_rows_lose_duties_and_bi_row_keeps_bi():
    notes: list = []
    out = g.clean_skill_rows(RESUME, notes)
    assert "technical documentation" not in out and ", performance" not in out and "postmortems" not in out
    assert "• Business Intelligence and Analytics: Power BI" in out
    assert "• Tools and Formats: Parquet, JSON, NumPy, Pandas" in out
    assert "• DevOps and Infrastructure: CDK, CloudFormation" in out


def test_restore_context_adds_the_product_word():
    base = "X\n\nEXPERIENCE:\nDE @ JPMorgan Chase | NY\t2018 – 2020\n• Migrated a SQL Server warehouse to Snowflake.\n"
    ctx = g.restore_context({"target_tools": ["Snowflake internals", "dbt architecture", "Python"]}, base)
    assert ctx["target_tools"][0] == "Snowflake" and "dbt" not in ctx["target_tools"]      # dbt is not in this base


def test_slim_score_restores_the_constants():
    before = (t._BULLET_MAX, t._figure_cap, t._SHORT_MAX)
    ctx = {"target_tools": ["Kafka"], "responsibilities": [], "job_title": "Data Engineer II"}
    s = g.slim_score(RESUME, RESUME, "Kafka", ctx, [])
    assert isinstance(s.get("overall"), (int, float))
    assert (t._BULLET_MAX, t._figure_cap, t._SHORT_MAX) == before
