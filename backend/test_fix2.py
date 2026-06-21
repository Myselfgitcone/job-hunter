import sys; sys.path.insert(0, '.')
from resume_lint import lint_resume

base = open('resume_raw.txt', encoding='utf-8').read()

# Inject: original has "6+ years", simulate AI output inflating to "8+ years"
ai_output = """Jagadish Reddy Butukuri - Senior Data Engineer
(347)-695-1020 | jagadishbutukuri00@gmail.com

PROFESSIONAL SUMMARY:
- Senior Data Engineer with 8+ years designing and operating large-scale ETL pipelines.
- Deep expertise in Apache Spark, PySpark, and Databricks for large-scale pipeline development.
- Implements data quality frameworks across complex multi-source pipeline environments.
- Collaborates with data science teams to integrate models into pipelines.
- Delivers governed data platforms at enterprise scale with HIPAA and GDPR compliance.

WORK EXPERIENCE:

Senior Data Engineer @ Cargill | Minneapolis, MN          Sep 2023 - Present
- Designed cloud-native ELT pipelines on AWS at 2TB+ daily scale.
- Built PySpark ETL frameworks processing structured supply-chain data.
- Created data quality frameworks using Great Expectations.
- Implemented dbt models with freshness SLAs.
- Optimized Spark jobs cutting execution times by 35%.
Technologies Used: Python, PySpark, AWS, Databricks, dbt

Data Engineer @ Molina Healthcare | Long Beach, CA          Jan 2021 - Jul 2022
- Built Azure Data Factory pipelines for member datasets across 12 source systems.
- Enforced HIPAA-compliant security via Azure Key Vault.
Technologies Used: Azure Data Factory, Synapse Analytics, Python

Data Engineer @ JPMorgan Chase | New York, NY          Dec 2018 - Dec 2020
- Built Spark pipelines handling 500M+ daily retail-banking records.
- Wrote SQL and PL/SQL transformations reducing query runtime by 25%.
Technologies Used: Spark, SQL, Python

TECHNICAL SKILLS:
Python, PySpark, SQL, Apache Spark, Databricks

EDUCATION:
Master of Science in Information Systems @ Saint Louis University | 2024"""

# Bullet char is '-' not '•' in the fake resume — won't matter for years check
jd = "Data Engineer - AWS, Spark, Python, SQL"

issues = lint_resume(ai_output, jd, base_resume=base)
years_issues = [i for i in issues if 'YEARS' in i]
print(f"Total issues: {len(issues)}")
print(f"Years mismatch issues: {len(years_issues)}")
for i in years_issues:
    print(f"  {i}")

if years_issues:
    print("\nPASS - years drift caught")
else:
    print("\nFAIL - years drift not caught")
