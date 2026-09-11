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


def test_headline_keeps_jd_title_verbatim_in_same_family():
    # review 2026-09-10: "Data Architect" became "Senior Data" because the level
    # words were stripped and re-added; same family now keeps the JD title as is
    base = ("Jane Doe — Senior Data Engineer\n\nEXPERIENCE:\nSenior Data Engineer @ Acme | 2021 - Present\n"
            "• Leading a staff of analysts through a platform migration.\n")
    def head(jt):
        return t._headline_hybrid("Jane Doe — " + jt + "\nrest", base, jt, []).splitlines()[0].split("—")[1].strip()
    assert head("ETL Data Engineer") == "ETL Data Engineer"
    assert head("Data Architect") == "Data Architect"
    assert head("Lead Data Engineer") == "Lead Data Engineer"
    assert head("Software Engineer") == "Senior Data Engineer"        # other family: real title


def test_headline_plain_base_keeps_jd_title():
    base = "Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built pipelines.\n"
    out = t._headline_hybrid("Jane Doe — Senior Data Engineer\nrest", base, "Senior Data Engineer", [])
    assert out.splitlines()[0].split("—")[1].strip() == "Senior Data Engineer"


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
    assert "Summary voice" not in msgs                         # voice forcing removed (broke grammar)
    assert "Too many JD terms in one line (6)" in msgs
    assert t._verb_form("Builds") == "third-person" and t._verb_form("Led") == "past-tense" and t._verb_form("Partner") == "base-form"


def test_keyword_pattern_tolerates_forms_and_hyphens():
    body = ("EXPERIENCE:\nX @ Y | Z\n• Modeled the lakehouse and set up alerts on freshness; "
            "wrote infrastructure as code in Terraform; near real time loads; ran Kubernetes.")
    assert t._unevidenced(["lakehouses", "alerting", "Infrastructure-as-Code", "near-real-time", "Kubernetes"], body) == []
    assert t._unevidenced(["AWS"], "EXPERIENCE:\nX @ Y | Z\n• Said aw shucks.") == ["AWS"]
    assert t._unevidenced(["Redis"], "EXPERIENCE:\nX @ Y | Z\n• Used Redis caches.") == []


def test_figure_cap_keeps_jd_backed_bullets():
    text = ("Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Built Snowflake models cutting cost by 40%.\n"
            "• Wrote docs for 8 teams.\n"
            "• Tuned Airflow DAGs, saving $100K a year.\n"
            "• Ran Kafka streams at sub-100ms latency.\n"
            "• Cleaned 15+ vendor feeds.\n")
    plan = t._figure_cap_plan(text, ["Snowflake", "Airflow", "Kafka"], 3)
    lines = text.split("\n")
    gone = {lines[i].strip() for i in plan}
    assert gone == {"• Wrote docs for 8 teams.", "• Cleaned 15+ vendor feeds."}   # the two with no JD tool
    assert t._figure_cap_plan(text, ["Snowflake"], 5) == {}


def test_number_audit_floor_waives_drops_in_covered_jobs():
    base = ("Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Built Snowflake models cutting cost by 40%.\n• Tuned Airflow DAGs saving $100K.\n"
            "• Wrote docs for 8 teams across the org.\n")
    tailored = ("Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
                "• Built Snowflake models cutting cost by 40%.\n• Tuned Airflow DAGs saving $100K.\n"
                "• Wrote docs for every team across the org.\n")
    inv, dropped, removed = t._number_audit(tailored, base, "")
    assert not inv and (dropped or removed)                       # strict read: the 8 is gone
    inv, dropped, removed = t._number_audit(tailored, base, "", floor=2)
    assert not inv and not dropped and not removed                # job still has 2 figures: a choice
    one = tailored.replace("saving $100K", "saving money")
    inv, dropped, removed = t._number_audit(one, base, "", floor=2)
    assert dropped or removed                                     # below the floor: reported again


# ── contact line: phone | email, nothing else ────────────────────────────────

def test_contact_line_drops_city_state():
    out = t._contact_only("Jane Doe — Data Engineer\n(347) 695-1020 | jane@example.com | Minneapolis, MN\n\nSUMMARY:\n• x")
    assert out.splitlines()[1] == "(347) 695-1020 | jane@example.com"


def test_contact_line_reorders_and_strips_links():
    out = t._contact_only("Jane Doe — Data Engineer\nAustin, TX | jane@example.com | 347-695-1020 | linkedin.com/in/jane\n\nSUMMARY:")
    assert out.splitlines()[1] == "347-695-1020 | jane@example.com"


def test_contact_line_untouched_when_already_clean():
    src = "Jane Doe — Data Engineer\n(347) 695-1020 | jane@example.com\n\nSUMMARY:\n• x"
    assert t._contact_only(src) == src


def test_contact_line_left_alone_when_incomplete():
    # nothing to rebuild from: lint reports the missing field instead
    src = "Jane Doe — Data Engineer\njane@example.com | Austin, TX\n\nSUMMARY:"
    assert t._contact_only(src) == src

