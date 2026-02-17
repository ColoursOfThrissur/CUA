@echo off
echo Starting Offline Agent System (Production Mode)...
echo.

echo [1/2] Starting Enhanced Python Backend...
start "Agent API" cmd /k "cd /d %~dp0 && python api\enhanced_server.py"

echo [2/2] Starting React Frontend (Production Build)...
timeout /t 3 /nobreak > nul
start "Agent UI" cmd /k "cd /d %~dp0\ui && npx serve -s build -l 3000"

echo.
echo Production System Started!
echo ========================================
echo  Frontend:    http://localhost:3000
echo  Backend:     http://localhost:8000  
echo  API Docs:    http://localhost:8000/docs
echo  WebSocket:   ws://localhost:8000/ws
echo ========================================
echo.
echo Features:
echo  ✓ Voice Input with Speech Recognition
echo  ✓ Real-time WebSocket Updates  
echo  ✓ Session Management
echo  ✓ Plan Review & Approval
echo  ✓ Execution Timeline
echo  ✓ Safety Controls & Audit Trail
echo.
pause