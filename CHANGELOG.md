# Changelog

All notable changes to this project are documented here.

---

## [0.2.0-beta.1] — 2026-07-30

### Added

- **Multi-platform support** (`app/worker.py`, `app/window.py`)
  Browser impersonation (Chrome) added to all yt-dlp workers, enabling downloads
  from Dailymotion, Vimeo, and Instagram which actively block default yt-dlp
  user-agents. Uses `curl_cffi` for impersonation with graceful fallback for
  older yt-dlp versions.

- **Cookie support** (`app/worker.py`, `app/window.py`)
  Two options for authenticated content (Instagram private, Vimeo private, etc.):
  - **Use browser cookies**: Auto-detect and use cookies from Chrome
  - **Cookie file**: Load cookies from a `cookies.txt` file exported from browser
  Settings persisted via QSettings. Cookie options passed to all workers
  (DownloadWorker, PlaylistInspectWorker, FileSizeWorker).

- **Extended playlist detection** (`app/window.py`)
  `_is_playlist_url()` now recognizes playlist URLs from:
  - YouTube (youtube.com, youtu.be, *.youtube.com)
  - Vimeo (vimeo.com, player.vimeo.com)
  - Instagram (instagram.com, www.instagram.com)
  - Dailymotion (dailymotion.com, www.dailymotion.com)

- **Improved URL display** (`app/window.py`)
  Queue items now show platform-appropriate identifiers:
  - YouTube: `[v=XXXXX]` or `📋 list=XXXXX`
  - Vimeo: `[video_id]` from path
  - Instagram/Dailymotion: `[post_id]` from path

### Fixed

- **Dailymotion downloads failing**
  Resolved by adding browser impersonation (`impersonate: chrome`).

- **Vimeo public videos failing**
  Resolved by adding browser impersonation.

- **Instagram public content failing**
  Resolved by adding browser impersonation. Private content now works with cookies.

### Dependencies

- Added `curl_cffi>=0.15.0` as a **required** dependency for browser impersonation.

---

## [0.2.0-beta.1] Re-release — 2026-08-04

### Fixed

- **YouTube downloads broken by unconditional browser impersonation**
  Initial v0.2.0-beta.1 build applied `impersonate: chrome` to ALL URLs,
  causing YouTube to throttle/block requests. Now impersonation is only
  enabled when cookies are used (for authenticated content on Instagram,
  Vimeo, Dailymotion). YouTube and other platforms work without it.

---

## [0.1.0-beta.5] — 2026-07-23

### Added

- **Download History tab** (`app/window.py`)
  New 4th tab (📋 History) recording every completed and failed download.
  Persisted to `~/.config/chrisnov-media-toolkit/download-history.json`
  with a versioned JSON schema so history survives app restarts.
  Includes search/filter (All / Audio / Video / Playlist), Clear All with
  confirmation, and double-click to Open Folder or Re-download.

### Fixed

- **Info button vs Start button race** (`app/window.py`)
  Pressing Start while the Info worker was still running spawned two
  yt-dlp instances on the same URL. When an Info result arrived
  mid-download it also clobbered the status label back to "Ready.",
  making the download look stalled. Added `_dl_active` flag so Info
  disables Start while fetching, and `_on_info_result` guards its status
  reset behind `_dl_active`.

- **macOS x86_64 build stuck in "queued"** (`.github/workflows/build-macos.yml`)
  The Intel runner label was pinned to `macos-13`, which GitHub has retired
  — no host backs it anymore, so the x86_64 leg queued indefinitely.
  Updated to `macos-15-intel`; also pinned the arm64 leg to `macos-15`
  for reproducible releases.

- **Artifact storage quota exceeded** (`.github/workflows/build-*.yml`)
  Free-plan 500 MB quota was hit (1.61 GB across 17 stale artifacts),
  causing `Upload artifact` to fail on every build. Set `retention-days: 1`
  on all three workflows and cleaned up old artifacts.

### Documentation

- `docs/OLD-MAC-WORKAROUND.md` — synced runner labels to `macos-15` +
  `macos-15-intel` and removed stale Cloudflare R2 / "December 2025"
  wording.
- Added design spec for Download History.

---

### Added

- **VERSIONINFO embedded in Windows executable** (`build-windows.ps1` +
  `chrisnov-media-toolkit.spec`)
  The build script generates a `version_info.txt` (VSVersionInfo) from
  `APP_VERSION` and the spec embeds it when building on Windows. This
  provides file-version metadata that helps reduce SmartScreen false
  positives. `version_info.txt` is gitignored.
- **Remember last used folders** (`app/window.py`)
  Output folders are now persisted per mode with `QSettings` under the
  key group `dirs/` — `download_video`, `download_audio`,
  `convert_audio`, `convert_video`. The chosen folder is restored on the
  next launch instead of always falling back to `~/Videos` or `~/Music`.
  Folders are saved whenever they are changed via Browse, toggled between
  audio/video, or when a download/convert starts.
- **Open Folder button** on all three tabs (Downloader, Audio Converter,
  Video Converter). Opens the currently selected output directory in the
  system file manager via `QDesktopServices.openUrl`.
- **File-size estimation** before download. A new `FileSizeWorker`
  (`app/worker.py`) resolves title, duration, and an estimated output
  size; the Downloader tab's **Info** button shows it in a small box
  without starting a download.
- **Embed metadata and thumbnail** (`app/worker.py` + `app/window.py`)
  Downloads can now write tags into the output file. The Downloader tab
  gained **Embed metadata** (on by default) and **Embed thumbnail**
  (off by default) checkboxes. Thumbnail embedding is limited to
  containers that support cover art (mp3, m4a, mp4, mkv). Metadata uses
  yt-dlp's built-in `FFmpegMetadata` postprocessor, which prefers the
  `track` field over the raw title so music videos get a clean track
  title.
- **Compact GUI for smaller screens** (`app/window.py`)
  Font reduced to 9 pt, tighter margins/spacing, minimum window size
  lowered to 700×480, and all three tab layouts reorganized into compact
  grids with horizontal checkbox rows. `QScrollArea` retained as a
  safety net for very short windows.

### Changed

- **Version display**: window title now reads
  `Chrisnov Media Toolkit vX.Y.Z-beta.N`; About dialog and header label
  already used `APP_VERSION`. `APP_VERSION` remains the single hardcoded
  source of truth in `app/constants.py`.
- Short labels expanded to full words: `Res:` → `Resolution:`,
  `Fmt:` → `Format:`.
- GitHub Actions build workflows pin `pyinstaller==6.17.0` and default
  their manual `version` input to `0.1.0-beta.4`.

### Fixed

- **Metadata title corruption** (`app/worker.py`)
  A `MetadataParser` `INTERPRET` postprocessor overwrote the `title`
  field with `NA`/empty when `track` was missing, which also produced
  `NA` filenames. Removed the `MetadataParser`; yt-dlp's native
  `FFmpegMetadata` already maps `track` → title with a safe fallback, so
  titles and filenames are never `NA`.

### Maintenance

- Bumped GitHub Actions: `actions/checkout` v4→v5,
  `actions/setup-python` v5→v6, `actions/upload-artifact` v4→v6.
  Resolves the "Node.js 20 is deprecated" annotation GitHub
  surfaced after the September 2025 runner deprecation.
- Removed internal docs (`AGENTS.md`, `WALKTHROUGH.md`, `ROADMAP.md`) from
  git tracking via `git rm --cached` and added them to `.gitignore` —
  these are local-only development notes. `test_opus.opus` also deleted
  and gitignored.

---

## [0.1.0-beta.2] — 2026-07-08

### Fixed

- **Build always reported failure on Linux** (`build-linux.sh`)
  `OUT` was set to `dist/chrisnov-media-toolkit` but the spec produces
  `dist/chrisnov-media-toolkit-lite`; the success check always missed the
  real output and exited 1. Fixed the path to match the spec.

- **PyInstaller 6.x build failure** (`chrisnov-media-toolkit.spec`)
  `cipher=block_cipher` was passed to `Analysis` and `PYZ`; PyInstaller 6.0
  removed cipher support entirely, raising `TypeError` on every build.
  Both arguments removed.

- **Linux BUNDLED build guard checked Windows paths** (`chrisnov-media-toolkit.spec`)
  The bundled guard used `not is_macos`, which is also True on Linux. It
  then checked for `bin/ffmpeg.exe`, so a Linux BUNDLED build always raised
  `FileNotFoundError`. Fixed to `sys.platform == 'win32'`.

- **Crash when yt-dlp reports speed as None** (`app/worker.py`)
  While buffering, yt-dlp sets `speed: None` instead of omitting the key.
  The progress hook divided by `d.get('speed', 0)`, causing `TypeError`.
  Fixed with `(d.get('speed') or 0)`.

- **mp3 sample rate ignored / duplicate `-ar` flag** (`app/converter_worker.py`)
  `_codec_args` hardcoded `-ar 44100` for mp3 regardless of the user's
  sample rate choice; when an explicit rate was selected, `-ar` appeared
  twice. Removed from `_codec_args` and delegated to `_sample_rate_args`.

- **Multi-select remove corrupted backing list** (`app/window.py`)
  Forward iteration through selected rows and `.pop()` by index shifted all
  subsequent indices, causing the wrong items to be removed from the backing
  list while the widget stayed in sync — silent data corruption. Fixed by
  collecting rows into a set and iterating in reverse order. Affected the
  downloader queue, audio converter file list, and video converter file list.

- **Cancel race: signals fired after batch reset** (`app/window.py`)
  `_cancel_download` called `terminate()` without first disconnecting worker
  signals. If `finished_ok` or `failed` fired after `_reset_after_batch()`
  cleared the batch, `_kick_next()` would increment stale indices and could
  start a phantom download. Signals are now disconnected before `terminate()`.

- **Converter clean-title silently disabled by downloader checkbox** (`app/window.py`)
  Both converter tabs guarded clean-title logic with `self.clean_chk.isChecked()`
  (the downloader tab's checkbox). Unchecking that unrelated checkbox silently
  disabled title cleanup in the converters. Each tab now reads the tag list
  independently.

- **Retina/HiDPI blurry rendering on macOS** (`chrisnov-media-toolkit.spec`)
  `NSHighResolutionCapable` was set to the string `'True'` instead of the
  boolean `True`; macOS ignored the string value. Fixed.

- **sha256 files embedded `dist/` path prefix** (`.github/workflows/`)
  On Linux and macOS, `sha256sum`/`shasum` was run against the full
  `dist/<filename>` path, so the checksum file contained `dist/foo.tar.gz`
  instead of just `foo.tar.gz`. `sha256sum -c` would fail for anyone
  verifying a flat download. Both workflows now `cd dist` before hashing.

- **PowerShell `finally` block skipped on missing FFmpeg** (`build-windows.ps1`)
  `exit 1` inside a `try` block bypasses `finally` in PowerShell, leaving
  temp extract directories on disk. Changed to `throw`.

### Changed

- Added `set -o pipefail` to `build-linux.sh`.
- Added `timeout-minutes: 30` to all three GitHub Actions build jobs to
  prevent hung PyInstaller runs from consuming runners for hours.
- Added `BUILD_TYPE: LITE` to the Windows workflow job `env:` block (Linux
  and macOS already had it) for consistency.
- Wrapped Windows `.exe` builds in `.zip` archives (using
  `Compress-Archive`) so Chrome does not block the download with
  SmartScreen. SHA256 and R2 uploads now target the `.zip` files. No
  more applying `$PWD` directly for venv path resolution — using
  `$env:GITHUB_WORKSPACE` instead.
- macOS build split into two parallel jobs: `build-arm64` (Apple Silicon)
  and `build-intel` (`macos-13`, for Intel Macs including 2015 hardware).
  Each produces its own ZIP artifact and R2 object.
- Playlist inspection moved to a `PlaylistInspectWorker` thread; the UI
  is no longer blocked while walking the playlists to count entries.
  The large-playlist confirmation dialog now appears as a callback.
- `DownloadWorker` gained a clean `cancel()` method (consistent with
  the converter workers). Cancel no longer relies on
  `QThread.terminate()` first; it raises from inside the yt-dlp progress
  hook and waits up to 5 s for graceful shutdown before falling back.

### Added

- Initial automated test suite under `tests/` covering `app.cleaner`
  and core `app.converter_worker` logic (46 tests). Runs on every push
  and PR via `.github/workflows/tests.yml`.
- `APP_VERSION` constant in `app/constants.py`. Shown in a header
  label and in a new About dialog (`MainWindow._show_about`) reporting
  platform, Python, PySide6, and yt-dlp versions.

---

## [0.1.0-beta.1] — 2026-07-05

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

- **Lite and Bundled Windows build variants**
  `build-windows.ps1` now supports `-Type Lite`, `-Type Bundled`, and
  `-Type Both`. Lite builds require system FFmpeg, while Bundled builds include
  `ffmpeg.exe` and `ffprobe.exe` from the local `bin/` folder.

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

- **Blog article moved out of the repository**
  `BLOG_ARTICLE.md` is no longer tracked in this private app repository. The
  article draft now lives one directory up at `D:\dev\chrisnov-it\BLOG_ARTICLE.md`.

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

- **Clean title not applied after completed playlist downloads**
  Playlist downloads previously emitted only a summary string, so the GUI tried
  to discover files by timestamp. Playlist results now include concrete output
  paths from yt-dlp metadata, and `_on_item_ok` cleans each completed file.

- **Clean title not applied when cancelling large playlists**
  Cancelling a playlist used to terminate the worker before `_on_item_ok` could
  run. Cancel now scans completed media files created since the batch started
  and applies clean-title renaming before resetting the queue.

- **Opus conversion failing for unsupported sample rates**
  libopus only accepts specific sample rates. Opus conversion now preserves
  supported rates and falls back to 48000 Hz for unsupported inputs such as
  44100 Hz.
