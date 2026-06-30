"""Run Purpose Financial JD — tailor + HackerRank 4-dimension scoring."""
import asyncio, sys, io, contextlib, os, json, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

PURPOSE_JD = """Data Architect - Purpose Financial
Design, implement, and optimize data models, databases, data warehouses, and data lakes.
Architect and implement data integration solutions, ETL pipelines, and data governance frameworks.
Design and implement master data management (MDM) strategies, metadata management solutions.
Experience with NoSQL, Kafka, Middleware, and cloud-based platforms (e.g., AWS, Snowflake).
Certifications (e.g., Certified Solutions Architect) are highly desirable.
Data catalog, data lineage, and data architecture standards.
Technical knowledge in data quality standards, governance, and design.
3-5 years experience in data architecture, database design, and data management."""

SCORE_SYS = "You are a fair evidence-based resume evaluator. Return only valid JSON. No extra text."

SCORE_USER = """Score this resume across 4 dimensions for a Data Architect role.

SCORING (be strict, evidence only):

open_source (0-35): Contributing to OTHER repos. Personal repos only = max 10pts. PRs merged to 1000+ star projects = 25-35pts.
self_projects (0-30): Complex deployed projects with links = high. Tutorial/no links = low. -3 to -5 per project missing URL.
production (0-25): Real companies, real scale, quantified impact, years experience.
technical_skills (0-10): Breadth + depth demonstrated in actual work.
bonus (max 20): +2 for portfolio URL, +3-5 startup founder, +1 LinkedIn.
deductions: -2 to -5 per project without link/demo.

Return ONLY this JSON structure:
{"scores":{"open_source":{"score":0,"max":35,"evidence":""},"self_projects":{"score":0,"max":30,"evidence":""},"production":{"score":0,"max":25,"evidence":""},"technical_skills":{"score":0,"max":10,"evidence":""}},"bonus_points":{"total":0,"breakdown":""},"deductions":{"total":0,"reasons":""},"key_strengths":[],"areas_for_improvement":[]}

RESUME:
"""

async def score_resume(resume_text, api_key, provider):
    from ai.llm import chat
    resp = await chat(
        system=SCORE_SYS, user=SCORE_USER + resume_text,
        api_key=api_key, provider=provider,
        model="google/gemini-2.5-flash",
        max_tokens=1200, pass_name="hr-score",
    )
    m = re.search(r'\{[\s\S]*\}', resp)
    if m:
        try: return json.loads(m.group())
        except: pass
    return {}

def show_score(s, label):
    if not s or "scores" not in s: print(f"  {label}: parse error"); return
    scores = s["scores"]
    base = sum(min(v["score"], v["max"]) for v in scores.values())
    bonus = s.get("bonus_points", {}).get("total", 0)
    ded = s.get("deductions", {}).get("total", 0)
    final = base + bonus - ded
    print(f"\n{'='*50}")
    print(f"  {label}: {final}/100  (base={base} bonus=+{bonus} deductions=-{ded})")
    print(f"{'='*50}")
    for dim, d in scores.items():
        capped = min(d["score"], d["max"])
        pct = int(capped / d["max"] * 20)
        bar = "█"*pct + "░"*(20-pct)
        print(f"  {dim:20s} [{bar}] {capped:2d}/{d['max']}")
        print(f"    {d['evidence'][:100]}")
    if ded > 0:
        print(f"\n  Deductions (-{ded}): {s['deductions']['reasons'][:100]}")
    if s.get("key_strengths"):
        print(f"\n  Strengths:")
        for x in s["key_strengths"][:3]: print(f"    + {x}")
    if s.get("areas_for_improvement"):
        print(f"\n  Improve:")
        for x in s["areas_for_improvement"][:2]: print(f"    - {x}")

async def main():
    from resume_lint import extract_jd_hard_skills, skill_coverage_report
    from ai.tailor import tailor_resume

    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    api_key, provider, model = env['AI_API_KEY'], env['AI_PROVIDER'], env['AI_MODEL']

    print("\n[1] Scoring BASE resume on HackerRank rubric...")
    base_score = await score_resume(BASE_RESUME, api_key, provider)
    show_score(base_score, "BASE RESUME")

    print("\n[2] Running tailor pipeline...")
    cap = io.StringIO()
    with contextlib.redirect_stdout(cap):
        result = await tailor_resume(
            base_resume=BASE_RESUME, job_description=PURPOSE_JD,
            api_key=api_key, provider=provider, model=model,
            profile_skills=None, secondary_model="google/gemini-2.5-flash",
        )
    log = cap.getvalue()

    print("\n[3] Pipeline log:")
    for line in log.splitlines():
        if line.strip(): print(f"  {line}")

    cov = skill_coverage_report(result, PURPOSE_JD)
    print(f"\n[4] ATS coverage: {cov['coverage_text']} ({cov['coverage_ratio']:.0%})")
    if cov['missing']: print(f"    Missing: {', '.join(cov['missing'])}")

    print("\n[5] Scoring TAILORED resume on HackerRank rubric...")
    tai_score = await score_resume(result, api_key, provider)
    show_score(tai_score, "TAILORED RESUME")

    def total(s):
        if not s or "scores" not in s: return 0
        t = sum(min(v["score"], v["max"]) for v in s["scores"].values())
        return t + s.get("bonus_points",{}).get("total",0) - s.get("deductions",{}).get("total",0)

    b, t = total(base_score), total(tai_score)
    delta = t - b
    print(f"\n{'='*50}")
    print(f"  IMPROVEMENT: {b}/100 → {t}/100  ({'+' if delta>=0 else ''}{delta} points)")
    print(f"{'='*50}")

    print("\n[6] Final tailored resume:")
    print("-"*60)
    print(result)
    print("-"*60)

    with open('purpose_financial_out.txt', 'w', encoding='utf-8') as f:
        f.write(f"LOG:\n{log}\n\nRESUME:\n{result}\n")

asyncio.run(main())
