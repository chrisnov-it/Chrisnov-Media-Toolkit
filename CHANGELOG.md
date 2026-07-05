# Changelog

All notable changes to this project are documented here.

---

## [Unreleased] — 2026-07-05

### Added

- **Renamed app to Chrisnov Media Toolkit**
  The UI window title, PyInstaller output names, build scripts, spec file, and
  documentation now use the broader Media Toolkit name.

- **Audio Converter tab** (`app/converter_worker.py` + `app/window.py`)
  Dedicated audio conversion tab alongside the Downloader tab. Supports:
  - Batch file queue with drag-and-drop (audio and video input)
  - Add files and Add folder for album/collection batch conversion
  - Video-to-audio extraction (strips video stream via `-vn`)
  - Output formats: mp3, m4a (AAC-LC), opus, flac, wav
  - CBR / VBR mode for lossy formats (mp3, m4a); opus always VBR
  - Bitrate selector (96–320 kbps)
  - Sample rate conversion: As-is / 44100 / 48000 / 96000 Hz
  - EBU R128 loudness normalization (2-pass, adjustable LUFS target)
  - Peak normalization (dynaudnorm + volume filter)
  - Trim silence (leading + trailing, via silenceremove + areverse trick)
  - Shared Clean title setting from the Downloader tab
  - Output folder with Browse, auto-rename on collision

- **Video Converter tab**
  New local video converter for mp4, mkv, webm, avi, mov, wmv, flv, ts, and
  m4v input. Outputs mp4, mkv, or webm with simple quality presets: Keep
  quality, Balanced, and Smaller file. The worker keeps original audio when
  possible and retries with AAC/Opus when the stream is incompatible.

- **Real FFmpeg progress and graceful cancel**
  Audio and video converters now parse `ffmpeg -progress` output for live
  progress updates. Cancel terminates the FFmpeg subprocess instead of abruptly
  killing the Qt thread first.

- **Windows executable icon generation**
  `build-windows.ps1` creates `icon.ico` from `icon.svg` when needed and the
  PyInstaller spec embeds it in `chrisnov-media-toolkit.exe`.

- **Contributor guide**
  Added `AGENTS.md` with repository structure, build commands, coding style,
  testing notes, and PR guidelines.

- **Smart output folder auto-switch**
  Checking "Audio only" now automatically switches the output folder to
  `~/Music`; unchecking switches back to `~/Videos`. The switch only happens
  if the folder is still on the default path — a manually chosen folder is
  never overwritten.

- **Expanded default Clean Title tag list**
  Added common Indonesian tags (`Video Lirik`, `Lirik Video`, `Lirik Lagu`,
  `Lirik`, `Video Klip`, `Musik Video`, `Audio Visual`, `Lagu Resmi`, `Resmi`,
  `Versi Akustik`, `Live`) and additional English tags (`Official Live Video`,
  `Official Visualizer`, `Official Acoustic`, `Acoustic Version`,
  `Live Performance`, `Live Session`, `Full Album`, `Album Stream`,
  `Visualizer`, `HD`, `HQ`, `4K`, `MV`).

### Changed

- **UI polish and responsive layout**
  The main window is now larger by default, tabs are scrollable, queue/file
  lists expand when the window is maximized, and primary/cancel buttons have
  clearer visual states.

- **Build outputs renamed**
  Windows output is now `dist\chrisnov-media-toolkit.exe`; Linux output is
  `dist/chrisnov-media-toolkit`. The spec file is now
  `chrisnov-media-toolkit.spec`.

- **Config/archive path renamed with migration**
  Download archives now live under `~/.config/chrisnov-media-toolkit/`.
  Existing archives from `~/.config/chrisnov-yt-downloader/` are copied forward
  automatically if the new archive does not exist yet.

- **UPX is optional, not required**
  Builds remain unpacked by default unless UPX is installed and intentionally
  used. This avoids increasing false-positive antivirus risk for normal builds.

- **Queue auto-clears after batch completes**
  Previously the download queue (URL list + `current_batch`) was not cleared
  after a batch finished, causing old URLs to be re-downloaded on the next
  Start. `_reset_after_batch` now clears both the list widget and the internal
  batch list. This also applies after Cancel.

### Fixed

- **Double file extension on audio-only downloads** (`song.m4a.m4a`)
  `outtmpl` for audio-only mode was hardcoding the container extension
  (e.g. `%(title)s.m4a`). `FFmpegExtractAudio` then appended its own
  extension after conversion, producing a double suffix. Fixed by using
  `%(title)s.%(ext)s` and letting yt-dlp manage the extension.

- **Clean title not applied to audio-only files**
  `worker.run()` emitted the path from `prepare_filename()`, which returns
  the pre-conversion extension (e.g. `.webm`). `rename_with_cleanup` looked
  for a `.webm` file that no longer existed on disk and silently skipped the
  rename. Fixed by replacing the extension with the chosen container
  (`.mp3`, `.m4a`, `.opus`) before emitting `finished_ok`.

- **Clean title regex leaving behind unclosed brackets**
  `clean_title()` matched fully-bracketed tags `(tag)` / `[tag]` but failed
  on titles where the closing bracket was missing, e.g. `Song (Official Music
  Video`. Added passes for unclosed brackets at end-of-string and mid-string,
  plus a final sweep to remove dangling bracket characters.

- **`AttributeError: 'MainWindow' object has no attribute 'batch_done'`**
  `batch_done` was only initialised inside `_on_item_ok`, so if the very first
  item in a batch failed, `_kick_next` crashed trying to reference it. Fixed
  by initialising `batch_done = 0` alongside `batch_idx` and `batch_total` in
  `_start_download`, and replacing the fragile `getattr` fallback with a direct
  `+= 1`.
