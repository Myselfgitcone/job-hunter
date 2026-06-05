from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, or_, text, func
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import httpx
import json
import re
import uuid
import uuid as _uuid
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load .env file
load_dotenv()
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import init_db, SessionLocal, engine, Job, Setting, User, UserSettings, UserJob, Company
from auth import get_current_user_id, get_optional_user_id, hash_password, verify_password, create_token
from scrapers import run_all_scrapers
from scrapers.jobspy_scraper import fetch as jobspy_fetch
from ai.ats import score_ats
from ai.tailor import tailor_resume
from ai.fit import analyze_fit
from ai.cover_letter import generate_cover_letter
from pdf_gen import generate_pdf
from docx_gen import generate_docx
from jd_docx_gen import generate_jd_docx
from jd_fetcher import fetch_full_jd

app = FastAPI(title="Job Hunter API")

@app.get("/version")
def version():
    return {"version": "5", "cors": "raw-asgi"}

import os as _os
_cors_raw = _os.getenv("CORS_ORIGINS", "")
_CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []
_CORS_ORIGINS += [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://job-hunter-sigma.vercel.app",
]
_CORS_ORIGINS = list(set(_CORS_ORIGINS))

# â”€â”€ Raw ASGI CORS â€” works with file uploads, streaming, and exceptions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_CORS_HEADERS = [
    (b"access-control-allow-origin",  b"*"),
    (b"access-control-allow-methods", b"GET, POST, PUT, DELETE, OPTIONS, PATCH"),
    (b"access-control-allow-headers", b"*"),
    (b"access-control-max-age",        b"86400"),
]

class RawCORSMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Handle OPTIONS preflight immediately â€” no auth, no routing
        if scope.get("method") == "OPTIONS":
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": _CORS_HEADERS,
            })
            await send({"type": "http.response.body", "body": b""})
            return

        # For all other requests â€” inject CORS headers into the response
        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                # Merge existing headers with CORS headers
                existing = dict(message.get("headers", []))
                for k, v in _CORS_HEADERS:
                    existing[k] = v
                message = {**message, "headers": list(existing.items())}
            await send(message)

        await self.app(scope, receive, send_with_cors)

app.add_middleware(RawCORSMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# â”€â”€ Global exception handlers â€” always include CORS headers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from fastapi import Request as _Request
from fastapi.responses import JSONResponse as _JSONResponse
from fastapi.exception_handlers import http_exception_handler as _default_http_handler

@app.exception_handler(Exception)
async def _global_exc_handler(_req: _Request, exc: Exception):
    return _JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"},
    )

@app.exception_handler(HTTPException)
async def _http_exc_handler(_req: _Request, exc: HTTPException):
    return _JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"},
    )

@app.get("/health")
async def health_check():
    """Public health endpoint for Railway/Vercel healthchecks."""
    return {"status": "ok"}


_scheduler = AsyncIOScheduler()


async def _run_scrape() -> dict:
    """Core scrape logic â€” shared by the scheduler and the /api/jobs/scrape endpoint."""
    from datetime import timezone, timedelta

    async with SessionLocal() as db:
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

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

    scraped = await run_all_scrapers(settings)
    ALLOWED_COUNTRIES = {"USA", "India", "Remote"}
    scraped = [j for j in scraped if j.get("country", "") in ALLOWED_COUNTRIES]

    cutoff_posted = (now - timedelta(hours=_CUTOFF_H)).isoformat()
    scraped = [j for j in scraped if not j.get("posted_at") or j["posted_at"] >= cutoff_posted]
    print(f"[Scrape] {len(scraped)} jobs after date/country filter")

    new_count = 0
    new_jobs_for_tg: list[dict] = []
    async with SessionLocal() as db:
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
            if (url and url in existing_urls) or fp in existing_fps:
                continue
            db.add(Job(id=str(uuid.uuid4()), scraped_at=now_iso, **job_data))
            if url:
                existing_urls.add(url)
            existing_fps.add(fp)
            new_count += 1
            new_jobs_for_tg.append(job_data)

        setting = await db.get(Setting, "last_scraped_at")
        if setting:
            setting.value = now_iso
        else:
            db.add(Setting(key="last_scraped_at", value=now_iso))
        await db.commit()

    print(f"[Scrape] Done â€” {new_count} new jobs saved.")

    # Telegram digest
    try:
        import telegram_bot
        await telegram_bot.send_scrape_digest(new_jobs_for_tg)
    except Exception as te:
        print(f"[Scrape] Telegram notify failed: {te}")

    # Auto-qualify new jobs in background (fire-and-forget)
    asyncio.create_task(_run_qualify_all())

    return {"new_jobs": new_count, "total_scraped": len(scraped), "deleted_old": deleted, "scraped_at": now_iso}


async def _auto_scrape():
    """Background auto-scrape task â€” runs on schedule."""
    print("[Scheduler] Auto-scrape startingâ€¦")
    try:
        result = await asyncio.wait_for(_run_scrape(), timeout=300)  # 5 min max
        print(f"[Scheduler] Auto-scrape complete: {result}")
    except asyncio.TimeoutError:
        print("[Scheduler] Auto-scrape timed out after 5 minutes")
    except Exception as e:
        print(f"[Scheduler] Auto-scrape failed: {e}")
        import traceback; traceback.print_exc()




@app.on_event("startup")
async def startup():
    try:
        await init_db()
        print("[Startup] DB initialized")
    except Exception as e:
        print(f"[Startup] DB init error (will retry on requests): {e}")


    # â”€â”€ Auto-migrate: add any missing columns safely â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    new_columns = [
        ("user_settings", "profile_phone",     "VARCHAR"),
        ("user_settings", "profile_address",    "VARCHAR"),
        ("user_settings", "profile_linkedin",   "VARCHAR"),
        ("user_settings", "profile_github",     "VARCHAR"),
        ("user_settings", "profile_website",    "VARCHAR"),
        ("user_settings", "profile_summary",    "TEXT"),
        ("user_settings", "telegram_bot_token", "VARCHAR"),
        ("user_settings", "telegram_chat_id",   "VARCHAR"),
    ]
    try:
        async with engine.begin() as conn:
            for table, col, typedef in new_columns:
                try:
                    # Works for both SQLite and PostgreSQL
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))
                except Exception:
                    pass  # column already exists â€” safe to ignore
        print("[Startup] DB migration complete")
    except Exception as e:
        print(f"[Startup] DB migration error: {e}")

    # â”€â”€ Init Telegram + Seed companies in background (non-blocking) â”€â”€â”€â”€â”€â”€
    async def _background_init():
        try:
            async with SessionLocal() as db:
                result = await db.execute(text(
                    "SELECT telegram_bot_token, telegram_chat_id FROM user_settings "
                    "WHERE telegram_bot_token IS NOT NULL AND telegram_bot_token != '' LIMIT 1"
                ))
                row = result.fetchone()
                if row and row[0] and row[1]:
                    await telegram_bot.init_bot(row[0], row[1])
        except Exception as e:
            print(f"[Startup] Telegram init skipped: {e}")
        try:
            from scrapers.company_seeder import seed_companies_if_empty
            await seed_companies_if_empty()
        except Exception as e:
            print(f"[Startup] Company seeder failed: {e}")

    asyncio.create_task(_background_init())
    # Start auto-scraper scheduler (every 6 hours by default)
    async with SessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == "auto_scrape_cron"))
        row = result.scalar_one_or_none()
        cron_expr = row.value if row and row.value else "0 * * * *"

    _scheduler.add_job(_auto_scrape, CronTrigger.from_crontab(cron_expr), id="auto_scrape", replace_existing=True)
    _scheduler.start()
    print(f"[Scheduler] Auto-scrape scheduled: {cron_expr}")



# â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RegisterBody(BaseModel):
    email: str
    password: str
    name: Optional[str] = ""

class LoginBody(BaseModel):
    email: str
    password: str

@app.post("/api/auth/register")
async def register(body: RegisterBody):
    async with SessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == body.email.lower()))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
        user_id = str(_uuid.uuid4())
        now = datetime.utcnow().isoformat()
        user = User(
            id=user_id,
            email=body.email.lower().strip(),
            password_hash=hash_password(body.password),
            name=body.name or "",
            created_at=now,
            last_seen_at=now,
        )
        db.add(user)
        # Create default user settings
        db.add(UserSettings(
            user_id=user_id,
            resume="",
            job_roles='["Data Engineer"]',
            countries='["USA", "Remote"]',
            visa_filter=False,
            level_filter=False,
        ))
        await db.commit()
    token = create_token(user_id)
    return {"token": token, "user": {"id": user_id, "email": body.email.lower(), "name": body.name or ""}}


@app.post("/api/auth/login")
async def login(body: LoginBody):
    try:
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.email == body.email.lower()))
            user = result.scalar_one_or_none()
            if not user or not verify_password(body.password, user.password_hash):
                raise HTTPException(status_code=401, detail="Invalid email or password")
            # Update last_seen
            user.last_seen_at = datetime.utcnow().isoformat()
            await db.commit()
        token = create_token(user.id)
        return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("[LOGIN ERROR]", str(e))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/me")
async def get_me(user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"id": user.id, "email": user.email, "name": user.name, "created_at": user.created_at}


# â”€â”€ Change Password (logged-in users) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str

@app.post("/api/auth/change-password")
async def change_password(body: ChangePasswordBody, user_id: str = Depends(get_current_user_id)):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.password_hash = hash_password(body.new_password)
        await db.commit()
    return {"ok": True, "message": "Password changed successfully"}


# â”€â”€ Forgot Password â€” sends reset email via Resend â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import secrets as _secrets
import os as _os
from database import PasswordResetToken as _PRT

class ForgotPasswordBody(BaseModel):
    email: str

@app.post("/api/auth/forgot-password")
async def forgot_password(body: ForgotPasswordBody):
    _SAFE_RESPONSE = {"ok": True, "message": "If that email is registered, you'll receive a reset link shortly."}
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == body.email.lower().strip()))
        user = result.scalar_one_or_none()
        if not user:
            return _SAFE_RESPONSE  # don't reveal whether email exists

        # Expire any existing unused tokens for this user
        existing = await db.execute(
            select(_PRT).where(_PRT.user_id == user.id, _PRT.used == False)
        )
        for t in existing.scalars().all():
            t.used = True

        # Generate fresh token (valid 1 hour)
        token = _secrets.token_urlsafe(40)
        from datetime import timezone, timedelta
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        now_iso = datetime.now(timezone.utc).isoformat()
        db.add(_PRT(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            used=False,
            created_at=now_iso,
        ))
        await db.commit()

    # Build reset link
    frontend_url = _os.getenv("FRONTEND_URL", "https://job-hunter-sigma.vercel.app").rstrip("/")
    reset_link = f"{frontend_url}?reset_token={token}"
    user_name = user.name or "there"

    # Send email via Resend
    try:
        import resend
        resend.api_key = _os.getenv("RESEND_API_KEY", "")
        resend.Emails.send({
            "from": _os.getenv("EMAIL_FROM", "onboarding@resend.dev"),
            "to": [user.email],
            "subject": "Reset your Job Hunter password",
            "html": f"""
<!DOCTYPE html>
<html>
<body style="font-family:Inter,sans-serif;background:#f8fafc;margin:0;padding:32px;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
    <div style="background:linear-gradient(135deg,#1d4ed8,#0284c7);padding:32px 36px;">
      <div style="font-size:22px;font-weight:800;color:#fff;letter-spacing:-0.03em;">ðŸŽ¯ Job Hunter</div>
      <div style="font-size:13px;color:rgba(255,255,255,0.7);margin-top:4px;">Hunt Smarter, Not Harder</div>
    </div>
    <div style="padding:36px;">
      <h2 style="font-size:20px;font-weight:700;color:#0f172a;margin:0 0 12px;">Hi {user_name},</h2>
      <p style="font-size:15px;color:#475569;line-height:1.6;margin:0 0 24px;">
        We received a request to reset your Job Hunter password. Click the button below to choose a new password.
        This link expires in <strong>1 hour</strong>.
      </p>
      <a href="{reset_link}"
         style="display:inline-block;background:linear-gradient(135deg,#1d4ed8,#2563eb);color:#fff;text-decoration:none;font-size:15px;font-weight:700;padding:14px 28px;border-radius:10px;letter-spacing:-0.01em;">
        Reset Password â†’
      </a>
      <p style="font-size:12px;color:#94a3b8;margin-top:28px;line-height:1.6;">
        If you didn't request this, you can safely ignore this email. Your password won't change.<br/>
        Link not working? Copy this: <span style="color:#2563eb;">{reset_link}</span>
      </p>
    </div>
  </div>
</body>
</html>
""",
        })
        print(f"[Auth] Reset email sent to {user.email}")
    except Exception as e:
        print(f"[Auth] Failed to send reset email: {e}")

    return _SAFE_RESPONSE


# â”€â”€ Reset Password with token â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ResetPasswordBody(BaseModel):
    token: str
    new_password: str

@app.post("/api/auth/reset-password")
async def reset_password_with_token(body: ResetPasswordBody):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    from datetime import timezone
    async with SessionLocal() as db:
        result = await db.execute(select(_PRT).where(_PRT.token == body.token))
        token_record = result.scalar_one_or_none()
        if not token_record:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link. Please request a new one.")
        if token_record.used:
            raise HTTPException(status_code=400, detail="This reset link has already been used. Please request a new one.")
        try:
            expires_at = datetime.fromisoformat(token_record.expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid token data.")
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")

        result2 = await db.execute(select(User).where(User.id == token_record.user_id))
        user = result2.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=400, detail="User not found.")
        user.password_hash = hash_password(body.new_password)
        token_record.used = True
        await db.commit()
        return {"ok": True, "message": "Password reset successfully. You can now log in.", "email": user.email}

# ── OAuth (Google / GitHub) ───────────────────────────────────────────────────
import urllib.parse
from fastapi.responses import RedirectResponse

GOOGLE_CLIENT_ID = _os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = _os.getenv("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID = _os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = _os.getenv("GITHUB_CLIENT_SECRET", "")
FRONTEND_URL = _os.getenv("FRONTEND_URL", "http://localhost:5173")

from fastapi import Request

@app.get("/api/auth/google/login")
def google_login(request: Request):
    frontend = request.headers.get("origin") or FRONTEND_URL
    if not GOOGLE_CLIENT_ID:
        return RedirectResponse(f"{frontend}?error=Google+OAuth+not+configured")
    base_url = str(request.base_url).rstrip("/")
    if "railway.app" in base_url and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://")
    redirect_uri = f"{base_url}/api/auth/google/callback"
    scope = "openid email profile"
    url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={GOOGLE_CLIENT_ID}&redirect_uri={urllib.parse.quote(redirect_uri)}&scope={urllib.parse.quote(scope)}"
    return RedirectResponse(url)

@app.get("/api/auth/google/callback")
async def google_callback(request: Request, code: str = None, error: str = None):
    # Origin won't be present on a callback redirect from Google, so use FRONTEND_URL env var
    frontend = _os.getenv("FRONTEND_URL", "https://job-hunter-sigma.vercel.app" if "railway" in str(request.base_url) else "http://localhost:5173")
    if error or not code:
        return RedirectResponse(f"{frontend}?error=Google+login+failed")
    base_url = str(request.base_url).rstrip("/")
    if "railway.app" in base_url and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://")
    redirect_uri = f"{base_url}/api/auth/google/callback"
    async with httpx.AsyncClient() as client:
        token_res = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri
        })
        token_data = token_res.json()
        if "access_token" not in token_data:
            return RedirectResponse(f"{FRONTEND_URL}?error=Google+token+error")
        user_res = await client.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {token_data['access_token']}"})
        user_data = user_res.json()
        email = user_data.get("email")
        name = user_data.get("name")
        if not email:
            return RedirectResponse(f"{FRONTEND_URL}?error=Google+no+email")
        
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                user = User(id=str(_uuid.uuid4()), email=email, name=name, password_hash="OAUTH_USER", created_at=datetime.utcnow().isoformat() + "Z")
                db.add(user)
                await db.commit()
                await db.refresh(user)
            
            token = create_token(user.id)
            user_json = urllib.parse.quote(json.dumps({"id": user.id, "email": user.email, "name": user.name}))
            return RedirectResponse(f"{frontend}?token={token}&user={user_json}#jobs")

@app.get("/api/auth/github/login")
def github_login(request: Request):
    frontend = request.headers.get("origin") or FRONTEND_URL
    if not GITHUB_CLIENT_ID:
        return RedirectResponse(f"{frontend}?error=GitHub+OAuth+not+configured")
    base_url = str(request.base_url).rstrip("/")
    if "railway.app" in base_url and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://")
    redirect_uri = f"{base_url}/api/auth/github/callback"
    scope = "user:email"
    url = f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&redirect_uri={urllib.parse.quote(redirect_uri)}&scope={urllib.parse.quote(scope)}"
    return RedirectResponse(url)

@app.get("/api/auth/github/callback")
async def github_callback(request: Request, code: str = None, error: str = None):
    frontend = _os.getenv("FRONTEND_URL", "https://job-hunter-sigma.vercel.app" if "railway" in str(request.base_url) else "http://localhost:5173")
    if error or not code:
        return RedirectResponse(f"{frontend}?error=GitHub+login+failed")
    base_url = str(request.base_url).rstrip("/")
    if "railway.app" in base_url and base_url.startswith("http://"):
        base_url = base_url.replace("http://", "https://")
    redirect_uri = f"{base_url}/api/auth/github/callback"
    async with httpx.AsyncClient() as client:
        token_res = await client.post("https://github.com/login/oauth/access_token", data={
            "client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET,
            "code": code, "redirect_uri": redirect_uri
        }, headers={"Accept": "application/json"})
        token_data = token_res.json()
        if "access_token" not in token_data:
            return RedirectResponse(f"{FRONTEND_URL}?error=GitHub+token+error")
        access_token = token_data["access_token"]
        
        user_res = await client.get("https://api.github.com/user", headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"})
        user_data = user_res.json()
        
        email = user_data.get("email")
        if not email:
            emails_res = await client.get("https://api.github.com/user/emails", headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"})
            emails_data = emails_res.json()
            primary = next((e["email"] for e in emails_data if e.get("primary")), None)
            email = primary if primary else (emails_data[0]["email"] if emails_data else None)

        if not email:
            return RedirectResponse(f"{FRONTEND_URL}?error=GitHub+no+email")
            
        name = user_data.get("name") or user_data.get("login") or email.split("@")[0]
        
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                user = User(id=str(_uuid.uuid4()), email=email, name=name, password_hash="OAUTH_USER", created_at=datetime.utcnow().isoformat() + "Z")
                db.add(user)
                await db.commit()
                await db.refresh(user)
            
            token = create_token(user.id)
            user_json = urllib.parse.quote(json.dumps({"id": user.id, "email": user.email, "name": user.name}))
            return RedirectResponse(f"{frontend}?token={token}&user={user_json}#jobs")

import telegram_bot

# â”€â”€ Settings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _get_user_settings(user_id: str) -> dict:
    """Helper to fetch user's AI/resume settings from user_settings table."""
    async with SessionLocal() as db:
        result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        s = result.scalar_one_or_none()
        if not s:
            return {}
        return {
            "resume": s.resume or "",
            "ai_provider": s.ai_provider or "openrouter",
            "ai_api_key": s.ai_api_key or "",
            "ai_model_parse": s.ai_model_parse or "",
            "ai_model_tailor": s.ai_model_tailor or "",
            "ai_model_qualify": s.ai_model_qualify or "",
            "ai_model_cover_letter": s.ai_model_cover_letter or "",
        }


@app.get("/api/settings")
async def get_settings(user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        s = result.scalar_one_or_none()
        if not s:
            # Create defaults
            s = UserSettings(user_id=user_id)
            db.add(s)
            await db.commit()
        data = {
            "resume": s.resume or "",
            "job_roles": json.loads(s.job_roles or '["Data Engineer"]'),
            "countries": json.loads(s.countries or '["USA","Remote"]'),
            "visa_filter": bool(s.visa_filter),
            "level_filter": bool(s.level_filter),
            "ai_provider": s.ai_provider or "openrouter",
            "ai_api_key": s.ai_api_key or "",
            "ai_model_parse": s.ai_model_parse or "google/gemini-2.5-flash-lite",
            "ai_model_tailor": s.ai_model_tailor or "anthropic/claude-opus-4-8",
            "ai_model_qualify": s.ai_model_qualify or "anthropic/claude-opus-4-8",
            "ai_model_cover_letter": s.ai_model_cover_letter or "anthropic/claude-sonnet-4.6",
            "profile_name": s.profile_name or "",
            "profile_visa": s.profile_visa or "",
            "profile_phone": s.profile_phone or "",
            "profile_address": s.profile_address or "",
            "profile_linkedin": s.profile_linkedin or "",
            "profile_github": s.profile_github or "",
            "profile_website": s.profile_website or "",
            "profile_summary": s.profile_summary or "",
            "telegram_bot_token": "â€¢â€¢â€¢â€¢" if s.telegram_bot_token else "",
            "telegram_chat_id": s.telegram_chat_id or "",
            "telegram_configured": bool(s.telegram_bot_token and s.telegram_chat_id),
            # Legacy fields for backward compat
            "auto_scrape_cron": "0 * * * *",
            "last_scraped_at": "",
        }
        return data


@app.put("/api/settings")
async def update_settings(body: dict = Body(...), user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        s = result.scalar_one_or_none()
        if not s:
            s = UserSettings(user_id=user_id)
            db.add(s)
        for field in ["resume", "ai_provider", "ai_model_parse", "ai_model_tailor", "ai_model_qualify", "ai_model_cover_letter",
                       "profile_name", "profile_visa",
                       "profile_phone", "profile_address", "profile_linkedin",
                       "profile_github", "profile_website", "profile_summary",
                       "telegram_chat_id", "ai_api_key", "telegram_bot_token"]:
            if field in body:
                setattr(s, field, body[field])

        if "job_roles" in body:
            s.job_roles = json.dumps(body["job_roles"] if isinstance(body["job_roles"], list) else [body["job_roles"]])
        if "countries" in body:
            s.countries = json.dumps(body["countries"] if isinstance(body["countries"], list) else [body["countries"]])
        if "visa_filter" in body:
            s.visa_filter = bool(body["visa_filter"])
        if "level_filter" in body:
            s.level_filter = bool(body["level_filter"])
        await db.commit()
    return {"ok": True}


@app.post("/api/telegram/test")
async def test_telegram(body: dict = Body(...), user_id: str = Depends(get_current_user_id)):
    """Test Telegram bot connection and send a test message."""
    token = body.get("token", "")
    chat_id = body.get("chat_id", "")
    if not token or not chat_id:
        raise HTTPException(status_code=400, detail="Bot token and Chat ID are required")
    ok, msg = await telegram_bot.test_connection(token, chat_id)
    if ok:
        # Also save to settings
        async with SessionLocal() as db:
            result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
            s = result.scalar_one_or_none()
            if not s:
                s = UserSettings(user_id=user_id)
                db.add(s)
            s.telegram_bot_token = token
            s.telegram_chat_id = chat_id
            await db.commit()
        # Initialize the live bot
        await telegram_bot.init_bot(token, chat_id)
        return {"ok": True, "message": msg}
    else:
        raise HTTPException(status_code=400, detail=f"Telegram error: {msg}")


# â”€â”€ Companies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/companies")
async def list_companies(user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        result = await db.execute(select(Company).order_by(Company.ats, Company.name))
        companies = result.scalars().all()
        return [{"id": c.id, "name": c.name, "ats": c.ats, "slug": c.slug,
                 "careers_url": c.careers_url, "active": c.active, "source": c.source}
                for c in companies]


@app.post("/api/companies/detect")
async def detect_company_ats(body: dict, user_id: str = Depends(get_current_user_id)):
    url = body.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    from scrapers.ats_detect import detect
    result = await detect(url)
    if not result:
        raise HTTPException(status_code=422, detail="Could not detect ATS from this URL")
    return result


@app.post("/api/companies")
async def add_company(body: dict, user_id: str = Depends(get_current_user_id)):
    name = body.get("name", "")
    ats = body.get("ats", "")
    slug = body.get("slug", "")
    careers_url = body.get("careers_url", "")
    if not ats or not slug:
        raise HTTPException(status_code=400, detail="ats and slug required")
    async with SessionLocal() as db:
        company = Company(
            id=str(_uuid.uuid4()),
            name=name or slug.replace("-", " ").title(),
            ats=ats, slug=slug, careers_url=careers_url,
            active=True,
            added_at=datetime.utcnow().isoformat(),
            source="manual",
        )
        db.add(company)
        await db.commit()
        return {"id": company.id, "name": company.name, "ats": company.ats, "slug": company.slug}


@app.delete("/api/companies/{company_id}")
async def delete_company(company_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        result = await db.execute(select(Company).where(Company.id == company_id))
        c = result.scalar_one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
        await db.delete(c)
        await db.commit()
    return {"ok": True}


@app.put("/api/companies/{company_id}/toggle")
async def toggle_company(company_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        result = await db.execute(select(Company).where(Company.id == company_id))
        c = result.scalar_one_or_none()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
        c.active = not c.active
        await db.commit()
        return {"id": c.id, "active": c.active}


# â”€â”€ Jobs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/jobs/count")
async def public_job_count():
    """Public endpoint â€” no auth needed. Returns total job count for login page."""
    async with SessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(Job))
        count = result.scalar() or 0
    return {"count": count}

@app.get("/api/stats/today")
async def public_today_stats():
    """Public endpoint â€” live stats for login page (no auth needed)."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with SessionLocal() as db:
        # Jobs added today
        added_r = await db.execute(
            select(func.count()).select_from(Job).where(Job.scraped_at.like(f"{today}%"))
        )
        added_today = added_r.scalar() or 0
        # Most recent scrape timestamp
        last_r = await db.execute(
            select(Job.scraped_at).order_by(Job.scraped_at.desc()).limit(1)
        )
        last_scraped_at = last_r.scalar()
        # Best ATS match score
        score_r = await db.execute(
            select(func.max(Job.ats_score_before)).select_from(Job)
        )
        best_score = score_r.scalar()

    mins_ago = None
    if last_scraped_at:
        try:
            last_dt = datetime.fromisoformat(last_scraped_at.replace("Z", "+00:00"))
            mins_ago = max(0, int((datetime.now(timezone.utc) - last_dt).total_seconds() / 60))
        except Exception:
            pass

    return {
        "added_today": added_today,
        "last_scrape_mins_ago": mins_ago,
        "best_match_score": best_score,
    }

@app.get("/api/jobs")
async def list_jobs(
    user_id:    str            = Depends(get_current_user_id),
    status:     Optional[str]  = None,
    source:     Optional[str]  = None,
    remote:     Optional[bool] = None,
    country:    Optional[str]  = None,
    time_range: Optional[str]  = None,   # "24h" | "48h" | "7d" | None=all
):
    from datetime import timezone, timedelta
    now = datetime.now(timezone.utc)

    async with SessionLocal() as db:
        q = select(Job).order_by(Job.posted_at.desc(), Job.scraped_at.desc())
        if source:
            q = q.where(Job.source == source)
        if remote is not None:
            q = q.where(Job.remote == remote)
        if country:
            q = q.where(Job.country == country)
        result = await db.execute(q)
        jobs = result.scalars().all()

        # Get user's job statuses
        job_ids = [j.id for j in jobs]
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id.in_(job_ids))
        )
        user_jobs_map = {uj.job_id: uj for uj in uj_result.scalars().all()}

    # Filter by status using user_jobs overlay
    def get_uj_status(j):
        uj = user_jobs_map.get(j.id)
        return uj.status if uj else "new"

    if status:
        jobs = [j for j in jobs if get_uj_status(j) == status]

    # Time filter in Python â€” use posted_at when available, fallback to scraped_at
    def parse_dt(s: str):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def effective_dt(j) -> datetime:
        """Use scraped_at (when WE found it) â€” avoids old posted_at dates from jobspy filtering out fresh scrapes."""
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

    # Merge user_jobs overlay into job dicts
    out = []
    for job in jobs:
        d = _job_to_dict(job)
        uj = user_jobs_map.get(job.id)
        if uj:
            d["status"] = uj.status
            d["tailored_resume"] = uj.tailored_resume
            d["cover_letter"] = uj.cover_letter or ""
            d["ats_score_before"] = uj.ats_score_before
            d["ats_score_after"] = uj.ats_score_after
            d["ats_keywords_matched"] = json.loads(uj.ats_keywords_matched) if uj.ats_keywords_matched else []
            d["ats_keywords_missing"] = json.loads(uj.ats_keywords_missing) if uj.ats_keywords_missing else []
            d["fit_analysis"] = uj.fit_analysis
            d["interview_tips"] = json.loads(uj.interview_tips) if uj.interview_tips else []
            d["notes"] = uj.notes or ""
            d["priority"] = uj.priority or 0
            d["qualify_result"] = json.loads(uj.qualify_result) if uj.qualify_result else None
            d["deadline"] = uj.deadline or ""
            d["interview_date"] = uj.interview_date or ""
        else:
            d["status"] = "new"
        out.append(d)
    return out



@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        d = _job_to_dict(job)
        # Overlay user-specific data
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        if uj:
            d["status"] = uj.status
            d["tailored_resume"] = uj.tailored_resume
            d["cover_letter"] = uj.cover_letter or ""
            d["ats_score_before"] = uj.ats_score_before
            d["ats_score_after"] = uj.ats_score_after
            d["notes"] = uj.notes or ""
            d["priority"] = uj.priority or 0
            d["qualify_result"] = json.loads(uj.qualify_result) if uj.qualify_result else None
        return d


# â”€â”€ Live job verification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/jobs/{job_id}/verify")
async def verify_job_live(job_id: str, user_id: str = Depends(get_current_user_id)):
    """
    HEAD-ping the job URL to check if it still exists.
    Returns: {alive: bool|null, status_code: int|null}
    null = couldn't reach (network error) â€” don't assume dead.
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

            # Some servers block HEAD â€” fall back to GET
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
        # Network error â€” unknown, don't flag as dead
        return {"alive": None, "status_code": None, "error": str(e)[:120]}


class StatusUpdate(BaseModel):
    status: str  # new / applied / skipped / interview


@app.put("/api/jobs/{job_id}/status")
async def set_status(job_id: str, body: StatusUpdate, user_id: str = Depends(get_current_user_id)):
    if body.status not in ("new", "applied", "skipped", "interview"):
        raise HTTPException(400, "Invalid status")
    async with SessionLocal() as db:
        # Verify job exists
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        # Write to user_jobs table
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        if not uj:
            uj = UserJob(id=str(_uuid.uuid4()), user_id=user_id, job_id=job_id, saved_at=datetime.utcnow().isoformat())
            db.add(uj)
        uj.status = body.status
        if body.status == "applied" and not uj.applied_at:
            uj.applied_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        elif body.status != "applied":
            uj.applied_at = None  # reset if un-applied
        await db.commit()
    return {"ok": True}


# â”€â”€ Clear All Jobs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.delete("/api/jobs/all")
async def clear_all_jobs(user_id: str = Depends(get_current_user_id)):
    from sqlalchemy import delete as sa_delete
    async with SessionLocal() as db:
        result = await db.execute(sa_delete(Job))
        await db.commit()
        return {"deleted": result.rowcount}


# â”€â”€ Debug JobSpy â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/debug/jobspy")
async def debug_jobspy(user_id: str = Depends(get_current_user_id)):
    """Test JobSpy directly â€” bypasses DB, shows raw counts."""
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


# ————————————————————————————————————————————————————————————————————————————————


@app.post("/api/jobs/scrape")
async def scrape_jobs(user_id: str = Depends(get_current_user_id)):
    return await _run_scrape()


# ————————————————————————————————————————————————————————————————————————————————


class DescriptionUpdate(BaseModel):
    description: str

@app.put("/api/jobs/{job_id}/description")
async def set_description(job_id: str, body: DescriptionUpdate, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.description = body.description.strip()
        await db.commit()
    return {"ok": True}

@app.post("/api/jobs/{job_id}/fetch-jd")
async def fetch_jd(job_id: str, user_id: str = Depends(get_current_user_id)):
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


# ————————————————————————————————————————————————————————————————————————————————

@app.post("/api/jobs/{job_id}/tailor")
async def tailor_job(job_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")

    user_cfg = await _get_user_settings(user_id)
    api_key = user_cfg.get("ai_api_key", "")
    provider = (user_cfg.get("ai_provider", "openrouter") or "openrouter").lower().strip()
    model = user_cfg.get("ai_model_tailor", "anthropic/claude-opus-4-8")

    if not api_key:
        raise HTTPException(400, "No AI API key set. Add one in Settings.")

    base_resume = user_cfg.get("resume", "")
    jd = job.description

    ats_before = score_ats(base_resume, jd)

    tailored_text = await tailor_resume(base_resume, jd, api_key, provider, model)
    ats_after = score_ats(tailored_text, jd)

    fit = await analyze_fit(base_resume, jd, job.title, job.company, api_key, provider, model)

    # Write tailored resume to user_jobs table
    async with SessionLocal() as db:
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        if not uj:
            uj = UserJob(id=str(_uuid.uuid4()), user_id=user_id, job_id=job_id, saved_at=datetime.utcnow().isoformat())
            db.add(uj)
        uj.tailored_resume = tailored_text
        uj.tailored_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        uj.ats_score_before = ats_before["score"]
        uj.ats_score_after = ats_after["score"]
        uj.ats_keywords_matched = json.dumps(ats_after["matched"])
        uj.ats_keywords_missing = json.dumps(ats_after["missing"])
        uj.fit_analysis = fit["analysis"]
        uj.interview_tips = json.dumps(fit["tips"])
        await db.commit()

    return {
        "ats_before": ats_before,
        "ats_after": ats_after,
        "tailored_resume": tailored_text,
        "fit_analysis": fit["analysis"],
        "interview_tips": fit["tips"],
    }


# ————————————————————————————————————————————————————————————————————————————————

@app.post("/api/jobs/{job_id}/cover-letter")
async def generate_cover_letter_endpoint(job_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")

    user_cfg = await _get_user_settings(user_id)
    api_key = user_cfg.get("ai_api_key", "")
    provider = (user_cfg.get("ai_provider", "openrouter") or "openrouter").lower().strip()
    model = user_cfg.get("ai_model_cover_letter", "anthropic/claude-sonnet-4.6")

    if not api_key:
        raise HTTPException(400, "No AI API key set. Add one in Settings.")

    resume = user_cfg.get("resume", "")
    jd = job.description or ""

    letter = await generate_cover_letter(resume, jd, job.title, job.company, api_key, provider, model)

    # Write cover letter to user_jobs table
    async with SessionLocal() as db:
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        if not uj:
            uj = UserJob(id=str(_uuid.uuid4()), user_id=user_id, job_id=job_id, saved_at=datetime.utcnow().isoformat())
            db.add(uj)
        uj.cover_letter = letter
        await db.commit()

    return {"cover_letter": letter}


class NotesUpdate(BaseModel):
    notes: str


@app.put("/api/jobs/{job_id}/notes")
async def update_notes(job_id: str, body: NotesUpdate, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        # Verify job exists
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        # Write to user_jobs
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        if not uj:
            uj = UserJob(id=str(_uuid.uuid4()), user_id=user_id, job_id=job_id, saved_at=datetime.utcnow().isoformat())
            db.add(uj)
        uj.notes = body.notes
        await db.commit()
    return {"ok": True}


# â”€â”€ PDF Download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/jobs/{job_id}/resume/pdf")
async def download_pdf(job_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        tailored_resume = uj.tailored_resume if uj else None
        if not tailored_resume:
            raise HTTPException(400, "No tailored resume yet. Click Tailor Resume first.")

    pdf_bytes = generate_pdf(tailored_resume, job.title, job.company)
    title_slug = re.sub(r"[^\w]+", "_", job.title or "Senior_Data_Engineer").strip("_")
    filename = f"Jagadish_Reddy_Butukuri_{title_slug}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# â”€â”€ DOCX Download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/jobs/{job_id}/resume/docx")
async def download_docx(job_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        tailored_resume = uj.tailored_resume if uj else None
        if not tailored_resume:
            raise HTTPException(400, "No tailored resume yet. Click Tailor Resume first.")

    docx_bytes = generate_docx(tailored_resume, job.title, job.company)
    title_slug = re.sub(r"[^\w]+", "_", job.title or "Senior_Data_Engineer").strip("_")
    filename = f"Jagadish_Reddy_Butukuri_{title_slug}.docx"

    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# â”€â”€ Quick Tailor (paste any JD, no job record needed) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class QuickTailorRequest(BaseModel):
    jd: str
    company: str = "Company"

@app.post("/api/quick-tailor")
async def quick_tailor(body: QuickTailorRequest, user_id: str = Depends(get_current_user_id)):
    user_cfg = await _get_user_settings(user_id)
    api_key = user_cfg.get("ai_api_key", "")
    provider = (user_cfg.get("ai_provider", "openrouter") or "openrouter").lower().strip()
    model    = user_cfg.get("ai_model", "google/gemini-flash-1.5")

    if not api_key:
        raise HTTPException(400, "No AI API key set. Add one in Settings.")

    base_resume = user_cfg.get("resume", "")
    if not base_resume:
        raise HTTPException(400, "No base resume found. Add it in Settings.")

    tailored = await tailor_resume(base_resume, body.jd, api_key, provider, model)
    return {"tailored_resume": tailored}


@app.post("/api/quick-tailor/pdf")
async def quick_tailor_pdf(body: QuickTailorRequest, user_id: str = Depends(get_current_user_id)):
    user_cfg = await _get_user_settings(user_id)
    api_key = user_cfg.get("ai_api_key", "")
    provider = (user_cfg.get("ai_provider", "openrouter") or "openrouter").lower().strip()
    model    = user_cfg.get("ai_model", "google/gemini-flash-1.5")

    if not api_key:
        raise HTTPException(400, "No AI API key set.")

    base_resume = user_cfg.get("resume", "")
    if not base_resume:
        raise HTTPException(400, "No base resume found.")

    tailored = await tailor_resume(base_resume, body.jd, api_key, provider, model)
    pdf_bytes = generate_pdf(tailored, "", body.company)
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="Jagadish_Reddy_Butukuri_Senior_Data_Engineer.pdf"'},
    )


@app.post("/api/quick-tailor/docx")
async def quick_tailor_docx(body: QuickTailorRequest, user_id: str = Depends(get_current_user_id)):
    user_cfg = await _get_user_settings(user_id)
    api_key = user_cfg.get("ai_api_key", "")
    provider = (user_cfg.get("ai_provider", "openrouter") or "openrouter").lower().strip()
    model    = user_cfg.get("ai_model", "google/gemini-flash-1.5")

    if not api_key:
        raise HTTPException(400, "No AI API key set.")

    base_resume = user_cfg.get("resume", "")
    if not base_resume:
        raise HTTPException(400, "No base resume found.")

    tailored = await tailor_resume(base_resume, body.jd, api_key, provider, model)
    docx_bytes = generate_docx(tailored, "", body.company)
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="Jagadish_Reddy_Butukuri_Senior_Data_Engineer.docx"'},
    )


# â”€â”€ Save Package (create folder + write all files to disk) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _build_package_zip(company: str, jd: str, tailored_resume: str, cover_letter: str = "") -> bytes:
    """Build all package files into a ZIP in memory. Returns raw ZIP bytes."""
    import zipfile, io as _io
    company_clean = re.sub(r"[^\w\s\-]", "", company).strip()
    slug = re.sub(r"[^\w]+", "_", company).strip("_")
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{company_clean}_JD.docx",         generate_jd_docx(jd, company_clean))
        zf.writestr("Jagadish_Reddy_Butukuri_Senior_Data_Engineer.pdf",  generate_pdf(tailored_resume, "", company))
        zf.writestr("Jagadish_Reddy_Butukuri_Senior_Data_Engineer.docx", generate_docx(tailored_resume, "", company))
        if cover_letter and cover_letter.strip():
            zf.writestr(f"Jagadish_Reddy_Butukuri_{slug}_CoverLetter.txt",
                        cover_letter.encode("utf-8"))
    return buf.getvalue()


@app.get("/api/jobs/{job_id}/save-package")
async def save_package(job_id: str, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        tailored_resume = uj.tailored_resume if uj else None
        cover_letter = uj.cover_letter if uj else ""
        if not tailored_resume:
            raise HTTPException(400, "No tailored resume yet. Tailor first.")

    zip_bytes = _build_package_zip(job.company, job.description or "", tailored_resume, cover_letter or "")
    slug = re.sub(r"[^\w]+", "_", job.company).strip("_")
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Package_{slug}.zip"'},
    )


class QuickSaveRequest(BaseModel):
    company: str
    jd: str
    tailored_resume: str
    cover_letter: str = ""

@app.post("/api/quick-tailor/save-package")
async def quick_save_package(body: QuickSaveRequest, user_id: str = Depends(get_current_user_id)):
    zip_bytes = _build_package_zip(body.company, body.jd, body.tailored_resume, body.cover_letter)
    slug = re.sub(r"[^\w]+", "_", body.company).strip("_")
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Package_{slug}.zip"'},
    )


# â”€â”€ Analytics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/analytics")
async def get_analytics(user_id: str = Depends(get_current_user_id)):
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


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

# â”€â”€ Deadline / Interview Date / Priority â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class DeadlineUpdate(BaseModel):
    deadline: Optional[str] = None        # ISO date "2025-03-15"
    interview_date: Optional[str] = None  # ISO datetime
    priority: Optional[int] = None        # 0/1/2

@app.patch("/api/jobs/{job_id}/meta")
async def update_job_meta(job_id: str, body: DeadlineUpdate, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        # Write to user_jobs for per-user deadline/interview/priority
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        if not uj:
            uj = UserJob(id=str(_uuid.uuid4()), user_id=user_id, job_id=job_id, saved_at=datetime.utcnow().isoformat())
            db.add(uj)
        if body.deadline is not None:
            uj.deadline = body.deadline
        if body.interview_date is not None:
            uj.interview_date = body.interview_date
        if body.priority is not None:
            uj.priority = body.priority
        await db.commit()
    return {"ok": True}


# â”€â”€ Search endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/search")
async def search_jobs(
    user_id: str = Depends(get_current_user_id),
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


# â”€â”€ Upcoming deadlines / reminders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/api/reminders")
async def get_reminders(user_id: str = Depends(get_current_user_id)):
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


# â”€â”€ Scheduler control â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class SchedulerConfig(BaseModel):
    cron: str  # e.g. "0 */6 * * *"

@app.get("/api/scheduler/status")
async def scheduler_status(user_id: str = Depends(get_current_user_id)):
    jobs = _scheduler.get_jobs()
    return {
        "running": _scheduler.running,
        "jobs": [{"id": j.id, "next_run": str(j.next_run_time)} for j in jobs],
    }

@app.put("/api/scheduler/cron")
async def update_scheduler_cron(body: SchedulerConfig, user_id: str = Depends(get_current_user_id)):
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
async def run_scraper_now(user_id: str = Depends(get_current_user_id)):
    """Trigger scraper immediately outside the schedule."""
    _scheduler.modify_job("auto_scrape", next_run_time=datetime.now())
    return {"ok": True, "message": "Scraper triggered immediately"}



# â”€â”€ Structured Profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ProfileExperience(BaseModel):
    role: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    years: float = 0
    bullets: List[str] = []
    expanded: bool = True

class ProfileEducation(BaseModel):
    degree: str = ""
    school: str = ""
    year: str = ""
    expanded: bool = True

class ProfileProject(BaseModel):
    name: str = ""
    description: str = ""
    expanded: bool = True

class ProfileData(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    address: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    visa_status: str = ""
    experience: List[ProfileExperience] = []
    education: List[ProfileEducation] = []
    projects: List[ProfileProject] = []
    skills: List[str] = []
    certifications: List[str] = []

@app.get("/api/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        row = await db.get(Setting, "profile")
        if row and row.value:
            return json.loads(row.value)
    return {}

def _profile_to_resume_text(p: dict) -> str:
    """Convert structured profile to plain-text resume for AI tailoring."""
    lines = []
    name = p.get("name", "")
    email = p.get("email", "")
    phone = p.get("phone", "")
    location = p.get("location", "")
    contact = " | ".join(filter(None, [phone, email, location]))
    if name:
        lines.append(f"{name} â€” Senior Data Engineer")
    if contact:
        lines.append(contact)
    lines.append("")

    exp = p.get("experience", [])
    if exp:
        lines.append("WORK EXPERIENCE:")
        for e in exp:
            role = e.get("role", "")
            company = e.get("company", "")
            start = e.get("start_date", "")
            end = e.get("end_date", "")
            date_range = f"{start} â€“ {end}".strip(" â€“") if (start or end) else ""
            header = " | ".join(filter(None, [f"{role} @ {company}" if role and company else (role or company), date_range]))
            lines.append(header)
            for b in e.get("bullets", []):
                if b.strip():
                    lines.append(f"â€¢ {b.strip()}")
            lines.append("")

    edu = p.get("education", [])
    if edu:
        lines.append("EDUCATION:")
        for e in edu:
            degree = e.get("degree", "")
            school = e.get("school", "")
            year = e.get("year", "")
            lines.append(" | ".join(filter(None, [f"{degree} @ {school}" if degree and school else (degree or school), year])))
        lines.append("")

    skills = p.get("skills", [])
    if skills:
        lines.append("TECHNICAL SKILLS:")
        lines.append(", ".join(skills))
        lines.append("")

    certs = p.get("certifications", [])
    if certs:
        lines.append("CERTIFICATIONS:")
        lines.append(", ".join(certs))

    return "\n".join(lines).strip()


@app.put("/api/profile")
async def save_profile(body: ProfileData, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as db:
        row = await db.get(Setting, "profile")
        val = json.dumps(body.model_dump())
        if row:
            row.value = val
        else:
            db.add(Setting(key="profile", value=val))

        # Auto-sync plain-text resume for AI tailoring
        resume_text = _profile_to_resume_text(body.model_dump())
        if resume_text:
            resume_row = await db.get(Setting, "resume")
            if resume_row:
                resume_row.value = resume_text
            else:
                db.add(Setting(key="resume", value=resume_text))

        await db.commit()
    return {"ok": True}


# â”€â”€ Parse Resume File â†’ structured profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/api/profile/parse-resume")
async def parse_resume_file(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    import io

    user_cfg = await _get_user_settings(user_id)
    api_key = user_cfg.get("ai_api_key", "")
    provider = (user_cfg.get("ai_provider", "openrouter") or "openrouter").lower().strip()
    model = user_cfg.get("ai_model_parse", "google/gemini-2.5-flash-lite")


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

    PARSE_SYSTEM = """Extract ALL structured information from this resume. Return ONLY valid JSON, no markdown, no explanation:
{
  "name": "",
  "email": "",
  "phone": "",
  "location": "",
  "linkedin": "",
  "github": "",
  "summary": "",
  "experience": [
    {
      "role": "",
      "company": "",
      "start_date": "Jan 2022",
      "end_date": "Present",
      "years": 2.5,
      "bullets": ["All bullet points exactly as written in resume â€” do not skip, summarize, or truncate any"]
    }
  ],
  "education": [
    {"degree": "", "school": "", "year": "", "gpa": ""}
  ],
  "projects": [
    {"name": "", "description": "", "stack": "", "url": ""}
  ],
  "skills": ["Python", "SQL"],
  "certifications": ["AWS Solutions Architect"]
}

Rules:
- name: full name from top of resume
- email: extract email address
- phone: extract phone number
- location: ONLY extract the applicant's personal home city/state. Do NOT extract locations of client companies or work history. If missing, leave as "".
- linkedin: full LinkedIn URL or just the handle (e.g. linkedin.com/in/username)
- github: full GitHub URL or handle (e.g. github.com/username)
- summary: professional summary or objective paragraph if present, else ""
- start_date / end_date: exact date format from resume (e.g. "Sep 2023", "Jan 2021", "Present"). Use "" if not found.
- years: calculate as decimal from start to end (2 years 6 months = 2.5). Estimate if dates missing.
- bullets: extract EVERY bullet point for each role exactly as written â€” do NOT truncate, skip, or summarize any bullet.
- skills: technical only (languages, frameworks, tools, platforms, databases, cloud services). No soft skills.
- certifications: only actual certs/licenses. Empty array [] if none.
- education: ALWAYS extract even if at the bottom. Include degree, university/school name, graduation year, GPA if present.
- projects: extract all personal/side projects with name, description, tech stack, and URL if present.
- Use "" for missing text fields. Use [] for missing arrays.
- Do NOT invent, paraphrase, or add anything not explicitly in the resume."""

    try:
        response = await chat(
            system=PARSE_SYSTEM,
            user=f"Resume:\n\n{text[:15000]}",
            api_key=api_key,
            provider=provider,
            model=model,
            max_tokens=4000,
        )
    except Exception as e:
        raise HTTPException(502, f"AI call failed on all fallback models. Last error: {str(e)[:300]}")

    try:
        import json_repair
        result = json_repair.loads(response)
        if not isinstance(result, dict):
            raise Exception("Parsed result is not a JSON object. Ensure the AI returns structured data.")
        return result
    except Exception as e:
        raise HTTPException(500, f"AI could not parse resume JSON. Error: {str(e)}\n\nRaw output snippet: {response[:500]}")



# â”€â”€ Job Qualification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/api/jobs/{job_id}/qualify")
async def qualify_job_endpoint(job_id: str, user_id: str = Depends(get_current_user_id)):
    from ai.qualify import qualify_job

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")

    user_cfg = await _get_user_settings(user_id)
    api_key = user_cfg.get("ai_api_key", "")
    provider = (user_cfg.get("ai_provider", "openrouter") or "openrouter").lower().strip()
    model = user_cfg.get("ai_model_qualify", "anthropic/claude-opus-4-8")
    # Profile still read from global Setting for now
    async with SessionLocal() as db:
        profile_row = await db.get(Setting, "profile")
    profile_raw = profile_row.value if profile_row else "{}"
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
        # Write qualify_result to user_jobs table
        uj_result = await db.execute(
            select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
        )
        uj = uj_result.scalar_one_or_none()
        if not uj:
            uj = UserJob(id=str(_uuid.uuid4()), user_id=user_id, job_id=job_id, saved_at=datetime.utcnow().isoformat())
            db.add(uj)
        uj.qualify_result = json.dumps(result)
        # Auto-set priority based on score
        score = result.get("score", 0)
        if result.get("qualified") and score >= 80:
            uj.priority = 2
        elif result.get("qualified") and score >= 60:
            uj.priority = 1
        await db.commit()

    return result


@app.post("/api/jobs/qualify-all")
async def qualify_all_jobs(background_tasks: BackgroundTasks, user_id: str = Depends(get_current_user_id)):
    """Qualify all unanalyzed jobs in the background."""
    background_tasks.add_task(_run_qualify_all)
    return {"message": "Qualification running in background"}


async def _run_qualify_all():
    """Standalone qualify-all â€” usable from scheduler and endpoint."""
    from ai.qualify import qualify_job

    async with SessionLocal() as db:
        settings_result = await db.execute(select(Setting))
        settings = {r.key: r.value for r in settings_result.scalars().all()}

    api_key = settings.get("ai_api_key", "")
    provider = settings.get("ai_provider", "openrouter")
    model = settings.get("ai_model", "google/gemini-flash-1.5")
    profile_raw = settings.get("profile", "{}")
    try:
        profile = json.loads(profile_raw)
    except Exception:
        profile = {}

    if not api_key or not profile:
        print("[Qualify] No API key or profile â€” skipping auto-qualify")
        return

    async with SessionLocal() as db:
        result = await db.execute(
            select(Job).where(Job.qualify_result == None, Job.status == "new")
        )
        jobs = result.scalars().all()

    print(f"[Qualify] Auto-qualifying {len(jobs)} new jobsâ€¦")
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
                if j:
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
        await asyncio.sleep(0.3)

    print(f"[Qualify] Done. Qualified={qualified} Disqualified={disqualified}")



# â”€â”€ Clean HTML descriptions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/api/jobs/clean-descriptions")
async def clean_html_descriptions(user_id: str = Depends(get_current_user_id)):
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
                # Collapse 3+ newlines â†’ 2
                clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
                j = await db.get(Job, job.id)
                j.description = clean[:10000]
                cleaned += 1
        await db.commit()

    return {"cleaned": cleaned}




