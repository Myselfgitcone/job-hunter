"""A base resume may write its job headers with pipes instead of "@":

    Senior Data Engineer | Cargill | Minneapolis, MN   Sep 2024 - Present

(the user's own base does; the fields live in a one-row table that the upload parser joins with
spaces). Every guard reads the "@" form, so without normalising this the engine saw ZERO employers
and the figure restore, cloud guard, invented-employer guard and base-specifics guard all silently
did nothing while the output still looked correct.

Run from backend/:  python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import tailor as t  # noqa: E402

PIPE_BASE = """JAGADISH BUTUKURI
Senior Data Engineer
(347) 695-1020  |  jagadishbutukuri11@gmail.com

PROFESSIONAL SUMMARY
• Senior Data Engineer with 5+ years building data platforms.

PROFESSIONAL EXPERIENCE
Senior Data Engineer | Cargill | Minneapolis, MN   Sep 2024 – Present
• Optimized PySpark workloads in Databricks, generating more than $100K in annual platform savings.
Data Engineer | Molina Healthcare | Long Beach, CA   Jan 2021 – Jul 2022
• Configured CDC incremental loading, cutting full-refresh from about six hours to under one hour.
Data Engineer | JPMorgan Chase | New York, NY   Dec 2018 – Dec 2020
• Built Spark pipelines processing hundreds of millions of daily retail-banking records.

TECHNICAL SKILLS
Languages: Python, SQL, PySpark, PL/SQL, Scala, Shell scripting, Java
Cloud Platforms: AWS (S3, EMR, Glue) | Azure (ADF, Synapse)

EDUCATION
Master of Science in Information Systems | Saint Louis University | 2022 – 2024
"""


def test_pipe_headers_become_visible_employers():
    assert t._job_bodies(PIPE_BASE) == []                    # the fault this guards against
    fixed = t.normalize_job_headers(PIPE_BASE)
    assert [c for c, _ in t._job_bodies(fixed)] == ["cargill", "molina healthcare", "jpmorgan chase"]
    assert "Senior Data Engineer @ Cargill | Minneapolis, MN\tSep 2024 – Present" in fixed


def test_education_and_skills_rows_are_left_alone():
    fixed = t.normalize_job_headers(PIPE_BASE)
    # a degree line has a job header's exact shape and must not become a fourth employer
    assert "Master of Science in Information Systems | Saint Louis University | 2022 – 2024" in fixed
    assert "Languages: Python, SQL, PySpark, PL/SQL, Scala, Shell scripting, Java" in fixed
    assert "Cloud Platforms: AWS (S3, EMR, Glue) | Azure (ADF, Synapse)" in fixed
    assert sum(1 for a, b in zip(PIPE_BASE.split("\n"), fixed.split("\n")) if a != b) == 3


def test_only_a_trailing_date_range_makes_a_header():
    for line in ("Python | SQL | Scala",
                 "Cloud Platforms: AWS (S3, EMR) | Azure (ADF)",
                 "Certifications | AWS Certified Data Engineer | 2023"):
        assert t.normalize_job_headers(line) == line, line
    assert t.normalize_job_headers("Data Engineer | Acme | NY   Jan 2020 - Dec 2021") == \
        "Data Engineer @ Acme | NY\tJan 2020 - Dec 2021"
    # a header with no location still works
    assert t.normalize_job_headers("Senior Engineer | Foo Corp   2018 - 2020") == \
        "Senior Engineer @ Foo Corp\t2018 - 2020"


def test_an_at_header_is_untouched():
    already = "Senior Data Engineer @ Cargill | Minneapolis, MN\tSep 2024 – Present"
    assert t.normalize_job_headers(already) == already
