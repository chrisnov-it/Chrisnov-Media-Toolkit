# Chrisnov YT Downloader

Minimal cross-platform GUI for `yt-dlp`, built with PySide6. Lightweight enough
for low-spec laptops (tested on Intel i5-5200U / 7GB RAM / Intel HD 5500).

## Features

- Paste any yt-dlp-supported URL (YouTube and 1000+ sites)
- **Audio-only mode** — extracts soundtrack with selectable bitrate (96/128/160/192/256/320 kbps)
- **Smart output folder** — automatically switches to `~/Music` when Audio only is on,
  back to `~/Videos` when off (only if you haven't manually changed the folder)
- **Title cleanup** — strips "Official Music Video", "Video Lirik", etc. from filenames
  (editable tag list in GUI; includes common Indonesian tags out of the box)
- Resolution presets: Best / 1080p / 720p / 480p / 360p
- Container choice: mp4 / mkv / webm (video) or mp3 / m4a / opus (audio)
- **Batch queue** — add many URLs, removes the need to babysit each download
- **Playlist support** — paste a `youtube.com` or `music.youtube.com` playlist URL and
  the whole list expands. Large playlists (>50 entries) ask for confirmation with a size
  estimate.
- **Skip duplicates** — yt-dlp `download_archive` keeps a history file at
  `~/.config/chrisnov-yt-downloader/archive_*.txt` (separate for audio vs video).
  Anything re-queued gets skipped automatically.
- **Drag-and-drop** — drop a URL, text, or a text file of URLs onto the window
- Pick output folder (defaults to `~/Videos` or `~/Music` depending on mode)
- Live progress + speed (per item, e.g. "[2/5] Downloading...")
- Cancel mid-batch
- Queue clears automatically after each batch finishes

## Building a standalone executable

Produces a single self-contained binary — no Python installation required for end-users.

> **Cross-compile limitation:** PyInstaller must run on the **target OS**.
> Build the Linux binary on Linux, and the Windows `.exe` on Windows.
> If you dual-boot, run the matching script on each OS.

### Linux (single-file binary)

```bash
bash build-linux.sh
# Output: dist/chrisnov-yt-downloader  (~70 MB)
```

### Windows (single-file .exe)

```powershell
# In PowerShell from the project root:
Set-ExecutionPolicy -Scope Process Bypass
.\build-windows.ps1
# Output: dist\chrisnov-yt-downloader.exe  (~80-90 MB)
```

The Windows script installs Pillow automatically to convert `icon.svg` to `.ico`
for the taskbar icon. If you prefer, drop a hand-crafted `icon.ico` in the project
root and change the `icon=` line in `chrisnov-yt-downloader.spec` accordingly.

> **Note on file size:** The binary bundles Python, PySide6, and yt-dlp.
> ~70-90 MB is normal. Install UPX (`sudo apt install upx` / `choco install upx`)
> before building to shrink it by ~30%.

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

For audio-only downloads, `yt-dlp` first saves the raw stream (e.g. `.webm`),
then `FFmpegExtractAudio` converts it to the chosen container (`.mp3`, `.m4a`,
`.opus`). The worker corrects the path extension before passing it to the
rename step so cleanup always targets the actual file on disk.

Playlist mode is auto-detected via `list=` in the URL. Before kicking
off any playlist >50 entries, `_confirm_playlists` does a dry `extract_info`
to count and asks for confirmation with a size estimate.

## Notes

- Skip-duplicates archive lives at `~/.config/chrisnov-yt-downloader/archive_audio.txt`
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
   Jendela berlabel **Chrisnov YT Downloader** akan muncul.

2. Buka YouTube (atau situs lain yang didukung) di browser, lalu salin link videonya
   (klik kanan pada video → *Copy video URL*, atau salin dari address bar).

3. Tempel link tersebut ke kolom **Video URL** di aplikasi, lalu tekan **Enter**
   atau klik **Add to queue**.

4. Pilih mode unduhan:
   - Mau **video**? Biarkan semua pengaturan pada default.
   - Mau **audio/musik saja**? Centang **Audio only** — aplikasi otomatis
     pindahkan folder tujuan ke `~/Music` dan pilihkan format audio.

5. Klik **Start**. Lihat progress bar dan pesan di bagian bawah jendela.

6. Setelah selesai, file tersimpan di:
   - `~/Videos` — untuk video
   - `~/Music` — untuk audio

7. Daftar antrian otomatis bersih setelah semua selesai diunduh.

### Tips Cepat

| Mau apa? | Caranya |
|---|---|
| Unduh musik dari YouTube | Centang **Audio only**, pilih format mp3/m4a, klik Start |
| Unduh beberapa video sekaligus | Tambahkan satu per satu ke antrian, baru klik Start |
| Unduh seluruh playlist | Tempel link playlist langsung — semua episode otomatis masuk antrian |
| Hapus tag "(Official Music Video)" dari nama file | Pastikan **Clean title** dicentang |
| Lanjutkan unduhan yang sempat dibatalkan | Klik Start lagi — yang sudah diunduh otomatis dilewati |
| Ubah folder tujuan | Klik **Browse...** di samping kolom Output folder |

### Pengaturan yang Perlu Diketahui

**Audio only** — Kalau dicentang, aplikasi hanya mengambil suaranya saja (tidak
ada gambar/video). Cocok untuk menyimpan lagu. Format default: mp3. Bisa diganti
ke m4a atau opus di dropdown Container.

**Bitrate** — Kualitas audio. Angka lebih besar = suara lebih jernih = file lebih
besar. Untuk musik, 192 kbps sudah sangat baik. 320 kbps untuk kualitas maksimal.

**Resolution** — Resolusi video. "Best" = kualitas terbaik yang tersedia. 720p
sudah cukup untuk kebanyakan layar laptop.

**Clean title** — Menghapus tag seperti "Official Music Video", "Video Lirik", dll.
dari nama file secara otomatis. Bisa tambah tag sendiri di kotak teksnya (pisahkan
dengan koma).

**Skip duplicates** — Kalau dicentang (default), video/lagu yang pernah diunduh
sebelumnya akan dilewati otomatis. Berguna saat melanjutkan unduhan yang berhenti
di tengah jalan.

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
  rm ~/.config/chrisnov-yt-downloader/archive_audio.txt
  # atau
  rm ~/.config/chrisnov-yt-downloader/archive_video.txt
  ```

**Q: Drag-and-drop file teks tapi URL tidak masuk.**
- File harus berisi satu URL per baris.
- Baris yang diawali `#` diabaikan.

**Q: Di mana file hasil unduhan disimpan?**
- Video: `~/Videos` (atau folder yang kamu pilih manual)
- Audio: `~/Music` (otomatis saat Audio only diaktifkan)

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
