"""Pure-code regression tests for the tailor guards (no model calls).

Every bug a live run exposed gets a test here so the next change cannot
bring it back. Run from backend/:  python -m pytest tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import tailor as t  # noqa: E402

BASE = """Jane Doe — Data Engineer
jane@example.com | Austin, TX

SUMMARY:
Data engineer with 6 years building pipelines.

SKILLS:
• Languages: Python, SQL, .NET
• Platforms: Kubernetes, Snowflake, EMR

EXPERIENCE:
Data Engineer @ Acme | 2021 - Present
• Built Python pipelines on Snowflake for finance reporting.
• Deployed Spark jobs on Kubernetes clusters for nightly loads.
• Processed EMR feeds for clinical reporting.
Technologies Used: Python, Snowflake, Kubernetes, EMR

Data Engineer @ Beta | 2018 - 2021
• Wrote SQL models and Python jobs on Snowflake.
Technologies Used: Python, SQL, Snowflake
"""

EVANS_LABEL = "orchestration tools (e.g., Airflow, Dagster, or dbt for transformations)"
EVANS_JD = ("Experience building pipelines with orchestration tools (e.g., Airflow, "
            "Dagster, or dbt for transformations). Strong SQL. Familiarity with EMR.")


def test_tidy_keeps_leading_dot():
    body, _ = t._tidy_items(" Python, SQL, .NET.", 20)
    assert body == "Python, SQL, .NET"


def test_dotnet_survives_clean_and_final_trim():
    # live miss (Evans): ".NET" -> "NET" in the tidy pass, then the keep-list
    # (".NET") no longer matched and the Skills-only keyword was deleted
    out, _ = t._clean_lists(BASE)
    assert ".NET" in out
    notes: list = []
    kept = t._drop_unevidenced_skills(out, notes, keep=[".NET"])
    assert ".NET" in kept, notes
    # the keep-list compares on the normalised key
    assert ".NET" not in t._orphan_skills(out, keep=["NET"])


def test_split_compound_label_into_products():
    ctx = {"target_tools": [EVANS_LABEL, "SQL"], "present": ["SQL"], "missing": [EVANS_LABEL],
           "bridge_only": [], "equivalent": []}
    log = t._split_compound_labels(ctx, EVANS_JD, BASE)
    assert log and EVANS_LABEL not in ctx["target_tools"]
    for piece in ("Airflow", "Dagster", "dbt"):
        assert piece in ctx["target_tools"]
        assert piece in ctx["missing"]
    assert "for transformations" not in ctx["target_tools"]
    assert "SQL" in ctx["target_tools"] and ctx["target_tools"][-1] == "SQL"


def test_plain_labels_untouched():
    ctx = {"target_tools": ["Git-based development", "ETL/ELT", "CI/CD"], "present": [], "missing": []}
    assert t._split_compound_labels(ctx, "Git-based development, ETL/ELT and CI/CD.", BASE) == []
    assert ctx["target_tools"] == ["Git-based development", "ETL/ELT", "CI/CD"]


def test_anchors_single_job_tools_only():
    anchors = t._anchored_tools(BASE, {"target_tools": ["Kubernetes", "Snowflake", "Python"]})
    assert anchors.get("Kubernetes") == {"acme"}
    assert "Snowflake" not in anchors          # used at two jobs: everyday kit
    assert "Python" not in anchors


def test_coverage_anchors_exempt_jd_acronym():
    ctx = {"target_tools": ["Kubernetes", "EMR"], "target_cloud": "None"}
    anchors = t._coverage_anchors(BASE, ctx, BASE, EVANS_JD)
    assert "Kubernetes" in anchors
    assert "EMR" not in anchors                # the JD says EMR: ambiguous vocabulary


def test_page_fit_full_size_scores_ten():
    pts, why = t._page_fit_points(BASE, BASE)
    assert pts == 10 and why == ""


def test_page_fit_penalises_a_third_page():
    long = BASE + "\n" + "\n".join(f"• Filler bullet number {i} about routine pipeline work here." for i in range(160))
    pts, why = t._page_fit_points(long, BASE)
    assert pts <= 3 and why


def test_plain_label_filler_cut():
    ctx = {"target_tools": ["dbt for transformations", "Infrastructure as Code", "SQL"],
           "present": [], "missing": ["dbt for transformations"], "bridge_only": [], "equivalent": []}
    log = t._split_compound_labels(ctx, "dbt for transformations and Infrastructure as Code, plus SQL.", BASE)
    assert log == ["dbt for transformations -> dbt"]
    assert ctx["target_tools"] == ["dbt", "Infrastructure as Code", "SQL"]
    assert "dbt" in ctx["missing"] and "dbt for transformations" not in ctx["missing"]


def test_symbol_edged_names_are_evidenced():
    # \b cannot sit next to "+", "#" or "." — KDB+ in three bullets scored as missing (Zealogics)
    body = "EXPERIENCE:\nX @ Y | Z\n• Migrated KDB+, C# services and .NET jobs; C++ tooling stayed."
    assert t._unevidenced(["KDB+", "C#", ".NET", "C++"], body) == []
    assert t._unevidenced(["KDB"], "EXPERIENCE:\nX @ Y | Z\n• Used KDBX only.") == ["KDB"]
    present, missing = t._covered_anywhere(["KDB+", "Python"], "• Databases: Snowflake, KDB+, Oracle\n• Built Python jobs.")
    assert present == ["KDB+", "Python"] and missing == []


def test_headline_mirrors_same_family_but_never_inflates():
    base = ("Jane Doe — Senior Data Engineer\n\nEXPERIENCE:\nSenior Data Engineer @ Acme | 2021 - Present\n"
            "• Leading a staff of analysts through a platform migration.\n")
    def head(jt):
        return t._headline_hybrid("Jane Doe — " + jt + "\nrest", base, jt, []).splitlines()[0].split("—")[1].strip()
    assert head("ETL Data Engineer") == "Senior ETL Data Engineer"    # JD words + the base's level
    assert head("Data Engineer") == "Senior Data Engineer"            # never downgraded
    assert head("Senior ETL Data Engineer") == "Senior ETL Data Engineer"   # Senior is a real base title
    assert head("Lead Data Engineer") == "Senior Data Engineer"        # "leading" in a bullet is not a title
    assert head("Staff Data Engineer") == "Senior Data Engineer"       # "staff of analysts" is not a title
    assert head("Software Engineer") == "Senior Data Engineer"        # other family: real title


def test_headline_level_not_invented_for_plain_base():
    base = "Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built pipelines.\n"
    out = t._headline_hybrid("Jane Doe — Senior Data Engineer\nrest", base, "Senior Data Engineer", [])
    assert out.splitlines()[0].split("—")[1].strip() == "Data Engineer"


def test_role_family_data_plus_engineer_beats_generic_keywords():
    assert t._role_family("Senior Data Infrastructure Engineer") == "Data Engineer"
    assert t._role_family("Senior Cloud Data Engineer") == "Data Engineer"
    assert t._role_family("Sr. Cloud Engineer") == "Cloud"
    assert t._role_family("Data Analyst") == "Data Analyst"
    base = ("Jane Doe — Senior Data Engineer\n\nEXPERIENCE:\nSenior Data Engineer @ Acme | 2021 - Present\n• Built pipelines.\n")
    out = t._headline_hybrid("Jane Doe — Senior Data Infrastructure Engineer\nrest", base, "Senior Data Infrastructure Engineer", [])
    assert out.splitlines()[0].split("—")[1].strip() == "Senior Data Infrastructure Engineer"


def test_paraphrased_label_keeps_its_literal_part():
    jd = "Deep experience with high-performance software in a distributed, cloud-scale environment. Demonstrated experience optimizing database performance."
    assert t._literal_subspan("distributed systems", jd) == "distributed"
    assert t._literal_subspan("database performance optimization", jd) == "database performance"
    assert t._literal_subspan("Infrastructure as Code", jd) == ""
    ctx = {"target_tools": ["distributed systems", "SQL"], "present": [], "missing": ["distributed systems"],
           "bridge_only": [], "equivalent": []}
    t._split_compound_labels(ctx, jd + " Strong SQL skills.", BASE)
    assert ctx["target_tools"] == ["distributed", "SQL"]


def test_summary_voice_and_density_flags():
    text = ("Jane Doe — Senior Data Engineer\n\nSUMMARY:\nSenior Data Engineer with 6 years.\n"
            "Builds CDC connectors for relational databases.\nPartner with product teams on connector design.\n"
            "Strengthens CDC infrastructure with checkpointing.\n"
            "Designs Kafka, Debezium, Snowflake, Airflow and dbt pipelines with schema drift handling.\n\n"
            "EXPERIENCE:\nSenior Data Engineer @ Acme | 2021 - Present\n• Built pipelines.\n")
    flags = t._qa_flags(text, {}, jd_tools=["Kafka", "Debezium", "Snowflake", "Airflow", "dbt", "schema drift"])
    msgs = " || ".join(flags.values())
    assert "third-person verb like 'Builds'" in msgs          # the lone "Partner" line is flagged
    assert msgs.count("Summary voice") == 1
    assert "Too many JD terms in one line (6)" in msgs
    assert t._verb_form("Builds") == "third-person" and t._verb_form("Led") == "past-tense" and t._verb_form("Partner") == "base-form"


def test_keyword_pattern_tolerates_forms_and_hyphens():
    body = ("EXPERIENCE:\nX @ Y | Z\n• Modeled the lakehouse and set up alerts on freshness; "
            "wrote infrastructure as code in Terraform; near real time loads; ran Kubernetes.")
    assert t._unevidenced(["lakehouses", "alerting", "Infrastructure-as-Code", "near-real-time", "Kubernetes"], body) == []
    assert t._unevidenced(["AWS"], "EXPERIENCE:\nX @ Y | Z\n• Said aw shucks.") == ["AWS"]
    assert t._unevidenced(["Redis"], "EXPERIENCE:\nX @ Y | Z\n• Used Redis caches.") == []
