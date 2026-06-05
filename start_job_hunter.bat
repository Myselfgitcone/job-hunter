@echo off
echo Starting Job Hunter...

:: Start the FastAPI backend in a new window
echo Starting Backend...
start cmd /k "cd backend && venv\Scripts\activate && uvicorn main:app --reload"

:: Start the Vite frontend in a new window
echo Starting Frontend...
start cmd /k "cd frontend && npm run dev"

echo.
echo Both servers are starting up!
echo Your browser should open automatically, or you can go to: http://localhost:5173
echo.
pause
