# Roadmap

Chrisnov Media Toolkit is currently in early internal beta. The app is already
usable for downloading media and converting local audio/video, but the next
milestones should focus on reliability, usability, and packaging quality before
sharing it more broadly.

## Current Beta Scope

- Downloader for yt-dlp-supported URLs.
- Audio-only downloads with bitrate/container selection.
- Batch queue, playlist support, duplicate skip archive, and title cleanup.
- Audio Converter with Add files, Add folder, normalization, trim silence, and
  batch processing.
- Video Converter with mp4/mkv/webm output, quality presets, folder import,
  FFmpeg progress, and graceful cancel.
- Windows single-file build: `v0.1.0-beta.1-windows-x64`.

## Short-Term Priorities

- Test the Windows beta build on multiple Windows 11 machines.
- Test Linux Mint from source, then produce a Linux binary from Linux.
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
- Consider creating GitHub Releases once beta builds are shared outside internal
  testing.
- Later, investigate installer packaging, Start Menu shortcuts, and code signing
  for better Windows trust signals.

## Later Ideas

- Download history view with quick open-folder actions.
- Per-site notes or presets if yt-dlp behavior differs across platforms.
- Queue import/export as text.
- Optional dark theme once the light UI is stable.
- Local-only settings file for remembering preferred folders, formats, and
  quality presets.
