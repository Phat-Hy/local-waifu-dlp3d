# Automated 1-Click CosyVoice Setup Script for Windows (CUDA / RTX GPU)
$ErrorActionPreference = "Stop"

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "   CosyVoice Zero-Shot Voice Cloning 1-Click Setup       " -ForegroundColor Magenta
Write-Host "=========================================================" -ForegroundColor Cyan

$serviceDir = Join-Path $PSScriptRoot "services\cosyvoice"
if (-not (Test-Path $serviceDir)) {
    New-Item -ItemType Directory -Path $serviceDir -Force | Out-Null
}

Set-Location $serviceDir

# 1. Check Python installation
Write-Host "`n[1/4] Checking Python environment..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Error: Python was not found in PATH." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Found Python: $(python --version)" -ForegroundColor Green

# 2. Check NVIDIA GPU
Write-Host "`n[2/4] Checking GPU & CUDA drivers..." -ForegroundColor Yellow
$nvsmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvsmi) {
    & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    Write-Host "✓ NVIDIA GPU detected for real-time zero-shot cloning." -ForegroundColor Green
} else {
    Write-Host "! Warning: nvidia-smi not detected. CPU mode will be used (slower)." -ForegroundColor Yellow
}

# 3. Create or use virtual environment in services/cosyvoice/venv
Write-Host "`n[3/4] Preparing dedicated Python virtual environment for CosyVoice..." -ForegroundColor Yellow
$venvPath = Join-Path $serviceDir "venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment at $venvPath..." -ForegroundColor Cyan
    python -m venv $venvPath
}
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

Write-Host "Installing PyTorch with CUDA 12.4 support..." -ForegroundColor Cyan
& $venvPip install --upgrade pip
& $venvPip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
& $venvPip install fastapi uvicorn modelscope pydantic soundfile

# 4. Clone or install CosyVoice repository if not present
Write-Host "`n[4/4] Setting up CosyVoice repository & downloading pretrained model..." -ForegroundColor Yellow
$cosyRepoDir = Join-Path $serviceDir "CosyVoice"
if (-not (Test-Path $cosyRepoDir)) {
    Write-Host "Cloning official FunAudioLLM/CosyVoice..." -ForegroundColor Cyan
    git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git $cosyRepoDir
}

# Install CosyVoice dependencies
if (Test-Path (Join-Path $cosyRepoDir "requirements.txt")) {
    & $venvPip install -r (Join-Path $cosyRepoDir "requirements.txt")
}

# Download pretrained CosyVoice-300M weights via ModelScope
$pretrainedDir = Join-Path $serviceDir "pretrained_models\CosyVoice-300M"
if (-not (Test-Path $pretrainedDir)) {
    Write-Host "Downloading CosyVoice-300M weights via ModelScope (~2.8GB)..." -ForegroundColor Cyan
    & $venvPython -c "from modelscope import snapshot_download; snapshot_download('iic/CosyVoice-300M', local_dir=r'$pretrainedDir')"
}

Write-Host "`n=========================================================" -ForegroundColor Green
Write-Host "   CosyVoice Setup Complete!                             " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "You can now run .\run.ps1 to start everything with 1 click!" -ForegroundColor Cyan
