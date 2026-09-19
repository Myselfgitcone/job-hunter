"""Regression gate for the mirror pipeline. Run BEFORE every push that touches tailoring.

    set TAILOR_KEY=<api key>            (never stored, never printed)
    python tools/mirror_regression.py <base_resume.txt> <folder with one sub-folder per JD, each holding jd.txt>
    python tools/mirror_regression.py <base> <folder> --audit-only     (re-check saved outputs, no model call)

Every JD is tailored once; each output is checked in code. Any FAIL means: do not push.
Outputs are written next to each jd.txt as regression_out.txt / regression_review.json.
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai import tailor as t  # noqa: E402
from ai import tailor_mirror as m  # noqa: E402

HEDGE = re.compile(r"transferable to|analogous to|similar to|mirroring|exposure to|\(concepts", re.I)
FILLER = re.compile(r"\b(robust|seamless|spearheaded|leveraged|utilized|expertly|cutting-edge|mission-critical)\b", re.I)
# words that only the hiring company's own pitch / legal text would put in a bullet
PITCH = re.compile(r"cooperative|shared mission|office locations|total[- ]compensation|total reward|"
                   r"regional data boundaries|vpn|public trust|equal opportunity", re.I)


def audit(tailored: str, base: str, jd: str) -> list[str]:
    fails: list[str] = []
    lines = tailored.split("\n")
    jobs = t._job_bullet_lines(tailored)
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    companies = [t._company_key(lines[h]) for h in hdr]
    base_cloud = {}
    for co, body in t._job_bodies(base):
        low = " " + body.lower() + " "
        base_cloud[co] = {c for c, sig in m.CLOUD_SIG.items() if any(x in low for x in sig)}
    seen: list[tuple[int, set]] = []
    for j, bl in jobs:
        n = len(bl)
        if j < len(m.JOB_MAX) and n > m.JOB_MAX[j]:
            fails.append(f"job {j + 1}: {n} bullets, cap {m.JOB_MAX[j]}")
        if j < len(m.JOB_MIN) and n < m.JOB_MIN[j] - 1:
            fails.append(f"job {j + 1}: {n} bullets, minimum {m.JOB_MIN[j]}")
        for i in bl:
            b = lines[i].lstrip()[1:].strip()
            low = " " + b.lower() + " "
            w = len(b.split())
            if w > 42:
                fails.append(f"job {j + 1}: bullet of {w} words: {b[:50]}")
            if w < 12:
                fails.append(f"job {j + 1}: stub of {w} words: {b[:50]}")
            for rx, name in ((HEDGE, "hedge"), (FILLER, "filler"), (PITCH, "hiring-company text")):
                hit = rx.search(b)
                if hit:
                    fails.append(f"job {j + 1}: {name} '{hit.group(0)}': {b[:50]}")
            if any(co and co in low for co in companies):
                fails.append(f"job {j + 1}: bullet names an employer: {b[:60]}")
            # a cloud the base never shows for this job (Job 1 may be swapped to the JD's cloud)
            if j > 0 and companies[j] in base_cloud:
                for c, sig in m.CLOUD_SIG.items():
                    if any(x in low for x in sig) and c not in base_cloud[companies[j]]:
                        fails.append(f"job {j + 1}: names {c}, not this job's cloud: {b[:50]}")
            cw = t._content_words(b)
            for k, other in seen:
                if cw and other and len(cw & other) / len(cw | other) >= 0.6:
                    fails.append(f"job {j + 1}: near-duplicate of a job {k + 1} bullet: {b[:50]}")
                    break
            seen.append((j, cw))
    invented, _, _ = t._number_audit(tailored, base, jd, floor=None)
    if invented:
        fails.append("invented figure(s): " + ", ".join(sorted(set().union(*[f for _, f in invented]))))
    n_sum = len(t._summary_lines(tailored))
    if not 5 <= n_sum <= 8:
        fails.append(f"summary has {n_sum} lines")
    skills = [ln for ln in lines if ln.lstrip().startswith("•") and ":" in ln
              and lines.index(ln) < (hdr[0] if hdr else 0) and lines.index(ln) > max(t._summary_lines(tailored), default=0)]
    if len(skills) > 10:
        fails.append(f"{len(skills)} SKILLS rows")
    base_co = {co for co, _ in t._job_bodies(base)}
    if set(companies) != base_co:
        fails.append(f"employers changed: {sorted(set(companies) ^ base_co)}")
    return fails


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    base = open(sys.argv[1], encoding="utf-8").read()
    root = sys.argv[2]
    audit_only = "--audit-only" in sys.argv
    key = os.environ.get("TAILOR_KEY", "")
    if not key and not audit_only:
        print("TAILOR_KEY is not set")
        return 2
    os.environ["TAILOR_PIPELINE"] = "mirror"
    total_fail, cost = 0, 0.0
    for name in sorted(os.listdir(root)):
        jd_path = os.path.join(root, name, "jd.txt")
        if not os.path.isfile(jd_path):
            continue
        jd = open(jd_path, encoding="utf-8").read()
        out_path = os.path.join(root, name, "regression_out.txt")
        if not audit_only:
            try:
                tailored, review = asyncio.run(m.tailor_resume_mirror(
                    base, jd, key, "anthropic", os.environ.get("TAILOR_MODEL", "claude-sonnet-4-6"),
                    secondary_model=os.environ.get("TAILOR_MODEL_CHEAP", "claude-haiku-4-5")))
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  {name}: run crashed: {exc}")
                total_fail += 1
                continue
            open(out_path, "w", encoding="utf-8").write(tailored)
            open(os.path.join(root, name, "regression_review.json"), "w", encoding="utf-8").write(
                json.dumps(review, indent=1, default=str))
        if not os.path.isfile(out_path):
            continue
        tailored = open(out_path, encoding="utf-8").read()
        review = json.load(open(os.path.join(root, name, "regression_review.json"), encoding="utf-8"))
        mi = (review.get("scores") or {}).get("mirror") or {}
        cost += float((review.get("usage") or {}).get("cost") or 0)
        fails = audit(tailored, base, jd)
        if (mi.get("duty_coverage_any_job") or 0) < 85:
            fails.append(f"JD lines covered {mi.get('duty_coverage_any_job')}%")
        total_fail += len(fails)
        print(f"{'PASS' if not fails else 'FAIL'}  {name}: JD lines {mi.get('duty_coverage_any_job')}%, tools "
              f"{mi.get('tool_bullet_coverage')}%, bullets {mi.get('bullets_per_job')}, "
              f"score {(review.get('scores') or {}).get('overall')}")
        for f in fails:
            print(f"        - {f}")
    print(f"\n{'ALL PASS' if not total_fail else str(total_fail) + ' FAILURE(S): do not push'}   cost ${cost:.2f}")
    return 0 if not total_fail else 1


if __name__ == "__main__":
    sys.exit(main())
