# Running Chrisnov Media Toolkit on Intel Macs (2015–2020 hardware)

Chrisnov Media Toolkit now ships prebuilt `.zip` releases for both
Apple Silicon (`*-macos-arm64-lite.zip`) and Intel
(`*-macos-x86_64-lite.zip`) Macs. The x86_64 build runs on GitHub's
`macos-15-intel` runner and is published alongside the ARM64 zip on
every release.

If you have a MacBook Air 2015, MacBook Pro 2017, or any other 2015–2020
Intel Mac running macOS 12 Monterey or later, the prebuilt x86_64 zip
is the recommended path.

---

## Option 1 — Download the prebuilt x86_64 zip (recommended)

1. Visit the [Releases page](https://github.com/chrisnov-it/Chrisnov-Media-Toolkit/releases)
   on GitHub.
2. Download `chrisnov-media-toolkit-v<version>-macos-x86_64-lite.zip`
   under the latest release.
3. Double-click the zip to extract `Chrisnov Media Toolkit.app`.
4. Drag the `.app` into your Applications folder.
5. Right-click the `.app` → **Open** the first time (Gatekeeper
   warning, because the binary is unsigned). Subsequent launches are
   normal double-click.

Install FFmpeg once via Homebrew — the Lite build does not bundle it:

```bash
brew install ffmpeg
```

FFmpeg is discovered automatically on macOS.

### Verifying the download

Each release zip ships with a `.sha256` checksum file. Verify your
download before extracting:

```bash
shasum -a 256 -c chrisnov-media-toolkit-v<version>-macos-x86_64-lite.zip.sha256
```

Output should end with `OK`.

### System requirements

- macOS 12 Monterey or later (macBook Air 2015's last supported OS)
- ~250 MB free disk space for the unpacked `.app`
- Internet access for downloads and `yt-dlp` fetches
- FFmpeg on `$PATH` (Homebrew install above)

---

## Option 2 — Run from source

Useful if you want the latest unreleased code, or if the prebuilt zip
is blocked by your network or admin policy. PySide6 6.x and Python 3.12
wheels support macOS 12 Monterey and later. Setup is ~3 minutes.

```bash
# Open Terminal and ensure Xcode CLI tools are installed
xcode-select --install

# Install Homebrew's Python 3.12 (NOT Apple's bundled Python 3.9)
brew install python@3.12

# Install FFmpeg (Lite build does not bundle it)
brew install ffmpeg

# Get the source code
git clone https://github.com/chrisnov-it/Chrisnov-Media-Toolkit.git
cd Chrisnov-Media-Toolkit

python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip PySide6 yt-dlp

python main.py
```

The app runs identically to the prebuilt `.app`. Title cleanup,
playlist workflow, converters, and drag-and-drop all work.

### Caveats

- Launching is slower (about 1 second vs 0.2 s for the prebuilt `.app`)
  because PySide6 has to spin up from the source distribution on every
  start.
- Gatekeeper **does not** complain because you are running a Python
  script, not an unsigned binary. No `xattr` workaround needed.
- Tested on macOS 12.7 (Monterey) and macOS 13.6 (Ventura) on
  MacBook Air 2015 (Intel HD 6000) and MacBook Pro 2017 (Radeon Pro).
- macOS 10 (Catalina) and 11 (Big Sur): untested and unlikely to work;
  PySide6 wheels require macOS 12+.

---

## Option 3 — Build your own `.app` locally

If you want a standalone `.app` matching the exact CI artifact, build
it yourself. First-time setup takes ~5 min; each subsequent build
~2 min on Intel hardware.

```bash
brew install python@3.12 ffmpeg pyinstaller

git clone https://github.com/chrisnov-it/Chrisnov-Media-Toolkit.git
cd Chrisnov-Media-Toolkit

python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip PySide6 yt-dlp pyinstaller

pyinstaller chrisnov-media-toolkit.spec
open "dist/Chrisnov Media Toolkit.app"
```

The first launch needs right-click → Open because the binary is
unsigned (Gatekeeper warning). Subsequent launches are double-click
normal.

---

## CI configuration

The x86_64 zip is built by `.github/workflows/build-macos.yml` using
a matrix over two runners:

- `macos-latest` → Apple Silicon (M1/M2/M3+)
- `macos-15-intel` → x86_64 Intel (4 vCPU / 14 GB RAM, supported
  until August 2027)

Each matrix leg publishes a separate zip and uploads it to Cloudflare
R2 under `app/macos/`. Both legs complete in roughly 3 minutes total
when run in parallel.

### Why we paused the Intel build (now resumed)

GitHub's older `macos-13` Intel runner was retired in December 2025;
builds on that image could queue for hours. The replacement
`macos-15-intel` runner has more CPU and RAM than the Apple Silicon
runner and a much shorter queue, so resuming the x86_64 leg became
worthwhile.

---

## Verification

After installing (any option above), click the **About** button in the
header. It should report:

- Platform: macOS
- Python: 3.12.x
- PySide6: 6.x
- yt-dlp: latest

If the About dialog reports an older Python, you launched the wrong
interpreter — re-run `source .venv/bin/activate` and try again.
