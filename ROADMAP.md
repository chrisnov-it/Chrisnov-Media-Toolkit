# Roadmap

Chrisnov Media Toolkit is currently in early internal beta. The app is already
usable for downloading media and converting local audio/video, but the next
milestones should focus on reliability, usability, and packaging quality before
sharing it more broadly.

## Current Beta Scope

- Downloader for yt-dlp-supported URLs.
- Audio-only downloads with bitrate/container selection.
- Batch queue, playlist support, duplicate skip archive, and title cleanup.
- Playlist title cleanup for completed downloads and completed files left after
  Cancel.
- Audio Converter with Add files, Add folder, normalization, trim silence, and
  batch processing.
- Video Converter with mp4/mkv/webm output, quality presets, folder import,
  FFmpeg progress, and graceful cancel.
- Windows single-file builds:
  - Lite: requires system FFmpeg.
  - Bundled: includes FFmpeg/FFprobe.
- macOS Lite build workflow via GitHub Actions:
  - Builds a native unsigned `.app` on a macOS runner.
  - Packages the app as a ZIP artifact for internal beta testing.

## Short-Term Priorities

- Test the Windows beta build on multiple Windows 11 machines.
- Test Linux Mint from source, then produce a Linux binary from Linux.
- Run the macOS GitHub Actions build and validate the ZIP on a real Mac.
- Verify taskbar/window icon behavior across source run and built `.exe`.
- Smoke-test download, audio-only, Audio Converter, Video Converter, Add Folder,
  Cancel, and title cleanup on real-world files.
- Add a visible version label in the app, for example `v0.1.0-beta.1`.
- Add a simple About dialog with app name, version, build platform, and credits.

## UI & Usability

- Continue polishing tab layouts for non-technical users.
- Improve responsive behavior when maximized on large screens.
- Add clearer empty states for queues and converter file lists.
- Add status summaries after batch completion, including failed/skipped counts.
- Consider separate "Output" presets for common use cases:
  - Music collection
  - Phone-friendly video
  - Small file / sharing
  - Archive quality

## Media Tools

- Add video compression presets with clearer labels: Small, Balanced, High
  quality.
- Add trim/cut support for audio and video using start/end time fields.
- Add audio extraction as a dedicated workflow if users find it clearer than
  using Audio Converter with video input.
- Add filename cleanup for local files without conversion.
- Consider recursive folder import options: current folder only vs include
  subfolders.

## Reliability & Testing

- Add lightweight automated tests for filename cleanup and path collision logic.
- Add manual release checklist for Windows and Linux.
- Improve cancellation for downloader workers if yt-dlp exposes a safer stop
  path than thread termination.
- Keep builds unpacked by default; avoid UPX unless a specific distribution
  need justifies the antivirus false-positive risk.

## Packaging & Release

- Keep release filenames explicit:
  `chrisnov-media-toolkit-vX.Y.Z-beta.N-windows-x64.exe`.
- Add SHA256 checksums beside release builds.
- Maintain two Windows release variants:
  - **Lite**: smaller binary, requires FFmpeg installed separately.
  - **Bundled**: includes `ffmpeg.exe` and `ffprobe.exe` for non-technical
    users who want the app to work without extra setup.
- Maintain a macOS Lite artifact from `.github/workflows/build-macos.yml`.
  This artifact is unsigned and intended for internal testers first.
- Consider creating GitHub Releases once beta builds are shared outside internal
  testing.
- Later, investigate installer packaging, Start Menu shortcuts, and code signing
  for better Windows trust signals.

## macOS Packaging Plan

- Build macOS artifacts on GitHub Actions or a real Mac; do not build macOS
  binaries from Windows or Linux.
- Start with Lite ZIP releases that require users to install FFmpeg separately,
  usually via Homebrew.
- Treat the first macOS ZIPs as unsigned beta builds. Users may need to use
  right-click > Open or approve the app in macOS security settings.
- Add macOS FFmpeg bundling only after validating the Lite build, selecting a
  reputable FFmpeg binary, and documenting third-party licenses.
- Consider Apple Developer ID signing and notarization before sharing macOS
  builds broadly.

## FFmpeg Bundling Status

- Keep Lite/non-bundled as the baseline for technical users.
- `build-windows.ps1` supports `-Type Lite`, `-Type Bundled`, and `-Type Both`.
- Bundled builds include `bin/ffmpeg.exe` and `bin/ffprobe.exe`.
- `find_ffmpeg()` and `find_ffprobe()` check PyInstaller runtime extraction
  paths such as `sys._MEIPASS / "bin"` before falling back to local `bin/` and
  PATH.
- Keep UPX disabled for both variants to reduce antivirus false-positive risk.
- Expect bundled Windows builds to be much larger, likely 100-300+ MB depending
  on the FFmpeg build used.
- Prefer a reputable minimal FFmpeg build over UPX compression if size becomes
  a concern.

## Later Ideas

- Download history view with quick open-folder actions.
- Per-site notes or presets if yt-dlp behavior differs across platforms.
- Queue import/export as text.
- Optional dark theme once the light UI is stable.
- Local-only settings file for remembering preferred folders, formats, and
  quality presets.
