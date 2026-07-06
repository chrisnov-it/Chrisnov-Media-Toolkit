# Mengenal Chrisnov Media Toolkit: Downloader dan Converter Media Ringan untuk Windows dan Linux

Saya sedang mengembangkan sebuah aplikasi kecil bernama **Chrisnov Media Toolkit**. Aplikasi ini berawal dari kebutuhan sederhana: punya downloader media yang ringan, mudah dipakai, dan tidak membuat pengguna non-teknis harus berurusan langsung dengan command line.

Dalam proses pengembangan, fiturnya berkembang. Selain downloader berbasis `yt-dlp`, aplikasi ini sekarang juga punya audio converter dan video converter berbasis FFmpeg. Jadi, untuk tahap beta awal ini, Chrisnov Media Toolkit sudah bisa dipakai sebagai alat bantu harian untuk download, ekstrak audio, convert audio, dan convert video lokal.

Saat ini aplikasi masih dalam tahap **internal beta**, dengan build pertama:

```text
v0.1.0-beta.1-windows-x64
```

Download beta Windows x64:

```text
https://dl.chrisnov.com/app/windows/chrisnov-media-toolkit-v0.1.0-beta.1-windows-x64.exe
```

SHA256:

```text
3346B887E5DFD63E7DCFE65A0A25A690C29771967868FED32A212A1BAAC037D6
```

Walaupun belum rilis publik, fitur utamanya sudah fungsional dan sedang diuji di Windows 11. Target awalnya adalah cross-platform untuk **Windows** dan **Linux Mint**.

## Fitur Utama

Chrisnov Media Toolkit saat ini punya tiga tab utama:

1. **Downloader**
2. **Audio Converter**
3. **Video Converter**

### Downloader

Fitur Downloader memakai `yt-dlp`, jadi mendukung YouTube dan banyak situs lain yang juga didukung oleh yt-dlp.

Fitur yang sudah tersedia:

- Download video dari URL.
- Mode **Audio only** untuk mengambil audio saja.
- Pilihan resolusi: Best, 1080p, 720p, 480p, 360p.
- Pilihan container video: mp4, mkv, webm.
- Pilihan format audio: mp3, m4a, opus.
- Pilihan bitrate audio: 96 sampai 320 kbps.
- Batch queue untuk banyak URL.
- Playlist support.
- Skip duplicate memakai download archive.
- Drag-and-drop URL atau file teks berisi daftar URL.
- Clean title untuk membersihkan tag seperti `Official Music Video`, `Video Lirik`, dan sejenisnya.

### Audio Converter

Audio Converter dipakai untuk mengubah file audio lokal atau mengambil audio dari file video lokal.

Fitur yang sudah tersedia:

- Input audio dan video lokal.
- Output: mp3, m4a, opus, flac, wav.
- Add files dan Add folder.
- Batch conversion.
- Pilihan CBR/VBR untuk format lossy.
- Pilihan bitrate.
- Pilihan sample rate.
- EBU R128 loudness normalization.
- Peak normalize.
- Trim silence.
- Progress real-time dari FFmpeg.
- Cancel yang menghentikan proses FFmpeg dengan lebih aman.

Fitur **Add folder** berguna untuk kasus seperti convert satu folder album atau koleksi file audio sekaligus.

### Video Converter

Video Converter dipakai untuk convert video lokal ke format umum.

Fitur yang sudah tersedia:

- Input: mp4, mkv, webm, avi, mov, wmv, flv, ts, m4v.
- Output: mp4, mkv, webm.
- Preset kualitas:
  - Keep quality
  - Balanced
  - Smaller file
- Add files dan Add folder.
- Batch conversion.
- Opsi **Keep original audio when possible**.
- Fallback otomatis ke AAC/Opus kalau audio asli tidak kompatibel dengan container output.
- Progress real-time dari FFmpeg.
- Cancel conversion.

## Kenapa Dibuat?

Saya ingin aplikasi yang ringan dan langsung ke fungsi utama. Banyak aplikasi media converter komersial terasa besar atau terlalu banyak fitur yang tidak selalu diperlukan. Untuk kebutuhan dasar seperti download video, ambil audio, convert folder album, atau convert video pendek, aplikasi sederhana seperti ini lebih nyaman.

Selain itu, aplikasi ini dirancang agar tetap ramah untuk laptop low-spec. Pengujian awal dilakukan di mesin dengan spesifikasi sederhana, dan hasilnya cukup ringan untuk workflow harian.

## Panduan Penggunaan di Windows

Mayoritas pengujian awal difokuskan di Windows 11, jadi build Windows menjadi prioritas pertama.

### 1. Siapkan FFmpeg

Chrisnov Media Toolkit beta ini adalah versi **Lite**, jadi masih membutuhkan
FFmpeg terinstall di Windows untuk proses merge video/audio dan conversion.
Nanti bisa saja ada versi Bundled yang sudah menyertakan FFmpeg, tetapi ukuran
file-nya akan jauh lebih besar.

Cara install FFmpeg di Windows:

```powershell
winget install Gyan.FFmpeg
```

Setelah install, tutup dan buka ulang terminal atau restart aplikasi.

Untuk memastikan FFmpeg sudah tersedia:

```powershell
ffmpeg -version
```

### 2. Jalankan Aplikasi

Untuk build beta Windows, file yang digunakan:

```text
chrisnov-media-toolkit-v0.1.0-beta.1-windows-x64.exe
```

Download:

```text
https://dl.chrisnov.com/app/windows/chrisnov-media-toolkit-v0.1.0-beta.1-windows-x64.exe
```

Cukup double-click file tersebut. Tidak perlu install Python.

### 3. Download Video

Langkah dasar:

1. Buka tab **Downloader**.
2. Paste URL video.
3. Klik **Add to queue**.
4. Pilih resolusi dan container.
5. Pilih output folder jika perlu.
6. Klik **Start**.

Untuk download audio saja:

1. Centang **Audio only**.
2. Pilih format audio, misalnya mp3 atau m4a.
3. Pilih bitrate.
4. Klik **Start**.

Secara default, folder output akan otomatis pindah ke `Music` saat Audio only aktif, dan kembali ke `Videos` saat mode video.

### 4. Convert Audio atau Ekstrak Audio dari Video

Langkah dasar:

1. Buka tab **Audio Converter**.
2. Klik **Add files...** atau **Add folder...**.
3. Pilih output format, misalnya mp3, m4a, flac, atau wav.
4. Atur bitrate, sample rate, atau normalization jika perlu.
5. Pilih output folder.
6. Klik **Convert**.

Jika input berupa file video, aplikasi akan mengambil audionya saja.

### 5. Convert Video

Langkah dasar:

1. Buka tab **Video Converter**.
2. Klik **Add files...** atau **Add folder...**.
3. Pilih output format: mp4, mkv, atau webm.
4. Pilih quality preset.
5. Biarkan **Keep original audio when possible** aktif jika ingin proses lebih efisien.
6. Klik **Convert**.

Untuk penggunaan umum, preset **Balanced** adalah pilihan aman.

## Panduan Singkat untuk Linux Mint

Di Linux Mint, aplikasi bisa dijalankan dari source terlebih dahulu.

Install dependency:

```bash
sudo apt install ffmpeg python3-venv
```

Setup environment:

```bash
cd ~/dev/Chrisnov-Media-Toolkit
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install PySide6 yt-dlp
.venv/bin/python main.py
```

Untuk build binary Linux:

```bash
bash build-linux.sh
```

Output build Linux:

```text
dist/chrisnov-media-toolkit
```

Catatan: PyInstaller harus dijalankan di OS target. Jadi build Windows dibuat di Windows, dan build Linux dibuat di Linux.

## Catatan Beta

Build ini masih beta, jadi hasil di setiap sistem bisa berbeda tergantung:

- Versi Windows atau Linux.
- Ketersediaan FFmpeg.
- Driver dan codec sistem.
- Perbedaan behavior yt-dlp untuk situs tertentu.
- Antivirus atau security policy Windows.

Untuk saat ini build dibuat tanpa UPX. Ukuran file memang sedikit lebih besar, tetapi ini lebih aman untuk mengurangi risiko false positive antivirus. Dalam pengujian, UPX hampir tidak mengurangi ukuran binary, jadi tidak layak dipakai untuk build beta ini.

Build Windows saat ini juga belum menyertakan FFmpeg. Ini membuat ukuran aplikasi
lebih kecil, tetapi pengguna tetap perlu menginstall FFmpeg sendiri. Ke depan,
kemungkinan akan ada dua varian: **Lite** untuk pengguna yang sudah punya FFmpeg
dan **Bundled** untuk pengguna awam yang ingin langsung pakai tanpa setup
tambahan.

## Rencana Pengembangan

Beberapa fitur yang sedang dipertimbangkan:

- Version label dan About dialog di dalam aplikasi.
- Video compression preset yang lebih jelas.
- Trim/cut audio dan video.
- Filename cleanup untuk file lokal tanpa conversion.
- Download history.
- Queue import/export.
- Settings lokal untuk menyimpan preferensi folder dan format.
- Build Linux yang lebih rapi.
- GitHub Release internal ketika beta mulai dibagikan ke tester.

## Penutup

Chrisnov Media Toolkit masih dalam tahap awal, tapi fondasinya sudah cukup kuat untuk pengujian internal. Fokusnya bukan menjadi aplikasi media super kompleks, melainkan alat yang ringan, jelas, dan praktis untuk kebutuhan download serta convert media sehari-hari.

Untuk tahap berikutnya, saya akan lanjut menguji build Windows, menyiapkan build Linux, dan memperbaiki UX berdasarkan hasil penggunaan nyata.
