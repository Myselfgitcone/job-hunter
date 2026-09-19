"""Run ONE real tailor and check the six review items. Costs one tailoring run.

    set TAILOR_KEY=<api key>          (never stored, never printed)
    set TAILOR_PROVIDER=anthropic     (anthropic | openai | google | openrouter)
    set TAILOR_MODEL=<model id>       (optional)
    python tools/live_tailor_check.py path/to/base_resume.txt path/to/jd.txt

Writes live_tailor_out.txt and live_tailor_review.json next to the JD file.
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai import tailor as t  # noqa: E402

DEFAULT_MODEL = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4.1", "google": "gemini-2.5-pro",
                 "openrouter": "anthropic/claude-sonnet-4-6"}
# The app runs analyze + every fix-up pass on a cheap model (Settings ->
# ai_model_secondary, default Haiku); the check must do the same or its cost
# and behaviour are not the app's. Override with TAILOR_MODEL_CHEAP.
DEFAULT_CHEAP = {"anthropic": "claude-haiku-4-5", "openai": "gpt-4o-mini", "google": "gemini-2.5-flash",
                 "openrouter": "anthropic/claude-haiku-4.5"}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    key = os.environ.get("TAILOR_KEY", "")
    if not key:
        print("TAILOR_KEY is not set")
        return 2
    provider = os.environ.get("TAILOR_PROVIDER", "anthropic")
    model = os.environ.get("TAILOR_MODEL") or DEFAULT_MODEL.get(provider, DEFAULT_MODEL["openrouter"])
    cheap = os.environ.get("TAILOR_MODEL_CHEAP") or DEFAULT_CHEAP.get(provider, DEFAULT_CHEAP["openrouter"])
    base = open(sys.argv[1], encoding="utf-8").read()
    jd = open(sys.argv[2], encoding="utf-8").read()
    out_dir = os.path.dirname(os.path.abspath(sys.argv[2]))
    # TAILOR_TAG names the output files so two prompts on one JD do not overwrite
    tag = os.environ.get("TAILOR_TAG", "")
    tag = f".{tag}" if tag else ""

    from ai.tailor_slim import tailor_resume_routed          # slim by default; TAILOR_PIPELINE=full for the old one
    tailored, review = asyncio.run(tailor_resume_routed(base, jd, key, provider, model, secondary_model=cheap))
    open(os.path.join(out_dir, f"live_tailor_out{tag}.txt"), "w", encoding="utf-8").write(tailored)
    open(os.path.join(out_dir, f"live_tailor_review{tag}.json"), "w", encoding="utf-8").write(
        json.dumps(review, indent=1, default=str))
    print(f"pipeline={os.environ.get('TAILOR_PIPELINE', 'mirror')} main={model} cheap={cheap}")

    ctx = review.get("context") or {}
    scores = review.get("scores") or {}
    lines = tailored.split("\n")
    jobs = t._job_bullet_lines(tailored)
    head_title = lines[0].split("—", 1)[1].strip() if "—" in lines[0] else lines[0]
    gen = set()
    for n in review.get("notes", []):
        for m in re.finditer(r"new bullet[^:]*:\s*(.+)$", n):
            gen.add(m.group(1).strip())
    present = [str(p) for p in (ctx.get("present") or [])]

    results = []
    results.append(("1 header keeps the JD title", head_title == (ctx.get("job_title") or "").strip(),
                    f"header={head_title!r} jd_title={ctx.get('job_title')!r}"))
    results.append(("2 job 1 <= 12 bullets (cap 11 + one coverage slot)", bool(jobs) and len(jobs[0][1]) <= t._job_cap(0) + 1, f"per job {[len(b) for _, b in jobs]}"))
    bad = [lines[i].lstrip()[1:].strip()[:60] for _, bl in jobs for i in bl
           if t._CLICHE_RE.match(lines[i].lstrip()[1:].strip())]
    weak = [lines[i].lstrip()[1:].strip()[:60] for j, bl in jobs for n, i in enumerate(bl)
            if n < t._impact_slots(j) and t._WEAK_VERB_RE.match(lines[i].lstrip()[1:].strip())]
    results.append(("3 no filler openers; no weak verb in an impact slot", not bad and not weak,
                    f"filler={bad[:3]} weak_in_impact_slot={weak[:3]}"))
    gen_fail, gen_seen = [], 0
    base_nums = t._num_tokens(base)
    for _, bl in jobs:
        blob = "\n".join(lines[i].lstrip()[1:].strip() for i in bl)
        job_tools = t._line_skills(blob, present)
        for i in bl:
            body = lines[i].lstrip()[1:].strip()
            if body not in gen:
                continue
            gen_seen += 1
            # a generated bullet may carry no figure the base resume lacks, and
            # must anchor to a tool the job already uses
            invented = t._num_tokens(body) - base_nums
            ok = not invented and ((not job_tools) or any(tl.lower() in body.lower() for tl in job_tools))
            if not ok:
                gen_fail.append(body[:60])
    results.append(("4 generated bullets: no invented figure + a job tool", not gen_fail,
                    f"generated={gen_seen} failing={gen_fail[:3]}"))
    ga = t._ga_years(ctx)
    ga_fail = []
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    for j, h in enumerate(hdr):
        ey = t._job_end_year(lines[h])
        if not ey:
            continue
        blob = "\n".join(lines[h + 1:t._job_block_end(lines, h)]).lower()
        ga_fail += [(j + 1, tool, y) for tool, y in ga.items()
                    if y > ey and re.search(rf"(?<![a-z0-9]){re.escape(tool)}(?![a-z0-9])", blob)]
    results.append(("5 no tool before its release year", not ga_fail, f"tool_facts={len(t._tool_facts(ctx))} failing={ga_fail[:3]}"))
    overall = scores.get("overall")
    results.append(("6 score 75-88", overall is not None and 75 <= overall <= 88, f"overall={overall} points={scores.get('points')}"))

    print("\n=== LIVE TAILOR CHECK ===")
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    print(f"\nneeds_review={review.get('needs_review')} reasons={review.get('reasons')}")
    print(f"cost={(review.get('usage') or {}).get('cost')}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
