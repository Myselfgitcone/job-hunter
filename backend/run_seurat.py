"""Real pipeline run: Seurat Data Engineer JD."""
import asyncio, sys, io, contextlib, os, re
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JD = """About Seurat
Seurat is transforming manufacturing for people and our planet by delivering a scalable additive manufacturing solution.

Position Overview
Seurat is looking for an experienced Data Engineer to own and expand the upstream data foundation behind our process engineering work. The role covers ingestion, cleaning, organization, governance, and access. You will design and operate the pipelines and storage that turn raw output from numerous materials studies, machine qualification trials, application development runs, and customer builds into reliable, well-organized data that engineers, scientists, and downstream analysis or AI/ML systems can rely on.

Key Responsibilities
Build and operate the pipelines that pull in high-volume process data from Seurat's print systems and adjacent equipment.
Integrate data from heterogeneous sources, including telemetry streams, in-situ process monitoring (optical, thermal, imaging), build job metadata, powder lot and material records, and post-build inspection such as metrology, microscopy, and mechanical tests.
Efficiently store and retrieve large binary artifacts such as images, layer-wise scans, and sensor traces, alongside more structured data.
Add validation, deduplication, and normalization so that downstream consumers do not have to keep rediscovering the same data quality issues.
Define and maintain schemas across data sources whose formats change as the hardware and process evolve.
Work with hardware, process, and software engineers to address data quality problems at the source.
Design and run Seurat's data lakehouse, including partitioning strategies, file formats such as Parquet, HDF5, and Zarr, schema enforcement, retention, and cost management.
Build catalog and lineage tooling so that engineers can find and understand the data they need without relying on tribal knowledge.
Provide well-documented access patterns, including query interfaces, APIs, and notebooks.
Manage access control, governance, and auditing sensitive or proprietary data.
Build internal tooling that lowers the cost of common data tasks, including extraction, joining, exploration, and sharing.
Instrument pipelines for observability and respond to failures and data quality regressions.
Establish testing patterns appropriate to data systems, including contract tests, data quality checks, lineage verification, and backfills.

Qualifications
Bachelor's degree in Computer Science, Data Engineering, or a related technical field.
3+ years of professional experience as a Data Engineer.
Strong Python and SQL (PostgreSQL).
Experience with time-series databases such as TimescaleDB, streaming systems such as Kafka or Kinesis, and observation and reporting systems such as Grafana.
Experience designing and operating production data pipelines, for example Airflow, Dagster, Prefect, or similar.
Hands-on experience with cloud data infrastructure, including object storage (S3 or equivalent) and at least one major data warehouse or lakehouse such as Snowflake, Databricks, BigQuery, or Redshift.
A solid grasp of file formats and storage trade-offs across formats like Parquet, Avro, JSON, and HDF5.
Practical experience with data quality, schema evolution, and pipeline observability.
Experience supporting AI/ML workflows as a data engineer, including feature stores, training data management, dataset versioning, and labeling pipelines.

Nice to Haves
Experience with manufacturing or industrial data, such as high-frequency sensor telemetry.
Experience handling large scientific or image-heavy datasets, including CT scans, layer-wise build imagery, melt pool monitoring, thermography, and metrology."""


async def main():
    from resume_lint import detect_role_type, lint_resume, extract_jd_hard_skills, extract_jd_keywords_dynamic, skill_coverage_report
    from ai.tailor import tailor_resume

    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    api_key, provider, model = env['AI_API_KEY'], env['AI_PROVIDER'], env['AI_MODEL']

    print(f"Provider: {provider}  Model: {model}\n")

    role_type = detect_role_type(JD)
    print(f"[STEP 1] detect_role_type() = {role_type}")

    jd_skills = extract_jd_hard_skills(JD, role_type)
    print(f"\n[STEP 2] extract_jd_hard_skills() ({len(jd_skills)} skills):")
    print("  " + ", ".join(jd_skills))

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

    with open('seurat_out.txt', 'w', encoding='utf-8') as f:
        f.write(f"=== LOG ===\n{log}\n\n=== RESUME ===\n{result}\n")

    print("\n[STEP 4] Pipeline log:")
    for line in log.splitlines():
        if line.strip(): print(f"  {line}")

    print("\n[STEP 5] FINAL TAILORED RESUME:")
    print("-"*60)
    print(result)
    print("-"*60)

    dyn = extract_jd_keywords_dynamic(JD)
    print(f"\n[STEP 6] Dynamic keywords ({len(dyn)}): {', '.join(dyn)}")

    cov = skill_coverage_report(result, JD, role_type=role_type)
    print(f"\n[STEP 7] Coverage: {cov['coverage_text']} ({cov['coverage_ratio']:.0%})")
    print(f"  Covered: {', '.join(sorted(cov['covered']))}")
    print(f"  Missing: {', '.join(sorted(cov['missing'])) if cov['missing'] else 'none'}")

    lint_issues = lint_resume(result, JD)
    print(f"\n[STEP 8] Lint: {len(lint_issues)} issue(s)")
    for i in lint_issues: print(f"  * {i}")

    print("\n[STEP 9] Pin-by-pin — all JD keywords vs resume:")
    lines = result.splitlines()
    for kw in sorted(jd_skills):
        hits = [(i+1, l.strip()) for i, l in enumerate(lines)
                if re.search(r'\b' + re.escape(kw) + r'\b', l, re.IGNORECASE) and l.strip()]
        if hits:
            print(f"  FOUND  [{kw}] — {len(hits)} location(s)")
            for ln, t in hits[:2]: print(f"         line {ln}: {t[:100]}")
        else:
            print(f"  ABSENT [{kw}]")

asyncio.run(main())
