import sys; sys.path.insert(0, '.')
from resume_lint import lint_resume

JD = "Data Engineer - AWS, Spark, Python"

# Base resume WITH no years claim in summary
BASE_NO_YEARS = """Jagadish Reddy Butukuri
(347)-695-1020 | test@example.com

PROFESSIONAL SUMMARY:
• Senior Data Engineer who builds scalable pipelines and cloud-native platforms.
• Deep expertise in Apache Spark, PySpark, and Databricks.

WORK EXPERIENCE:

Senior Data Engineer @ Cargill | Minneapolis, MN          Sep 2023 - Present
• Built cloud ELT pipelines on AWS at 2TB+ daily scale.

EDUCATION:
Master of Science in Information Systems @ Saint Louis University | 2024"""

# Base resume WITH "6+ years" claim
BASE_WITH_YEARS = BASE_NO_YEARS.replace(
    "• Senior Data Engineer who builds scalable pipelines",
    "• Senior Data Engineer with 6+ years building scalable pipelines"
)

# AI output WITH no years claim
AI_NO_YEARS = BASE_NO_YEARS

# AI output inventing "8+ years"
AI_INVENTED_YEARS = BASE_NO_YEARS.replace(
    "• Senior Data Engineer who builds scalable pipelines",
    "• Senior Data Engineer with 8+ years building scalable pipelines"
)

# AI output inflating "6+" to "8+"
AI_INFLATED_YEARS = BASE_WITH_YEARS.replace(
    "Senior Data Engineer with 6+ years",
    "Senior Data Engineer with 8+ years"
)

print("=" * 60)
print("CASE 1: orig=no years, output=no years -> expect SILENT")
print("=" * 60)
issues = lint_resume(AI_NO_YEARS, JD, base_resume=BASE_NO_YEARS)
years_issues = [i for i in issues if 'YEARS' in i]
print(f"Years issues: {len(years_issues)}")
for i in years_issues: print(f"  {i}")
print("PASS" if not years_issues else "FAIL")

print()
print("=" * 60)
print("CASE 2: orig=no years, output=invented '8+ years' -> expect [YEARS FABRICATED]")
print("=" * 60)
issues = lint_resume(AI_INVENTED_YEARS, JD, base_resume=BASE_NO_YEARS)
years_issues = [i for i in issues if 'YEARS' in i]
print(f"Years issues: {len(years_issues)}")
for i in years_issues: print(f"  {i}")
print("PASS" if any('FABRICATED' in i for i in years_issues) else "FAIL")

print()
print("=" * 60)
print("CASE 3: orig='6+ years', output='8+ years' -> expect [YEARS MISMATCH]")
print("=" * 60)
issues = lint_resume(AI_INFLATED_YEARS, JD, base_resume=BASE_WITH_YEARS)
years_issues = [i for i in issues if 'YEARS' in i]
print(f"Years issues: {len(years_issues)}")
for i in years_issues: print(f"  {i}")
print("PASS" if any('MISMATCH' in i for i in years_issues) else "FAIL")
