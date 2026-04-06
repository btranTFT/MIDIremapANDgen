#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-command dev launcher for MIDI Remaster Lab.
    Starts the FastAPI backend and Vite frontend in separate console windows.

.DESCRIPTION
    Proposal citation: Deliverable 4 (demo app); ONBOARDING_REPORT §D item #7.
    This script resolves the "two terminal" friction for new developers.

.PARAMETER Backend
    Path to the backend directory (default: ./backend relative to this script).

.PARAMETER Frontend
    Path to the frontend directory (default: ./frontend relative to this script).

.PARAMETER BackendPort
    Port for the FastAPI backend (default: 8001, matches vite.config.ts proxy).

.EXAMPLE
    # From repo root:
    .\scripts\start.ps1

.EXAMPLE
    # With ML venv:
    .\scripts\start.ps1  # then activate venv_ml in the backend window manually
#>

param(
    [string]$Backend  = (Join-Path (Join-Path $PSScriptRoot "..") "backend"),
    [string]$Frontend = (Join-Path (Join-Path $PSScriptRoot "..") "frontend"),
    [int]   $BackendPort = 8001
)

$Backend  = Resolve-Path $Backend
$Frontend = Resolve-Path $Frontend

# ── Preflight checks ──────────────────────────────────────────────────────
function Test-Command($cmd) { $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

if (-not (Test-Command "python")) {
    Write-Error "python not found. Install Python 3.11+ and add it to PATH."
    exit 1
}
if (-not (Test-Command "node")) {
    Write-Error "node not found. Install Node.js 18+ and add it to PATH."
    exit 1
}
if (-not (Test-Path (Join-Path $Backend "venv\Scripts\activate.ps1"))) {
    Write-Warning "Backend venv not found at $Backend\venv. Run:"
    Write-Warning "  cd $Backend && python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt"
}
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Warning "node_modules not found. Run: cd $Frontend && npm install"
}
if (-not (Test-Command "fluidsynth")) {
    Write-Warning "fluidsynth not on PATH - audio rendering will be unavailable."
}
if (-not (Test-Command "lame")) {
    Write-Warning "lame not on PATH - MP3 conversion will be unavailable."
}

# ── Auto-install ML dependencies if missing ───────────────────────────────
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$mlTrainingDir = Join-Path $RepoRoot "MLtraining"
if (-not (Test-Path $mlTrainingDir)) { New-Item -ItemType Directory -Path $mlTrainingDir -Force | Out-Null }

$venvPip = Join-Path $Backend "venv\Scripts\pip.exe"
$venvPython = Join-Path $Backend "venv\Scripts\python.exe"
if (Test-Path $venvPip) {
    Write-Host "[start.ps1] Checking ML dependencies..." -ForegroundColor Cyan

    & $venvPython -c "import torch" 2>&1 | Out-Null
    $torchOk = ($LASTEXITCODE -eq 0)

    & $venvPython -c "from audiocraft.models import MusicGen" 2>&1 | Out-Null
    $acOk = ($LASTEXITCODE -eq 0)

    if (-not $torchOk) {
        Write-Host "[start.ps1] Installing torch + torchaudio..." -ForegroundColor Yellow
        & $venvPip install torch torchaudio --quiet
    }
    if (-not $acOk) {
        Write-Host "[start.ps1] Installing audiocraft from source..." -ForegroundColor Yellow
        & $venvPip install "git+https://github.com/facebookresearch/audiocraft.git" --quiet
    }
    if ($torchOk -and $acOk) {
        Write-Host "[start.ps1] ML dependencies already installed." -ForegroundColor Green
    }
}
else {
    Write-Warning "Backend venv pip not found -- skipping ML auto-install."
}

# ── Launch backend ─────────────────────────────────────────────────────────
$backendCmd = @"
cd '$Backend'
if (Test-Path 'venv\Scripts\Activate.ps1') { & 'venv\Scripts\Activate.ps1' }
python -m uvicorn src.api:app --host 0.0.0.0 --port $BackendPort --reload
"@

Write-Host "[start.ps1] Starting backend on http://localhost:$BackendPort ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# Small delay so backend is up before frontend hits /health
Start-Sleep -Seconds 2

# ── Launch frontend ────────────────────────────────────────────────────────
$frontendCmd = @"
cd '$Frontend'
npm run dev
"@

Write-Host "[start.ps1] Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host ""
Write-Host "  Backend : http://localhost:$BackendPort/health" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "  Close the two opened PowerShell windows to stop the servers." -ForegroundColor Yellow
