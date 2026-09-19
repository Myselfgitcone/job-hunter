"""MIRROR tailoring pipeline: every line of the JD becomes a bullet.

Why it exists (2026-09-18): three third-party resumes for this candidate each got
a recruiter interview. Their method is a full mirror of the JD (10-12 bullets in
every job, 9-line summary, JD-named SKILLS rows, three pages). This pipeline does
the same and keeps what those resumes lacked: the base's real figures, concrete
endings, no bullet pasted into two jobs, no filler words, no hedges.

  1. ANALYZE   cheap model, once (same analysis as the other pipelines)
  2. DUTY MAP  code: every responsibility / requirement line of the JD, numbered
  3. WRITE     main model, once, TAILOR_SYSTEM_MIRROR
  4. ADD       main model, only when a D-line still has no bullet: NEW bullets only
  5. GUARD     code only, and only guards that never remove a coverage bullet:
               header, titles, certifications, figures, magnitudes, verb ladder,
               hedges, filler words, endings, cross-job duplicates, SKILLS rows
  6. SCORE     duty coverage + tool coverage + the shared code score

Select with TAILOR_PIPELINE=mirror. ai/tailor_slim.py and ai/tailor.py are untouched.
"""
from __future__ import annotations

import re

from ai import tailor as t
from ai.tailor_mirror_prompt import ADD_DUTY_SYSTEM, TAILOR_SYSTEM_MIRROR
from ai.tailor_slim_guards import clean_skill_rows, core_tools, slim_score, strip_adjacent, trim_vague_endings

MAX_DUTIES = 24
MAX_ADDS = 4              # new bullets the add step may write (JD lines first, then core tools)
BULLET_MAX = 35           # words
JOB_MAX = (14, 12, 11)    # bullets, by recency; Job 4 and older: 5
JOB_MIN = (10, 8, 7)


def _cap(j: int) -> int:
    return JOB_MAX[j] if j < len(JOB_MAX) else 5

# JD lines that are never work to prove: pay, benefits, legal, education, the company pitch
_NOT_DUTY_RE = re.compile(
    r"\$\s?\d|salary|compensation|benefits?\b|bonus|equal opportunity|accommodat|veteran|disabilit|"
    r"\b401|insurance|paid time|pto\b|visa|sponsor|background check|drug|bachelor|master'?s|degree|"
    r"\bphd\b|years? of experience|other duties|we offer|about us|our mission|apply now|cost of living|"
    r"good faith|open-source projects|technical communities|"
    r"performed in the united states|reside in|authorized to work|lived in the u|public trust|clearance|"
    r"foreign (?:locations?|ip)|vpn|work locations?|eastern time|east coast hours|core hours|travel|"
    r"position is remote|right team of people|full years out of|failure to do so|we combine|since (?:19|20)\d\d|clients have|this position|the position|applicants?\b|submitted directly|interview|"
    r"candidates?\b|pay range|full-time employment|consultants|employer|employment|eeo policy|"
    r"track record|you will be involved|we are looking|we know|our .{0,40}team works|need help|learn more", re.I)
_DUTY_HEAD_RE = re.compile(r"^(role and |key |core )?(responsibilit|what you|how will you|you will|you'll|"
                           r"qualification|requirement|what will you|preferred|must have|nice to have|"
                           r"about the role|position overview)", re.I)
# culture lines: who the person is, not work done. One collaboration bullet answers all of them,
# so they are not D-lines (live: seven of them produced seven near-identical "teamwork" bullets)
_SOFT_LINE_RE = re.compile(
    r"mindset|enjoys working|willingness to learn|openness to|respectful|inclusive|values continuous|"
    r"communicate (?:progress|openly|clearly)|proactive approach|comfort(?:able)? working in|"
    r"attention to detail|self[- ]starter|team player|passion(?:ate)? (?:about|for)|curious", re.I)
# the employer describing itself: never work the candidate did
_PITCH_RE = re.compile(
    r"\b(?:cooperatives?|our (?:associations?|mission|team members|customers|culture|values|company)|"
    r"we take pride|great place to work|is based in|offices?\b|local offices|employees\b|headquartered|founded in|"
    r"owned by|total rewards?|click here|we are seeking|is seeking|join our team|rural america|"
    r"for qualifying positions|work-life balance|well-being)", re.I)
_TAIL_HEAD_RE = re.compile(r"^\s*(?:why us|about us|about the company|who we are|benefits|perks|what we offer|"
                           r"compensation|equal (?:employment )?opportunity|eeo)\b", re.I)
_LIST_MARK_RE = re.compile(r"^[\s•\-*·▪●○■\d.)]+")

_HEDGE_RE = re.compile(
    r",?\s*(?:\(?\s*(?:concepts?(?: and integration)?|exposure|familiarity)\s*\)?$|"
    r"(?:applying |using )?(?:principles?|practices|techniques) (?:transferable|analogous|similar) to [^,.;]+|"
    r"(?:analogous|transferable|similar|comparable) to [^,.;]+|mirroring [^,.;]+|"
    r"including potential [^,.;]+)", re.I)
_FILLER_RE = re.compile(
    r"\b(?:robust|seamless(?:ly)?|comprehensive|cutting-edge|mission-critical|extensively|expertly|"
    r"highly|various|diverse|numerous|crucial|stringent|rigorous(?:ly)?)\s+", re.I)


_WORK_RE = re.compile(
    r"\b(?:design|build|develop|maintain|implement|writ|perform|ensur|collaborat|partner|support|optimi[sz]|"
    r"monitor|troubleshoot|document|creat|integrat|analy[sz]|manag|mentor|review|automat|deploy|migrat|test|"
    r"communicat|contribut|participat|improv|updat|enhanc|translat|deliver|defin|establish|resolv|model|"
    r"script|query|querying|tun|scal|secur|govern|validat|transform|ingest|orchestrat|architect|lead|own|"
    r"experience|proficien|knowledge|understanding|familiar|expertise|hands-on|skills?|worked|used)", re.I)
_PITCH_VOICE_RE = re.compile(r"\b(?:we\W?re|we are|we have|we believe|we build|our (?:mission|vision|story|platform|product)|"
                             r"you\W?ll be excited|why you|about the role|location:|full-time|is to improve|mission is)", re.I)


def jd_duties(job_description: str, company: str = "", tools: list | None = None) -> list[str]:
    """Every line of the JD a recruiter would tick off: responsibilities and
    requirements, in JD order. Headers, pay, benefits, legal text, education and
    years-of-experience lines are left out. A long paragraph is split into sentences."""
    out: list[str] = []
    seen: set[str] = set()
    co = re.sub(r"[^a-z0-9 ]", " ", (company or "").lower()).split()
    co_rx = re.compile(r"\b" + re.escape(co[0]) + r"\b", re.I) if co and len(co[0]) >= 3 else None
    tool_low = [str(x).lower() for x in (tools or []) if len(str(x)) >= 2]
    for raw in (job_description or "").splitlines():
        if _TAIL_HEAD_RE.match(raw) and len(out) >= 3:        # benefits / about-us: the role is over
            break
        s = _LIST_MARK_RE.sub("", raw).strip()
        if not s or _DUTY_HEAD_RE.match(s) and len(s.split()) < 8:
            continue
        parts = [s] if len(s.split()) <= 45 else re.split(r"(?<=[.;])\s+", s)
        for p in parts:
            p = p.strip(" .;")
            n = len(p.split())
            if n < 5 or n > 45 or _NOT_DUTY_RE.search(p) or _SOFT_LINE_RE.search(p) or _PITCH_RE.search(p) or p.endswith("?"):
                continue
            if _PITCH_VOICE_RE.search(p) or (co_rx and co_rx.search(p)):
                continue
            if not _WORK_RE.search(p) and not any(x in p.lower() for x in tool_low):
                continue
            key = " ".join(sorted(t._content_words(p)))
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out[:MAX_DUTIES]


# words every JD line carries; they prove nothing about coverage
_GENERIC_STEMS = {"experienc", "abilit", "ability", "understand", "strong", "work", "includ", "such", "tool",
                  "team", "role", "help", "support", "using", "use", "need", "new", "well", "across", "with",
                  "you\u2019ll", "you'll", "familiarit", "familiarity", "exposure", "solid", "modern", "some",
                  "along", "other", "similar", "related", "within", "while", "their", "that", "our", "key"}


def _duty_stems(duty: str) -> list[str]:
    return [st for st in dict.fromkeys(t._stems(duty)) if st.replace("\\", "") not in _GENERIC_STEMS]


def uncovered_duties(duties: list[str], tailored: str, job: int | None = 0) -> list[int]:
    """Indexes of D-lines no bullet covers. A D-line is covered when ONE bullet
    carries at least a third of its distinctive word stems, or the bullets plus
    the summary together carry half. job=0 checks Job 1 only; None checks every job."""
    lines = tailored.split("\n")
    bullets = [lines[i].lower() for j, bl in t._job_bullet_lines(tailored) for i in bl if job is None or j == job]
    blob = "\n".join(bullets + [lines[i].lower() for i in t._summary_lines(tailored)])
    missing = []
    for n, d in enumerate(duties):
        stems = _duty_stems(d)
        if not stems:
            continue
        hit = lambda text: sum(1 for st in stems if re.search(rf"\b{st}", text)) / len(stems)
        if max((hit(b) for b in bullets), default=0.0) >= 0.34 or hit(blob) >= 0.50:
            continue
        missing.append(n)
    return missing


def strip_hedges(text: str, notes: list) -> str:
    """"principles transferable to Bills of Material", "analogous to ERP/MES",
    "(concepts and integration)": a hedge tells the reader the work was never done."""
    lines, n = text.split("\n"), 0
    for i, ln in enumerate(lines):
        if not ln.lstrip().startswith("•"):
            continue
        new = _HEDGE_RE.sub("", ln)
        if new != ln and len(new.split()) >= 4:
            lines[i] = re.sub(r"\s+([,.])", r"\1", new).rstrip(" ,") + ("." if ln.rstrip().endswith(".") else "")
            n += 1
    if n:
        notes.append(f"hedge guard: removed {n} hedge phrase(s)")
    return "\n".join(lines)


_PLAIN = {"utilized": "used", "utilizing": "using", "utilize": "use", "leveraged": "used",
          "leveraging": "using", "leverage": "use", "spearheaded": "built"}
_PLAIN_RE = re.compile(r"\b(" + "|".join(_PLAIN) + r")\b", re.I)


def _plain(m: re.Match) -> str:
    w = _PLAIN[m.group(1).lower()]
    return w.capitalize() if m.group(1)[0].isupper() else w


def strip_filler(text: str, notes: list) -> str:
    lines, n = text.split("\n"), 0
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        if not s.startswith("•"):
            continue
        new, k = _FILLER_RE.subn("", ln)
        new, k2 = _PLAIN_RE.subn(_plain, new)
        k += k2
        if k:
            body = new.lstrip()[1:].strip()
            lines[i] = ln[: len(ln) - len(s)] + "• " + body[:1].upper() + body[1:]
            n += k
    if n:
        notes.append(f"filler guard: removed {n} filler word(s) (robust, seamless, various…)")
    return "\n".join(lines)


def dedupe_across_jobs(text: str, notes: list, floor: int | None = None) -> str:
    """The same sentence in two jobs is the tell of a generated resume. The copy
    in the OLDER job goes when two bullets share their first five words or 80% of
    their content words; Job 1 is never touched, and no job drops under 5 bullets."""
    lines = text.split("\n")
    jobs = t._job_bullet_lines(text)
    body = lambda i: lines[i].lstrip()[1:].strip()
    kept: list[tuple[str, set]] = []
    drop: set[int] = set()
    for j, bl in jobs:
        live = len(bl)
        for i in bl:
            b = body(i)
            head = " ".join(re.findall(r"[a-z0-9]+", b.lower())[:5])
            cw = t._content_words(b)
            dup = j > 0 and any(head == h or (cw and c and len(cw & c) / len(cw | c) >= 0.8) for h, c in kept)
            keep = floor if floor is not None else (JOB_MIN[j] - 1 if j < len(JOB_MIN) else 3)
            if dup and live > keep:
                drop.add(i)
                live -= 1
            else:
                kept.append((head, cw))
    if drop:
        notes.append(f"cross-job guard: removed {len(drop)} bullet(s) repeated from a newer job")
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def restore_figure_bullets(text: str, base_resume: str, job_description: str, notes: list,
                           restored: list, per_job: int = 2) -> str:
    """The base's figures are what a hiring manager asks about. A base bullet that
    carries a figure and has no descendant in the tailored resume returns to its own
    job, as the base wrote it, when the job is under its cap and the bullet is at most
    38 words. It lands fourth, so the JD's lead duties still open the job."""
    _, _, removed = t._number_audit(text, base_resume, job_description, floor=None)
    if not removed:
        return text
    lines = text.split("\n")
    hdr = {t._company_key(ln): i for i, ln in reversed(list(enumerate(lines))) if t._is_job_header_line(ln)}
    order = [t._company_key(ln) for ln in lines if t._is_job_header_line(ln)]
    back = 0
    for company, body in t._job_bodies(base_resume):
        if company not in hdr:
            continue
        j = order.index(company)
        done = 0
        for bl in body.splitlines():
            b = bl.strip().lstrip("•-* ").strip()
            if done >= per_job or not b or not any(b.startswith(str(r)[:60]) for r in removed):
                continue
            if len(b.split()) > 38:
                continue
            h = hdr[company]
            idx = [i for i in range(h + 1, t._job_block_end(lines, h))
                   if lines[i].lstrip().startswith("•") and not t._TECH_LINE_RE.match(lines[i].strip())]
            if len(idx) >= _cap(j):
                break
            bw = t._content_words(b)
            if any(bw and len(bw & t._content_words(lines[i])) / len(bw | t._content_words(lines[i])) >= 0.45
                   for i in idx):
                continue
            at = idx[3] if len(idx) > 3 else (idx[-1] + 1 if idx else h + 1)
            lines.insert(at, "• " + b)
            hdr = {k: (v + 1 if v >= at else v) for k, v in hdr.items()}
            restored.append(b)
            done += 1
            back += 1
    if back:
        notes.append(f"figure guard: {back} base bullet(s) with a real figure returned to their job")
    return "\n".join(lines)


async def vary_opening_verbs(text: str, base_resume: str, notes: list, **kw) -> str:
    """With 12 bullets in a job the writer repeats "Built" and "Developed". Only the
    repeats are sent, only the opening verb may change, each line is verified by
    _fix_lines (figures, tools, tense), anything else reverts. No call when clean."""
    lines = text.split("\n")
    _, yrs = t._base_years_claim(base_resume or "")
    flags: dict[int, str] = {}
    for _, bl in t._job_bullet_lines(text):
        verbs = [re.match(r"[A-Za-z][A-Za-z-]*", lines[i].lstrip()[1:].strip()) for i in bl]
        used = [v.group(0).lower() for v in verbs if v]
        banned = [v for v, need in t._VERB_TIER.items() if (yrs or 0) < need]
        seen: set[str] = set()
        for i, v in zip(bl, verbs):
            if not v:
                continue
            w = v.group(0).lower()
            if w in seen:
                flags[i] = (f"Start with a different past-tense working verb than '{v.group(0)}' (already used in "
                            f"this job). Do not use any of: {', '.join(dict.fromkeys(used + banned))}. Change "
                            "only the opening verb and the few words needed for grammar; keep everything else.")
            seen.add(w)
    if not flags:
        return text
    return await t._fix_lines(text, flags, notes, "verb_vary", **kw)


def trim_tech_lines(text: str, notes: list) -> str:
    """Technologies Used lists what THIS job's bullets name. A 50-item line that repeats
    the SKILLS section is a generated-resume tell. Left alone when fewer than 6 would remain."""
    lines = text.split("\n")
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    cut = 0
    for h in hdr:
        end = t._job_block_end(lines, h)
        blob = "EXPERIENCE:\nX @ Y | Z\n" + "\n".join(
            lines[i] for i in range(h + 1, end) if lines[i].lstrip().startswith("•"))
        for i in range(h + 1, end):
            m = t._TECH_LINE_RE.match(lines[i].strip())
            if not m:
                continue
            items = [x.strip() for x in t._split_list_items(m.group(2)) if x.strip()]
            gone = set(t._unevidenced(items, blob))
            kept = [x for x in items if x not in gone]
            if gone and len(kept) >= 6:
                lines[i] = "Technologies Used: " + ", ".join(kept)
                cut += len(gone)
    if cut:
        notes.append(f"tech line guard: removed {cut} item(s) no bullet of that job names")
    return "\n".join(lines)


# t._CLOUD_SIG minus " emr" ("EMR integrations with eClinicalWorks" is not Amazon EMR)
CLOUD_SIG = {c: tuple(x for x in sig if x.strip() != "emr") for c, sig in t._CLOUD_SIG.items()}

_GERUND_PAST = {"storing": "Stored", "cutting": "Cut", "routing": "Routed", "enabling": "Enabled", "reducing": "Reduced",
                "improving": "Improved", "giving": "Gave", "supporting": "Supported", "delivering": "Delivered",
                "meeting": "Met", "saving": "Saved", "processing": "Processed", "enforcing": "Enforced",
                "replacing": "Replaced", "feeding": "Fed", "serving": "Served", "holding": "Held", "catching": "Caught",
                "allowing": "Allowed", "ensuring": "Ensured", "adding": "Added", "tracking": "Tracked",
                "loading": "Loaded", "covering": "Covered", "sustaining": "Sustained", "eliminating": "Eliminated",
                "halving": "Halved", "standardizing": "Standardized", "surfacing": "Surfaced", "passing": "Passed",
                "maintaining": "Maintained", "providing": "Provided", "handling": "Handled", "ingesting": "Ingested",
                "orchestrating": "Orchestrated", "normalizing": "Normalized", "validating": "Validated"}


def split_long(text: str, notes: list, max_words: int = 40, min_half: int = 12) -> str:
    """A bullet past `max_words` becomes two at the boundary nearest its middle: ";" or
    ", and / , while" before a past-tense verb, or a gerund clause whose verb is a known one
    ("..., routing hundreds of millions ... while storing fraud-signal data ..."). Both halves keep
    at least `min_half` words (the shared splitter allowed 8 and shipped a 9-word stub). No model;
    every name and figure stays. A bullet with no safe boundary is left alone."""
    lines = text.split("\n")
    idx = {i for _, bl in t._job_bullet_lines(text) for i in bl}
    out, n = [], 0
    for i, ln in enumerate(lines):
        body = ln.lstrip()[1:].strip() if i in idx else ""
        if not body or len(body.split()) <= max_words:
            out.append(ln)
            continue
        cands = []
        for m in re.finditer(r";\s+|,\s+(?:and|while|which|then|plus)\s+", body):
            first = re.match(r"[A-Za-z]+", body[m.end():])
            fw = first.group(0).lower() if first else ""
            if not fw or fw.endswith("ing") or not (fw.endswith("ed") or fw in t._IRREGULAR_PAST):
                continue
            hw, tw = len(body[:m.start()].split()), len(body[m.end():].split())
            if hw >= min_half and tw >= min_half:
                tail = body[m.end():].strip()
                cands.append((abs(hw - tw), m.start(), tail[0].upper() + tail[1:]))
        for m in re.finditer(r"(?:,|\s+while|\s+and)\s+([a-z]+ing)\b", body):
            past = _GERUND_PAST.get(m.group(1).lower())
            hw, tw = len(body[:m.start()].split()), len(body[m.start(1):].split())
            if past and hw >= min_half and tw >= min_half:
                cands.append((abs(hw - tw), m.start(), past + body[m.end(1):].rstrip()))
        if not cands:
            out.append(ln)
            continue
        _, a, tail = min(cands)
        out.append("• " + body[:a].rstrip(" ,;") + ".")
        out.append("• " + tail + ("" if tail.endswith(".") else "."))
        n += 1
    if n:
        notes.append(f"length guard: split {n} bullet(s) over {max_words} words at a clause boundary")
    return "\n".join(out)


def drop_invented_jobs(text: str, base_resume: str, notes: list) -> str:
    """An employer the base resume does not list is removed with its whole block. Regression
    (Citizens): the writer added "Senior Data Analyst @ Sutherland Global Services, 2016 - 2018"
    to reach the JD's years of experience. Employers are verified by background checks; an
    invented one ends the application. Nothing is removed when the base has no readable jobs."""
    real = {co for co, _ in t._job_bodies(base_resume)}
    if not real:
        return text
    lines = text.split("\n")
    drop: set[int] = set()
    gone: list[str] = []
    for h in [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]:
        co = t._company_key(lines[h])
        if co in real or any(co and (co in r or r in co) for r in real):
            continue
        gone.append(lines[h].strip()[:70])
        drop.update(range(h, t._job_block_end(lines, h)))
    if gone:
        notes.append("employer guard: REMOVED job(s) the base resume does not list: " + " | ".join(gone))
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def merge_duplicate_jobs(text: str, notes: list) -> str:
    """Each employer appears once. A second header for the same employer is removed, its bullets
    join the first block, and only the last Technologies Used line of the merged job stays."""
    lines = text.split("\n")
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    seen: dict[str, int] = {}
    drop: set[int] = set()
    for k, h in enumerate(hdr):
        co = t._company_key(lines[h])
        if co not in seen:
            seen[co] = h
            continue
        if k == 0 or t._company_key(lines[hdr[k - 1]]) != co:
            continue                                   # only an adjacent repeat is safely one job
        drop.add(h)
        for i in range(hdr[k - 1] + 1, h):             # the earlier block's tech line and blank lines go
            if t._TECH_LINE_RE.match(lines[i].strip()) or not lines[i].strip():
                drop.add(i)
    if drop:
        notes.append("employer guard: merged an employer the writer listed twice into one job")
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def strip_employer_names(text: str, notes: list) -> str:
    """"At Cargill, optimized..." / "across the Cargill platform": the job header already names
    the employer; inside a bullet it reads as generated."""
    lines = text.split("\n")
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    n = 0
    for h in hdr:
        m = t._JOB_HDR_RE.search(lines[h])
        name = (m.group(1).strip() if m else "")
        if len(name) < 3:
            continue
        rx = re.escape(name)
        for i in range(h + 1, t._job_block_end(lines, h)):
            ln = lines[i]
            if not ln.lstrip().startswith("•") or not re.search(rx, ln, re.I):
                continue
            new = re.sub(rf"^(\s*•\s*)At {rx},\s*(\w)", lambda k: k.group(1) + k.group(2).upper(), ln, flags=re.I)
            new = re.sub(rf"\s+at {rx}\b", "", new, flags=re.I)
            new = re.sub(rf"\b{rx}(?:'s)?\s+", "", new, flags=re.I)
            if new != ln and len(new.split()) >= 10:
                lines[i] = new
                n += 1
    if n:
        notes.append(f"employer guard: removed the employer's name from {n} bullet(s)")
    return "\n".join(lines)


_CLOUD_HOME = {"Azure": "Azure (Synapse Analytics for a warehouse, ADLS Gen2 for object storage, Azure Data Factory "
                        "for ETL, Azure Functions, Event Hubs for streaming, Azure SQL)",
               "AWS": "AWS (Redshift for a warehouse, S3 for object storage, Glue for ETL, Lambda, Kinesis/MSK, RDS)",
               "GCP": "GCP (BigQuery, Cloud Storage, Dataflow, Cloud Functions, Pub/Sub, Cloud SQL)"}


async def keep_older_jobs_on_their_cloud(text: str, base_resume: str, notes: list, **kw) -> str:
    """Job 2 and older ran on the cloud the base shows. A bullet there that names another
    provider's service (Redshift and BigQuery written into an Azure job) is rewritten onto the
    job's own cloud by one verified call; a line that still names it afterwards loses nothing
    else but is reported. The Technologies Used line drops the foreign services in code."""
    lines = text.split("\n")
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    base_cloud = {}
    for co, body in t._job_bodies(base_resume):
        low = " " + body.lower() + " "
        base_cloud[co] = [c for c, sig in CLOUD_SIG.items() if any(x in low for x in sig)]
    flags: dict[int, str] = {}
    for j, h in enumerate(hdr):
        home = base_cloud.get(t._company_key(lines[h]))
        if j == 0 or not home:
            continue
        for i in range(h + 1, t._job_block_end(lines, h)):
            low = " " + lines[i].lower() + " "
            foreign = [c for c, sig in CLOUD_SIG.items() if c not in home and any(x in low for x in sig)]
            if not foreign:
                continue
            tm = t._TECH_LINE_RE.match(lines[i].strip())
            if tm:
                items = [x.strip() for x in t._split_list_items(tm.group(2)) if x.strip()]
                keep = [x for x in items if not any(s_ in " " + x.lower() + " " for c in foreign for s_ in CLOUD_SIG[c])]
                lines[i] = "Technologies Used: " + ", ".join(keep)
            elif lines[i].lstrip().startswith("•"):
                flags[i] = (f"This job ran on {' and '.join(_CLOUD_HOME.get(c, c) for c in home)}. Replace every "
                            f"{' / '.join(foreign)} service with the equivalent on this job's own cloud. "
                            "Change nothing else: same work, same figures, same length.")
    for i in list(flags):
        new = re.sub(r"\s+(?:and|,)\s+(?:AWS|Amazon Web Services|GCP|Google Cloud|Azure)\s+Data Services\b", "", lines[i])
        new = re.sub(r"\b(?:AWS|GCP|Google Cloud|Azure)\s+Data Services\s+and\s+", "", new)
        low = " " + new.lower() + " "
        home = base_cloud.get(next((t._company_key(lines[h]) for h in reversed(hdr) if h < i), "")) or []
        if new != lines[i] and not any(x in low for c, sig in CLOUD_SIG.items() if c not in home for x in sig):
            lines[i] = new
            del flags[i]
    text = "\n".join(lines)
    if not flags:
        return text
    notes.append(f"cloud guard: {len(flags)} bullet(s) in older jobs named another cloud; rewriting onto the job's own")
    return await t._fix_lines(text, flags, notes, "cloud_home", **kw)


def enforce_job_caps(text: str, notes: list, protect: set | None = None) -> str:
    """Past the cap, bullets leave from the end of the job: never one with a figure, never one
    the add step just wrote, unless nothing else is left."""
    lines = text.split("\n")
    drop: set[int] = set()
    for j, bl in t._job_bullet_lines(text):
        extra = len(bl) - _cap(j)
        if extra <= 0:
            continue
        body = lambda i: lines[i].lstrip()[1:].strip()
        plain = [i for i in reversed(bl) if not t._num_tokens(body(i)) and body(i) not in (protect or set())]
        for i in (plain + [i for i in reversed(bl) if i not in plain])[:extra]:
            drop.add(i)
    if drop:
        notes.append(f"cap guard: trimmed {len(drop)} bullet(s) past the per-job cap")
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def merge_skill_rows(text: str, notes: list, max_rows: int = 9) -> str:
    """More than nine SKILLS rows: the two shortest neighbours are merged until nine remain."""
    lines = text.split("\n")
    rows, in_sk = [], False
    for i, ln in enumerate(lines):
        st = ln.strip()
        if t._is_section_hdr(st):
            in_sk = "skill" in st.lower()
            continue
        if in_sk and st.startswith("•") and ":" in st:
            rows.append(i)
    merged = 0
    while len(rows) > max_rows:
        size = lambda i: len(t._split_list_items(lines[i].partition(":")[2]))
        k = min(range(len(rows) - 1), key=lambda n: size(rows[n]) + size(rows[n + 1]))
        a, b = rows[k], rows[k + 1]
        la, _, ra = lines[a].partition(":")
        lb, _, rb = lines[b].partition(":")
        label = la.strip() + " & " + lb.strip().lstrip("• ").strip()
        lines[a] = f"{label}: {ra.strip()}, {rb.strip()}"
        lines[b] = None
        rows.pop(k + 1)
        merged += 1
    if merged:
        notes.append(f"skills guard: merged {merged} row(s) to keep the section at {max_rows}")
    return "\n".join(ln for ln in lines if ln is not None)


def _insert_bullets(text: str, additions: dict[int, list[str]]) -> str:
    lines = text.split("\n")
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    for j in sorted(additions, reverse=True):
        end = t._job_block_end(lines, hdr[j])
        at = next((i for i in range(hdr[j] + 1, end) if t._TECH_LINE_RE.match(lines[i].strip())), end)
        while at > hdr[j] + 1 and not lines[at - 1].strip():
            at -= 1
        lines[at:at] = ["• " + b for b in additions[j]]
    return "\n".join(lines)


_ADD_RE = re.compile(r"^[\s>*`\-•]*(?:N\s*)?(?:JOB\s*)?(\d+)[\s*`]*::\s*D?(\d+)[^:]*::\s*(.+?)[\s*`]*$", re.I)


async def add_duty_bullets(tailored: str, duties: list[str], notes: list, inserted: list,
                           core: list[str] | None = None, _retry: bool = True, **main_kw) -> str:
    duties_in = list(duties)
    need = uncovered_duties(duties, tailored, job=None)
    notes.append(f"duty map: {len(duties) - len(need)}/{len(duties)} JD lines covered by the writer")
    tools = t._unevidenced(list(core or []), tailored)
    notes.append(f"core tools: {len(core or []) - len(tools)}/{len(core or [])} named in a bullet"
                 + (f"; adding: {', '.join(tools)}" if tools else ""))
    short = {j: JOB_MIN[j] - len(bl) for j, bl in t._job_bullet_lines(tailored)
             if j < len(JOB_MIN) and len(bl) < JOB_MIN[j]}
    if not need and not tools and not short:
        return tailored
    need = need[:MAX_ADDS]
    # a core tool is asked for as one more D-line, numbered after the JD's own
    duties = list(duties)
    tool_at: dict[int, str] = {}
    for x in tools[:max(0, MAX_ADDS - len(need))]:
        duties.append(f"Hands-on work with {x} (name {x} in the bullet, as real work on this job's systems)")
        tool_at[len(duties)] = x
        need.append(len(duties) - 1)
    lines = tailored.split("\n")
    hdr = [i for i, ln in enumerate(lines) if t._is_job_header_line(ln)]
    have = [t._content_words(lines[i]) for _, bl in t._job_bullet_lines(tailored) for i in bl]
    jobs = t._job_bullet_lines(tailored)
    shown: list[str] = []
    for j, bl in jobs:
        shown.append(f"\nJOB {j + 1}: {lines[hdr[j]].strip()}")
        shown += [f"  - {lines[i].lstrip()[1:].strip()}" for i in bl]
    full = [str(j + 1) for j, bl in jobs if len(bl) >= _cap(j)]
    prompt = ("RESUME JOBS (read only):\n" + "\n".join(shown)
              + (f"\n\nFULL, add nothing here: JOB {', '.join(full)}. Write for the next job, using ONLY that "
                 "job's own systems, cloud, datasets and teams." if full else "")
              + "\n\nJD LINES WITHOUT A BULLET:\n"
              + ("\n".join(f"D{n + 1}: {duties[n]}" for n in need) or "(none)")
              + "".join(f"\n\nJOB {j + 1} IS SHORT: write {k} more bullet(s) for JOB {j + 1}, each covering one of "
                        f"these JD lines as THAT job's own work (its cloud, systems, datasets, teams), "
                        f"saying nothing its existing bullets already say: "
                        + " | ".join(f"D{n + 1}: {d}" for n, d in list(enumerate(duties))[:8])
                        for j, k in short.items()))
    try:
        raw = await t.chat(ADD_DUTY_SYSTEM, prompt, max_tokens=2000, pass_name="add_duty", **main_kw)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"add duty bullets: skipped ({exc})")
        return tailored
    additions: dict[int, list[str]] = {}
    ok, bad = 0, []
    count = {j: len(bl) for j, bl in jobs}
    companies = [t._company_key(lines[h]) for h in hdr]
    for ln in raw.splitlines():
        m = _ADD_RE.match(ln)
        if not m:
            continue
        j = int(m.group(1)) - 1
        body = re.sub(r"\s*[—–]\s*", ", ", re.sub(r"^[\s•\-*]+", "", m.group(3)).strip())
        first = re.match(r"[A-Za-z][A-Za-z-]*", body)
        why = ""
        if not 0 <= j < len(jobs):
            why = "bad job"
        elif not 14 <= len(body.split()) <= 38:
            why = f"{len(body.split())} words"
        elif t._bad_figures(body):
            why = "carries a figure"
        elif not first or t._verb_form(first.group(0)) != "past-tense":
            why = "not past tense"
        elif int(m.group(2)) in tool_at and t._unevidenced([tool_at[int(m.group(2))]],
                                                           "EXPERIENCE:\nX @ Y | Z\n• " + body):
            why = "does not name the tool"
        elif any(c and len(t._content_words(body) & c) / len(t._content_words(body) | c) >= 0.35 for c in have):
            why = "repeats an existing bullet"
        elif any(co and co in body.lower() for co in companies):
            why = "names an employer"              # "...at Molina Healthcare" written into the Cargill job
        elif ok >= MAX_ADDS + sum(short.values()):
            why = "over the add limit"
        if not why and count[j] >= _cap(j):
            why = f"job {j + 1} is at its cap"
        if not why:
            # never a cloud this job does not use (AWS / S3 written into an Azure job)
            blob = " " + " ".join(lines[i].lower() for i in jobs[j][1]) + " "
            low = " " + body.lower() + " "
            for cloud, sig in CLOUD_SIG.items():
                if any(x in low for x in sig) and not any(x in blob for x in sig):
                    why = f"names {cloud}, which job {j + 1} does not use"
        if why:
            bad.append(f"D{m.group(2)} ({why})")
            continue
        count[j] += 1
        additions.setdefault(j, []).append(body)
        have.append(t._content_words(body))
        inserted.append((j, f"D{m.group(2)}", body))
        ok += 1
    if additions:
        tailored = _insert_bullets(tailored, additions)
    notes.append(f"add duty bullets: {ok} new bullet(s)" + (f"; rejected {len(bad)}: {', '.join(bad)}" if bad else ""))
    if bad and _retry:
        # one more try for what was refused (a bullet with a number, a repeat): the gaps are recomputed
        return await add_duty_bullets(tailored, duties_in, notes, inserted, core=core, _retry=False, **main_kw)
    return tailored


async def tailor_resume_mirror(base_resume: str, job_description: str,
                               api_key: str, provider: str, model: str,
                               profile_skills: list[str] | None = None,
                               secondary_model: str = "",
                               user_job_roles: list[str] | None = None,
                               profile_projects: list[dict] | None = None,
                               company: str = "",
                               keys=None) -> tuple[str, dict]:
    """Same signature and return shape as ai.tailor.tailor_resume."""
    from ai.tailor_slim import fix_figures_only, restore_magnitudes, strip_unowned_certs, _CERT_RE

    notes: list[str] = ["pipeline: mirror"]
    reasons: list[str] = []
    try:
        from ai.llm import reset_usage
        reset_usage()
    except Exception:  # noqa: BLE001
        pass
    try:
        from resume_lint import clean_jd_html
        job_description = clean_jd_html(job_description)
    except Exception:  # noqa: BLE001
        pass
    base_resume = (base_resume or "").strip()
    job_description = (job_description or "").strip()
    if len(base_resume) < 40:
        raise ValueError("Resume text is too short — upload or paste your resume first.")
    if len(job_description) < 40:
        raise ValueError("Job description is too short. Paste the full posting.")

    cheap = secondary_model or model
    main_kw = {"api_key": api_key, "provider": provider, "model": model, "keys": keys}
    cheap_kw = {"api_key": api_key, "provider": provider, "model": cheap, "keys": keys}

    # ── 1. ANALYZE ───────────────────────────────────────────────────────
    context: dict = {}
    for attempt in (1, 2):
        try:
            raw = await t.chat(t.ANALYZE_SYSTEM, t.analyze_prompt(base_resume, job_description),
                               max_tokens=6000, pass_name="analyze" if attempt == 1 else "analyze_retry", **cheap_kw)
            context = t._loads_loose(raw)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"analyze: attempt {attempt} failed ({exc})")
            context = {}
        if t._analysis_ok(context):
            break
    if not t._analysis_ok(context):
        raise ValueError("Could not analyze this job description (the model returned no usable "
                         "analysis twice). Try again in a moment.")
    for k in ("present", "missing", "baseline_missing", "responsibilities"):
        context.setdefault(k, [])
    context.setdefault("target_cloud", "None")
    tc = (context.get("target_cloud") or "").strip()
    if tc in t._CLOUD_TERMS and not any(term in job_description.lower() for term in t._CLOUD_TERMS[tc]):
        context["target_cloud"] = "None"
    for k in ("target_tools", "present", "missing", "bridge_only", "equivalent"):
        context[k] = [x for x in (context.get(k) or [])
                      if not t._is_soft_skill(str(x)) and not _CERT_RE.search(str(x))]
    context["target_tools"] = [x for x in context["target_tools"] if t._phrase_in_jd(str(x), job_description)]

    job_description, cut = t._trim_jd_tail(job_description, context.get("jd_tail_starts"), context["target_tools"])
    if cut:
        notes.append(f"jd trimmed: dropped {cut} chars of pay/benefits/legal tail")

    # ── 2. DUTY MAP ──────────────────────────────────────────────────────
    duties = jd_duties(job_description, company or str(context.get("company") or ""), context["target_tools"])
    notes.append(f"duty map: {len(duties)} JD lines")
    print(f"[TAILOR-MIRROR] target_cloud={context.get('target_cloud')!r} tools={len(context['target_tools'])} "
          f"duties={len(duties)} company={company or context.get('company', '')!r}")

    # ── 3. WRITE ─────────────────────────────────────────────────────────
    hints = t._base_number_hints(base_resume)
    core = core_tools(context, job_description)
    notes.append(f"core tools given to the writer: {', '.join(core) or 'none'}")
    prompt = (
        "ANALYSIS:\n"
        f"  job_title:    {context.get('job_title', '')}\n"
        f"  target_cloud: {context.get('target_cloud', 'None')}\n"
        f"  industry:     {context.get('industry', '')}\n"
        f"  JD tools (every one: a bullet + Technologies Used + SKILLS): "
        f"{', '.join(str(x) for x in context['target_tools']) or '(none)'}\n\n"
        + (f"CORE TOOLS (each NAMED in an experience bullet, by product name): {', '.join(core)}\n\n" if core else "")
        + "DUTY MAP (every D-line gets a Job 1 bullet; the main ones again in Jobs 2 and 3, reworded):\n"
        + "\n".join(f"  D{n + 1}: {d}" for n, d in enumerate(duties)) + "\n\n"
        + (("REAL FIGURES IN THE BASE (each stays, exactly as written, in a bullet of its own job):\n  "
            + "\n  ".join(hints) + "\n\n") if hints else "")
        + (("CANDIDATE'S OWN DECLARED SKILLS:\n  " + ", ".join(profile_skills) + "\n\n") if profile_skills else "")
        + f"JOB DESCRIPTION:\n{job_description}\n\nORIGINAL RESUME:\n{base_resume}\n\n"
        "Write the full mirrored resume now, in the plain-text format.")
    tailored = (await t.chat(TAILOR_SYSTEM_MIRROR, prompt, max_tokens=12000, pass_name="tailor", **main_kw)).strip()
    tailored = t._contact_only(t._clean_header_title(t._ensure_header(t._normalize_format(tailored), base_resume)), base_resume)

    tailored = drop_invented_jobs(tailored, base_resume, notes)
    tailored = merge_duplicate_jobs(tailored, notes)
    tailored = t._dedupe_bullets(tailored, notes)
    tailored = dedupe_across_jobs(tailored, notes, floor=0)

    # ── 4. ADD what the duty map still lacks ─────────────────────────────
    inserted: list = []
    tailored = await add_duty_bullets(tailored, duties, notes, inserted, core=core, **main_kw)

    # ── 5. GUARD (code; nothing here removes a coverage bullet) ──────────
    tailored, junk = t._strip_junk_lines(tailored)
    tailored, tech_added = t._ensure_tech_lines(tailored)
    target = context.get("target_cloud", "None")
    still = t._missing_native_clouds(tailored, base_resume, target)
    if still:
        notes.append("cloud backstop applied: " + ", ".join(f"{c}={cl}" for c, cl in still.items()))
        tailored = t._backstop_native_clouds(tailored, still)
    tailored = t._guard_title_inflation(tailored, base_resume, notes)
    tailored = t._headline_hybrid(tailored, base_resume, context.get("job_title", ""), notes)
    tailored = strip_unowned_certs(tailored, base_resume, notes)
    tailored = strip_employer_names(tailored, notes)
    tailored = strip_hedges(tailored, notes)
    tailored = strip_filler(tailored, notes)
    tailored, intens = t._strip_intensifiers(tailored)
    if intens:
        notes.append(f"intensifier guard: removed {intens} vague intensifier(s)")
    over = [i for _, bl in t._job_bullet_lines(tailored) for i in bl
            if len(tailored.split("\n")[i].split()) - 1 > BULLET_MAX]
    if over:
        tailored = await t._compress_long_bullets(tailored, notes, [str(x) for x in context["target_tools"]],
                                                  max_words=BULLET_MAX, target=BULLET_MAX - 4,
                                                  summary_max=10 ** 6, **main_kw)
    tailored = re.sub(r"\b(\d+)\s?min\b(?!\w)", r"\1-minute", tailored)
    tailored = split_long(tailored, notes)
    tailored = await t._fix_fragment_endings(tailored, job_description, notes, **cheap_kw)
    tailored = trim_vague_endings(tailored, notes)
    tailored = t._dedupe_bullets(tailored, notes)
    tailored = dedupe_across_jobs(tailored, notes)
    tailored, dash = t._strip_dash_asides(tailored)
    tailored, yrs = t._clamp_years(tailored, base_resume)
    if yrs:
        notes.append("years guard: clamped inflated experience claim to base resume")
    tailored = await fix_figures_only(tailored, base_resume, job_description, notes, **cheap_kw)
    restored: list = []
    tailored = restore_figure_bullets(tailored, base_resume, job_description, notes, restored)
    tailored = restore_magnitudes(tailored, base_resume, notes)
    tailored = strip_adjacent(tailored, notes)
    tailored = split_long(tailored, notes)          # again: the figure passes can lengthen a bullet
    tailored = await keep_older_jobs_on_their_cloud(tailored, base_resume, notes, **main_kw)
    tailored = enforce_job_caps(tailored, notes, protect={b for _, _, b in inserted} | set(restored))
    tailored = await vary_opening_verbs(tailored, base_resume, notes, **cheap_kw)
    tailored = t._verb_ladder_guard(tailored, base_resume, context.get("bridge_only") or [], notes)
    _, off_page = t._covered_anywhere([str(x) for x in context["target_tools"] if t._looks_like_tool(str(x))], tailored)
    tailored = t._ensure_skills_row(tailored, off_page, notes)
    tailored = t._dedupe_skill_rows(tailored, notes)
    tailored = clean_skill_rows(tailored, notes)
    tailored = merge_skill_rows(tailored, notes)
    tailored, tidied = t._clean_lists(tailored)
    tailored = trim_tech_lines(tailored, notes)
    tailored = t._strip_empty_sections(tailored).strip()

    # ── 6. SCORE ─────────────────────────────────────────────────────────
    miss_all = uncovered_duties(duties, tailored, job=None)
    miss_j1 = uncovered_duties(duties, tailored, job=0)
    named = [str(x) for x in context["target_tools"] if t._looks_like_tool(str(x))]
    # a product or language is capitalised or short (Neo4j, SQL, dbt); "graph databases" is a concept
    is_product = lambda x: bool(re.search(r"[A-Z0-9+#]", x)) or len(x.split()) == 1
    tools = [x for x in named if is_product(x)]
    concepts_missing = t._unevidenced([x for x in named if not is_product(x)], tailored)
    no_bullet = t._unevidenced(tools, tailored)
    jobs = t._job_bullet_lines(tailored)
    mirror = {
        "duties": len(duties),
        "duty_coverage_any_job": round(100 * (len(duties) - len(miss_all)) / max(1, len(duties))),
        "duty_coverage_job1": round(100 * (len(duties) - len(miss_j1)) / max(1, len(duties))),
        "duties_missing": [duties[n] for n in miss_all],
        "tool_bullet_coverage": round(100 * (len(tools) - len(no_bullet)) / max(1, len(tools))),
        "tools_without_bullet": no_bullet,
        "jd_phrases_not_literal": concepts_missing,
        "bullets_per_job": [len(bl) for _, bl in jobs],
        "summary_lines": len(t._summary_lines(tailored)),
        "words": len(tailored.split()),
    }
    notes.append(f"mirror: duties {mirror['duty_coverage_any_job']}% (Job 1 {mirror['duty_coverage_job1']}%), "
                 f"tools in bullets {mirror['tool_bullet_coverage']}%, bullets {mirror['bullets_per_job']}, "
                 f"{mirror['words']} words")
    scores: dict = {}
    _orph = t._orphan_skills
    base_blob = "EXPERIENCE:\nX @ Y | Z\n• " + base_resume.replace("\n", " ")
    t._orphan_skills = lambda text, keep=None: t._unevidenced(_orph(text, keep=keep), base_blob)
    try:
        scores = slim_score(tailored, base_resume, job_description, context, inserted)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"score skipped ({exc})")
    finally:
        t._orphan_skills = _orph
    scores["mirror"] = mirror
    if mirror["duty_coverage_any_job"] < 90:
        reasons.append("JD lines without a bullet: " + "; ".join(d[:60] for d in mirror["duties_missing"][:3]))
    try:
        from ai.llm import get_run_usage
        usage = get_run_usage()
    except Exception:  # noqa: BLE001
        usage = {"cost": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": []}
    for n in notes:
        print(f"[TAILOR-MIRROR GUARDS] {n[:300]}")
    return tailored, {"needs_review": bool(reasons), "reasons": reasons, "notes": notes,
                      "scores": scores, "context": context, "usage": usage}
