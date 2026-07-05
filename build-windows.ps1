# build-windows.ps1 — build a single-file .exe for Windows
# Run from the project root in PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\build-windows.ps1

$ErrorActionPreference = "Stop"

$venv  = ".venv"
$spec  = "chrisnov-media-toolkit.spec"
$out   = "dist\chrisnov-media-toolkit.exe"
$icon  = "icon.ico"

Write-Host "==> Checking venv..." -ForegroundColor Cyan
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "ERROR: .venv not found. Run setup first:" -ForegroundColor Red
    Write-Host "  py -m venv .venv"
    Write-Host "  .venv\Scripts\pip install PySide6 yt-dlp"
    exit 1
}

Write-Host "==> Installing / upgrading PyInstaller..." -ForegroundColor Cyan
& "$venv\Scripts\pip.exe" install -q --upgrade pyinstaller

if ((Test-Path "icon.svg") -and -not (Test-Path $icon)) {
    Write-Host "==> Creating Windows icon..." -ForegroundColor Cyan
    $oldQtPlatform = $env:QT_QPA_PLATFORM
    $env:QT_QPA_PLATFORM = "offscreen"
    $iconScript = @'
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication(sys.argv)
renderer = QSvgRenderer("icon.svg")
image = QImage(256, 256, QImage.Format_ARGB32)
image.fill(Qt.transparent)
painter = QPainter(image)
renderer.render(painter)
painter.end()
if not image.save("icon.ico", "ICO"):
    raise SystemExit("Failed to save icon.ico")
'@
    try {
        $iconScript | & "$venv\Scripts\python.exe" -
    } finally {
        $env:QT_QPA_PLATFORM = $oldQtPlatform
    }
}

if (-not (Test-Path $icon)) {
    Write-Host "==> icon.ico not found; Windows executable will use the default icon." -ForegroundColor Yellow
}

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
    Write-Host "Test it by double-clicking $out"
} else {
    Write-Host "ERROR: Build failed — $out not found." -ForegroundColor Red
    exit 1
}
