#!/usr/bin/env bash
# build-linux.sh — build a single-file executable for Linux
# Run from the project root: bash build-linux.sh

set -e
set -o pipefail

VENV=".venv"
SPEC="chrisnov-media-toolkit.spec"
OUT="dist/chrisnov-media-toolkit-lite"

echo "==> Checking venv..."
if [ ! -d "$VENV" ]; then
    echo "ERROR: .venv not found. Run setup first:"
    echo "  python3 -m venv .venv && .venv/bin/pip install PySide6 yt-dlp"
    exit 1
fi

echo "==> Installing PyInstaller..."
# Pin to a known-good version to avoid CI surprise breakage.
# Bump deliberately after local verification, not automatically.
"$VENV/bin/pip" install -q pyinstaller==6.17.0

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
