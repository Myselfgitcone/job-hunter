"""Real pipeline run: TRS Data Engineer JD."""
import asyncio, sys, io, contextlib, re
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JD = """Data Engineer (Intermediate or Senior) - TRS Teacher Retirement System of Texas
Austin, Texas

The Data Engineer is responsible for designing, developing, and optimizing data pipelines, data modeling, and platform management to support seamless integration and operation of data systems. The incumbent will maintain the data warehouse, generate complex reports, and perform in-depth data analysis, while actively contributing to Agile team activities.

WHAT WILL YOU DO:
Develop and manage data platforms.
Design and implement ETL processes and perform data lake management.
Implement and manage CI/CD pipelines.
Create and maintain data models to ensure structured data storage and accessibility.
Manage data catalogs to maintain an organized and easily accessible repository of data resources.
Develop and maintain data warehouses.
Manage data permissions, ensuring proper access control and data security.
Develop data-driven applications contributing to data solutions that support business needs.
Conduct data analysis and assist in data analysis projects, providing insights and support to business stakeholders.
Engage in Agile/Scrum activities.
Generate reports using reporting tools, including Power BI or equivalent.
Develop dashboards providing visibility into key performance, risk, and control indicators.

PREFERRED QUALIFICATIONS:
Experience with data architecture and modeling.
Experience with Microsoft Fabric, Databricks, Snowflake, Spark, SQL, Python, and cloud platforms.
Experience with data encryption (REST, SOAP, XML, JSON) and web services (SSL, SSH, SFTP).
DevOps principles, CI/CD, Azure services, Kubernetes, scripting skills (SQL, Python, PowerShell).
Terraform knowledge and Azure certifications preferred.

REQUIRED:
3-5+ years of data pipeline builds and implementation.
ETL tools for creating ETL scripts.
Power BI or equivalent modern data visualization.
Strong knowledge of SQL, Python, databases, and object-oriented programming.
Database modeling and data warehousing principles.
Microsoft Fabric, Databricks, Snowflake, Spark, and cloud platforms.
Agile/Scrum participation."""


async def main():
    from resume_lint import detect_role_type, lint_resume, extract_jd_hard_skills, extract_jd_keywords_dynamic, skill_coverage_report, _dynamic_coverage_pattern
    from ai.tailor import tailor_resume

    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    api_key, provider, model = env['AI_API_KEY'], env['AI_PROVIDER'], env['AI_MODEL']

    print(f"Provider: {provider}  Model: {model}\n")

    role_type = detect_role_type(JD)
    print(f"[STEP 1] detect_role_type() = {role_type}")

    jd_skills = extract_jd_hard_skills(JD, role_type)
    print(f"\n[STEP 2] JD keywords ({len(jd_skills)}): {', '.join(sorted(jd_skills))}")

    print(f"\n[STEP 3] Running tailor_resume()...")
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = await tailor_resume(
            base_resume=BASE_RESUME,
            job_description=JD,
            api_key=api_key,
            provider=provider,
            model=model,
            profile_skills=None,
        )
    log = capture.getvalue()

    with open('trs_out.txt', 'w', encoding='utf-8') as f:
        f.write(f"=== LOG ===\n{log}\n\n=== RESUME ===\n{result}\n")

    print("\n[STEP 4] Pipeline log:")
    for line in log.splitlines():
        if line.strip(): print(f"  {line}")

    print("\n[STEP 5] FINAL RESUME:")
    print("-"*60)
    print(result)
    print("-"*60)

    cov = skill_coverage_report(result, JD, role_type=role_type)
    print(f"\n[STEP 6] Coverage: {cov['coverage_text']} ({cov['coverage_ratio']:.0%})")
    print(f"  Covered: {', '.join(sorted(cov['covered']))}")
    print(f"  Missing: {', '.join(sorted(cov['missing'])) if cov['missing'] else 'none'}")

    lint_issues = lint_resume(result, JD, base_resume=BASE_RESUME)
    print(f"\n[STEP 7] Lint: {len(lint_issues)} issue(s)")
    for i in lint_issues: print(f"  * {i}")

    # Pin-by-pin placement
    lines = result.splitlines()
    print(f"\n[STEP 8] Keyword placement:")
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

asyncio.run(main())
