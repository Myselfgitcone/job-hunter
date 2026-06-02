import re
from ai.llm import chat


# ── Hard limits enforced in Python (AI cannot count) ─────────────────────────
BULLET_LIMITS = {
    "PROFESSIONAL SUMMARY": 7,
    "summary":              7,
}
JOB_BULLET_LIMITS = [11, 8, 7]   # most-recent → oldest
SKILLS_LINE_LIMIT = 12


def _enforce_limits(text: str) -> str:
    """
    Post-process AI output to hard-enforce bullet counts per section.
    Trims bullets from the bottom of each section (lowest relevance = last).
    """
    lines = text.split("\n")
    out   = []

    # Track which job role we're in (0=first/most-recent, 1=second, 2=third+)
    job_index      = -1
    in_section     = None   # "summary" | "job" | "skills" | "education" | "other"
    bullet_count   = 0
    bullet_limit   = 9999
    skills_count   = 0
    in_tech_line   = False

    def is_section_header(l):
        s = l.strip()
        return (s == s.upper() and len(s) > 3
                and s.endswith(":") and not s.startswith("•"))

    def is_job_header(l):
        return bool(re.match(r"^.+? @ .+", l.strip()))

    def is_bullet(l):
        return l.strip().startswith("•")

    def is_tech_line(l):
        return l.strip().startswith("Technologies Used:")

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── Section header ───────────────────────────────────────────────────
        if is_section_header(stripped):
            sec = stripped.rstrip(":").upper()
            if "SUMMARY" in sec or "PROFESSIONAL" in sec:
                in_section   = "summary"
                bullet_limit = BULLET_LIMITS["PROFESSIONAL SUMMARY"]
                bullet_count = 0
            elif "SKILL" in sec or "TECHNICAL" in sec:
                in_section   = "skills"
                skills_count = 0
            elif "EDUC" in sec:
                in_section   = "education"
            else:
                in_section   = "other"
            job_index = -1
            out.append(line)
            i += 1
            continue

        # ── Job header ───────────────────────────────────────────────────────
        if is_job_header(stripped):
            in_section  = "job"
            job_index  += 1
            limit_idx   = min(job_index, len(JOB_BULLET_LIMITS) - 1)
            bullet_limit = JOB_BULLET_LIMITS[limit_idx]
            bullet_count = 0
            out.append(line)
            i += 1
            continue

        # ── Technologies Used line ────────────────────────────────────────────
        if is_tech_line(stripped):
            out.append(line)
            i += 1
            continue

        # ── Bullet lines ─────────────────────────────────────────────────────
        if is_bullet(stripped):
            if in_section == "summary":
                if bullet_count < bullet_limit:
                    out.append(line)
                    bullet_count += 1
                # else skip
            elif in_section == "job":
                if bullet_count < bullet_limit:
                    out.append(line)
                    bullet_count += 1
                # else skip
            elif in_section == "skills":
                if skills_count < SKILLS_LINE_LIMIT:
                    out.append(line)
                    skills_count += 1
                # else skip
            else:
                out.append(line)
            i += 1
            continue

        # ── Continuation lines (wrapped bullet text, not starting with •) ────
        # Keep only if previous line was kept (check out[-1] is bullet content)
        if in_section in ("summary", "job") and stripped and not is_section_header(stripped):
            # It's a wrapped continuation — keep if last appended was kept bullet
            if out and (out[-1].strip().startswith("•") or
                        (not out[-1].strip().startswith("•") and
                         not is_section_header(out[-1].strip()) and
                         not is_job_header(out[-1].strip()) and
                         out[-1].strip())):
                out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out)

SYSTEM_PROMPT = """You are an expert technical resume writer for a Senior Data Engineer with 6+ years experience. Your output MUST fit exactly 2 printed pages — this is non-negotiable.

═══ STRICT 2-PAGE BUDGET (HARD LIMITS) ═══
• PROFESSIONAL SUMMARY:  7 bullets max — most relevant to JD
• MOST RECENT JOB:        11 bullets max + 1 Technologies Used line
• SECOND JOB:             8 bullets max + 1 Technologies Used line
• THIRD JOB:              7 bullets max + 1 Technologies Used line
• TECHNICAL SKILLS:       12 lines max — group tightly
• EDUCATION:              1 line only

Total bullets across entire resume: 33-35 max. If you write more, you FAILED.

═══ SELECTION CRITERIA ═══
For each job role, rank all existing bullets by JD relevance. Keep only the top N (per limits above). Cut the rest — no mercy. Shorter bullets beat longer ones when content is equal.

Bullet scoring (keep highest):
  5 pts — Directly uses a tool/skill explicitly named in JD
  4 pts — Describes a responsibility explicitly listed in JD
  3 pts — Quantified impact (%, volume, time saved)
  2 pts — Relevant tech but not explicitly in JD
  1 pt  — Generic soft skill or low-specificity statement → CUT FIRST

═══ GAP FILLING ═══
For each JD requirement missing from resume: craft ONE tight bullet (≤20 words), realistic, industry-specific, with a number. Add it to the most relevant role. It counts against that role's bullet budget — so it must displace the lowest-scoring existing bullet.

═══ OTHER RULES ═══
• KEYWORDS: inject JD keywords naturally into kept bullets
• SUMMARY: rewrite to mirror JD's exact language for the role
• SKILLS: include every JD tool the candidate plausibly knows; remove tools not relevant to this JD to save space
• FORMAT: • bullets, ALL CAPS section headers with colon, "Title @ Company | Location   Date" job headers, Technologies Used lines
• HEADER: copy the name line and contact line EXACTLY as-is — never alter name, title, phone, or email
• NO padding, NO generic filler sentences, NO repeated ideas across bullets
• Return ONLY the resume — no commentary, no preamble"""


async def tailor_resume(base_resume: str, job_description: str,
                        api_key: str, provider: str, model: str) -> str:
    raw = await chat(
        system=SYSTEM_PROMPT,
        user=f"""Tailor this resume to the JD. HARD LIMIT: 2 printed pages.

PROCESS:
1. Score every existing bullet (1-5) by JD relevance
2. Keep only top bullets per the per-role limits (11/8/7)
3. Identify JD gaps → craft tight gap-filling bullets → displace lowest-scoring bullet in that role
4. Output the final resume — nothing else

=== JOB DESCRIPTION ===
{job_description[:3000]}

=== ORIGINAL RESUME ===
{base_resume}

OUTPUT: complete tailored resume, plain text only, exact format preserved.""",
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=4096,
    )
    return _enforce_limits(raw)
