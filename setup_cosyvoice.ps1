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
Write-Host ""
Write-Host "[1/4] Checking Python environment..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Error: Python was not found in PATH." -ForegroundColor Red
    exit 1
}
$pyVer = python --version
Write-Host "Found Python: $pyVer" -ForegroundColor Green

# 2. Check NVIDIA GPU
Write-Host ""
Write-Host "[2/4] Checking GPU and CUDA drivers..." -ForegroundColor Yellow
$nvsmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvsmi) {
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    Write-Host "NVIDIA GPU detected for real-time zero-shot cloning." -ForegroundColor Green
} else {
    Write-Host "Warning: nvidia-smi not detected. CPU mode will be used." -ForegroundColor Yellow
}

# 3. Create or use virtual environment in services/cosyvoice/venv
Write-Host ""
Write-Host "[3/4] Preparing dedicated Python virtual environment for CosyVoice..." -ForegroundColor Yellow
$venvPath = Join-Path $serviceDir "venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment at $venvPath..." -ForegroundColor Cyan
    python -m venv $venvPath
}
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

Write-Host "Turbo-charging package downloads with UV multi-threaded installer..." -ForegroundColor Cyan
python -m uv pip install --python "$venvPython" torch torchaudio --index-url https://download.pytorch.org/whl/cu124
python -m uv pip install --python "$venvPython" fastapi uvicorn modelscope "huggingface_hub[hf_transfer]" pydantic soundfile

# 4. Clone or install CosyVoice repository if not present
Write-Host ""
Write-Host "[4/4] Setting up CosyVoice repository and downloading pretrained model..." -ForegroundColor Yellow
$cosyRepoDir = Join-Path $serviceDir "CosyVoice"
if (-not (Test-Path $cosyRepoDir)) {
    Write-Host "Cloning official FunAudioLLM/CosyVoice..." -ForegroundColor Cyan
    git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git $cosyRepoDir
}

# Install CosyVoice dependencies
$cosyReqs = Join-Path $cosyRepoDir "requirements.txt"
if (Test-Path $cosyReqs) {
    Write-Host "Installing repository dependencies via UV..." -ForegroundColor Cyan
    python -m uv pip install --python "$venvPython" setuptools wheel
    python -m uv pip install --python "$venvPython" -r $cosyReqs --index-strategy unsafe-best-match --no-build-isolation
}

# Download pretrained CosyVoice-300M weights via ModelScope / HuggingFace
$pretrainedDir = Join-Path $serviceDir "pretrained_models\CosyVoice-300M"
$flowFile = Join-Path $pretrainedDir "flow.pt"
$hiftFile = Join-Path $pretrainedDir "hift.pt"
if (-not (Test-Path $flowFile) -or -not (Test-Path $hiftFile)) {
    Write-Host "Downloading CosyVoice-300M weights (~2.8GB)..." -ForegroundColor Cyan
    $env:HF_HUB_ENABLE_HF_TRANSFER = "1"
    & "$venvPython" -c "try:
    from huggingface_hub import snapshot_download
    print('Downloading via HuggingFace Cloudflare CDN (multi-threaded)...')
    snapshot_download(repo_id='FunAudioLLM/CosyVoice-300M', local_dir=r'$pretrainedDir')
except Exception as e:
    print('HuggingFace notice:', e, 'Falling back to ModelScope...')
    from modelscope import snapshot_download
    snapshot_download('iic/CosyVoice-300M', local_dir=r'$pretrainedDir')
"
}

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "   CosyVoice Setup Complete!                             " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "You can now run .\run.bat or .\run.ps1 to start everything with 1 click!" -ForegroundColor Cyan
