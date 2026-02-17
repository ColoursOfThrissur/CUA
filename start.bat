@echo off
echo Starting CUA Autonomous Agent System...
echo.

echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo Starting FastAPI backend server...
start "CUA Backend" python api/server.py

echo.
echo Backend started on http://localhost:8000
echo.
echo To start the frontend:
echo 1. Open new terminal
echo 2. cd ui
echo 3. npm install
echo 4. npm start
echo.
echo Frontend will be available on http://localhost:3000
echo.
pause