# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Chrisnov Media Toolkit
# Build on Linux  : .venv/bin/pyinstaller chrisnov-media-toolkit.spec
# Build on macOS  : .venv/bin/pyinstaller chrisnov-media-toolkit.spec
# Build on Windows: .venv\Scripts\pyinstaller chrisnov-media-toolkit.spec

import os
import sys
from pathlib import Path

build_type = os.environ.get("BUILD_TYPE", "LITE").upper()
is_bundled = build_type == "BUNDLED"
is_macos = sys.platform == "darwin"

if is_bundled and sys.platform == 'win32':
    if not (Path('bin/ffmpeg.exe').exists() and Path('bin/ffprobe.exe').exists()):
        raise FileNotFoundError(
            "ERROR: ffmpeg.exe and ffprobe.exe must be present in the 'bin/' folder "
            "to build the BUNDLED version of the application."
        )

exe_name = "chrisnov-media-toolkit-bundled" if is_bundled else "chrisnov-media-toolkit-lite"
app_icon = (
    'icon.ico' if sys.platform == 'win32' and Path('icon.ico').exists()
    else ('icon.svg' if sys.platform not in ('win32', 'darwin') else None)
)

block_cipher = None  # retained for legacy compat; not used by PyInstaller 6+

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Bundle the SVG icon so it's available at runtime inside the package
        ('icon.svg', '.'),
    ] + ([('bin/ffmpeg.exe', 'bin'), ('bin/ffprobe.exe', 'bin')] if is_bundled and not is_macos else []),
    hiddenimports=[
        # yt-dlp extractor plugins are loaded dynamically — tell PyInstaller about them
        'yt_dlp.extractor',
        'yt_dlp.postprocessor',
        # PySide6 platform plugins
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused Qt modules to reduce binary size
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
        'PySide6.QtMultimedia',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # keep unpacked to reduce antivirus false-positive risk
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no black terminal window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon,
)

if is_macos:
    app = BUNDLE(
        exe,
        name='Chrisnov Media Toolkit.app',
        icon=None,
        bundle_identifier='com.chrisnovit.mediatoolkit',
        info_plist={
            'CFBundleName': 'Chrisnov Media Toolkit',
            'CFBundleDisplayName': 'Chrisnov Media Toolkit',
            'CFBundleShortVersionString': os.environ.get('APP_VERSION', '0.1.0-beta.1'),
            'CFBundleVersion': os.environ.get('APP_BUILD_NUMBER', '1'),
            'NSHighResolutionCapable': True,
        },
    )
