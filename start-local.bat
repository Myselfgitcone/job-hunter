@echo off
REM ============================================================
REM  Job Hunter - LOCAL sandbox
REM
REM  backend\.env points DATABASE_URL at the PRODUCTION Railway
REM  Postgres. Environment variables set here win over the .env
REM  file (load_dotenv does not override), so this launcher keeps
REM  a local run off the live database:
REM
REM    DATABASE_URL      -> a local SQLite file, jobs_local.db
REM    DISABLE_SCHEDULER -> no scraping, so no API credits are spent
REM
REM  Use start.bat instead only when you intend to touch production.
REM ============================================================
echo Starting Job Hunter (LOCAL sandbox, SQLite, scheduler off)...

start "Job Hunter LOCAL - API" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && set DATABASE_URL=sqlite+aiosqlite:///./jobs_local.db&& set DISABLE_SCHEDULER=1&& set ADMIN_EMAIL=jaggubhai8766@gmail.com&& uvicorn main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 3 /nobreak >nul

start "Job Hunter LOCAL - UI" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 4 /nobreak >nul
start http://localhost:5173
echo.
echo   API : http://localhost:8000      (docs at /docs)
echo   UI  : http://localhost:5173
echo   DB  : backend\jobs_local.db      (delete it to start clean)
echo.
