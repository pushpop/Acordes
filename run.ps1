# Acordes launcher for Windows (PowerShell)
# Uses uv to manage Python versions and dependencies.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PinFile = Join-Path $ScriptDir ".python-version"
$VenvDir = Join-Path $ScriptDir ".venv"

# Check uv is installed
$uvCmd = Get-Command "uv" -ErrorAction SilentlyContinue
if ($uvCmd -eq $null) {
    Write-Host ""
    Write-Host " ERROR: uv is not installed." -ForegroundColor Red
    Write-Host ""
    Write-Host " Install via PowerShell:"
    Write-Host "   powershell -ExecutionPolicy BypassUser -c 'irm https://astral.sh/uv/install.ps1 | iex'"
    Write-Host ""
    Write-Host " Full instructions: https://docs.astral.sh/uv/getting-started/installation/"
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Pin Python version if not already done
$needsSetup = $false
if (-not (Test-Path $PinFile)) {
    $needsSetup = $true
    Write-Host " First run - setting up Acordes..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host " Pinning Python 3.12..."

    & uv python pin 3.12 2>$null
    if ($LASTEXITCODE -ne 0) {
        & uv python pin 3.11 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host " ERROR: Neither Python 3.12 nor 3.11 could be pinned." -ForegroundColor Red
            Write-Host " Install Python via uv: uv python install 3.12"
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 1
        }
        Write-Host " Pinned Python 3.11"
    }
    else {
        Write-Host " Pinned Python 3.12"
    }
    Write-Host ""
}

# Install dependencies if .venv is missing
if (-not (Test-Path $VenvDir)) {
    if (-not $needsSetup) {
        Write-Host " First run - setting up Acordes..." -ForegroundColor Cyan
        Write-Host ""
    }
    Write-Host " Installing dependencies (this may take a minute)..."

    & uv sync --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host " ERROR: Dependency installation failed." -ForegroundColor Red
        Write-Host " Common fixes:"
        Write-Host "   1. Install Python: uv python install 3.12"
        Write-Host "   2. PyAudio issues: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host " Done." -ForegroundColor Green
    Write-Host ""
}
else {
    & uv sync --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host " ERROR: Dependency sync failed. Run 'uv sync' for details." -ForegroundColor Red
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── Install ASIO-enabled PortAudio DLL if provided ────────────────────────────
# If portaudio-asio\libportaudio64bit.dll exists in the project folder, copy it
# into the sounddevice package so ASIO backends (Steinberg, ASIO4ALL, etc.) appear
# in the config screen. Safe no-op if the file is absent.
$AsioDll    = Join-Path $ScriptDir "portaudio-asio\libportaudio64bit.dll"
$SdDataDir  = Join-Path $VenvDir "Lib\site-packages\_sounddevice_data\portaudio-binaries"
$TargetDll  = Join-Path $SdDataDir "libportaudio64bit.dll"
$BackupDll  = Join-Path $SdDataDir "libportaudio64bit.dll.bak"

if (Test-Path $AsioDll) {
    if (Test-Path $SdDataDir) {
        # Back up the original DLL once so the user can restore it if needed
        if ((Test-Path $TargetDll) -and -not (Test-Path $BackupDll)) {
            Copy-Item $TargetDll $BackupDll -Force
        }
        # Only copy if the ASIO DLL differs from what is already in place
        $asioHash   = (Get-FileHash $AsioDll   -Algorithm MD5).Hash
        $targetHash = if (Test-Path $TargetDll) { (Get-FileHash $TargetDll -Algorithm MD5).Hash } else { "" }
        if ($asioHash -ne $targetHash) {
            Copy-Item $AsioDll $TargetDll -Force
            Write-Host " ASIO PortAudio DLL installed." -ForegroundColor Cyan
        }
    }
}

# Launch Acordes
& uv run python (Join-Path $ScriptDir "main.py")
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host " Acordes exited with error (code $exitCode)." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit $exitCode
}
