# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Chrisnov Media Toolkit
# Build on Linux  : .venv/bin/pyinstaller chrisnov-media-toolkit.spec
# Build on Windows: .venv\Scripts\pyinstaller chrisnov-media-toolkit.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Bundle the SVG icon so it's available at runtime inside the package
        ('icon.svg', '.'),
    ],
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
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='chrisnov-media-toolkit',
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
    icon='icon.ico' if sys.platform == 'win32' and Path('icon.ico').exists()
    else ('icon.svg' if sys.platform != 'win32' else None),
)
