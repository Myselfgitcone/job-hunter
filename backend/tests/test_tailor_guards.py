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
    # words were stripped and re-added; same family keeps the JD title's ROLE
    # words as is. 2026-09-16: a LEVEL word stays only when the base's titles
    # carry it or tenure earns it (Senior 5y, Lead/Staff 7y, Principal 10y).
    base = ("Jane Doe — Senior Data Engineer\n\nEXPERIENCE:\nSenior Data Engineer @ Acme | 2018 - Present\n"
            "• Leading a staff of analysts through a platform migration.\n")   # 8 years
    def head(jt, b=base):
        return t._headline_hybrid("Jane Doe — " + jt + "\nrest", b, jt, []).splitlines()[0].split("—")[1].strip()
    assert head("ETL Data Engineer") == "ETL Data Engineer"
    assert head("Data Architect") == "Data Architect"
    assert head("Lead Data Engineer") == "Lead Data Engineer"          # 8 years earns Lead
    assert head("Principal Data Engineer") == "Data Engineer"          # 8 years does not earn Principal
    assert head("Software Engineer") == "Senior Data Engineer"         # other family: real title
    two = ("Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2024 - Present\n• Built pipelines.\n")
    assert head("Senior Data Engineer", two) == "Data Engineer"        # 2 years: level word dropped
    assert head("Data Engineering Manager", two) == "Data Engineering"  # never earned by tenure alone


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


# ── contact line: phone | email, plus the links the base itself lists ──────

def test_contact_line_drops_city_state():
    out = t._contact_only("Jane Doe — Data Engineer\n(347) 695-1020 | jane@example.com | Minneapolis, MN\n\nSUMMARY:\n• x")
    assert out.splitlines()[1] == "(347) 695-1020 | jane@example.com"


def test_contact_line_keeps_links_the_base_has():
    base = "Jane Doe — Data Engineer\njane@example.com | 347-695-1020 | Austin, TX | linkedin.com/in/jane | github.com/jane\n\nEXPERIENCE:"
    out = t._contact_only("Jane Doe — Data Engineer\n347-695-1020 | jane@example.com | Austin, TX\n\nSUMMARY:", base)
    assert out.splitlines()[1] == "347-695-1020 | jane@example.com | linkedin.com/in/jane | github.com/jane"


def test_contact_line_never_adds_a_link_the_base_lacks():
    base = "Jane Doe — Data Engineer\n347-695-1020 | jane@example.com\n\nEXPERIENCE:"
    out = t._contact_only("Jane Doe — Data Engineer\n347-695-1020 | jane@example.com | linkedin.com/in/invented\n\nSUMMARY:", base)
    assert out.splitlines()[1] == "347-695-1020 | jane@example.com"


def test_contact_line_untouched_when_already_clean():
    src = "Jane Doe — Data Engineer\n(347) 695-1020 | jane@example.com\n\nSUMMARY:\n• x"
    assert t._contact_only(src) == src


def test_contact_line_left_alone_when_incomplete():
    # nothing to rebuild from: lint reports the missing field instead
    src = "Jane Doe — Data Engineer\njane@example.com | Austin, TX\n\nSUMMARY:"
    assert t._contact_only(src) == src


# \u2500\u2500 QA flags: summary length, JD copy, cloud mix \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

_JD = ("Own document parsing, chunking, metadata extraction, and embedding generation stages "
       "for the retrieval platform. Build pipelines on Snowflake.")


def test_qa_flags_summary_over_80_words():
    long = "\u2022 " + " ".join(["word"] * 30) + "."
    text = "Jane Doe \u2014 X\n\nSUMMARY:\n" + "\n".join([long] * 4) + "\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n\u2022 Built pipelines.\n"
    msgs = " || ".join(t._qa_flags(text, {}).values())
    assert f"limit {t._SUMMARY_MAX_WORDS}" in msgs
    short = "Jane Doe \u2014 X\n\nSUMMARY:\n\u2022 Builds pipelines on Snowflake for finance teams.\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n\u2022 Built pipelines.\n"
    assert "limit " not in " || ".join(t._qa_flags(short, {}).values())


def test_qa_flags_jd_copied_word_for_word():
    text = ("Jane Doe \u2014 X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "\u2022 Owned document parsing, chunking, metadata extraction, and embedding generation stages with Pinecone.\n"
            "\u2022 Built 14 Snowflake feeds for the retrieval platform over two quarters.\n")
    flags = t._qa_flags(text, {}, jd_text=_JD)
    lines = text.split("\n")
    copied = [i for i, m in flags.items() if "Copied from the JD" in m]
    assert len(copied) == 1 and "document parsing" in lines[copied[0]]


def test_qa_flags_second_cloud_in_a_one_cloud_job():
    base = ("Jane Doe \u2014 X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n\u2022 Built pipelines on AWS S3 and EMR.\n")
    text = ("Jane Doe \u2014 X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "\u2022 Architected ELT on Databricks, Delta Lake, Microsoft Azure, and Lambda cutting incidents.\n"
            "\u2022 Built Spark jobs on EMR reading from S3.\n")
    flags = t._qa_flags(text, {}, base_resume=base)
    msgs = list(flags.values())
    assert len(msgs) == 1 and "ran on AWS" in msgs[0] and "Azure" in msgs[0]
    # job 1 may carry the target cloud under an active swap
    assert not t._qa_flags(text, {}, base_resume=base, target_cloud="Azure")


# ── invented figures: a generated bullet may carry no number the base lacks ──

def test_generated_bullet_any_figure_is_bad():
    # 2026-09-16: bare counts up to 50 used to pass ("14 feeds, never round")
    assert t._bad_figures("Owned migration of 14 Kafka CDC feeds over two quarters") == {"14"}
    assert t._bad_figures("Prototyped a Snowflake landing layer for the Kafka CDC feeds") == set()


def test_number_audit_flags_small_invented_count_but_not_years():
    base = ("Jane Doe — Data Engineer\n\nSUMMARY:\nData engineer with 6+ years.\n\n"
            "EXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Snowflake models cutting cost by 40%.\n")
    tailored = ("Jane Doe — Data Engineer\n\nSUMMARY:\nData engineer with 6 years on Snowflake.\n\n"
                "EXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Snowflake models cutting cost by 40%.\n"
                "• Owned migration of 14 Kafka feeds to Snowflake over two quarters.\n")
    inv, _, _ = t._number_audit(tailored, base, "")
    figs = set().union(*[f for _, f in inv]) if inv else set()
    assert "14" in figs                      # the invented count is caught
    assert not any(f.endswith("y") for f in figs)   # "6 years" is tenure, not a figure
    assert "6y" in t._num_tokens("6+ years") and "6y" in t._num_tokens("6 years")


def test_proof_score_penalises_invented_figure_not_missing_one():
    base = ("Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Built Kafka pipelines on Databricks.\n")
    honest = "Prototyped a Snowflake landing layer for the Kafka feeds behind pricing marts for analytics teams."
    faked = "Owned migration of 14 Kafka feeds to Snowflake over two quarters for analytics teams."
    def score(bullet):
        text = ("Jane Doe — Data Engineer\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
                "• Built Kafka pipelines on Databricks.\n• " + bullet + "\n")
        ctx = {"target_tools": ["Snowflake", "Kafka"], "responsibilities": [], "job_title": "Data Engineer"}
        return t._code_score(text, base, "Snowflake and Kafka.", ctx, [(0, "Snowflake", bullet)])["points"]["proof"]
    assert score(honest) == 10
    assert score(faked) < score(honest)


# ── bullet caps: one number per job, coverage slot survives the final trim ──

def test_caps_match_prompt_ladder():
    assert (t._job_cap(0), t._job_cap(1), t._job_cap(2), t._job_cap(3)) == (11, 7, 5, 3)


def test_final_cap_keeps_coverage_bullet_in_its_bonus_slot():
    base = "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Kafka pipelines.\n"
    cov = "Integrated Great Expectations checks into the Kafka ingestion for analytics teams."
    bullets = [f"• Bullet number {i} about routine Kafka pipeline work for the team." for i in range(11)]
    text = base + "\n".join(bullets[1:]) + "\n• " + cov + "\n"
    # 12 bullets in Job 1: writer's 11 + the coverage bullet
    notes: list = []
    strict = t._enforce_caps(text, base, notes)                       # cap 11: coverage bullet (last, no figure) dies
    assert cov not in strict
    final = t._enforce_caps(text, base, [], bonus=1, protect={cov})   # cap 12 + protected: it survives
    assert cov in final and len(t._job_bullet_lines(final)[0][1]) == 12
    over = text + "• One more bullet past even the bonus slot for Kafka work.\n"
    final2 = t._enforce_caps(over, base, [], bonus=1, protect={cov})
    assert cov in final2 and len(t._job_bullet_lines(final2)[0][1]) == 12   # over the bonus: a non-protected one goes


# ── bullet length: one rule (_BULLET_MAX), every check reads it ──────────────

def test_bullet_length_thresholds_share_one_constant():
    assert t._BULLET_MAX == 26 and t._BULLET_SPLIT == 32
    assert t._WEAVE_MAX_WORDS == t._BULLET_MAX and t._SPLIT_MAX_WORDS == t._BULLET_SPLIT
    import inspect
    sig = inspect.signature(t._compress_long_bullets)
    assert sig.parameters["max_words"].default == t._BULLET_MAX
    # the prompt states the same ceiling the code enforces
    assert f"never past {t._BULLET_MAX}" in t.TAILOR_SYSTEM


def test_score_penalises_over_max_not_over_35():
    base = "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Kafka pipelines.\n"
    mk = lambda n: "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• " + " ".join(["word"] * n) + "\n"
    ctx = {"target_tools": [], "responsibilities": [], "job_title": "X"}
    r28 = t._code_score(mk(28), base, "", ctx, [])["points"]["readability"]
    r26 = t._code_score(mk(26), base, "", ctx, [])["points"]["readability"]
    assert r28 < r26


# ── summary: 4 bullets, 5 at most, 80 words; one rule for prompt and code ──

def test_summary_rule_is_one_constant():
    assert t._SUMMARY_MAX_WORDS == 110 and t._SUMMARY_MAX_LINES == 5
    assert "never 6" in t.TAILOR_SYSTEM and "three sentences" not in t.TAILOR_SYSTEM
    import inspect
    assert inspect.signature(t._compress_long_bullets).parameters["summary_max"].default == t._SUMMARY_MAX_WORDS


def test_summary_sixth_bullet_dropped_in_code():
    head = "Jane Doe — X\n\nSUMMARY:\n"
    tail = "\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built pipelines.\n"
    six = head + "\n".join(f"• Summary line {i} about real work." for i in range(6)) + tail
    notes: list = []
    out = t._cap_summary_lines(six, notes)
    assert len(t._summary_lines(out)) == 5 and "Summary line 5" not in out and "Summary line 0" in out
    assert notes and "summary guard" in notes[0]
    four = head + "\n".join(f"• Summary line {i}." for i in range(4)) + tail
    assert t._cap_summary_lines(four, []) == four


# ── prompt v2: rendered from the engine constants, legacy kept behind a flag ──

def test_tailor_prompt_v2_is_default_and_renders_constants():
    assert t.TAILOR_SYSTEM is t._TAILOR_SYSTEM_V2
    s = t.TAILOR_SYSTEM
    assert f"never past {t._BULLET_MAX}" in s
    assert f"Job 1 \u2264 {t._JOB_BULLET_CAPS[0]}" in s and f"Job 4+ \u2264 {t._JOB_CAP_OLDER}" in s
    assert f"at least {int(round(t._COVERAGE_TARGET * 100))}%" in s
    assert f"90\u2013{t._SUMMARY_MAX_WORDS} words" in s
    assert "{" not in s and "}" not in s          # every placeholder rendered
    assert len(s.split()) < 0.7 * len(t.TAILOR_SYSTEM_LEGACY.split())
    for rule in ("TENURE CEILING", "IMPACT LADDER", "VERB REGISTER", "SECURITY CLEARANCE",
                 "Ruby on Rails", "Purview", "one observability bullet covers ONE"):
        assert rule in s, rule


# ── verbs: filler is a cliche; Maintained/Managed are scope verbs, not clichés ──

def test_scope_verbs_are_not_cliches_but_are_flagged_in_impact_slots():
    assert t._CLICHE_RE.match("Responsible for nightly loads")
    assert t._CLICHE_RE.match("Utilized Spark for ETL")
    assert not t._CLICHE_RE.match("Maintained the nightly Airflow DAGs")
    assert not t._CLICHE_RE.match("Collaborated with analysts on the semantic layer")
    assert t._WEAK_VERB_RE.match("Maintained the nightly Airflow DAGs")
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Maintained the nightly Airflow DAGs for finance marts.\n"        # slot 1: flagged
            "• Built Kafka ingestion for pricing feeds.\n"
            "• Designed the Snowflake landing layer for analytics teams.\n"
            "• Managed the on-call rotation for the ingestion service.\n"       # slot 4: fine
            "• Responsible for documentation of the data marts.\n")            # cliché anywhere
    flags = t._qa_flags(text, {})
    lines = text.split("\n")
    by_text = {lines[i].strip(): m for i, m in flags.items()}
    assert "impact slot" in by_text["• Maintained the nightly Airflow DAGs for finance marts."]
    assert "• Managed the on-call rotation for the ingestion service." not in by_text
    assert "templated" in by_text["• Responsible for documentation of the data marts."]


def test_cliche_penalised_once_not_twice():
    base = "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Kafka pipelines.\n"
    mk = lambda b: "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• " + b + "\n"
    ctx = {"target_tools": [], "responsibilities": [], "job_title": "X"}
    clean = t._code_score(mk("Built Kafka pipelines for pricing feeds."), base, "", ctx, [])["points"]
    cliche = t._code_score(mk("Utilized Kafka pipelines for pricing feeds."), base, "", ctx, [])["points"]
    assert cliche["readability"] < clean["readability"]
    assert cliche["proof"] == clean["proof"]


def test_impact_slot_verbs_follow_tenure():
    two = "Jane Doe — X\n\nSUMMARY:\nData engineer with 2 years.\n\nEXPERIENCE:\nData Engineer @ Acme | 2024 - Present\n• Built pipelines.\n"
    twelve = two.replace("2 years", "12+ years")
    assert "Architected" not in t._ownership_verbs(two) and "Led" not in t._ownership_verbs(two)
    assert "Built" in t._ownership_verbs(two)
    assert "Architected" in t._ownership_verbs(twelve)
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2024 - Present\n"
            "• Maintained the nightly Airflow DAGs for finance marts.\n• Built Kafka ingestion.\n")
    msg = " || ".join(t._qa_flags(text, {}, base_resume=two).values())
    assert "impact slot" in msg and "Architected" not in msg and "Built" in msg


# ── tenure: job headers only, "Present" = this year, education years ignored ──

def test_tenure_from_job_headers_only():
    import datetime
    y = datetime.date.today().year
    base = ("Jane Doe — Data Engineer\n\nEXPERIENCE:\n"
            "Data Engineer @ Acme | Austin, TX Jan 2024 – Present\n• Built pipelines.\n"
            "Intern @ Beta | 2023 - 2023\n• Wrote SQL.\n\n"
            "EDUCATION:\nB.S. Computer Science, State University, 2015\n\n"
            "CERTIFICATIONS:\n• AWS Certified Data Analytics (2019)\n")
    assert t._tenure_years(base) == y - 2023          # not 2015 (education), not 0 ("Present")
    assert t._base_years_claim(base) == (None, y - 2023)
    assert t._base_years_claim("Data engineer with 6+ years.\n\nEXPERIENCE:\nX @ Y | 2024 - Present\n")[0] == "6+ years"
    assert t._page_budget(base) == 1                  # <= 3 years -> one page


# ── company key: the whole name, so "Bank of America" != "Bank of the West" ──

def test_company_key_uses_the_whole_name():
    assert t._company_key("Data Engineer @ Bank of America | Charlotte, NC Jan 2022 – Present") == "bank of america"
    assert t._company_key("Analyst @ Bank of the West | Phoenix 2019 – 2022") == "bank of the west"
    assert t._company_key("Engineer @ J.P. Morgan & Co. | NYC 2020 - 2021") == "j p morgan & co"
    assert t._company_key("Engineer @ Acme 2020 – 2021") == "acme"           # no pipe: cut at the date
    assert t._company_key("Data Engineer @ Bank of America | 2022 – Present") == \
           t._company_key("Data Engineer @ Bank of America | Charlotte, NC 2022 – Present")   # location-independent
    base = ("Jane Doe — X\n\nEXPERIENCE:\n"
            "Data Engineer @ Bank of America | Charlotte 2022 – Present\n• Built Kafka pipelines on AWS.\n"
            "Analyst @ Bank of the West | Phoenix 2019 – 2022\n• Wrote SSIS packages on Azure.\n")
    blocks = t._base_job_blocks(base)
    assert set(blocks) == {"bank of america", "bank of the west"}
    anchors = t._anchored_tools(base, {"target_tools": ["Kafka", "SSIS"]})
    assert anchors["Kafka"] == {"bank of america"} and anchors["SSIS"] == {"bank of the west"}
    clouds = {c: t._detect_cloud(b) for c, b in t._split_jobs(base)}
    assert clouds == {"bank of america": "AWS", "bank of the west": "Azure"}


# ── role families: software / ML / security / QA / PM titles, adjacency, unknown-vs-unknown ──

def test_role_families_cover_non_data_titles_and_adjacency():
    rf = t._role_family
    assert rf("Senior Software Engineer") == "Software Engineer"
    assert rf("Backend Engineer") == "Software Engineer"
    assert rf("Machine Learning Engineer") == "ML" and rf("Data Scientist") == "ML"
    assert rf("Cloud Security Engineer") == "Security"
    assert rf("SDET") == "QA" and rf("Product Manager") == "Product"
    assert rf("Analytics Engineer") == "Data Engineer"
    assert rf("Senior Data Infrastructure Engineer") == "Data Engineer"   # data+engineer rule still first
    sf = t._same_family
    assert sf("Data Engineer", "Analytics Engineer")
    assert sf("Data Engineer", "BI Developer") and sf("Data Analyst", "BI Developer")
    assert sf("Data Engineer", "Machine Learning Engineer")
    assert sf("Cloud Engineer", "DevOps Engineer")
    assert sf("Software Engineer", "Backend Engineer")
    assert not sf("Software Engineer", "Product Manager")
    assert not sf("Data Engineer", "Software Engineer")                   # not adjacent: base title
    assert sf("Epic Cogito Analyst", "Clinical Reporting Analyst")        # both unknown, same role noun
    assert not sf("Epic Cogito Analyst", "Anaplan Model Builder")         # both unknown, different noun
    base = ("Jane Doe — Software Engineer\n\nEXPERIENCE:\nSoftware Engineer @ Acme | 2019 - Present\n• Built APIs.\n")
    out = t._headline_hybrid("Jane Doe — Backend Engineer\nrest", base, "Backend Engineer", [])
    assert out.splitlines()[0].split("—")[1].strip() == "Backend Engineer"
    out = t._headline_hybrid("Jane Doe — Product Manager\nrest", base, "Product Manager", [])
    assert out.splitlines()[0].split("—")[1].strip() == "Software Engineer"


# ── analyze: an empty analysis is a failure, not a silent empty context ──────

def test_analysis_ok_requires_three_tools():
    assert not t._analysis_ok({})
    assert not t._analysis_ok({"target_tools": []})
    assert not t._analysis_ok({"target_tools": ["Kafka", ""]})
    assert not t._analysis_ok("not a dict")
    assert t._analysis_ok({"target_tools": ["Kafka", "Spark", "Airflow"]})


def test_release_year_guard_spares_the_base_resumes_own_claim():
    base = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2017 - 2019\n• Scheduled loads with Airflow.\n"
            "Analyst @ Beta | 2014 - 2016\n• Wrote SQL reports.\n")
    ctx = {"target_tools": ["Airflow", "dbt"], "target_cloud": "None", "bridge_only": [],
           "tool_facts": {"Airflow": {"ga_year": 2019, "platforms": [], "category": "orchestrator"},
                          "dbt": {"ga_year": 2020, "platforms": [], "category": "other"}}}
    # Airflow at a 2017-2019 job with a guessed GA of 2019: the base names it there -> never a leak
    tailored = base.replace("Scheduled loads with Airflow.", "Scheduled loads with Airflow and modeled marts in dbt.")
    leaks = t._scope_leaks(tailored, base, ctx)
    flagged = {tool for ts in leaks.values() for tool in ts}
    assert "Airflow" not in flagged
    assert "Dbt" not in flagged                       # 2020 vs end 2019: inside the one-year slack
    # dbt written into the 2014-2016 job: the base never had it there and 2020 is well past 2016
    tailored2 = base.replace("Wrote SQL reports.", "Wrote SQL reports and dbt models.")
    flagged2 = {tool for ts in t._scope_leaks(tailored2, base, ctx).values() for tool in ts}
    assert "Dbt" in flagged2


# ── A/B follow-ups 2026-09-16: topic leak, bridge lead, duty in tech line, fit gate, blank row ──

def test_bridge_bullet_leaves_the_impact_slots():
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Prototyped cross-cloud data aggregation for procurement analytics teams.\n"
            "• Built Kafka ingestion for pricing feeds.\n"
            "• Designed the Snowflake landing layer.\n"
            "• Maintained the nightly Airflow DAGs.\n"
            "Technologies Used: Kafka, Snowflake\n")
    notes: list = []
    out = t._demote_bridge_bullets(text, notes)
    bl = [out.split("\n")[i] for _, b in t._job_bullet_lines(out) for i in b]
    assert bl[0].startswith("• Built") and bl[-1].startswith("• Prototyped") and len(bl) == 4
    assert "Technologies Used: Kafka, Snowflake" in out and notes
    assert t._demote_bridge_bullets(out, []) == out            # already placed: untouched


def test_tech_line_takes_tools_not_duties():
    assert t._looks_like_tool("dbt") and t._looks_like_tool("Great Expectations") and t._looks_like_tool("data governance")
    assert not t._looks_like_tool("Building high-quality ETL/ELT pipelines")
    assert not t._looks_like_tool("translate finance pain points into self-serve data solutions")
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Kafka ingestion.\n"
            "Technologies Used: Kafka\n")
    out, n = t._insert_skill_bullets(text, {0: [("dbt + Building high-quality ETL/ELT pipelines",
                                                 "Extended the Kafka ingestion with dbt models for finance teams.")]})
    assert n == 1 and "Technologies Used: Kafka, dbt" in out and "high-quality" not in out.split("Technologies Used")[1]


def test_emptied_skills_row_leaves_no_blank_line():
    text = "Jane Doe — X\n\nSKILLS:\n• Languages: Python\n• Niche: ArcGIS\n• Cloud: AWS\n\nEXPERIENCE:\nX @ Y | Z\n• Built Python jobs on AWS.\n"
    out, removed = t._rewrite_skill_lines(text, {"arcgis"})
    assert removed == ["ArcGIS"]
    assert "• Languages: Python\n• Cloud: AWS\n\nEXPERIENCE:" in out


def test_weave_keeps_topic_helper():
    old = "Built Airflow DAGs orchestrating commodity pricing and logistics feeds for procurement analysts."
    drift = "Integrated PostgreSQL analytical views to surface healthcare claims data feeds for risk analytics."
    same = "Built Airflow DAGs orchestrating commodity pricing and logistics feeds in PostgreSQL for procurement analysts."
    ow = t._content_words(old)
    assert len(ow & t._content_words(drift)) / len(ow) < 0.4
    assert len(ow & t._content_words(same)) / len(ow) >= 0.4


def test_duplicate_bullets_collapse_keeping_the_richer_one():
    text = ("Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n"
            "• Mentored data engineers on pipeline design patterns, data quality frameworks, and Spark optimization techniques.\n"
            "• Built Kafka ingestion for pricing feeds.\n"
            "• Coached data engineers on pipeline design patterns, data quality frameworks, Spark optimization techniques, and code review.\n"
            "Technologies Used: Kafka, Spark\n")
    notes: list = []
    out = t._dedupe_bullets(text, notes)
    bl = [out.split("\n")[i] for _, b in t._job_bullet_lines(out) for i in b]
    assert len(bl) == 2 and any("code review" in b for b in bl) and any("Kafka" in b for b in bl)
    assert notes and "duplicate guard" in notes[0]
    distinct = text.replace("Coached data engineers on pipeline design patterns, data quality frameworks, Spark optimization techniques, and code review.",
                            "Ran the weekly code review rotation for the ingestion team.")
    assert t._dedupe_bullets(distinct, []) == distinct


# ── B+ -> A: vague summary tails, 3x phrase echo, missing-numbers nudge ──────

def test_summary_vague_tail_is_flagged():
    text = ("Jane Doe — X\n\nSUMMARY:\n• Senior Data Engineer with 5 years across Snowflake and Airflow, plus additional cloud data warehouses and processing frameworks.\n"
            "• Designs data models for finance teams using slowly changing dimensions.\n\n"
            "EXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built pipelines.\n")
    flags = t._qa_flags(text, {})
    msgs = list(flags.values())
    assert len(msgs) == 1 and "vague tail" in msgs[0] and "plus additional" in msgs[0]
    assert t._VAGUE_TAIL_RE.search("Built Kafka, Spark and other tools for the team")
    assert not t._VAGUE_TAIL_RE.search("Built Kafka and Spark pipelines for the finance team.")


def test_two_word_phrase_echo_fires_at_three():
    bullets = "\n".join(f"• Built commodity pricing feed number {i} on Spark for analysts." for i in range(3))
    text = "Jane Doe — X\n\nSUMMARY:\n• Data engineer.\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n" + bullets + "\n"
    flags = t._overused_phrases(text, "A JD about Spark.", ["Spark"])
    assert any("commodity pricing" in ps for ps in flags.values())          # 3 uses, JD never says it
    assert not any("commodity pricing" in ps for ps in t._overused_phrases(text, "commodity pricing " * 3, ["Spark"]).values())


def test_missing_numbers_nudge_when_base_has_none():
    base = "Jane Doe — X\n\nEXPERIENCE:\nData Engineer @ Acme | 2021 - Present\n• Built Kafka pipelines for finance.\n"
    ctx = {"target_tools": ["Kafka"], "responsibilities": [], "job_title": "X"}
    fixes = t._code_score(base, base, "Kafka", ctx, [])["top_fixes"]
    assert fixes and fixes[0].startswith("Your base resume carries no numbers")
    with_fig = base.replace("for finance.", "for finance, cutting load time 40%.")
    assert not any(f.startswith("Your base resume carries no numbers") for f in t._code_score(with_fig, with_fig, "Kafka", ctx, [])["top_fixes"])
