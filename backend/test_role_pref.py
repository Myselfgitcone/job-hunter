import asyncio, sys, io, contextlib, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JDS = {
    "healthcare_titled": """Senior Business Analyst, Regulatory Requirements - Molina Healthcare
Remote, US

Job Summary:
Molina Healthcare is hiring a Senior Business Analyst to support regulatory compliance reporting for Medicaid and Medicare programs.

Essential Functions:
- Analyze regulatory requirements and translate them into business and data requirements
- Partner with clinical operations, compliance, and IT teams to validate reporting accuracy
- Build dashboards and reports tracking claims, eligibility, and compliance metrics
- Document business processes and data flows for state and federal regulatory submissions
- Support audits and ensure data quality across Medicaid/Medicare reporting pipelines

Qualifications:
- 5+ years experience as a business/data analyst, healthcare industry preferred
- Strong SQL and Excel skills; experience with Tableau or Power BI
- Familiarity with HIPAA, CMS reporting requirements
- Bachelor's degree required
""",
    "finance_titled": """Financial Data Analyst - Regional Bank
New York, NY

Job Summary:
We are seeking a Financial Data Analyst to support FP&A reporting, budget variance analysis, and financial forecasting.

Responsibilities:
- Build and maintain financial models for budget forecasting and variance analysis
- Analyze month-end close data and reconcile discrepancies
- Partner with finance leadership on board-ready reporting
- Build SQL queries and dashboards to track KPIs across business units
- Support annual budgeting cycle and ad-hoc financial analysis

Qualifications:
- 4+ years in financial analysis or FP&A
- Strong SQL, Excel, and BI tool experience (Tableau/Power BI)
- Bachelor's in Finance, Accounting, or related field
""",
    "clean_data_analyst": """Data Analyst - Logistics Tech Co.
Remote, US

Job Summary:
We're looking for a Data Analyst to help our operations and product teams make data-driven decisions.

Responsibilities:
- Write complex SQL queries to analyze shipment, inventory, and operations data
- Build and maintain dashboards in Tableau/Power BI for stakeholders
- Partner with data engineering to ensure data quality and pipeline reliability
- Perform exploratory analysis to identify trends in delivery performance
- Present findings and recommendations to product and ops leadership

Qualifications:
- 3+ years as a data analyst
- Strong SQL, Python (pandas), and BI tooling experience
- Experience with A/B testing and statistical analysis a plus
""",
}

async def run_one(name, jd, env):
    api_key, provider, model = env['AI_API_KEY'], env['AI_PROVIDER'], env['AI_MODEL']
    from ai.tailor import tailor_resume

    cap = io.StringIO()
    with contextlib.redirect_stdout(cap):
        result = await tailor_resume(
            base_resume=BASE_RESUME, job_description=jd,
            api_key=api_key, provider=provider, model=model,
            profile_skills=None, secondary_model="google/gemini-2.5-flash",
            user_job_roles=["Data Analyst"],
        )
    log = cap.getvalue()

    plan_m = re.search(r'<plan>(.*?)</plan>', log, re.DOTALL)
    role_line = ""
    for line in log.splitlines():
        if "ROLE:" in line or "Role type" in line:
            role_line = line.strip()
            break

    bullets = [l.strip() for l in result.splitlines() if l.strip().startswith('•')]
    finance_terms = re.findall(r'(?i)\b(variance|forecast|FP&A|budget|reconcil|board-ready|P&L|month-end close)\b', result)
    health_terms = re.findall(r'(?i)\b(clinical|patient|HIPAA|Medicaid|Medicare|CMS|claims adjud|care coordination)\b', result)

    out_file = f"role_pref_{name}.txt"
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f"\n=== {name} ===")
    print(f"  bullet count: {len(bullets)} (TECH budget = 11/8/7/5, total 37)")
    print(f"  finance terms found: {sorted(set(finance_terms)) or 'none'}")
    print(f"  healthcare terms found: {sorted(set(health_terms)) or 'none'}")
    print(f"  saved -> {out_file}")
    return result

async def main():
    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)

    for name, jd in JDS.items():
        await run_one(name, jd, env)

if __name__ == "__main__":
    asyncio.run(main())
