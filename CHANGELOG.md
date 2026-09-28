# Changelog

All notable changes to this project are documented here.

---

## [Unreleased]

### Fixed

- **Closing the app while a batch ran destroyed live worker threads (and left
  ffmpeg running)**
  `MainWindow` had no `closeEvent`, so quitting mid-download/mid-conversion tore
  down QThreads that were still inside `run()` ("QThread: Destroyed while thread
  is still running", possible abort) and left ffmpeg children orphaned mid-file.
  `closeEvent` now calls an idempotent `shutdown()` on every tab that owns
  workers, ignores the
  close while `WorkerTracker.running()` is non-empty, and re-polls every 100 ms
  (window greyed out, title shows "stopping…") until the workers exit — with a
  10 s deadline before `terminate()` as a last resort. `aboutToQuit` is wired to
  the same shutdown for quits that never send a close event.

- **Cancel froze the GUI for up to 7 seconds and could deadlock the process**
  The cancel slots blocked in `QThread.wait()` and then called `terminate()` on a
  thread that can be inside Python or `subprocess` code — on Windows that risks a
  GIL deadlock or a corrupted `.part` file. Cancel now disconnects the signals,
  sets the flag, and returns immediately (same for the audio/video converter
  tabs). The conversion workers' `probe_duration()` was the worst offender —
  a plain `subprocess.run(timeout=30)` that cancellation could not interrupt —
  and now runs through a poll loop that terminates (then kills) its ffprobe
  child, so a cancel during the probe stops before ffmpeg is ever spawned.
  The GUI-side `_conv_active` / `_batch` guards also stop an already-queued
  `finished_ok`/`failed` event from silently starting the next item after a
  cancel.

- **One bad `stat()` could freeze the download queue until the user found Cancel**
  `_on_item_ok` computed file sizes with an `exists()`-then-`stat()` race and
  appended to the history model with no `try/finally`. Any exception escaped the
  Qt slot, skipped `batch.idx += 1` / `_kick_next()`, and left the batch stuck
  with Start disabled — invisible in a `--noconsole` build. Both completion
  handlers now fence their bookkeeping and always advance; size reads go through
  a TOCTOU-safe helper and failures are logged and surfaced in the status label.

- **A crash mid-write could silently lose the entire download history**
  `DownloadHistory.save()` truncated the JSON file in place, and `load()` reset
  to `[]` on the resulting `JSONDecodeError` — the next append then overwrote
  everything, with the `OSError` swallowed by a bare `pass`. The payload is now
  written to a sibling `.tmp` and moved into place with `os.replace()`, the
  previous file is kept as `.bak` and used as a fallback when the main file is
  unreadable, the entry cap is applied at load time too, and a failed save
  returns `False` and logs instead of pretending it worked.

- **Dropping a non-UTF-8 file on the Downloader tab raised out of the drop
  handler**
  `Path.read_text()` failures were caught with `except OSError`, but
  `UnicodeDecodeError` is a `ValueError` — dropping an mp3/mkv/pdf (easy to do in
  a media toolkit) threw an uncaught exception and aborted the drop. The handler
  now catches `(OSError, UnicodeError)` and simply ignores the file.

- **Release builds did not use the pinned dependency versions**
  The three build workflows installed `PySide6 yt-dlp curl_cffi` ad hoc while
  `requirements.txt` pinned them for exactly this purpose, so releases resolved
  whatever PyPI served on build day and validated a different dependency set than
  the CI test job. They now install `-r requirements.txt` (PyInstaller keeps its
  deliberate in-workflow pin).

- **A new download silently reset the History search and type filter**
  `HistoryTab.refresh()` defaulted its arguments to `""`/`"All"`, so whenever
  `history_changed` fired (or Clear All ran) a search the user had typed was
  thrown away. `None` now means "reuse what is in the widgets", and only an
  explicit call passes new values.

- **Declining the large-playlist confirmation emptied the queue**
  The batch-reset path always cleared the URL list, so answering "No" to the
  50+ entries dialog - or hitting a playlist-inspect error - discarded the URLs
  the user had just queued. Validation and inspect failures now keep the queue
  (`_reset_after_batch(clear_queue=False)`); it is cleared only when a batch
  finishes or is cancelled.

- **Title cleanup glued bracketed tags onto the word before them**
  The bare-tag rule matched anywhere inside a word, turning
  `Song[Official]` into `SongOfficial` (while `[Official] Video` was fine).
  Word boundaries now apply on the side that touches a word character, so
  `Song [Official]` cleans to `Song` but glued tags are left alone.

- **Playlist cleanup could rename a file that was not part of the batch**
  `discover_new_files()` only compared mtimes against the batch start, so a
  pre-existing file touched during the batch passed as "new". It now also
  requires the file's creation time (birth time, `st_ctime` on Windows) to
  fall inside the window; Linux keeps the mtime-only behaviour.

- **ffmpeg could stall waiting on the GUI's stdin**
  Every ffmpeg/ffprobe invocation now gets `-nostdin`, so a build with a
  console (or an accidental interactive prompt) can never block a conversion;
  `run_ffmpeg_with_progress()` also clears its `set_process` hook in a
  `finally`, and a failed conversion removes its partial output file.

- **Unhandled exceptions left no trace in release builds**
  `main()` installs a `sys.excepthook` first: it appends the traceback to
  `~/.config/chrisnov-media-toolkit/crash.log` and, on the main thread, shows
  a short dialog instead of the app silently continuing without a stack trace.

- **A completed download whose file had vanished was logged as "completed"**
  `_on_item_ok` now stats the resolved path and records a `failed` entry with
  the error when the file is missing, so History and the queue summary report
  `0/1 completed` instead of a green check over a file that does not exist.

- **The About dialog froze the UI while reading the FFmpeg version**
  The version probe now runs in a `_FFmpegVersionWorker` (off the GUI thread)
  and fills the row when it answers; a late result for a reopened dialog is
  dropped.

- **Huge folder drops froze the converter tabs**
  `Folder` used `Path.rglob("*")` + a full sort on the GUI thread, so pointing
  at a large or network tree stalled the window for the whole walk. Both
  converter tabs now use `app/utils.scan_media_files()`, a bounded `os.scandir`
  walk (hidden entries and directory symlinks skipped, entry/file caps), and
  report truncation instead of hanging.

- **A batch could run with mixed settings or write to several folders**
  The audio and video converter tabs freeze their settings widgets (and
  snapshot the cleanup tags) for the whole batch, so changing format, quality,
  normalization or destination mid-run can no longer split one queue across
  inconsistent outputs.

- **Disabled buttons had an invisible label (1.00:1 contrast)**
  `QPushButton:disabled` set `color: {mid}; background: {mid}` — the *same*
  palette color for text and surface, so every frozen control's caption (Start,
  Convert, Clear…) vanished the moment it was disabled. Disabled labels now use
  the button surface with text blended 45% toward it (4.6:1 in light, 4.9:1 in
  dark — WCAG AA) plus explicit `#primaryButton:disabled` and
  `#dangerButton:disabled` rules: Qt ranks ID selectors above `:disabled`, so
  without them the blue primary kept looking enabled. Controls frozen by a
  batch additionally swap their tooltip for "Unavailable while a batch is
  running." (tooltips still fire on disabled widgets) and restore the original
  text when the batch ends.

- **Conversion failures left no trace and could not be read or copied**
  Neither converter tab ever called `history.append`, so a failed run existed
  only as a one-line status message that the batch summary overwrote — unquoted,
  unselectable, and gone after the queue reset. Both tabs now take the shared
  `DownloadHistory` (new constructor argument), record `completed`/`failed`
  entries (source path in `url`: searchable, but never requeued as a URL — the
  History action is scheme-guarded), fence the write so it can never stall the
  queue, and emit `history_changed`. History rows append the error to the row
  itself (word-wrapped) with the full message in the tooltip, and all three
  status labels plus the Info box are word-wrapped and mouse-selectable so a
  long error can actually be read and copied.

- **Queue rows hid what they were about to download**
  Labels were raw slices (`identifier[:20]`, `url[:40]`) that cut identifiers
  mid-word with no indication anything was missing, and rows carried no tooltip
  at all. Labels now end with `…` (shared `clip_text()`) and every row keeps the
  full URL as its tooltip; converter rows show the full source path the same
  way, and `mark_status()` appends a failure message instead of overwriting the
  tooltip that was already there.

- **Secondary text below WCAG AA (search placeholder 4.00:1, About links
  2.82:1)**
  Stylesheets have no placeholder pseudo-element, so `QLineEdit` draws its
  placeholder from the palette's `PlaceholderText` role — the raw system value
  measures 4.00:1 on the field, and the About dialog's credit/GitHub links used
  `NEUTRAL_GRAY` on the window (2.82:1 in light mode). Both now come from
  `theme.muted_color()` (blends the foreground toward the background until it
  clears 4.5:1): 4.74:1 / 4.66:1 light, 4.73:1 / 4.92:1 dark, verified by pixel
  measurement in both palettes. Qt keeps an **explicit palette snapshot on every
  widget** (a window-level `setPalette()` never reaches the edits — measured),
  so the role is also written to all three color groups on every
  QLineEdit/QTextEdit/QPlainTextEdit under the window, re-applied on system
  theme changes, and the About links use the window palette instead of a hard
  coded gray.

- **The selected radio button had no visible indicator (light mode)**
  The Windows style painted the *checked* radio's dot in the background
  color (or not at all) while unchecked circles rendered normally — the
  selected CBR/VBR mode and normalization were simply invisible, which the
  dark/Fusion build never showed. The indicator is now drawn explicitly by
  the stylesheet (`QRadioButton::indicator*`): accent-filled when checked,
  `{mid}`-bordered `{base}` circle when not, dimmed when disabled.

- **Frozen checkboxes and combos still looked enabled**
  The stylesheet sets an unconditional `color:` on fields, checkboxes and
  radios, which beats the palette's disabled text — a control frozen by a
  batch greyed out its *buttons* but kept full-strength text everywhere
  else, so the panel read as half-editable. New `:disabled` rules mute that
  text with the P1-style 45% blend (`{disabled_field}`: ≥4.5:1 on both the
  field and widget surfaces in both palettes).

- **The progress bar and status line were below the fold at the default
  size**
  `MainWindow` opened 900×620 but the Downloader tab's content is ~605 px
  tall, leaving its QProgressBar and status label 65 px outside the
  viewport — the batch's only progress/ETA readout (and every error message)
  required scrolling. The default is now 900×700 so all four tabs fit.

- **The History summary counted rows the filter had hidden**
  With 1 of 2 entries visible it still reported "(2 items, …)" — and could
  quote a total size that included hidden files. The summary now describes what
  is on screen: "(1 of 2 items, 12.3 MB shown)".

- **Emoji glyphs rendered differently — or as tofu — depending on the font**
  History rows (🎵🎬📋📁 + ✅/❌ status), the Downloader's playlist marker 📋
  and the History legend (📂/🔁) all leaned on whatever symbols the user's
  fonts happen to ship — the exact failure that already forced the tab icons
  to bundled SVGs (▣ showed as a box on Linux Mint). Status marks now reuse
  the queue's SVG `queue_status_icon()` (green check / red cross), playlist
  rows get a new bundled `clipboard` icon, the legend pairs its labels with
  the platform style's standard pixmaps, and row text keeps only the status
  *word*.

- **Secondary font sizes ignored the platform base**
  Hardcoded 7pt/8pt/9pt/10pt literals don't scale with the base the theme
  picks (11pt on macOS), where an "8pt" hint ends up nearly the same size as
  the base text it should sit under. `small_font_size()` / `tiny_font_size()`
  now derive from `_base_font_points()`, and every literal call site uses
  them (About dialog, History title/summary/legend, in-list placeholders,
  version/about controls) — unit tests assert the stylesheet contains no
  literal sizes at all.

- **The Info button's label turned into "..." while fetching**
  The button mutated its own text (and disabled Start for the duration) with
  no word on screen about what was happening. It now keeps its "Info" label,
  disables itself, and the status line reports "Fetching info..."; the
  result/error handlers re-sync Start instead of unconditionally enabling it.

- **The cleanup-tag list and the cookie path were clipped with no way to
  read them**
  The tag field is a 440-char comma list scrolled to the right (its start
  was cut off on screen) and the cookie label sliced paths at 40 chars. Both
  now carry their full text on hover, updated when the cookie file changes.

- **Clearing the queue or a file list could silently wipe hours of work**
  "Clear All" in History confirmed, but the Downloader's Clear and both
  converter Clears removed every row with one misclick. At
  `CLEAR_CONFIRM_ROWS` (5) rows or more they now ask first (default No);
  below the threshold clearing stays instant.

- **The Downloader's settings stayed editable while a batch ran**
  Both converter tabs froze theirs, but resolution, container, checkboxes,
  folder and cleanup-tag inputs could all be changed mid-run — changes the
  batch had already snapshotted and would never apply. `_set_batch_busy()`
  now freezes queue + settings (with the busy tooltip) and, on thaw, restores
  each control's *previous* enabled state instead of force-enabling it (the
  bitrate combo stays off in video mode, the tag field with Clean title off).

### Added

- **Empty states inside the list boxes**
  The Downloader's queue had no hint at all (just a blank box), and the
  converter/history placeholders sat *below* their list where they read as
  unrelated captions. Each list now carries a centered placeholder inside its
  own viewport (`install_placeholder()`, model-signal driven so it survives
  `addItem`/`clear`/filtered re-renders), and the Downloader invites
  "Paste or drop URLs here (Ctrl+V)".

- **A batch finishing now announces itself**
  Title goes to "✓ Done (3/5) — Chrisnov Media Toolkit …" plus a taskbar
  flash (`QApplication.alert`) on `batch_finished`, cleared when the next
  batch starts — previously a finished batch left no trace on screen.

- **"Open last result" on all three tabs**
  One click reopens the finished file (or its folder) in the default app /
  file manager; it arms on success and is disabled again until the next
  result, so a vanished file can never become its target.

- **Deleting a single History entry**
  "Clear All" was the only way to remove anything. Each row can now be removed
  with a Remove button or the Delete key: rows carry their **model index**
  (`DownloadHistory.remove_at()` is bounds-checked, and `item.data()` returns a
  dict *copy*, so identity matching could not work), making removal safe from
  a filtered view and a stale selection a silent no-op.

- **Ctrl+Enter starts, Esc cancels**
  Bound on all three worker tabs (`WidgetWithChildrenShortcut`): Ctrl+Enter
  (and Ctrl+KeypadEnter) triggers Start/Convert — with an empty list it just
  reaches the same validation as a click — while Esc cancels a *running*
  batch only. Both handlers are guarded because they fire on a live signal:
  Ctrl+Enter must not snapshot a second batch over a running one, and an idle
  Esc must never wipe the queue/list (cancel clears it). Delete already
  removes a History row.

### Changed

- **Download progress shows where you are in the queue and when it ends**
  The bar used to be a bare percent (identical for item 1 and item 5 of 5);
  it now reads "[2/5] 50% • ETA 00:10" from the already-existing position and
  `EtaEstimator` data, reset per batch.

- **Drops answer back**
  Dropping a URL on the History tab queues it *and* switches to the Downloader
  (it used to queue silently behind the wrong tab); plain text or an
  unsupported file on a converter tab reports "not text" / "Nothing added —
  drop video files or a folder." instead of doing nothing visible.

- **History polish** - the empty state distinguishes an empty history
  ("No downloads yet") from a filter that hides everything ("No matching
  entries"), the summary shows the total size for any non-empty history
  (previously only GB/MB), and the missing-cleanup-tags warning tells the user
  what to do instead of ending with "Returning.".

- **Primary buttons follow the work list instead of warning after the fact**
  Start/Remove/Clear (Downloader) and Convert/Remove/Clear (both converters)
  used to stay clickable while empty and only answered with a warning dialog —
  or nothing at all. They now start disabled and arm when the queue/list
  holds something (Start also with a typed URL), re-synced after a batch thaw
  so a reset that emptied the list disarms them again. The warning dialogs
  remain as validation for direct calls (shortcuts, tests).

- **Key inputs name themselves for screen readers**
  `accessibleName`s on the URL field, queue, cleanup-tag and output-folder
  fields, both converter file lists, and the History search/list/filter —
  previously a screen reader heard nothing for any of them.

- **CI and release hardening** - workflows declare
  `permissions: contents: read`; the release `version` input is validated
  against a strict pattern before it reaches `GITHUB_ENV`, artifact names or
  the shell (awk reads it via `-v` instead of program-text splicing);
  `build-windows.ps1` sanitizes the version written into `version_info.txt`
  and verifies the FFmpeg download checksum (fail-closed, with an explicit
  `ALLOW_UNVERIFIED_FFMPEG=1` escape hatch); `installer.nsi` only compiles the
  optional FFmpeg component when `bin\ffmpeg.exe` and `bin\ffprobe.exe` are
  actually present (and closes its preprocessor blocks with `!endif`); Windows
  release `.sha256` files now carry `hash  filename` like the Linux/macOS
  ones, so `sha256sum -c` accepts them.

- **Tests** - the suite grew from 171 to 242 (`tests/test_theme.py`,
  `tests/test_utils.py` and `tests/test_main_excepthook.py` are new), with
  regression coverage for every
  fix above, exact-value assertions where checks were vacuous, and skip guards
  that match how `find_ffmpeg()`/`find_ffprobe()` actually behave.

### Documentation

- README now names the Video Converter's checkbox as it really appears
  (**Copy audio**), `docs/BUILDING.md` documents the local Windows outputs
  (bare `.exe`s - CI produces the versioned zips) and the automatic
  `icon.ico` rendering, the setup hints in `build-linux.sh` /
  `build-windows.ps1` install `-r requirements.txt` (which pulls in the pinned
  `curl_cffi`), the lost `## [0.1.0-beta.4]` header was restored in this file,
  and `docs/OLD-MAC-WORKAROUND.md` relies on the venv's pinned PyInstaller.

---

## [0.2.0-beta.4] — 2026-09-25

### Fixed

- **App could refuse to start after a corrupted `download-history.json`**
  `DownloadHistory.load()` only verified that `items` was a list and then
  called `.get()` on every element, so a truncated write, a cloud-sync
  conflict, or a hand-edited file containing a scalar raised `AttributeError`
  straight out of `MainWindow.__init__` — the app died before showing a window.
  Non-dict entries are now dropped, and wrong-typed `filesize_bytes` /
  `timestamp` values are normalised (the History tab sums and `int()`-casts
  both, so a string there crashed rendering with `TypeError`). Guarded by
  three new `tests/test_history.py` cases.

- **`scripts/smoke_gui.py` appended to — and would have cleared — the real
  download history on Windows**
  The isolation prelude only redirected `HOME`/`XDG_CONFIG_HOME`, but
  `ntpath.expanduser()` reads `USERPROFILE` first, so the smoke test wrote its
  fixture entries into the developer's real
  `%USERPROFILE%\.config\chrisnov-media-toolkit\download-history.json`, then
  failed its own "history should render 2 entries" check. Had the real history
  been empty, the run would have ended by deleting real entries via Clear All.
  `USERPROFILE`, `HOMEDRIVE`, and `HOMEPATH` are now redirected as well, and
  the throwaway home directory is removed when the run finishes.

- **Test suite was red on Windows** (`tests/test_ffmpeg_utils.py`)
  `test_uses_pyinstaller_bundled_binary` created a `bin/ffmpeg` fixture while
  `find_binary()` appends `.exe` on win32, so the lookup fell through to PATH
  and the assertion failed. The fixture is platform-aware now, and the CI test
  matrix runs on Windows as well as Linux.

- **About dialog could freeze and advertise a downgrade**
  The yt-dlp update check called `urllib.request.urlopen()` on the GUI thread
  (blocking the dialog for up to the 3 s timeout) and compared versions with
  `!=`, so a self-built or nightly yt-dlp was told to "update" downwards. The
  request now runs in `UpdateCheckWorker` (`app/update_check.py`) and versions
  are compared numerically — only a strictly newer release is reported.

- **`version_info.txt` could embed a stale version**
  The committed file still said `0.2.0-beta.2`/`(0, 2, 0, 2)` while
  `APP_VERSION` had moved to `0.2.0-beta.3`, so a manual
  `pyinstaller chrisnov-media-toolkit.spec` run produced executable metadata
  that disagreed with the About dialog and the release tag. The file is
  correct again, written ASCII-only (the copyright sign is a `\u00a9` escape),
  `build-windows.ps1` now writes it without a BOM (Windows PowerShell 5.1 adds
  one, which PyInstaller's parser rejects), and the new
  `tests/test_version_metadata.py` fails if it ever drifts again.

- **Converter/probe no longer flash a terminal window in the released builds**
  The app is built with `console=False`, so on Windows every console-subsystem
  child process gets a console window of its own. `app/ffmpeg_utils.py` spawned
  ffprobe/ffmpeg without `CREATE_NO_WINDOW`: a console flashed whenever the
  About dialog read the FFmpeg version and whenever a conversion was prepared,
  and one stayed open for the whole encode or loudness scan. All four spawn
  sites now pass `_no_window_kwargs()` (a no-op off Windows). yt-dlp already
  hid its own ffmpeg children (`STARTUPINFO`/`STARTF_USESHOWWINDOW`), so the
  downloader path was unaffected.

- **Missing-FFmpeg hint named the wrong package manager**
  `find_binary()` always suggested `sudo apt install ffmpeg`, including in the
  Windows and macOS builds. The hint is per-platform now
  (`winget install Gyan.FFmpeg` / `brew install ffmpeg`).

### Added

- **List-item separators and consistent minimal scrollbars** (`app/theme.py`)
  Queue and history rows now carry a thin palette-derived divider
  (`QListWidget::item` border in `midlight`, selected rows in
  `highlight`/`highlighted-text`) so items stay readable in both Light and
  Dark Mode with no hardcoded colors. Vertical and horizontal scrollbars
  share one minimal 10 px style (transparent track, `mid` handle,
  `highlight` on hover/press) across the Downloader, converter, and
  History tabs.

- **Live ETA on both converter progress bars** (`app/progress.py`,
  `app/convert_tab.py`, `app/video_convert_tab.py`)
  The workers already reported real FFmpeg progress; the bars now also show
  a remaining-time estimate (`45% • ETA 00:32`, falling back to a bare
  percent while no estimate exists yet). The new `EtaEstimator`
  extrapolates wall-clock time over each worker's known range (single-pass
  10–90, EBU R128 two-pass 5–90, video 10–90), rebases cleanly on the video
  worker's AAC/Opus retry, and the bar format is only rewritten when the
  displayed string changes. Covered by `tests/test_progress.py`.

- **`app/update_check.py`** — Qt-light yt-dlp release check with pure
  `version_key()` / `is_newer_version()` helpers (unit-tested in
  `tests/test_update_check.py`) plus the worker the About dialog uses.
- **`tests/test_version_metadata.py`** — keeps `version_info.txt` in sync with
  `APP_VERSION` (version strings, numeric tuple, ASCII-only file).
- **`ruff.toml`** — the lint baseline now lives in the repository instead of
  depending on each developer's personal configuration, so
  `ruff check .` reports the same findings everywhere. `main.py` was cleaned up
  to keep the baseline at zero.
- **`requirements.txt` / `requirements-dev.txt`** — pinned runtime and dev
  dependencies, so a fresh checkout, the CI job, and release builds all
  resolve the same versions (the project still has no `pyproject.toml`).
- **CI: Windows and Linux test matrix** running lint, `pytest`, and the
  offscreen GUI smoke test, plus a step asserting the smoke test never created
  a real user config directory.
- **`docs/THIRD-PARTY.md`** — licence obligations for the bundled GPL FFmpeg
  binaries and the Python dependencies.
- **FFmpeg archive verification and licence handling in
  `build-windows.ps1`** — the downloaded archive is checked against the
  release's published `checksums.sha256` before it is embedded, reusing the
  FFmpeg found on the build host now logs a provenance/licence warning, and the
  archive's licence text is saved as `bin\FFMPEG-LICENSE.txt`. The bundled ZIP
  (`build-windows.yml`) and the installer's optional FFmpeg component ship that
  file when it exists.

### Changed

- Download history is sanitised when it is loaded, so a damaged
  `download-history.json` degrades to "some entries missing" instead of
  preventing the app from starting.

---

## [0.2.0-beta.3] — 2026-09-14

### Added

- **Offscreen GUI smoke test** (`scripts/smoke_gui.py`)
  A no-network regression net covering tab construction, URL-queue handling
  (dedup, remove, clear, playlist labeling), history render/search/clear,
  converter file lists, worker tracking, idle cancel guards, and Start
  validation guards. Redirects HOME/XDG_CONFIG_HOME to a temp dir before any
  Qt import so it never touches real user config. Run with
  `QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/smoke_gui.py`.

- **Unit tests for the download-history model** (`tests/test_history.py`)
  Covers load (missing/corrupt/wrong-version/valid), legacy playlist-payload
  sanitization, newest-first append + persistence, nested parent-dir creation,
  entry capping, and clear.

- **Per-item status icons in every batch queue** (Downloader, Audio
  Converter, Video Converter)
  Queue rows now carry a colored status mark as the batch advances: amber
  arrow = running, green check = completed, red cross = failed — the row
  text takes the same color, and a failed download keeps the error (plus
  the yt-dlp hint, see below) as a row tooltip. Mid-batch progress is
  scannable on the list itself instead of only in the status bar.

- **Mode-aware "update yt-dlp" hint on extractor-type download errors**
  `ytdlp_update_hint()` (`app/worker.py`, unit-tested in `tests/test_worker.py`)
  recognizes errors that mean yt-dlp is out of date (YouTube "not a bot"
  checks, "unable to extract", signature/nsig extraction failures — the
  A/B-cohort cases where one video fails while every other URL works) and
  appends the right advice to the status bar: frozen builds point to the
  latest app release, source installs to `pip install -U yt-dlp curl_cffi`
  from the README. Display-only — the stored history error stays raw.

- **Empty-state placeholders in both converter tabs**
  "No files yet." / "No videos yet." while the list is empty, mirroring
  the History tab's placeholder pattern.

- **Keyboard shortcuts**
  Ctrl+V/Cmd+V on the Downloader tab queues every URL in the clipboard
  (focused text fields keep their normal paste); F1 opens the About
  dialog from anywhere in the app.

### Changed

- **`MainWindow` split into one module per tab** (`app/window.py` + new `app/download_tab.py`, `app/convert_tab.py`, `app/video_convert_tab.py`, `app/history_tab.py`)
  The former 2000-line monolith is now a thin shell (~400 lines) owning only
  the tab layout, drag-and-drop routing, theme changes, and the About dialog.
  Each tab is its own widget with its own `WorkerTracker`; cross-tab coupling
  goes through explicit public APIs (`is_active`, `add_url`, `add_folder`,
  `requeue`, `clean_tags_text`, `history_changed` / `requeue_requested` signals).
  Downloader batch state is consolidated into a `BatchState` dataclass
  replacing the lazily-set attributes and their `getattr()` fallbacks; Start
  validation now runs before any state is built so early returns can't leave a
  half-initialized batch behind. Extracted shared leaves: `AppSettings`
  (`app/settings.py`, typed QSettings accessors), `DownloadHistory`
  (`app/history.py`, Qt-free versioned-JSON model), `WorkerTracker`
  (`app/worker_tracking.py`), `open_in_explorer` (`app/utils.py`), `CONFIG_DIR`
  (`app/constants.py`). Behavior is unchanged — widget and handler names are
  identical, guarded by the new smoke test.

- **Lint and annotation hygiene: project ruff baseline from 30 findings to zero**
  Extraneous f-string prefixes in `cleaner.py` and `converter_worker.py`,
  import ordering across eight files, `typing.Callable` →
  `collections.abc.Callable` in `ffmpeg_utils.py`, a needless bool in
  `is_playlist_url()`, a misnumbered step comment in `find_binary()`, and
  mutable class defaults / unused unpacks / a `dict()` call in the test
  suite. The intentional catch-all `except Exception` guards at every
  worker `run()` boundary — which exist to route *any* failure into the
  failed/error signal — are kept and marked with justified `noqa`
  comments instead of being narrowed, since narrowing could let new
  exception types escape uncaught and crash the worker thread.

### Fixed

- **Worker threads could be destroyed mid-shutdown or lingered after use** (`app/window.py`)
  All five worker types (download, playlist inspect, info, audio convert,
  video convert) are parentless QThreads owned by Python: the moment the
  last reference disappears, the C++ object is deleted immediately — but
  completion handlers fire *inside* run(), before the thread has exited,
  so dropping the last reference there (`self.worker = None`, or
  overwriting the attribute with the next worker) could destroy a QThread
  still winding down ("QThread: Destroyed while thread is still running").
  Every worker is now pinned in a tracked set from creation (attribute
  writes are unconditionally safe) and released via finished →
  deleteLater → destroyed right after its thread exits. `self.worker` is
  also initialized in `__init__` and cleared at batch end, replacing the
  fragile `hasattr()` guard.

- **Single video with a `list=` parameter downloaded the whole playlist** (`app/yt_dlp_opts.py`, `app/window.py`)
  Pasting a video URL opened from inside a playlist page
  (`youtube.com/watch?v=X&list=Y`) was classified as a full playlist: the
  queue showed a playlist label, a slow size inspection with confirmation
  dialog ran, and the download fetched every playlist entry instead of the
  one video. Playlist detection now actually parses YouTube URLs — only
  `playlist?list=` URLs are playlists; `watch?v=`/`youtu.be/ID` URLs that
  merely carry a `list=` parameter download exactly that one video
  (`noplaylist=True`). Non-YouTube hosts keep the existing behavior.

- **Loudness scan decoded video streams and hung on long files** (`app/ffmpeg_utils.py`, `app/converter_worker.py`)
  `probe_loudness()` ran the EBU R128 first pass without `-vn`, so measuring
  a video file decoded its entire video stream just to read audio loudness
  — the audio conversion itself already used `-vn`, making the scan the
  slowest step by far. The scan now skips video, checks ffmpeg's exit code
  (clear error messages instead of a bare "no JSON in output"), raises a
  readable RuntimeError on timeout instead of a raw `TimeoutExpired`
  traceback, and its timeout scales with the file's duration
  (at least 300s) so long podcasts/audiobooks don't hit a false ceiling.

- **`MainWindow.height` shadowed the inherited `QWidget.height()` method** (`app/window.py`)
  The downloader's resolution setting was stored as `self.height`, which
  shadows Qt's built-in `height()` method — harmless at runtime because it
  is always assigned before use, but fragile and confusing for static
  analysis (caught by the project-wide diagnostics sweep). Renamed to
  `self.dl_height` and initialized in `__init__`.

- **Impersonation missing from CI-built executables** (`.github/workflows/*`, `chrisnov-media-toolkit.spec`)
  The three build workflows did not install `curl_cffi`, so released binaries
  hit the guarded ImportError in `build_cookie_opts()` and silently shipped
  without Chrome impersonation — breaking browser-cookie downloads for
  Instagram/Vimeo private in every CI build (local builds were unaffected).
  All workflows now install `curl_cffi` and drop the leftover `awscli` from
  the removed R2 upload step; the PyInstaller spec also lists `curl_cffi` in
  `hiddenimports` so it is always bundled.

- **Cancel race in the converter tabs** (`app/window.py`)
  `_conv_cancel()` and `_video_conv_cancel()` now disconnect the worker's
  signals before cancelling (mirroring `_cancel_download()`). Previously, a
  `finished_ok`/`failed` signal still in flight when Cancel was clicked could
  arrive after the UI reset, calling `_conv_kick_next()` and starting the
  next file's conversion even though the user had cancelled.

- **Queue changes during a running batch were silently discarded** (`app/window.py`)
  Drag-and-drop, the converter's Files/Folder/Remove/Clear buttons, and the
  downloader's Remove/Clear all stayed active while a batch was running, but
  additions never reached the running snapshot and were wiped by the queue
  reset. Dropped URLs/files during an active batch now get an explanatory
  dialog, the queue-editing buttons are disabled while a batch runs, and a
  history re-queue during a download leaves the URL in the input box to add
  after the queue finishes.

- **Windows installer script was broken in three ways** (`installer.nsi`, `app/ffmpeg_utils.py`, `main.py`)
  `installer.nsi` could not compile at all: `MUI_PAGE_WELCOME` was inserted
  twice, the mandatory license page referenced a `LICENSE` file that does not
  exist in the repo, and the `File` command pointed at
  `dist\chrisnov-media-toolkit.exe` — an artifact the build never produces
  (the spec outputs `-lite.exe` / `-bundled.exe`). The optional FFmpeg
  component also installed into a `bin\` folder the frozen app never
  looked in. The script now compiles (single welcome page, license page only
  when built with `-DPRODUCT_LICENSE=<file>`, version overridable with
  `-DPRODUCT_VERSION=<x>`), packages the actual Lite build under a stable
  installed name, drops the dead `icon.svg` install (the icon is already
  embedded in the exe), and the optional FFmpeg component genuinely works:
  `find_binary()` and the PATH setup in `main.py` now also search a `bin\`
  folder placed next to the frozen executable.

- **Playlist history entries stored raw worker payloads as the filename** (`app/window.py`)
  Completed playlist downloads recorded their internal payload string
  (e.g. `playlist_files:["C:\\...\\song1.mp3", ...]`) as the history `filename`,
  so the History tab showed a wall of JSON paths with a `0 B` size, and
  double-clicking a playlist entry opened the *parent* of the output
  folder. Playlist entries now store a readable label
  (`Playlist — 12 file(s)` or `Playlist: <title> — 5 item(s)`) together with
  the real total size of the downloaded files; double-clicking opens the
  output folder itself. Legacy entries with payload filenames are rewritten
  to a plain "Playlist" label on load.

- **Cancel during the EBU R128 loudness scan left ffmpeg running as an orphan** (`app/ffmpeg_utils.py`, `app/converter_worker.py`)
  The first-pass loudness scan ran via blocking `subprocess.run`, which the
  converter's cancel path could not terminate — cancel() could only set a
  flag, so cancelling mid-scan made the UI hard-terminate the QThread while
  the ffmpeg scan kept running with nobody waiting on it. `probe_loudness()`
  now runs via `Popen` with a poll loop that checks the worker's cancelled
  flag every 100 ms (mirroring `run_ffmpeg_with_progress`): the scan
  process is registered with the worker so `cancel()` terminates it
  directly, the poll loop terminates → waits → kills if the process ignores
  SIGTERM, and the same `RuntimeError("Cancelled.")` the conversion passes
  use propagates cleanly. The loudnorm JSON is buffered to a temp file, so
  the scan can also never block on a full stderr pipe. The old
  `subprocess.run`-based unit tests were ported to the new interface, plus
  new tests for the cancel, timeout-kill, and missing-JSON paths.

- **Tab "icons" were font-dependent text glyphs** (`app/window.py`, `app/icon.py`)
  The four tab labels carried Unicode glyphs (⬇ ♫ ▣ 📋) whose rendering
  depends entirely on which symbol fonts the user's system ships — the
  Video Converter's ▣ (U+25A3) showed up as a plain box on Linux Mint,
  and the others risked tofu boxes elsewhere. Tabs now use bundled line-art
  SVG icons (inline in `app/icon.py` — no asset files, nothing extra to
  ship in the frozen builds), rendered in the current palette's text
  color and re-rendered on Light/Dark mode switches.

- **About dialog always showed FFmpeg as "n/a"** (`app/window.py`, `app/ffmpeg_utils.py`)
  The version probe read ffmpeg's output from stderr, but `ffmpeg -version`
  prints its banner to stdout — so the row showed "n/a" on every system
  where FFmpeg was installed and on PATH (e.g. Linux Mint's apt build).
  It also looked up the bare binary name instead of the app's own
  resolution order, and would have returned the whole copyright line
  rather than just the version number. The About row now reports the
  version of the exact binary the app itself uses (PyInstaller bundle →
  bin/ beside the exe → project bin/ → system PATH, via the new
  `probe_version()` helper), e.g. `6.1.1-3ubuntu5`.

- **Deprecated Qt 5 enum/attribute access in the theming module** (`app/theme.py`)
  `QPalette.Window`-style shorthand is superseded by the scoped
  `QPalette.ColorRole.*` form, and the two HiDPI application attributes
  enabled at startup (`AA_EnableHighDpiScaling` / `AA_UseHighDpiPixmaps`)
  are deprecated no-ops in Qt 6 that newer PySide6 stubs stop exposing —
  together these were the last genuine (non-stub) pyright errors in the
  project. The shorthand accesses are now scoped properly,
  `widget_stylesheet()` reads the palette via the static
  `QGuiApplication.palette()` (no instance lookup needed), and the HiDPI
  attributes are only set when they still exist, so the call site in
  `main.py` stays valid on any Qt version.

### Removed

- **Dead theming helpers** (`app/theme.py`)
  `is_dark_mode()` — whose "modern" Qt 6.5 check read
  `app.property("colorScheme")`, a property Qt never sets, so it always
  fell through to the palette heuristic — and `refresh_palette()` were never
  called from anywhere (the UI adapts to Light/Dark Mode purely through the
  palette-driven `widget_stylesheet()` re-applied in `changeEvent()`).
  Both were removed along with the unused `_is_dark_palette()` helper and the
  unused `QColor` import.

---

## [0.2.0-beta.2] — 2026-08-07

**Highlights:** readable macOS fonts + Retina/HiDPI scaling, native Dark Mode
support, and browser-cookie logins (Instagram private, Vimeo private, etc.)
that now actually work — plus a significant internal refactor and new unit
tests.

### Fixed

- **Font too small on macOS** (`main.py`, `app/window.py`, `app/theme.py`)
  The 9pt base font introduced in v0.1.0-beta.5 was too small for macOS,
  especially on MacBook Air 13-inch (Early 2015) which runs at 1280×800.
  Added `app/theme.py` with platform-aware font sizing (11pt on macOS,
  9pt on Linux/Windows) and macOS-native font family (`.SF NS Text`,
  `-apple-system`). Also enabled `Qt.AA_EnableHighDpiScaling` and
  `Qt.AA_UseHighDpiPixmaps` before QApplication creation for proper
  Retina/Display scaling on macOS.

- **Dark Mode not adapting** (`app/theme.py`, `app/window.py`)
  All widget colors were hardcoded as light-mode hex values, so the UI
  did not adapt when macOS switched to Dark Mode. Replaced the hardcoded
  stylesheet in `MainWindow._apply_style()` with a palette-aware version
  from `theme.py` that dynamically reads colors from `QPalette`. Added
  a `MainWindow.changeEvent()` handler that re-applies the palette-aware
  stylesheet on `QEvent.PaletteChange` and `QEvent.ColorSchemeChange`
  (Qt 6.5+) so the UI adapts at runtime without a restart.

- **Cookie options not applied to yt-dlp** (`app/worker.py`,
  `app/yt_dlp_opts.py`)
  During the worker refactor the cookie options were found to use
  non-canonical yt-dlp keys (`cookies_from_browser` / `cookies`) that yt-dlp
  silently ignores, so authenticated content (Instagram private, Vimeo
  private, etc.) never actually used the configured cookies. Corrected to the
  canonical `cookiesfrombrowser` / `cookiefile` keys in the shared
  `build_cookie_opts()` helper.

### Added

- **`app/theme.py`** — Centralized theming module:
  `enable_high_dpi()`, `_base_font_size()`, `_font_family()`,
  `is_dark_mode()`, `global_stylesheet()`, `widget_stylesheet()`,
  `_palette_color()`, `_is_dark_palette()`.

- **Unit tests for `app/ffmpeg_utils` and `app/yt_dlp_opts`**
  (`tests/test_ffmpeg_utils.py`, `tests/test_yt_dlp_opts.py`)
  Cover binary discovery, duration/loudness probing, output-path
  resolution, progress-aware ffmpeg execution (including cancellation),
  and the shared yt-dlp option builders (cookie/impersonation, format
  opts, dry-run opts) extracted during the workers refactor.

### Changed

- **Embed metadata checkbox default** (`app/window.py`)
  The "Embed metadata" checkbox in the Downloader tab now defaults to
  unchecked (matching the default video mode). When the user checks
  "Audio only", the checkbox is automatically checked — ID3 tag embedding
  benefits audio files and avoids manual tag editing later. Unchecking
  "Audio only" automatically unchecks the metadata checkbox again.
  Video downloads no longer embed metadata by default.

- **Workers refactored into shared helpers** (`app/base_worker.py`,
  `app/ffmpeg_utils.py`, `app/yt_dlp_opts.py`, `app/worker.py`,
  `app/converter_worker.py`)
  Introduced a shared `CancellableWorker(QThread)` base class (one
  cancellation pattern for all workers) and extracted the duplicated
  FFmpeg helpers (`find_ffmpeg`/`find_ffprobe`, `probe_duration`,
  `probe_loudness`, output-path resolution, progress-aware execution) and the
  duplicated yt-dlp cookie/impersonation/format-option builders into dedicated
  modules. Net effect: less duplication and a single source of truth for
  option construction. No user-visible behavior change is intended (beyond the
  cookie-key fix listed above).

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

## [0.1.0-beta.4] - 2026-07-16

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
