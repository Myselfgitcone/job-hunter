import asyncio, sys, io, contextlib, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JD = """Data Warehouse Manager - Lewisville TX / Irvine CA

Key Responsibilities:
Lead architecture, optimization, and administration of enterprise data warehouse.
Manage Microsoft Fabric, SQL Server, Lakehouse/Warehouse platforms.
Define enterprise data architecture standards, dimensional modeling, semantic models.
Manage end-to-end ELT/ETL pipelines integrating ERP, CRM, ecommerce, WMS, finance.
Ensure secure and scalable REST API/OData-based integrations.
Support enterprise reporting using Power BI, DAX, Power Platform, Dataverse.
Implement enterprise data governance, MDM, data quality monitoring, lineage, audit controls.
Lead, mentor, and develop a team of data engineers.
Support AI/ML and Copilot initiatives with AI-ready enterprise data foundations.
Serve as hands-on player-coach: architecture, troubleshooting, delivery execution.

Required:
7+ years data warehousing, BI, or enterprise analytics.
3+ years managing and developing technical teams.
Microsoft Fabric, SQL Server, T-SQL, Power BI, Power Platform, Dataverse.
Data Lake / Lakehouse architectures.
ETL/ELT pipeline design and management.
Dimensional modeling, semantic models, data ontology.
ERP, CRM, operational systems integrations.
Git, Azure DevOps, CI/CD pipelines, release management.
Manufacturing and distribution domain experience.

Preferred:
Databricks, PySpark, Python.
Azure AI, OpenAI services, AI agents.
MDM, Enterprise API architecture.
Microsoft Dynamics NAV / Business Central, Dynamics 365 CRM.
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

    with open('zocalo_out.txt', 'w', encoding='utf-8') as f:
        f.write(result)

asyncio.run(main())
