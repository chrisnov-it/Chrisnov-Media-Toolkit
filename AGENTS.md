# Repository Guidelines

## Project Structure & Module Organization

This is a small Python desktop app built with PySide6, `yt-dlp`, and FFmpeg.

- `main.py` is the application entry point.
- `app/window.py` contains the main GUI and user workflow.
- `app/worker.py` handles threaded downloads with `yt-dlp`.
- `app/converter_worker.py` handles local audio and video conversion.
- `app/cleaner.py` contains filename cleanup helpers.
- `app/constants.py` stores presets, containers, and shared defaults.
- `icon.svg` is the application icon.
- `build-linux.sh`, `build-windows.ps1`, and `chrisnov-media-toolkit.spec` package the app with PyInstaller.

Generated folders such as `.venv/`, `build/`, `dist/`, `__pycache__/`, and `.pytest_cache/` should stay out of commits.

## Build, Test, and Development Commands

Set up a local environment before running the app:

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip PySide6 yt-dlp
.venv/bin/python main.py
```

On Windows:

```powershell
py -m venv .venv
.venv\Scripts\pip install -U pip PySide6 yt-dlp
.venv\Scripts\python main.py
```

Build release binaries with `bash build-linux.sh` on Linux or `.\build-windows.ps1` in PowerShell. On Windows, use `.\build-windows.ps1 -Type Lite`, `-Type Bundled`, or `-Type Both`. PyInstaller must run on the target OS. Lite builds require FFmpeg on the system `PATH`; Bundled builds include `bin/ffmpeg.exe` and `bin/ffprobe.exe`.

## Coding Style & Naming Conventions

Use Python 3 style with 4-space indentation, type hints where practical, and concise docstrings for modules or non-obvious behavior. Follow existing naming: classes use `PascalCase`, functions and attributes use `snake_case`, and GUI-only helper methods commonly use a leading underscore. Keep worker logic outside the GUI thread by using `QThread` patterns already present in `DownloadWorker`, `ConvertWorker`, and `VideoConvertWorker`.

## Testing Guidelines

There is no committed automated test suite yet. For changes, run the app locally and smoke-test the affected workflow: queue a URL, start/cancel a download, test playlist clean-title behavior, test audio-only mode, and test audio/video converter drag-and-drop when relevant. If adding tests, prefer `pytest`, place tests under `tests/`, and name files `test_*.py`.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries, for example `Add converter tab, fix bugs, expand clean title tags`. Keep commit subjects direct and user-visible when possible. Pull requests should include a brief change summary, manual test steps, affected platforms, and screenshots or short recordings for GUI changes.

## Security & Configuration Tips

Do not commit downloaded media, archives, virtual environments, or build outputs. `test_opus.opus` is a local reference sample and should remain untracked unless explicitly requested. Treat user-selected paths and downloaded filenames carefully; keep cleanup and rename behavior conservative. Avoid broad network or filesystem changes outside the selected output folder.
