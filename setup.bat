@echo off
echo ========================================
echo  Offline Agent System - Production Setup
echo ========================================
echo.

echo [1/4] Installing Python Dependencies...
python -m pip install --upgrade pip
pip install -r api/requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)

echo [2/4] Installing Node.js Dependencies...
cd ui
call npm install
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Node.js dependencies
    pause
    exit /b 1
)

echo [3/4] Building React Production Bundle...
call npm run build
if %errorlevel% neq 0 (
    echo ERROR: Failed to build React app
    pause
    exit /b 1
)
cd ..

echo [4/4] System Ready!
echo.
echo ========================================
echo  Available Commands:
echo ========================================
echo  start.bat          - Development mode (hot reload)
echo  start-prod.bat     - Production mode (optimized)
echo  python cli.py      - Command line interface
echo.
echo  Web Interface:     http://localhost:3000
echo  API Endpoint:      http://localhost:8000
echo  API Docs:          http://localhost:8000/docs
echo ========================================
echo.
pause