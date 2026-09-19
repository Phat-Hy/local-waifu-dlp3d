# Local AI Waifu 1-Click Startup Script for Windows PowerShell
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   Starting Local AI Waifu (1-Click Run) " -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Cyan

$f5Script = Join-Path $PSScriptRoot "services\f5-tts\server.py"
$f5VenvPy = Join-Path $PSScriptRoot "services\f5-tts\venv\Scripts\python.exe"
$f5Proc = $null

$cosyScript = Join-Path $PSScriptRoot "services\cosyvoice\server.py"
$cosyVenvPy = Join-Path $PSScriptRoot "services\cosyvoice\venv\Scripts\python.exe"
$cosyProc = $null

# 1. Check & Auto-Launch F5-TTS Engine (Port 50001 - Default Ultra-Fast Engine)
$f5PortActive = Get-NetTCPConnection -LocalPort 50001 -ErrorAction SilentlyContinue
if (-not $f5PortActive -and (Test-Path $f5Script)) {
    $f5Python = if (Test-Path $f5VenvPy) { $f5VenvPy } else { "python" }
    Write-Host "[1/3] Launching F5-TTS Ultra-Fast Engine on port 50001..." -ForegroundColor Cyan
    $f5Proc = Start-Process -FilePath $f5Python -ArgumentList "`"$f5Script`"" -PassThru -NoNewWindow
    Start-Sleep -Seconds 2
} elseif ($f5PortActive) {
    Write-Host "[1/3] F5-TTS Engine is already running on port 50001." -ForegroundColor Green
}

# 2. Check & Auto-Launch CosyVoice Zero-Shot Engine (Port 50000 - Alternative)
$cosyPortActive = Get-NetTCPConnection -LocalPort 50000 -ErrorAction SilentlyContinue
if (-not $cosyPortActive -and (Test-Path $cosyScript) -and (Get-Content (Join-Path $PSScriptRoot "config.json") -Raw | Select-String '"cosyvoice"')) {
    $cosyPython = if (Test-Path $cosyVenvPy) { $cosyVenvPy } else { "python" }
    Write-Host "[2/3] Launching CosyVoice Zero-Shot Engine on port 50000..." -ForegroundColor Yellow
    $cosyProc = Start-Process -FilePath $cosyPython -ArgumentList "`"$cosyScript`"" -PassThru -NoNewWindow
    Start-Sleep -Seconds 2
} elseif ($cosyPortActive) {
    Write-Host "[2/3] CosyVoice Engine is already running on port 50000." -ForegroundColor Green
}

# 3. Launch Main Waifu Orchestrator & 3D Viewport (Port 18002)
Write-Host "[3/3] Launching Orchestrator & Viewport at http://127.0.0.1:18002" -ForegroundColor Green
Write-Host "Press Ctrl+C in this window to stop all services.`n" -ForegroundColor Yellow

try {
    python -m uvicorn backend.server:app --host 127.0.0.1 --port 18002
} finally {
    if ($f5Proc -and -not $f5Proc.HasExited) {
        Write-Host "`nStopping F5-TTS background process..." -ForegroundColor Cyan
        Stop-Process -Id $f5Proc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($cosyProc -and -not $cosyProc.HasExited) {
        Write-Host "`nStopping CosyVoice background process..." -ForegroundColor Cyan
        Stop-Process -Id $cosyProc.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "AI Waifu services stopped." -ForegroundColor Yellow
}
