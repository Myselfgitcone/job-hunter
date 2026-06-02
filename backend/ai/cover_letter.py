from ai.llm import chat

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


async def generate_cover_letter(resume: str, jd: str, job_title: str, company: str,
                                 api_key: str, provider: str, model: str) -> str:
    return await chat(
        system=SYSTEM_PROMPT,
        user=f"""Write a cover letter for this candidate applying to: {job_title} at {company}

=== JOB DESCRIPTION ===
{jd[:2500]}

=== CANDIDATE RESUME ===
{resume}

Write the cover letter body only (starting from "Dear Hiring Manager," or similar). Keep it 250-350 words, highly specific to this role and company.""",
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=1024,
    )
