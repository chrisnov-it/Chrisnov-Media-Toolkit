# Chrisnov YT Downloader

Minimal cross-platform GUI for `yt-dlp`, built with PySide6. Lightweight enough
for low-spec laptops (tested on Intel i5-5200U / 7GB RAM / Intel HD 5500).

## Features

- Paste any yt-dlp-supported URL (YouTube and 1000+ sites)
- **Audio-only mode** — extracts soundtrack with selectable bitrate (96/128/160/192/256/320 kbps)
- **Title cleanup** — strips "Official Music Video" etc. from filenames (editable tag list in GUI)
- Resolution presets: Best / 1080p / 720p / 480p / 360p
- Container choice: mp4 / mkv / webm (video) or mp3 / m4a / opus (audio)
- **Batch queue** — add many URLs, removes the need to babysit each download
- **Playlist support** — paste a `youtube.com` or `music.youtube.com` playlist URL and the whole list expands. Large playlists (>50 entries) ask for confirmation with a size estimate.
- **Skip duplicates** — yt-dlp `download_archive` keeps a history file at `~/.config/chrisnov-yt-downloader/archive_*.txt`
  (separate for audio vs video). Anything re-queued gets skipped automatically.
- **Drag-and-drop** — drop a URL, text, or a text file of URLs onto the window
- Pick output folder (defaults to `~/Videos` or `%USERPROFILE%\Videos`)
- Live progress + speed (per item, e.g. "[2/5] Downloading...")
- Cancel mid-batch

## Setup

### Linux Mint (and other Debian/Ubuntu)

```bash
sudo apt install ffmpeg python3-venv
cd ~/dev/chrisnov-yt-downloader
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install PySide6 yt-dlp
.venv/bin/python main.py
```

### Windows 11

```powershell
# Install ffmpeg first (winget or choco), e.g.:
winget install Gyan.FFmpeg

cd %USERPROFILE%\dev\chrisnov-yt-downloader
py -m venv .venv
.venv\Scripts\pip install -U pip
.venv\Scripts\pip install PySide6 yt-dlp
.venv\Scripts\python main.py
```

## Project layout

```
chrisnov-yt-downloader/
├── main.py              # entry point
├── icon.svg             # app icon (SVG)
├── app/
│   ├── constants.py     # presets, container lists, threshold
│   ├── cleaner.py       # clean_title, rename_with_cleanup, discover_new_files
│   ├── worker.py        # DownloadWorker (QThread subclass)
│   ├── window.py        # MainWindow (GUI)
│   └── icon.py          # load_svg_icon helper
└── .venv/               # Python venv with PySide6 + yt-dlp
```

## Architecture

GUI runs in the main thread; downloads happen in `DownloadWorker` (`QThread`)
so the UI stays responsive. The worker uses yt-dlp's Python API directly
(`YoutubeDL.extract_info(download=True)`), passing `download_archive` for
de-duplication and a `progress_hooks` callback for live status updates.

After each download completes, `MainWindow._on_item_ok` calls
`rename_with_cleanup` (single file) or `discover_new_files` + loop
(playlist batch) to apply user-configured title cleanup on disk.

Playlist mode is auto-detected via `list=` in the URL. Before kicking
off any playlist >50 entries, `_confirm_playlists` does a dry `extract_info`
to count and asks for confirmation with a size estimate.

## Notes

- Skip-duplicates archive lives at `~/.config/chrisnov-yt-downloader/archive_audio.txt`
  (or `archive_video.txt`). Delete these files to re-download from scratch.
- No GPU mode change needed. Intel Power Saving is fine for this GUI.
- yt-dlp is bundled via the venv, so a system yt-dlp install is optional.
- To update yt-dlp later: `.venv/bin/pip install -U yt-dlp`
- App icon: `icon.svg` (auto-loaded from project root). To customise, replace that file with any valid SVG.
- On Windows 11 the taskbar gets the same icon automatically (via AppUserModelID).

## License

Private use.

## FAQ / Troubleshooting

**Q: I clicked Start but nothing happens.**
- Check the URL field — it must start with `http://` or `https://`.
- Look at the bottom status bar; errors and updates are written there.
- Try clicking Down arrow or scroll the status area to read past output.

**Q: Downloaded video has no sound (or no video).**
- Almost always means `ffmpeg` isn't installed. On Linux:
  `sudo apt install ffmpeg`. On Windows: `winget install Gyan.FFmpeg`,
  then restart the app.
- Re-download the same video. Skip-duplicates will let it overwrite the
  previous version (only when the archive file has been cleared).

**Q: The download file still has "(Official Music Video)" in the filename.**
- Make sure the "Clean title" checkbox is **ticked**.
- Edit the tag list textbox — add whatever tags you want stripped (separate with commas).
- The title-cleanup runs **after** download. Status bar will say
  `"Cleaned N file(s), ..."` if it worked; if no file got renamed, no strip was needed.

**Q: I cancelled mid-batch. How do I resume without re-downloading everything?**
- Just hit Start again. The **Skip duplicates** checkbox uses yt-dlp's
  archive file at `~/.config/chrisnov-yt-downloader/archive_audio.txt`
  (or `archive_video.txt`). Anything already in the archive is skipped on
  the next run.
- To re-download everything from scratch, delete the relevant archive file:
  ```bash
  rm ~/.config/chrisnov-yt-downloader/archive_audio.txt
  ```

**Q: Drag-and-drop a text file but IDs weren't added.**
- The file must contain one URL per line, or one URL separated by spaces.
- Lines starting with `#` are ignored.

**Q: Where is the app icon on my Linux taskbar?**
- After first launch, the app should appear in the menu. Restart Cinnamon's
  menu cache if needed:
  ```bash
  # Linux Mint Cinnamon:
  xdg-desktop-menu forceupdate
  ```

**Q: Application failed to start with "xcb-cursor0" error on Linux.**
- Install the system package: `sudo apt install libxcb-cursor0`

**Q: I want to integrate into my own scripts.**
- Use `yt-dlp` directly — it has a stable CLI: `yt-dlp -S "res:720,f:mp4" <url>`.
  This GUI is just thin packaging around it.

**Q: Does the app upload my data anywhere?**
- No. Everything runs locally. yt-dlp sends standard HTTP requests to
  YouTube/cDNs just as a browser would when playing videos.

## Use

1. Run `.venv/bin/python main.py` (Linux/Mac) or
   `.venv\Scripts\python main.py` (Windows). A window titled
   **Chrisnov YT Downloader** opens.
2. Paste a video URL (YouTube or 1000+ other supported sites) into the URL
   field, then press **Enter** or click **Add to queue**.
3. Choose your options:
   - **Audio only** checkbox — extract soundtrack (mp3/m4a/opus), with bitrate.
   - **Resolution** — pick 1080p / 720p / etc. (or "Best").
   - **Container** — mp4/mkv/webm (or mp3/m4a/opus for audio).
   - **Clean title** — strip "Official Music Video" etc.
   - **Output folder** — defaults to `~/Videos`.
4. Hit **Start** to begin downloading.
5. Watch the status bar at the bottom for live progress, speed, and rename feedback.

For friends / non-technical users:

- Just open the app, paste a link, click Start. That's it.
- For music-only: tick **Audio only**, leave the rest on defaults.
- The window, status messages, and status bar should be enough guidance.
- If something looks wrong, talk them through the **FAQ** section above — most
  questions come up there.
