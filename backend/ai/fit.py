from ai.llm import chat
import json
import re

SYSTEM_PROMPT = """You are a senior technical recruiter and career coach specializing in Data Engineering.

Analyze the candidate's fit for the job and provide:
1. A 3-4 sentence "why you're a strong fit" analysis — specific, concrete, referencing actual skills and experience from the resume
2. Exactly 5 interview tips specific to THIS job description — actionable, precise, not generic

Respond ONLY with valid JSON in this exact format:
{
  "analysis": "...",
  "tips": ["tip 1", "tip 2", "tip 3", "tip 4", "tip 5"]
}"""

FALLBACK_TIPS = [
    "Review the job description thoroughly before the interview.",
    "Prepare STAR-format answers for behavioral questions.",
    "Research the company's tech stack and data infrastructure.",
    "Be ready to discuss your most complex pipeline architecture.",
    "Prepare questions about team structure and data engineering practices.",
]


async def analyze_fit(resume: str, job_description: str, job_title: str, company: str,
                      api_key: str, provider: str, model: str) -> dict:
    text = await chat(
        system=SYSTEM_PROMPT,
        user=f"""Job: {job_title} at {company}

=== JOB DESCRIPTION ===
{job_description[:2500]}

=== CANDIDATE RESUME ===
{resume[:3000]}

Provide the fit analysis and 5 interview tips as JSON.""",
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=1024,
    )

    match = re.search(r"\{[\s\S]*\}", text.strip())
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {"analysis": text, "tips": FALLBACK_TIPS}
