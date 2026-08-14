<#
    Start the PolyMorph web console - Windows (PowerShell)
    Launches the FastAPI backend (:8123) and the Vite frontend (:5173)
    in separate windows. Close those windows to stop the servers.
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$root = $PSScriptRoot

# sanity: setup must have run
if (-not (Test-Path ".\.venv\Scripts\python.exe")) { Write-Host "ERROR: engine venv missing. Run .\setup.ps1 first." -ForegroundColor Red; exit 1 }
if (-not (Test-Path ".\web\backend\.venv\Scripts\python.exe")) { Write-Host "ERROR: backend venv missing. Run .\setup.ps1 first." -ForegroundColor Red; exit 1 }
if (-not (Test-Path ".\web\frontend\node_modules")) { Write-Host "ERROR: frontend deps missing. Run .\setup.ps1 first." -ForegroundColor Red; exit 1 }

# point the backend at the engine venv (has pefile/capstone/keystone/lief)
$env:POLYMORPH_PYTHON = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "Starting backend  -> http://127.0.0.1:8123"
Start-Process -WorkingDirectory (Join-Path $root "web\backend") `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","app.main:app","--port","8123"

Write-Host "Starting frontend -> http://localhost:5173"
Start-Process -WorkingDirectory (Join-Path $root "web\frontend") `
    -FilePath "cmd.exe" -ArgumentList "/c","npm run dev"

Write-Host ""
Write-Host "Both servers launched in separate windows."
Write-Host "Open http://localhost:5173 in your browser."
Write-Host "Close the two spawned windows to stop the servers."
