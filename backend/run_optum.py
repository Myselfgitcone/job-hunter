import asyncio, sys, io, contextlib, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()

BASE_RESUME = open('resume_raw.txt', encoding='utf-8').read()

JD = """Senior Data Engineer – Exadata Platform Engineering - Optum / UnitedHealth Group
Remote, US

Primary Responsibilities:
Administer and maintain Oracle Exadata Database Machine, ZDLRA, and Exadata Cloud environments, including compute nodes, storage cells, operating systems, networking, and supporting platform components.
Manage Exadata infrastructure performance, capacity planning, storage utilization, and growth forecasting.
Configure, monitor, and optimize Exadata-specific infrastructure technologies, including Smart Scan, Storage Indexes, Smart Flash Cache, and IORM.
Administer and support Exadata networking, backup infrastructure, and disaster recovery platform components.
Monitor system health, performance, and availability using Oracle Enterprise Manager (OEM).
Support Exadata deployments, migrations, and platform operations across on-premises, OCI, Exadata Cloud Service (ExaCS), KVM, OCI@Azure, and OCI@AWS environments.
Develop and maintain automation solutions using Ansible, Python, and Shell scripting.
Troubleshoot and resolve complex Exadata platform issues.
Participate in incidents, problems, change, and on-call support processes.

Required Qualifications:
5+ years of hands-on experience administering Oracle Exadata engineered systems in production environments.
5+ years experience supporting Exadata infrastructure, including storage cells, compute nodes, operating systems, and networking.
5+ years experience monitoring and optimizing Exadata environments using Smart Scan, Storage Indexes, Smart Flash Cache, and IORM.
5+ years experience with Exadata capacity planning, storage management, backup infrastructure, and high availability/disaster recovery platforms.
4+ years experience troubleshooting complex Exadata infrastructure issues.
4+ years experience automating administrative processes using Ansible, Python, Shell scripting.
4+ years experience with Incident, Problem, and Change Management processes in enterprise production environments.

Preferred Qualifications:
Experience with ZDLRA administration.
Experience supporting Exadata Cloud Service (ExaCS), OCI, Oracle Database@Azure, or Oracle Database@AWS.
Experience with OEM Administration.
Experience with ServiceNow.
"""

async def main():
    from resume_lint import extract_jd_hard_skills, skill_coverage_report, _dynamic_coverage_pattern
    from ai.tailor import tailor_resume

    with open('.env_run') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line)
    api_key, provider, model = env['AI_API_KEY'], env['AI_PROVIDER'], env['AI_MODEL']

    jd_skills = extract_jd_hard_skills(JD)
    print(f"[JD Keywords] ({len(jd_skills)}): {', '.join(sorted(jd_skills))}")

    base_cov = skill_coverage_report(BASE_RESUME, JD)
    missing_from_base = base_cov.get('missing', [])
    print(f"\n[Base coverage] {base_cov['coverage_text']} ({base_cov['coverage_ratio']:.0%})")
    print(f"[Missing from base] ({len(missing_from_base)}): {', '.join(missing_from_base)}")

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

    # Extract plan block
    plan_m = re.search(r'<plan>(.*?)</plan>', result + log, re.DOTALL)
    if not plan_m:
        # Try from raw output before plan strip
        plan_m = re.search(r'<plan>(.*?)</plan>', cap.getvalue(), re.DOTALL)

    # Re-run to capture raw output with plan
    cap2 = io.StringIO()
    with contextlib.redirect_stdout(cap2):
        from ai.llm import chat
    # Just show what we have from log
    print("\n[GAPS from plan — searching log]")
    for line in log.splitlines():
        if 'GAPS' in line or 'gap' in line.lower() or 'tier' in line.lower():
            print(f"  {line}")

    after_cov = skill_coverage_report(result, JD)
    print(f"\n[After coverage] {after_cov['coverage_text']} ({after_cov['coverage_ratio']:.0%})")
    if after_cov['missing']: print(f"  Still missing: {', '.join(after_cov['missing'])}")

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
        was_missing = kw in missing_from_base
        print(f"  {loc:12} {'[WAS MISSING]' if was_missing else '             '} {kw}")

    print("\n[Final resume]")
    print("-"*60)
    print(result)
    print("-"*60)

    with open('optum_out.txt', 'w', encoding='utf-8') as f:
        f.write(result)
    print("\nSaved → optum_out.txt")

asyncio.run(main())
