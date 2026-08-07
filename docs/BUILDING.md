# Building & Architecture

This document covers building standalone executables, the project layout, and the internal architecture. End-user install instructions are in the [main README](../README.md).

## Building a standalone executable

Produces a single self-contained binary — end users don't need Python.

> **Cross‑compile limitation:** PyInstaller must run on the **target OS**. Build the Linux binary on Linux, and the Windows `.exe` on Windows. If you dual‑boot, run the matching script on each OS.

### Linux
```bash
bash build-linux.sh
# Output: dist/chrisnov-media-toolkit
```

### Windows
```powershell
# In PowerShell from the project root:
Set-ExecutionPolicy -Scope Process Bypass
.\build-windows.ps1
# Outputs: dist\chrisnov-media-toolkit-vX.Y.Z-windows-x64-lite.zip
#          dist\chrisnov-media-toolkit-vX.Y.Z-windows-x64-bundled.zip
```
Each `.zip` contains the standalone `.exe`. For a custom Windows icon, place `icon.ico` in the project root before building; without it the `.exe` uses the default icon (the in‑app window still uses `icon.svg`).

### macOS
Prebuilt `.zip`s are produced by `.github/workflows/build-macos.yml` and attached to GitHub Releases for both Apple Silicon (`-macos-arm64-lite.zip`) and Intel (`-macos-x86_64-lite.zip`). The CI pins a macOS deployment target of 12.0 so Intel builds run on older Macs (e.g. 2015 MacBook Air). See [`OLD-MAC-WORKAROUND.md`](OLD-MAC-WORKAROUND.md) for Intel‑Mac specifics and SHA256 verification.

> **File size:** ~50–90 MB is normal — it bundles Python, PySide6, and yt-dlp. UPX is avoided because packed executables can trigger antivirus false positives.

## Project layout
```
Chrisnov-Media-Toolkit/
├── main.py               # entry point
├── icon.svg              # app icon (SVG)
├── app/
│   ├── constants.py      # APP_VERSION, presets, container lists, thresholds
│   ├── cleaner.py        # clean_title, rename_with_cleanup, discover_new_files
│   ├── base_worker.py    # CancellableWorker — shared QThread base with cancel()
│   ├── yt_dlp_opts.py    # Shared yt-dlp option builders (cookies, format, dry-run)
│   ├── ffmpeg_utils.py   # FFmpeg binary discovery, probing, progress-aware execution
│   ├── worker.py         # DownloadWorker, PlaylistInspectWorker, FileSizeWorker
│   ├── converter_worker.py # ConvertWorker, VideoConvertWorker (FFmpeg-based)
│   ├── window.py         # MainWindow (GUI)
│   └── icon.py           # load_svg_icon helper
└── .venv/                # Python venv with PySide6 + yt-dlp
```

## Shared utilities (extracted to reduce duplication)
- **`base_worker.py`** — `CancellableWorker` provides the `_cancelled` flag, `cancel()`, and `cancelled` property. All 5 worker classes inherit from it; converter workers override `cancel()` to also terminate their FFmpeg subprocess.
- **`yt_dlp_opts.py`** — centralizes yt-dlp options: `build_cookie_opts()` (cookie + impersonation), `build_format_opts()` (format/outtmpl/postprocessors), `build_dry_opts()` (metadata‑only), `_thumbnail_supported()` / `_extra_postprocessors()`.
- **`ffmpeg_utils.py`** — centralizes FFmpeg ops: `find_ffmpeg()`/`find_ffprobe()` (PyInstaller → local → PATH), `probe_duration()`/`probe_loudness()`, `resolve_output_path()`, `run_ffmpeg_with_progress()` (progress parsing, cancellation, range mapping).

## Architecture
GUI runs in the main thread; downloads happen in `DownloadWorker` (a `QThread`) so the UI stays responsive. The worker uses yt-dlp's Python API directly (`YoutubeDL.extract_info(download=True)`), passing `download_archive` for de‑duplication, `progress_hooks` for live status, `impersonate` for browser mimicry, and cookie options for authenticated content. After each download, `MainWindow._on_item_ok` applies title cleanup on disk. Local conversion uses FFmpeg via `ConvertWorker`/`VideoConvertWorker`, which parse `ffmpeg -progress` for live progress and terminate the FFmpeg subprocess on Cancel. Playlists >50 entries trigger a dry `extract_info` count and a confirmation dialog.

## Notes
- Skip‑duplicates archive: `~/.config/chrisnov-media-toolkit/archive_audio.txt` (or `archive_video.txt`). Delete these to re‑download from scratch.
- Download history: `~/.config/chrisnov-media-toolkit/download-history.json` (capped at 1,000 entries).
- `curl_cffi` is required for browser impersonation: `pip install curl_cffi`.
- yt-dlp is bundled via the venv; a system yt-dlp isn't required.
- App icon: `icon.svg` in the project root (any valid SVG). On Windows 11 the taskbar uses it automatically.
