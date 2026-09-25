# Third-party components and licence obligations

Chrisnov Media Toolkit itself is MIT licensed — see [LICENSE](../LICENSE).
Two groups of redistributed components carry their own terms.

## FFmpeg / FFprobe (bundled builds only)

- The Windows **bundled** build embeds `ffmpeg.exe` + `ffprobe.exe` inside the
  executable, and the NSIS installer can drop them into the app's `bin/`
  folder as an optional component.
- `build-windows.ps1` either copies the binaries it finds on the build host's
  `PATH` or downloads the official `yt-dlp/FFmpeg-Builds`
  `ffmpeg-master-latest-win64-gpl.zip` archive. Downloads are verified against
  the release's published `checksums.sha256` before they are packaged.
- That archive is a **GPL** build (the `-gpl` suffix), so redistributing a
  bundled build obliges you to:
  1. ship FFmpeg's licence text next to the distributed binary — keep
     `bin/FFMPEG-LICENSE.txt` (written automatically when the archive is
     downloaded) in the release ZIP, not only inside the single-file exe;
  2. point users at the corresponding source:
     <https://github.com/yt-dlp/FFmpeg-Builds>;
  3. keep the FFmpeg binaries' GPL terms separate from this project's MIT
     licence — do not state that the bundled `ffmpeg.exe` is MIT.
- The "lite" builds never contain FFmpeg: they use whatever the user has
  installed, so no FFmpeg redistribution happens there.
- The NSIS installer's optional FFmpeg component installs the same binaries
  from `bin/`, including the licence text when present.

## Python dependencies

Runtime libraries are pinned in `requirements.txt` and embedded by PyInstaller:

| Component | Licence |
|---|---|
| PySide6 (Qt for Python) | LGPLv3 (Qt) / LGPLv3 for the bindings |
| yt-dlp | Unlicense |
| curl_cffi | MIT |

`requirements-dev.txt` adds pytest (MIT), ruff (MIT), and PyInstaller (GPL with
an exception that permits building and distributing non-free/other-licensed
programs — the *output* of PyInstaller is not covered by the GPL).
