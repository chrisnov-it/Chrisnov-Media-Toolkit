"""Download worker threaded for the GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from yt_dlp import YoutubeDL

from .constants import VIDEO_CONTAINERS, AUDIO_CONTAINERS


class DownloadWorker(QThread):
    progress = Signal(int)        # 0-100
    status = Signal(str)          # status message
    finished_ok = Signal(str)     # final saved path (or "playlist:N:title")
    failed = Signal(str)          # error message

    def __init__(self, url: str, height: int | None, container: str, bitrate: int,
                 outdir: str, audio_only: bool = False, idx_label: str = "",
                 clean_tags: list[str] | None = None, playlist: bool = False,
                 archive_path: str | None = None):
        super().__init__()
        self.url = url
        self.height = height
        self.container = container
        self.bitrate = bitrate
        self.outdir = outdir
        self.audio_only = audio_only
        self.idx_label = idx_label
        self.clean_tags = clean_tags
        self.playlist = playlist
        self.archive_path = archive_path

    def run(self) -> None:
        try:
            ytdl_opts = self._build_opts()
            self.status.emit(f"{self.idx_label} Resolving info...")
            with YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
            if isinstance(info, dict) and "entries" in info and info["entries"]:
                n = len(info["entries"])
                self.finished_ok.emit(f"playlist:{n}:{info.get('title', '?')}")
            else:
                saved = ydl.prepare_filename(info)
                self.finished_ok.emit(saved)
        except Exception as e:
            self.failed.emit(str(e))

    def _hook(self, d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = int(d["downloaded_bytes"] / total * 100)
                self.progress.emit(pct)
                self.status.emit(
                    f"{self.idx_label} Downloading... {pct}% @ {d.get('speed', 0)/1e6:.1f} MB/s"
                )
        elif d["status"] == "finished":
            self.progress.emit(100)
            self.status.emit(f"{self.idx_label} Merging/post-processing...")

    def _build_opts(self) -> dict:
        opts: dict = {
            "noplaylist": not self.playlist,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._hook],
        }
        if self.archive_path:
            opts["download_archive"] = self.archive_path

        if self.audio_only:
            codec = {"mp3": "mp3", "m4a": "aac", "opus": "opus"}.get(self.container, "mp3")
            ext = self.container
            opts.update({
                "format": "ba/b",
                "outtmpl": str(Path(self.outdir) / f"%(title)s.{ext}"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": str(self.bitrate),
                }],
            })
            return opts
        if self.height:
            fmt = f"bv*[height<={self.height}]+ba/b[height<={self.height}]/b"
        else:
            fmt = "bv*+ba/b"
        opts.update({
            "format": fmt,
            "merge_output_format": self.container,
            "outtmpl": str(Path(self.outdir) / "%(title)s [%(height)sp].%(ext)s"),
        })
        return opts


def audio_extensions() -> set[str]:
    return {"mp3", "m4a", "opus"}


def video_extensions() -> set[str]:
    return {"mp4", "mkv", "webm"}
