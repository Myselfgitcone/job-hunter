import re
from ai.llm import chat
from resume_lint import lint_resume, detect_role_type, detect_domain_leak, BULLET_BUDGETS, BULLET_MINIMUMS, SUMMARY_EXACT
from resume_lint import TECH, IB, FINANCE, CYBER, HEALTHCARE, CONSULTING, GENERAL
from resume_lint import user_roles_to_role_type

try:
    from resume_lint import skill_coverage_report, extract_jd_hard_skills
except ImportError:  # Backward compatibility if older resume_lint.py is used.
    skill_coverage_report = None
    extract_jd_hard_skills = None


# ── Hard limits enforced in Python (AI cannot count) ─────────────────────────
# Bullet limits are now role-type-aware. Loaded dynamically from resume_lint.
# BULLET_BUDGETS[role_type] = (most_recent, second, third, fourth_plus, summary, hard_total)
SUMMARY_LIMIT  = 6
SKILLS_LINE_LIMIT = 9

# Closing line prefixes per role type — what _enforce_limits passes through unchanged
_CLOSING_PREFIXES = {
    TECH:       "Technologies Used:",
    CYBER:      "Technologies & Platforms:",
    IB:         "Selected Transactions:",
    FINANCE:    "Key Tools:",
    HEALTHCARE: "Systems Used:",
    CONSULTING: None,
    GENERAL:    None,
}

# Skills section keywords per role type — used to detect skills section in enforce_limits
_SKILLS_SECTION_KEYWORDS = {
    TECH:       {"SKILL", "TECHNICAL"},
    IB:         {"COMPETENC", "SKILL"},
    FINANCE:    {"COMPETENC", "SKILL"},
    CYBER:      {"SKILL", "TECHNICAL", "CERTIF"},
    HEALTHCARE: {"SKILL", "EXPERTISE", "LICENS", "CERTIF"},
    CONSULTING: {"COMPETENC", "SKILL"},
    GENERAL:    {"SKILL", "COMPETENC"},
}


_HDR_PHONE_RE = re.compile(r'\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}')
_HDR_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')


def _clean_header_title(result: str) -> str:
    """
    Deterministic: strip posting-title suffixes from the header title line.
    'Name — Data Migration Engineer – SQL Server to Snowflake & Matillion'
    → 'Name — Data Migration Engineer'
    The name—title separator is an em-dash (—); posting suffixes follow an
    en-dash (–), ' - ', pipe, colon, or opening parenthesis.
    """
    lines = result.splitlines()
    if not lines:
        return result
    first = lines[0]
    if '—' not in first:
        return result
    name, _, title = first.partition('—')
    cleaned = re.split(r'\s+–\s+|\s+-\s+|\s*\|\s*|\s*:\s+|\s*\(', title, maxsplit=1)[0].strip()
    if cleaned and cleaned != title.strip():
        lines[0] = f"{name.strip()} — {cleaned}"
        print(f"[HEADER TITLE] Cleaned posting suffix: '{title.strip()}' -> '{cleaned}'")
    return '\n'.join(lines)


def _ensure_header(result: str, base_resume: str) -> str:
    """
    Deterministic safety net: if AI dropped the name/contact header, restore it.
    - If AI has a name line (contains '—') but missing contact → add contact from base.
    - If AI dropped everything before PROFESSIONAL SUMMARY → prepend full header from base.
    Preserves any title change the AI made on the name line.
    """
    result_stripped = result.strip()
    result_lines    = result_stripped.splitlines()
    top3            = "\n".join(result_lines[:3])

    if _HDR_PHONE_RE.search(top3) and _HDR_EMAIL_RE.search(top3):
        return result  # header intact

    # Extract contact line from base resume (has phone + email)
    base_lines   = [l for l in base_resume.strip().splitlines() if l.strip()]
    contact_line = next((l for l in base_lines[:4] if _HDR_PHONE_RE.search(l)), "")
    base_name    = base_lines[0] if base_lines else ""
    if not contact_line:
        return result  # can't restore — give up

    # Find where PROFESSIONAL SUMMARY starts in the AI output
    ps_m = re.search(r'^PROFESSIONAL SUMMARY', result_stripped, re.IGNORECASE | re.MULTILINE)
    body = result_stripped[ps_m.start():] if ps_m else result_stripped

    # AI has a name/title line before the summary?
    first_line = result_lines[0].strip() if result_lines else ""
    has_name_line = bool(re.search(r'\b[A-Z][a-z]+.+[A-Z][a-z]+', first_line)) and ps_m and ps_m.start() > len(first_line)

    if has_name_line:
        print("[HEADER MISSING] Contact line missing — restoring.")
        return first_line + "\n" + contact_line + "\n\n" + body
    else:
        print("[HEADER MISSING] Full header missing — restoring from base resume.")
        return base_name + "\n" + contact_line + "\n\n" + body


def _extract_education_section(text: str) -> str:
    """Return the content lines under the EDUCATION header (stripped, newline-joined)."""
    lines = text.split("\n")
    edu_lines: list[str] = []
    in_edu = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^EDUCATION:?\s*$', stripped, re.IGNORECASE):
            in_edu = True
            continue
        if in_edu:
            # Any new ALL-CAPS section header ends the block
            if stripped and stripped == stripped.upper() and len(stripped) > 3 and not stripped.startswith("•"):
                break
            if stripped:
                edu_lines.append(stripped)
    return "\n".join(edu_lines)


def _replace_education_section(text: str, correct_edu: str) -> str:
    """Splice correct_edu into text, replacing whatever the AI generated under EDUCATION."""
    lines = text.split("\n")
    out: list[str] = []
    in_edu = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^EDUCATION:?\s*$', stripped, re.IGNORECASE):
            in_edu = True
            out.append(line)
            for edu_line in correct_edu.split("\n"):
                if edu_line.strip():
                    out.append(edu_line)
            continue
        if in_edu:
            if stripped and stripped == stripped.upper() and len(stripped) > 3 and not stripped.startswith("•"):
                in_edu = False
                out.append(line)
            # else: discard AI-generated education content
            continue
        out.append(line)
    return "\n".join(out)


_EDU_WORDS = ("university", "college", "institute", "bachelor", "master", "phd", "degree")

def _is_job_header_line(s: str) -> bool:
    if " @ " not in s or s.startswith("•"):
        return False
    if any(d in s.lower() for d in _EDU_WORDS):
        return False
    return bool(re.search(r' @ .+? \|', s))


# ── Section augmenter — surgical bullet injection ────────────────────────────
def _parse_resume_sections(resume: str) -> list[dict]:
    """
    Parse resume into job blocks. Returns list of dicts:
      {header, bullets, tech_line, start_idx, end_idx}
    Ordered by appearance (job 0 = most recent).
    """
    lines  = resume.split('\n')
    blocks = []
    cur    = None

    for i, raw in enumerate(lines):
        s = raw.strip()
        if _is_job_header_line(s):
            if cur is not None:
                cur['end_idx'] = i
                blocks.append(cur)
            cur = {'header': s, 'bullets': [], 'tech_line': None,
                   'start_idx': i, 'end_idx': None}
        elif cur is not None:
            if s.startswith('•'):
                cur['bullets'].append(s[1:].strip())
            elif s.lower().startswith('technologies used:'):
                cur['tech_line'] = s
            elif s and s == s.upper() and len(s) > 3 and not s.startswith('•'):
                # New section header → close current job block
                cur['end_idx'] = i
                blocks.append(cur)
                cur = None

    if cur is not None:
        cur['end_idx'] = len(lines)
        blocks.append(cur)

    return blocks


async def _augment_section(
    block: dict,
    deficit: int,
    jd_excerpt: str,
    api_key: str,
    provider: str,
    model: str,
    keys=None,
) -> list[str]:
    """
    Ask the model to write exactly `deficit` more bullets for a job section.
    Uses NO system prompt — tiny call, ~600-900 tokens input.
    Returns list of bullet text strings (no leading •).
    """
    from ai.llm import chat as _chat
    existing = '\n'.join(f'• {b}' for b in block['bullets'])
    tech = block.get('tech_line') or ''

    prompt = (
        f"You are adding exactly {deficit} bullet point(s) to this job section of a tailored resume.\n\n"
        f"JOB: {block['header']}\n"
        f"EXISTING BULLETS:\n{existing}\n"
        + (f"TECH STACK: {tech}\n" if tech else "")
        + f"\nJD CONTEXT (for keyword alignment): {jd_excerpt}\n\n"
        f"Write exactly {deficit} new bullet(s) that:\n"
        f"• Match the voice, format, and level of specificity of the existing bullets\n"
        f"• Start with a strong past-tense action verb (different from existing openers)\n"
        f"• Include specific tools/metrics matching the existing style\n"
        f"• Are ≤25 words each\n"
        f"• Do NOT duplicate or restate existing bullets\n\n"
        f"Return ONLY the {deficit} bullet(s), each on its own line, starting with •"
    )

    raw = await _chat(
        system="",
        user=prompt,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=200 * deficit,
        pass_name="augment",
        keys=keys,
    )

    bullets = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith('•'):
            bullets.append(line[1:].strip())
        elif line and not line.startswith('#'):
            bullets.append(line)
    return bullets[:deficit]  # never return more than asked


def _insert_bullets_into_section(resume: str, block: dict, new_bullets: list[str]) -> str:
    """
    Insert new_bullets into the resume at the correct job block position.
    Inserts just BEFORE the Technologies Used line (or at end of block if none).
    """
    lines = resume.split('\n')
    start = block['start_idx']
    end   = block['end_idx'] if block['end_idx'] is not None else len(lines)

    # Find insertion point: before Tech line or before next section header
    insert_at = end  # default: end of block
    for i in range(start, end):
        s = lines[i].strip()
        if s.lower().startswith('technologies used:'):
            insert_at = i
            break

    bullet_lines = [f'• {b}' for b in new_bullets]
    lines = lines[:insert_at] + bullet_lines + lines[insert_at:]

    # Shift end_idx references — caller should re-parse if needed
    return '\n'.join(lines)


# ── Missing-skill bullet injection ────────────────────────────────────────────
# For each JD hard skill absent from the BASE resume, generate ONE dedicated
# bullet and place it in the best-matching job block. One AI call total.
# Tier-aware wording so the downstream tier audit passes the bullets:
#   W/A → production wording (reads as real employer work)
#   S   → prototype/POC wording (real-looking, but audit-safe)
#   H   → SKIP (never a bullet; skills-row injection handles visibility later)
# Timeline-aware: skill must exist before the job's end date.
# Budget-aware: never pushes a job block past its BULLET_BUDGETS max.

_SKILL_INJECT_PROMPT = """You place missing JD skills into a resume as single dedicated bullets.

For EACH skill in the MISSING SKILLS list, output exactly one line:
  SKILL_NAME | TIER | JOB_NUMBER | BULLET_TEXT

TIER — judge against the ORIGINAL RESUME (ground truth):
  W = work-supported. Original resume shows directly related real work.
  A = adjacent-stretch. Plausible extension of proven work (same ecosystem/category).
  S = self-implementable. Learnable solo; no employer evidence at all.
  H = high-risk. Certifications, licenses, clearances, regulated credentials.

JOB_NUMBER — 1 = most recent job. Pick the job whose tech stack overlaps the skill most.
  TIMELINE RULE: never place a skill in a job that ended before the skill's
  general-availability year (e.g. no Snowflake before 2015, no Kubernetes
  before 2016, no dbt before 2018, no GPT/LLM work before 2020). If the only
  overlapping job predates the skill, move it to the most recent job that
  doesn't violate the timeline.

BULLET_TEXT rules:
  - ONE skill per bullet. The skill name MUST appear verbatim in the bullet.
  - Match the voice, tense, and specificity of that job's existing bullets.
  - Start with a past-tense action verb not already used as an opener in that job.
  - 14-22 words. At most one metric, and only if the job's bullets carry metrics.
  - W/A tier: write it as real production work at that employer. Concrete,
    specific, integrated with that job's actual domain and stack.
  - S tier: output JOB_NUMBER as exactly  PROJ  — the bullet goes to a
    PROJECTS section, NOT a job block. Write it full-strength as a standalone
    technical project: strong verbs fine (Designed/Built/Implemented), name
    the skill plus 2-3 supporting technologies, describe what it does. No
    employer, no company metrics. Example: "Designed Snowflake warehouse with
    dbt models, clustering keys, and CI-driven deployments for analytics workloads".
  - H tier: output exactly:  SKILL_NAME | H | SKIP | SKIP

Do not invent employers, titles, or dates. Do not restate existing bullets.
Return ONLY the pipe-delimited lines. No commentary, no markdown."""


async def inject_missing_skill_bullets(
    resume: str,
    missing_skills: list[str],
    base_resume: str,
    jd: str,
    role_type: str,
    api_key: str,
    provider: str,
    model: str,
    keys=None,
) -> str:
    """
    One dedicated bullet per missing JD skill, placed in the best-match job.
    Single AI call for all skills. Deterministic parse + insert + budget guard.
    Returns resume unchanged on any failure.
    """
    from ai.llm import chat as _chat

    # Filter noise the keyword injector also skips
    skills = [
        s for s in missing_skills
        if s.lower() not in _INJECTION_SKIP and len(s) >= 2
    ]
    if not skills:
        return resume

    blocks = _parse_resume_sections(resume)
    if not blocks:
        return resume

    budget = BULLET_BUDGETS[role_type]
    job_limits = [budget[0], budget[1], budget[2], budget[3]]

    jobs_ctx = []
    for i, b in enumerate(blocks):
        existing = "\n".join(f"  • {x}" for x in b["bullets"][:6])
        tech = f"\n  {b['tech_line']}" if b.get("tech_line") else ""
        jobs_ctx.append(f"JOB {i + 1}: {b['header']}\n{existing}{tech}")

    user_msg = (
        f"MISSING SKILLS:\n{', '.join(skills)}\n\n"
        f"JOBS IN TAILORED RESUME (1 = most recent):\n" + "\n\n".join(jobs_ctx) + "\n\n"
        f"JD EXCERPT:\n{jd[:800]}\n\n"
        f"ORIGINAL RESUME (ground truth for tier judgment):\n{base_resume[:6000]}"
    )

    try:
        raw = await _chat(
            system=_SKILL_INJECT_PROMPT,
            user=user_msg,
            api_key=api_key,
            provider=provider,
            model=model,
            max_tokens=120 * len(skills) + 200,
            pass_name="skill-inject",
            keys=keys,
        )
    except Exception as e:
        print(f"[SKILL INJECT] AI call failed: {e}")
        return resume

    # Parse: SKILL | TIER | JOB_NUMBER | BULLET
    from resume_lint import _dynamic_coverage_pattern
    per_job_new: dict[int, list[str]] = {}
    project_new: list[str] = []
    skills_lo = {s.lower(): s for s in skills}
    seen: set[str] = set()

    for line in raw.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        skill, tier, job_s, bullet = parts[0], parts[1].upper(), parts[2], "|".join(parts[3:]).strip()
        skill_lo = skill.lower()
        if skill_lo not in skills_lo or skill_lo in seen:
            continue
        seen.add(skill_lo)

        if tier == "H" or job_s.upper() == "SKIP" or bullet.upper() == "SKIP":
            print(f"[SKILL INJECT] '{skill}' tier={tier} — skipped (skills-row only)")
            continue
        if tier not in ("W", "A", "S"):
            continue

        # S tier → PROJECTS section: full-strength standalone project bullet,
        # no employer attached. Honest AND strong — audit-proof by design.
        if job_s.upper() == "PROJ" or tier == "S":
            if not re.search(_dynamic_coverage_pattern(skill), bullet.lower()):
                print(f"[SKILL INJECT] '{skill}' — project bullet missing skill, dropped")
                continue
            wc = len(bullet.split())
            if wc < 8 or wc > 30:
                print(f"[SKILL INJECT] '{skill}' — project bullet {wc} words, dropped")
                continue
            project_new.append(bullet.lstrip("•").strip())
            continue

        m = re.match(r"(\d+)", job_s)
        if not m:
            continue
        job_idx = int(m.group(1)) - 1
        if job_idx < 0 or job_idx >= len(blocks):
            continue

        # Bullet must actually contain the skill (verbatim-ish)
        if not re.search(_dynamic_coverage_pattern(skill), bullet.lower()):
            print(f"[SKILL INJECT] '{skill}' — bullet missing skill mention, dropped")
            continue

        # Sanity: length + no header/company fabrication markers
        wc = len(bullet.split())
        if wc < 8 or wc > 30:
            print(f"[SKILL INJECT] '{skill}' — bullet {wc} words out of range, dropped")
            continue

        bullet = bullet.lstrip("•").strip()
        per_job_new.setdefault(job_idx, []).append((bullet, skill, tier))

    if not per_job_new and not project_new:
        return resume

    # Insert per job, newest-block indices shift after each insert → re-parse.
    # Budget guard: cap so block never exceeds its role-type per-job max.
    injected_total = 0
    for job_idx in sorted(per_job_new):
        blocks = _parse_resume_sections(resume)
        if job_idx >= len(blocks):
            continue
        block = blocks[job_idx]
        limit = job_limits[min(job_idx, 3)]
        headroom = limit - len(block["bullets"])
        if headroom <= 0:
            print(f"[SKILL INJECT] job #{job_idx + 1} at budget cap ({limit}) — skipped")
            continue
        entries = per_job_new[job_idx][:headroom]
        new_bullets = [b for b, _s, _t in entries]
        resume = _insert_bullets_into_section(resume, block, new_bullets)
        injected_total += len(new_bullets)
        print(f"[SKILL INJECT] job #{job_idx + 1}: +{len(new_bullets)} skill bullet(s)")

        # Sync Technologies Used line — W/A tiers only. An S-tier skill on
        # the tech line reads as employer production use; the tier audit
        # would flag it. Prototype bullets keep the skill visible without
        # the production claim.
        tech_line = block.get("tech_line")
        if tech_line:
            additions = [
                s for _b, s, t in entries
                if t in ("W", "A") and s.lower() not in tech_line.lower()
            ]
            if additions:
                new_tech = tech_line.rstrip() + ", " + ", ".join(additions)
                resume = resume.replace(tech_line, new_tech, 1)
                print(f"[SKILL INJECT] job #{job_idx + 1} tech line += {', '.join(additions)}")

    # ── PROJECTS section — S-tier landing zone ───────────────────────────
    if project_new:
        resume = _insert_project_bullets(resume, project_new)
        injected_total += len(project_new)
        print(f"[SKILL INJECT] PROJECTS: +{len(project_new)} project bullet(s)")

    if injected_total:
        print(f"[SKILL INJECT] Total: {injected_total} dedicated skill bullet(s) added")
    return resume


def _insert_project_bullets(resume: str, bullets: list[str]) -> str:
    """
    Append bullets to an existing PROJECTS section, or create one directly
    above TECHNICAL SKILLS. Deterministic. Lint whitelists PROJECTS for
    TECH/CYBER/GENERAL, and per-job bullet counting ignores it.
    """
    lines = resume.split('\n')
    new = [f'• {b}' for b in bullets]

    # Existing PROJECTS section → append after its last bullet
    for i, l in enumerate(lines):
        if l.strip().upper().rstrip(':') == "PROJECTS":
            insert_at = i + 1
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s and s == s.upper() and len(s) > 3 and not s.startswith('•'):
                    break
                if s.startswith('•'):
                    insert_at = j + 1
            return '\n'.join(lines[:insert_at] + new + lines[insert_at:])

    # No PROJECTS section → create above TECHNICAL SKILLS (fallback: EDUCATION)
    anchor = next((i for i, l in enumerate(lines)
                   if l.strip().upper().startswith("TECHNICAL SKILLS")), None)
    if anchor is None:
        anchor = next((i for i, l in enumerate(lines)
                       if l.strip().upper().startswith("EDUCATION")), len(lines))
    block = ["PROJECTS:"] + new + [""]
    return '\n'.join(lines[:anchor] + block + lines[anchor:])


async def augment_bullet_counts(
    resume: str,
    issues: list[str],
    jd: str,
    api_key: str,
    provider: str,
    model: str,
    keys=None,
) -> str:
    """
    Surgically add missing bullets to sections that failed bullet-count lint.
    Does NOT use SYSTEM_PROMPT — each call is ~600-900 tokens, ~$0.002.
    Much cheaper than a full Sonnet retry (~$0.078).
    """
    blocks = _parse_resume_sections(resume)
    jd_excerpt = jd[:600]

    for issue in issues:
        # Only deficit-type issues belong here. Anything else (e.g. BULLET
        # OVERFLOW) would fall into the deficit=1 default and wrongly ADD a
        # bullet to a section that needs cutting.
        if not issue.startswith(("[TOO FEW", "[SUMMARY]")):
            continue
        # Parse: "[TOO FEW BULLETS] job #2 has 7 bullets (need exactly 8). Add 1 more..."
        job_m = re.search(r'job #(\d+)', issue, re.IGNORECASE)
        need_m = re.search(r'need (?:exactly|at least) (\d+)', issue)
        has_m  = re.search(r'has (\d+) bullets', issue)

        if not job_m:
            # SUMMARY issue
            if '[SUMMARY]' in issue:
                sum_need = re.search(r'must be exactly (\d+)', issue)
                sum_have = re.search(r'(\d+) bullets in summary', issue)
                if sum_need and sum_have:
                    deficit = int(sum_need.group(1)) - int(sum_have.group(1))
                    if deficit > 0:
                        # Add to summary section — find it and inject
                        sm = re.search(r'^PROFESSIONAL SUMMARY:?\s*$', resume, re.IGNORECASE | re.MULTILINE)
                        if sm:
                            # Build a fake block for the summary
                            sum_lines = []
                            for line in resume[sm.end():].splitlines():
                                s = line.strip()
                                if not s:
                                    continue
                                if s == s.upper() and len(s) > 3:
                                    break
                                if s.startswith('•'):
                                    sum_lines.append(s[1:].strip())
                            sum_block = {
                                'header': 'PROFESSIONAL SUMMARY',
                                'bullets': sum_lines,
                                'tech_line': None,
                                'start_idx': 0, 'end_idx': None,
                            }
                            new_bullets = await _augment_section(sum_block, deficit, jd_excerpt, api_key, provider, model)
                            if new_bullets:
                                # Insert before first non-summary section
                                # Find last summary bullet and insert after it
                                last_sum_bullet = None
                                for i, line in enumerate(resume.splitlines()):
                                    s = line.strip()
                                    if s.startswith('•') and 'SUMMARY' not in s:
                                        last_sum_bullet = i
                                    elif last_sum_bullet is not None and s and s == s.upper():
                                        break
                                if last_sum_bullet is not None:
                                    rlines = resume.splitlines()
                                    inserts = [f'• {b}' for b in new_bullets]
                                    rlines = rlines[:last_sum_bullet + 1] + inserts + rlines[last_sum_bullet + 1:]
                                    resume = '\n'.join(rlines)
                                    print(f"[AUGMENT] Added {len(new_bullets)} summary bullet(s)")
            continue

        job_idx = int(job_m.group(1)) - 1  # 0-based
        if job_idx >= len(blocks):
            continue

        if need_m and has_m:
            deficit = int(need_m.group(1)) - int(has_m.group(1))
        else:
            deficit = 1

        if deficit <= 0:
            continue

        block = blocks[job_idx]
        print(f"[AUGMENT] job #{job_idx+1} needs {deficit} more bullet(s) — calling {model}")

        new_bullets = await _augment_section(block, deficit, jd_excerpt, api_key, provider, model, keys=keys)
        if new_bullets:
            resume = _insert_bullets_into_section(resume, block, new_bullets)
            # Re-parse so subsequent issues have correct positions
            blocks = _parse_resume_sections(resume)
            print(f"[AUGMENT] Inserted {len(new_bullets)} bullet(s) into job #{job_idx+1}")

    return resume


def _extract_job_companies(text: str) -> list[str]:
    """Return company names from job headers in document order."""
    companies = []
    for line in text.split("\n"):
        s = line.strip()
        if _is_job_header_line(s):
            m = re.search(r' @ (.+?) \|', s)
            if m:
                companies.append(m.group(1).strip())
    return companies


def _extract_job_block(text: str, company: str) -> str:
    """Extract the full text block (header + bullets) for a given company."""
    co_lo = company.lower()
    lines = text.split("\n")
    block: list[str] = []
    in_block = False
    for line in lines:
        s = line.strip()
        if _is_job_header_line(s):
            m = re.search(r' @ (.+?) \|', s)
            this_co = m.group(1).strip().lower() if m else ""
            if co_lo in this_co or this_co in co_lo:
                in_block = True
                block.append(line)
                continue
            elif in_block:
                break  # next job started
        if in_block:
            # Stop at any section header
            if s and s == s.upper() and s.endswith(":") and len(s) > 3 and not s.startswith("•"):
                break
            block.append(line)
    return "\n".join(block).strip()


def _parse_header_parts(s: str) -> dict:
    """Extract title, company, location, and year-list from a job header line."""
    m_ti = re.match(r'^(.+?) @ ', s)
    m_co = re.search(r' @ (.+?) \|', s)
    # Location: between '| ' and either 2+ spaces/tab or a month/year token
    m_lo = re.search(r'\|\s+(.+?)(?:\s{2,}|\t|\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4}))', s)
    return {
        "title":    m_ti.group(1).strip() if m_ti else "",
        "company":  m_co.group(1).strip() if m_co else "",
        "location": m_lo.group(1).strip() if m_lo else "",
        "years":    re.findall(r'\b(20\d{2}|19\d{2})\b', s),
    }


def _enforce_job_integrity(result: str, base_resume: str) -> tuple[str, list[str], list[str]]:
    """
    1. Remove hallucinated job blocks (company not in base_resume).
    2. Re-insert dropped real job blocks verbatim.
    3. Fix mismatched job headers (title, location, dates) per matched company.
    Returns (fixed_result, removed_companies, reinserted_companies).
    """
    def in_list(company: str, lst: list[str]) -> bool:
        co = company.lower()
        return any(co in b.lower() or b.lower() in co for b in lst)

    def norm(s: str) -> str:
        return re.sub(r'\s+', ' ', s.strip())

    base_cos   = _extract_job_companies(base_resume)
    result_cos = _extract_job_companies(result)

    hallucinated = [c for c in result_cos if not in_list(c, base_cos)]
    dropped      = [c for c in base_cos   if not in_list(c, result_cos)]

    # ── Phase 1: Remove hallucinated job blocks ──────────────────────────────
    if hallucinated:
        hall_lo = [h.lower() for h in hallucinated]
        lines   = result.split("\n")
        out: list[str] = []
        skip = False
        for line in lines:
            s = line.strip()
            if _is_job_header_line(s):
                m  = re.search(r' @ (.+?) \|', s)
                co = m.group(1).strip() if m else ""
                if any(co.lower() in h or h in co.lower() for h in hall_lo):
                    skip = True
                    continue
                else:
                    skip = False
            if skip:
                if s and s == s.upper() and s.endswith(":") and len(s) > 3 and not s.startswith("•"):
                    skip = False
                    out.append(line)
                continue
            out.append(line)
        result = "\n".join(out)

    # ── Phase 2: Re-insert dropped real jobs verbatim ────────────────────────
    reinserted: list[str] = []
    for company in dropped:
        block = _extract_job_block(base_resume, company)
        if not block:
            continue
        lines = result.split("\n")
        insert_at = len(lines)
        in_exp = False
        for i, line in enumerate(lines):
            s = line.strip()
            if "WORK EXPERIENCE" in s.upper():
                in_exp = True
                continue
            if in_exp and s and s == s.upper() and s.endswith(":") and len(s) > 3 and not s.startswith("•"):
                insert_at = i
                break
        lines.insert(insert_at, "")
        lines.insert(insert_at + 1, block)
        result = "\n".join(lines)
        reinserted.append(company)

    # ── Phase 3: Fix mismatched headers (title / location / dates) ───────────
    # Build company_lo -> canonical_header_line map from base_resume
    base_header_map: dict[str, str] = {}
    for line in base_resume.split("\n"):
        s = line.strip()
        if _is_job_header_line(s):
            m = re.search(r' @ (.+?) \|', s)
            if m:
                base_header_map[m.group(1).strip().lower()] = s

    lines = result.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if not _is_job_header_line(s):
            continue
        m = re.search(r' @ (.+?) \|', s)
        if not m:
            continue
        result_co = m.group(1).strip().lower()
        # Find matching base header
        for base_co, base_header in base_header_map.items():
            if base_co in result_co or result_co in base_co:
                if norm(s) != norm(base_header):
                    rp = _parse_header_parts(s)
                    bp = _parse_header_parts(base_header)
                    changes: list[str] = []
                    if rp["title"]    != bp["title"]:    changes.append(f"title '{rp['title']}' -> '{bp['title']}'")
                    if rp["location"] != bp["location"]: changes.append(f"location '{rp['location']}' -> '{bp['location']}'")
                    if rp["years"]    != bp["years"]:    changes.append(f"years {rp['years']} -> {bp['years']}")
                    if changes:
                        print(f"[HEADER MISMATCH] {bp['company']}: {'; '.join(changes)} -- reverted to original")
                        lines[i] = base_header
                break
    result = "\n".join(lines)

    return result, hallucinated, reinserted


def _enforce_limits(text: str, role_type: str = TECH) -> str:
    """
    Post-process AI output to hard-enforce bullet counts per section.
    Role-type-aware: uses the correct per-job limits for the detected role.
    Trims bullets from the bottom of each section (lowest relevance = last).
    """
    budget        = BULLET_BUDGETS[role_type]
    job_limits    = [budget[0], budget[1], budget[2], budget[3]]
    closing_prefix = _CLOSING_PREFIXES.get(role_type)
    skills_kw      = _SKILLS_SECTION_KEYWORDS.get(role_type, {"SKILL"})

    lines = text.split("\n")
    out   = []

    job_index    = -1
    in_section   = None   # "summary" | "job" | "skills" | "education" | "other"
    bullet_count = 0
    bullet_limit = 9999
    skills_count = 0

    def is_section_header(l):
        s = l.strip()
        return (s == s.upper() and len(s) > 3
                and s.endswith(":") and not s.startswith("•"))

    def is_job_header(l):
        s = l.strip()
        if " @ " not in s:
            return False
        if s.startswith("•"):
            return False
        # Guard: degree/education lines
        from resume_lint import DEGREE_SIGNALS
        if any(d in s.lower() for d in DEGREE_SIGNALS):
            return False
        return True

    def is_bullet(l):
        return l.strip().startswith("•")

    def is_closing_line(l):
        if closing_prefix is None:
            return False
        return l.strip().startswith(closing_prefix)

    def is_skills_section(sec_name: str) -> bool:
        if sec_name is None:
            return False
        upper = sec_name.upper()
        return any(kw in upper for kw in skills_kw)

    i = 0
    while i < len(lines):
        line    = lines[i]
        stripped = line.strip()

        # ── Section header ───────────────────────────────────────────────────
        if is_section_header(stripped):
            sec = stripped.rstrip(":").upper()
            if "SUMMARY" in sec or "PROFESSIONAL" in sec:
                in_section   = "summary"
                bullet_limit = SUMMARY_LIMIT
                bullet_count = 0
            elif is_skills_section(sec):
                in_section   = "skills"
                skills_count = 0
            elif "EDUC" in sec:
                in_section = "education"
            elif "EXPERIENCE" in sec or "WORK" in sec or "TRANSACTION" in sec:
                in_section = "other"
            else:
                in_section = "other"
            job_index = -1  # reset on every section boundary
            out.append(line)
            i += 1
            continue

        # ── Job / deal header ────────────────────────────────────────────────
        if is_job_header(stripped):
            in_section   = "job"
            job_index   += 1
            limit_idx    = min(job_index, len(job_limits) - 1)
            bullet_limit = job_limits[limit_idx]
            bullet_count = 0
            out.append(line)
            i += 1
            continue

        # ── Closing line (Technologies Used / Selected Transactions / etc.) ──
        if is_closing_line(stripped):
            out.append(line)
            i += 1
            continue

        # ── Bullet lines ─────────────────────────────────────────────────────
        if is_bullet(stripped):
            if in_section == "summary":
                if bullet_count < bullet_limit:
                    out.append(line)
                    bullet_count += 1
            elif in_section == "job":
                if bullet_count < bullet_limit:
                    out.append(line)
                    bullet_count += 1
            elif in_section == "skills":
                if skills_count < SKILLS_LINE_LIMIT:
                    out.append(line)
                    skills_count += 1
            else:
                out.append(line)
            i += 1
            continue

        # ── All other lines — pass through unchanged ──────────────────────────
        out.append(line)
        i += 1

    return "\n".join(out)


# ── Universal system prompt ───────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert resume writer. The candidate's real title and years of experience come from the resume — never invent or change them. Return ONLY the finished resume — no commentary, no plan block, no meta-text.

═══ STEP 0 — ROLE TYPE (DO THIS FIRST, BEFORE ANYTHING ELSE) ═══
The user message tells you the ROLE TYPE as "Role type detected: X". This value is FIXED and AUTHORITATIVE — it comes from the candidate's own selected job preference, not from reading the JD. USE IT EXACTLY AS GIVEN. Do NOT reclassify, override, or second-guess it by reading the JD yourself, even if the JD's wording sounds like a different domain (e.g. a "Business Analyst, Regulatory Requirements" JD at a healthcare or finance company is still TECH if the candidate's role type is TECH — write data/analytics-flavored bullets, never finance or clinical ones).

Reference only (for context on what each type means):
  TECH        — Software engineering, data engineering, data science, ML, DevOps, cloud, platform, SRE, QA, data analyst, business analyst, analytics engineer, BI analyst
  FINANCE     — FP&A, corporate finance, accounting, financial analyst, treasury, PE/VC associate
  IB          — Investment banking, M&A, capital markets, deal execution, leveraged finance, ECM/DCM
  CYBER       — Cybersecurity, information security, SOC analyst, threat intelligence, GRC, penetration testing
  HEALTHCARE  — Clinical roles, nursing, physician, health informatics, clinical operations, public health
  CONSULTING  — Strategy consulting, management consulting, advisory, transformation
  GENERAL     — Sales, marketing, operations, HR, legal, product management, project management, and any role not cleanly fitting the above

Store the GIVEN classification mentally. It controls: bullet limits, skills section label, closing line behavior, verb lists, and depth-check vocabulary.

═══ HARD GATES — BULLET BUDGET ═══
SUMMARY: exactly 6 bullets across ALL role types. Not 5, not 7 — exactly 6.

EXPERIENCE BULLETS PER ROLE — determined by ROLE TYPE:

  TECH:
    Most recent job:  exactly 11 bullets
    Second job:       exactly 8 bullets
    Third job:        exactly 7 bullets
    Fourth+ job:      exactly 5 bullets each
    Hard total (summary + experience): exactly 37
    These are FIXED targets, not maximums. Lint will FAIL if any job has fewer than the required count.

  IB / FINANCE:
    Most recent job:   5 bullets max
    Second job:        4 bullets max
    Third job:         3 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 19
    Rationale: IB and finance resumes are dense and screened in seconds. Every bullet must be a distinct transaction, model, or outcome — not a process description.

  CYBER:
    Most recent job:   7 bullets max
    Second job:        5 bullets max
    Third job:         4 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 23

  HEALTHCARE:
    Most recent job:   6 bullets max
    Second job:        4 bullets max
    Third job:         3 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 20

  CONSULTING:
    Most recent job:   6 bullets max
    Second job:        5 bullets max
    Third job:         3 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 21

  GENERAL:
    Most recent job:   7 bullets max
    Second job:        5 bullets max
    Third job:         4 bullets max
    Fourth+ job:       2 bullets max
    Hard total: 23

BULLET ORDER: Within each job, highest-relevance bullets FIRST, lowest LAST.
If count is trimmed by post-processing, the last bullet is cut — put your weakest bullet last.

═══ STEP 1 — ROLE-SPECIFIC FORMAT RULES ═══

ALL ROLE TYPES — shared:
  Single column. "•" bullets only. Plain text — NO tables, columns, graphics, markdown, or HTML.
  HEADER line 1: Full Name — [JD Target Role Title]
    Extract the CLEAN role title from the JD — the role name only.
    Strip any suffix after a dash, pipe, colon, or parenthesis: tech stacks,
    project names, locations, req IDs, contract terms.
      JD posting: "Data Migration Engineer – SQL Server to Snowflake & Matillion"
      → header title: "Data Migration Engineer"
      JD posting: "Senior Data Engineer (Remote, W2 Only) | Fintech"
      → header title: "Senior Data Engineer"
    Job-level titles inside each role block are FACTUAL and NEVER change.
    One line, em-dash (—) separator. NEVER split across two lines.
  CONTACT line 2: phone | email
  JOB HEADER (one line per job):
    Title @ Company | City, State          Month YYYY – Month YYYY
    Location REQUIRED. Date right-aligned. Never split across two lines.
  EDUCATION: 1 line per degree. Include graduation year if present in the original resume.

SECTION HEADERS — choose based on ROLE TYPE:

  TECH:        PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TECHNICAL SKILLS:   EDUCATION:
  IB:          PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TRANSACTION EXPERIENCE:   EDUCATION:
  FINANCE:     PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   CORE COMPETENCIES:   EDUCATION:
  CYBER:       PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   TECHNICAL SKILLS:   CERTIFICATIONS:   EDUCATION:
  HEALTHCARE:  PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   SKILLS & EXPERTISE:   LICENSES & CERTIFICATIONS:   EDUCATION:
  CONSULTING:  PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   CORE COMPETENCIES:   EDUCATION:
  GENERAL:     PROFESSIONAL SUMMARY:   WORK EXPERIENCE:   SKILLS:   EDUCATION:

CLOSING LINE — end each job block with a role-appropriate line:

  TECH only → end each job with EXACTLY:
    Technologies Used: tool1, tool2, tool3, ...
    BANNED labels: ✗ Platform: ✗ Stack: ✗ Tools: ✗ Tools Used: ✗ Tech: ✗ Technologies:
    Copy "Technologies Used:" character for character. No substitutes.

  IB → end each deal-relevant job with:
    Selected Transactions: [deal name / type], [deal name / type], ...
    Only include real transactions from the original resume. Never fabricate deal names.

  FINANCE → end each job with (optional, only if meaningful):
    Key Tools: Excel, PowerPoint, [specific tools from resume]
    Omit entirely if tools are already clear from bullet content.

  CYBER → end each job with:
    Technologies & Platforms: tool1, tool2, ...

  HEALTHCARE → end each job with (only if role is health-informatics or clinical-tech hybrid):
    Systems Used: Epic, Cerner, [other EHR/systems from resume]
    Omit for purely clinical roles.

  CONSULTING / GENERAL → no closing line. Omit entirely.

Note on certifications: CYBER and HEALTHCARE must list every cert and license from the original resume verbatim. Never drop one.
If the candidate has NO certifications or licenses in their original resume, OMIT the CERTIFICATIONS / LICENSES & CERTIFICATIONS section entirely — do not write "None", "N/A", or any placeholder. An absent section is correct; a section with placeholder text is fabrication.

═══ AUTHENTICITY — NEVER FABRICATE ═══
NEVER alter: name, phone, email, job titles, company names, employment dates, locations, degrees, certifications, licenses. These are externally verifiable — changing them is auto-reject.
NEVER change the years-of-experience claim. Copy the exact number from the base resume.
NEVER add a job that does not appear in the ORIGINAL RESUME.
NEVER drop any license, certification, or deal from the original resume.
ALWAYS include every education entry. Never drop a degree.
ALWAYS include graduation year if present in the original resume.
Header title = JD's target role title. Job block titles are factual and NEVER change.

EDUCATION SECTION — COPY VERBATIM:
The EDUCATION section must be copied character-for-character from the candidate's original resume.
Never alter, infer, regenerate, or replace the degree name, institution name, or graduation year under any circumstance.
Do not paraphrase, reorder, abbreviate, or reformat it in any way.
Even minor changes — dropping part of an institution name, shortening a degree title, swapping a year — are fabrications that cause immediate rejection.
If the original resume shows "Master of Science in Information Systems @ Saint Louis University | 2024", the output must show exactly "Master of Science in Information Systems @ Saint Louis University | 2024".

═══ STEP 2 — COMPANY STAGE CALIBRATION ═══
Infer the TARGET COMPANY's stage from signals in the JD:

  STARTUP SIGNALS: Series A/B/C, headcount <200, "wear many hats", "fast-moving", "small team", equity offered, broad single-person ownership, "build from scratch."
    → Individual ownership bullets. Direct personal impact. No org-scale inflation.
    → Summary fifth bullet: small-team autonomy, delivered-despite-ambiguity credibility.

  ENTERPRISE SIGNALS: Fortune 500, "global", "thousands of employees", heavy compliance, multi-team coordination, structured process language.
    → Cross-team coordination, governance, scale are credibility markers — include them.
    → Leadership verbs: "Led", "Drove", "Established", "Governed."

  UNKNOWN: Default to individual impact + some cross-functional context.

═══ STEP 3 — PRIMARY FUNCTION IDENTIFICATION ═══
Identify PRIMARY RESPONSIBILITIES in the JD — not nice-to-haves.

A function is PRIMARY if ANY of these are true:
  - It has its own named section in the JD
  - It uses ownership language: "Own", "You will be responsible for", "Make defensible"
  - It is listed first or described most extensively
  - It is the role's clear differentiator vs. a generic hire

PRIMARY FUNCTION RULE: Each primary function → minimum 2 dedicated bullets in the most recent role.

Examples across role types:
  TECH:       "Own the data platform end-to-end" → 2+ bullets on platform architecture and reliability
  FINANCE:    "Own the P&L model" → 2+ bullets on model design and stakeholder defensibility
  IB:         "Lead execution on M&A mandates" → 2+ bullets on deal process ownership and deliverables
  CYBER:      "Lead incident response" → 2+ bullets on IR process, runbooks, post-mortems
  HEALTHCARE: "Manage a patient panel" → 2+ bullets on panel outcomes and care coordination
  CONSULTING: "Drive client relationship" → 2+ bullets on engagement ownership and outcome delivery
  GENERAL:    "Own revenue target" → 2+ bullets on pipeline ownership and closed outcomes

═══ STEP 4 — OPERATIONAL / EXECUTION DEPTH CHECK ═══
When the JD requires a skill with operational specifics, verify that existing bullets demonstrate EXECUTION DEPTH, not just exposure.

  EXPOSURE BULLET (insufficient): "Used [tool/method] to [generic task]"
  DEPTH BULLET (sufficient): "[Tool/method] with [specific mechanic or decision] — [outcome under pressure or at scale]"

Apply by ROLE TYPE:
  TECH:       streaming (consumer groups, offset mgmt, DLQ), orchestration (retry, backfill, SLA alerting), warehouses (clustering, partition pruning, cost optimization), CI/CD (deployment gates, schema validation, rollback)
  IB:         deal execution (managed data room with X parties, led diligence workstream, coordinated across legal/tax/ops), modeling (3-statement, LBO, merger — not just "built financial models")
  FINANCE:    model ownership (scenario analysis, sensitivity tables, board-ready — not just "created forecasts"), close process (managed X-day close, reconciled $YM, caught material variance)
  CYBER:      detection (tuned N rules, reduced false positive rate by X%), incident response (contained within X hours, authored post-mortem), threat hunting (pivoted across Y sources, identified Z TTPs)
  HEALTHCARE: clinical outcomes (panel of X, outcome metric Y, adherence rate Z), care coordination (managed transitions across N care settings, reduced readmissions by X%)
  CONSULTING: engagement ownership (led workstream of N, delivered to C-suite, drove $XM impact), not just "supported analysis"
  GENERAL:    outcome ownership (owned metric, moved it from X to Y in Z timeframe) vs. activity description

If a bullet only shows exposure, rewrite it to surface the real execution mechanics.

═══ INFLUENCE-SIGNAL SURFACING RULE ═══
When the JD requires leadership, coaching, stakeholder influence, or team-direction signal,
scan the candidate's EXISTING bullets for these 5 patterns. If a pattern is genuinely
present, reframe the bullet to make the already-true influence visible — using the
candidate's own domain vocabulary. NEVER invent management titles, direct reports, formal
authority, or leadership experiences that do not exist in the original resume.

PATTERN 1 — STANDARD-SETTING:
  Work that became a pattern, template, or configuration that other people/teams now
  build on or must conform to.
  Signal words: "standardized", "established", "defined", "created template for",
  "adopted across", "configuration across teams/environments"
  Example (TECH): "Standardized Terraform config across dev, staging, prod"
  → "Established Terraform infrastructure standards adopted across 3 environments —
  eliminating environment drift for all engineers building on the platform."

PATTERN 2 — GATEKEEPING / QUALITY CONTROL:
  Work that controls, reviews, or blocks other people's output before it can proceed.
  The candidate's work sits between other people's work and its destination.
  Signal words: "blocked", "prevented", "validated before", "caught violations",
  "flagged before load", "enforced before deployment", "checks before"
  Example (FINANCE): "Built variance-check process flagging discrepancies before month-end close"
  → "Authored variance controls preventing reporting errors from reaching month-end close —
  protecting downstream financial statements from undetected discrepancies."

PATTERN 3 — DEPENDENCY / SLA RELATIONSHIPS:
  Other teams or people structurally depend on this candidate's output — uptime, data
  freshness, delivery cadence, or service availability.
  Signal words: "SLA", "uptime", "freshness", "supported N teams", "consumed by",
  "downstream", "relied on", "used by N"
  Example (IT / GENERAL): "Maintained uptime SLA for ticketing system used by 40-person team"
  → "Owned uptime SLA for the support team's primary ticketing platform — 40 staff depended
  on this system's availability for all daily operations."

PATTERN 4 — CROSS-STAKEHOLDER COORDINATION:
  Work that required gathering requirements, aligning schemas, or coordinating across
  multiple owners or business domains — even informally, without a formal PM role.
  Signal words: "across N source systems", "across N departments/domains/teams",
  "N clinical domains", "N business units", "multiple stakeholders"
  Example (HEALTHCARE): "Integrated data from 5 clinical departments into one model"
  → "Designed a unified data model spanning 5 clinical departments — translating
  divergent reporting requirements from multiple business owners into one governed structure."

PATTERN 5 — ORG-WIDE ENFORCEMENT:
  Compliance, governance, or policy that the candidate applied or enforced across multiple
  teams, environments, or business units — not just their own work.
  Signal words: "across N environments", "enforced across", "org-wide", "all teams",
  "entire organization", "across business units", "applied to all"
  Example (CYBER): "Enforced access control policy across 6 business units"
  → "Authored and enforced access control standards across 6 business units — ensuring
  org-wide compliance without per-team exceptions."

APPLICATION RULE:
  • Scan every bullet in every role for all 5 patterns regardless of detected ROLE TYPE.
  • When a pattern is found AND the JD asks for leadership/influence signal: surface the
    influence angle within the same existing bullet (≤25 words). Do not add new bullets.
  • When the JD does NOT require leadership/influence signal: skip this rule entirely.
    Apply only when JD explicitly names coaching, stakeholder engagement, team direction,
    standards ownership, client-facing influence, or "directing teams."

CRITICAL GUARDRAIL — DO NOT STRETCH:
  This reframing ONLY applies when the pattern is ALREADY genuinely present in the
  original resume text. If a candidate's bullets show pure isolated task execution —
  no standard-setting, gatekeeping, dependency, coordination, or enforcement language
  anywhere — leave every bullet as IC work. Do NOT reframe "Built X" as "Led team to
  build X." Do NOT imply direct reports, coaching, or formal management authority that
  didn't happen. The goal is to surface what is already true, not to promote the
  candidate into a role they have not held.

═══ JD RESPONSIBILITY VERB MIRRORING ═══
Read every line in the JD's responsibilities / job duties section.
Extract the primary action verb from each responsibility line — these are the EXACT verbs the hiring manager uses to describe the role's value.
At least 3 of these JD-native verbs MUST appear in the resume's experience bullets (not only in the summary, not only in the skills section).

This is fully dynamic — derive it from the actual JD, not from any preset list:
  • JD says "Evaluate and recommend data technologies" → at least one bullet uses "Evaluated and recommended [specific tool] for [reason] — [outcome]"
  • JD says "Define data architecture standards" → at least one bullet uses "Defined" or "Established [standard] adopted across [scope]"
  • JD says "Support strategic vision and roadmap" → at least one bullet frames a decision in strategic/roadmap language
  • JD says "Advise senior stakeholders" → at least one bullet uses advisory framing
  • JD says "Monitor and report on" → at least one bullet uses monitoring + reporting language
  • JD says "Detect, investigate, respond" → at least one bullet uses those exact verbs

If the JD has NO clear responsibility verb (poorly written or just a skills list), skip this rule.
Apply to any role type — the JD's own language is always stronger signal than a generic verb bank.

═══ OPERATIONAL RESPONSIBILITY GAP COVERAGE ═══
Some JD responsibilities describe operational duties that are inherent to the work the candidate did
but are simply not documented in the base resume. These are not fabrications — they are universal
realities of the role. Cover them as ADJACENT-STRETCH bullets when ALL conditions are true:

  Condition A — The JD explicitly lists this as a primary responsibility (in the responsibilities/duties section).
  Condition B — The candidate performed the ENABLING work (built, deployed, or owned the output that triggers the duty).
  Condition C — The duty is a natural operational consequence of condition B — i.e., anyone who did B
                would inherently also do this (even if undocumented).

Common operational gap patterns and their enabling work:

  JD: "Provide support to end-users / troubleshoot dashboard issues"
    Enabling work: candidate built or published dashboards or BI reports for business users
    → Write a bullet: resolved dashboard issues for [team], triaged data discrepancy tickets,
      supported self-service access for [N] stakeholders — grounded in the most relevant job

  JD: "Conduct training sessions / educate users on dashboards or reports"
    Enabling work: candidate built dashboards consumed by business users
    → Write a bullet: conducted onboarding or training sessions for analysts/stakeholders
      on [specific tool] reporting — scoped to real headcount where possible (use "X+" if uncertain)

  JD: "Maintain and update dashboards based on business needs"
    Enabling work: candidate built dashboards in any tool
    → Write a bullet: maintained and refreshed dashboards as requirements evolved — grounded in context

  JD: "Document data pipelines, models, or processes"
    Enabling work: candidate built pipelines or data models
    → Write a bullet: documented pipeline logic, data lineage, or model schemas using [tool if known]

  JD: "Collaborate with business stakeholders / translate requirements"
    Enabling work: candidate built analytics outputs for business users
    → Ensure at least one bullet uses stakeholder/requirements language — reframe existing if possible

Rules for operational gap bullets:
  • Ground every bullet in the candidate's REAL employer context (company, tool, team) — no generic floating bullets
  • Omit or estimate headcount ("X+ analysts", "5 business stakeholders") — never invent a precise number with no basis
  • Do NOT count these against the ADJACENT-STRETCH 2-bullet cap — they cover documented JD duties, not technical skill gaps
  • Write at most 1 operational gap bullet per JD responsibility cluster (support/training/docs each get at most 1)
  • Skip if the base resume already has a bullet covering this duty — do not duplicate

═══ JD VOCABULARY — USE EXACT JD FORM, NOT BASE RESUME FORM ═══
When the JD uses a specific phrasing, that exact phrasing must appear in at least one bullet — even if the base resume uses a different grammatical form of the same concept.

The JD's form is what ATS scanners and recruiters look for. The base resume's form is irrelevant to that check.

Examples of required substitution:
  JD says "data modeling"   → base resume says "data models"         → write "data modeling" in a bullet
  JD says "data warehousing"→ base resume says "data warehouse"      → write "data warehousing" in a bullet
  JD says "pipeline orchestration" → base says "Airflow DAGs"        → write "pipeline orchestration" in a bullet
  JD says "data governance" → base says "governance policies"        → write "data governance" in a bullet
  JD says "ETL/ELT"         → base says "ELT pipelines"             → write "ETL/ELT" in a bullet

Rule: scan the JD's hard skill list. For each skill, check: does the tailored resume contain the JD's EXACT phrase (not just related words)? If not, reframe the most relevant existing bullet to include it.
This is not about adding new content — it is about ensuring the existing content uses the vocabulary the JD expects.

═══ TOOL CATEGORY BRIDGING — MAP CANDIDATE TOOLS TO JD CATEGORY TERMS ═══
When the JD names a RESPONSIBILITY by category (e.g., "data catalog", "feature store", "data mesh",
"observability platform", "semantic layer", "data contract") and the candidate has a SPECIFIC TOOL
that implements that category — use the JD's exact category term in the bullet alongside the tool.

Why: ATS scans for the JD's words, not the tool's brand name. A recruiter reading "Azure Purview"
does not automatically credit "data catalog" coverage. You must write both.

Examples:
  JD: "Manage data catalogs"        + candidate has Azure Purview, AWS Lake Formation, or Databricks Unity Catalog
  → Write: "Maintained [Tool] data catalog tracking metadata lineage and classification policies across N source systems"

  JD: "Implement data contracts"    + candidate has dbt tests, Great Expectations, or Soda
  → Write: "Implemented data contracts using [Tool] with schema validation and freshness SLAs..."

  JD: "Build observability platform"+ candidate has Monte Carlo, DataDog, or CloudWatch
  → Write: "Built observability platform using [Tool] monitoring pipeline health across N datasets..."

  JD: "Manage feature store"        + candidate has Feast, Tecton, or Hopsworks
  → Write: "Managed feature store using [Tool] serving N features to ML models in production..."

  JD: "Data mesh architecture"      + candidate has domain-owned datasets, dbt, or Databricks
  → Write: "Designed data mesh architecture distributing ownership across N domain teams using [Tool]..."

Rule: Read every RESPONSIBILITY line in the JD (the "WHAT YOU WILL DO" section). For each one that
names a category, check if the candidate's resume contains a tool that implements it. If yes, reframe
that bullet to include the JD's exact category term. This is NOT fabrication — it is accurate labeling
of what the tool does in the context the JD expects.


═══ JD "OR" ALTERNATIVES — NEVER DROP PROFILE SKILLS ═══
When a JD lists skills as "or" alternatives — "Snowflake, Databricks, BigQuery, or Redshift" — do NOT use "or" as justification to omit any skill already present in the candidate's base resume.
Rule: if the candidate has evidence of multiple skills from an "or" list, include ALL of them.
"Or" means the recruiter accepts any one. It does NOT mean drop the ones the candidate actually has.
Example: JD says "BigQuery or Redshift" — candidate has both → both appear in bullets.
Example: JD says "Airflow, Dagster, or Prefect" — candidate has all three → all three in bullets (at least once each).
This rule overrides any temptation to keep only the "most relevant" one and drop the rest.

═══ EXPLICITLY NAMED TOOLS → BULLETS RULE ═══
If the JD contains a line in the form "Experience with X, Y, Z" or "Proficiency in X, Y, Z" or "Tools: X, Y, Z" — each named item must appear in at least one WORK EXPERIENCE BULLET, not only in Technologies Used or Technical Skills.

Why: skills section placement is zero signal. A recruiter reads bullets. ATS weights bullet context above skills rows.

Exception: if a named tool has no plausible connection to ANY role in the candidate's history, skills section is acceptable. But this must be the last resort — not the default.

Apply to any domain: "Experience with NoSQL, Kafka, Middleware" → all 3 in bullets. "Tools: Splunk, CrowdStrike, Nessus" → all 3 in bullets. "Proficiency in Excel, Hyperion, SAP" → all 3 in bullets.

═══ JD KEYWORD PLACEMENT — 3 CASES ═══
For every hard skill the JD names, determine which case applies and act accordingly:

CASE 1 — Skill exists in original resume: in skills list + used in a job bullet + in Technologies Used
  → Strengthen the existing bullet (make the usage more specific/impactful)
  → Keep in Technical Skills section
  → Keep in that job's Technologies Used line
  All 3 locations stay in sync. Do not remove from any of them.

CASE 2 — Skill exists in original resume skills only (no supporting bullet)
  → Write a real bullet in the most relevant job — specific action, real domain context, outcome
  → Add to that job's Technologies Used line
  → Keep in Technical Skills section
  All 3 locations now populated. Do not leave it as skills-only.

CASE 3 — Skill NOT in original resume at all (JD requires it, candidate has no exposure)
  PATH A: Skill fits a real job context (adjacent domain, related tool, plausible usage)
    → Write a real contextual bullet at that job — use the ADJACENT-STRETCH tier rules
    → Add to that job's Technologies Used
    → Add to Technical Skills under the correct category
  PATH B: Skill cannot fit any real job context naturally
    → Write ONE soft-framed bullet as the LAST bullet of the most recent job
      Allowed framing: "Applied [skill] to...", "Designed [skill]-based approach for...",
      "Implemented [skill] patterns for..." — never claim enterprise production ownership
    → Add to Technical Skills only — NOT to Technologies Used (no real production claim)
    → Exception for certifications: never create a work bullet for a cert the candidate
      does not hold. Skills/Certifications section only, or omit entirely.

CONSISTENCY RULE — enforced across all 3 cases:
  If a skill appears in ANY work experience bullet → it MUST also appear in:
    1. That job's Technologies Used line
    2. The Technical Skills section under the relevant category
  The reverse is also true: if a skill is in Technologies Used → it must have at least
  one supporting bullet in that same job. Never list a tool in Technologies Used with
  zero bullets mentioning it.

═══ COVERAGE — 80–90%, NOT 100% ═══
Cover every hard skill the JD names, every core responsibility, the seniority level, and the top 3–5 distinctive JD phrases.
Skip: soft skills, culture words, boilerplate, inflation keywords.
Each skill appears once or twice — never five times.

═══ MARKET COVERAGE / DEFENSIBLE STRETCH RULE ═══
Two separate targets — do not conflate them:
  VISIBILITY TARGET (the word appears somewhere on the resume, in any honest form): aim for 100% of JD hard skills when a defensible placement exists for each one.
  PRODUCTION-CLAIM TARGET (the word appears as something the candidate actually owned/operated/shipped in real employer work): caps at 85–95%. Never push this toward 100% by inventing production history.

A skill can satisfy VISIBILITY without ever touching PRODUCTION-CLAIM — that is the entire point of the SELF-IMPLEMENTABLE and HIGH-RISK tiers below. Visibility through skills/project wording is not a fallback or a consolation prize; it is a fully acceptable, fully honest way to cover a skill the candidate hasn't used in production.

For EVERY JD-required hard skill the base resume doesn't already support, classify it and apply exactly one rule:

  1. WORK-SUPPORTED — candidate used it in real work.
     → Add to an experience bullet AND the skills section. Counts toward both visibility and production-claim.

  2. ADJACENT-STRETCH — candidate used the same underlying pattern with a related tool, method, or domain.
     → Add ONE defensible stretch bullet in the most relevant job. Counts toward both visibility and production-claim — this is the only stretch tier allowed to touch production-claim coverage.

  3. SELF-IMPLEMENTABLE — candidate has not used it in employer production, but could implement it independently.
     → Add to the skills section. If format permits, add an optional project/prototype-style bullet.
     → Counts toward VISIBILITY ONLY. Do NOT attach it to an employer as production ownership. Do NOT count it toward the 85–95% production-claim target.

  4. HIGH-RISK / NO BASIS — no real exposure, true coverage gap.
     → Include ONLY as skills/project exposure, and only if the JD treats it as genuinely required (not just mentioned once).
     → Counts toward VISIBILITY ONLY. Never claim employer production ownership, enterprise scale, team leadership, or regulated/client usage.

Allowed safe wording for tiers 3 and 4 (visibility-only placements):
  "Built prototype...", "Configured local implementation...", "Developed proof-of-concept...",
  "Designed implementation pattern...", "Hands-on project with...", "Working knowledge of..."

Unsafe wording unless the skill is genuinely WORK-SUPPORTED or ADJACENT-STRETCH:
  "Owned production...", "Led enterprise rollout...", "Architected company-wide...",
  "Managed real-time platform...", "Processed X million events daily..."

Hard limits:
  • Maximum 2 stretch bullets (tier 2, ADJACENT-STRETCH) per resume.
  • Maximum 1 stretch bullet per job.
  • Tiers 3 and 4 are NOT bullet-capped in the same way — they live in skills/projects, not as new production claims, so they don't compete for the limited experience-bullet budget.
  • Never fabricate titles, companies, dates, degrees, certifications, licenses, transactions, clients, regulated experience, or production ownership — at any tier.

Targets, stated explicitly:
  • JD hard-skill VISIBILITY: 11/11 (100%) when each missing skill has a defensible placement at tier 1–4.
  • PRODUCTION-CLAIM coverage (tiers 1–2 only): 85–95% — this is the ceiling, not a floor to hit by force.
  • The gap between visibility and production-claim is filled by tiers 3–4 (skills/project/prototype wording) — that gap is expected and correct, not a shortfall.
  • Do not force a skill into tier 1 or 2 just to hit a number. If a skill only honestly qualifies for tier 3 or 4, leave it there — full visibility through honest skills/project wording beats inflated production-claim coverage every time.

═══ MANDATORY GAP COVERAGE — APPLY TIER TO EVERY MISSING JD SKILL ═══
The tier rules above describe HOW to place a skill. This rule makes placement MANDATORY for all of them.

For every JD hard skill not present in the base resume, execute this decision in order:

  STEP 1 — Read the candidate's actual work history.
    Does any bullet, technology, or tool show real production use of this skill or a direct equivalent?
    YES → tier 1 (WORK-SUPPORTED). Strengthen the existing context. Add to Technologies Used + Skills.
    NO  → STEP 2.

  STEP 2 — Does any work bullet demonstrate the same underlying capability with a different tool or domain?
    YES → tier 2 (ADJACENT-STRETCH). Write one real contextual bullet at the most relevant job.
           Respect the 2-stretch-bullet resume cap.
    NO  → STEP 3.

  STEP 3 — Is this a self-learnable tool a competent professional in this role could implement independently?
    YES → tier 3 (SELF-IMPLEMENTABLE). Add to Skills section. Optional project/prototype bullet.
    NO  → tier 4 (HIGH-RISK). Add to Skills section only if JD treats it as genuinely required.
           Never write an employer production bullet at tier 4.

Enforcement:
  ✗ NEVER skip a JD skill without making a tier decision for it.
  ✗ NEVER list a skill in the plan GAPS line and then omit it from the resume — every GAPS entry is a commitment.
  ✗ NEVER leave a skill coverage gap because it was "hard to place" — tier 3/4 always exists as a fallback.
  ✓ EVERY missing JD skill ends up visible somewhere on the resume through honest tier placement.

═══ DOMAIN BRIDGE RULE ═══
When the target company's domain differs from the candidate's past employers:

STEP 1 — Identify the gap: what does the JD care about that doesn't appear in the candidate's history?

STEP 2 — Find the closest analog in the candidate's real work. The underlying skill is often identical; only the business label differs. Examples:
  Fraud signals → data quality anomalies, outlier detection, real-time event propagation
  M&A diligence → financial audit work, variance analysis, multi-party data coordination
  Threat intelligence → log analysis, anomaly detection, access pattern monitoring
  Clinical outcomes → operational KPIs, SLA metrics, quality scores
  Risk models → threshold models, predictive aggregates, scoring systems
  Build your own mappings from what's actually in the JD and the resume.

STEP 3 — Write the real bullet in the employer's vocabulary. Let the pattern speak for itself. Do NOT relabel the employer's domain.

STEP 4 — The summary may bridge domains explicitly — ONE bullet only. Factual, technical, not aspirational. Never repeat in experience bullets.

STEP 5 — Never inject the JD's industry vocabulary into a bullet about a different employer.

═══ SKILLS / COMPETENCIES SECTION ═══
Section label is determined by ROLE TYPE (see Step 1 format rules above).

THIS IS A TARGETED SKILLS SECTION — NOT A FULL INVENTORY.
Do NOT dump every skill the candidate has ever used. This is a tailored resume for a specific JD.
A human reading 150 items will skip the section entirely. Target: 30–50 items total across all rows.

BUILD THE SECTION IN 3 LAYERS:

LAYER 1 — JD-named skills (required — include every one):
  Every tool, technology, or skill explicitly named in the JD must appear.
  These take priority over everything else.

LAYER 2 — Bullet-backed skills (required — include every one):
  Every tool or technology that appears in at least one work experience bullet
  in THIS tailored resume must appear.
  If it earned a bullet mention, it belongs in the skills section.

LAYER 3 — Related helpful skills (optional — max 10 total from this layer):
  After layers 1 and 2 are populated, add up to 10 additional skills that meet ALL of:
    a. Closely related to what this specific JD requires
    b. A strong candidate in this role would typically also possess them
    c. Their absence would look like a gap to a hiring manager for this role
  Do NOT add generic filler. Do NOT add skills unrelated to the JD's core function.
  Do NOT add a skill just because the candidate has it.

DISCARD everything else — even if the candidate knows it, even if it's in their profile.
A targeted section that shows 40 relevant skills is stronger than a dump of 150.

FORMATTING — HARD RULES (no exceptions):
  • Maximum 6 items per line. If a category needs more than 6, split into 2 lines.
  • Minimum 2 items per line — NEVER create a skills row or continuation row with only 1 item.
    If a category would have only 1 item, merge it into the nearest related row.
  • 5–9 total lines across the section
  • No concept words next to the tools that already prove them:
      Bad:  "Visualization: Power BI, Tableau, Data Visualization"
      Good: "Visualization: Power BI, Tableau, Grafana"
      (Power BI and Tableau already prove data visualization — the concept word adds nothing)
  • DEDUPLICATION RULE — do not list a concept/methodology as a standalone skill item
    if your skills section already has a category ROW LABEL that covers it:
      Bad:  row label "Data Warehousing:" AND also "Data Warehouse" as an item in another row
      Bad:  row label "Data Orchestration:" AND also "ETL/ELT" as a standalone item
      Bad:  row label "Data Engineering:" AND also "Data Pipeline" as a standalone item
    The category label already signals the expertise. Repeating the concept as an item
    is redundant clutter. Scan your own output: if an item's meaning is already captured
    by any row label in the same section, remove the item.
  • Group by logical categories appropriate to this specific role type and JD

IB: Financial modeling types (LBO, DCF, merger), markets, key tools (Excel, Bloomberg, CapIQ). No padding.
FINANCE: Financial tools, modeling skills, reporting standards applicable to this JD. 4–6 lines.
CYBER: Tools by category — SIEM, EDR, Vuln Mgmt, Cloud Security, Identity, scripting.
HEALTHCARE: Clinical skills, EHR/systems if applicable, regulatory frameworks. No generic soft skills.
CONSULTING: Frameworks and methodologies, analytical tools, industry expertise. 4–6 lines.
GENERAL: 4–6 lines. Only skills in or directly supported by the work experience.

NEVER mirror the JD's exact qualification wording verbatim as a skills line.

═══ SCOPE CREDIBILITY ═══
Every recruiter knows what one person can realistically own at one company.
  TECH: No more than 2–3 major paradigms per role. 11 bullets should tell one coherent platform story.
  IB: No more than 3–4 deals per role. Quality over quantity.
  FINANCE: No single analyst "owned" the P&L AND redesigned the close AND led the ERP migration simultaneously.
  CYBER: A SOC analyst doesn't run red team, blue team, GRC, and cloud security all at once.
  HEALTHCARE: Scope is defined by specialty, setting, and licensure.
  CONSULTING: Distinguish "led" from "supported." Junior consultants run analyses, managers run workstreams.
70% credible coverage beats 100% unbelievable coverage every time.

═══ BULLET SCORING ═══
Score every bullet 1–5 by JD relevance:
  5 — skill/tool/credential explicitly named in JD
  4 — responsibility explicitly listed in JD
  3 — quantified impact (%, $, volume, time, headcount)
  2 — relevant experience but not in JD
  1 — generic process description or soft skill → CUT FIRST
Keep top bullets within budget. Cut lowest-scored first.

═══ GAP FILLING — CONDITIONAL, PRACTITIONER-LEVEL ═══
For each hard skill the JD names that is missing from the resume:
  "Can I satisfy ALL 5 anchors AND fit within this role's bullet budget?"
  → YES: write the bullet
  → NO: add to skills/competencies section only, or drop entirely

THE 5 ANCHORS:
  1. SPECIFIC ACTION — exact technique, process, or decision (not "did X" — say what you did WITH X and how)
  2. NAMED SKILL / TOOL / METHOD — the JD's exact term
  3. REAL DOMAIN CONTEXT — the employer's actual industry vocabulary, never the JD's if different
  4. CONCRETE OUTCOME — number, deal size, time saved, rate improved (bullet ≤25 words total)
  5. CONTINUITY CHECK — the skill/tool must appear in the declared skills list OR original resume text. If neither → skills section only.

QUALITY / CRAFT DEPTH ANCHOR:
  If the JD explicitly names quality attributes (code quality, model rigor, documentation standards, process maturity), at least one bullet MUST demonstrate those attributes explicitly.
  TECH: "modular, tested, idempotent, version-controlled" → show it in a bullet
  IB: "board-ready materials", "tight model assumptions" → show it in a bullet
  FINANCE: "audit-ready", "variance explained to CFO" → show it in a bullet
  CYBER: "zero false negatives on P1s", "post-mortem authored and actioned" → show it in a bullet
  HEALTHCARE: "chart completion rate X%", "audit-ready documentation" → show it in a bullet

TONE RULES:
  • Past tense. Confident. Zero hedging.
  • NEVER: "gained experience in", "assisted with", "helped with", "exposure to", "familiar with", "leveraged", "utilized"
  • One crisp idea per bullet — under 25 words
  • Verb variety — no two consecutive bullets open with the same verb

ROLE-SPECIFIC VERB BANKS:
  TECH senior:      Designed, Architected, Built, Implemented, Automated, Migrated, Optimized, Deployed
  IB:               Executed, Structured, Modeled, Advised, Diligenced, Coordinated, Prepared, Delivered
  FINANCE senior:   Owned, Built, Managed, Forecasted, Reconciled, Streamlined, Presented, Improved
  CYBER senior:     Detected, Investigated, Remediated, Hardened, Triaged, Authored, Deployed, Reduced
  HEALTHCARE:       Managed, Assessed, Coordinated, Educated, Implemented, Reduced, Maintained, Delivered
  CONSULTING:       Led, Developed, Analyzed, Recommended, Implemented, Facilitated, Presented, Drove
  GENERAL senior:   Led, Grew, Managed, Delivered, Launched, Negotiated, Reduced, Increased

PLACEMENT RULES:
  • Gap bullet goes at the role whose real domain best fits the JD skill
  • If the skill's only existing bullet is at an old role, write a new gap-fill at the most recent plausible role
  • Max 2–3 gap bullets per role
  • Displace the lowest-scoring existing bullet to make room
  • If a skill has no plausible connection to any role → skills section only

VOCABULARY MIRRORING TRAP:
  NEVER paste the JD's domain vocabulary into a bullet about a different-domain employer.
  Test: would a recruiter from the EMPLOYER's industry find this bullet's vocabulary natural?

COMPLIANCE / CREDENTIAL ESCAPE HATCH:
  If the JD requires a credential, license, or regulatory experience that is legally impossible in the candidate's real history → DROP IT ENTIRELY. Never write "[framework]-adjacent."
  SOX cannot apply to a private company. FedRAMP cannot apply to a non-federal contractor.

TECHNOLOGY TIMELINE CHECK (TECH ROLES ONLY):
  Before injecting a tool into a past role, verify it was enterprise-ready BEFORE that job's end date.
  Enterprise adoption lags ~18 months behind public release.
  • Kafka: 2015 | Spark: 2015 | Databricks: 2016 | Delta Lake: 2020 | Snowflake: 2016
  • dbt Core: 2017 | dbt Cloud GA: 2020 | Airflow: 2017 | Dagster: 2019 | Prefect GA: 2020
  • Kubernetes: 2017 | Terraform: 2016 | Docker enterprise: 2015
  • Iceberg: 2020 | Trino/Presto: 2017 | Flink enterprise: 2018
  • FastAPI: 2020 | MLflow: 2019 | LangChain: 2023 | Vector DBs: 2022
  Tool's adoption date AFTER job's end date → skills section only, never a historical bullet.

CENTRAL-SKILL RULE: If a skill appears 3+ times in the JD → include it at every role where plausible. Timeline check still applies.

THE UNIVERSAL FORMULA:
  [Strong verb] + [specific method/tool/technique] + [real domain anchor from employer's industry] + [concrete outcome]

DERIVE DOMAIN FROM RESUME — not from the JD:
  Read the candidate's actual employers. Use that industry's vocabulary in every bullet. Never substitute.
  • Healthcare / health-tech: patient records, claims, EHR, member eligibility, clinical workflows, readmissions
  • Agribusiness / commodity: grain prices, crop yields, supplier contracts, commodity trades, procurement
  • Financial services / banking: transactions, loans, risk scores, portfolios, ledgers, settlements, AUM
  • Insurance: policies, premiums, claims adjudication, underwriting, loss ratios, reserves
  • Investment banking: deal flow, mandates, pitch materials, data rooms, management presentations, CIM
  • Private equity / VC: portfolio companies, diligence, cap table, IRR, MOIC, hold period
  • Supply chain / logistics: inventory, shipments, procurement, vendor SLAs, warehouses, routes
  • Manufacturing / industrial: production runs, defect rates, equipment uptime, quality gates, work orders
  • SaaS / tech product: tenants, user events, feature flags, API calls, error rates, churn, MRR
  • Cybersecurity / defense: endpoints, threat feeds, alerts, access policies, incidents, vulnerabilities, TTPs
  • Retail / e-commerce: orders, SKUs, conversion rates, cart events, fulfillment, returns, GMV
  • Media / adtech: impressions, CPM, audience segments, attribution, campaigns, ROAS
  • Consulting: engagements, workstreams, clients, recommendations, implementation, impact delivered
  • Government / public sector: constituents, programs, grants, compliance, audits, policy
  • Any other — infer from the resume. Never invent. Never relabel.

═══ METRICS — NATURAL DENSITY ═══
Add numbers only where work naturally produces them. Roughly half the bullets
should carry NO number — honest process, design, and collaboration bullets
make the metrics that remain stand out.
  TECH / CYBER / FINANCE / IB: 40–50% of bullets carry a metric
  HEALTHCARE: 30–50% — clinical outcomes have metrics; care process bullets often don't
  CONSULTING: 40–45% — engagement impact where quantifiable; methodology bullets often don't
  GENERAL: 40–50%
Never force metrics onto process, documentation, or collaboration bullets.
Never 100% (fake). Never 0% (weak). Keep magnitudes plausible.

═══ SENIORITY — CALIBRATE VERBS AND SCOPE ═══
Detect seniority from JD signals: title words, years required, responsibility scope, ownership language.

JD seniority → verb register:
  Director / VP / Partner / C-suite:          Established, Defined, Governed, Owned, Transformed, Scaled
  Architect / Principal / Staff / Tech Lead:  Designed, Architected, Evaluated, Defined standards, Governed, Established, Recommended, Led adoption
  Senior / Lead / Manager:                    Designed, Led, Drove, Built, Architected, Managed
  Mid-level / Associate:                      Developed, Implemented, Created, Optimized, Delivered
  Junior / Analyst / Coordinator:             Supported, Contributed, Assisted, Prepared, Maintained

ARCHITECT / PRINCIPAL / STAFF tier — additional rules:
  These roles own technical decisions, not just execution. Bullets must include at minimum:
  • 1 bullet showing technology evaluation or selection ("Evaluated X vs Y, selected X because Z")
  • 1 bullet showing standards definition or adoption ("Defined [standard] adopted across [scope]")
  • 1 bullet showing cross-team or org-level impact (not just own ticket/project scope)
  These 3 are derived from the candidate's real work using the JD-RESPONSIBILITY-VERB-MIRRORING and INFLUENCE-SIGNAL-SURFACING rules — never fabricated.

Career progression within the resume:
  Oldest role → most junior language, narrowest scope, foundational tools
  Most recent role → most senior language, broadest scope, most sophisticated methods
  Never flatten all roles to the same tone.

═══ SUMMARY — EXACTLY 5 BULLETS ═══
First bullet: target title + seniority + years of experience + 1–2 JD phrases.
Bullets 2–4: core skill clusters matching the JD's primary functions. No copying from experience bullets.
Fifth bullet: company-stage signal.
  Startup → small-team ownership, shipped in ambiguity, end-to-end accountability
  Enterprise → governance maturity, cross-functional impact, organizational scale
Always exactly 5 bullets. Never a paragraph. Never 4, never 6.

DOMAIN BRIDGE (optional): If candidate's background ≠ target company's domain, one summary bullet may bridge explicitly. Factual and technical only. Never repeat in experience bullets.

═══ HUMAN VOICE — ANTI-AI TELLS ═══
  • NEVER "utilized" or "leveraged"
  • No two consecutive bullets open with the same verb
  • Vary structure: metric-first, action-first, tool-first, outcome-first
  • No empty intensifiers without a real number
  • Every bullet ≤ 25 words. Target 17–22. One idea only.
  • No distinctive JD word repeated 3+ times across the full resume

═══ CRITICAL REMINDERS ═══
✗ NEVER fabricate titles, companies, dates, locations, degrees, deals, or credentials
✗ NEVER write a gap bullet if all 5 anchors can't be satisfied
✗ NEVER mirror the JD's exact feature list as a skills line
✗ NEVER inject the JD's domain vocabulary into a different-domain employer's bullet
✗ NEVER use finance-specific KPIs (FP&A, P&L, budget variance, month-end close, board-ready reporting, reconciliation) or clinical/regulatory program names (Medicaid, Medicare, CMS, claims adjudication, care coordination, patient panel) in any bullet or skills line when ROLE TYPE is not FINANCE/HEALTHCARE — even if the JD's employer is a bank or healthcare company. Describe the underlying data/technical work only (e.g. "ingested claims and eligibility data" not "validated Medicaid/Medicare compliance reporting")
✗ NEVER drop a license, certification, or deal from the original resume
✗ NEVER write a CERTIFICATIONS or LICENSES & CERTIFICATIONS section containing "None", "N/A", or any placeholder — omit the section entirely if the candidate has no certs
✗ NEVER exceed the bullet budget for this role type
✗ NEVER write an exposure bullet when the JD demands execution depth
✗ NEVER omit graduation year if present in the original resume
✗ NEVER apply a compliance framework outside its legally plausible domain
✓ ALWAYS use the correct section labels for the detected role type
✓ ALWAYS use the correct closing line format per role type (or omit if not applicable)
✓ ALWAYS include "| City, State" in every job header
✓ ALWAYS give PRIMARY FUNCTIONS dedicated 2+ bullet coverage
✓ ALWAYS calibrate summary fifth bullet to company stage
✓ ALWAYS ask: "Would this bullet survive a live interview challenge?" before keeping a gap fill
✓ ALWAYS preserve every license, certification, and deal from the original resume
✗ NEVER explain how a metric was measured inside a bullet. No "measured by",
  "tracked via", "calculated by", "confirmed by", "as reported by", "based on
  stakeholder-reported", "per billing dashboards". State the outcome and stop.
  A resume asserts results; it does not present evidence. "reduced runtime 35%"
  — correct. "reduced runtime 35%, measured by comparing job durations in
  Databricks before and after tuning" — wrong, delete the justification clause.
✗ NEVER put a number in every bullet. HARD RULE: roughly HALF of experience
  bullets must contain NO digits at all — no percentages, no counts, no
  dollar amounts. Write honest process, design, and collaboration bullets
  without numbers. A resume where 90-100% of bullets carry metrics reads as
  AI-generated and gets rejected by recruiters. Target: only 40-50% of
  bullets carry a metric (30-50% for HEALTHCARE, 40-45% for CONSULTING).

═══ FINAL CHECK BEFORE OUTPUT ═══
1. Confirm role type detected: [TECH / IB / FINANCE / CYBER / HEALTHCARE / CONSULTING / GENERAL]
2. Confirm correct section labels used for that role type
3. Count all bullets — must be within the budget for this role type
4. Confirm word count ≤ 22 on every bullet
5. Count bullets containing digits — if more than half do, strip the numbers
   from the weakest process/collaboration bullets until roughly half are
   metric-free
6. Confirm: no fabricated content, no domain vocabulary injection, no "utilized/leveraged", no repeated opening verbs, no missed licenses/certs/deals, execution depth demonstrated, PRIMARY FUNCTIONS have 2+ bullets, summary fifth bullet matches company stage
7. Output the finished resume. Nothing else."""


# ── Semantic reviewer ─────────────────────────────────────────────────────────
# Runs ONCE after _enforce_limits. Fixes semantic issues lint can't catch.
# Scope is intentionally narrow — only 3 checks, nothing else.
REVIEWER_PROMPT = """You are a resume quality reviewer — NOT a resume writer.
Fix exactly 3 semantic issues in the resume given to you. Change NOTHING outside
these 3 checks. Do NOT: add bullets, remove bullets, change bullet content,
change company names, dates, locations, titles, or bullet count.
NEVER touch, shorten, or omit these sections — copy them through VERBATIM:
contact/header lines (name, phone, email), EDUCATION, CERTIFICATIONS.
Output the COMPLETE resume from the very first line to the very last line —
dropping any section is a critical failure.
Every bullet you write or rewrite must be ≤ 25 words. Return plain text only.

CHECK 1 — SKILLS ANTI-STUFFING AND CONCEPT DEDUPLICATION:
If the skills/competencies section mirrors the JD's exact feature list verbatim
(e.g. copied qualification wording pasted as category names or line content),
regroup them organically by how the candidate actually works. Use natural category
names appropriate to the role type (e.g. "Distributed Processing", "Cloud
Warehousing" for tech; "Financial Modeling", "Planning Tools" for finance).
Max 6–7 items per line. Do NOT change any bullet in the experience section.
This includes soft-skill or leadership lines copied verbatim from JD requirements
(e.g. "Excellent leadership, communication, and interpersonal skills" appearing as
a skills line) — rewrite these as a concise factual competency line or remove if
they add no technical signal. A skills section lists capabilities, not JD quals.

CONCEPT DEDUPLICATION (part of Check 1):
Scan each item in the skills section. If an item is a concept/methodology word
whose meaning is already captured by a row LABEL in the same section, REMOVE it.

CATEGORIZATION CORRECTION (part of Check 1):
Move tools to the correct category row if they are miscategorized.
  Apache Spark, PySpark, Databricks = PROCESSING engines, not orchestration tools.
    If they appear under a row labeled "Orchestration" or "Data Orchestration",
    move them to a row labeled "Data Processing" or "Compute & Processing".
  Airflow, Dagster, Prefect, Luigi = ORCHESTRATION tools (schedulers, DAG runners).
  dbt, Fivetran, Airbyte = TRANSFORMATION/INTEGRATION tools.
  NetSuite, QuickBooks, Salesforce, SAP, Workday = BUSINESS/ERP APPLICATIONS,
    never databases. If they appear under a "Databases" row, move them to a
    "Business Systems" or "ERP & Business Applications" row (create if needed,
    min 2 items) or remove them from the skills section.
  Do not mix processing engines with orchestrators in the same row.
  Rule: for each item I, check if I appears as or within any row label L.
  If yes → I is redundant → remove I from its row.
  Examples of what to remove:
    "ETL/ELT" as an item when a row is labeled "Data Orchestration" or "ETL/Orchestration"
    "Data Warehouse" as an item when a row is labeled "Data Warehousing"
    "Data Pipeline" as an item when a row is labeled "Data Engineering"
    "Data Visualization" as an item when a row already has "Visualization" in its label
  The label already signals the expertise. The item adds visual clutter, not signal.

CHECK 2 — SUMMARY TECH/SPEC DUMP:
If any summary bullet is a spec list (5+ tools or credentials with no candidate
context, no impact statement, no who-you-are signal), rewrite it as a single
crisp who-you-are statement. ≤ 25 words. One idea only.

CHECK 3 — UNSUPPORTED SKILLS ONLY:
If a tool or skill appears in the skills/competencies section but has zero
supporting bullets anywhere in the WORK EXPERIENCE section AND it does NOT appear
in the CANDIDATE'S DECLARED SKILLS list provided in this message, remove it from
that skills line entirely UNLESS it is explicitly listed as a hard requirement in
the JD. JD-required missing skills may remain in the skills section as market
coverage, but do NOT add employer production ownership or fake experience bullets.
Tools that ARE in the Declared Skills list are the candidate's own claims — keep
them regardless of bullet support.
Do NOT add any label — just delete unsupported, non-JD-required items.

CHECK 4 — SUMMARY UNSUPPORTED EXPERIENCE CLAIMS:
Read the PROFESSIONAL SUMMARY. For each summary bullet, check whether it claims
an experience TYPE (not a skill) that is completely absent from the WORK EXPERIENCE bullets below.

Specifically catch and correct:
  "client-facing advisory / consulting experience" — only valid if the work bullets
    show actual external client work or consultancy employment. If no such bullets exist,
    replace that claim with what the bullets actually show (e.g. "cross-functional
    stakeholder collaboration within enterprise data teams").
  "managed / led a team of N" / "direct reports" — only valid if the work bullets
    mention headcount, people management, or direct-report responsibility. Remove if absent.
  "advisory" or "trusted advisor" role framing — only valid if experience bullets
    show consulting or external advisory work with named clients.

Do NOT remove the entire summary bullet — only remove or rewrite the unsupported
portion within it. If the rest of the bullet is valid, keep it.
If no unsupported experience claims exist in the summary, leave all summary bullets unchanged.

CONSTRAINT — NOTHING ELSE:
Reproduce every other line exactly as given. No commentary. No plan blocks.
Return the complete corrected resume as plain text only."""


# ── Tier-compliance audit prompt ──────────────────────────────────────────────
# Second AI pass, narrow and specific: verify that skills added to close JD
# coverage gaps were placed at the tier the prompt actually allows for them.
# This is a TRUTH check, not a pattern-match — it reads the bullet and judges
# whether it reads as real employer production work vs. honest stretch/skills
# wording. Runs once, no retry, report-only — never silently edits the resume.
TIER_AUDIT_PROMPT = """You are a skeptical technical recruiter doing a final truth-audit on a tailored resume.

You will be given:
1. The CANDIDATE'S ORIGINAL RESUME (ground truth — what they actually did)
2. A list of SKILLS THAT WERE MISSING from the original resume but appear in the FINAL RESUME
3. The FINAL TAILORED RESUME

Your only job: for EACH skill in the missing-skills list, find where it appears in the final
resume and classify how it was placed. Do NOT rewrite, fix, or edit anything. Report only.

For each skill, decide:

  TIER 1/2 — WORK-SUPPORTED or ADJACENT-STRETCH (acceptable as a production claim):
    The skill appears in a bullet that reads as something the candidate actually did, at a real
    employer, doing real work. This is only legitimate if the original resume shows clear evidence
    the candidate did related real work this skill could plausibly extend from.

  TIER 3/4 — SELF-IMPLEMENTABLE or HIGH-RISK (visibility-only, should NOT read as production work):
    The skill appears only in the skills/competencies section, or in a bullet using safe non-production
    wording ("Built prototype...", "Working knowledge of...", "Hands-on project with...").

  VIOLATION — the skill was placed as if it were a real production claim (specific company context,
    metric, ownership verb like "Owned"/"Led"/"Architected", woven into an otherwise-real bullet)
    but the ORIGINAL RESUME shows no real or adjacent basis for it. This is the case you are
    specifically hunting for — a fabricated or unsupported claim dressed up to look real.

Return your findings as plain text, one line per skill, in exactly this format:
  SKILL_NAME | TIER_FOUND | VERDICT (OK or VIOLATION) | ONE-LINE REASON

If a skill from the missing-skills list does not appear anywhere in the final resume, report:
  SKILL_NAME | NOT_PRESENT | OK | skill was not added

After the per-skill lines, add a final line:
  SUMMARY: N skills audited, M violations found

Return ONLY this report. No commentary, no resume rewriting, no markdown formatting."""


_INJECTION_SKIP = {
    # Work arrangements — never a technical skill
    "remote", "hybrid", "onsite", "in-office", "office", "full-time", "part-time",
    "contract", "permanent", "relocation", "candidates", "applicants",
    # Vague business words
    "opportunity", "position", "opening", "role", "join",
    # Education / qualification terms
    "bs/ms", "ms/phd", "bs/phd", "phd", "msc", "bsc", "mba",
    # Degree FIELDS — extraction grabs "Bachelor's in Computer Science" as a
    # hard skill; it's a credential subject, never an injectable skill.
    "computer science", "information systems", "information technology",
    "business analytics", "related field",
    # AI/company jargon — not a skill a candidate claims
    "agi", "asi",
    # Company/product names that slip through
    "quantifind", "nimble",
}

# Programming languages — route to Programming/Languages row when injecting
_PROGRAMMING_LANG_KW = {
    "rust", "go", "kotlin", "swift", "ruby", "php", "r", "matlab",
    "typescript", "javascript", "c++", "c#", "elixir", "haskell", "lua",
    "groovy", "dart", "zig", "clojure", "erlang", "f#",
}

# Domain/compliance terms that don't belong in DevOps/tech rows — use their own row
_COMPLIANCE_DOMAIN_KW = {
    "kyc", "cdd", "aml", "osint", "bsa", "fincen", "fatf", "ofac", "kyb",
    "fraud", "sanctions", "pep", "watchlist", "gdpr", "hipaa", "sox", "pci",
}

def _row_item_count(row_line: str) -> int:
    """Count items in a skills row (comma-separated values after the colon)."""
    if ':' not in row_line:
        return 0
    content = row_line.split(':', 1)[1]
    return len([x for x in content.split(',') if x.strip()])


def _inject_missing_keywords(resume: str, missing: list[str]) -> str:
    """
    Mechanical post-generation keyword injection.
    Rules:
      1. Skip if already in resume (false negative)
      2. Skip if clearly not a technical skill (work arrangement, company name, location)
      3. Compliance/domain terms (KYC, AML, OSINT) → own 'Compliance & Domain' row
      4. Technical terms → best-matching skills row by label similarity
      5. Respect 6-item-per-row limit: if target row is full, create a continuation row
      6. No match found → create 'Additional Skills' row (never append to wrong category)
    """
    if not missing:
        return resume

    sec_m = re.search(
        r'(TECHNICAL SKILLS|CORE COMPETENCIES|SKILLS & EXPERTISE|SKILLS):?\s*\n',
        resume, re.IGNORECASE
    )
    if not sec_m:
        return resume

    sec_start = sec_m.end()
    next_sec  = re.search(r'\n(?:[A-Z][A-Z &]+):\s*\n', resume[sec_start:])
    sec_end   = sec_start + next_sec.start() if next_sec else len(resume)

    skills_block = resume[sec_start:sec_end]
    lines = skills_block.split('\n')
    row_indices = [i for i, l in enumerate(lines) if ':' in l and l.strip()]

    # Buckets for unmatched items
    compliance_queue: list[str] = []
    other_queue:      list[str] = []

    for kw in missing:
        # 1. Already present
        if re.search(r'\b' + re.escape(kw) + r'\b', resume, re.IGNORECASE):
            continue

        # 2. Not a technical skill — skip entirely
        if kw.lower() in _INJECTION_SKIP:
            continue
        # Skip single-word geographic-looking proper nouns (Palo, Alto, Atlanta, etc.)
        if len(kw.split()) == 1 and kw[0].isupper() and kw.lower() not in {
            "python","scala","java","rust","go","r",
        } and not kw.isupper():
            # Heuristic: single TitleCase word that's not a well-known language → skip if looks like a name/place
            if len(kw) >= 4 and kw.isalpha() and kw.lower() not in _COMPLIANCE_DOMAIN_KW:
                continue

        # 3. Compliance/domain terms → separate bucket
        if kw.lower() in _COMPLIANCE_DOMAIN_KW:
            compliance_queue.append(kw)
            continue

        # 3b. Programming languages → target Programming/Languages row specifically
        if kw.lower() in _PROGRAMMING_LANG_KW:
            prog_idx = next(
                (i for i in row_indices
                 if re.search(r'program|language|scripting', lines[i].split(':')[0], re.I)), -1
            )
            if prog_idx >= 0:
                if _row_item_count(lines[prog_idx]) < 6:
                    lines[prog_idx] = lines[prog_idx].rstrip().rstrip(',') + f", {kw}"
                else:
                    cont_label = lines[prog_idx].split(':')[0].strip() + " (cont.)"
                    cont_idx = next(
                        (i for i in row_indices if lines[i].startswith(cont_label)), -1
                    )
                    if cont_idx >= 0 and _row_item_count(lines[cont_idx]) < 6:
                        lines[cont_idx] = lines[cont_idx].rstrip().rstrip(',') + f", {kw}"
                    else:
                        lines.insert(prog_idx + 1, f"{cont_label}: {kw}")
                        row_indices = [i for i, l in enumerate(lines) if ':' in l and l.strip()]
                continue

        # 4. Score rows by label similarity
        kw_words = [w for w in kw.lower().split() if len(w) > 2]
        best_idx, best_score = -1, 0
        for i in row_indices:
            label = lines[i].split(':')[0].lower()
            score = sum(len(w) for w in kw_words if w in label)
            if score > best_score:
                best_score, best_idx = score, i

        if best_score > 0:
            # Found a matching row — respect 6-item limit
            if _row_item_count(lines[best_idx]) < 6:
                lines[best_idx] = lines[best_idx].rstrip().rstrip(',') + f", {kw}"
            else:
                # Row is full — check if a continuation row already exists
                cont_label = lines[best_idx].split(':')[0].strip() + " (cont.)"
                cont_idx = next(
                    (i for i in row_indices if lines[i].startswith(cont_label)), -1
                )
                if cont_idx >= 0 and _row_item_count(lines[cont_idx]) < 6:
                    lines[cont_idx] = lines[cont_idx].rstrip().rstrip(',') + f", {kw}"
                else:
                    # Create new continuation row
                    new_row = f"{cont_label}: {kw}"
                    lines.insert(best_idx + 1, new_row)
                    row_indices = [i for i, l in enumerate(lines) if ':' in l and l.strip()]
        else:
            # No label match — queue for 'Additional Skills' row
            other_queue.append(kw)

    # Append compliance/domain terms as their own row
    if compliance_queue:
        existing_comp = next(
            (i for i, l in enumerate(lines)
             if re.match(r'compliance|domain|financial crimes|risk', l.split(':')[0], re.I)), -1
        )
        if existing_comp >= 0:
            for kw in compliance_queue:
                if _row_item_count(lines[existing_comp]) < 6:
                    lines[existing_comp] = lines[existing_comp].rstrip().rstrip(',') + f", {kw}"
                else:
                    lines.append(f"Compliance & Domain (cont.): {kw}")
        else:
            chunk = compliance_queue[:6]
            rest  = compliance_queue[6:]
            lines.append(f"Compliance & Domain: {', '.join(chunk)}")
            if rest:
                lines.append(f"Compliance & Domain (cont.): {', '.join(rest)}")

    # Unmatched terms: silently discard — no "Additional Skills" row.
    # If a keyword doesn't fit any existing skills row, it's likely a
    # non-technical term that slipped past extraction (NASDAQ, SFIX, USD,
    # company names, etc.). Showing it as "Additional Skills" looks broken.
    # The zone-based extractor already filters most garbage; anything that
    # still doesn't fit a row is garbage and should not appear in the resume.
    if other_queue:
        print(f"[KEYWORD INJECT] Discarded (no row match): {', '.join(other_queue)}")

    return resume[:sec_start] + '\n'.join(lines) + resume[sec_end:]


def _trim_skills_to_layers(resume: str, jd_keywords: list[str], max_layer3: int = 10) -> str:
    """
    Trim the Technical Skills section to 3-layer logic:
      Layer 1 — JD-named keywords: always keep
      Layer 2 — appears in a work bullet (• line): always keep
      Layer 3 — everything else: keep at most max_layer3 total

    Technologies Used lines are Layer 3 territory unless also in a bullet.
    This reduces 150-item dumps to 35-55 targeted items.
    """
    sec_m = re.search(
        r'(TECHNICAL SKILLS|CORE COMPETENCIES|SKILLS & EXPERTISE|SKILLS):?\s*\n',
        resume, re.IGNORECASE
    )
    if not sec_m:
        return resume

    sec_start = sec_m.end()
    next_sec  = re.search(r'\n(?:[A-Z][A-Z &/]+):\s*\n', resume[sec_start:])
    sec_end   = sec_start + next_sec.start() if next_sec else len(resume)

    # Build bullet text (• lines only — not Technologies Used)
    bullet_text = ' '.join(
        line for line in resume[:sec_start].splitlines()
        if line.strip().startswith('•') or line.strip().startswith('*')
        and 'Technologies Used:' not in line
    ).lower()

    jd_set = {k.lower() for k in jd_keywords}

    def classify(item: str) -> int:
        il = item.lower().strip()
        # L1: JD keyword
        for kw in jd_set:
            if kw in il or il in kw:
                return 1
        # L2: in a bullet sentence
        if re.search(r'\b' + re.escape(il) + r'\b', bullet_text):
            return 2
        return 3

    skills_block = resume[sec_start:sec_end]
    lines = skills_block.split('\n')

    # Collect all items with their layer classification
    all_items: list[tuple[int, str]] = []  # (layer, item)
    row_meta: list[tuple[int, str, list[str]]] = []  # (line_idx, label, items)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if ':' not in stripped or not stripped:
            continue
        colon = stripped.index(':')
        label = stripped[:colon].strip()
        items_str = stripped[colon+1:].strip()
        if not items_str:
            continue
        # Parse items respecting parentheses
        items: list[str] = []
        cur, depth = '', 0
        for ch in items_str + ',':
            if ch == '(':   depth += 1; cur += ch
            elif ch == ')': depth -= 1; cur += ch
            elif ch == ',' and depth == 0:
                t = cur.strip()
                if t: items.append(t)
                cur = ''
            else: cur += ch
        row_meta.append((i, label, items))
        for it in items:
            all_items.append((classify(it), it))

    # Decide which to keep
    l1 = {it for layer, it in all_items if layer == 1}
    l2 = {it for layer, it in all_items if layer == 2}
    l3_ordered = [it for layer, it in all_items if layer == 3]
    # Deduplicate l3 preserving order
    seen: set[str] = set()
    l3_unique: list[str] = []
    for it in l3_ordered:
        if it not in seen and it not in l1 and it not in l2:
            seen.add(it); l3_unique.append(it)
    l3_keep = set(l3_unique[:max_layer3])

    keep = l1 | l2 | l3_keep

    # Rebuild skills block keeping only approved items
    new_lines = list(lines)
    for i, label, items in row_meta:
        kept = [it for it in items if it in keep or any(
            k.lower() in it.lower() or it.lower() in k.lower() for k in keep
        )]
        if kept:
            indent = len(lines[i]) - len(lines[i].lstrip())
            new_lines[i] = ' ' * indent + label + ': ' + ', '.join(kept)
        else:
            new_lines[i] = ''  # remove empty row

    new_skills = '\n'.join(new_lines)
    # Clean up consecutive blank lines
    new_skills = re.sub(r'\n{3,}', '\n\n', new_skills)
    return resume[:sec_start] + new_skills + resume[sec_end:]


def _fix_metric_grammar(resume: str) -> str:
    """
    Deterministically insert 'by' before bare percentage metrics in bullet points.
    'cutting execution times 35%' → 'cutting execution times by 35%'

    Only fires when the percentage directly follows a change-verb + noun phrase
    ('reduced X 35%'), so subject-position percentages ('the 45% drop',
    '99.8% uptime') and rate/coverage forms ('95% of') are never touched.
    The old proximity heuristic mis-fired on '~' ('by ~60%' → 'by ~by 60%')
    and on percentages used as subjects ('the by 45% drop').
    Also repairs any double-'by' artifacts from earlier passes.
    Only runs on bullet lines (starting with •).
    """
    _CHANGE_VERBS = (
        r'(?:reduc\w+|cut|cutting|improv\w+|increas\w+|decreas\w+|lower\w+|'
        r'boost\w+|acceler\w+|shorten\w+|grew|grow\w+|dropp\w+|slash\w+|'
        r'rais\w+|optimiz\w+)'
    )
    # verb + 1-4 non-numeric words + bare percentage (no 'by' already there)
    _BARE_PCT = re.compile(
        rf'\b({_CHANGE_VERBS}(?:\s+[a-z][\w/-]*){{1,4}})\s+(~?\d+(?:\.\d+)?%)(?!\+|\s*of\b)',
        re.IGNORECASE,
    )

    lines = resume.splitlines()
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith('•') or s.startswith('*'):
            # Repair artifacts first: 'by ~by 60%' / 'by by 60%' → 'by ~60%'
            line = re.sub(r'\bby\s+(~?)\s*by\s+(\d)', r'by \1\2', line, flags=re.IGNORECASE)
            # 'the by 45% drop' — percentage as subject, 'by' is wrong
            line = re.sub(r'\b(the|a|an)\s+by\s+(\d+(?:\.\d+)?%)', r'\1 \2', line, flags=re.IGNORECASE)
            # 'maintaining by 99.7% data quality SLA' / 'by 99.8% pipeline uptime was' —
            # strip stray 'by' before subject-position % (up to 2 words before keyword)
            line = re.sub(r'\bby\s+(\d+(?:\.\d+)?%(?:\s+[a-z][\w-]*){0,2}\s+'
                          r'(?:uptime|SLA|accuracy|availability|coverage|quality))',
                          r'\1', line, flags=re.IGNORECASE)
            def _insert_by(m: re.Match) -> str:
                phrase = m.group(1)
                if re.search(r'\bby\s*$', phrase, re.IGNORECASE):
                    return m.group(0)
                return f"{phrase} by {m.group(2)}"
            line = _BARE_PCT.sub(_insert_by, line)
        out.append(line)
    return '\n'.join(out)


def _enforce_metric_density(resume: str, role_type: str) -> str:
    """
    Deterministically reduce metric density to the role ceiling.
    Prompt rules alone have not worked — models output 85-100% bullets-with-
    numbers regardless. This strips trailing outcome clauses (' — reducing
    X by 40%') from the lowest-relevance bullets (bottom of each job, last
    job first) until at most half the experience bullets carry a digit.
    Only touches bullets whose pre-clause text is digit-free, so stripping
    actually makes the bullet metric-free and never mangles mid-sentence.
    """
    ceiling = 0.45 if role_type == CONSULTING else 0.50

    lines = resume.splitlines()
    # Bound the experience section
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().upper().startswith("WORK EXPERIENCE"))
    except StopIteration:
        return resume
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].strip().upper().startswith("TECHNICAL SKILLS")), len(lines))

    bullet_idx = [i for i in range(start, end) if lines[i].strip().startswith('•')]
    if not bullet_idx:
        return resume

    def _ratio() -> float:
        withm = sum(1 for i in bullet_idx if re.search(r'\d', lines[i]))
        return withm / len(bullet_idx)

    # Trailing outcome clause: ' — <verb phrase containing a digit>' at end of line
    _CLAUSE = re.compile(r'\s+[—–]\s+[a-z][^—–•\n]*\d[^•\n]*$', re.IGNORECASE)
    # Vague metric: bare percentage improvement with no absolute anchor
    # ('reducing latency by 40%', 'improved efficiency 25%'). Concrete metrics
    # ($2M, 2M records, 500 users, 12 TB) get stripped only as a last resort.
    _VAGUE = re.compile(
        r'\b(?:by\s+)?~?\d{1,3}(?:\.\d+)?\s*%', re.IGNORECASE)
    _CONCRETE = re.compile(
        r'[$€£]\s?\d|\b\d[\d,.]*\s*(?:M|K|B|million|billion|thousand)?\+?\s*'
        r'(?:records?|rows?|users?|customers?|clients?|TB|GB|PB|engineers?|'
        r'analysts?|reports?|pipelines?|sources?|systems?|teams?|markets?|'
        r'countries|hours?|days?)\b', re.IGNORECASE)

    def _strippable(i: int):
        """Return (head, clause) if bullet i has a strippable trailing clause."""
        line = lines[i]
        m = _CLAUSE.search(line)
        if not m:
            return None
        head = line[:m.start()]
        if re.search(r'\d', head):
            return None  # stripping wouldn't make it metric-free
        return head, line[m.start():]

    def _finish(head: str) -> str:
        head = head.rstrip().rstrip(',;')
        if not head.endswith('.'):
            head += '.'
        return head

    stripped = 0
    if _ratio() > ceiling:
        # PASS 1 — vague-percentage clauses, bottom-up. These read as filler
        # ('by 40%') and are the least defensible in an interview.
        for i in reversed(bullet_idx):
            if _ratio() <= ceiling:
                break
            hit = _strippable(i)
            if not hit:
                continue
            head, clause = hit
            if _VAGUE.search(clause) and not _CONCRETE.search(clause):
                lines[i] = _finish(head)
                stripped += 1
        # PASS 2 — still over ceiling: strip remaining clauses bottom-up,
        # concrete metrics included (original behavior, last resort).
        for i in reversed(bullet_idx):
            if _ratio() <= ceiling:
                break
            hit = _strippable(i)
            if not hit:
                continue
            head, _clause = hit
            lines[i] = _finish(head)
            stripped += 1

    if stripped:
        print(f"[METRIC DENSITY] Stripped outcome clauses from {stripped} bullet(s) "
              f"-> {_ratio():.0%} of bullets carry metrics (ceiling {ceiling:.0%})")
    return '\n'.join(lines)


def _drop_singleton_skill_rows(resume: str) -> str:
    """
    Deterministically remove single-item rows from TECHNICAL SKILLS
    ('Data Quality & Governance: RBAC'). The prompt's min-2-items rule is
    routinely ignored. If the orphan item matches another row's label it is
    moved there; otherwise the row and item are dropped (the item usually
    still appears in a Technologies Used line).
    """
    m = re.search(r'^TECHNICAL SKILLS:?\s*$', resume, re.MULTILINE | re.IGNORECASE)
    if not m:
        return resume
    sec_start = m.end()
    nxt = re.search(r'^[A-Z][A-Z &/]{3,}:?\s*$', resume[sec_start:], re.MULTILINE)
    sec_end = sec_start + (nxt.start() if nxt else len(resume) - sec_start)

    lines: list = resume[sec_start:sec_end].splitlines()
    row_re = re.compile(r'^\s*([^:]{2,40}):\s*(.+)$')
    rows = [(i, mm.group(1).strip(), [x.strip() for x in mm.group(2).split(',') if x.strip()])
            for i, l in enumerate(lines) if (mm := row_re.match(l))]
    outside = resume[:sec_start] + resume[sec_end:]

    for i, label, items in rows:
        if len(items) != 1:
            continue
        orphan = items[0]
        # Relocate only on whole-word label overlap ('data' must not match 'databases')
        moved = False
        ow = {w for w in re.split(r'[\s/&\-]+', orphan.lower()) if len(w) > 2}
        for j, lbl2, items2 in rows:
            if j == i or len(items2) >= 6 or len(items2) < 2:
                continue
            lblw = {w for w in re.split(r'[\s/&\-]+', lbl2.lower())}
            if ow & lblw:
                lines[j] = lines[j].rstrip().rstrip(',') + f", {orphan}"
                moved = True
                break
        if moved:
            lines[i] = None
            print(f"[SKILLS ROW] Dropped singleton row '{label}' — moved '{orphan}' to matching row")
        elif re.search(re.escape(orphan), outside, re.IGNORECASE):
            # Item still visible elsewhere (bullet / Technologies Used) — safe to drop
            lines[i] = None
            print(f"[SKILLS ROW] Dropped singleton row '{label}: {orphan}' — item visible elsewhere")
        # else: keep the row — dropping would erase the skill from the resume entirely

    kept = [l for l in lines if l is not None]
    # Drop trailing empties, then restore the section's original tail so the
    # next section header keeps its blank-line separation exactly once
    while kept and not kept[-1].strip():
        kept.pop()
    new_sec = '\n'.join(kept)
    sec_text = resume[sec_start:sec_end]
    if sec_text.endswith('\n\n'):
        new_sec += '\n\n'
    elif sec_text.endswith('\n'):
        new_sec += '\n'
    return resume[:sec_start] + new_sec + resume[sec_end:]


def _remove_concept_redundancy(resume: str) -> str:
    """
    Dynamically remove concept/category words from Technical Skills when
    the section's own row LABELS already describe that category.

    No hardcoded concept lists. Structural heuristic only:
      An item is a CONCEPT (not a tool) if at least one of its words
      that is >= 6 characters long appears in the vocabulary built from
      all row LABELS in the skills section.

    Why this works:
      - Brand/tool names (Power BI, GitHub Actions, Snowflake, Databricks,
        Apache Spark) contain specific words that never appear in category
        labels like "Orchestration & DevOps" or "Visualization & Reporting."
      - Abstract concept words (visualization, warehousing, orchestration,
        governance, integration) DO appear in those labels — because that
        is how the AI names its categories.

    Examples (label vocab built from actual section headers):
      label vocab: {visualization, reporting, orchestration, warehousing,
                    integration, governance, quality, processing, ...}
      "Data Visualization" -> "visualization" (14 chars) in vocab -> concept -> drop
      "Power BI"           -> "power" (5) too short, "bi" (2) too short -> tool -> keep
      "Apache Airflow"     -> "apache" (6) not in vocab, "airflow" (7) not in vocab -> keep
      "GitHub Actions"     -> neither word in vocab -> tool -> keep
      "CI/CD"              -> "ci" (2), "cd" (2) -> both too short -> keep
      "Data Warehousing"   -> "warehousing" (11) in vocab -> concept -> drop

    Adapts automatically to any JD and any AI-generated section structure.
    """
    sec_m = re.search(
        r'(TECHNICAL SKILLS|CORE COMPETENCIES|SKILLS & EXPERTISE|SKILLS):?\s*\n',
        resume, re.IGNORECASE
    )
    if not sec_m:
        return resume

    sec_start = sec_m.end()
    next_sec  = re.search(r'\n(?:[A-Z][A-Z &/]+):\s*\n', resume[sec_start:])
    sec_end   = sec_start + next_sec.start() if next_sec else len(resume)

    skills_block = resume[sec_start:sec_end]
    lines        = skills_block.split('\n')

    # ── Build label vocabulary from this section's own row labels ─────────────
    # Words >= 6 chars from labels = category-describing vocabulary.
    # Tool names are never in this vocabulary.
    label_vocab: set[str] = set()
    row_data: list[tuple[int, str, list[str]]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if ':' not in stripped or not stripped:
            continue
        colon_idx = stripped.index(':')
        label     = stripped[:colon_idx].strip()
        items_str = stripped[colon_idx + 1:].strip()
        if not items_str:
            continue

        # Strip continuation suffix before extracting vocab
        label_clean = re.sub(r'\s*\(cont\.?\)\s*$', '', label, flags=re.IGNORECASE)
        for word in re.split(r'[\s&/\-()]+', label_clean.lower()):
            if len(word) >= 3:   # same threshold used when checking items below
                label_vocab.add(word)

        # Parse items respecting parentheses
        items: list[str] = []
        cur, depth = '', 0
        for ch in items_str + ',':
            if ch == '(':   depth += 1; cur += ch
            elif ch == ')': depth -= 1; cur += ch
            elif ch == ',' and depth == 0:
                t = cur.strip()
                if t: items.append(t)
                cur = ''
            else: cur += ch
        row_data.append((i, label, items))

    if not label_vocab:
        return resume

    # ── Filter each row ───────────────────────────────────────────────────────
    new_lines = list(lines)
    for i, label, items in row_data:
        concepts, concrete = [], []
        for item in items:
            # An item is a CONCEPT word if ALL of its meaningful words
            # (≥3 chars) appear in the label vocabulary built from this
            # section's row labels.
            #
            # Rationale: category labels use abstract nouns. Tools/techniques
            # have specific words that never appear in category label names.
            #
            # "Data Visualization": words {data, visualization}
            #   "data" in label vocab (many labels use "data") ✓
            #   "visualization" in vocab (from "Visualization & Reporting") ✓
            #   ALL words in vocab → concept → remove
            #
            # "Shell Scripting": words {shell, scripting}
            #   "scripting" in vocab (from "Languages & Scripting") ✓
            #   "shell" NOT in vocab → NOT ALL → tool → keep ✓
            #
            # "Power BI": words {power, bi} — both < 3 chars or not in vocab
            #   "power" not in vocab, "bi" < 3 chars → NOT all → keep ✓
            #
            # "Dimensional Modeling": words {dimensional, modeling}
            #   "modeling" in vocab ✓, "dimensional" NOT in vocab → keep ✓
            item_words = [w for w in re.split(r'[\s&/\-()]+', item.lower()) if len(w) >= 3]
            is_concept = (
                bool(item_words)
                and all(w in label_vocab for w in item_words)
            )
            if is_concept:
                concepts.append(item)
            else:
                concrete.append(item)



        # Only remove concept words if at least 1 concrete tool remains.
        # Never empty a row — if everything is a "concept," keep it all.
        if concrete:
            removed  = concepts
            filtered = concrete
        else:
            removed  = []
            filtered = items

        if removed:
            print(f"[CONCEPT DEDUP] Removed ({label}): {', '.join(removed)}")

        # Intra-row sub-phrase dedup: remove item A when another item B in
        # the same row contains all words of A (e.g. "Functions" + "Azure Functions"
        # → keep only "Azure Functions").
        deduped = []
        filtered_lo = [it.lower() for it in filtered]
        for idx, item in enumerate(filtered):
            words = re.findall(r'\b\w+\b', item.lower())
            is_sub = any(
                jdx != idx
                and all(re.search(r'\b' + re.escape(w) + r'\b', filtered_lo[jdx]) for w in words)
                and len(filtered[jdx].split()) > len(words)
                for jdx in range(len(filtered))
            )
            if is_sub:
                print(f"[CONCEPT DEDUP] Removed sub-phrase ({label}): {item}")
            else:
                deduped.append(item)
        filtered = deduped if deduped else filtered

        indent = len(lines[i]) - len(lines[i].lstrip())
        if filtered:
            new_lines[i] = ' ' * indent + label + ': ' + ', '.join(filtered)
        else:
            new_lines[i] = ''

    new_skills = '\n'.join(new_lines)
    new_skills = re.sub(r'\n{3,}', '\n\n', new_skills)
    return resume[:sec_start] + new_skills + resume[sec_end:]


def _trim_tech_lines(resume: str, jd_keywords: list[str], role_type: str,
                     max_items: int = 15) -> str:
    """
    Cap 'Technologies Used:' lines. Live output shipped a 35-item monster —
    ATS-fine, human-hostile. Keep JD-matching items first (original order),
    then non-matching items, cut at max_items. Paren groups stay intact.
    Deterministic, no AI.
    """
    prefix = _CLOSING_PREFIXES.get(role_type)
    if not prefix:
        return resume
    prefix_lo = prefix.lower()
    kw_lo = [k.lower() for k in (jd_keywords or [])]

    def _relevant(item: str) -> bool:
        it = item.lower()
        return any(k in it or it in k for k in kw_lo)

    out = []
    for line in resume.split('\n'):
        s = line.strip()
        if not s.lower().startswith(prefix_lo):
            out.append(line)
            continue
        body = s[len(prefix):].strip()
        # Split on commas NOT inside parens — "AWS (S3, EMR, Glue)" = one item
        items = [i.strip() for i in re.split(r",\s*(?![^()]*\))", body) if i.strip()]
        if len(items) <= max_items:
            out.append(line)
            continue
        keep = [i for i in items if _relevant(i)]
        keep += [i for i in items if not _relevant(i)]
        keep = keep[:max_items]
        # Preserve original relative order in final output
        ordered = [i for i in items if i in set(keep)][:max_items]
        out.append(f"{prefix} " + ", ".join(ordered))
        print(f"[TECH LINE] Trimmed {len(items)} -> {len(ordered)} items")
    return '\n'.join(out)


def _merge_cont_rows(resume: str) -> str:
    """
    Merge 'Label (cont.): items' rows back into their base 'Label: ...' row.
    Runs after all injection and limit-enforcement so the final output never
    shows a repeated label with '(cont.)' appended.
    """
    sec_m = re.search(
        r'(TECHNICAL SKILLS|CORE COMPETENCIES|SKILLS & EXPERTISE|SKILLS):?\s*\n',
        resume, re.IGNORECASE
    )
    if not sec_m:
        return resume

    sec_start = sec_m.end()
    next_sec  = re.search(r'\n(?:[A-Z][A-Z &/]+):\s*\n', resume[sec_start:])
    sec_end   = sec_start + next_sec.start() if next_sec else len(resume)

    lines = resume[sec_start:sec_end].split('\n')
    out: list[str] = []

    for line in lines:
        m = re.match(r'^(\s*)(.+?) \(cont\.\): (.+)$', line)
        if not m:
            out.append(line)
            continue
        indent, base_label, extra = m.group(1), m.group(2), m.group(3)
        base_prefix = indent + base_label + ':'
        merged = False
        for i in range(len(out) - 1, -1, -1):
            if out[i].startswith(base_prefix):
                out[i] = out[i].rstrip().rstrip(',') + ', ' + extra.strip()
                merged = True
                break
        if not merged:
            out.append(f"{indent}{base_label}: {extra}")

    return resume[:sec_start] + '\n'.join(out) + resume[sec_end:]


def _enforce_skills_line_limit(resume: str, max_items: int = 6) -> str:
    """
    Deterministic post-processing: split any skills row with > max_items
    into multiple rows. Uses BALANCED splitting to avoid orphan 1-item rows.

    7 items -> 4+3  (not 6+1)
    8 items -> 4+4
    9 items -> 5+4
    10 items -> 5+5
    11 items -> 6+5
    12 items -> 6+6
    """
    sec_m = re.search(
        r'(TECHNICAL SKILLS|CORE COMPETENCIES|SKILLS & EXPERTISE|SKILLS):?\s*\n',
        resume, re.IGNORECASE
    )
    if not sec_m:
        return resume

    sec_start = sec_m.end()
    next_sec  = re.search(r'\n(?:[A-Z][A-Z &/]+):\s*\n', resume[sec_start:])
    sec_end   = sec_start + next_sec.start() if next_sec else len(resume)

    skills_block = resume[sec_start:sec_end]
    lines = skills_block.split('\n')
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if ':' not in stripped or not stripped:
            new_lines.append(line)
            continue

        colon_idx = stripped.index(':')
        label     = stripped[:colon_idx].strip()
        items_str = stripped[colon_idx + 1:].strip()

        if not items_str:
            new_lines.append(line)
            continue

        # Parse items — handle parenthetical groups like "AWS (S3, EMR)" as ONE item
        items: list[str] = []
        current = ''
        depth = 0
        for ch in items_str:
            if ch == '(':
                depth += 1
                current += ch
            elif ch == ')':
                depth -= 1
                current += ch
            elif ch == ',' and depth == 0:
                t = current.strip()
                if t:
                    items.append(t)
                current = ''
            else:
                current += ch
        if current.strip():
            items.append(current.strip())

        if len(items) <= max_items:
            new_lines.append(line)
            continue

        # Balanced split — distribute evenly so no row has < 3 items
        import math
        n_rows   = math.ceil(len(items) / max_items)
        row_size = math.ceil(len(items) / n_rows)   # <= max_items, balanced
        indent   = len(line) - len(line.lstrip())
        prefix   = ' ' * indent
        for chunk_start in range(0, len(items), row_size):
            chunk  = items[chunk_start:chunk_start + row_size]
            suffix = ' (cont.)' if chunk_start > 0 else ''
            new_lines.append(f"{prefix}{label}{suffix}: {', '.join(chunk)}")

    new_skills = '\n'.join(new_lines)
    return resume[:sec_start] + new_skills + resume[sec_end:]


def _parse_tier_audit(report: str):
    """Parse the tier audit report and return only the VIOLATION lines as issue strings."""
    violations = []
    for line in report.strip().split("\n"):
        line = line.strip()
        if not line or line.upper().startswith("SUMMARY:"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4 and parts[2].upper() == "VIOLATION":
            skill, tier_found, _, reason = parts[0], parts[1], parts[2], parts[3]
            violations.append(
                f"[TIER VIOLATION] '{skill}' placed as {tier_found} but original resume "
                f"shows no real/adjacent basis — {reason}"
            )
    return violations


# ── Slim retry system prompt ──────────────────────────────────────────────────
# Retries previously shipped the full ~15K-token SYSTEM_PROMPT on every call.
# A targeted fix doesn't need generation strategy — only output-format law.
# Per-issue fix rules already ride in the user message (_RETRY_RULES).
# ~600 tokens vs ~15K → saves ~13-14K input tokens per retry call.
RETRY_SYSTEM_PROMPT = """You are a precise resume editor fixing specific lint issues.

Fix ONLY the issues listed in the user message. Change nothing else.

OUTPUT LAW (violations fail lint again):
- Plain text only. No markdown, no commentary, no <plan> block.
- Output the COMPLETE resume, first line to last. Never truncate.
- Keep the exact section order and every section header as given.
- Line 1: name + title. Line 2: phone | email (keep verbatim).
- Job headers stay verbatim: Title @ Company | City, State   Month YYYY – Month YYYY
- Every experience bullet: starts with '• ', past-tense action verb, ≤25 words, ONE idea.
- No two consecutive bullets open with the same verb.
- Never use the words "utilized" or "leveraged" (except "leveraged finance/buyout" in IB).
- PROFESSIONAL SUMMARY: exactly 6 bullets.
- Keep each job's closing line (e.g. "Technologies Used:") with its exact label.
- EDUCATION content stays byte-identical to input.
- Never invent employers, dates, titles, degrees, or metrics.
- When cutting an overflow bullet, cut the lowest-relevance one; never merge two bullets.
- When a bullet is too long, TRIM words; never split into two bullets.
- NEVER add new bullets unless an issue explicitly says to add one — adding
  bullets to unflagged jobs causes overflow failures.
- PRESERVE all existing numbers and metrics in every bullet, including ones
  you rewrite. Removing metrics from bullets is a failure."""


# ── Closing-line restore — deterministic, no AI ───────────────────────────────
# Live run showed the merged reviewer dropping every "Technologies Used:" line
# (3× MISSING CLOSING LINE post-review). Reviewer prompt says "reproduce every
# other line exactly" — Haiku ignores it sometimes. Restore from pre-review.
def _restore_closing_lines(result: str, pre_review: str, role_type: str) -> str:
    prefix = _CLOSING_PREFIXES.get(role_type)
    if not prefix:
        return result
    prefix_lo = prefix.lower()

    def _job_closings(text: str) -> dict[str, str]:
        """Map job-header line -> its closing line (if any)."""
        out, cur = {}, None
        for line in text.split('\n'):
            s = line.strip()
            if _is_job_header_line(s):
                cur = s
            elif cur and s.lower().startswith(prefix_lo):
                out[cur] = s
        return out

    wanted = _job_closings(pre_review)
    have   = _job_closings(result)
    missing = {h: c for h, c in wanted.items() if h not in have}
    if not missing:
        return result

    lines = result.split('\n')
    restored = 0
    for header, closing in missing.items():
        try:
            hi = next(i for i, l in enumerate(lines) if l.strip() == header)
        except StopIteration:
            continue  # reviewer also changed the header — job integrity net handles that
        # Insert after the block's last bullet (or right after header if none)
        insert_at = hi + 1
        for j in range(hi + 1, len(lines)):
            s = lines[j].strip()
            if _is_job_header_line(s) or (s and s == s.upper() and len(s) > 3):
                break
            if s.startswith('•'):
                insert_at = j + 1
        lines.insert(insert_at, closing)
        restored += 1
    if restored:
        print(f"[CLOSING RESTORE] Re-inserted {restored} closing line(s) dropped by reviewer")
    return '\n'.join(lines)


# ── Summary restore — deterministic, no AI ────────────────────────────────────
# Live run shipped a 5-bullet summary (must be exactly SUMMARY_EXACT).
# Reviewer sometimes merges/drops a summary bullet post-loop; nothing
# downstream re-adds. If reviewer output has FEWER summary bullets than
# pre-review, splice the pre-review summary section back in verbatim.
def _summary_block(text: str) -> tuple[int, int, int]:
    """(start_line, end_line, bullet_count) of PROFESSIONAL SUMMARY block."""
    lines = text.split('\n')
    start = next((i for i, l in enumerate(lines)
                  if l.strip().upper().startswith("PROFESSIONAL SUMMARY")), -1)
    if start < 0:
        return -1, -1, 0
    end, count = len(lines), 0
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s and s == s.upper() and len(s) > 3 and not s.startswith('•'):
            end = j
            break
        if s.startswith('•'):
            count += 1
    return start, end, count


def _restore_summary(result: str, pre_review: str) -> str:
    ps, pe, pc = _summary_block(pre_review)
    rs, re_, rc = _summary_block(result)
    if ps < 0 or rs < 0 or rc >= pc:
        return result
    pre_lines    = pre_review.split('\n')
    result_lines = result.split('\n')
    spliced = result_lines[:rs] + pre_lines[ps:pe] + result_lines[re_:]
    print(f"[SUMMARY RESTORE] Reviewer dropped {pc - rc} summary bullet(s) — restored pre-review summary")
    return '\n'.join(spliced)


async def audit_tier_compliance(
    base_resume: str,
    final_resume: str,
    missing_skills: list[str],
    api_key: str, provider: str, model: str,
    keys=None,
) -> tuple[list[str], str]:
    """
    Truth-audit pass: verifies skills added to close JD coverage gaps were placed
    at an honest tier (visibility-only vs. production-claim). Report-only — never
    edits the resume. Returns (violation_issues, raw_report).
    If missing_skills is empty, skips the call entirely (nothing to audit).
    """
    if not missing_skills:
        return [], ""

    msg = (
        f"=== SKILLS THAT WERE MISSING FROM THE ORIGINAL RESUME ===\n"
        f"{', '.join(missing_skills)}\n\n"
        f"=== CANDIDATE'S ORIGINAL RESUME (ground truth) ===\n{base_resume}\n\n"
        f"=== FINAL TAILORED RESUME ===\n{final_resume}"
    )

    report = await chat(
        system=TIER_AUDIT_PROMPT,
        user=msg,
        api_key=api_key,
        provider=provider,
        model=model,  # caller passes _sec here
        max_tokens=2500,
        pass_name="tier-audit",
        keys=keys,
    )
    report = report.strip()
    violations = _parse_tier_audit(report)
    return violations, report


# Appended to REVIEWER_PROMPT when the review call also carries the tier audit.
# Merging saves one full AI call + ~15s latency per run: both passes read the
# same resume on the same cheap model.
_AUDIT_ADDENDUM = """

CHECK 5 — TIER-COMPLIANCE AUDIT (report only — do NOT edit for this check):
You will also receive the CANDIDATE'S ORIGINAL RESUME and a list of GAP-FILLED
SKILLS (absent from the original, present in the tailored resume). For EACH
gap-filled skill, judge how it was placed:
  TIER 1/2 (OK)  — production claim backed by clearly related real work in the
                   ORIGINAL resume.
  TIER 3/4 (OK)  — skills-section only, or non-production wording ("Built
                   prototype...", "Working knowledge of...", "Piloted...").
  VIOLATION      — reads as real employer production work (ownership verbs,
                   company context, metrics) with NO real or adjacent basis in
                   the original resume.

OUTPUT FORMAT (STRICT):
First output the complete corrected resume (checks 1-4 applied).
Then a line containing exactly:  ===TIER AUDIT===
Then one line per gap-filled skill:  SKILL_NAME | TIER_FOUND | OK-or-VIOLATION | one-line reason
If a skill does not appear in the resume:  SKILL_NAME | NOT_PRESENT | OK | skill was not added
Then a final line:  SUMMARY: N skills audited, M violations found"""


async def review_resume(tailored: str, job_description: str,
                        api_key: str, provider: str, model: str,
                        profile_skills: list[str] | None = None,
                        base_resume: str = "",
                        missing_skills: list[str] | None = None,
                        keys=None) -> tuple[str, str]:
    """
    One-shot semantic review pass. Fires exactly once after _enforce_limits.
    If missing_skills given, the same call also performs the tier audit
    (CHECK 5) and returns its report — saving a separate audit call.
    Returns (reviewed_resume, audit_report). audit_report == "" when the
    audit wasn't requested or the model omitted the footer (caller should
    then fall back to the standalone audit).
    """
    do_audit = bool(missing_skills and base_resume)
    skills_ctx = ""
    if profile_skills:
        skills_ctx = (
            f"\n=== CANDIDATE'S FULL SKILL INVENTORY (reference only) ===\n"
            f"{', '.join(profile_skills)}\n"
        )
    audit_ctx = ""
    if do_audit:
        audit_ctx = (
            f"\n=== GAP-FILLED SKILLS TO AUDIT (CHECK 5) ===\n"
            f"{', '.join(missing_skills)}\n\n"
            f"=== CANDIDATE'S ORIGINAL RESUME (ground truth for CHECK 5) ===\n"
            f"{base_resume}\n"
        )
    msg = (
        "Review and fix the semantic issues per your instructions.\n"
        "CRITICAL: Output the COMPLETE resume from first line to last — every section, "
        "every job, every bullet, TECHNICAL SKILLS, EDUCATION. Do NOT truncate or stop early.\n"
        "NEVER lengthen bullets or append measurement-methodology clauses "
        "('measured by...', 'confirmed via...', parenthetical evidence). "
        "Bullets assert outcomes; they never present evidence.\n"
        + ("After the resume, output the ===TIER AUDIT=== report per CHECK 5.\n" if do_audit else "")
        + "Return plain text only — no commentary, no plan block.\n"
        f"{skills_ctx}{audit_ctx}\n"
        f"=== JOB DESCRIPTION ===\n{job_description[:5000]}\n\n"
        f"=== TAILORED RESUME ===\n{tailored}"
    )

    reviewed = await chat(
        system=REVIEWER_PROMPT + (_AUDIT_ADDENDUM if do_audit else ""),
        user=msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=16384,
        pass_name="reviewer" + ("+audit" if do_audit else ""),
        keys=keys,
    )
    stripped = re.sub(r'<plan>.*?</plan>', '', reviewed, flags=re.DOTALL).strip()
    if stripped != reviewed:
        print("[WARN] Reviewer output contained <plan> block — may be over-thinking")

    audit_report = ""
    if do_audit and "===TIER AUDIT===" in stripped:
        stripped, _, audit_report = stripped.partition("===TIER AUDIT===")
        stripped = stripped.strip()
        audit_report = audit_report.strip()
    return stripped, audit_report


# ── Per-issue retry rules ─────────────────────────────────────────────────────
_RETRY_RULES = {
    "[MISSING CONTACT]":       "Line 2 must be 'phone | email' — add the contact line with real phone and email.",
    "[MISSING LOCATION]":      "Every job header must include '| City, State' after the company name.",
    "[MISSING CLOSING LINE]":  "Every job block must end with the correct closing line for this role type (e.g. 'Technologies Used:' for tech, 'Selected Transactions:' for IB, 'Technologies & Platforms:' for cyber).",
    "[BANNED CLOSING LABEL]":  "Use the exact closing line label required for this role type — no substitutes.",
    "[BANNED WORD]":           "Replace 'utilized' and 'leveraged' with active verbs: 'used', 'built', 'ran'.",
    "[META LEAK]":             "Remove all instruction text, placeholders, or commentary from the resume body.",
    "[TOO LONG]":              "Shorten to ≤25 words by TRIMMING words — never split one bullet into two (that overflows the bullet budget). Cut justification clauses, filler, and secondary details.",
    "[METRIC NARRATION]":      "Delete the measurement-methodology clause ('measured by...', 'tracked via...', 'confirmed by...'). Keep only the action and outcome. Resumes assert results; they never present evidence.",
    "[MULTI-IDEA]":            "One accomplishment per bullet. Split into two or cut the weaker half.",
    "[SAME VERB]":             "No two consecutive experience bullets may open with the same verb — vary them.",
    "[SUMMARY]":               "PROFESSIONAL SUMMARY must have exactly 6 bullet lines — not 5, not 7. Count your bullets and add or remove to hit exactly 6.",
    "[TOO FEW BULLETS]":       "A job block has fewer bullets than its minimum. Add more specific, metric-backed bullets until the minimum is met — quality over padding. Do NOT cut other sections — add only to the flagged job.",
    "[BULLET OVERFLOW]":       "Total bullets exceed the limit for this role type. Cut lowest-relevance bullets first.",
    "[MISSING SECTION]":       "A required section is missing — check for output truncation and regenerate the full resume.",
    "[LOW METRICS]":           "Add quantified outcomes to more experience bullets to meet the role-appropriate target.",
    "[HIGH METRICS]":          "Remove forced numbers from process/collaboration bullets — looks artificial.",
    "[JD ECHO]":               "A JD word repeated 3+ times reads as keyword stuffing. Vary phrasing; keep ≤2 uses.",
    "[LOW JD SKILL VISIBILITY]": "Add 1–3 missing skills via the correct tier: WORK-SUPPORTED bullet, ADJACENT-STRETCH bullet (max 1/job, 2 total), or SELF-IMPLEMENTABLE/HIGH-RISK skills-project wording. Visibility-only placement is acceptable — never force a production claim.",
    "[PROFILE SKILL DROPPED]":   "These skills exist in the candidate's original resume and are WORK-SUPPORTED. Add each back: write a real bullet in the most relevant job, add to that job's Technologies Used, add to Technical Skills. Do not omit because JD listed them as 'or' alternatives.",
    "[YEARS MISMATCH]":          "Use the exact years-of-experience number from the ORIGINAL RESUME — do not inflate or deflate it.",
    "[DOMAIN LEAK]":             "Remove this phrase entirely and rewrite the bullet using neutral technical/data language only — do not reference the JD employer's specific business domain (finance KPIs, clinical/regulatory program names) when it doesn't match the locked role type.",
    "[YEARS FABRICATED]":        "The original resume has no years-of-experience claim in the summary. Remove the years number entirely — do not invent one.",
    "[UNSUPPORTED EXPERIENCE CLAIM]": "Remove or rewrite the summary claim to only reflect experience types supported by the work bullets below it.",
}


def _strip_metric_narration(resume: str) -> str:
    """
    Kill measurement-methodology clauses the reviewer appends post-loop
    ('measured by comparing...', 'confirmed via...', '(Redshift query history
    before/after)'). Resumes assert outcomes; they never present evidence.
    Deterministic, runs after all AI passes.
    """
    _NARR = re.compile(
        r"[;,]?\s*(?:as\s+)?(?:measured|confirmed|calculated|tracked|validated|"
        r"verified|logged|quantified|benchmarked)\s+"
        r"(?:by|via|in|through|against|using|across|over)\b[^•\n]*",
        re.IGNORECASE)
    _PAREN_EVIDENCE = re.compile(
        r"\s*\((?:[^()]*(?:before/after|dashboards?|history|pre/post|"
        r"per\s+billing)[^()]*)\)", re.IGNORECASE)

    def _paren_sub(m: re.Match) -> str:
        # Evidence paren may wrap a real money metric — keep the figure.
        money = re.search(r"[$€£]\s?[\d,.]+[KMB]?(?:/year|/yr|/month)?",
                          m.group(0), re.IGNORECASE)
        return f" ({money.group(0).strip()})" if money else ""

    out, stripped = [], 0
    for line in resume.split('\n'):
        if line.strip().startswith('•'):
            new = _NARR.sub('', line)
            new = _PAREN_EVIDENCE.sub(_paren_sub, new)
            if new != line:
                new = new.rstrip().rstrip(',;')
                if not new.endswith('.'):
                    new += '.'
                stripped += 1
            out.append(new)
        else:
            out.append(line)
    if stripped:
        print(f"[NARRATION] Stripped evidence clauses from {stripped} bullet(s)")
    return '\n'.join(out)


def _trim_long_bullets(resume: str, word_limit: int) -> str:
    """
    Trim experience bullets that exceed word_limit words.
    Cuts at the last natural break point (—, ;, ,) at or before word_limit.
    Falls back to hard truncation at word_limit.
    Eliminates [TOO LONG] + most [MULTI-IDEA] lint issues before the retry loop.
    Free, deterministic, zero AI calls.
    """
    # Natural break characters, in preference order
    _BREAKS = ('—', '–', ';', ',')

    def trim_bullet(text: str) -> str:
        words = text.split()
        if len(words) <= word_limit:
            return text

        # Find the rightmost natural break within [word_limit-5, word_limit]
        # Reconstruct progressively to find break positions
        best_trim = None
        for target in range(word_limit, max(word_limit - 6, 5), -1):
            prefix = ' '.join(words[:target])
            for brk in _BREAKS:
                last = prefix.rfind(brk)
                if last > 0:
                    # Found a break — trim there
                    trimmed = prefix[:last].rstrip()
                    if len(trimmed.split()) >= 8:  # don't make it too short
                        best_trim = trimmed
                        break
            if best_trim:
                break

        if best_trim:
            return best_trim
        # Hard truncation at word_limit
        return ' '.join(words[:word_limit])

    lines = resume.split('\n')
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith('•'):
            body = s[1:].strip()
            trimmed = trim_bullet(body)
            if trimmed != body:
                print(f"[TRIM] {len(body.split())}->{len(trimmed.split())} words: '{body[:50]}...'")
            # Preserve original indentation
            indent = len(line) - len(line.lstrip())
            out.append(' ' * indent + '• ' + trimmed)
        else:
            out.append(line)
    return '\n'.join(out)


async def tailor_resume(base_resume: str, job_description: str,
                        api_key: str, provider: str, model: str,
                        profile_skills: list[str] | None = None,
                        secondary_model: str = "",
                        user_job_roles: list[str] | None = None,
                        keys=None) -> str:
    # secondary_model: cheaper model for reviewer, tier audit, correction, retries.
    # Falls back to main model if not set.
    _sec = secondary_model or model

    # Some ATS feeds deliver the JD as (double-)encoded HTML. Decode/strip it
    # once here so the model prompt, lint, and coverage all see clean text.
    from resume_lint import clean_jd_html
    job_description = clean_jd_html(job_description)

    # Role type comes from user's job preference only. No JD body scan.
    # Job preference is required to use the app — if empty, default TECH.
    role_type = user_roles_to_role_type(user_job_roles or []) or TECH
    print(f"[TAILOR] user_job_roles={user_job_roles!r} -> role_type={role_type}")
    budget    = BULLET_BUDGETS[role_type]
    minimums  = BULLET_MINIMUMS.get(role_type, (0, 0, 0, 0))
    hard_total = budget[5]
    exp_total  = hard_total - SUMMARY_EXACT

    jd_hard_skills = []
    if extract_jd_hard_skills is not None:
        jd_hard_skills = extract_jd_hard_skills(job_description, role_type)

    # Snapshot which JD hard skills are missing from the ORIGINAL resume —
    # this is the ground-truth list the tier-compliance audit checks against
    # later. Computed once, before any tailoring happens.
    skills_missing_from_original: list[str] = []
    if skill_coverage_report is not None and jd_hard_skills:
        original_coverage = skill_coverage_report(
            base_resume, job_description, role_type=role_type, profile_skills=profile_skills
        )
        skills_missing_from_original = original_coverage.get("missing", [])

    jd_skills_section = ""
    if jd_hard_skills:
        jd_skills_section = (
            "\n=== JD HARD SKILLS DETECTED ===\n"
            + ", ".join(jd_hard_skills)
            + "\nVISIBILITY target: 100% — every skill above should appear somewhere on the resume "
              "(experience bullet, stretch bullet, or skills/project section) when a defensible placement exists.\n"
            + "PRODUCTION-CLAIM target: 85–95% — only WORK-SUPPORTED and ADJACENT-STRETCH skills may read as "
              "real employer production work. SELF-IMPLEMENTABLE and HIGH-RISK skills satisfy visibility only, "
              "via skills/project/prototype wording — never as employer production claims.\n"
        )

    declared_section = ""
    if profile_skills:
        declared_section = (
            "\n=== CANDIDATE'S FULL SKILL INVENTORY (reference only — do NOT dump all of these) ===\n"
            + ", ".join(profile_skills)
            + "\nUse the 3-layer skills section rule: include JD-named + bullet-backed + up to 10 related helpful."
            + " This list is a reference pool — not a mandate to include everything.\n"
        )

    # Build per-job bullet requirement string — RANGES, not exact counts.
    # Exact counts force filler bullets on thin jobs; ranges let the model
    # stop when real content runs out. Lint enforces min and max separately.
    _job_counts = (
        f"job1={minimums[0]}-{budget[0]}, job2={minimums[1]}-{budget[1]}, "
        f"job3={minimums[2]}-{budget[2]}, job4+={minimums[3]}-{budget[3]}"
    )

    user_msg = (
        f"Tailor this resume to the JD. "
        f"Role type detected: {role_type}. "
        f"Bullet counts per job (min-max RANGES — hit the minimum, never exceed the max, "
        f"and never pad with filler to reach the max): "
        f"summary={SUMMARY_EXACT} (exact), {_job_counts}. "
        f"Hard total cap: {hard_total}. Lint FAILS below any minimum or above any maximum. "
        f"Output: plain text resume only.\n"
        f"{declared_section}"
        f"{jd_skills_section}\n"
        "STEP 1 — Open a <plan> block with exactly 5 lines:\n"
        "  1. ROLE: [role type] | STAGE: [startup/enterprise] | TITLE: [clean JD role title — strip tech-stack/location/req-ID suffixes after dash, pipe, colon, or parenthesis]\n"
        "  2. PRIMARY: [top 3 JD responsibilities and which job/bullet covers each]\n"
        "  3. TIMELINE_BLOCKS: [any JD tool not enterprise-ready by that job's end date → exclude from that job's bullets; 'none' if clear]\n"
        "  4. GAPS: [for each JD skill absent from base resume: 'Skill → tier W/A/S/H → placed at [Job/Skills] as [bullet/tech-line/skills-row]'."
        " Every entry here is a COMMITMENT — it must appear in Step 2. Never list a gap and skip it.]\n"
        "  5. JOB_HEADERS: [copy every job header verbatim from original resume — Title @ Company | City, State   Month YYYY – Month YYYY]\n"
        "Close </plan>.\n\n"
        "STEP 2 — Write the complete tailored resume following all system prompt rules.\n\n"
        f"=== JOB DESCRIPTION ===\n{job_description[:16000]}\n\n"
        f"=== ORIGINAL RESUME ===\n{base_resume}"
    )

    raw = await chat(
        system=SYSTEM_PROMPT,
        user=user_msg,
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=4000,
        pass_name="main-tailor",
        allow_fallback=False,
        retry_on_ratelimit=2,
        keys=keys,
    )

    # Strip <plan> block
    raw = re.sub(r'<plan>.*?</plan>', '', raw, flags=re.DOTALL).strip()

    # ── Deterministic bullet trim — BEFORE the lint loop ─────────────────────
    # The base resume's own bullets run 26-40 words; the model copies that
    # style. One run showed 19 [TOO LONG] + 8 [MULTI-IDEA] on lint-1, all
    # burnable for free here. Zero AI calls.
    from resume_lint import WORD_LIMIT as _WL
    raw = _trim_long_bullets(raw, _WL)

    # Metric-density issues are handled deterministically by
    # _enforce_metric_density after the loop. Retrying them causes
    # ping-pong (HIGH 68% -> model overcorrects -> LOW 19% observed live).
    # LOW JD SKILL VISIBILITY never retries: skill-inject + keyword-inject
    # own that downstream, and the loop can't sensibly add junk-adjacent
    # skills anyway (burned 2 retries on "Computer Science" live).
    _NO_RETRY_PREFIXES = ("[HIGH METRICS]", "[LOW METRICS]", "[LOW JD SKILL VISIBILITY]")
    # JD ECHO gets ONE retry, then drops: live runs show whack-a-mole —
    # fixing "workflows/reports" surfaces "analysis/dashboards" at 3x.
    _ECHO_PREFIX = "[JD ECHO]"

    def _retryable(iss_list, attempt: int = 0):
        out = [i for i in iss_list if not i.startswith(_NO_RETRY_PREFIXES)]
        if attempt >= 1:
            out = [i for i in out if not i.startswith(_ECHO_PREFIX)]
        return out

    # ── Quality gate: lint → up to 3 retries, best-of-N ────────────────────
    _best_raw         = raw
    _best_issue_count = len(_retryable(
        lint_resume(raw, job_description, base_resume=base_resume, role_type=role_type)
        + detect_domain_leak(raw, role_type, base_resume)))
    _lint_clean_first = False   # attempt 0 passed lint with zero issues

    for attempt in range(3):
        issues = lint_resume(raw, job_description, base_resume=base_resume, role_type=role_type)
        issues += detect_domain_leak(raw, role_type, base_resume)
        issues = _retryable(issues, attempt)

        if len(issues) <= _best_issue_count:
            _best_issue_count = len(issues)
            _best_raw = raw

        if not issues:
            if attempt == 0:
                _lint_clean_first = True
            break

        # Log what lint found so Railway logs reveal the actual failure pattern
        print(f"[lint-{attempt+1}] {len(issues)} issue(s): " +
              " | ".join(i[:60] for i in issues))

        # ── Classify issues ───────────────────────────────────────────────────
        # NOTE: [BULLET OVERFLOW] must NOT go to the augmenter — it ADDS bullets,
        # overflow needs cutting. Overflow routes to the targeted retry instead.
        _COUNT_PREFIXES = ("[TOO FEW", "[SUMMARY]")
        count_issues = [i for i in issues if i.startswith(_COUNT_PREFIXES)]
        other_issues = [i for i in issues if not i.startswith(_COUNT_PREFIXES)]

        # ── Route: bullet-count issues → augmenter (cheap, surgical) ─────────
        # Augmenter inserts/removes individual bullets without regenerating the
        # full resume. No SYSTEM_PROMPT → ~$0.002 per call vs ~$0.008 retry.
        if count_issues and not other_issues:
            # ONLY count issues — augmenter can fix all of them
            raw = await augment_bullet_counts(
                raw, count_issues, job_description,
                api_key, provider, _sec, keys=keys,
            )
            continue  # re-lint immediately without a full retry

        if count_issues and other_issues:
            # Both: augment counts first, then do one targeted retry for the rest
            raw = await augment_bullet_counts(
                raw, count_issues, job_description,
                api_key, provider, _sec, keys=keys,
            )
            # Fall through to targeted retry for other_issues below
            issues = other_issues  # retry only non-count issues

        # ── Targeted retry for non-count issues ──────────────────────────────
        if not issues:
            continue

        issue_lines = "\n".join(
            "  • {}\n    → {}".format(
                iss,
                _RETRY_RULES.get(
                    "[" + iss.split("]")[0].lstrip("[") + "]",
                    "Re-read the system prompt rules and fix this issue."
                )
            )
            for iss in issues
        )
        fix_msg = (
            f"TARGETED FIX — attempt {attempt + 2} of 3.\n"
            "Fix ONLY the specific issues listed below.\n"
            "CRITICAL: Output the COMPLETE resume from the very first line to the very last line. "
            "Do NOT truncate, summarize, or omit any section — even sections you did not change. "
            "Every section (PROFESSIONAL SUMMARY, WORK EXPERIENCE with all jobs and bullets, "
            "TECHNICAL SKILLS, EDUCATION, CERTIFICATIONS) must appear in the output. "
            "Do not stop early. If the resume is long, output all of it.\n\n"
            f"ISSUES TO FIX:\n{issue_lines}\n\n"
            "=== RESUME TO FIX ===\n" + raw
        )

        raw = await chat(
            system=RETRY_SYSTEM_PROMPT,
            user=fix_msg,
            api_key=api_key,
            provider=provider,
            model=_sec,
            max_tokens=16384,
            pass_name=f"retry-{attempt+1}",
            keys=keys,
        )
        raw = re.sub(r'<plan>.*?</plan>', '', raw, flags=re.DOTALL).strip()
        # Truncation guard: if retry dropped required sections, revert to best known good
        if any(s not in raw for s in ("WORK EXPERIENCE:", "TECHNICAL SKILLS:", "EDUCATION:")):
            print(f"[RETRY] retry-{attempt+1} truncated — reverting to best-of-N")
            raw = _best_raw


    # Best-of-N final check
    final_issues = _retryable(
        lint_resume(raw, job_description, base_resume=base_resume, role_type=role_type)
        + detect_domain_leak(raw, role_type, base_resume))
    if len(final_issues) < _best_issue_count:
        _best_raw = raw
        _best_issue_count = len(final_issues)
    if _best_issue_count > 0 and _best_raw is not raw:
        print(
            f"[RETRY] Best-of-N: using earlier attempt "
            f"({_best_issue_count} issues remaining vs {len(final_issues)} in last)"
        )
    raw = _best_raw

    # ── Enforce hard limits — role-type-aware ────────────────────────────────
    result = _enforce_limits(raw, role_type=role_type)

    # ── Job integrity safety net — deterministic, no AI involvement ──────────
    # Runs before review so the reviewer never sees hallucinated companies.
    result, removed_jobs, reinserted_jobs = _enforce_job_integrity(result, base_resume)
    if removed_jobs:
        print(f"[JOB HALLUCINATION] Removed {len(removed_jobs)} fake job block(s): {', '.join(removed_jobs)}")
    if reinserted_jobs:
        print(f"[JOB RESTORED] Re-inserted {len(reinserted_jobs)} real job(s) verbatim: {', '.join(reinserted_jobs)}")

    # ── Missing-skill bullet injection — one dedicated bullet per JD gap ────
    # Skills the ORIGINAL resume lacked that the main pass still left without
    # an experience bullet each get one tier-worded bullet in the best job.
    # Runs BEFORE review (reviewer polishes them) and BEFORE tier audit
    # (audit validates the tier wording). Uses cheap secondary model.
    if skills_missing_from_original:
        try:
            _still_unbulleted = []
            _blocks_now = _parse_resume_sections(result)
            _exp_blob = "\n".join(
                "\n".join(b["bullets"]) for b in _blocks_now
            ).lower()
            from resume_lint import _dynamic_coverage_pattern as _cov_pat
            for _sk in skills_missing_from_original:
                if not re.search(_cov_pat(_sk), _exp_blob):
                    _still_unbulleted.append(_sk)
            if _still_unbulleted:
                print(f"[SKILL INJECT] {len(_still_unbulleted)} JD skill(s) lack an experience bullet: {', '.join(_still_unbulleted[:8])}")
                result = await inject_missing_skill_bullets(
                    result, _still_unbulleted, base_resume, job_description,
                    role_type, api_key, provider, _sec, keys=keys,
                )
        except Exception as e:
            print(f"[SKILL INJECT] Failed: {e}")

    # ── Semantic review — 1 pass, no retry ──────────────────────────────────
    # Merged with the tier audit (one call instead of two). Skipped entirely
    # when attempt 0 passed lint clean — a first-try-clean resume gains
    # nothing from review, so save the call. Audit still runs standalone
    # if there are gap-filled skills to check.
    _REQUIRED_SECTIONS = ["WORK EXPERIENCE:", "TECHNICAL SKILLS:", "EDUCATION:"]
    violations: list[str] = []
    _audit_done = False

    if _lint_clean_first:
        print("[REVIEW] Skipped — lint clean on first attempt")
    else:
        pre_review = result
        reviewed, _audit_report = await review_resume(
            result, job_description, api_key, provider, _sec,
            profile_skills=profile_skills,
            base_resume=base_resume,
            missing_skills=skills_missing_from_original,
            keys=keys,
        )
        # Truncation guard: if reviewer dropped any required section, discard its output
        _review_truncated = any(s not in reviewed for s in _REQUIRED_SECTIONS)
        if _review_truncated:
            print("[REVIEW] Truncation detected — discarding reviewer output, keeping pre-review")
            result = pre_review
            _audit_report = ""  # audit judged a discarded resume — rerun standalone
        elif reviewed != pre_review:
            print("[REVIEW] Reviewer made changes")
            result = _restore_closing_lines(reviewed, pre_review, role_type)
            result = _restore_summary(result, pre_review)
        else:
            print("[REVIEW] No semantic violations found — resume passed all checks")
            result = reviewed
        if _audit_report:
            violations = _parse_tier_audit(_audit_report)
            _audit_done = True
            print("[TIER AUDIT] Merged with review call — no separate audit call")

    # ── Post-review lint — log WARN only, no retry ───────────────────────────
    post_issues = lint_resume(result, job_description, base_resume=base_resume, role_type=role_type)
    if post_issues:
        print(f"[WARN] post-review lint ({len(post_issues)}):")
        for iss in post_issues:
            print(f"  • {iss}")

    if skill_coverage_report is not None:
        coverage = skill_coverage_report(
            result, job_description, role_type=role_type, profile_skills=profile_skills
        )
        if coverage.get("jd_skills"):
            print(
                f"[VISIBILITY] JD hard skills visible on resume: {coverage['coverage_text']} "
                f"({coverage['coverage_ratio']:.0%}) — presence check only, "
                f"not a verification of production-claim tier."
            )
            if coverage.get("missing"):
                print("[VISIBILITY] Missing: " + ", ".join(coverage["missing"]))

    # ── Tier-compliance audit + hard-gate correction ─────────────────────────
    # Audit normally rides the review call (above). Standalone call fires only
    # when review was skipped, truncated, or dropped the audit footer.
    if skills_missing_from_original:
        try:
            if not _audit_done:
                violations, _ = await audit_tier_compliance(
                    base_resume, result, skills_missing_from_original,
                    api_key, provider, _sec, keys=keys,
                )
            if violations:
                print(f"[TIER AUDIT] {len(violations)} violation(s) found:")
                for v in violations:
                    print(f"  • {v}")
                # Hard-gate: correct violations — remove fabricated bullets,
                # downgrade to skills-section-only placement.
                violation_summary = "\n".join(f"- {v}" for v in violations)
                correction_msg = (
                    f"The following bullets in the tailored resume are fabrications — "
                    f"the candidate has no real basis for these specific production claims:\n"
                    f"{violation_summary}\n\n"
                    f"For each violating bullet:\n"
                    f"  1. REMOVE the bullet entirely from the work experience section.\n"
                    f"  2. REMOVE the fabricated skill from that job's 'Technologies Used' "
                    f"     line too — listing it there still claims use at that job.\n"
                    f"  3. If the skill still needs visibility, keep it ONLY in the "
                    f"     TECHNICAL SKILLS section — never in a bullet or Technologies Used line.\n"
                    f"  4. Do NOT replace with another invented bullet.\n"
                    f"  5. Do NOT change any other bullets.\n"
                    f"Return the complete corrected resume as plain text only.\n\n"
                    f"=== ORIGINAL RESUME (ground truth) ===\n{base_resume}\n\n"
                    f"=== TAILORED RESUME TO CORRECT ===\n{result}"
                )
                corrected = await chat(
                    system="You are a precise resume editor. Remove only the specific fabricated bullets listed. Do not change anything else. Return the complete resume as plain text.",
                    user=correction_msg,
                    api_key=api_key,
                    provider=provider,
                    model=_sec,
                    max_tokens=16384,
                    pass_name="tier-correction",
                    keys=keys,
                )
                corrected = re.sub(r'<plan>.*?</plan>', '', corrected, flags=re.DOTALL).strip()
                # Truncation guard: correction must contain every required section —
                # a half-resume passing the old len//2 check once shipped to a user
                # cut off mid-word with no TECHNICAL SKILLS or EDUCATION.
                _corr_complete = all(
                    s in corrected for s in ("WORK EXPERIENCE:", "TECHNICAL SKILLS:", "EDUCATION:")
                )
                if corrected and _corr_complete and len(corrected) > len(result) // 2:
                    result = corrected
                    print(f"[TIER AUDIT] Correction applied — fabricated bullet(s) removed.")
                else:
                    print(f"[TIER AUDIT] Correction truncated/unexpected — keeping pre-correction resume.")
            else:
                print(f"[TIER AUDIT] Clean — {len(skills_missing_from_original)} gap-filled skill(s) audited, no violations.")
        except Exception as e:
            print(f"[TIER AUDIT] Audit pass failed to run: {e}")

    # ── Mechanical keyword injection — deterministic 100% visibility ─────────
    # Runs after all AI passes. For any JD keyword still absent from the
    # resume, injects it into the best-matching Technical Skills row.
    # No AI call. No retry. Guarantees keyword shows up somewhere honest.
    if job_description and skill_coverage_report is not None:
        try:
            final_cov  = skill_coverage_report(result, job_description, role_type=role_type)
            still_gone = final_cov.get("missing", [])
            if still_gone:
                result = _inject_missing_keywords(result, still_gone)
                # Confirm injection worked
                injected = [k for k in still_gone
                            if re.search(r'\b' + re.escape(k) + r'\b', result, re.IGNORECASE)]
                if injected:
                    print(f"[KEYWORD INJECT] Injected into skills section: {', '.join(injected)}")
                skipped = [k for k in still_gone if k not in injected]
                if skipped:
                    print(f"[KEYWORD INJECT] Could not inject (no skills section found): {', '.join(skipped)}")
        except Exception as e:
            print(f"[KEYWORD INJECT] Failed: {e}")

    # ── Skills 3-layer trim — remove non-JD, non-bullet Layer 3 overflow ──
    try:
        result = _trim_skills_to_layers(result, jd_hard_skills, max_layer3=3)
    except Exception as e:
        print(f"[SKILLS TRIM] Failed: {e}")

    # ── Concept-word deduplication — remove concept words proven by tools ──
    try:
        result = _remove_concept_redundancy(result)
    except Exception as e:
        print(f"[CONCEPT DEDUP] Failed: {e}")

    # ── Grammar fix — insert 'by' before bare metric percentages ──────────
    try:
        result = _fix_metric_grammar(result)
    except Exception as e:
        print(f"[GRAMMAR] Metric 'by' fix failed: {e}")

    # ── Narration strip + re-trim — reviewer runs LAST of the AI passes and
    # re-lengthens bullets / appends evidence clauses. Live output shipped
    # 30-45-word bullets with 'measured by comparing...' tails. Enforce here.
    try:
        result = _strip_metric_narration(result)
        from resume_lint import WORD_LIMIT as _WL2
        result = _trim_long_bullets(result, _WL2)
    except Exception as e:
        print(f"[NARRATION] Strip/re-trim failed: {e}")

    # ── Metric density ceiling — deterministic, no AI ─────────────────────
    # Models ignore the 40-50% prompt target (85-100% observed). Strip
    # trailing outcome clauses from lowest-relevance bullets until at most
    # half the experience bullets carry a number.
    try:
        result = _enforce_metric_density(result, role_type)
    except Exception as e:
        print(f"[METRIC DENSITY] Enforcement failed: {e}")

    # ── Singleton skills rows — deterministic min-2-items enforcement ─────
    try:
        result = _drop_singleton_skill_rows(result)
    except Exception as e:
        print(f"[SKILLS ROW] Singleton cleanup failed: {e}")

    # ── Skills line-length enforcement — max 6 items per line ─────────────
    try:
        result = _enforce_skills_line_limit(result, max_items=6)
    except Exception as e:
        print(f"[SKILLS LIMIT] Enforcement failed: {e}")

    # ── Merge cont. rows — no repeated labels in final output ──────────────
    try:
        result = _merge_cont_rows(result)
    except Exception as e:
        print(f"[MERGE CONT] Failed: {e}")

    # ── Tech-line cap — JD-relevant first, max 15 items ──────────────────
    try:
        result = _trim_tech_lines(result, jd_hard_skills, role_type)
    except Exception as e:
        print(f"[TECH LINE] Trim failed: {e}")

    # ── Education section safety net — deterministic, no AI involvement ──────
    # Runs after all AI passes. Compares EDUCATION section of final output
    # against the original base resume. If the AI altered it (degree name,
    # institution, year), hard-replaces with the verbatim original content.
    original_edu = _extract_education_section(base_resume)
    result_edu   = _extract_education_section(result)
    if original_edu and result_edu != original_edu:
        print("[EDUCATION MISMATCH] AI altered education section — reverting to original.")
        print(f"  Original : {original_edu[:120]}")
        print(f"  AI had   : {result_edu[:120]}")
        result = _replace_education_section(result, original_edu)

    # ── Header safety net — deterministic, no AI ─────────────────────────────
    # Checks that name + contact appear at the top. If AI dropped them (even
    # after lint retries), restores from base resume without another AI call.
    try:
        result = _ensure_header(result, base_resume)
    except Exception as e:
        print(f"[HEADER] Safety net failed: {e}")

    # ── Header title cleanup — strip posting suffixes (tech stacks, req IDs) ─
    try:
        result = _clean_header_title(result)
    except Exception as e:
        print(f"[HEADER TITLE] Cleanup failed: {e}")

    return result
