"""
Proof runs for 3 bug fixes:
  Bug 1: Paramount education must be correct (Saint Louis, not JNTU)
  Bug 2: Kyndryl summary must not claim client-facing advisory
  Bug 3: Kyndryl must classify as CONSULTING, not TECH
"""
import asyncio, sys, os, io, contextlib
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

PARAMOUNT_JD = """Data Engineer - Data Pipeline & ETL - Paramount Streaming
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
Proven track record of technical leadership and cross-functional collaboration."""

KYNDRYL_JD = """Data Analyst - Kyndryl
Harness expertise in basic statistics, business fundamentals, and communication to uncover valuable insights.
Transform raw data into rigorous visualizations and compelling stories.
Work closely with customers as part of a team - client-facing role.
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
Cloud platform certification e.g. AWS Certified Data Analytics, Google Cloud Looker, Microsoft Power BI."""


async def run(jd_name, jd_text, api_key, provider, model):
    from resume_lint import detect_role_type
    from ai.tailor import tailor_resume

    role_type = detect_role_type(jd_text)

    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = await tailor_resume(
            base_resume=BASE_RESUME,
            job_description=jd_text,
            api_key=api_key,
            provider=provider,
            model=model,
            profile_skills=None,
        )
    log = capture.getvalue()
    return role_type, result, log


async def main():
    engine = create_async_engine(os.getenv('DATABASE_URL', ''))
    async with AsyncSession(engine) as sess:
        r = await sess.execute(text(
            "SELECT ai_api_key, ai_provider, ai_model_tailor "
            "FROM user_settings WHERE user_id='6d3dda6b-c809-4f11-b9e2-97f70cd87028'"
        ))
        row = r.fetchone()
    api_key, provider, model = row

    print("=== BUG 3 STATIC CHECK (before pipeline) ===")
    from resume_lint import detect_role_type
    kt = detect_role_type(KYNDRYL_JD)
    print(f"Kyndryl detect_role_type() = {kt}  (expect: CONSULTING)")
    print()

    print("Running Paramount (Bug 1 proof)...")
    p_role, p_result, p_log = await run("Paramount", PARAMOUNT_JD, api_key, provider, model)
    with open('proof_paramount.txt', 'w', encoding='utf-8') as f:
        f.write("=== PIPELINE LOG ===\n")
        f.write(p_log)
        f.write("\n=== FULL RESUME ===\n")
        f.write(p_result)

    print("Running Kyndryl (Bug 2 + Bug 3 proof)...")
    k_role, k_result, k_log = await run("Kyndryl", KYNDRYL_JD, api_key, provider, model)
    with open('proof_kyndryl.txt', 'w', encoding='utf-8') as f:
        f.write("=== PIPELINE LOG ===\n")
        f.write(k_log)
        f.write("\n=== FULL RESUME ===\n")
        f.write(k_result)

    # BUG 1 CHECK
    from ai.tailor import _extract_education_section
    p_edu = _extract_education_section(p_result)
    print("\n=== BUG 1 (Paramount education) ===")
    print(f"  Education line: {p_edu}")
    if "Saint Louis" in p_edu and "Master" in p_edu:
        print("  PASS - correct degree and institution")
    else:
        print("  FAIL - education still wrong!")

    # BUG 2 CHECK
    print("\n=== BUG 2 (Kyndryl unsupported claim) ===")
    lines = k_result.split("\n")
    in_summary = False
    summary_lines = []
    for ln in lines:
        s = ln.strip()
        if "PROFESSIONAL SUMMARY" in s.upper():
            in_summary = True
            continue
        if in_summary:
            if s == s.upper() and s.endswith(":") and len(s) > 3:
                break
            if s:
                summary_lines.append(s)
    print("  Summary section:")
    for sl in summary_lines:
        print(f"    {sl}")
    summary_text = "\n".join(summary_lines).lower()
    if "client-facing advisory" in summary_text:
        print("  FAIL - 'client-facing advisory' still present")
    else:
        print("  PASS - unsupported claim removed or corrected")

    # BUG 3 CHECK
    print(f"\n=== BUG 3 (Kyndryl role type) ===")
    print(f"  detect_role_type() = {k_role}  (expect: CONSULTING)")
    print(f"  {'PASS' if k_role == 'CONSULTING' else 'FAIL'}")

    print("\nFull outputs in proof_paramount.txt and proof_kyndryl.txt")


asyncio.run(main())
