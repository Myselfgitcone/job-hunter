"""Measure exact token counts for Review, Tier Audit, and Correction passes."""
import sys, re
sys.path.insert(0, '.')

# Approx tokenizer: 1 token ~ 4 chars (OpenAI standard estimate)
def tokens(text): return len(text) // 4

with open('ai/tailor.py', encoding='utf-8') as f:
    src = f.read()

# Extract SYSTEM_PROMPT
sp_start = src.index('SYSTEM_PROMPT = """') + len('SYSTEM_PROMPT = """')
sp_end = src.index('"""', sp_start)
SYSTEM_PROMPT = src[sp_start:sp_end]

# Extract REVIEWER_PROMPT
rp_start = src.index('REVIEWER_PROMPT = """') + len('REVIEWER_PROMPT = """')
rp_end = src.index('"""', rp_start)
REVIEWER_PROMPT = src[rp_start:rp_end]

# Extract TIER_AUDIT_PROMPT
tp_start = src.index('TIER_AUDIT_PROMPT = """') + len('TIER_AUDIT_PROMPT = """')
tp_end = src.index('"""', tp_start)
TIER_AUDIT_PROMPT = src[tp_start:tp_end]

# Load sample data
base_resume = open('resume_raw.txt', encoding='utf-8').read()
tailored_resume = open('trs_out.txt', encoding='utf-8').read()
# Extract just the resume part from trs_out
tailored_resume = tailored_resume[tailored_resume.index('=== RESUME ==='):].replace('=== RESUME ===', '').strip()

jd = """Data Engineer TRS Texas - ETL, Power BI, CI/CD, Databricks, Python, SQL, 
Microsoft Fabric, Snowflake, Spark, Terraform, Azure, Kubernetes, PowerShell"""
skills_missing = ["SFTP", "SOAP", "Data Visualization", "PowerShell"]

# ── REVIEW PASS ──────────────────────────────────────────────────────────────
review_system = REVIEWER_PROMPT
review_user = (
    f"=== JOB DESCRIPTION ===\n{jd}\n\n"
    f"=== CANDIDATE'S DECLARED SKILLS ===\nskills placeholder\n\n"
    f"=== TAILORED RESUME ===\n{tailored_resume}"
)
print("=" * 60)
print("REVIEW PASS")
print(f"  System prompt:  {tokens(review_system):,} tokens  ({len(review_system):,} chars)")
print(f"  User message:   {tokens(review_user):,} tokens  ({len(review_user):,} chars)")
print(f"  Total INPUT:    {tokens(review_system) + tokens(review_user):,} tokens")
print(f"  Expected output:~500 tokens")
print(f"  Cost (Sonnet):  ${(tokens(review_system)+tokens(review_user))*3/1_000_000 + 500*15/1_000_000:.4f}")
print(f"  Cost (Gemini):  ${(tokens(review_system)+tokens(review_user))*0.30/1_000_000 + 500*2.50/1_000_000:.4f}")

# ── TIER AUDIT PASS ──────────────────────────────────────────────────────────
audit_system = TIER_AUDIT_PROMPT
audit_user = (
    f"=== CANDIDATE'S ORIGINAL RESUME ===\n{base_resume}\n\n"
    f"=== SKILLS MISSING FROM ORIGINAL RESUME (to audit) ===\n"
    + "\n".join(f"- {s}" for s in skills_missing) +
    f"\n\n=== FINAL TAILORED RESUME ===\n{tailored_resume}"
)
print()
print("=" * 60)
print("TIER AUDIT PASS")
print(f"  System prompt:  {tokens(audit_system):,} tokens  ({len(audit_system):,} chars)")
print(f"  User message:   {tokens(audit_user):,} tokens  ({len(audit_user):,} chars)")
print(f"  Total INPUT:    {tokens(audit_system) + tokens(audit_user):,} tokens")
print(f"  Expected output:~400 tokens")
print(f"  Cost (Sonnet):  ${(tokens(audit_system)+tokens(audit_user))*3/1_000_000 + 400*15/1_000_000:.4f}")
print(f"  Cost (Gemini):  ${(tokens(audit_system)+tokens(audit_user))*0.30/1_000_000 + 400*2.50/1_000_000:.4f}")

# ── CORRECTION PASS ──────────────────────────────────────────────────────────
correction_user = (
    "The following bullets are fabrications:\n"
    "- SFTP: placed as production bullet at Molina with no basis\n"
    "- SOAP: same bullet\n\n"
    "Remove each. Keep in Skills only. Do not replace.\n\n"
    f"=== ORIGINAL RESUME ===\n{base_resume}\n\n"
    f"=== TAILORED RESUME TO CORRECT ===\n{tailored_resume}"
)
print()
print("=" * 60)
print("CORRECTION PASS")
print(f"  System prompt:  {tokens(SYSTEM_PROMPT):,} tokens  ({len(SYSTEM_PROMPT):,} chars)")
print(f"  User message:   {tokens(correction_user):,} tokens  ({len(correction_user):,} chars)")
print(f"  Total INPUT:    {tokens(SYSTEM_PROMPT) + tokens(correction_user):,} tokens")
print(f"  Expected output:~2500 tokens (full resume)")
print(f"  Cost (Sonnet):  ${(tokens(SYSTEM_PROMPT)+tokens(correction_user))*3/1_000_000 + 2500*15/1_000_000:.4f}")
print(f"  Cost (Gemini):  ${(tokens(SYSTEM_PROMPT)+tokens(correction_user))*0.30/1_000_000 + 2500*2.50/1_000_000:.4f}")

print()
print("=" * 60)
print("SYSTEM PROMPT size:")
print(f"  {len(SYSTEM_PROMPT):,} chars = {tokens(SYSTEM_PROMPT):,} tokens")
print()
print("REVIEWER_PROMPT size:")
print(f"  {len(REVIEWER_PROMPT):,} chars = {tokens(REVIEWER_PROMPT):,} tokens")
print()
print("TIER_AUDIT_PROMPT size:")
print(f"  {len(TIER_AUDIT_PROMPT):,} chars = {tokens(TIER_AUDIT_PROMPT):,} tokens")
