# Changelog

## v1.0.0 (2026-07-04)

Initial release — Chrisnov YT Downloader.

### Added

- **Minimal PySide6 GUI** around yt-dlp. Paste a YouTube URL (or
  any yt-dlp-supported site) and download.
- **Audio-only mode** with selectable bitrate (96/128/160/192/256/320 kbps).
  Container choice: mp3 / m4a / opus.
- **Resolution presets:** Best (no limit) / 1080p / 720p / 480p / 360p.
  Video containers: mp4 / mkv / webm (auto‑merge via ffmpeg).
- **Title cleanup checkbox** — strips "Official Music Video", "Official Video",
  "Official Lyrics Video", "Music Video", "Lyric Video", "Lyrics Video",
  "Official Audio", "Audio", "Topic" from filenames.
    - Handles bare words, `[bracketed]`, `(parenthesised)`, dash/pipe separators.
    - Editable tag list (comma‑separated) in the GUI.
    - Runs after download; status bar shows `"Cleaned N file(s), ..."` when
      active.
- **Batch queue** — add URLs one by one or drop a text file. Queue runs
  sequentially. Remove selected / Clear buttons.
- **Playlist support** — auto‑detected via `&list=` or `?list=` in the URL.
  Uses yt-dlp's playlist expansion. Large playlists (≥50 entries) run a dry
  fetch to count and show a confirmation dialog with estimated size.
- **Skip duplicates** — yt‑dlp `download_archive` stores a history of downloaded
  IDs at `~/.config/chrisnov-yt-downloader/archive_audio.txt` (or
  `archive_video.txt`). Re‑queuing a previously downloaded entry skips it
  automatically. Delete the archive file to re‑download from scratch.
- **Drag‑and‑drop** — drop a URL (plain text), a browser link, or a `.txt` file
  of URLs onto the window.
- **Cancel mid‑batch** — terminates the current worker; queue state is
  preserved.
- **App icon** — custom SVG icon (`icon.svg`). Rendered to QIcon via
  QSvgRenderer + QPixmap for consistent display on Linux and Windows.
  Windows taskbar icon set via AppUserModelID.
- **Modular project layout:** `app/constants.py`, `app/cleaner.py`,
  `app/worker.py` (QThread), `app/window.py` (MainWindow), `app/icon.py`.
- **Cross‑platform:** Python 3.12+, PySide6, yt‑dlp, and ffmpeg only. Runs
  unchanged on Linux Mint and Windows 11.

### Installation

See `README.md` → Setup (Linux Mint or Windows 11 instructions).
