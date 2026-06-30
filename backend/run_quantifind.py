import asyncio, sys, io, contextlib, re, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JD = """AI Data Engineer - Quantifind
Palo Alto, CA (Remote candidates considered)

Who We Are: Quantifind helps banks catch money laundering and fraud using AI platform
that uncovers signals of risk across unstructured text sources. KYC, CDD, Fraud Risk,
AML (Anti-Money Laundering) compliance SaaS platform.

What You Will Do:
Drive data discovery, open-source intelligence (OSINT) and data acquisition.
Build and manage reliable ETL pipelines with focus on speed from discovery to value.
Database indexing, performance tuning, concurrency, and load balancing.
Perform data quality assurance and independent testing.
Work across structured and unstructured data parsing, enrichment, data architecture.
Ontology management, knowledge graphs, and data fusion.
Manage data compliance, documentation, and data cards.

What We Are Looking For:
4+ years of professional experience.
Core stack: Python. Helpful: Spark/PySpark, Scala, and other large-scale data tooling.
Database management experience: PostgreSQL, RDS.
Solid AWS cloud management experience.
Knowledge-graph and ontology frameworks (e.g., Neo4j).
Experience with large data pipelines, high-performance computing, and Spark/PySpark.
Hands-on with AI coding tools and agentic workflows (Claude Code, GPT/Codex, Cursor).
Multi-agent approaches for testing and validation.
Self-driven, mission-driven, startup mindset.
"""

async def main():
    from resume_lint import extract_jd_hard_skills, skill_coverage_report, _dynamic_coverage_pattern
    from ai.tailor import tailor_resume

    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    api_key, provider, model = env['AI_API_KEY'], env['AI_PROVIDER'], env['AI_MODEL']

    jd_skills = extract_jd_hard_skills(JD)
    print(f"[JD Keywords] ({len(jd_skills)}): {', '.join(sorted(jd_skills))}")

    cap = io.StringIO()
    with contextlib.redirect_stdout(cap):
        result = await tailor_resume(
            base_resume=BASE_RESUME, job_description=JD,
            api_key=api_key, provider=provider, model=model,
            profile_skills=None, secondary_model="google/gemini-2.5-flash",
        )
    log = cap.getvalue()

    print("\n[Pipeline log]")
    for line in log.splitlines():
        if line.strip(): print(f"  {line}")

    cov = skill_coverage_report(result, JD)
    print(f"\n[Coverage] {cov['coverage_text']} ({cov['coverage_ratio']:.0%})")
    if cov['missing']: print(f"  Missing: {', '.join(cov['missing'])}")

    # Pin-by-pin
    lines = result.splitlines()
    print("\n[Keyword placement]")
    for kw in sorted(jd_skills):
        pat = _dynamic_coverage_pattern(kw)
        in_bullet = in_tech = in_skills = False
        for line in lines:
            if re.search(pat, line, re.IGNORECASE):
                l = line.strip()
                if l.startswith('•'): in_bullet = True
                elif 'Technologies Used:' in line: in_tech = True
                elif re.match(r'^[A-Z][A-Za-z /&]+:\s+\S', l): in_skills = True
        loc = 'BULLET' if in_bullet else ('TECH_USED' if in_tech else ('SKILLS_ROW' if in_skills else 'ABSENT'))
        print(f"  {loc:12} {kw}")

    print("\n[Final resume]")
    print("-"*60)
    print(result)
    print("-"*60)

    with open('quantifind_out.txt', 'w', encoding='utf-8') as f:
        f.write(result)

asyncio.run(main())
