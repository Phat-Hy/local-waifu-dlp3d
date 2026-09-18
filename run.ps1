# Local AI Waifu 1-Click Startup Script for Windows PowerShell
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   Starting Local AI Waifu (1-Click Run) " -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Cyan

$cosyScript = Join-Path $PSScriptRoot "services\cosyvoice\server.py"
$cosyVenvPy = Join-Path $PSScriptRoot "services\cosyvoice\venv\Scripts\python.exe"
$cosyProc = $null

# 1. Check & Auto-Launch CosyVoice Zero-Shot Engine (Port 50000)
$cosyPortActive = Get-NetTCPConnection -LocalPort 50000 -ErrorAction SilentlyContinue
if (-not $cosyPortActive -and (Test-Path $cosyScript)) {
    $cosyPython = if (Test-Path $cosyVenvPy) { $cosyVenvPy } else { "python" }
    Write-Host "[1/2] Launching CosyVoice Zero-Shot Engine on port 50000..." -ForegroundColor Yellow
    $cosyProc = Start-Process -FilePath $cosyPython -ArgumentList "`"$cosyScript`"" -PassThru -NoNewWindow
    Start-Sleep -Seconds 2
} elseif ($cosyPortActive) {
    Write-Host "[1/2] CosyVoice Engine is already running on port 50000." -ForegroundColor Green
} else {
    Write-Host "[1/2] CosyVoice server script not found. Using Edge-TTS neural speech." -ForegroundColor DarkGray
}

# 2. Launch Main Waifu Orchestrator & 3D Viewport (Port 18002)
Write-Host "[2/2] Launching Orchestrator & Viewport at http://127.0.0.1:18002" -ForegroundColor Green
Write-Host "Press Ctrl+C in this window to stop both services.`n" -ForegroundColor Yellow

try {
    python -m uvicorn backend.server:app --host 127.0.0.1 --port 18002
} finally {
    if ($cosyProc -and -not $cosyProc.HasExited) {
        Write-Host "`nStopping CosyVoice background process..." -ForegroundColor Cyan
        Stop-Process -Id $cosyProc.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "AI Waifu services stopped." -ForegroundColor Yellow
}
