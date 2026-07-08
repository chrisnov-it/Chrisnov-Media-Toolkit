"""FFmpeg-based media converter workers (QThread)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_INPUT_EXTENSIONS = {
    # Audio
    "mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "wma", "ape", "aiff",
    # Video (extract audio)
    "mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "ts", "m4v",
}

OUTPUT_FORMATS = ["mp3", "m4a", "opus", "flac", "wav"]

VIDEO_INPUT_EXTENSIONS = {
    "mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "ts", "m4v",
}

VIDEO_OUTPUT_FORMATS = ["mp4", "mkv", "webm"]

VIDEO_QUALITY_PRESETS = [
    ("Keep quality", "keep"),
    ("Balanced", "balanced"),
    ("Smaller file", "small"),
]

SAMPLE_RATES = [
    ("As-is (no change)", None),
    ("44100 Hz (CD / standard)", 44100),
    ("48000 Hz (video / broadcast)", 48000),
    ("96000 Hz (hi-res)", 96000),
]

AUDIO_BITRATES = ["96", "128", "160", "192", "256", "320"]

# EBU R128 default target
DEFAULT_LUFS = -14.0
DEFAULT_TRUE_PEAK = -1.0
DEFAULT_LRA = 11.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_ffmpeg() -> str:
    """Return path to ffmpeg binary, preferring project-local bin/ or PyInstaller bundled bin/."""
    import sys
    ext = ".exe" if sys.platform == "win32" else ""

    # 1. Check PyInstaller temp directory (sys._MEIPASS)
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "bin" / f"ffmpeg{ext}"
        if bundled.exists():
            return str(bundled)

    # 2. Check local project-level bin/ folder
    local = Path(__file__).resolve().parent.parent / "bin" / f"ffmpeg{ext}"
    if local.exists():
        return str(local)

    # 3. Check system PATH
    system = shutil.which("ffmpeg")
    if system:
        return system

    raise FileNotFoundError(
        "ffmpeg not found. Install it with: sudo apt install ffmpeg"
    )


def find_ffprobe() -> str:
    """Return path to ffprobe binary, preferring project-local bin/ or PyInstaller bundled bin/."""
    import sys
    ext = ".exe" if sys.platform == "win32" else ""

    # 1. Check PyInstaller temp directory (sys._MEIPASS)
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "bin" / f"ffprobe{ext}"
        if bundled.exists():
            return str(bundled)

    # 2. Check local project-level bin/ folder
    local = Path(__file__).resolve().parent.parent / "bin" / f"ffprobe{ext}"
    if local.exists():
        return str(local)

    # 3. Check system PATH
    system = shutil.which("ffprobe")
    if system:
        return system

    raise FileNotFoundError("ffprobe not found.")


def probe_duration(ffprobe: str, src: Path) -> float | None:
    """Return media duration in seconds, or None if ffprobe cannot determine it."""
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def probe_loudness(ffmpeg: str, src: Path) -> dict:
    """Run EBU R128 first-pass loudness scan. Returns loudnorm measured values."""
    cmd = [
        ffmpeg, "-hide_banner", "-nostats",
        "-i", str(src),
        "-af", (
            f"loudnorm=I={DEFAULT_LUFS}:TP={DEFAULT_TRUE_PEAK}"
            f":LRA={DEFAULT_LRA}:print_format=json"
        ),
        "-f", "null", "-",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300
    )
    # loudnorm prints JSON to stderr
    stderr = result.stderr
    # Extract the JSON block from stderr
    match = re.search(r"\{[^{}]+\}", stderr, re.DOTALL)
    if not match:
        raise RuntimeError(
            f"loudnorm scan failed — no JSON in output.\nstderr: {stderr[-500:]}"
        )
    return json.loads(match.group())


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class ConvertWorker(QThread):
    """Convert a single file using ffmpeg. Emits progress (0-100), status, and result."""

    progress = Signal(int)      # 0-100
    status   = Signal(str)      # human-readable status
    finished_ok = Signal(str)   # output path on success
    failed      = Signal(str)   # error message

    def __init__(
        self,
        src: str | Path,
        outdir: str | Path,
        fmt: str,                       # "mp3" | "m4a" | "opus" | "flac" | "wav"
        *,
        cbr: bool = True,               # True=CBR, False=VBR (ignored for flac/wav)
        bitrate: int = 192,             # kbps, ignored for flac/wav
        sample_rate: int | None = None, # None = keep original
        norm_mode: str = "none",        # "none" | "ebu" | "peak"
        lufs_target: float = DEFAULT_LUFS,
        peak_target: float = -1.0,
        trim_silence: bool = False,
        clean_tags: list[str] | None = None,
        idx_label: str = "",
    ):
        super().__init__()
        self.src          = Path(src)
        self.outdir       = Path(outdir)
        self.fmt          = fmt
        self.cbr          = cbr
        self.bitrate      = bitrate
        self.sample_rate  = sample_rate
        self.norm_mode    = norm_mode
        self.lufs_target  = lufs_target
        self.peak_target  = peak_target
        self.trim_silence = trim_silence
        self.clean_tags   = clean_tags
        self.idx_label    = idx_label
        self._cancelled = False
        self._process: subprocess.Popen[str] | None = None

    def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.poll() is None:
            self._process.terminate()

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            ffmpeg = find_ffmpeg()
            ffprobe = find_ffprobe()
            self.duration = probe_duration(ffprobe, self.src)
            out_path = self._resolve_output_path()

            if self.norm_mode == "ebu":
                self._run_with_ebu(ffmpeg, out_path)
            else:
                self._run_single_pass(ffmpeg, out_path)

            # Apply clean title rename if requested
            if self.clean_tags:
                from .cleaner import rename_with_cleanup
                new = rename_with_cleanup(out_path, self.clean_tags)
                if new:
                    out_path = new

            if self._cancelled:
                self.status.emit("Cancelled.")
            else:
                self.progress.emit(100)
                self.finished_ok.emit(str(out_path))

        except Exception as exc:
            if self._cancelled:
                self.status.emit("Cancelled.")
            else:
                self.failed.emit(str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_output_path(self) -> Path:
        """Build output path, appending numeric suffix on collision."""
        if self.clean_tags:
            from .cleaner import clean_title
            stem = clean_title(self.src.stem, self.clean_tags)
        else:
            stem = self.src.stem

        base = self.outdir / f"{stem}.{self.fmt}"
        if not base.exists():
            return base
        counter = 1
        while True:
            candidate = self.outdir / f"{stem} ({counter}).{self.fmt}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _audio_filters(self, loudnorm_apply: str | None = None) -> list[str]:
        """Build -af filter chain based on settings."""
        filters: list[str] = []

        if self.trim_silence:
            # Trim leading silence only (start_periods=1).
            # Avoid stop_periods=-1 which can cause ffmpeg to hang on short
            # or near-silent files — use a separate areverse pass instead
            # (handled as two filters: trim start, reverse, trim start, reverse).
            # For simplicity and reliability we only trim the head here;
            # trailing silence is handled by the areverse trick below.
            filters.append(
                "silenceremove=start_periods=1"
                ":start_duration=0.1"
                ":start_threshold=-55dB"
                ":detection=peak"
            )
            # Trim trailing silence: reverse → trim head → reverse
            filters.append("areverse")
            filters.append(
                "silenceremove=start_periods=1"
                ":start_duration=0.1"
                ":start_threshold=-55dB"
                ":detection=peak"
            )
            filters.append("areverse")

        if loudnorm_apply:
            filters.append(loudnorm_apply)
        elif self.norm_mode == "peak":
            filters.append(f"dynaudnorm=p=0.9:m=100:s=12")
            filters.append(f"volume={self.peak_target}dB")

        return filters

    def _codec_args(self) -> list[str]:
        """Return ffmpeg codec + quality arguments for the chosen format."""
        if self.fmt == "mp3":
            if self.cbr:
                return ["-c:a", "libmp3lame", "-b:a", f"{self.bitrate}k"]
            else:
                # VBR quality: 0=best … 9=worst; map bitrate roughly
                q = max(0, min(9, int((320 - self.bitrate) / 35)))
                return ["-c:a", "libmp3lame", "-q:a", str(q)]

        if self.fmt == "m4a":
            args = ["-c:a", "aac", "-profile:a", "aac_low"]
            if self.cbr:
                args += ["-b:a", f"{self.bitrate}k"]
            else:
                # aac VBR: 1(low)…5(high)
                vbr = max(1, min(5, round(self.bitrate / 64)))
                args += ["-vbr", str(vbr)]
            return args

        if self.fmt == "opus":
            return ["-c:a", "libopus", "-b:a", f"{self.bitrate}k",
                    "-vbr", "on"]

        if self.fmt == "flac":
            return ["-c:a", "flac", "-compression_level", "8"]

        if self.fmt == "wav":
            return ["-c:a", "pcm_s16le"]

        return ["-c:a", "copy"]

    def _sample_rate_args(self) -> list[str]:
        if self.fmt == "opus":
            if self.sample_rate in {8000, 12000, 16000, 24000, 48000}:
                return ["-ar", str(self.sample_rate)]
            return ["-ar", "48000"]
        if self.sample_rate:
            return ["-ar", str(self.sample_rate)]
        return []

    def _build_cmd(
        self,
        ffmpeg: str,
        out_path: Path,
        af_filters: list[str],
        extra_input_args: list[str] | None = None,
    ) -> list[str]:
        cmd = [ffmpeg, "-hide_banner", "-y"]
        if extra_input_args:
            cmd += extra_input_args
        cmd += ["-i", str(self.src), "-vn"]  # -vn strips video stream
        if af_filters:
            cmd += ["-af", ",".join(af_filters)]
        cmd += self._codec_args()
        cmd += self._sample_rate_args()
        cmd += [str(out_path)]
        return cmd

    def _run_single_pass(self, ffmpeg: str, out_path: Path) -> None:
        """Single-pass conversion (no EBU R128)."""
        af = self._audio_filters()
        cmd = self._build_cmd(ffmpeg, out_path, af)
        self.status.emit(f"{self.idx_label} Converting {self.src.name}...")
        self.progress.emit(10)
        self._exec(cmd, progress_floor=10, progress_ceiling=90)
        self.progress.emit(90)

    def _run_with_ebu(self, ffmpeg: str, out_path: Path) -> None:
        """Two-pass EBU R128 loudnorm conversion."""
        # Pass 1 — measure
        self.status.emit(f"{self.idx_label} Scanning loudness (pass 1/2)...")
        self.progress.emit(5)
        measured = probe_loudness(ffmpeg, self.src)
        self.progress.emit(40)

        # Build loudnorm filter with measured values for accurate 2nd pass
        lnorm = (
            f"loudnorm=I={self.lufs_target}"
            f":TP={DEFAULT_TRUE_PEAK}"
            f":LRA={DEFAULT_LRA}"
            f":measured_I={measured['input_i']}"
            f":measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}"
            f":measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}"
            f":linear=true:print_format=none"
        )

        # Pass 2 — apply + convert
        self.status.emit(f"{self.idx_label} Applying loudnorm + converting (pass 2/2)...")
        af = self._audio_filters(loudnorm_apply=lnorm)
        cmd = self._build_cmd(ffmpeg, out_path, af)
        self._exec(cmd, progress_floor=40, progress_ceiling=90)
        self.progress.emit(90)

    def _exec(
        self,
        cmd: list[str],
        *,
        progress_floor: int = 0,
        progress_ceiling: int = 100,
    ) -> None:
        """Run ffmpeg command, parsing progress and supporting cancellation."""
        progress_cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]]
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as stderr_file:
            self._process = subprocess.Popen(
                progress_cmd,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert self._process.stdout is not None
            last_emit = 0.0
            for line in self._process.stdout:
                if self._cancelled:
                    self._process.terminate()
                    break
                key, _, value = line.strip().partition("=")
                if key == "out_time_ms" and self.duration:
                    try:
                        elapsed = int(value) / 1_000_000
                    except ValueError:
                        continue
                    pct = int(min(1.0, elapsed / self.duration) * (progress_ceiling - progress_floor))
                    now = time.monotonic()
                    if now - last_emit >= 0.2:
                        self.progress.emit(progress_floor + pct)
                        last_emit = now
            try:
                code = self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                code = self._process.wait()
            stderr_file.seek(0)
            stderr_tail = stderr_file.read()[-800:]
            self._process = None
        if self._cancelled:
            raise RuntimeError("Cancelled.")
        if code != 0:
            raise RuntimeError(
                f"ffmpeg error (exit {code}):\n{stderr_tail}"
            )


class VideoConvertWorker(QThread):
    """Convert a single video file using ffmpeg."""

    progress = Signal(int)
    status = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        src: str | Path,
        outdir: str | Path,
        fmt: str,
        *,
        quality: str = "balanced",
        copy_audio: bool = True,
        clean_tags: list[str] | None = None,
        idx_label: str = "",
    ):
        super().__init__()
        self.src = Path(src)
        self.outdir = Path(outdir)
        self.fmt = fmt
        self.quality = quality
        self.copy_audio = copy_audio
        self.clean_tags = clean_tags
        self.idx_label = idx_label
        self._cancelled = False
        self._process: subprocess.Popen[str] | None = None
        self.duration: float | None = None

    def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def run(self) -> None:
        try:
            ffmpeg = find_ffmpeg()
            ffprobe = find_ffprobe()
            self.duration = probe_duration(ffprobe, self.src)
            out_path = self._resolve_output_path()
            cmd = self._build_cmd(ffmpeg, out_path)
            self.status.emit(f"{self.idx_label} Converting {self.src.name}...")
            self.progress.emit(10)
            try:
                self._exec(cmd)
            except RuntimeError:
                if self._cancelled or not self.copy_audio:
                    raise
                self.status.emit(
                    f"{self.idx_label} Audio stream incompatible, retrying with AAC/Opus..."
                )
                self.copy_audio = False
                self._exec(self._build_cmd(ffmpeg, out_path))

            if self.clean_tags:
                from .cleaner import rename_with_cleanup
                new = rename_with_cleanup(out_path, self.clean_tags)
                if new:
                    out_path = new

            if self._cancelled:
                self.status.emit("Cancelled.")
            else:
                self.progress.emit(100)
                self.finished_ok.emit(str(out_path))
        except Exception as exc:
            if self._cancelled:
                self.status.emit("Cancelled.")
            else:
                self.failed.emit(str(exc))

    def _resolve_output_path(self) -> Path:
        if self.clean_tags:
            from .cleaner import clean_title
            stem = clean_title(self.src.stem, self.clean_tags)
        else:
            stem = self.src.stem

        base = self.outdir / f"{stem}.{self.fmt}"
        if not base.exists():
            return base
        counter = 1
        while True:
            candidate = self.outdir / f"{stem} ({counter}).{self.fmt}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _video_args(self) -> list[str]:
        if self.fmt == "webm":
            crf = {"keep": "20", "balanced": "30", "small": "36"}[self.quality]
            return ["-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0", "-deadline", "good"]

        crf = {"keep": "18", "balanced": "23", "small": "28"}[self.quality]
        return [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", crf,
            "-pix_fmt", "yuv420p",
        ]

    def _audio_args(self) -> list[str]:
        if self.copy_audio and self.fmt != "webm":
            return ["-c:a", "copy"]
        if self.fmt == "webm":
            return ["-c:a", "libopus", "-b:a", "128k"]
        return ["-c:a", "aac", "-b:a", "160k"]

    def _build_cmd(self, ffmpeg: str, out_path: Path) -> list[str]:
        cmd = [ffmpeg, "-hide_banner", "-y", "-i", str(self.src)]
        cmd += self._video_args()
        cmd += self._audio_args()
        if self.fmt == "mp4":
            cmd += ["-movflags", "+faststart"]
        cmd += [str(out_path)]
        return cmd

    def _exec(self, cmd: list[str]) -> None:
        progress_cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]]
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as stderr_file:
            self._process = subprocess.Popen(
                progress_cmd,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert self._process.stdout is not None
            last_emit = 0.0
            for line in self._process.stdout:
                if self._cancelled:
                    self._process.terminate()
                    break
                key, _, value = line.strip().partition("=")
                if key == "out_time_ms" and self.duration:
                    try:
                        elapsed = int(value) / 1_000_000
                    except ValueError:
                        continue
                    pct = int(min(1.0, elapsed / self.duration) * 80)
                    now = time.monotonic()
                    if now - last_emit >= 0.2:
                        self.progress.emit(10 + pct)
                        last_emit = now
            try:
                code = self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                code = self._process.wait()
            stderr_file.seek(0)
            stderr_tail = stderr_file.read()[-800:]
            self._process = None
        if self._cancelled:
            raise RuntimeError("Cancelled.")
        if code != 0:
            raise RuntimeError(
                f"ffmpeg error (exit {code}):\n{stderr_tail}"
            )
