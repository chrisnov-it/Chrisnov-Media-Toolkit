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

Write-Host "==> Installing PyInstaller..." -ForegroundColor Cyan
# Pin to a known-good version to avoid CI surprise breakage.
# Bump deliberately after local verification, not automatically.
& "$venv\Scripts\pip.exe" install -q pyinstaller==6.17.0

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
# VERSIONINFO metadata — adds FileVersion / ProductVersion to the .exe
# -----------------------------------------------------------------------------
Write-Host "==> Preparing version_info.txt..." -ForegroundColor Cyan

$appVersion = try {
    # Try reading from app/constants.py
    $match = Select-String -Path 'app\constants.py' -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
    if ($match) { $match.Matches.Groups[1].Value } else { 'dev' }
} catch { 'dev' }

# Environment variable overrides local read (CI use-case)
if ($env:APP_VERSION) {
    $appVersion = $env:APP_VERSION
}

$versionArray = try {
    # Parse semver, allow beta suffix like 0.1.0-beta.2
    if ($appVersion -match '^(\d+)\.(\d+)\.(\d+)') {
        [int]$Matches[1], [int]$Matches[2], [int]$Matches[3], 0
    } else {
        0, 0, 0, 0
    }
} catch { 0, 0, 0, 0 }

$company = 'Chrisnov IT Solutions'
$desc   = 'Desktop toolkit for downloading and converting YouTube media with yt-dlp + FFmpeg'

@"
# See https://pyinstaller.org/en/stable/usage.html#embedding-version-information
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($($versionArray[0]), $($versionArray[1]), $($versionArray[2]), $($versionArray[3])),
    prodvers=($($versionArray[0]), $($versionArray[1]), $($versionArray[2]), $($versionArray[3])),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904b0',  # US English, Unicode
        [
          StringStruct('CompanyName',     '$company'),
          StringStruct('FileDescription', '$desc'),
          StringStruct('FileVersion',     '$appVersion'),
          StringStruct('InternalName',    'ChrisnovMediaToolkit'),
          StringStruct('LegalCopyright',  '© $company'),
          StringStruct('ProductName',     'Chrisnov Media Toolkit'),
          StringStruct('ProductVersion',  '$appVersion'),
        ]
      ),
    ]),
    VarFileInfo([VarStruct('Translation', [0x0409, 0x04b0])]),
  ],
)
"@ | Set-Content -LiteralPath 'version_info.txt' -Encoding UTF8

Write-Host "  version_info.txt written (v$appVersion)" -ForegroundColor Green

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
