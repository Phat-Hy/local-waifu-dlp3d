# Local AI Waifu Startup Script for Windows PowerShell
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   Starting Local AI Waifu (DLP3D)       " -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Cyan

$serverScript = Join-Path $PSScriptRoot "backend\server.py"

Write-Host "Launching Orchestrator & Viewport at http://127.0.0.1:18002" -ForegroundColor Green
Write-Host "Press Ctrl+C in this window to stop the server.`n" -ForegroundColor Yellow

python -m uvicorn backend.server:app --host 127.0.0.1 --port 18002 --reload
