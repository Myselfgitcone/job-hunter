import sys; sys.path.insert(0, '.')

JD = """Data Analyst — Kyndryl
Harness expertise in basic statistics, business fundamentals, and communication to uncover valuable insights.
Transform raw data into rigorous visualizations and compelling stories.
Work closely with customers as part of a team — client-facing role.
Dive into vast IT datasets, unravel trends and patterns to revolutionize customers understanding.
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

raw = open('pipeline_out.txt', encoding='utf-8').read()
start = raw.find('JD3_Kyndryl')
end   = raw.find('======================================================================', start + 5)
section = raw[start:end] if end > start else raw[start:]
dashes = []
idx = 0
while True:
    p = section.find('----', idx)
    if p == -1: break
    dashes.append(p)
    idx = p + 4
resume_text = section[dashes[0]+64:dashes[1]].strip() if len(dashes) >= 2 else ""

from main import score_ats
from resume_lint import extract_jd_hard_skills, detect_role_type

role = detect_role_type(JD)
print(f"Role type: {role}")

ats = score_ats(resume_text, JD)
print(f"ATS score: {ats['score']}/100")
print(f"Matched ({len(ats['matched'])}): {', '.join(ats['matched'])}")
print(f"Missing ({len(ats['missing'])}): {', '.join(ats['missing']) if ats['missing'] else 'none'}")

skills = extract_jd_hard_skills(JD, role)
print(f"Hard skills extracted by pipeline: {len(skills)} -> {', '.join(skills)}")
