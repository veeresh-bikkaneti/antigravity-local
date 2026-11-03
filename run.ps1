# Google Antigravity Local - 1-Command PowerShell Bootstrap
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
Set-Location $scriptDir

# Prefer managed virtual environment Python if available
$venvPython = Join-Path $scriptDir "venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython run.py @args
    exit $LASTEXITCODE
}

# Check system Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Error "[ERROR] Python was not found in PATH. Install Python 3.11/3.12: winget install Python.Python.3.12"
    exit 1
}

& $pythonCmd.Source run.py @args
