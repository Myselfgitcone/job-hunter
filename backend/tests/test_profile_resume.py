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


def test_contact_line_is_phone_email_links_no_location():
    lines = _profile_to_resume_text(_profile()).splitlines()
    assert lines[1] == "(212) 555-0100 | priya@example.com | linkedin.com/in/priya-nair"
    lines = _profile_to_resume_text(_profile(linkedin="", github="https://github.com/pn", website="priya.dev")).splitlines()
    assert lines[1] == "(212) 555-0100 | priya@example.com | https://github.com/pn | priya.dev"


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
