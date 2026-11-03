@echo off
setlocal
cd /d "%~dp0"

REM 1. Prefer managed virtual environment Python if available
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" run.py %*
    goto :end
)

REM 2. Otherwise find system Python executable to bootstrap
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python run.py %*
    goto :end
)

py --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py run.py %*
    goto :end
)

echo [ERROR] Python was not found in your system PATH.
echo Please install Python (3.11, 3.12, or 3.13) from https://python.org or run:
echo winget install Python.Python.3.12
pause
exit /b 1

:end
endlocal
