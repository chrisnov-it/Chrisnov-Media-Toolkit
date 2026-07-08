# Development Walkthrough

This document summarizes the main changes made during the early beta push for
Chrisnov Media Toolkit.

## 1. Contributor and Project Documentation

- Added `AGENTS.md` as a repository contributor guide.
- Added `ROADMAP.md` to capture beta goals, packaging plans, UI work, and later
  media-tool ideas.
- Updated `README.md` and `CHANGELOG.md` to reflect the new app direction.
- Moved the blog article draft out of this private app repository to:
  `D:\dev\chrisnov-it\BLOG_ARTICLE.md`.

## 2. Rename and Scope Expansion

- Renamed the app from Chrisnov YT Downloader to **Chrisnov Media Toolkit**.
- Updated the window title, AppUserModelID, build output names, spec file, and
  documentation.
- Kept the downloader as the first tab, then expanded the app into a broader
  media toolkit with audio and video conversion workflows.

## 3. Downloader Improvements

- Kept yt-dlp as the download engine.
- Preserved support for single URLs, queues, playlists, audio-only downloads,
  skip-duplicate archives, and title cleanup.
- Migrated archive paths from `~/.config/chrisnov-yt-downloader/` to
  `~/.config/chrisnov-media-toolkit/`.
- Fixed playlist title cleanup by passing concrete playlist output paths from
  yt-dlp metadata to the GUI.
- Added cleanup-on-cancel so completed playlist items are renamed even when a
  large playlist is stopped before all entries finish.

## 4. Audio Converter

- Added a dedicated Audio Converter tab.
- Supported local audio and video input, folder import, batch processing,
  CBR/VBR mode, bitrate selection, sample-rate conversion, EBU R128 loudness
  normalization, peak normalization, trim silence, and title cleanup.
- Added real FFmpeg progress parsing via `ffmpeg -progress`.
- Added graceful cancel by terminating the FFmpeg subprocess instead of relying
  only on abrupt Qt thread termination.
- Fixed Opus conversion for unsupported input sample rates by forcing Opus
  output to a supported rate when needed.

## 5. Video Converter

- Added a dedicated Video Converter tab.
- Supported common video inputs such as mp4, mkv, webm, avi, mov, wmv, flv, ts,
  and m4v.
- Added mp4, mkv, and webm outputs with Keep quality, Balanced, and Smaller
  file presets.
- Added folder import, batch processing, title cleanup, real FFmpeg progress,
  and graceful cancel.
- Added fallback audio transcoding when original audio cannot be copied into the
  selected output container.

## 6. UI Polish

- Restyled the PySide6 UI with a cleaner light interface.
- Added scrollable tabs, better spacing, clearer primary/cancel buttons, and
  expandable queue/file lists.
- Reduced minimum window size and shortened button labels so the app fits better
  on 1366x768 laptop screens.
- Set the window icon more reliably and embedded a Windows executable icon for
  built releases.

## 7. Windows Builds

- Renamed the PyInstaller spec to `chrisnov-media-toolkit.spec`.
- Disabled UPX to reduce antivirus false-positive risk.
- Added build variants:
  - `Lite`: smaller executable, requires FFmpeg on PATH.
  - `Bundled`: includes FFmpeg and FFprobe.
  - `Both`: builds both variants in one run.
- Added PyInstaller support for bundled `bin/ffmpeg.exe` and `bin/ffprobe.exe`.
- Added runtime PATH handling so bundled/local FFmpeg is discoverable by both
  app code and yt-dlp.

## 8. Release and Distribution Notes

- Produced an early Windows x64 beta build and uploaded it to the Cloudflare R2
  custom download domain.
- Kept the repository private while publishing a public-facing article draft
  separately.
- Updated the landing page portfolio entry from Chrisnov YT Downloader to
  Chrisnov Media Toolkit.

## 10. Bug Fixes and Build Pipeline Hardening (v0.1.0-beta.2)

- Fixed build-linux.sh always reporting failure due to wrong output path check.
- Dropped `cipher=block_cipher` from spec to fix builds with PyInstaller 6.x.
- Fixed BUNDLED guard using `not is_macos` (was also true on Linux); now checks
  `sys.platform == 'win32'` explicitly.
- Fixed yt-dlp speed=None crash in download progress hook.
- Fixed mp3 sample rate: removed hardcoded `-ar 44100` from `_codec_args`,
  delegated to `_sample_rate_args` like all other formats.
- Fixed multi-select remove in all three list widgets to iterate in reverse
  order, preventing backing list corruption.
- Fixed cancel race by disconnecting worker signals before `terminate()`.
- Fixed converter clean-title being silently disabled by the downloader checkbox.
- Fixed Retina blurry rendering: `NSHighResolutionCapable` now a proper bool.
- Fixed sha256 files on Linux and macOS embedding a `dist/` path prefix.
- Fixed PowerShell `finally` skip on failed FFmpeg extraction in build-windows.ps1.
- Added `set -o pipefail` to build-linux.sh.
- Added `timeout-minutes: 30` to all three GitHub Actions build jobs.
- Added `BUILD_TYPE: LITE` to Windows workflow job env for consistency.

- Test playlist cleanup and cancel cleanup on real large playlists.
- Rebuild and publish fresh Lite/Bundled binaries after the latest cleanup fixes.
- Add a visible version label and About dialog.
- Add lightweight tests for title cleanup and collision handling.
- Decide whether to keep `test_opus.opus` as a manual fixture or move it into a
  documented `scratch/` or `tests/fixtures/` location.
