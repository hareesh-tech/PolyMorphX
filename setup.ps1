<#
    PolyMorph one-shot setup - Windows (PowerShell)
    Creates all virtualenvs, installs every dependency, and leaves the
    project ready to run (CLI + web console).

    Run from an elevated or normal PowerShell:
        .\setup.ps1
    Or just double-click setup.bat.
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=================================================="
Write-Host " PolyMorph setup (Windows)"
Write-Host "=================================================="

function Require-Cmd($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: $name not found. $hint" -ForegroundColor Red
        exit 1
    }
}

# ---- prerequisite checks ----
Require-Cmd python "Install Python 3.8+ from python.org (tick 'Add to PATH') and re-run."
$pyv = (python -c "import sys; print('%d.%d' % sys.version_info[:2])")
$pyok = (python -c "import sys; print(1 if sys.version_info[:2] >= (3,8) else 0)")
if ($pyok -ne "1") { Write-Host "ERROR: Python 3.8+ required (found $pyv)." -ForegroundColor Red; exit 1 }
Write-Host " Python $pyv  OK"

Require-Cmd node "Install Node.js 18+ from nodejs.org and re-run."
Require-Cmd npm  "Install Node.js (includes npm) and re-run."
Write-Host (" Node " + (node -v) + "  OK")
Write-Host ""

# ---- 1. engine venv (also used by the web backend as the orchestrator interpreter) ----
Write-Host "==> [1/3] Engine virtualenv (.venv) + dependencies"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\pip.exe install -r requirements.txt
Write-Host ""

# ---- 2. web backend venv ----
Write-Host "==> [2/3] Web backend virtualenv (web\backend\.venv) + dependencies"
python -m venv web\backend\.venv
& .\web\backend\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\web\backend\.venv\Scripts\pip.exe install -r web\backend\requirements.txt
Write-Host ""

# ---- 3. web frontend deps ----
Write-Host "==> [3/3] Web frontend dependencies (npm install)"
Push-Location web\frontend
npm install
Pop-Location
Write-Host ""

Write-Host "=================================================="
Write-Host " Setup complete."
Write-Host ""
Write-Host " Start the web console:"
Write-Host "     .\run-web.ps1        (then open http://localhost:5173)"
Write-Host ""
Write-Host " Or run the CLI directly:"
Write-Host "     .\.venv\Scripts\python.exe modules\orchestrator.py ``"
Write-Host "         --input <your_binary.exe> --config modules\config.json ``"
Write-Host "         --output .\Output --cfg-seed 1234 -v"
Write-Host "=================================================="
