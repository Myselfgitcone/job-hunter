"""
Full pipeline test: Jagadish resume x 3 JDs.
Captures all stdout, writes to UTF-8 file per JD.
"""
import asyncio, sys, os, io, contextlib
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JDS = {
    "JD1_CVS": """Data Engineer — CVS Health / Caremark (Irving, TX)
Design, build and manage large scale data structures, pipelines and ETL/ELT workflows.
Develop large scale data structures and pipelines to organize, collect and standardize data.
Write ETL processes, design database systems, develop tools for real-time and offline analytic processing.
Collaborate with Data Science team to transform data and integrate algorithms and models.
Leverage knowledge of Hadoop architecture, HDFS commands, and optimizing queries to build data pipelines.
Utilize Python, Java, or similar languages to build robust data pipelines and dynamic systems.
Build data marts and data models to support Data Science and internal customers.
Integrate data from variety of sources and ensure adherence to data quality and accessibility standards.
Analyze current IT environments to identify critical capabilities and recommend solutions.
Requirements: Master's degree in Computer Science, Data Science, Statistics, Mathematics, Analytics.
2+ years experience in: GIT, DB2, JIRA, Rally, Confluence; Agile methodologies; Google Cloud Platform (GCP);
Hadoop or Hive; BQ, GCS, Python, MySQL, SQL, HDFS; Spark, PySpark, Airflow;
Writing application code and deploying to production; Relational database concepts; ETL processes;
Data analytics on large data sets in healthcare, business, or retail sector.""",

    "JD2_Paramount": """Data Engineer – Data Pipeline & ETL — Paramount Streaming
Build and maintain scalable data pipelines for large-scale structured and unstructured datasets.
Build robust ETL/ELT frameworks supporting analytics, BI, experimentation, and machine learning.
Optimize pipelines for performance, reliability, scalability, and cost efficiency.
Implement CDC, incremental loads, and event-driven processing patterns.
Design scalable dimensional and hybrid data models optimized for analytics and ML.
Develop reusable transformation layers (semantic layers) serving BI, ML, and AI applications.
Write optimized production-grade SQL for large-scale analytics workloads.
Implement automated data validation, anomaly detection, and monitoring frameworks.
Establish data lineage and metadata standards for ML workflow reproducibility.
Enforce governance, privacy, and security best practices for sensitive AI datasets.
Build real-time data pipelines using Kafka, Pub/Sub, or similar technologies.
Experience with feature streaming, low-latency data processing, and event-driven architectures.
Design cloud-native data architectures (GCP preferred).
Experience with Lakehouse architectures and cloud data warehouses.
Familiarity with vector databases, embeddings pipelines, and AI-serving infrastructure.
Integrate data pipelines with ML platforms such as Vertex AI, Databricks ML, or equivalent.
2-4+ years in data engineering, data pipeline development.
Proven track record of technical leadership and cross-functional collaboration.""",

    "JD3_Kyndryl": """Data Analyst — Kyndryl
Harness expertise in basic statistics, business fundamentals, and communication to uncover valuable insights.
Transform raw data into rigorous visualizations and compelling stories.
Work closely with customers as part of a team — client-facing role.
Dive into vast IT datasets, unravel trends and patterns to revolutionize customers' understanding.
Draw compelling conclusions and develop data-driven insights impacting decision-making.
Act as trusted advisor, utilizing domain expertise, critical thinking, and consulting skills.
Unravel complex business problems and translate into innovative solutions.
Gather, explore, and prepare data for analysis, business intelligence, and insightful visualizations.
Collaborate closely with cross-functional teams to gather, structure, organize, and clean data.
Communicate and empathize with stakeholders, understanding business objectives and success criteria.
Mastery of business valuation, decision-making, project scoping, and storytelling.
Determine root causes of defects and variation.
5+ years of data analysis experience.
Tools: Looker, Power BI, QuickSight, BigQuery, Azure Synapse, Python, R, SQL.
Professional certification e.g. ASQ Six Sigma.
Cloud platform certification e.g. AWS Certified Data Analytics, Google Cloud Looker, Microsoft Power BI.""",
}


async def run_one(jd_name, jd_text, api_key, provider, model, out):
    from resume_lint import detect_role_type, lint_resume
    from ai.tailor import tailor_resume

    try:
        from resume_lint import extract_jd_hard_skills, skill_coverage_report
    except ImportError:
        extract_jd_hard_skills = None
        skill_coverage_report = None

    out.write(f"\n{'='*70}\n{jd_name}\n{'='*70}\n")

    # Step 1: role type
    role_type = detect_role_type(jd_text)
    out.write(f"\n[STEP 1] detect_role_type() = {role_type}\n")

    # Step 2: JD hard skills
    if extract_jd_hard_skills:
        jd_skills = extract_jd_hard_skills(jd_text, role_type)
        out.write(f"\n[STEP 2] extract_jd_hard_skills() ({len(jd_skills)} skills):\n")
        out.write("  " + ", ".join(jd_skills) + "\n")
    else:
        out.write("\n[STEP 2] extract_jd_hard_skills not available\n")
        jd_skills = []

    # Step 3: full tailor with stdout capture
    out.write(f"\n[STEP 3] Running tailor_resume()...\n")
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = await tailor_resume(
            base_resume=BASE_RESUME,
            job_description=jd_text,
            api_key=api_key,
            provider=provider,
            model=model,
            profile_skills=None,  # no declared skills override — use JD-driven
        )
    log_output = capture.getvalue()

    # Step 4: pipeline log
    out.write(f"\n[STEP 4] Pipeline log output:\n")
    for line in log_output.splitlines():
        out.write(f"  {line}\n")

    # Step 5: final resume
    out.write(f"\n[STEP 5] FINAL TAILORED RESUME:\n")
    out.write("-"*60 + "\n")
    out.write(result)
    out.write("\n" + "-"*60 + "\n")

    # Step 6: coverage report on final output
    if skill_coverage_report and jd_skills:
        cov = skill_coverage_report(result, jd_text, role_type=role_type, profile_skills=None)
        out.write(f"\n[STEP 6] skill_coverage_report() on final output:\n")
        out.write(f"  coverage: {cov.get('coverage_text', 'n/a')}  ({cov.get('coverage_ratio', 0):.0%})\n")
        if cov.get('missing'):
            out.write(f"  still missing: {', '.join(cov['missing'])}\n")
        else:
            out.write("  no missing skills\n")
    else:
        out.write("\n[STEP 6] skill_coverage_report not available\n")

    # Step 7: post-delivery lint
    lint_issues = lint_resume(result, jd_text)
    out.write(f"\n[STEP 7] lint_resume() on final output: {len(lint_issues)} issue(s)\n")
    for iss in lint_issues:
        out.write(f"  * {iss}\n")

    # summary stats
    ai_calls = log_output.count("[RETRY]") + log_output.count("[REVIEW]") + log_output.count("[TIER AUDIT]") + log_output.count("[VISIBILITY]")
    retries = log_output.count("attempt")
    cov_ratio = cov.get('coverage_ratio', 0) if (skill_coverage_report and jd_skills) else None
    return {
        "role_type": role_type,
        "lint_issues": len(lint_issues),
        "coverage": f"{cov_ratio:.0%}" if cov_ratio is not None else "n/a",
        "log_lines": len([l for l in log_output.splitlines() if l.strip()]),
    }


async def main():
    engine = create_async_engine(os.getenv('DATABASE_URL', ''))
    async with AsyncSession(engine) as sess:
        r = await sess.execute(text(
            "SELECT ai_api_key, ai_provider, ai_model_tailor "
            "FROM user_settings WHERE user_id='6d3dda6b-c809-4f11-b9e2-97f70cd87028'"
        ))
        row = r.fetchone()
    api_key, provider, model = row
    print(f"Using provider={provider}  model={model}")
    print("Running 3 JDs — this will take ~8-12 minutes total...\n")

    out = io.StringIO()
    summaries = {}

    for jd_name, jd_text in JDS.items():
        print(f"  Running {jd_name}...")
        stats = await run_one(jd_name, jd_text, api_key, provider, model, out)
        summaries[jd_name] = stats
        print(f"  {jd_name} done. role={stats['role_type']} lint={stats['lint_issues']} cov={stats['coverage']}")

    # Write all output to file
    with open('pipeline_out.txt', 'w', encoding='utf-8') as f:
        f.write(out.getvalue())

    # Summary table
    print("\n" + "="*70)
    print("SUMMARY TABLE")
    print("="*70)
    print(f"{'JD':<20} {'Role Type':<12} {'Lint Issues':<14} {'Coverage'}")
    print("-"*60)
    for jd_name, s in summaries.items():
        print(f"{jd_name:<20} {s['role_type']:<12} {s['lint_issues']:<14} {s['coverage']}")

asyncio.run(main())
