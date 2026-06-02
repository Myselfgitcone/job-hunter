"""
Per-job qualification analysis — ApplyNxt style.
Scores each job against the candidate's structured profile on 6 criteria.
"""
from ai.llm import chat
import json
import re

SYSTEM_PROMPT = """You are a strict job qualification screener for a Data Engineer / Data Analyst candidate.

Analyze whether this job is a good match for the candidate profile. Score on exactly 6 criteria:

1. job_category   — Is the title "Data Engineer", "Data Analyst", or directly related?
2. experience     — Does candidate's years of experience satisfy the requirement?
3. skills_match   — Do the candidate's tech skills match the core requirements?
4. sponsorship    — Does the job offer visa sponsorship (or not mention citizenship/clearance requirements)?
5. location       — Is the job remote, in the US, or in a location candidate can work?
6. seniority      — Does the seniority level match candidate's experience?

Respond ONLY with valid JSON, no markdown:
{
  "qualified": true,
  "score": 85,
  "summary": "One sentence why qualified or not",
  "criteria": {
    "job_category":  { "pass": true,  "note": "Senior Data Engineer role matches" },
    "experience":    { "pass": true,  "note": "5 yrs experience satisfies 3-5 yr req" },
    "skills_match":  { "pass": true,  "note": "Spark, Python, AWS all required and present" },
    "sponsorship":   { "pass": true,  "note": "No citizenship requirement mentioned" },
    "location":      { "pass": true,  "note": "Remote US eligible" },
    "seniority":     { "pass": false, "note": "Requires 10+ years, candidate has 5" }
  }
}

score = (passed_criteria / 6) * 100, rounded to nearest 5.
qualified = true only if score >= 60 AND job_category passes AND sponsorship passes.
"""


async def qualify_job(
    profile: dict,
    job_title: str,
    job_description: str,
    company: str,
    location: str,
    api_key: str,
    provider: str,
    model: str,
) -> dict:
    # Build compact profile summary
    exp = profile.get("experience", [])
    total_years = sum(float(e.get("years", 0)) for e in exp if e.get("years"))
    roles = [e.get("role", "") for e in exp if e.get("role")]
    skills = profile.get("skills", [])
    certs = profile.get("certifications", [])
    education = profile.get("education", [])
    edu_str = "; ".join(f"{e.get('degree','')} from {e.get('school','')}" for e in education if e.get("degree"))

    profile_summary = f"""Candidate Profile:
- Total experience: {total_years} years
- Roles: {', '.join(roles[:3])}
- Skills: {', '.join(skills[:20])}
- Certifications: {', '.join(certs)}
- Education: {edu_str}
- Location preference: {profile.get('location', 'USA / Remote')}
"""

    text = await chat(
        system=SYSTEM_PROMPT,
        user=f"""Job: {job_title} at {company} ({location})

=== JOB DESCRIPTION ===
{job_description[:2000]}

=== CANDIDATE PROFILE ===
{profile_summary}

Qualify this job. Return JSON only.""",
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=600,
    )

    # Parse JSON
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    # Fallback
    return {
        "qualified": False,
        "score": 0,
        "summary": "Could not analyze",
        "criteria": {},
    }
