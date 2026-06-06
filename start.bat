@echo off
echo Starting Job Hunter...

:: Backend
start "Job Hunter - API" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

:: Wait 2 seconds for backend to start
timeout /t 2 /nobreak >nul

:: Frontend
start "Job Hunter - UI" cmd /k "cd /d %~dp0frontend && npm run dev"

:: Open browser after 3 seconds
timeout /t 3 /nobreak >nul
start http://localhost:5173
