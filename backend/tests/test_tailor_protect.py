"""PROTECT pipeline (2026-10-29): the pure guards. Run from backend/: python -m pytest tests -q"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import tailor as t  # noqa: E402
from ai.tailor_protect import (  # noqa: E402
    JOB_MAX, base_identity, drop_foreign_bullets, enforce_caps, fix_years, normalize_base, order_projects, rebuild,
    restore_lost_figures, settle_long_bullets, split_sections, split_tools, strip_unowned_skills, summary_ok, trim_skills, uncovered_must_haves,
)

BASE = """JAGADISH BUTUKURI
Senior Data Engineer | AI Engineer
St. Louis, MO | (347) 695-1020 | jb@example.com | linkedin.com/in/x | github.com/y | site.dev
SUMMARY
Senior Data Engineer with 5+ years. Saved $100K+ a year and cut a 6-hour refresh to under 1 hour.
SKILLS
Languages: Python, SQL, PySpark
Lakehouse: Databricks, Delta Lake, Snowflake
EXPERIENCE
Senior Data Engineer @ Cargill | Minneapolis, MN (remote) | Sep 2024 – Present
Saved $100K+ a year in cluster spend by tuning PySpark jobs in Databricks with adaptive query execution and caching.
Cut stale-data incidents 40% by building the AWS and Databricks ELT platform with Delta Lake schema contracts.
Data Engineer @ Molina Healthcare | Long Beach, CA | Jan 2021 – Jul 2022
Cut full-refresh runtime from about 6 hours to under 1 hour by moving loads to CDC-based incremental pipelines.
PROJECTS
Footnote — RAG over SEC filings (personal, live)  ·  site/footnote
Raised answer grounding from 87% to 100% on a 29-question LLM-as-judge evaluation suite.
Grainflow — streaming lakehouse (personal, live)  ·  site/grainflow
Kafka to Iceberg with 44 unit tests in CI.
EDUCATION
M.S. Information Systems, Saint Louis University — Aug 2022 – May 2024
CERTIFICATIONS
AWS Certified AI Practitioner
"""


def test_upload_text_becomes_engine_shaped():
    base = normalize_base(BASE)
    header, sec = split_sections(base)
    assert header[0] == "JAGADISH BUTUKURI"
    assert set(sec) == {"SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS"}
    assert all(ln.startswith("• ") for ln in sec["SKILLS"] if ln.strip())
    exp = sec["EXPERIENCE"]
    assert t._is_job_header_line(exp[0]) and exp[1].startswith("• ")
    assert [c for c, _ in t._job_bodies(base)] == ["cargill", "molina healthcare"]
    proj = [ln for ln in sec["PROJECTS"] if ln.strip()]
    assert proj[0].startswith("Footnote —") and proj[1].startswith("• ")


def test_identity_keeps_title_and_city():
    base = normalize_base(BASE)
    header, _ = split_sections(base)
    name, title, contact = base_identity(header, base)
    assert name == "JAGADISH BUTUKURI"
    assert title == "Senior Data Engineer | AI Engineer"
    assert "St. Louis, MO" in contact and "jb@example.com" in contact
    assert t._contact_extras(base)[0] == "St. Louis, MO"         # the shared contact guard keeps the city now


def test_owned_vs_gap_tools():
    base = normalize_base(BASE)
    have, gaps = split_tools(["Databricks", "BigQuery", "PySpark", "Adjust", "Delta Lake"], base, ["Kafka"])
    assert have == ["Databricks", "PySpark", "Delta Lake"]
    assert gaps == ["BigQuery", "Adjust"]
    have, _ = split_tools(["Kafka"], base, ["Kafka"])
    assert have == ["Kafka"]                                          # profile skills count as owned


def test_unowned_skills_are_stripped_not_added():
    base = normalize_base(BASE)
    notes = []
    rows = strip_unowned_skills(["• Warehouses: Databricks, BigQuery, Snowflake", "• Ads: Adjust, AppsFlyer"], base, None, notes)
    assert rows == ["• Warehouses: Databricks, Snowflake"]
    assert any("BigQuery" in n for n in notes)


def test_foreign_tool_or_invented_figure_drops_the_bullet():
    base = normalize_base(BASE)
    exp = ("EXPERIENCE:\nSenior Data Engineer @ Cargill | Minneapolis, MN (remote) | Sep 2024 – Present\n"
           "• Designed core ads data models in BigQuery powering attribution for four teams.\n"
           "• Cut stale-data incidents 40% by building the AWS and Databricks ELT platform with Delta Lake contracts.\n"
           "• Processed billions of rows daily holding quality above 99.9% across 30 feeds.\n")
    notes = []
    out = drop_foreign_bullets(exp, base, "", ["BigQuery"], notes)
    kept = [ln for ln in out.split("\n") if ln.startswith("•")]
    assert len(kept) == 1 and "40%" in kept[0]
    assert any("BigQuery" in n for n in notes) and any("invented" in n for n in notes)


def test_caps_drop_the_weakest_numberless_bullets_first():
    exp = "EXPERIENCE:\nSenior Data Engineer @ Cargill | Minneapolis, MN | Sep 2024 – Present\n" + "\n".join(
        f"• Built pipeline number {i} with Spark for the commodity team and a figure of {i}0% when it has one." if i % 2
        else f"• Documented things for the team in the wiki about pipelines item {i} without any number here at all."
        for i in range(1, 11))
    exp = exp.replace("figure of 20%", "figure of twenty").replace("figure of 40%", "figure of forty")
    notes = []
    out = enforce_caps(exp, notes, t._content_words("spark pipelines commodity"), ["Spark"])
    bl = t._job_bullet_lines(out)[0][1]
    assert len(bl) == JOB_MAX[0]
    assert any("cap guard" in n for n in notes)


def test_projects_follow_the_postings_family_and_stay_verbatim():
    base = normalize_base(BASE)
    _, sec = split_sections(base)
    ai_first = order_projects(sec["PROJECTS"], "AI Engineer", "")
    de_first = order_projects(sec["PROJECTS"], "Senior Data Engineer", "")
    assert ai_first[0].startswith("Footnote") and de_first[0].startswith("Grainflow")
    assert sorted(ln for ln in ai_first if ln.strip()) == sorted(ln for ln in sec["PROJECTS"] if ln.strip())


def test_summary_must_keep_base_figures():
    base_sum = ["Senior Data Engineer with 5+ years. Saved $100K+ a year and cut a 6-hour refresh to under 1 hour."]
    assert summary_ok(["Senior DE with 5+ years on Databricks. Saved $100K+ a year and cut a 6-hour refresh to under 1 hour."], base_sum)
    assert not summary_ok(["Senior DE with 5+ years on Databricks across three industries."], base_sum)
    assert not summary_ok(["a", "b", "c", "d"], base_sum)


def test_rebuild_orders_sections():
    out = rebuild(["Name — Title", "x | y"], {"EDUCATION": ["M.S."], "SUMMARY": ["s"], "PROJECTS": ["P — p", "• b"]})
    assert out.index("SUMMARY:") < out.index("PROJECTS:") < out.index("EDUCATION:")


def test_years_claim_never_grows():
    base_sum = ["Senior Data Engineer with 5+ years building platforms."]
    notes = []
    out = fix_years(["Senior Data Engineer with 7+ years on Databricks.", "Saved $100K+ a year."], base_sum, notes)
    assert out[0] == "Senior Data Engineer with 5+ years on Databricks."
    assert out[1] == "Saved $100K+ a year." and notes


def test_lost_base_figure_comes_back():
    base = normalize_base(BASE)
    _, sec = split_sections(base)
    base_exp = "EXPERIENCE:\n" + "\n".join(sec["EXPERIENCE"])
    exp = ("EXPERIENCE:\nSenior Data Engineer @ Cargill | Minneapolis, MN (remote) | Sep 2024 – Present\n"
           "• Saved $100K+ a year in cluster spend by tuning PySpark jobs in Databricks with adaptive query execution and caching.\n"
           "• Documented the platform for the commodity team and ran weekly reviews with stakeholders across three domains.\n"
           "Data Engineer @ Molina Healthcare | Long Beach, CA | Jan 2021 – Jul 2022\n"
           "• Cut full-refresh runtime from about 6 hours to under 1 hour by moving loads to CDC-based incremental pipelines.\n")
    notes = []
    out = restore_lost_figures(exp, base_exp, notes)
    assert "40%" in out and "Documented the platform" in out      # under the cap: appended, nothing replaced
    assert any("restored 1" in n for n in notes)


def test_skills_trim_to_base_count_plus_slack():
    notes = []
    rows = trim_skills(["• A: a, b, c, d, e, f", "• B: g, h"], 5, notes)
    assert rows == ["• A: a, b, c", "• B: g, h"] and notes


def test_must_have_metric_counts_owned_terms_not_echoes():
    tailored = ("X — Y\nphone | mail\n\nSUMMARY:\nBuilds pipelines on Databricks and dbt.\n\nEXPERIENCE:\n"
                "Senior Data Engineer @ Cargill | Minneapolis, MN | Sep 2024 – Present\n"
                "• Cut stale-data incidents 40% by building the Databricks ELT platform with dbt models and Delta Lake contracts.\n")
    duties = ["Experience building data models in dbt on Databricks for analytics teams",
              "Proficiency in at least two of: Ruby, Node.js, Python, or Next.js",
              "Design fact and dimension tables that power delivery and attribution use cases"]
    miss = uncovered_must_haves(duties, tailored, ["dbt", "Databricks", "Ruby", "Node.js", "Python", "Next.js"])
    assert 0 not in miss                 # names dbt + Databricks, both present
    assert 1 in miss and 2 in miss       # Ruby/Node absent; fact/dim wording absent


def test_overlong_bullet_falls_back_to_the_base_twin():
    base = normalize_base(BASE)
    _, sec = split_sections(base)
    base_exp = "EXPERIENCE:\n" + "\n".join(sec["EXPERIENCE"])
    long = ("• Saved $100K+ a year in cluster spend by tuning PySpark jobs in Databricks with adaptive query execution, "
            "partitioning, caching, cluster right-sizing, FinOps tagging, monthly cost reviews and quarterly planning sessions with every platform owner.")
    exp = "EXPERIENCE:\nSenior Data Engineer @ Cargill | Minneapolis, MN (remote) | Sep 2024 – Present\n" + long + "\n"
    notes = []
    out = settle_long_bullets(exp, base_exp, notes)
    body = [ln for ln in out.split("\n") if ln.startswith("•")][0]
    assert len(body.split()) <= 32 and "$100K+" in body and notes
