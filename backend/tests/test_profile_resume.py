"""The plain-text base resume built from a user's Profile: nothing about it
may come from a fixed string (one live user with a ServiceNow grant got the
admin's 'Senior Data Engineer' headline)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from main import _profile_to_resume_text  # noqa: E402


def _profile(**over):
    p = {"name": "Priya Nair", "email": "priya@example.com", "phone": "(212) 555-0100",
         "location": "Austin, TX", "linkedin": "priya-nair", "github": "", "website": "",
         "experience": [{"role": "ServiceNow Developer", "company": "Acme", "location": "Austin, TX",
                         "start_date": "Jan 2022", "end_date": "Present", "bullets": ["Built ITSM flows."]}],
         "skills": ["ServiceNow", "JavaScript"], "education": [], "certifications": [], "projects": []}
    p.update(over)
    return p


def test_headline_is_the_users_own_or_latest_title():
    lines = _profile_to_resume_text(_profile()).splitlines()
    assert lines[0] == "Priya Nair \u2014 ServiceNow Developer"
    lines = _profile_to_resume_text(_profile(headline="Senior ServiceNow Architect")).splitlines()
    assert lines[0] == "Priya Nair \u2014 Senior ServiceNow Architect"
    lines = _profile_to_resume_text(_profile(experience=[])).splitlines()
    assert lines[0] == "Priya Nair"


def test_contact_line_is_phone_email_links_never_a_location():
    lines = _profile_to_resume_text(_profile()).splitlines()
    assert lines[1] == "(212) 555-0100 | priya@example.com | linkedin.com/in/priya-nair"
    lines = _profile_to_resume_text(_profile(linkedin="", github="https://github.com/pn", website="priya.dev")).splitlines()
    assert lines[1] == "(212) 555-0100 | priya@example.com | https://github.com/pn | priya.dev"
    lines = _profile_to_resume_text(_profile(address="12359 Lakepoint Dr, Maryland Heights, Mo - 63043")).splitlines()
    assert lines[1].startswith("(212) 555-0100") and "Maryland" not in lines[1] and "Austin" not in lines[1]


def test_projects_section_carries_title_links_and_bullets():
    text = _profile_to_resume_text(_profile(projects=[
        {"name": "Footnote \u2014 RAG over SEC filings", "stack": "LangGraph, Pinecone",
         "links": ["myselfgitcone.github.io/footnote", "github.com/Myselfgitcone/footnote"],
         "bullets": ["Raised answer grounding from 87% to 100% on a 29-question suite.", "\u2022 Built the LangGraph graph on Lambda."]},
        {"name": "Silo", "description": "MCP, DuckDB", "url": "github.com/Myselfgitcone/silo", "bullets": []},
    ]))
    sec = text.split("PROJECTS:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert sec[0] == "Footnote \u2014 RAG over SEC filings  \u00b7  myselfgitcone.github.io/footnote \u00b7 github.com/Myselfgitcone/footnote"
    assert sec[1] == "\u2022 Raised answer grounding from 87% to 100% on a 29-question suite."
    assert sec[2] == "\u2022 Built the LangGraph graph on Lambda."
    assert sec[3] == "Silo \u2014 MCP, DuckDB  \u00b7  github.com/Myselfgitcone/silo"   # legacy url + tagline
    assert len(sec) == 4
    assert "PROJECTS:" not in _profile_to_resume_text(_profile(projects=[]))
    # a legacy project whose description is only its tool list gets a title, no fake bullet
    text = _profile_to_resume_text(_profile(projects=[{"name": "Silo \u2014 MCP server over a lakehouse", "description": "MCP, DuckDB, sqlglot"}]))
    sec = text.split("PROJECTS:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert sec == ["Silo \u2014 MCP server over a lakehouse"]
    # a legacy project whose description is only its tool list gets a title, no fake bullet
    text = _profile_to_resume_text(_profile(projects=[{"name": "Silo \u2014 MCP server over a lakehouse", "description": "MCP, DuckDB, sqlglot"}]))
    sec = text.split("PROJECTS:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert sec == ["Silo \u2014 MCP server over a lakehouse"]


def test_phone_prints_in_us_shape_whatever_the_parser_returned():
    assert _profile_to_resume_text(_profile(phone="3476951020")).splitlines()[1].startswith("(347) 695-1020 |")
    assert _profile_to_resume_text(_profile(phone="+1 347 695 1020")).splitlines()[1].startswith("(347) 695-1020 |")
    assert _profile_to_resume_text(_profile(phone="+44 20 7946 0958")).splitlines()[1].startswith("+44 20 7946 0958 |")


def test_phone_prints_in_us_shape_whatever_the_parser_returned():
    assert _profile_to_resume_text(_profile(phone="3476951020")).splitlines()[1].startswith("(347) 695-1020 |")
    assert _profile_to_resume_text(_profile(phone="+1 347 695 1020")).splitlines()[1].startswith("(347) 695-1020 |")
    assert _profile_to_resume_text(_profile(phone="+44 20 7946 0958")).splitlines()[1].startswith("+44 20 7946 0958 |")


def test_bullets_use_a_real_bullet_character():
    text = _profile_to_resume_text(_profile())
    assert "\u2022 Built ITSM flows." in text
    assert "\u00e2\u20ac\u00a2" not in text


def test_skill_groups_render_as_labelled_rows_with_other_for_ungrouped():
    p = _profile(skills=["Python", "SQL", "S3", "EMR", "Airflow"],
                 skill_groups=[{"name": "Languages", "items": ["Python", "SQL"]},
                               {"name": "AWS", "items": ["S3", "EMR", "Glue"]}])   # Glue not in skills: dropped
    text = _profile_to_resume_text(p)
    assert "\u2022 Languages: Python, SQL\n\u2022 AWS: S3, EMR\n\u2022 Other: Airflow" in text
    flat = _profile_to_resume_text(_profile(skills=["Python", "SQL"], skill_groups=[]))
    assert "TECHNICAL SKILLS:\nPython, SQL" in flat


def test_education_line_is_not_a_job_header():
    text = _profile_to_resume_text(_profile(education=[{"degree": "M.S. Information Systems", "school": "Saint Louis University", "year": "2022 \u2013 2024"}]))
    assert "M.S. Information Systems, Saint Louis University  2022 \u2013 2024" in text
    assert " @ Saint Louis" not in text
    from ai.tailor import _is_job_header_line
    edu_line = [l for l in text.splitlines() if "Saint Louis" in l][0]
    assert not _is_job_header_line(edu_line)
