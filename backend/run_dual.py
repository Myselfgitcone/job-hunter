"""Real pipeline run: RIVO + Northern Trust JDs in parallel."""
import asyncio, sys, io, contextlib, re
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

RIVO_JD = """Data Engineer - RIVO Holdings
Build and maintain scalable ETL/ELT pipelines that move data from production systems into analytical environments.
Design and optimize data warehouse structures to support reporting, business intelligence, and analytics use cases.
Ingest and integrate data from multiple sources, including databases, APIs, and third-party systems.
Develop and maintain data models that support efficient querying and downstream consumption.
Write and optimize complex SQL queries to transform, validate, and analyze data.
Establish data quality checks and monitoring processes to ensure accuracy, reliability, and completeness.
Partner with Engineering, Product, and Analytics teams to define data requirements and deliver trusted datasets.
Support Data Science and analytics initiatives by providing clean, structured, and accessible data.
Implement data governance best practices, including data security, access controls, and lifecycle management.
Troubleshoot data pipeline issues, performance bottlenecks, and data inconsistencies.
Continuously improve and automate data workflows to increase efficiency and reduce manual processes.
Provide technical guidance to team members through collaboration and code reviews.
Qualifications: Bachelor's degree in Computer Science or related field.
4-6+ years of experience in data engineering, data warehousing, or a related field.
Strong expertise in SQL, including complex queries and performance optimization.
Proficiency in Python for data processing and automation.
Experience building and maintaining production-grade data pipelines and warehouse systems.
Experience integrating data from multiple sources into analytical environments.
Familiarity with data modeling, ETL/ELT processes, and pipeline orchestration.
Experience with data quality validation, monitoring, and troubleshooting."""

NT_JD = """Data Engineer - Northern Trust
Solves complex problems and takes a new perspective on existing solutions.
Exercises judgment based on the analysis of multiple sources of information.
Impacts a range of customer, operational, project or service activities within own team and other related teams.
Works within broad guidelines and policies.
Requires in-depth conceptual and practical knowledge in own job discipline and basic knowledge of related job disciplines.
Applies best practices and how own area integrates with others.
Is aware of the competition and the factors that differentiate them in the market.
Explains difficult or sensitive information and works to build consensus.
Acts as a resource for colleagues with less experience.
May lead small projects with manageable risks and resource requirements.
Financial services data engineering, data pipelines, data warehousing, SQL, Python.
Data integration, ETL, data quality, analytics, reporting."""


async def run_one(label, jd):
    from resume_lint import detect_role_type, lint_resume, extract_jd_hard_skills, extract_jd_keywords_dynamic, skill_coverage_report, _dynamic_coverage_pattern
    from ai.tailor import tailor_resume

    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    api_key, provider, model = env['AI_API_KEY'], env['AI_PROVIDER'], env['AI_MODEL']

    role_type = detect_role_type(jd)
    jd_skills = extract_jd_hard_skills(jd, role_type)

    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = await tailor_resume(
            base_resume=BASE_RESUME,
            job_description=jd,
            api_key=api_key,
            provider=provider,
            model=model,
            profile_skills=None,
        )
    log = capture.getvalue()

    cov = skill_coverage_report(result, jd, role_type=role_type)
    lint_issues = lint_resume(result, jd, base_resume=BASE_RESUME)

    lines = result.splitlines()
    placements = {}
    for kw in sorted(jd_skills):
        pat = _dynamic_coverage_pattern(kw)
        in_bullet = in_skills = in_tech = False
        for line in lines:
            if re.search(pat, line, re.IGNORECASE):
                l = line.strip()
                if l.startswith('•'): in_bullet = True
                elif 'Technologies Used:' in line: in_tech = True
                elif re.match(r'^[A-Z][A-Za-z /&]+:\s+\S', l): in_skills = True
        if in_bullet: placements[kw] = 'BULLET'
        elif in_tech:  placements[kw] = 'TECH_USED'
        elif in_skills: placements[kw] = 'SKILLS_ROW'
        else: placements[kw] = 'ABSENT'

    return {
        'label': label,
        'role_type': role_type,
        'jd_skills': jd_skills,
        'log': log,
        'resume': result,
        'coverage': cov,
        'lint': lint_issues,
        'placements': placements,
    }


async def main():
    print("Running RIVO and Northern Trust pipelines...")
    rivo, nt = await asyncio.gather(
        run_one('RIVO', RIVO_JD),
        run_one('Northern Trust', NT_JD),
    )

    for r in [rivo, nt]:
        print(f"\n{'='*70}")
        print(f"JD: {r['label']}  |  Role: {r['role_type']}")
        print(f"{'='*70}")
        print(f"\n[PIPELINE LOG]")
        for line in r['log'].splitlines():
            if line.strip(): print(f"  {line}")

        print(f"\n[FINAL RESUME]")
        print('-'*60)
        print(r['resume'])
        print('-'*60)

        print(f"\n[COVERAGE] {r['coverage']['coverage_text']} ({r['coverage']['coverage_ratio']:.0%})")
        print(f"  Keywords: {', '.join(r['jd_skills'])}")
        print(f"  Missing:  {', '.join(r['coverage']['missing']) if r['coverage']['missing'] else 'none'}")

        print(f"\n[LINT] {len(r['lint'])} issue(s)")
        for i in r['lint']: print(f"  * {i}")

        print(f"\n[PLACEMENT — each keyword]")
        for kw, loc in r['placements'].items():
            print(f"  {loc:12} {kw}")

    # Save
    with open('dual_out.txt', 'w', encoding='utf-8') as f:
        for r in [rivo, nt]:
            f.write(f"\n{'='*70}\n{r['label']}\n{'='*70}\n")
            f.write(r['resume'])
            f.write('\n')

    print("\nSaved to dual_out.txt")

asyncio.run(main())
