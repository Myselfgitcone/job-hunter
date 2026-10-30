"""Regression gate for the PROTECT pipeline. Run BEFORE every push that touches tailoring.

    set TAILOR_KEY=<api key>            (never stored, never printed)
    python tools/protect_regression.py <base_resume.txt> <folder with one sub-folder per JD, each holding jd.txt>
    python tools/protect_regression.py <base> <folder> --audit-only     (re-check saved outputs, no model call)

What a PASS means here (the base is the product):
  headline is the base's own title · contact line keeps the city · employers unchanged ·
  every base figure kept · no tool the base does not own · no invented figure ·
  bullets inside JOB_MAX / JOB_MIN · 12-32 words, full stop, no hedge or filler ·
  summary 1-3 lines carrying base figures · PROJECTS / EDUCATION / CERTIFICATIONS verbatim ·
  at least COVERAGE_MIN % of the must-haves have a bullet.
Outputs are written next to each jd.txt as protect_out.txt / protect_review.json.
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai import tailor as t  # noqa: E402
from ai import tailor_protect as p  # noqa: E402

COVERAGE_MIN = 70
HEDGE = re.compile(r"transferable to|analogous to|similar to|mirroring|exposure to|familiar with|\(concepts", re.I)
FILLER = re.compile(r"\b(robust|seamless|spearheaded|leveraged|utilized|expertly|cutting-edge|mission-critical|comprehensive)\b", re.I)
YEAR = re.compile(r"^(19|20)\d{2}$")


def _figs(text: str) -> set[str]:
    return {f for f in t._num_tokens(text) if not YEAR.match(f)}


def _verbatim(a: list[str], b: list[str]) -> bool:
    return [x.strip() for x in a if x.strip()] == [x.strip() for x in b if x.strip()]


def audit(tailored: str, base_norm: str, review: dict) -> list[str]:
    fails: list[str] = []
    bh, bsec = p.split_sections(base_norm)
    name, title, contact = p.base_identity(bh, base_norm)
    th, tsec = p.split_sections(tailored)
    lines = tailored.split("\n")
    # header
    allowed = {f"{name} — {title}"}
    halves = [x.strip() for x in re.split(r"\s*\|\s*", title) if x.strip()]
    if len(halves) == 2:
        allowed.add(f"{name} — {halves[1]} | {halves[0]}")      # family-ordered halves are fine
    if not th or th[0] not in allowed:
        fails.append(f"headline changed: {th[0] if th else ''!r}")
    if len(th) < 2 or "St. Louis" not in th[1] and re.search(r"[A-Z][a-z]+, [A-Z]{2}", contact) and not re.search(r"[A-Z][a-z.]+, [A-Z]{2}", th[1]):
        fails.append(f"contact line lost the city: {th[1] if len(th) > 1 else ''!r}")
    # employers + figures
    bco = [c for c, _ in t._job_bodies(base_norm)]
    tco = [c for c, _ in t._job_bodies(tailored)]
    if bco != tco:
        fails.append(f"employers changed: {tco}")
    base_exp = "\n".join(bsec.get("EXPERIENCE", []))
    lost = _figs(base_exp) - _figs(tailored)
    if lost:
        fails.append(f"base figures lost: {sorted(lost)}")
    invented = _figs("\n".join(tsec.get("EXPERIENCE", []) + tsec.get("SUMMARY", []))) - _figs(base_norm)
    if invented:
        fails.append(f"invented figures: {sorted(invented)}")
    gaps = (((review.get("scores") or {}).get("mirror") or {}).get("gaps")) or []
    low = p._norm("\n".join(tsec.get("EXPERIENCE", []) + tsec.get("SKILLS", []) + tsec.get("SUMMARY", [])))
    for g in gaps:
        if re.search(r"(?<![a-z0-9])" + re.escape(p._norm(g)) + r"(?![a-z0-9])", low):
            fails.append(f"gap tool written anyway: {g!r}")
    # bullets
    for j, bl in t._job_bullet_lines(tailored):
        n = len(bl)
        if j < len(p.JOB_MAX) and n > p.JOB_MAX[j]:
            fails.append(f"job {j + 1}: {n} bullets, cap {p.JOB_MAX[j]}")
        if j < len(p.JOB_MIN) and n < p.JOB_MIN[j]:
            fails.append(f"job {j + 1}: {n} bullets, minimum {p.JOB_MIN[j]}")
        for i in bl:
            b = lines[i].lstrip()[1:].strip(); w = len(b.split())
            if not 12 <= w <= 32:
                fails.append(f"job {j + 1}: bullet of {w} words: {b[:50]}")
            if not b.rstrip().endswith((".", "!")):
                fails.append(f"job {j + 1}: no full stop: ...{b[-40:]}")
            if HEDGE.search(b):
                fails.append(f"job {j + 1}: hedge: {b[:50]}")
            if FILLER.search(b):
                fails.append(f"job {j + 1}: filler: {b[:50]}")
    # summary + skills
    summ = [ln for ln in tsec.get("SUMMARY", []) if ln.strip()]
    if not 1 <= len(summ) <= p.SUMMARY_LINES_MAX:
        fails.append(f"summary has {len(summ)} lines")
    if not p.summary_ok(summ, [ln for ln in bsec.get("SUMMARY", []) if ln.strip()]):
        fails.append("summary lost the base figures")
    items = sum(len(t._split_list_items(ln.partition(":")[2])) for ln in tsec.get("SKILLS", []) if ":" in ln)
    base_items = sum(len(t._split_list_items(ln.partition(":")[2])) for ln in bsec.get("SKILLS", []) if ":" in ln)
    if not 15 <= items <= base_items + p.SKILL_ITEMS_SLACK:
        fails.append(f"{items} skills listed (base has {base_items})")
    # verbatim sections
    for name_ in ("PROJECTS", "EDUCATION", "CERTIFICATIONS"):
        if bsec.get(name_) and sorted(x.strip() for x in tsec.get(name_, []) if x.strip()) != sorted(x.strip() for x in bsec[name_] if x.strip()):
            fails.append(f"{name_} not verbatim")
    return fails


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    base_norm = p.normalize_base(open(sys.argv[1], encoding="utf-8").read())
    root = sys.argv[2]
    audit_only = "--audit-only" in sys.argv
    key = os.environ.get("TAILOR_KEY", "")
    if not key and not audit_only:
        print("TAILOR_KEY is not set")
        return 2
    os.environ["TAILOR_PIPELINE"] = "protect"
    total_fail, cost, n = 0, 0.0, 0
    for name in sorted(os.listdir(root)):
        jd_path = os.path.join(root, name, "jd.txt")
        if not os.path.isfile(jd_path):
            continue
        jd = open(jd_path, encoding="utf-8").read()
        out_path = os.path.join(root, name, "protect_out.txt")
        rev_path = os.path.join(root, name, "protect_review.json")
        if not audit_only:
            try:
                tailored, review = asyncio.run(p.tailor_resume_protect(
                    open(sys.argv[1], encoding="utf-8").read(), jd, key, "anthropic",
                    os.environ.get("TAILOR_MODEL", "claude-sonnet-4-6"),
                    secondary_model=os.environ.get("TAILOR_MODEL_CHEAP", "claude-haiku-4-5"), job_title=jd.split("\n", 1)[0].strip()))
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  {name}: run crashed: {exc}")
                total_fail += 1
                continue
            open(out_path, "w", encoding="utf-8").write(tailored)
            open(rev_path, "w", encoding="utf-8").write(json.dumps(review, indent=1, default=str))
        if not os.path.isfile(out_path):
            continue
        tailored = open(out_path, encoding="utf-8").read()
        review = json.load(open(rev_path, encoding="utf-8"))
        mi = (review.get("scores") or {}).get("mirror") or {}
        cost += float((review.get("usage") or {}).get("cost") or 0); n += 1
        fails = audit(tailored, base_norm, review)
        # Low coverage on a posting the candidate does not fit (many gap tools) is the
        # review flag doing its job, not a pipeline failure. It fails the gate only
        # when the posting IS a fit (few gaps) and the writer still left it uncovered.
        if (mi.get("duty_coverage_any_job") or 0) < COVERAGE_MIN and len(mi.get("gaps") or []) <= 3:
            fails.append(f"must-haves covered {mi.get('duty_coverage_any_job')}% on a good-fit posting")
        total_fail += len(fails)
        print(f"{'PASS' if not fails else 'FAIL'}  {name}: must-haves {mi.get('duty_coverage_any_job')}%, owned tools "
              f"{mi.get('tool_bullet_coverage')}%, bullets {mi.get('bullets_per_job')}, gaps {len(mi.get('gaps') or [])}, "
              f"score {(review.get('scores') or {}).get('overall')}, ${float((review.get('usage') or {}).get('cost') or 0):.4f}")
        for f in fails:
            print(f"        - {f}")
    print(f"\n{'ALL PASS' if not total_fail else str(total_fail) + ' FAILURE(S): do not push'}   cost ${cost:.2f}"
          + (f"   avg ${cost / n:.4f}/run" if n else ""))
    return 0 if not total_fail else 1


if __name__ == "__main__":
    sys.exit(main())
