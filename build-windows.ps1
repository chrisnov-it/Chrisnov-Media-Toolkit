# build-windows.ps1 — build a single-file .exe for Windows
# Run from the project root in PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\build-windows.ps1

$ErrorActionPreference = "Stop"

$venv  = ".venv"
$spec  = "chrisnov-yt-downloader.spec"
$out   = "dist\chrisnov-yt-downloader.exe"

Write-Host "==> Checking venv..." -ForegroundColor Cyan
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "ERROR: .venv not found. Run setup first:" -ForegroundColor Red
    Write-Host "  py -m venv .venv"
    Write-Host "  .venv\Scripts\pip install PySide6 yt-dlp"
    exit 1
}

Write-Host "==> Installing / upgrading PyInstaller..." -ForegroundColor Cyan
& "$venv\Scripts\pip.exe" install -q --upgrade pyinstaller

# Optional: install Pillow so PyInstaller can convert icon.svg -> .ico automatically
# Comment out if you supply a hand-crafted icon.ico instead.
Write-Host "==> Installing Pillow (for icon conversion)..." -ForegroundColor Cyan
& "$venv\Scripts\pip.exe" install -q --upgrade pillow

Write-Host "==> Cleaning previous build..." -ForegroundColor Cyan
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist"  }

Write-Host "==> Running PyInstaller..." -ForegroundColor Cyan
& "$venv\Scripts\pyinstaller.exe" $spec

if (Test-Path $out) {
    $size = (Get-Item $out).Length / 1MB
    Write-Host ""
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "  Output : $out"
    Write-Host ("  Size   : {0:N1} MB" -f $size)
    Write-Host ""
    Write-Host "Test it by double-clicking dist\chrisnov-yt-downloader.exe"
} else {
    Write-Host "ERROR: Build failed — $out not found." -ForegroundColor Red
    exit 1
}
