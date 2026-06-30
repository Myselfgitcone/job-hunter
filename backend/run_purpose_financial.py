"""
Real pipeline run: Purpose Financial Data Architect JD.
"""
import asyncio, sys, io, contextlib, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

PURPOSE_JD = """Purpose Financial is seeking a skilled Data Architect to support data architecture initiatives across cloud environments. Data Architect will play a role in designing, implementing, and optimizing our data infrastructure, systems and solutions to support business objectives and technical requirements.

Job Responsibility:
Design, implement, and optimize data models, databases, data warehouses, and data lakes to support data storage, retrieval, and analysis needs.
Support strategic vision and roadmap for data architecture, in alignment with the company's overall objectives and goals.
Define data architecture standards, best practices, and patterns to ensure the integrity, reliability, and scalability of our data assets.
Collaborate with cross-function teams, including software engineering, data science, and business domains to align data architecture initiatives with business requirements and technical objectives.
Architect and implement data integration solutions, ETL pipelines, and data governance frameworks to ensure the accuracy, consistency, and security of data across all systems and processes.
Design and implement master data management (MDM) strategies, data quality management processes, and metadata management solutions to enable data governance and compliance.
Evaluate and recommend data technologies, tools, and platforms to optimize performance, cost, and scalability.
Build a strong partnership with data engineering to ensure proper alignment fostering a culture of innovation, collaboration, and continuous learning.
Experience with NoSQL, Kafka, Middleware, and cloud-based platforms (e.g., AWS, Snowflake).
Technical knowledge in data quality standards, governance, and design.
Certifications (e.g., Certified Solutions Architect) are highly desirable."""


async def main():
    from resume_lint import detect_role_type, lint_resume, extract_jd_hard_skills, extract_jd_keywords_dynamic
    from ai.tailor import tailor_resume

    # Load key from env_run file
    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    api_key = env['AI_API_KEY']
    provider = env['AI_PROVIDER']
    model = env['AI_MODEL']

    print(f"Provider: {provider}  Model: {model}")
    print(f"Base resume: {len(BASE_RESUME)} chars")
    print()

    # Step 1: role type
    role_type = detect_role_type(PURPOSE_JD)
    print(f"[STEP 1] detect_role_type() = {role_type}")
    print()

    # Step 2: JD hard skills (new dynamic extractor)
    jd_skills = extract_jd_hard_skills(PURPOSE_JD, role_type)
    print(f"[STEP 2] extract_jd_hard_skills() ({len(jd_skills)} skills):")
    print("  " + ", ".join(jd_skills))
    print()

    # Step 3: run tailor_resume() capturing all stdout
    print("[STEP 3] Running tailor_resume()...")
    print()
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = await tailor_resume(
            base_resume=BASE_RESUME,
            job_description=PURPOSE_JD,
            api_key=api_key,
            provider=provider,
            model=model,
            profile_skills=None,
            secondary_model="google/gemini-2.5-flash",
        )
    log_output = capture.getvalue()

    # Save immediately before any further processing
    with open('purpose_financial_out.txt', 'w', encoding='utf-8') as f:
        f.write(f"=== PIPELINE LOG ===\n{log_output}\n\n=== FINAL RESUME ===\n{result}\n")

    # Step 4: print all pipeline log
    print("[STEP 4] Pipeline log output:")
    for line in log_output.splitlines():
        print(f"  {line}")
    print()

    # Step 5: final resume
    print("[STEP 5] FINAL TAILORED RESUME:")
    print("-" * 60)
    print(result)
    print("-" * 60)
    print()

    # Step 6: dynamic keyword extraction on JD
    print("[STEP 6] extract_jd_keywords_dynamic() on Purpose Financial JD:")
    dyn_keywords = extract_jd_keywords_dynamic(PURPOSE_JD)
    print(f"  {len(dyn_keywords)} keywords: {', '.join(dyn_keywords)}")
    print()

    # Step 7: skill coverage report
    from resume_lint import skill_coverage_report
    cov = skill_coverage_report(result, PURPOSE_JD, role_type=role_type, profile_skills=None)
    print("[STEP 7] skill_coverage_report():")
    print(f"  Coverage: {cov.get('coverage_text', 'n/a')}  ({cov.get('coverage_ratio', 0):.0%})")
    covered = cov.get('covered', [])
    missing = cov.get('missing', [])
    print(f"  Covered ({len(covered)}): {', '.join(sorted(covered))}")
    print(f"  Missing ({len(missing)}): {', '.join(sorted(missing)) if missing else 'none'}")
    print()

    # Step 8: lint
    lint_issues = lint_resume(result, PURPOSE_JD)
    print(f"[STEP 8] lint_resume(): {len(lint_issues)} issue(s)")
    for iss in lint_issues:
        print(f"  * {iss}")
    print()

    # Step 9: check 5 specific phrases
    print("[STEP 9] Checking 5 specific phrases in final resume:")
    phrases = ["ETL", "Data Warehouse", "Data Architecture", "Data Lineage", "Data Integration"]
    result_lower = result.lower()
    for phrase in phrases:
        if phrase.lower() in result_lower:
            # Find which line(s)
            lines = result.splitlines()
            hits = [(i+1, line.strip()) for i, line in enumerate(lines) if phrase.lower() in line.lower()]
            print(f"  YES '{phrase}' — found in {len(hits)} line(s):")
            for lineno, text in hits[:3]:
                print(f"      line {lineno}: {text[:100]}")
        else:
            print(f"  NO  '{phrase}' — NOT FOUND in resume")
    print()

    print("Full output already saved to purpose_financial_out.txt")


asyncio.run(main())
