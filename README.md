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
(O n Windows: `.venv\Scripts\pip install -U yt-dlp curl_cffi`)

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

## 🔧 For developers / building a standalone executable

Produces a single self-contained binary — end users don’t need Python.

> **Cross‑compile limitation:** PyInstaller must run on the **target OS**. Build the Linux binary on Linux, and the Windows `.exe` on Windows. If you dual‑boot, run the matching script on each OS.

### Linux
```bash
bash build-linux.sh
# Output: dist/chrisnov-media-toolkit
```

### Windows
```powershell
# In PowerShell from the project root:
Set-ExecutionPolicy -Scope Process Bypass
.\build-windows.ps1
# Outputs: dist\chrisnov-media-toolkit-vX.Y.Z-windows-x64-lite.zip
#          dist\chrisnov-media-toolkit-vX.Y.Z-windows-x64-bundled.zip
```
Each `.zip` contains the standalone `.exe`. For a custom Windows icon, place `icon.ico` in the project root before building; without it the `.exe` uses the default icon (the in‑app window still uses `icon.svg`).

### macOS
Prebuilt `.zip`s are produced by `.github/workflows/build-macos.yml` and attached to GitHub Releases for both Apple Silicon (`-macos-arm64-lite.zip`) and Intel (`-macos-x86_64-lite.zip`). The CI pins a macOS deployment target of 12.0 so Intel builds run on older Macs (e.g. 2015 MacBook Air). See `docs/OLD-MAC-WORKAROUND.md` for Intel‑Mac specifics and SHA256 verification.

> **File size:** ~50–90 MB is normal — it bundles Python, PySide6, and yt-dlp. UPX is avoided because packed executables can trigger antivirus false positives.

### Project layout
```
Chrisnov-Media-Toolkit/
├── main.py               # entry point
├── icon.svg              # app icon (SVG)
├── app/
│   ├── constants.py      # APP_VERSION, presets, container lists, thresholds
│   ├── cleaner.py        # clean_title, rename_with_cleanup, discover_new_files
│   ├── base_worker.py    # CancellableWorker — shared QThread base with cancel()
│   ├── yt_dlp_opts.py    # Shared yt-dlp option builders (cookies, format, dry-run)
│   ├── ffmpeg_utils.py   # FFmpeg binary discovery, probing, progress-aware execution
│   ├── worker.py         # DownloadWorker, PlaylistInspectWorker, FileSizeWorker
│   ├── converter_worker.py # ConvertWorker, VideoConvertWorker (FFmpeg-based)
│   ├── window.py         # MainWindow (GUI)
│   └── icon.py           # load_svg_icon helper
└── .venv/                # Python venv with PySide6 + yt-dlp
```

### Shared utilities (extracted to reduce duplication)
- **`base_worker.py`** — `CancellableWorker` provides the `_cancelled` flag, `cancel()`, and `cancelled` property. All 5 worker classes inherit from it; converter workers override `cancel()` to also terminate their FFmpeg subprocess.
- **`yt_dlp_opts.py`** — centralizes yt-dlp options: `build_cookie_opts()` (cookie + impersonation), `build_format_opts()` (format/outtmpl/postprocessors), `build_dry_opts()` (metadata‑only), `_thumbnail_supported()` / `_extra_postprocessors()`.
- **`ffmpeg_utils.py`** — centralizes FFmpeg ops: `find_ffmpeg()`/`find_ffprobe()` (PyInstaller → local → PATH), `probe_duration()`/`probe_loudness()`, `resolve_output_path()`, `run_ffmpeg_with_progress()` (progress parsing, cancellation, range mapping).

### Architecture
GUI runs in the main thread; downloads happen in `DownloadWorker` (a `QThread`) so the UI stays responsive. The worker uses yt-dlp’s Python API directly (`YoutubeDL.extract_info(download=True)`), passing `download_archive` for de‑duplication, `progress_hooks` for live status, `impersonate` for browser mimicry, and cookie options for authenticated content. After each download, `MainWindow._on_item_ok` applies title cleanup on disk. Local conversion uses FFmpeg via `ConvertWorker`/`VideoConvertWorker`, which parse `ffmpeg -progress` for live progress and terminate the FFmpeg subprocess on Cancel. Playlists >50 entries trigger a dry `extract_info` count and a confirmation dialog.

### Notes
- Skip‑duplicates archive: `~/.config/chrisnov-media-toolkit/archive_audio.txt` (or `archive_video.txt`). Delete these to re‑download from scratch.
- Download history: `~/.config/chrisnov-media-toolkit/download-history.json` (capped at 1,000 entries).
- `curl_cffi` is required for browser impersonation: `pip install curl_cffi`.
- yt-dlp is bundled via the venv; a system yt-dlp isn’t required.
- App icon: `icon.svg` in the project root (any valid SVG). On Windows 11 the taskbar uses it automatically.

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Panduan Pengguna (Bahasa Indonesia)

> Panduan ini ditujukan untuk pengguna yang belum terbiasa dengan aplikasi download.
> Tidak perlu install Python atau membuka terminal — ikuti langkah di bawah saja.

### Cara Pakai untuk Pengguna Biasa

1. Buka halaman artikel resmi untuk panduan download:  
   [https://chrisnov.com/blog/chrisnov-media-toolkit](https://chrisnov.com/blog/chrisnov-media-toolkit)
2. Download file `.zip` yang sesuai sistem kamu:
   - `chrisnov-media-toolkit-vX.Y.Z-windows-x64-lite.zip`
   - `chrisnov-media-toolkit-vX.Y.Z-windows-x64-bundled.zip`
3. Klik kanan file `.zip` → **Extract All…** → pilih folder tujuan, lalu klik **Extract**.
4. Buka folder hasil ekstraksi, lalu **double-click** file `.exe` yang ada di dalamnya.
5. Jika muncul peringatan **Windows protected your PC** dari SmartScreen:
   - Klik **More info** → **Run anyway**.
   - Peringatan ini normal untuk aplikasi beta yang belum memiliki sertifikat digital. Aplikasi ini aman digunakan.

Setelah aplikasi terbuka, ikuti langkah penggunaan di bagian **Tips Cepat** atau baca
penjelasan setiap tombol di **Pengaturan yang Perlu Diketahui**.

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
| Convert video lokal | Buka **Video Converter**, tambah file/folder, pilih format dan kualitas, klik Convert |

### Pengaturan yang Perlu Diketahui

**Audio only** — Kalau dicentang, aplikasi hanya mengambil suaranya saja (tidak
ada gambar/video). Cocok untuk menyimpan lagu. Format default: mp3. Bisa diganti
ke m4a atau opus di dropdown Container.

**Bitrate** — Kualitas audio. Angka lebih besar = suara lebih jernih = file lebih
besar. Untuk musik, 192 kbps sudah sangat baik. 320 kbps untuk kualitas maksimal.

**Resolution** — Resolusi video. "Best" = kualitas terbaik yang tersedia. 720p
sudah cukup untuk kebanyakan layar laptop.

**Info** — Tombol di sebelah **Start**. Menampilkan judul video, durasi, dan
perkiraan ukuran hasil unduh tanpa benar-benar mengunduh. Berguna untuk
memperkirakan pemakaian disk.

**Embed metadata / Embed thumbnail** — Menulis tag (judul, artis) ke dalam
file hasil unduh. "Embed thumbnail" menyematkan gambar mini ke file (tersedia
untuk mp3, m4a, mp4, mkv). Metadata otomatis memakai judul lagu yang bersih
bila tersedia.

**Open** — Tombol di samping **Browse**. Membuka folder tujuan yang sedang
dipilih di file manager sistem kamu.

**Clean title** — Menghapus tag seperti "Official Music Video", "Video Lirik", dll.
dari nama file secara otomatis. Bisa tambah tag sendiri di kotak teksnya (pisahkan
dengan koma).

**Use browser cookies** — Aktifkan untuk mengunduh konten yang memerlukan
login/autentikasi (Instagram private, Vimeo terbatas, dll.). App akan otomatis
mengambil cookies dari browser Chrome.

**Cookie file...** — Alternatif dari browser cookies, Anda bisa load cookie dari
file `cookies.txt` yang diexport dari browser.

**Skip duplicates** — Kalau dicentang (default), video/lagu yang pernah diunduh
sebelumnya akan dilewati otomatis. Berguna saat melanjutkan unduhan yang berhenti
di tengah jalan.

**Audio Converter** — Mengubah file audio atau mengambil audio dari video lokal.
Format output: mp3, m4a, opus, flac, wav. Bisa pilih bitrate, sample rate,
normalization, trim silence, dan Add folder untuk batch album.

**Video Converter** — Mengubah video lokal ke mp4, mkv, atau webm. Preset
kualitas: Keep quality, Balanced, Smaller file. Opsi "Keep original audio when
possible" menjaga audio asli jika container mendukungnya.

**History** — Tab **History** mencatat semua unduhan (berhasil/gagal) dengan
nama file, ukuran, waktu, dan status. Cari berdasarkan nama file atau URL, filter
berdasarkan tipe (Audio/Video/Playlist). Double-click item yang ✅ untuk buka
folder, atau ❌ untuk download ulang. Riwayat dibatasi 1.000 entri terbaru agar
tidak memakan storage berlebihan.

### FAQ / Troubleshooting

**Q: Saya klik Start tapi tidak ada yang terjadi.**
- Pastikan kolom URL sudah terisi dan diawali dengan `http://` atau `https://`.
- Lihat pesan di bagian bawah jendela (status bar) — biasanya ada keterangan error.

**Q: Video yang diunduh tidak ada suaranya (atau tidak ada gambarnya).**
- Hampir pasti `ffmpeg` belum terpasang. Di Linux: `sudo apt install ffmpeg`.
  Di Windows: `winget install Gyan.FFmpeg`, lalu restart aplikasi.
- Unduh ulang video yang sama — Skip duplicates akan mengizinkan overwrite
  (asal file archive sudah dihapus).

**Q: Nama file masih ada "(Official Music Video)" atau tag lain.**
- Pastikan centang **Clean title** aktif.
- Kalau tag-nya tidak ada di daftar default, ketik sendiri di kotak teks di
  bawah centang Clean title (pisah dengan koma). Contoh: tambahkan `Video Klip`
  atau `Lirik Lagu`.

**Q: Saya batalkan di tengah batch. Bagaimana lanjutkan tanpa unduh ulang?**
- Klik Start lagi. **Skip duplicates** akan melewati file yang sudah ada di archive.
- Untuk mengunduh ulang dari awal, hapus file archive:
  ```bash
  rm ~/.config/chrisnov-media-toolkit/archive_audio.txt
  # atau
  rm ~/.config/chrisnov-media-toolkit/archive_video.txt
  ```

**Q: Drag-and-drop file teks tapi URL tidak masuk.**
- File harus berisi satu URL per baris.
- Baris yang diawali `#` diabaikan.

**Q: Di mana file hasil unduhan disimpan?**
- Di folder tujuan yang kamu pilih (default `~/Videos` untuk video, `~/Music`
  untuk audio pada pemakaian pertama). Folder terakhir otomatis diingat untuk
  tiap mode, jadi tidak kembali ke default di pemakaian berikutnya.
- Klik tombol **Open** di sebelah **Browse** untuk langsung membukanya.

**Q: Ikon aplikasi tidak muncul di taskbar Linux.**
- Restart cache menu Cinnamon:
  ```bash
  xdg-desktop-menu forceupdate
  ```

**Q: Error "xcb-cursor0" saat membuka aplikasi di Linux.**
- Jalankan: `sudo apt install libxcb-cursor0`

**Q: Apakah data saya dikirim ke mana-mana?**
- Tidak. Semua berjalan di komputer lokal. yt-dlp hanya menghubungi
  YouTube/CDN seperti browser biasa saat memutar video.

**Q: Saya ingin integrasikan ke script sendiri.**
- Gunakan `yt-dlp` langsung via CLI: `yt-dlp -S "res:720,f:mp4" <url>`.
  Aplikasi ini hanya tampilan GUI di atasnya.

**Q: Dailymotion/Vimeo/Instagram gagal diunduh.**
- Pastikan `curl_cffi` terinstall: `pip install curl_cffi`.
- Platform-platform ini memblokir request default yt-dlp, jadi butuh browser
  impersonation yang sudah ditambahkan di app.
- Untuk konten private (Instagram akun private, Vimeo video terbatas):
  - Centang **"Use browser cookies"** di UI, atau
  - Klik **"Cookie file..."** dan pilih file `cookies.txt` dari browser Anda

**Q: Bagaimana cara export cookies dari browser?**
- **Chrome/Edge:** Gunakan extension "Get cookies.txt" dari Chrome Web Store.
  Buka halaman yang ingin diunduh, klik extension, dan save cookies.
- **Firefox:** Gunakan extension "Cookie-Editor" dan export sebagai cookies.txt.
- File cookies.txt dari browser lain (Brave, Opera, dll.) biasanya juga kompatibel.

**Q: Apakah platform X didukung?**
- Cek daftar lengkap: `yt-dlp --list-extractors`
- App ini mendukung **semua platform yang didukung yt-dlp**
- Beberapa platform butuh impersonation (sudah aktif) dan/atau cookies
