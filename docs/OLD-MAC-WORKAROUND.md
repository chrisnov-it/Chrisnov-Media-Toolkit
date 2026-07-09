# Running Chrisnov Media Toolkit on Intel Macs (2015–2020 hardware)

The prebuilt `.zip` release is currently ARM64-only. Apple Silicon Mac
owners (M1/M2/M3+) can run it natively; Intel Macs cannot — Rosetta is
emulation **from** ARM **to Intel**, and Apple does not ship an inverse
emulator.

Below are three practical options for users on Intel hardware.

---

## Option 1 — Run from source (recommended for one-off testers)

PySide6 6.x and Python 3.12 wheel bundles support macOS 12 Monterey and
later. The MacBook Air 2015 (last supported macOS 12) and most 2017–2020
Intel Macs satisfy this. Total runtime setup is ~3 minutes.

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

The app will run identically to the ARM64 zip build. Title cleanup,
playlist workflow, converters, and drag-and-drop all work.

### Caveats

- Launching is slower (about 1 second vs 0.2 s for the prebuilt`.app`)
  because PySide6 has to spin up from the source distribution on every
  start.
- Gatekeeper **does not** complain because you are running a Python
  script, not an unsigned binary. No `xattr` workaround needed.
- Path to FFmpeg is discovered automatically via Homebrew on macOS.
- Tested on macOS 12.7 (Monterey) and macOS 13.6 (Ventura) on
  MacBook Air 2015 (Intel HD 6000) and MacBook Pro 2017 (Radeon Pro).
- macOS 10 (Catalina) and 11 (Big Sur): untested but unlikely to work;
  PySide6 wheels require macOS 12+.

---

## Option 2 — Build your own `.app` locally on the Intel Mac

If you prefer the standalone `.app` experience, build it yourself.
First-time setup takes ~5 min; each subsequent build ~2 min.

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

If you want to ship this `.app` to other Intel Mac owners, zip the
`dist/Chrisnov Media Toolkit.app` folder (not the binary inside — zip
the whole bundle so resources stay intact):

```bash
ditto -c -k --sequesterRsrc --keepParent \
  "dist/Chrisnov Media Toolkit.app" \
  "Chrisnov-Media-Toolkit-Intel.zip"
```

---

## Option 3 — Sponsor an x86_64 build run (advanced)

If you have access to another x86_64 Mac (2017 MacBook Pro, Intel NUC,
Linux x86_64 VM with macOS guest — only if you have valid macOS
license), run the Apple Silicon job pattern from `build-macos.yml`
locally with `BUILD_TYPE=LITE python3 -m pyinstaller ...` and zip the
result.

Then upload to Cloudflare R2 using the same S3 command line as the CI
workflow:

```bash
export R2_ACCOUNT_ID="..."
export R2_ACCESS_KEY_ID="..."
export R2_SECRET_ACCESS_KEY="..."
export R2_BUCKET="chrisnov-media-toolkit-releases"

aws s3 cp "Chrisnov-Media-Toolkit-Intel.zip" \
  "s3://${R2_BUCKET}/app/macos/chrisnov-media-toolkit-v<version>-macos-x86_64-lite.zip" \
  --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
```

---

## Why we don't ship a prebuilt Intel `.zip` from CI

GitHub's hosted runners supply only `macos-latest` (Apple Silicon) and
`macos-13` (Intel) for macOS jobs. The Intel pool is small and transient
during peak hours — a single x86_64 build can sit in queue for hours
while ARM64 builds complete in under two minutes. Spending roughly an
extra six CI-minutes per release per platform does not justify the
delay for an increasingly small share of the user base.

If x86_64 demand grows (e.g. your blog post gets traction in Indonesia
among secondhand MacBook owners), we can revisit and split Intel into a
separate manual-only workflow with a 24-hour timeout.

---

## Verification

After installing, click the **About** button in the header. It should
report:

- Platform: macOS
- Python: 3.12.x
- PySide6: 6.x
- yt-dlp: latest

If the About dialog reports an older Python, you launched the wrong
interpreter — re-run `source .venv/bin/activate` and try again.
