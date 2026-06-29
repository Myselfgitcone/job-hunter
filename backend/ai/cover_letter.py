from ai.llm import chat
from resume_lint import detect_cover_letter_fabrication

SYSTEM_PROMPT = """You are an expert technical cover letter writer specializing in Data Engineering roles.

Write a compelling, personalized cover letter that:
1. Opens with a strong hook referencing the specific company and role
2. Connects 2-3 of the candidate's strongest relevant achievements to the job requirements
3. Shows genuine enthusiasm for the company's work/mission
4. Closes with a confident call-to-action
5. Sounds human and conversational, NOT generic or templated

STRICT RULES:
- Never fabricate experience not in the resume
- Keep to 3-4 short paragraphs (250-350 words max)
- No boilerplate like "I am writing to express my interest..."
- Use specific numbers and achievements from the resume
- Reference specific technologies mentioned in the job description
- Do NOT include address blocks or date headers — just the letter body starting from the greeting"""

_RETRY_SYSTEM_PROMPT = SYSTEM_PROMPT + """

You are FIXING a previously written letter. Fix ONLY the flagged issues below —
keep everything else in the letter unchanged. Output the complete letter body
only, same format as before (no commentary, no explanation of what you changed)."""


async def generate_cover_letter(resume: str, jd: str, job_title: str, company: str,
                                 api_key: str, provider: str, model: str, keys=None) -> str:
    user_msg = f"""Write a cover letter for this candidate applying to: {job_title} at {company}

=== JOB DESCRIPTION ===
{jd[:2500]}

=== CANDIDATE RESUME ===
{resume}

Write the cover letter body only (starting from "Dear Hiring Manager," or similar). Keep it 250-350 words, highly specific to this role and company."""

    letter = await chat(
        system=SYSTEM_PROMPT, user=user_msg,
        api_key=api_key, provider=provider, model=model,
        max_tokens=1024, pass_name="cover-letter", keys=keys,
    )

    # One-shot generation had zero verification — a prompt telling the model
    # "never fabricate" is exactly the instruction the resume pipeline also had
    # when it invented MongoDB production work. Check once; if it invented a
    # number or tool not grounded in the resume/JD, do ONE targeted retry.
    issues = detect_cover_letter_fabrication(letter, resume, jd)
    if not issues:
        return letter

    issue_lines = "\n".join(f"  • {iss}" for iss in issues)
    fix_msg = (
        f"ISSUES TO FIX in the letter below:\n{issue_lines}\n\n"
        f"=== JOB DESCRIPTION ===\n{jd[:2500]}\n\n"
        f"=== CANDIDATE RESUME (ground truth) ===\n{resume}\n\n"
        f"=== LETTER TO FIX ===\n{letter}"
    )
    fixed = await chat(
        system=_RETRY_SYSTEM_PROMPT, user=fix_msg,
        api_key=api_key, provider=provider, model=model,
        max_tokens=1024, pass_name="cover-letter-retry", keys=keys,
    )
    # Guard against a truncated/degenerate retry — keep the original rather
    # than ship an empty or drastically shorter letter.
    if len(fixed.strip()) < 0.5 * len(letter.strip()):
        return letter
    return fixed
