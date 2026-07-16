# Chrisnov Media Toolkit

Minimal cross-platform media downloader and converter built with PySide6,
`yt-dlp`, and FFmpeg. Lightweight enough for low-spec laptops (tested on Intel
i5-5200U / 7GB RAM / Intel HD 5500).

## Features

- Paste any yt-dlp-supported URL (YouTube and 1000+ sites)
- **Audio-only mode** — extracts soundtrack with selectable bitrate (96/128/160/192/256/320 kbps)
- **Remembers last folder** — the output folder you picked for each mode
  (video download, audio download, audio convert, video convert) is saved and
  restored the next time you open the app. No more falling back to defaults
  every launch.
- **Open Folder button** — opens the currently selected output directory in
  your system file manager, on all three tabs.
- **Pre-download info** — the **Info** button shows the video title, duration,
  and an estimated output size before you start downloading.
- **Embed metadata & thumbnail** — writes title/artist tags into the file
  (on by default) and can embed the cover thumbnail (off by default). Thumbnail
  embedding is available for mp3, m4a, mp4, and mkv.
- **Title cleanup** — strips "Official Music Video", "Video Lirik", etc. from filenames
  (editable tag list in GUI; includes common Indonesian tags out of the box)
- Resolution presets: Best / 1080p / 720p / 480p / 360p
- Container choice: mp4 / mkv / webm (video) or mp3 / m4a / opus (audio)
- **Batch queue** — add many URLs, removes the need to babysit each download
- **Playlist support** — paste a `youtube.com` or `music.youtube.com` playlist URL and
  the whole list expands. Large playlists (>50 entries) ask for confirmation with a size
  estimate.
- **Skip duplicates** — yt-dlp `download_archive` keeps a history file at
  `~/.config/chrisnov-media-toolkit/archive_*.txt` (separate for audio vs video).
  Anything re-queued gets skipped automatically.
- **Drag-and-drop** — drop a URL, text, or a text file of URLs onto the window
- Pick output folder (defaults to `~/Videos` or `~/Music` on first run)
- Live progress + speed (per item, e.g. "[2/5] Downloading...")
- Cancel mid-batch
- Queue clears automatically after each batch finishes
- **Audio converter** — batch convert local audio/video files to mp3, m4a,
  opus, flac, or wav
- **Video converter** — batch convert local videos to mp4, mkv, or webm with
  simple quality presets
- **Add folder** — add supported media from a folder tree for batch conversion

## Building a standalone executable

Produces a single self-contained binary — no Python installation required for end-users.

> **Cross-compile limitation:** PyInstaller must run on the **target OS**.
> Build the Linux binary on Linux, and the Windows `.exe` on Windows.
> If you dual-boot, run the matching script on each OS.

### Linux (single-file binary)

```bash
bash build-linux.sh
# Output: dist/chrisnov-media-toolkit
```

### Windows (single-file .exe)

```powershell
# In PowerShell from the project root:
Set-ExecutionPolicy -Scope Process Bypass
.\build-windows.ps1
# Output: dist\chrisnov-media-toolkit.exe  (~53 MB in current builds)
```

For a custom Windows executable icon, place a hand-crafted `icon.ico` in the
project root before building. Without it, the `.exe` builds with the default
Windows application icon; the in-app window icon still uses `icon.svg`.

> **Note on file size:** The binary bundles Python, PySide6, and yt-dlp.
> ~50-90 MB is normal depending on OS and dependency versions. The build scripts
> currently avoid requiring UPX because packed executables can trigger antivirus
> false positives more often than unpacked PyInstaller builds.

### macOS (prebuilt zip)

Prebuilt `.zip` releases are produced by `.github/workflows/build-macos.yml`
and attached to GitHub Releases for both Apple Silicon
(`-macos-arm64-lite.zip`) and Intel (`-macos-x86_64-lite.zip`).
See [`docs/OLD-MAC-WORKAROUND.md`](docs/OLD-MAC-WORKAROUND.md) for
Intel-Mac instructions and SHA256 verification.

## Setup

### Linux Mint (and other Debian/Ubuntu)

```bash
sudo apt install ffmpeg python3-venv
cd ~/dev/Chrisnov-Media-Toolkit
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install PySide6 yt-dlp
.venv/bin/python main.py
```

### Windows 11

```powershell
# Install ffmpeg first (winget or choco), e.g.:
winget install Gyan.FFmpeg

cd %USERPROFILE%\dev\Chrisnov-Media-Toolkit
py -m venv .venv
.venv\Scripts\pip install -U pip
.venv\Scripts\pip install PySide6 yt-dlp
.venv\Scripts\python main.py
```

## Project layout

```
Chrisnov-Media-Toolkit/
├── main.py              # entry point
├── icon.svg             # app icon (SVG)
├── app/
│   ├── constants.py     # presets, container lists, threshold
│   ├── cleaner.py       # clean_title, rename_with_cleanup, discover_new_files
│   ├── worker.py        # DownloadWorker (QThread subclass)
│   ├── converter_worker.py # FFmpeg audio/video converter workers
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

For audio-only downloads, `yt-dlp` first saves the raw stream (e.g. `.webm`),
then `FFmpegExtractAudio` converts it to the chosen container (`.mp3`, `.m4a`,
`.opus`). The worker corrects the path extension before passing it to the
rename step so cleanup always targets the actual file on disk.

Playlist mode is auto-detected via `list=` in the URL. Before kicking
off any playlist >50 entries, `_confirm_playlists` does a dry `extract_info`
to count and asks for confirmation with a size estimate.

Local audio/video conversion uses FFmpeg through `ConvertWorker` and
`VideoConvertWorker`. The workers parse `ffmpeg -progress` output for live
progress updates and terminate the FFmpeg subprocess when Cancel is clicked.

## Notes

- Skip-duplicates archive lives at `~/.config/chrisnov-media-toolkit/archive_audio.txt`
  (or `archive_video.txt`). Delete these files to re-download from scratch.
- No GPU mode change needed. Intel Power Saving is fine for this GUI.
- yt-dlp is bundled via the venv, so a system yt-dlp install is optional.
- To update yt-dlp later: `.venv/bin/pip install -U yt-dlp`
- App icon: `icon.svg` (auto-loaded from project root). To customise, replace that file
  with any valid SVG.
- On Windows 11 the taskbar gets the same icon automatically (via AppUserModelID).

## License

Private use.

---

## Panduan Pengguna (Non-Technical)

> Panduan ini ditujukan untuk pengguna yang belum terbiasa dengan aplikasi download.
> Tidak perlu paham teknis — ikuti langkah di bawah saja.

### Cara Pakai (Langkah Dasar)

1. Buka aplikasi dengan menjalankan `main.py` (atau klik shortcut kalau sudah dibuat).
   Jendela berlabel **Chrisnov Media Toolkit** akan muncul.

2. Buka YouTube (atau situs lain yang didukung) di browser, lalu salin link videonya
   (klik kanan pada video → *Copy video URL*, atau salin dari address bar).

3. Tempel link tersebut ke kolom **Video URL** di aplikasi, lalu tekan **Enter**
   atau klik **Add to queue**.

4. Pilih mode unduhan:
   - Mau **video**? Biarkan semua pengaturan pada default.
   - Mau **audio/musik saja**? Centang **Audio only** — aplikasi otomatis
     menyesuaikan folder tujuan dan memilihkan format audio.

5. (Opsional) Klik **Info** untuk melihat judul, durasi, dan perkiraan ukuran
   file sebelum mengunduh.

6. Klik **Start**. Lihat progress bar dan pesan di bagian bawah jendela.

7. Setelah selesai, file tersimpan di folder tujuan yang dipilih. Klik **Open**
   di sebelah tombol Browse untuk langsung membukanya di file manager.

8. Daftar antrian otomatis bersih setelah semua selesai diunduh.

### Tips Cepat

| Mau apa? | Caranya |
|---|---|
| Unduh musik dari YouTube | Centang **Audio only**, pilih format mp3/m4a, klik Start |
| Unduh beberapa video sekaligus | Tambahkan satu per satu ke antrian, baru klik Start |
| Unduh seluruh playlist | Tempel link playlist langsung — semua episode otomatis masuk antrian |
| Hapus tag "(Official Music Video)" dari nama file | Pastikan **Clean title** dicentang |
| Lanjutkan unduhan yang sempat dibatalkan | Klik Start lagi — yang sudah diunduh otomatis dilewati |
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

**Skip duplicates** — Kalau dicentang (default), video/lagu yang pernah diunduh
sebelumnya akan dilewati otomatis. Berguna saat melanjutkan unduhan yang berhenti
di tengah jalan.

**Audio Converter** — Mengubah file audio atau mengambil audio dari video lokal.
Format output: mp3, m4a, opus, flac, wav. Bisa pilih bitrate, sample rate,
normalization, trim silence, dan Add folder untuk batch album.

**Video Converter** — Mengubah video lokal ke mp4, mkv, atau webm. Preset
kualitas: Keep quality, Balanced, Smaller file. Opsi "Keep original audio when
possible" menjaga audio asli jika container mendukungnya.

---

## FAQ / Troubleshooting

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
