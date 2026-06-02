@echo off
echo ============================================
echo  Job Hunter — First-time Setup
echo ============================================
echo.

echo [1/3] Setting up Python backend...
cd backend
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
cd ..

echo.
echo [2/3] Setting up frontend...
cd frontend
call npm install
cd ..

echo.
echo [3/3] Done!
echo.
echo Run start.bat to launch the app.
pause
