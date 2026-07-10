"""
Per-job qualification analysis — role-agnostic.
Scores each job against the candidate's actual profile and target roles on 6 criteria.
Works for any field: Data Engineering, Java/Backend, Cybersecurity, Finance, BI, Healthcare, etc.
"""
from ai.llm import chat
from datetime import datetime
import json
import re


_DATE_FMTS = ("%b %Y", "%B %Y", "%m/%Y", "%Y")

def _parse_month(s: str):
    s = (s or "").strip()
    if not s:
        return None
    if s.lower() in ("present", "current", "now"):
        return datetime.now()
    for f in _DATE_FMTS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _derive_total_years(exp: list) -> float:
    """Sum per-entry durations from start/end date strings. Live bug: admin
    profile entries had years=0/missing, so every job was scored against
    'Candidate has 0 years of experience' and 10k+ jobs auto-disqualified
    on the experience/seniority criteria."""
    total = 0.0
    for e in exp:
        a = _parse_month(e.get("start_date", ""))
        b = _parse_month(e.get("end_date", ""))
        if a and b and b > a:
            total += (b - a).days / 365.25
    return round(total, 1)

_SYSTEM_PROMPT_TEMPLATE = """\
You are a strict job qualification screener.

Analyze whether this job is a good match for the candidate profile. Score on exactly 6 criteria:

1. job_category   — Is the job title aligned with the candidate's target role(s): {roles}?
2. experience     — Does candidate's years of experience satisfy the requirement?
3. skills_match   — Do the candidate's tech skills match the core requirements?
4. sponsorship    — Does the job offer visa sponsorship (or not mention citizenship/clearance requirements)?
5. location       — Is the job remote, in the US, or in a location candidate can work?
6. seniority      — Does the seniority level match candidate's experience?

Respond ONLY with valid JSON, no markdown:
{{
  "qualified": true,
  "score": 85,
  "summary": "One sentence why qualified or not",
  "criteria": {{
    "job_category":  {{ "pass": true,  "note": "Role aligns with target" }},
    "experience":    {{ "pass": true,  "note": "5 yrs experience satisfies 3-5 yr req" }},
    "skills_match":  {{ "pass": true,  "note": "Core skills present" }},
    "sponsorship":   {{ "pass": true,  "note": "No citizenship requirement mentioned" }},
    "location":      {{ "pass": true,  "note": "Remote US eligible" }},
    "seniority":     {{ "pass": false, "note": "Requires 10+ years, candidate has 5" }}
  }}
}}

score = (passed_criteria / 6) * 100, rounded to nearest 5.
qualified = true only if score >= 60 AND job_category passes AND sponsorship passes.\
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
    candidate_roles: list | None = None,
    keys=None,
) -> dict:
    # Determine the candidate's target roles:
    # 1. Prefer explicitly passed candidate_roles (from user settings job_roles)
    # 2. Fall back to roles held in profile experience
    # 3. Last resort: generic fallback
    if candidate_roles:
        roles_str = ", ".join(candidate_roles)
    else:
        exp_roles = [e.get("role", "") for e in profile.get("experience", []) if e.get("role")]
        roles_str = ", ".join(exp_roles[:3]) if exp_roles else "any relevant professional role"

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(roles=roles_str)

    # Build compact profile summary
    exp = profile.get("experience", [])
    total_years = sum(float(e.get("years", 0)) for e in exp if e.get("years"))
    if not total_years and exp:
        total_years = _derive_total_years(exp)   # fallback: derive from dates
    years_str = f"{total_years} years" if total_years else "not specified — judge from roles held, do NOT fail experience/seniority solely for this"
    roles = [e.get("role", "") for e in exp if e.get("role")]
    skills = profile.get("skills", [])
    certs = profile.get("certifications", [])
    education = profile.get("education", [])
    edu_str = "; ".join(
        f"{e.get('degree', '')} from {e.get('school', '')}"
        for e in education if e.get("degree")
    )

    profile_summary = f"""Candidate Profile:
- Target roles: {roles_str}
- Total experience: {years_str}
- Roles held: {', '.join(roles[:3])}
- Skills: {', '.join(skills[:20])}
- Certifications: {', '.join(certs)}
- Education: {edu_str}
- Location preference: {profile.get('location', 'USA / Remote')}
"""

    text = await chat(
        system=system_prompt,
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
        keys=keys,
        pass_name="qualify",
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
