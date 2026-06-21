import sys; sys.path.insert(0, '.')
from ai.tailor import _enforce_job_integrity

base = open('resume_raw.txt', encoding='utf-8').read()

# Inject 3 simultaneous header mutations on real companies
fake = base
fake = fake.replace(
    'Senior Data Engineer @ Cargill | Minneapolis, MN  Sep 2023',
    'Senior Data Architect @ Cargill | Minneapolis, MN  Sep 2023',
)
fake = fake.replace(
    'Data Engineer @ Molina Healthcare | Long Beach, CA  Jan 2021',
    'Data Engineer @ Molina Healthcare | San Francisco, CA  Jan 2021',
)
fake = fake.replace(
    'Data Engineer @ JPMorgan Chase | New York, NY  Dec 2018',
    'Data Engineer @ JPMorgan Chase | New York, NY  Jan 2016',
)

result, removed, reinserted = _enforce_job_integrity(fake, base)

print('Removed:', removed)
print('Reinserted:', reinserted)
print()

checks = [
    ('PASS if title reverted',    'Senior Data Engineer @ Cargill',         True),
    ('PASS if bad title gone',    'Senior Data Architect @ Cargill',         False),
    ('PASS if location reverted', 'Molina Healthcare | Long Beach, CA',      True),
    ('PASS if bad location gone', 'San Francisco, CA',                       False),
    ('PASS if date reverted',     'JPMorgan Chase | New York, NY  Dec 2018', True),
    ('PASS if bad date gone',     'Jan 2016',                                False),
]

all_pass = True
for label, needle, expect_present in checks:
    found = needle in result
    ok = found == expect_present
    all_pass = all_pass and ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {needle!r}")

print()
print('ALL PASS' if all_pass else 'FAILURES FOUND')
