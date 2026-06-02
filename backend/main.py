from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, or_
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import httpx
import json
import re
import uuid
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import init_db, SessionLocal, Job, Setting
from scrapers import run_all_scrapers
from scrapers.jobspy_scraper import fetch as jobspy_fetch
from scrapers.base import exceeds_experience_limit
from ai.ats import score_ats
from ai.tailor import tailor_resume
from ai.fit import analyze_fit
from ai.cover_letter import generate_cover_letter
from pdf_gen import generate_pdf
from docx_gen import generate_docx
from jd_docx_gen import generate_jd_docx
from jd_fetcher import fetch_full_jd

app = FastAPI(title="Job Hunter API")

import os as _os
_CORS_ORIGINS = _os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_scheduler = AsyncIOScheduler()


async def _auto_scrape():
    """Background auto-scrape task — runs on schedule."""
    print("[Scheduler] Auto-scrape starting…")
    try:
        from fastapi.testclient import TestClient  # avoid circular import
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://localhost:8000") as client:
            await client.post("/api/jobs/scrape", timeout=300)
        print("[Scheduler] Auto-scrape complete.")
    except Exception as e:
        print(f"[Scheduler] Auto-scrape failed: {e}")


@app.on_event("startup")
async def startup():
    await init_db()
    # Start auto-scraper scheduler (every 6 hours by default)
    async with SessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == "auto_scrape_cron"))
        row = result.scalar_one_or_none()
        cron_expr = row.value if row and row.value else "0 * * * *"

    _scheduler.add_job(_auto_scrape, CronTrigger.from_crontab(cron_expr), id="auto_scrape", replace_existing=True)
    _scheduler.start()
    print(f"[Scheduler] Auto-scrape scheduled: {cron_expr}")


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    async with SessionLocal() as db:
        result = await db.execute(select(Setting))
        rows = result.scalars().all()
        return {r.key: r.value for r in rows}


class SettingsUpdate(BaseModel):
    resume: Optional[str] = None
    ai_provider: Optional[str] = None      # openrouter / groq / nvidia / anthropic
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    adzuna_app_id: Optional[str] = None
    adzuna_app_key: Optional[str] = None
    jobo_api_key: Optional[str] = None


@app.put("/api/settings")
async def update_settings(body: SettingsUpdate):
    async with SessionLocal() as db:
        for key, val in body.model_dump(exclude_none=True).items():
            existing = await db.get(Setting, key)
            if existing:
                existing.value = val
            else:
                db.add(Setting(key=key, value=val))
        await db.commit()
    return {"ok": True}


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
async def list_jobs(
    status:     Optional[str]  = None,
    source:     Optional[str]  = None,
    remote:     Optional[bool] = None,
    country:    Optional[str]  = None,
    time_range: Optional[str]  = None,   # "24h" | "48h" | None=all
):
    from datetime import timezone, timedelta
    now = datetime.now(timezone.utc)

    async with SessionLocal() as db:
        q = select(Job).order_by(Job.posted_at.desc(), Job.scraped_at.desc())
        if status:
            q = q.where(Job.status == status)
        if source:
            q = q.where(Job.source == source)
        if remote is not None:
            q = q.where(Job.remote == remote)
        if country:
            q = q.where(Job.country == country)
        result = await db.execute(q)
        jobs = result.scalars().all()

    # Time filter in Python — use posted_at when available, fallback to scraped_at
    def parse_dt(s: str):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def effective_dt(j) -> datetime:
        """Use scraped_at (when WE found it) — avoids old posted_at dates from jobspy filtering out fresh scrapes."""
        return parse_dt(j.scraped_at or "") or parse_dt(j.posted_at or "") or now

    if time_range == "24h":
        cutoff = now - timedelta(hours=24)
        jobs = [j for j in jobs if effective_dt(j) >= cutoff]
        jobs = sorted(jobs, key=effective_dt, reverse=True)
    elif time_range == "48h":
        cutoff_new = now - timedelta(hours=24)
        cutoff_old = now - timedelta(hours=48)
        jobs = [j for j in jobs if cutoff_old <= effective_dt(j) < cutoff_new]
        jobs = sorted(jobs, key=effective_dt, reverse=True)
    elif time_range == "7d":
        cutoff = now - timedelta(days=7)
        jobs = [j for j in jobs if effective_dt(j) >= cutoff]
        jobs = sorted(jobs, key=effective_dt, reverse=True)

    return [_job_to_dict(j) for j in jobs]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return _job_to_dict(job)


# ── Live job verification ─────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/verify")
async def verify_job_live(job_id: str):
    """
    HEAD-ping the job URL to check if it still exists.
    Returns: {alive: bool|null, status_code: int|null}
    null = couldn't reach (network error) — don't assume dead.
    """
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        url = job.url

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            try:
                resp = await client.head(url)
            except Exception:
                resp = None

            # Some servers block HEAD — fall back to GET
            if resp is None or resp.status_code == 405:
                resp = await client.get(url)

            code = resp.status_code
            final_url = str(resp.url).lower()

            # Explicit dead signals
            dead_patterns = [
                "job-not-found", "position-closed", "job-closed",
                "no-longer-available", "this-job-is-no-longer",
                "posting-not-found", "req-not-found",
            ]
            url_looks_dead = any(p in final_url for p in dead_patterns)

            alive = (code < 400) and not url_looks_dead
            return {"alive": alive, "status_code": code}

    except Exception as e:
        # Network error — unknown, don't flag as dead
        return {"alive": None, "status_code": None, "error": str(e)[:120]}


class StatusUpdate(BaseModel):
    status: str  # new / applied / skipped / interview


@app.put("/api/jobs/{job_id}/status")
async def set_status(job_id: str, body: StatusUpdate):
    if body.status not in ("new", "applied", "skipped", "interview"):
        raise HTTPException(400, "Invalid status")
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.status = body.status
        if body.status == "applied" and not getattr(job, "applied_at", None):
            job.applied_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        elif body.status != "applied":
            job.applied_at = None  # reset if un-applied
        await db.commit()
    return {"ok": True}


# ── Clear All Jobs ────────────────────────────────────────────────────────────

@app.delete("/api/jobs/all")
async def clear_all_jobs():
    from sqlalchemy import delete as sa_delete
    async with SessionLocal() as db:
        result = await db.execute(sa_delete(Job))
        await db.commit()
        return {"deleted": result.rowcount}


# ── Debug JobSpy ──────────────────────────────────────────────────────────────

@app.get("/api/debug/jobspy")
async def debug_jobspy():
    """Test JobSpy directly — bypasses DB, shows raw counts."""
    jobs = await jobspy_fetch({})
    by_source: dict = {}
    for j in jobs:
        s = j.get("source", "?")
        by_source[s] = by_source.get(s, 0) + 1
    return {"total": len(jobs), "by_source": by_source,
            "sample": [{"title": j["title"], "company": j["company"], "source": j["source"]} for j in jobs[:5]]}


@app.get("/api/debug/google")
async def debug_google():
    """Test Google Jobs with different search terms."""
    import asyncio, traceback
    from concurrent.futures import ThreadPoolExecutor

    def _test(term: str):
        try:
            from jobspy import scrape_jobs
            df = scrape_jobs(
                site_name=["google"],
                google_search_term=term,
                results_wanted=10,
                description_format="markdown",
                verbose=0,
            )
            if df is None or df.empty:
                return {"count": 0, "term": term}
            return {"count": len(df), "term": term,
                    "sample": df[["title","company","location"]].head(3).to_dict("records")}
        except Exception as e:
            return {"count": 0, "term": term, "error": str(e)[:300]}

    loop = asyncio.get_event_loop()
    ex   = ThreadPoolExecutor(max_workers=3)
    r1 = await loop.run_in_executor(ex, _test, "data engineer USA")
    r2 = await loop.run_in_executor(ex, _test, "data engineer")
    r3 = await loop.run_in_executor(ex, _test, "software engineer New York")
    return {"results": [r1, r2, r3]}


# ── Scrape ────────────────────────────────────────────────────────────────────

@app.post("/api/jobs/scrape")
async def scrape_jobs():
    from datetime import timezone, timedelta
    from sqlalchemy import delete as sa_delete

    async with SessionLocal() as db:
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # ── 1. Delete jobs older than 7 days (keep applied/interview forever) ──
    from scrapers.base import CUTOFF_HOURS as _CUTOFF_H
    cutoff_old = (now - timedelta(hours=_CUTOFF_H)).isoformat()
    async with SessionLocal() as db:
        old_jobs_result = await db.execute(
            select(Job).where(
                Job.scraped_at < cutoff_old,
                Job.status.in_(["new", "skipped"]),
            )
        )
        old_jobs = old_jobs_result.scalars().all()
        for j in old_jobs:
            await db.delete(j)
        deleted = len(old_jobs)
        await db.commit()
    if deleted:
        print(f"[Scrape] Deleted {deleted} jobs older than {_CUTOFF_H}h")

    # ── 2. Run scrapers ──
    scraped = await run_all_scrapers(settings)
    new_count = 0


    # Whitelist — USA, India, and Remote (remote jobs at US companies)
    ALLOWED_COUNTRIES = {"USA", "India", "Remote"}
    scraped = [j for j in scraped if j.get("country", "") in ALLOWED_COUNTRIES]

    # Drop jobs with posted_at older than cutoff (stale results from scrapers)
    cutoff_posted = (now - timedelta(hours=_CUTOFF_H)).isoformat()
    def _posted_ok(j: dict) -> bool:
        pa = j.get("posted_at", "")
        if not pa:
            return True  # no date = keep (can't tell age)
        return pa >= cutoff_posted
    scraped = [j for j in scraped if _posted_ok(j)]

    # ── F1/OPT filter: drop jobs requiring citizenship, GC, or clearance ──
    import re as _re
    _VISA_BLOCK = _re.compile(
        r"(us\s*citizen(ship)?|u\.s\.?\s*citizen(ship)?|united\s+states\s+citizen"
        r"|must\s+be\s+(a\s+)?citizen"
        r"|permanent\s+residen(t|ce)|green\s*card"
        r"|no\s+(visa\s+)?sponsorship|unable\s+to\s+sponsor|cannot\s+sponsor"
        r"|not\s+able\s+to\s+sponsor|will\s+not\s+sponsor|does\s+not\s+sponsor"
        r"|sponsorship\s+(is\s+)?(not\s+available|unavailable)"
        r"|top\s*secret|ts/sci|ts\s*clearance|secret\s+clearance"
        r"|security\s+clearance|dod\s+clearance|active\s+clearance"
        r"|with\s+(security\s+)?clearance|clearance\s+required"
        r"|polygraph|public\s+trust|position\s+of\s+public\s+trust"
        r"|must\s+work\s+without\s+(any\s+)?sponsorship)",
        _re.IGNORECASE,
    )

    def _visa_ok(j: dict) -> bool:
        text = (j.get("title", "") + " " + j.get("description", "")).lower()
        return not _VISA_BLOCK.search(text)

    before = len(scraped)
    scraped = [j for j in scraped if _visa_ok(j)]
    print(f"[Visa filter] dropped {before - len(scraped)} ineligible jobs (clearance/citizenship)")

    before = len(scraped)
    scraped = [j for j in scraped if not exceeds_experience_limit(j.get("description", ""))]
    print(f"[Exp filter] dropped {before - len(scraped)} jobs requiring 7+ years experience")

    # ── Hard title filter — final gate before DB ──
    from scrapers.base import is_relevant_title as _is_title_ok
    before = len(scraped)
    scraped = [j for j in scraped if _is_title_ok(j.get("title", ""))]
    print(f"[Title filter] dropped {before - len(scraped)} non-DE titles (kept {len(scraped)} jobs)")

    async with SessionLocal() as db:
        # Load existing (url, title+company fingerprints) to dedup against DB
        existing_result = await db.execute(select(Job.url, Job.title, Job.company))
        existing_rows = existing_result.all()
        existing_urls = {row.url for row in existing_rows if row.url}
        existing_fps  = {
            f"{(row.title or '').lower().strip()}|||{(row.company or '').lower().strip()}"
            for row in existing_rows
        }

        for job_data in scraped:
            url = job_data.get("url", "")
            fp  = f"{(job_data.get('title','') or '').lower().strip()}|||{(job_data.get('company','') or '').lower().strip()}"

            if url and url in existing_urls:
                continue  # exact URL already in DB
            if fp in existing_fps:
                continue  # same title+company already in DB (cross-source dup)

            job = Job(
                id=str(uuid.uuid4()),
                scraped_at=now_iso,
                **job_data,
            )
            db.add(job)
            if url:
                existing_urls.add(url)
            existing_fps.add(fp)
            new_count += 1

        # ── 3. Save last scrape timestamp ──
        setting = await db.get(Setting, "last_scraped_at")
        if setting:
            setting.value = now_iso
        else:
            db.add(Setting(key="last_scraped_at", value=now_iso))

        await db.commit()

    return {
        "new_jobs": new_count,
        "total_scraped": len(scraped),
        "deleted_old": deleted,
        "scraped_at": now_iso,
    }


# ── Fetch Full JD ─────────────────────────────────────────────────────────────

class DescriptionUpdate(BaseModel):
    description: str

@app.put("/api/jobs/{job_id}/description")
async def set_description(job_id: str, body: DescriptionUpdate):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.description = body.description.strip()
        await db.commit()
    return {"ok": True}

@app.post("/api/jobs/{job_id}/fetch-jd")
async def fetch_jd(job_id: str):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        url       = job.url
        existing  = (job.description or "").strip()

    full_desc = await fetch_full_jd(url)

    # If URL fetch failed/useless, keep existing scraped description (better than nothing)
    FAILED = {"[Description not available", "[Could not load"}
    if any(full_desc.startswith(f) for f in FAILED):
        if len(existing) > 100:
            full_desc = existing   # existing Adzuna API snippet is better
        # else leave the error message so user knows to paste manually

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        job.description = full_desc
        await db.commit()

    return {"description": full_desc}


# ── Tailor ────────────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/tailor")
async def tailor_job(job_id: str):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model = settings.get("ai_model", "anthropic/claude-sonnet-4-5")

    if not api_key:
        raise HTTPException(400, "No AI API key set. Add one in Settings.")

    base_resume = settings.get("resume", "")
    jd = job.description

    ats_before = score_ats(base_resume, jd)

    tailored_text = await tailor_resume(base_resume, jd, api_key, provider, model)
    ats_after = score_ats(tailored_text, jd)

    fit = await analyze_fit(base_resume, jd, job.title, job.company, api_key, provider, model)

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        job.tailored_resume = tailored_text
        job.tailored_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        job.ats_score_before = ats_before["score"]
        job.ats_score_after = ats_after["score"]
        job.ats_keywords_matched = json.dumps(ats_after["matched"])
        job.ats_keywords_missing = json.dumps(ats_after["missing"])
        job.fit_analysis = fit["analysis"]
        job.interview_tips = json.dumps(fit["tips"])
        await db.commit()
        job = await db.get(Job, job_id)

    return {
        "ats_before": ats_before,
        "ats_after": ats_after,
        "tailored_resume": tailored_text,
        "fit_analysis": fit["analysis"],
        "interview_tips": fit["tips"],
    }


# ── Cover Letter ─────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/cover-letter")
async def generate_cover_letter_endpoint(job_id: str):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model = settings.get("ai_model", "anthropic/claude-sonnet-4-5")

    if not api_key:
        raise HTTPException(400, "No AI API key set. Add one in Settings.")

    resume = settings.get("resume", "")
    jd = job.description or ""

    letter = await generate_cover_letter(resume, jd, job.title, job.company, api_key, provider, model)

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        job.cover_letter = letter
        await db.commit()

    return {"cover_letter": letter}


class NotesUpdate(BaseModel):
    notes: str


@app.put("/api/jobs/{job_id}/notes")
async def update_notes(job_id: str, body: NotesUpdate):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.notes = body.notes
        await db.commit()
    return {"ok": True}


# ── PDF Download ──────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/resume/pdf")
async def download_pdf(job_id: str):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if not job.tailored_resume:
            raise HTTPException(400, "No tailored resume yet. Click Tailor Resume first.")

    pdf_bytes = generate_pdf(job.tailored_resume, job.title, job.company)
    title_slug = re.sub(r"[^\w]+", "_", job.title or "Senior_Data_Engineer").strip("_")
    filename = f"Jagadish_Reddy_Butukuri_{title_slug}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── DOCX Download ─────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/resume/docx")
async def download_docx(job_id: str):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if not job.tailored_resume:
            raise HTTPException(400, "No tailored resume yet. Click Tailor Resume first.")

    docx_bytes = generate_docx(job.tailored_resume, job.title, job.company)
    title_slug = re.sub(r"[^\w]+", "_", job.title or "Senior_Data_Engineer").strip("_")
    filename = f"Jagadish_Reddy_Butukuri_{title_slug}.docx"

    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Quick Tailor (paste any JD, no job record needed) ────────────────────────

class QuickTailorRequest(BaseModel):
    jd: str
    company: str = "Company"

@app.post("/api/quick-tailor")
async def quick_tailor(body: QuickTailorRequest):
    async with SessionLocal() as db:
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model    = settings.get("ai_model", "anthropic/claude-sonnet-4-5")

    if not api_key:
        raise HTTPException(400, "No AI API key set. Add one in Settings.")

    base_resume = settings.get("resume", "")
    if not base_resume:
        raise HTTPException(400, "No base resume found. Add it in Settings.")

    tailored = await tailor_resume(base_resume, body.jd, api_key, provider, model)
    return {"tailored_resume": tailored}


@app.post("/api/quick-tailor/pdf")
async def quick_tailor_pdf(body: QuickTailorRequest):
    async with SessionLocal() as db:
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model    = settings.get("ai_model", "anthropic/claude-sonnet-4-5")

    if not api_key:
        raise HTTPException(400, "No AI API key set.")

    base_resume = settings.get("resume", "")
    if not base_resume:
        raise HTTPException(400, "No base resume found.")

    tailored = await tailor_resume(base_resume, body.jd, api_key, provider, model)
    pdf_bytes = generate_pdf(tailored, "", body.company)
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="Jagadish_Reddy_Butukuri_Senior_Data_Engineer.pdf"'},
    )


@app.post("/api/quick-tailor/docx")
async def quick_tailor_docx(body: QuickTailorRequest):
    async with SessionLocal() as db:
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model    = settings.get("ai_model", "anthropic/claude-sonnet-4-5")

    if not api_key:
        raise HTTPException(400, "No AI API key set.")

    base_resume = settings.get("resume", "")
    if not base_resume:
        raise HTTPException(400, "No base resume found.")

    tailored = await tailor_resume(base_resume, body.jd, api_key, provider, model)
    docx_bytes = generate_docx(tailored, "", body.company)
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="Jagadish_Reddy_Butukuri_Senior_Data_Engineer.docx"'},
    )


# ── Save Package (create folder + write all files to disk) ───────────────────

SELF_APPLY_DIR = Path(_os.getenv("SAVE_DIR", str(Path.home() / "job-hunter-packages")))

def _save_package(company: str, jd: str, tailored_resume: str, cover_letter: str = "") -> str:
    """Create company folder, write JD.docx + PDF + DOCX + CoverLetter.txt. Return folder path."""
    company_clean = re.sub(r"[^\w\s\-]", "", company).strip()
    folder = SELF_APPLY_DIR / company_clean
    folder.mkdir(parents=True, exist_ok=True)

    # JD as formatted Word document
    jd_docx = generate_jd_docx(jd, company_clean)
    (folder / f"{company_clean}_JD.docx").write_bytes(jd_docx)

    # Resume PDF
    pdf_bytes = generate_pdf(tailored_resume, "", company)
    (folder / "Jagadish_Reddy_Butukuri_Senior_Data_Engineer.pdf").write_bytes(pdf_bytes)

    # Resume DOCX
    docx_bytes = generate_docx(tailored_resume, "", company)
    (folder / "Jagadish_Reddy_Butukuri_Senior_Data_Engineer.docx").write_bytes(docx_bytes)

    # Cover letter (if available)
    if cover_letter and cover_letter.strip():
        slug = re.sub(r"[^\w]+", "_", company).strip("_")
        (folder / f"Jagadish_Reddy_Butukuri_{slug}_CoverLetter.txt").write_text(
            cover_letter, encoding="utf-8"
        )

    return str(folder)


@app.post("/api/jobs/{job_id}/save-package")
async def save_package(job_id: str):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if not job.tailored_resume:
            raise HTTPException(400, "No tailored resume yet. Tailor first.")

    folder = _save_package(job.company, job.description or "", job.tailored_resume, job.cover_letter or "")
    return {"folder": folder, "company": job.company}


class QuickSaveRequest(BaseModel):
    company: str
    jd: str
    tailored_resume: str
    cover_letter: str = ""

@app.post("/api/quick-tailor/save-package")
async def quick_save_package(body: QuickSaveRequest):
    folder = _save_package(body.company, body.jd, body.tailored_resume, body.cover_letter)
    return {"folder": folder, "company": body.company}


# ── Analytics ────────────────────────────────────────────────────────────────

@app.get("/api/analytics")
async def get_analytics():
    from collections import defaultdict
    from datetime import date, timedelta

    async with SessionLocal() as db:
        result = await db.execute(select(Job).order_by(Job.scraped_at.desc()))
        jobs = result.scalars().all()

    total = len(jobs)
    by_status  = defaultdict(int)
    by_country = defaultdict(int)
    by_source  = defaultdict(int)
    by_day     = defaultdict(int)
    applied_by_day   = defaultdict(int)
    tailored_by_day  = defaultdict(int)
    by_month   = defaultdict(lambda: {"scraped": 0, "applied": 0, "tailored": 0})

    applied_jobs  = []
    tailored_jobs = []

    for j in jobs:
        by_status[j.status] += 1
        by_country[getattr(j, "country", "") or "Unknown"] += 1
        by_source[j.source] += 1
        day   = (j.scraped_at or "")[:10]
        month = (j.scraped_at or "")[:7]   # YYYY-MM
        if day:
            by_day[day] += 1
            by_month[month]["scraped"] += 1
        if j.status == "applied":
            if day:
                applied_by_day[day] += 1
                by_month[month]["applied"] += 1
            applied_jobs.append(_job_to_dict(j))
        if j.tailored_resume:
            if day:
                tailored_by_day[day] += 1
                by_month[month]["tailored"] += 1
            tailored_jobs.append(_job_to_dict(j))

    today = date.today()

    # 30-day timeline
    timeline = []
    for i in range(29, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        timeline.append({
            "date": d,
            "label": d[5:],   # MM-DD
            "scraped":  by_day.get(d, 0),
            "applied":  applied_by_day.get(d, 0),
            "tailored": tailored_by_day.get(d, 0),
        })

    # Last 6 months
    monthly = []
    for i in range(5, -1, -1):
        yr  = today.year
        mon = today.month - i
        while mon <= 0:
            mon += 12; yr -= 1
        key = f"{yr}-{mon:02d}"
        label = date(yr, mon, 1).strftime("%b")
        vals  = by_month.get(key, {"scraped": 0, "applied": 0, "tailored": 0})
        monthly.append({"month": label, **vals})

    return {
        "total": total,
        "by_status":  dict(by_status),
        "by_country": sorted(
            [(k, v) for k, v in by_country.items() if k and k not in ("Unknown", "")],
            key=lambda x: -x[1]
        )[:10],
        "by_source":  sorted(by_source.items(),  key=lambda x: -x[1]),
        "timeline":   timeline,
        "monthly":    monthly,
        "applied_jobs":  applied_jobs[:50],
        "tailored_jobs": tailored_jobs[:50],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "country": getattr(job, "country", "") or "",
        "url": job.url,
        "source": job.source,
        "description": job.description,
        "salary": job.salary,
        "remote": job.remote,
        "posted_at": job.posted_at,
        "scraped_at": job.scraped_at,
        "status": job.status,
        "tailored_resume": job.tailored_resume,
        "tailored_at": getattr(job, "tailored_at", None) or "",
        "applied_at":  getattr(job, "applied_at",  None) or "",
        "ats_score_before": job.ats_score_before,
        "ats_score_after": job.ats_score_after,
        "ats_keywords_matched": json.loads(job.ats_keywords_matched) if job.ats_keywords_matched else [],
        "ats_keywords_missing": json.loads(job.ats_keywords_missing) if job.ats_keywords_missing else [],
        "fit_analysis": job.fit_analysis,
        "interview_tips": json.loads(job.interview_tips) if job.interview_tips else [],
        "cover_letter": job.cover_letter or "",
        "notes": job.notes or "",
        "deadline": getattr(job, "deadline", None) or "",
        "interview_date": getattr(job, "interview_date", None) or "",
        "priority": getattr(job, "priority", 0) or 0,
        "qualify_result": json.loads(job.qualify_result) if getattr(job, "qualify_result", None) else None,
    }

# ── Deadline / Interview Date / Priority ─────────────────────────────────────

class DeadlineUpdate(BaseModel):
    deadline: Optional[str] = None        # ISO date "2025-03-15"
    interview_date: Optional[str] = None  # ISO datetime
    priority: Optional[int] = None        # 0/1/2

@app.patch("/api/jobs/{job_id}/meta")
async def update_job_meta(job_id: str, body: DeadlineUpdate):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if body.deadline is not None:
            job.deadline = body.deadline
        if body.interview_date is not None:
            job.interview_date = body.interview_date
        if body.priority is not None:
            job.priority = body.priority
        await db.commit()
    return {"ok": True}


# ── Search endpoint ───────────────────────────────────────────────────────────

@app.get("/api/search")
async def search_jobs(
    q: str = "",
    status: str = "",
    remote: Optional[bool] = None,
    country: str = "",
    source: str = "",
    min_ats: Optional[int] = None,
    has_deadline: Optional[bool] = None,
    priority: Optional[int] = None,
    sort: str = "scraped_at",
    order: str = "desc",
    page: int = 1,
    limit: int = 20,
):
    async with SessionLocal() as db:
        stmt = select(Job)

        filters = []
        if q:
            term = f"%{q}%"
            filters.append(or_(
                Job.title.ilike(term),
                Job.company.ilike(term),
                Job.description.ilike(term),
                Job.location.ilike(term),
            ))
        if status:
            filters.append(Job.status == status)
        if remote is not None:
            filters.append(Job.remote == remote)
        if country:
            filters.append(Job.country == country)
        if source:
            filters.append(Job.source == source)
        if min_ats is not None:
            filters.append(Job.ats_score_after >= min_ats)
        if has_deadline is True:
            filters.append(Job.deadline != None)
            filters.append(Job.deadline != "")
        if priority is not None:
            filters.append(Job.priority == priority)

        if filters:
            stmt = stmt.where(*filters)

        col = {
            "scraped_at": Job.scraped_at,
            "posted_at": Job.posted_at,
            "company": Job.company,
            "title": Job.title,
            "ats": Job.ats_score_after,
            "priority": Job.priority,
            "deadline": Job.deadline,
        }.get(sort, Job.scraped_at)

        stmt = stmt.order_by(col.asc() if order == "asc" else col.desc())

        count_result = await db.execute(stmt)
        total = len(count_result.scalars().all())

        stmt = stmt.offset((page - 1) * limit).limit(limit)
        result = await db.execute(stmt)
        jobs = result.scalars().all()

    return {
        "data": [_job_to_dict(j) for j in jobs],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


# ── Upcoming deadlines / reminders ───────────────────────────────────────────

@app.get("/api/reminders")
async def get_reminders():
    """Return jobs with upcoming deadlines or interview dates within 7 days."""
    from datetime import timezone, timedelta
    now = datetime.now(timezone.utc)
    cutoff = (now + timedelta(days=7)).isoformat()

    async with SessionLocal() as db:
        result = await db.execute(
            select(Job).where(
                Job.status.in_(["applied", "interview"]),
            )
        )
        jobs = result.scalars().all()

    reminders = []
    for j in jobs:
        deadline = j.deadline or ""
        interview = j.interview_date or ""
        if (deadline and deadline <= cutoff) or (interview and interview <= cutoff):
            d = _job_to_dict(j)
            d["days_until_deadline"] = None
            d["days_until_interview"] = None
            if deadline:
                try:
                    dl = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                    d["days_until_deadline"] = (dl - now).days
                except Exception:
                    pass
            if interview:
                try:
                    iv = datetime.fromisoformat(interview.replace("Z", "+00:00"))
                    d["days_until_interview"] = (iv - now).days
                except Exception:
                    pass
            reminders.append(d)

    reminders.sort(key=lambda x: (x.get("deadline") or x.get("interview_date") or ""))
    return reminders


# ── Scheduler control ─────────────────────────────────────────────────────────

class SchedulerConfig(BaseModel):
    cron: str  # e.g. "0 */6 * * *"

@app.get("/api/scheduler/status")
async def scheduler_status():
    jobs = _scheduler.get_jobs()
    return {
        "running": _scheduler.running,
        "jobs": [{"id": j.id, "next_run": str(j.next_run_time)} for j in jobs],
    }

@app.put("/api/scheduler/cron")
async def update_scheduler_cron(body: SchedulerConfig):
    async with SessionLocal() as db:
        setting = await db.get(Setting, "auto_scrape_cron")
        if setting:
            setting.value = body.cron
        else:
            db.add(Setting(key="auto_scrape_cron", value=body.cron))
        await db.commit()

    _scheduler.reschedule_job("auto_scrape", trigger=CronTrigger.from_crontab(body.cron))
    return {"ok": True, "cron": body.cron}

@app.post("/api/scheduler/run-now")
async def run_scraper_now():
    """Trigger scraper immediately outside the schedule."""
    _scheduler.modify_job("auto_scrape", next_run_time=datetime.now())
    return {"ok": True, "message": "Scraper triggered immediately"}



# ── Structured Profile ────────────────────────────────────────────────────────

class ProfileExperience(BaseModel):
    role: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    years: float = 0
    bullets: List[str] = []

class ProfileEducation(BaseModel):
    degree: str = ""
    school: str = ""
    year: str = ""

class ProfileProject(BaseModel):
    name: str = ""
    description: str = ""

class ProfileData(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    experience: List[ProfileExperience] = []
    education: List[ProfileEducation] = []
    projects: List[ProfileProject] = []
    skills: List[str] = []
    certifications: List[str] = []

@app.get("/api/profile")
async def get_profile():
    async with SessionLocal() as db:
        row = await db.get(Setting, "profile")
        if row and row.value:
            return json.loads(row.value)
    return {}

@app.put("/api/profile")
async def save_profile(body: ProfileData):
    async with SessionLocal() as db:
        row = await db.get(Setting, "profile")
        val = json.dumps(body.model_dump())
        if row:
            row.value = val
        else:
            db.add(Setting(key="profile", value=val))
        await db.commit()
    return {"ok": True}


# ── Parse Resume File → structured profile ───────────────────────────────────

@app.post("/api/profile/parse-resume")
async def parse_resume_file(file: UploadFile = File(...)):
    import io

    async with SessionLocal() as db:
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model = settings.get("ai_model", "anthropic/claude-sonnet-4-5")

    if not api_key:
        raise HTTPException(400, "No AI API key set. Add one in Settings first.")

    content = await file.read()
    filename = (file.filename or "").lower()
    text = ""

    if filename.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise HTTPException(500, "pypdf not installed. Run: pip install pypdf")
        except Exception as e:
            raise HTTPException(400, f"Could not read PDF: {e}")
    elif filename.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise HTTPException(400, f"Could not read DOCX: {e}")
    elif filename.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(400, "Unsupported file. Use PDF, DOCX, or TXT.")

    if not text.strip():
        raise HTTPException(400, "No text extracted from file. Try a different format.")

    from ai.llm import chat

    PARSE_SYSTEM = """Extract structured information from this resume. Return ONLY valid JSON, no markdown:
{
  "name": "",
  "email": "",
  "phone": "",
  "location": "",
  "experience": [
    {
      "role": "",
      "company": "",
      "start_date": "Jan 2022",
      "end_date": "Present",
      "years": 2.5,
      "bullets": ["All bullet points exactly as written in resume"]
    }
  ],
  "education": [
    {"degree": "", "school": "", "year": ""}
  ],
  "projects": [
    {"name": "", "description": ""}
  ],
  "skills": ["Python", "SQL"],
  "certifications": ["AWS Solutions Architect"]
}

Rules:
- start_date / end_date: use the exact date format from the resume (e.g. "Sep 2023", "Jan 2021", "Present"). If no date found, use "".
- years: calculate from start_date to end_date as decimal (e.g. 2 years 6 months = 2.5). If dates missing, estimate from context.
- bullets: extract ALL bullet points for each role exactly as written — do not truncate, summarize, or skip any.
- skills: technical only (languages, frameworks, tools, platforms, databases, cloud). No soft skills.
- certifications: only actual certs/licenses. Empty array if none.
- Use "" for missing text fields. Use [] for missing arrays.
- Do NOT invent or paraphrase data not present in the resume."""

    response = await chat(
        system=PARSE_SYSTEM,
        user=f"Resume:\n\n{text[:6000]}",
        api_key=api_key,
        provider=provider,
        model=model,
        max_tokens=2000,
    )

    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    raise HTTPException(500, "AI could not parse resume. Try again or use TXT format.")


# ── Job Qualification ─────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/qualify")
async def qualify_job_endpoint(job_id: str):
    from ai.qualify import qualify_job

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")

        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model = settings.get("ai_model", "anthropic/claude-sonnet-4-5")
    profile_raw = settings.get("profile", "{}")
    try:
        profile = json.loads(profile_raw)
    except Exception:
        profile = {}

    if not api_key:
        raise HTTPException(400, "No AI API key configured in Settings")
    if not profile:
        raise HTTPException(400, "No profile configured. Fill in your profile first.")

    result = await qualify_job(
        profile=profile,
        job_title=job.title,
        job_description=job.description or "",
        company=job.company,
        location=job.location or "",
        api_key=api_key,
        provider=provider,
        model=model,
    )

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        job.qualify_result = json.dumps(result)
        # Auto-set priority based on score
        score = result.get("score", 0)
        if result.get("qualified") and score >= 80:
            job.priority = 2
        elif result.get("qualified") and score >= 60:
            job.priority = 1
        await db.commit()

    return result


@app.post("/api/jobs/qualify-all")
async def qualify_all_jobs(background_tasks: BackgroundTasks):
    """Qualify all unanalyzed jobs in the background."""
    async def _run():
        from ai.qualify import qualify_job

        async with SessionLocal() as db:
            settings_result = await db.execute(select(Setting))
            settings = {r.key: r.value for r in settings_result.scalars().all()}

        api_key = settings.get("ai_api_key", "")
        provider = settings.get("ai_provider", "openrouter")
        model = settings.get("ai_model", "anthropic/claude-sonnet-4-5")
        profile_raw = settings.get("profile", "{}")
        try:
            profile = json.loads(profile_raw)
        except Exception:
            profile = {}

        if not api_key or not profile:
            print("[Qualify] No API key or profile — skipping")
            return

        async with SessionLocal() as db:
            result = await db.execute(
                select(Job).where(Job.qualify_result == None, Job.status == "new")
            )
            jobs = result.scalars().all()

        print(f"[Qualify] Analyzing {len(jobs)} unqualified jobs…")
        qualified = disqualified = 0

        for job in jobs:
            try:
                res = await qualify_job(
                    profile=profile,
                    job_title=job.title,
                    job_description=job.description or "",
                    company=job.company,
                    location=job.location or "",
                    api_key=api_key,
                    provider=provider,
                    model=model,
                )
                async with SessionLocal() as db2:
                    j = await db2.get(Job, job.id)
                    j.qualify_result = json.dumps(res)
                    score = res.get("score", 0)
                    if res.get("qualified") and score >= 80:
                        j.priority = 2
                    elif res.get("qualified") and score >= 60:
                        j.priority = 1
                    await db2.commit()
                if res.get("qualified"):
                    qualified += 1
                else:
                    disqualified += 1
            except Exception as e:
                print(f"[Qualify] Error on {job.id}: {e}")
            await asyncio.sleep(0.3)  # rate limit

        print(f"[Qualify] Done. Qualified={qualified} Disqualified={disqualified}")

    background_tasks.add_task(_run)
    return {"message": "Qualification running in background"}



# ── Clean HTML descriptions ───────────────────────────────────────────────────

@app.post("/api/jobs/clean-descriptions")
async def clean_html_descriptions():
    """Strip raw HTML from all job descriptions in DB. One-time cleanup."""
    from bs4 import BeautifulSoup
    import re

    _HTML_RE = re.compile(r'<[a-zA-Z][^>]*>')

    async with SessionLocal() as db:
        result = await db.execute(select(Job).where(Job.description != None))
        jobs = result.scalars().all()

    cleaned = 0
    async with SessionLocal() as db:
        for job in jobs:
            desc = job.description or ""
            if _HTML_RE.search(desc):
                clean = BeautifulSoup(desc, "lxml").get_text(separator="\n", strip=True)
                # Collapse 3+ newlines → 2
                clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
                j = await db.get(Job, job.id)
                j.description = clean[:10000]
                cleaned += 1
        await db.commit()

    return {"cleaned": cleaned}

