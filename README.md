# Chrisnov Media Toolkit

Minimal cross-platform **media downloader and converter** built with PySide6, yt-dlp, and FFmpeg. Paste a link from YouTube, Vimeo, Dailymotion, Instagram, TikTok, or 1000+ other sites and download or convert it — no Python needed to use the app. Lightweight enough for low-spec laptops (tested on Intel i5-5200U / 8GB RAM / Intel HD 5500).

**Requirements for the prebuilt app:** Windows 10/11 · macOS 12 (Monterey) or newer · Linux (Debian/Ubuntu-based). No Python or terminal required for end users.

> **Bahasa Indonesia?** Lompat ke [Panduan Pengguna (Bahasa Indonesia)](#panduan-pengguna-bahasa-indonesia).

---

## 🚀 Quick Start (no technical knowledge needed)

No terminal, no Python. You only need to download the right file and double-click it.

### 1. Get the app

Go to the [Releases page](https://github.com/chrisnov-it/Chrisnov-Media-Toolkit/releases) and download the file for your computer:

| Your computer | Download this | Notes |
|---|---|---|
| Windows (most PCs) | `...-windows-x64-lite.zip` | |
| Windows (no FFmpeg installed) | `...-windows-x64-bundled.zip` | Bigger, but FFmpeg is included |
| Mac with Apple chip (M1/M2/M3...) | `...-macos-arm64-lite.zip` | |
| Mac with Intel chip | `...-macos-x86_64-lite.zip` | e.g. older MacBooks |
| Linux | `...-linux-x64-lite.tar.gz` | |

### 2. Install and open the app

**Windows**
1. Right-click the `.zip` → **Extract All…** → choose a folder → **Extract**.
2. Open that folder and **double-click** the `.exe` inside.
3. If Windows shows *“Windows protected your PC”*: click **More info** → **Run anyway**. This is normal for unsigned beta builds — the app is safe to use.

**macOS**
1. Download the correct `.zip` for your Mac and double-click it to extract **Chrisnov Media Toolkit.app**.
2. If macOS says the app *“cannot be opened”*: **right-click** the app → **Open** → **Open** again. Normal for unsigned builds.

**Linux**
1. Extract the `.tar.gz`, then make the file runnable:
   ```bash
   chmod +x chrisnov-media-toolkit-lite
   ```
2. Double-click **chrisnov-media-toolkit-lite** (or run it from a terminal).

### 3. Your first download
1. Open the app.
2. Choose an **Output folder** (defaults are `~/Videos` for video, `~/Music` for audio — the app remembers your choice).
3. Paste a video or playlist link into the box.
4. Click **Start**. That’s it — progress and speed show at the bottom.

Want an explanation of every button? See [Using the app](#using-the-app) or the [Indonesian guide](#panduan-pengguna-bahasa-indonesia).

---

## 💻 For users comfortable with the terminal (run from source)

If you’d rather run the app from source (development, custom builds, or the latest code), you’ll set this up once. You need a little familiarity with your terminal.

### What you need
- **Python 3.12**
- **FFmpeg** (needed for downloads that remux and for all conversions)
- **Git** (to clone the repository)

### Linux (Debian / Ubuntu / Pop!_OS / Linux Mint)
```bash
sudo apt install ffmpeg python3-venv git

git clone https://github.com/chrisnov-it/Chrisnov-Media-Toolkit.git
cd Chrisnov-Media-Toolkit
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install PySide6 yt-dlp curl_cffi
.venv/bin/python main.py
```

### Windows 11 (PowerShell)
```powershell
# Install FFmpeg once (choose one):
winget install Gyan.FFmpeg

# Then clone and run:
git clone https://github.com/chrisnov-it/Chrisnov-Media-Toolkit.git
cd Chrisnov-Media-Toolkit
py -m venv .venv
.venv\Scripts\pip install -U pip
.venv\Scripts\pip install PySide6 yt-dlp curl_cffi
.venv\Scripts\python main.py
```

### macOS (from source)
```bash
# Install Homebrew first (https://brew.sh), then:
brew install ffmpeg python@3.12

git clone https://github.com/chrisnov-it/Chrisnov-Media-Toolkit.git
cd Chrisnov-Media-Toolkit
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install PySide6 yt-dlp curl_cffi
.venv/bin/python main.py
```

### Keep yt-dlp updated (all OSes, inside the virtual env)
```bash
.venv/bin/pip install -U yt-dlp curl_cffi
```
(On Windows: `.venv\Scripts\pip install -U yt-dlp curl_cffi`)

---

## Using the app

### Downloader tab
- **Start / URL box** — paste one or more links (one per line) and click **Start**. Progress shows as e.g. `[2/5] Downloading… 45% @ 2.3 MB/s`.
- **Info** — shows the video title, duration, and an estimated output size *before* you download.
- **Audio only** — downloads just the sound (no video). Choose `mp3`/`m4a`/`opus` and a **bitrate** (96–320 kbps). For music, 192 kbps is already very good.
- **Resolution** — Best / 1080p / 720p / 480p / 360p.
- **Container** — `mp4`/`mkv`/`webm` for video; `mp3`/`m4a`/`opus` for audio.
- **Clean title** — strips tags like “Official Music Video”, “Video Lirik”, etc. from filenames. Add your own tags (comma-separated) in the box.
- **Browse / Open** — choose the output folder / open it in your file manager.
- **Embed metadata & thumbnail** — writes title/artist tags; can embed cover art (mp3, m4a, mp4, mkv). Thumbnail is off by default.
- **Use browser cookies / Cookie file…** — for private or age-restricted content (Instagram private, Vimeo limited). See FAQ.
- **Skip duplicates** — defaults on: skips things you already downloaded (great for resuming a stopped batch).
- **Playlists** — paste a playlist URL (YouTube/Vimeo/Dailymotion); large playlists (>50 entries) ask for confirmation with a size estimate.
- **Batch queue** — add many URLs and download them one after another; cancel mid-batch anytime.
- **History** — search/filter past downloads by name or URL, and by type. Double-click a ✅ to open the folder, or a ❌ to re-download.

### Audio Converter tab
Convert local audio files — or pull the audio out of local videos — to **mp3, m4a, opus, flac, or wav**. Options: bitrate, sample rate, loudness normalization (EBU R128), trim silence, and **Add folder…** to batch a whole album.

### Video Converter tab
Convert local videos to **mp4, mkv, or webm**. Quality presets: **Keep quality / Balanced / Smaller file**. “Keep original audio when possible” keeps your existing audio track when the container supports it.

### Drag & drop
Drop a URL, some text, or a `.txt` file of URLs (one per line) onto the window to add them to the queue. Lines starting with `#` are ignored.

### Where files are saved
The app remembers the last output folder you chose for each mode. The defaults are `~/Videos` (video) and `~/Music` (audio). Click **Open** next to **Browse** to jump straight to that folder.

---

## FAQ / Troubleshooting

**Q: I click Start but nothing happens.**
- Make sure the URL box is not empty and the link starts with `http://` or `https://`.
- Read the message in the status bar at the bottom of the window — it usually explains the error.

**Q: Downloaded video has audio but no picture (or vice‑versa).**
- Almost always FFmpeg is missing. Linux: `sudo apt install ffmpeg`. Windows: `winget install Gyan.FFmpeg` then restart the app.
- Re‑download the same item (Skip duplicates allows overwriting if the archive file is removed).

**Q: Filenames still have “(Official Music Video)” or other tags.**
- Make sure **Clean title** is checked.
- If your tag isn’t in the default list, type it in the text box (comma-separated).

**Q: I cancelled mid‑batch. How do I continue without re‑downloading?**
- Click **Start** again. **Skip duplicates** skips files already in the archive.
- To re‑download from scratch, delete the archive file:
  ```bash
  rm ~/.config/chrisnov-media-toolkit/archive_audio.txt   # or archive_video.txt
  ```

**Q: Where are my downloads saved?**
- In the output folder you chose (defaults: `~/Videos` for video, `~/Music` for audio). The app remembers your last folder per mode. Click **Open** to see it.

**Q: Dailymotion / Vimeo / Instagram fail to download.**
- These sites block default requests; the app handles them via browser impersonation (enabled automatically when cookies are used).
- For private/authenticated content: check **Use browser cookies**, or click **Cookie file…** and pick a `cookies.txt` exported from your browser.
- Running from source? Ensure `curl_cffi` is installed: `pip install curl_cffi`.

**Q: How do I get a cookies.txt file from my browser?**
- **Chrome/Edge:** install the *“Get cookies.txt”* extension, open the page you want, click the extension and save.
- **Firefox:** use the *“Cookie-Editor”* extension and export as cookies.txt.
- Files from Brave/Opera etc. usually work too.

**Q: Is site X supported?**
- Check the full list: `yt-dlp --list-extractors`. If it’s supported by yt-dlp, this app supports it. Some sites need impersonation (already built‑in) and/or cookies.

**Q: Does the app send my data anywhere?**
- No. Everything runs locally on your computer. yt-dlp only talks to YouTube/CDN like a browser does when playing a video.

**Q: Unsigned/“recognized developer” warnings on macOS?**
- Expected for beta builds without a paid code‑signing certificate. Right‑click → **Open** to run; the app is safe.

---

## For developers / building standalone executables

Building standalone executables, the project layout, and the internal architecture are documented in [`docs/BUILDING.md`](docs/BUILDING.md).

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Panduan Pengguna (Bahasa Indonesia)

Panduan lengkap dalam Bahasa Indonesia — termasuk cara pakai, pengaturan, dan FAQ — tersedia di [blog kami](https://chrisnov.com/blog/chrisnov-media-toolkit).

### Tips Cepat

| Mau apa? | Caranya |
|---|---|
| Unduh musik dari YouTube | Centang **Audio only**, pilih format mp3/m4a, klik Start |
| Unduh beberapa video sekaligus | Tambahkan satu per satu ke antrian, baru klik Start |
| Unduh seluruh playlist | Tempel link playlist langsung — semua episode otomatis masuk antrian |
| Hapus tag "(Official Music Video)" dari nama file | Pastikan **Clean title** dicentang |
| Unduh dari Dailymotion/Instagram/Vimeo | Sudah didukung! Pastikan `curl_cffi` terinstall |
| Unduh konten private (Instagram/Vimeo) | Centang **Use browser cookies** atau pilih cookie file |
| Lanjutkan unduhan yang sempat dibatalkan | Klik Start lagi — yang sudah diunduh otomatis dilewati |
| Lihat riwayat unduhan | Buka tab **History**, cari/filter berdasarkan nama atau tipe file |
| Buka folder file yang pernah diunduh | Tab **History**, double-click item yang statusnya ✅ |
| Download ulang file yang gagal | Tab **History**, double-click item yang statusnya ❌ |
| Ubah folder tujuan | Klik **Browse...** di samping kolom Output folder |
| Convert satu folder album | Buka **Audio Converter**, klik **Add folder...**, pilih output, klik Convert |
