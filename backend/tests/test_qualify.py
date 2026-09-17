"""Hybrid qualify: the four code-decided criteria and the model fallback.
No model calls: `chat` is patched."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import qualify as q  # noqa: E402

PROFILE = {
    "visa_status": "F1 OPT",
    "location": "USA / Remote",
    "experience": [
        {"role": "Senior Data Engineer", "company": "Cargill", "start_date": "Sep 2024", "end_date": "Present", "years": 2.0},
        {"role": "Data Engineer", "company": "Molina", "start_date": "Jan 2021", "end_date": "Jul 2022", "years": 1.5},
        {"role": "Data Engineer", "company": "JPMC", "start_date": "Dec 2018", "end_date": "Dec 2020", "years": 2.0},
    ],
    "skills": ["Python", "SQL", "Spark", "PySpark", "Databricks", "Airflow", "dbt", "Snowflake", "Kafka", "AWS", "S3", "Redshift", "Terraform"],
}
JD_OK = ("Requirements:\n- 4+ years building data pipelines\n- Strong Python and SQL\n- Experience with Spark, Airflow and dbt\n"
         "- Snowflake or Redshift\nWe sponsor visas. Remote within the US.")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_code_decides_experience_sponsorship_location_seniority():
    years = q._candidate_years(PROFILE)
    assert years == 5.5
    assert q._experience_check(JD_OK, years, None) == (True, "5.5 years vs 4+ required")
    ok, note = q._experience_check("Requires 10+ years of experience.", years, None)
    assert not ok and "10+" in note
    ok, _ = q._experience_check("No years stated.", None, None)
    assert ok                                                      # unknown never fails
    assert q._sponsorship_check(JD_OK, PROFILE, None)[0]
    ok, note = q._sponsorship_check("Great team. Unfortunately we are unable to sponsor visas at this time.", PROFILE, None)
    assert not ok and "sponsorship" in note.lower()
    ok, note = q._sponsorship_check("Must hold an active Secret clearance.", PROFILE, None)
    assert not ok and "clearance" in note.lower()
    citizen = dict(PROFILE, visa_status="US Citizen")
    assert q._sponsorship_check("No visa sponsorship.", citizen, None)[0]           # wall waived
    assert not q._sponsorship_check("Active TS/SCI clearance required.", citizen, None)[0]
    assert not q._sponsorship_check("Nice job.", PROFILE, {"visa_sponsorship": False})[0]
    assert q._location_check("Remote - USA", "", PROFILE, {"country": "USA", "remote": True})[0]
    assert not q._location_check("Bengaluru, India", "", PROFILE, None)[0]
    assert not q._location_check("Toronto, ON", "", PROFILE, {"country": "Canada", "remote": False})[0]
    assert q._location_check("Remote", "", PROFILE, {"country": "", "remote": True})[0]
    assert q._seniority_check("Senior Data Engineer", 5.5, PROFILE)[0]
    assert not q._seniority_check("Principal Data Engineer", 5.5, PROFILE)[0]
    assert not q._seniority_check("Data Engineering Intern", 5.5, PROFILE)[0]
    assert not q._seniority_check("Data Engineer Intern", 1.5, PROFILE)[0]      # 1.5 years is past an internship
    assert q._seniority_check("Junior Data Engineer", 1.5, PROFILE)[0]
    assert not q._seniority_check("Junior Data Engineer", 5.5, PROFILE)[0]
    assert q._seniority_check("Staff Data Engineer", None, PROFILE)[0]          # unknown years: not failed
    assert q._seniority_check("Lead Data Engineer", 5.5, PROFILE)[0]             # 5 - 1 slack


def test_overlap_and_requirements_text():
    have, miss = q._skill_overlap(JD_OK, PROFILE)
    assert {"Airflow", "Spark", "dbt"} <= set(have)      # the extractor's product names, all in the profile
    assert not any(s in miss for s in ("Airflow", "Spark", "dbt"))
    txt = q._requirements_text(JD_OK + "\n\nBenefits\n401k, dental, PTO." * 3)
    assert "Strong Python" in txt


def test_qualify_job_combines_model_and_code(monkeypatch):
    async def fake_chat(**kw):
        assert "KEYWORD OVERLAP" in kw["user"] and "Airflow" in kw["user"]
        # the model wrongly lists Airflow (owned) as missing: code strikes it
        return ('{"job_category": {"pass": true, "note": "DE role"}, "must_have_missing": ["Airflow"], '
                '"nice_to_have_missing": ["Looker"], "summary": "Fits."}')
    monkeypatch.setattr(q, "chat", fake_chat)
    r = _run(q.qualify_job(PROFILE, "Senior Data Engineer", JD_OK, "Acme", "Remote - USA", "k", "google",
                           "google/gemini-2.5-flash", ["Data Engineer"], job_meta={"country": "USA", "remote": True}))
    assert r["qualified"] and r["score"] == 100 and set(r["criteria"]) == {
        "job_category", "experience", "skills_match", "sponsorship", "location", "seniority"}
    assert r["criteria"]["skills_match"]["pass"] and "Looker" in r["criteria"]["skills_match"]["note"]
    assert "overlap" in r and r["summary"] == "Fits."

    async def fake_chat_gap(**kw):
        return '{"job_category": {"pass": true, "note": "DE role"}, "must_have_missing": ["Go", "ClickHouse", "Rust"], "summary": "No."}'
    monkeypatch.setattr(q, "chat", fake_chat_gap)
    jd_go = JD_OK + "\nRequired: Go and ClickHouse in production.\nNice to have: Rust."
    r = _run(q.qualify_job(PROFILE, "Senior Data Engineer", jd_go, "Acme", "Remote - USA", "k", "google",
                           "google/gemini-2.5-flash", ["Data Engineer"]))
    note = r["criteria"]["skills_match"]["note"]
    assert not r["criteria"]["skills_match"]["pass"] and "Go, ClickHouse" in note
    assert "Rust" in note and "nice-to-have" in note          # named only under nice-to-have: demoted, not a gate
    # a must-have the posting never names is the model's invention: dropped
    r = _run(q.qualify_job(PROFILE, "Senior Data Engineer", JD_OK, "Acme", "Remote - USA", "k", "google",
                           "google/gemini-2.5-flash", ["Data Engineer"]))
    assert r["criteria"]["skills_match"]["pass"]
    monkeypatch.setattr(q, "chat", fake_chat)
    # a sponsorship wall below the 2,000-char line is now caught by code
    jd_wall = JD_OK + ("\nMore text. " * 200) + "\nWe are unable to sponsor visas."
    r2 = _run(q.qualify_job(PROFILE, "Senior Data Engineer", jd_wall, "Acme", "Remote - USA", "k", "google",
                            "google/gemini-2.5-flash", ["Data Engineer"]))
    assert not r2["qualified"] and not r2["criteria"]["sponsorship"]["pass"] and r2["score"] == 90


def test_confirm_required_alternatives_and_years():
    jd = "Requirements:\n- Proficiency in Go or Scala.\n- 5+ years of experience.\n- Trino in production.\nNice to have: Rust."
    keep, demoted = q._confirm_required(["Go", "5+ years of experience", "Trino", "Rust", "Haskell"], jd, ["Scala", "Python"])
    assert keep == ["Trino"]                     # Go: alternative Scala owned; years: not a skill; Rust: nice-to-have; Haskell: never named
    assert set(demoted) == {"Go", "Rust"}


def test_hard_gates_and_weighted_score(monkeypatch):
    async def fake_chat(**kw):
        return '{"job_category": {"pass": true, "note": "DE"}, "must_have_missing": ["Spark", "Scala"], "summary": "gaps"}'
    monkeypatch.setattr(q, "chat", fake_chat)
    junior = dict(PROFILE, experience=[{"role": "Data Engineer", "company": "X", "start_date": "Mar 2025", "end_date": "Present"}])
    r = _run(q.qualify_job(junior, "Senior Data Engineer", "Requires 5+ years. Spark and Scala required.", "Acme", "Remote - USA",
                           "k", "google", "google/gemini-2.5-flash", ["Data Engineer"]))
    # skills, experience and seniority fail: 30 + 10 + 10 = 50, and two hard gates are down
    assert r["score"] == 50 and not r["qualified"]
    async def wrong_family(**kw):
        return '{"job_category": {"pass": false, "note": "DevOps target"}, "must_have_missing": ["Spark", "Airflow"], "summary": "no"}'
    monkeypatch.setattr(q, "chat", wrong_family)
    devops = dict(PROFILE, skills=["Kubernetes", "Terraform", "Go", "Docker"])
    r = _run(q.qualify_job(devops, "Senior Data Engineer", JD_OK, "Acme", "Remote - USA", "k", "google",
                           "google/gemini-2.5-flash", ["DevOps"]))
    assert r["score"] == 40 and not r["qualified"]          # years/visa/location fine, job is not
    # an intern posting is never "qualified" for a working professional
    async def intern_ok(**kw):
        return '{"job_category": {"pass": true, "note": "DE"}, "must_have_missing": [], "summary": "ok"}'
    monkeypatch.setattr(q, "chat", intern_ok)
    r = _run(q.qualify_job(PROFILE, "Data Engineer Intern", JD_OK, "Acme", "Remote - USA", "k", "google",
                           "google/gemini-2.5-flash", ["Data Engineer"]))
    assert r["score"] == 95 and not r["qualified"]
    assert not q._location_check("Remote Poland", "", PROFILE, None)[0]
    assert q._location_check("Remote - USA", "", PROFILE, None)[0]


def test_qualify_job_without_model_falls_back_to_code(monkeypatch):
    async def dead_chat(**kw):
        raise RuntimeError("HTTP 429")
    monkeypatch.setattr(q, "chat", dead_chat)
    r = _run(q.qualify_job(PROFILE, "Senior Data Engineer", JD_OK, "Acme", "Remote - USA", "k", "google",
                           "google/gemini-2.5-flash", ["Data Engineer"]))
    assert r["criteria"]["job_category"]["pass"] and r["criteria"]["skills_match"]["pass"]
    assert "model unavailable" in r["criteria"]["job_category"]["note"]
    assert r["qualified"]
    r = _run(q.qualify_job(PROFILE, "Product Manager", JD_OK, "Acme", "Remote - USA", "k", "google",
                           "google/gemini-2.5-flash", ["Data Engineer"]))
    assert not r["criteria"]["job_category"]["pass"] and not r["qualified"]


def test_jd_noise_strip_keeps_about_the_job_and_minimum_qualifications():
    from resume_lint import _strip_jd_noise
    jd = ("Senior Data Engineer\nAbout the Job\n• You will own critical pipelines.\nAbout You\nMinimum Qualifications\n"
          "• 8+ years in data engineering.\n• Expert with SQL and dbt.\nPreferred Qualifications\n• Snowflake.\n"
          "About Instacart\nWe deliver groceries.\nBenefits\n401k, dental.\n")
    out = _strip_jd_noise(jd)
    assert "own critical pipelines" in out and "8+ years" in out and "Expert with SQL and dbt" in out and "Snowflake" in out
    assert "We deliver groceries" not in out and "401k" not in out
    assert "8+ years" in q._requirements_text(jd)
