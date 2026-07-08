# build-windows.ps1 - build a single-file .exe for Windows
# Run from the project root in PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\build-windows.ps1 -Type Both

param (
    [ValidateSet("Lite", "Bundled", "Both")]
    [string]$Type = "Both"
)

$ErrorActionPreference = "Stop"

$venv   = ".venv"
$spec   = "chrisnov-media-toolkit.spec"
$icon   = "icon.ico"
$binDir = "bin"

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

# -----------------------------------------------------------------------------
# FFmpeg Bundling Downloader
# -----------------------------------------------------------------------------
if ($Type -eq "Bundled" -or $Type -eq "Both") {
    if (-not (Test-Path "$binDir\ffmpeg.exe") -or -not (Test-Path "$binDir\ffprobe.exe")) {
        Write-Host "==> Bundling FFmpeg: Binaries not found in '$binDir'." -ForegroundColor Cyan
        if (-not (Test-Path $binDir)) {
            $null = New-Item -ItemType Directory -Path $binDir
        }
        
        # Check if FFmpeg is installed on the system PATH first
        Write-Host "Searching for system-installed FFmpeg and FFprobe..." -ForegroundColor Yellow
        $sysFfmpeg = Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue
        $sysFfprobe = Get-Command "ffprobe.exe" -ErrorAction SilentlyContinue
        
        if ($sysFfmpeg -and $sysFfprobe) {
            Write-Host "Found system FFmpeg at '$($sysFfmpeg.Source)' and FFprobe at '$($sysFfprobe.Source)'." -ForegroundColor Green
            Write-Host "Copying system binaries to '$binDir' to bypass download..." -ForegroundColor Yellow
            Copy-Item -Path $sysFfmpeg.Source -Destination "$binDir\ffmpeg.exe" -Force
            Copy-Item -Path $sysFfprobe.Source -Destination "$binDir\ffprobe.exe" -Force
            Write-Host "Successfully copied FFmpeg and FFprobe to '$binDir'." -ForegroundColor Green
        } else {
            # Fallback to downloading if system binaries are not found
            Write-Host "System FFmpeg/FFprobe not found. Attempting to download from yt-dlp/FFmpeg-Builds..." -ForegroundColor Yellow
            $zipUrl = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            $zipFile = "$binDir\ffmpeg.zip"
            $extractDir = "$binDir\extract"
            
            try {
                Write-Host "Downloading $zipUrl..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile
                
                Write-Host "Extracting archive..." -ForegroundColor Yellow
                if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
                Expand-Archive -Path $zipFile -DestinationPath $extractDir
                
                $extractedFfmpeg = Get-ChildItem -Path $extractDir -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
                $extractedFfprobe = Get-ChildItem -Path $extractDir -Filter "ffprobe.exe" -Recurse | Select-Object -First 1
                
                if ($extractedFfmpeg -and $extractedFfprobe) {
                    Move-Item -Path $extractedFfmpeg.FullName -Destination "$binDir\ffmpeg.exe" -Force
                    Move-Item -Path $extractedFfprobe.FullName -Destination "$binDir\ffprobe.exe" -Force
                    Write-Host "FFmpeg and FFprobe successfully downloaded and placed in '$binDir'." -ForegroundColor Green
                } else {
                    throw "Could not find ffmpeg.exe or ffprobe.exe in the extracted archive."
                }
            } catch {
                Write-Host "ERROR: Failed to obtain FFmpeg. Ensure you are connected to the internet or install FFmpeg on your system." -ForegroundColor Red
                throw $_
            } finally {
                if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
                if (Test-Path $zipFile) { Remove-Item -Force $zipFile }
            }
        }
    } else {
        Write-Host "==> Bundling FFmpeg: Found existing ffmpeg.exe and ffprobe.exe in '$binDir'." -ForegroundColor Cyan
    }
}

# -----------------------------------------------------------------------------
# Clean previous build directories
# -----------------------------------------------------------------------------
Write-Host "==> Cleaning previous build directories..." -ForegroundColor Cyan
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist"  }

# -----------------------------------------------------------------------------
# Run PyInstaller Builds
# -----------------------------------------------------------------------------
$targets = @()
if ($Type -eq "Lite" -or $Type -eq "Both") { $targets += "LITE" }
if ($Type -eq "Bundled" -or $Type -eq "Both") { $targets += "BUNDLED" }

foreach ($target in $targets) {
    Write-Host "==> Running PyInstaller for $target build..." -ForegroundColor Cyan
    $env:BUILD_TYPE = $target
    
    # We clean the temporary "build" folder between compilations to prevent caching conflicts,
    # but we preserve the "dist" folder.
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    
    & "$venv\Scripts\pyinstaller.exe" $spec
    
    $outName = if ($target -eq "BUNDLED") { "chrisnov-media-toolkit-bundled.exe" } else { "chrisnov-media-toolkit-lite.exe" }
    $outPath = "dist\$outName"
    
    if (Test-Path $outPath) {
        $size = (Get-Item $outPath).Length / 1MB
        $sizeStr = "{0:N1}" -f $size
        Write-Host "Build Successful: $outPath ($sizeStr MB)" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host "ERROR: Build failed for $target - $outPath not found." -ForegroundColor Red
        exit 1
    }
}

Write-Host "==> All builds completed successfully!" -ForegroundColor Green
