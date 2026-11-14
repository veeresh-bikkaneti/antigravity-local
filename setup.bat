@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================================
echo  Google Antigravity Local Setup (Windows)
echo ===================================================

REM Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.11, 3.12, or 3.13 from https://python.org
    exit /b 1
)

REM Create virtual environment if not present
if not exist "venv" (
    echo [1/3] Creating Python virtual environment in .\venv...
    python -m venv venv
) else (
    echo [1/3] Existing virtual environment found in .\venv.
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip and install requirements
echo [2/3] Installing dependencies from requirements.txt...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

REM Setup environment variables file
if not exist ".env" (
    echo [3/3] Copying .env.example to .env...
    copy .env.example .env >nul
) else (
    echo [3/3] Existing .env file found.
)

REM Turn on the commit-msg hook that blocks AI co-author trailers (only inside a git checkout)
git rev-parse --git-dir >nul 2>&1 && (
    REM Only when nothing is set yet, so a hooks folder you already use keeps working
    for /f "delims=" %%H in ('git config core.hooksPath 2^>nul') do set "HAVE_HOOKS=%%H"
    if not defined HAVE_HOOKS (
        git config core.hooksPath .githooks
        echo Commit hook on: AI co-author trailers are blocked [.githooks/commit-msg].
    )
)

echo.
echo ===================================================
echo  Setup Complete!
echo ===================================================
echo To get started:
echo   1. Activate venv:  venv\Scripts\activate.bat
echo   2. Start Ollama:   ollama run qwen2.5:14b
echo   3. Run test:       python test_local.py
echo   4. Run agent:      python agent_with_workspace.py
echo ===================================================
