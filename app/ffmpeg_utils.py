"""FFmpeg utilities — binary discovery, probing, and progress-aware execution.

Extracted from converter_worker.py to eliminate duplication between
ConvertWorker and VideoConvertWorker.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

def find_binary(name: str) -> str:
    """Return path to a binary, preferring PyInstaller bundled bin/, then
    project-local bin/, then system PATH.

    Resolution order:
      1. PyInstaller temp dir (sys._MEIPASS/bin/)
      2. Project-local bin/ folder
      3. System PATH
    """
    ext = ".exe" if sys.platform == "win32" else ""

    # 1. PyInstaller temp directory
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "bin" / f"{name}{ext}"
        if bundled.exists():
            return str(bundled)

    # 2. Project-local bin/ folder
    local = Path(__file__).resolve().parent.parent / "bin" / f"{name}{ext}"
    if local.exists():
        return str(local)

    # 3. System PATH
    system = shutil.which(name)
    if system:
        return system

    raise FileNotFoundError(
        f"{name} not found. Install it with: sudo apt install ffmpeg"
        if name == "ffmpeg" else f"{name} not found."
    )


def find_ffmpeg() -> str:
    """Return path to ffmpeg binary."""
    return find_binary("ffmpeg")


def find_ffprobe() -> str:
    """Return path to ffprobe binary."""
    return find_binary("ffprobe")


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

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


def probe_loudness(ffmpeg: str, src: Path, default_lufs: float,
                   default_true_peak: float, default_lra: float) -> dict:
    """Run EBU R128 first-pass loudness scan. Returns loudnorm measured values."""
    cmd = [
        ffmpeg, "-hide_banner", "-nostats",
        "-i", str(src),
        "-af", (
            f"loudnorm=I={default_lufs}:TP={default_true_peak}"
            f":LRA={default_lra}:print_format=json"
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
# Output path resolution
# ---------------------------------------------------------------------------

def resolve_output_path(
    src: Path,
    outdir: Path,
    fmt: str,
    clean_tags: list[str] | None,
) -> Path:
    """Build output path, appending numeric suffix on collision.

    If clean_tags is set, the stem is cleaned via cleaner.clean_title first.
    """
    if clean_tags:
        from .cleaner import clean_title
        stem = clean_title(src.stem, clean_tags)
    else:
        stem = src.stem

    base = outdir / f"{stem}.{fmt}"
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = outdir / f"{stem} ({counter}).{fmt}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Execution with progress
# ---------------------------------------------------------------------------

def run_ffmpeg_with_progress(
    cmd: list[str],
    *,
    duration: float | None,
    cancelled: Callable[[], bool],
    on_progress: Callable[[int], None],
    progress_floor: int = 0,
    progress_ceiling: int = 100,
    set_process: Callable[[subprocess.Popen[str] | None], None] | None = None,
) -> None:
    """Run an ffmpeg command, parsing `-progress pipe:1` output for live progress.

    Args:
        cmd: Full ffmpeg command (output path must be the last element).
        duration: Source duration in seconds (for progress %), or None.
        cancelled: Callable returning True if cancellation was requested.
        on_progress: Callable receiving progress 0-100 (within floor/ceiling range).
        progress_floor / progress_ceiling: Map ffmpeg's 0-100 progress onto this range.
        set_process: Optional callback receiving the active Popen object (None when done)
                     so the caller can terminate the process on cancel.

    Raises:
        RuntimeError: if cancelled or ffmpeg exits with a non-zero code.
    """
    progress_cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]]
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as stderr_file:
        process = subprocess.Popen(
            progress_cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if set_process is not None:
            set_process(process)
        assert process.stdout is not None
        last_emit = 0.0
        for line in process.stdout:
            if cancelled():
                process.terminate()
                break
            key, _, value = line.strip().partition("=")
            if key == "out_time_ms" and duration:
                try:
                    elapsed = int(value) / 1_000_000
                except ValueError:
                    continue
                pct = int(min(1.0, elapsed / duration) * (progress_ceiling - progress_floor))
                now = time.monotonic()
                if now - last_emit >= 0.2:
                    on_progress(progress_floor + pct)
                    last_emit = now
        try:
            code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
        stderr_file.seek(0)
        stderr_tail = stderr_file.read()[-800:]
        if set_process is not None:
            set_process(None)
    if cancelled():
        raise RuntimeError("Cancelled.")
    if code != 0:
        raise RuntimeError(
            f"ffmpeg error (exit {code}):\n{stderr_tail}"
        )