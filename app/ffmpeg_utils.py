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
from collections.abc import Callable
from pathlib import Path

# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

def _install_hint(name: str) -> str:
    """Platform-appropriate install command for a missing FFmpeg binary."""
    if sys.platform == "win32":
        return "winget install Gyan.FFmpeg"
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    return "sudo apt install ffmpeg"


def _local_bin_dir() -> Path:
    """Return the project-local bin/ folder (used by dev/source runs).

    A bundled build (build-windows.ps1 -Type Bundled) leaves ffmpeg.exe and
    ffprobe.exe here, which is why the unit tests patch this callable instead
    of relying on the checkout being free of build artifacts.
    """
    return Path(__file__).resolve().parent.parent / "bin"


def find_binary(name: str) -> str:
    """Return path to a binary, preferring PyInstaller bundled bin/, then
    a bin/ folder next to the frozen executable, then project-local bin/,
    then system PATH.

    Resolution order:
      1. PyInstaller temp dir (sys._MEIPASS/bin/)
      2. Next to the frozen executable (bin/ folder beside the exe —
         used when the NSIS installer adds its optional FFmpeg component,
         or for a portable exe+bin layout)
      3. Project-local bin/ folder (dev/source runs)
      4. System PATH
    """
    ext = ".exe" if sys.platform == "win32" else ""

    # 1. PyInstaller temp directory
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "bin" / f"{name}{ext}"
        if bundled.exists():
            return str(bundled)

    # 2. bin/ folder next to the frozen executable
    if getattr(sys, "frozen", False):
        beside_exe = Path(sys.executable).resolve().parent / "bin" / f"{name}{ext}"
        if beside_exe.exists():
            return str(beside_exe)

    # 3. Project-local bin/ folder
    local = _local_bin_dir() / f"{name}{ext}"
    if local.exists():
        return str(local)

    # 4. System PATH
    system = shutil.which(name)
    if system:
        return system

    raise FileNotFoundError(
        f"{name} not found. FFmpeg is required for this feature — install it "
        f"with: {_install_hint(name)}"
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

# CREATE_NO_WINDOW is Windows-only; spell the value out locally so this module
# stays importable (and _no_window_kwargs() testable) on every platform.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _no_window_kwargs() -> dict:
    """Return Popen/subprocess.run kwargs that suppress the child's console window.

    The released app is built with ``console=False``, i.e. it has no console of
    its own, and Windows gives every console-subsystem child a brand-new console
    window in that case. Without this, ffprobe flashes a console when the About
    dialog reads the FFmpeg version and when a conversion is prepared, and
    ffmpeg keeps one open for the whole encode / loudness scan. A no-op on
    other platforms.
    """
    if sys.platform == "win32":
        return {"creationflags": _CREATE_NO_WINDOW}
    return {}


def probe_version(binary: str) -> str | None:
    """Return the binary's version string (e.g. "6.1.1-3ubuntu5"), or None.

    `ffmpeg -version` / `ffprobe -version` print their banner to *stdout*
    (stderr only carries runtime logs), so that is where the version is
    read from. Returns None when the binary is missing, fails, or prints
    no recognizable banner.
    """
    try:
        result = subprocess.run(
            [binary, "-version"],
            capture_output=True, text=True, timeout=5, check=False,
            **_no_window_kwargs(),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    match = re.search(r"version (\S+)", result.stdout)
    return match.group(1) if match else None

def probe_duration(ffprobe: str, src: Path) -> float | None:
    """Return media duration in seconds, or None if ffprobe cannot determine it."""
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30, check=False,
        **_no_window_kwargs(),
    )
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def probe_loudness(
    ffmpeg: str,
    src: Path,
    default_lufs: float,
    default_true_peak: float,
    default_lra: float,
    timeout: int = 300,
    *,
    cancelled: Callable[[], bool] | None = None,
    set_process: Callable[[subprocess.Popen[str] | None], None] | None = None,
) -> dict:
    """Run EBU R128 first-pass loudness scan. Returns loudnorm measured values.

    -vn skips decoding the video stream (only the audio matters here), keeping
    the scan fast for video files.

    Runs via Popen with a poll loop instead of blocking subprocess.run so the
    caller can cancel: when *cancelled* reports cancellation the ffmpeg
    process is terminated (then killed if it ignores that) and
    RuntimeError("Cancelled.") is raised — without this, a cancelled scan
    would keep running as an orphan because cancel() could only set a flag.
    Raises a readable RuntimeError when ffmpeg fails or the scan exceeds
    *timeout* seconds.
    """
    cmd = [
        ffmpeg, "-hide_banner", "-nostats",
        "-i", str(src),
        "-vn",
        "-af", (
            f"loudnorm=I={default_lufs}:TP={default_true_peak}"
            f":LRA={default_lra}:print_format=json"
        ),
        "-f", "null", "-",
    ]
    deadline = time.monotonic() + timeout
    # loudnorm prints its JSON summary to stderr; buffer it in a file so the
    # process can never block on a full pipe.
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as stderr_file:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_no_window_kwargs(),
        )
        if set_process is not None:
            set_process(process)
        try:
            while process.poll() is None:
                if cancelled is not None and cancelled():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise RuntimeError("Cancelled.")
                if time.monotonic() > deadline:
                    process.kill()
                    process.wait()
                    raise RuntimeError(
                        f"Loudness scan timed out after {timeout}s "
                        f"({src.name} may be very long, or storage too slow)."
                    )
                time.sleep(0.1)
        finally:
            if set_process is not None:
                set_process(None)
        stderr_file.seek(0)
        stderr = stderr_file.read()
        if process.returncode != 0:
            raise RuntimeError(
                f"loudnorm scan failed (exit {process.returncode}): "
                f"{stderr[-500:]}"
            )
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
            **_no_window_kwargs(),
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