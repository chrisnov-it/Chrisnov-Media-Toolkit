#!/usr/bin/env bash
# build-linux.sh — build a single-file executable for Linux
# Run from the project root: bash build-linux.sh

set -e

VENV=".venv"
SPEC="chrisnov-yt-downloader.spec"
OUT="dist/chrisnov-yt-downloader"

echo "==> Checking venv..."
if [ ! -d "$VENV" ]; then
    echo "ERROR: .venv not found. Run setup first:"
    echo "  python3 -m venv .venv && .venv/bin/pip install PySide6 yt-dlp"
    exit 1
fi

echo "==> Installing / upgrading PyInstaller..."
"$VENV/bin/pip" install -q --upgrade pyinstaller

echo "==> Cleaning previous build..."
rm -rf build/ dist/

echo "==> Running PyInstaller..."
"$VENV/bin/pyinstaller" "$SPEC"

if [ -f "$OUT" ]; then
    echo ""
    echo "✓ Build successful!"
    echo "  Output : $OUT"
    echo "  Size   : $(du -sh "$OUT" | cut -f1)"
    echo ""
    echo "Test it with:"
    echo "  $OUT"
else
    echo "ERROR: Build failed — $OUT not found."
    exit 1
fi
