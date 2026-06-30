import asyncio, sys, io, contextlib, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JD = """Data Engineer - EXL Service
New York, NY (Hybrid)

Key Responsibilities:
Design and develop ETL/ELT pipelines using Azure Data Factory, Snowflake, and DBT.
Build and maintain data integration workflows from various data sources to Snowflake.
Write efficient and optimized SQL queries for data extraction and transformation.
Work with stakeholders to understand business requirements and translate them into technical solutions.
Monitor, troubleshoot, and optimize data pipelines for performance and reliability.
Provide technical leadership and mentorship to junior data engineers.
Maintain and enforce data quality, governance, and documentation standards.
Collaborate with data analysts, architects, and DevOps teams in a cloud-native environment.

Must-Have Skills:
Strong experience with Azure Cloud Platform services.
Proven expertise in Azure Data Factory (ADF) for orchestrating and automating data pipelines.
Proficiency in SQL for data analysis and transformation.
Hands-on experience with Snowflake and SnowSQL for data warehousing.
Practical knowledge of DBT (Data Build Tool) for transforming data in the warehouse.
Experience working in cloud-based data environments with large-scale datasets.

Good-to-Have Skills:
Experience with DataStage, Netezza, Azure Data Lake, Azure Synapse, or Azure Functions.
Familiarity with Python or PySpark for custom data transformations.
Understanding of CI/CD pipelines and DevOps for data workflows.
Exposure to data governance, metadata management, or data catalog tools.
Knowledge of business intelligence tools (e.g., Power BI, Tableau) is a plus.
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

    with open('exl_out.txt', 'w', encoding='utf-8') as f:
        f.write(result)
    print("\nSaved → exl_out.txt")

asyncio.run(main())
