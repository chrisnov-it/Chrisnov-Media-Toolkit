"""Download worker threaded for the GUI."""

from __future__ import annotations

import json
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
                paths = self._collect_saved_paths(info, ydl)
                if paths:
                    self.finished_ok.emit("playlist_files:" + json.dumps(paths))
                else:
                    n = len(info["entries"])
                    self.finished_ok.emit(f"playlist:{n}:{info.get('title', '?')}")
            else:
                saved = ydl.prepare_filename(info)
                if self.audio_only:
                    # prepare_filename returns the pre-conversion extension (e.g.
                    # ".webm"), but FFmpegExtractAudio writes the final file with
                    # the chosen container extension.  Correct it here so the
                    # caller can find the actual file on disk for rename/cleanup.
                    saved = str(Path(saved).with_suffix(f".{self.container}"))
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
                    f"{self.idx_label} Downloading... {pct}% @ {(d.get('speed') or 0)/1e6:.1f} MB/s"
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
            opts.update({
                "format": "ba/b",
                # Use %(ext)s — FFmpegExtractAudio rewrites the extension after
                # conversion, so hardcoding it here causes a double extension
                # (e.g. "title.m4a.m4a").
                "outtmpl": str(Path(self.outdir) / "%(title)s.%(ext)s"),
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

    def _collect_saved_paths(self, info: dict, ydl: YoutubeDL) -> list[str]:
        """Collect final output paths from a playlist extraction result."""
        paths: list[str] = []
        seen: set[str] = set()
        for entry in info.get("entries") or []:
            path = self._saved_path_for_entry(entry, ydl)
            if path and path not in seen:
                paths.append(path)
                seen.add(path)
        return paths

    def _saved_path_for_entry(self, entry: dict | None, ydl: YoutubeDL) -> str | None:
        if not isinstance(entry, dict):
            return None

        candidates: list[str] = []
        for item in entry.get("requested_downloads") or []:
            if isinstance(item, dict):
                candidates.extend(
                    str(v) for v in (item.get("filepath"), item.get("filename")) if v
                )
        candidates.extend(
            str(v)
            for v in (entry.get("filepath"), entry.get("_filename"), entry.get("filename"))
            if v
        )

        try:
            candidates.append(ydl.prepare_filename(entry))
        except Exception:
            pass

        for candidate in candidates:
            path = Path(candidate)
            if self.audio_only:
                path = path.with_suffix(f".{self.container}")
            if path.exists():
                return str(path)

        if candidates:
            path = Path(candidates[-1])
            if self.audio_only:
                path = path.with_suffix(f".{self.container}")
            return str(path)
        return None


def audio_extensions() -> set[str]:
    return {"mp3", "m4a", "opus"}


def video_extensions() -> set[str]:
    return {"mp4", "mkv", "webm"}
