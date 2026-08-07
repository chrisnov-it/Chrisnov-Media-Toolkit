"""Download worker threaded for the GUI."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from yt_dlp import YoutubeDL

from .base_worker import CancellableWorker
from .yt_dlp_opts import (
    build_cookie_opts,
    build_dry_opts,
    build_format_opts,
    _thumbnail_supported,
)
from .constants import VIDEO_CONTAINERS, AUDIO_CONTAINERS


class _CancelledError(Exception):
    """Raised from the yt-dlp progress hook to abort a download cleanly."""


class DownloadWorker(CancellableWorker):
    progress = Signal(int)        # 0-100
    status = Signal(str)          # status message
    finished_ok = Signal(str)     # final saved path (or "playlist:N:title")
    failed = Signal(str)          # error message

    def __init__(self, url: str, height: int | None, container: str, bitrate: int,
                 outdir: str, audio_only: bool = False, idx_label: str = "",
                 clean_tags: list[str] | None = None, playlist: bool = False,
                 archive_path: str | None = None, embed_metadata: bool = False,
                 embed_thumbnail: bool = False, cookie_path: str | None = None,
                 cookies_from_browser: bool = False):
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
        self.embed_metadata = embed_metadata
        self.embed_thumbnail = embed_thumbnail
        self.cookie_path = cookie_path
        self.cookies_from_browser = cookies_from_browser

    def run(self) -> None:
        try:
            ytdl_opts = self._build_opts()
            self.status.emit(f"{self.idx_label} Resolving info...")
            with YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
            if self._cancelled:
                return
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
        except _CancelledError:
            pass  # clean cancel — no error signal
        except Exception as e:
            if not self._cancelled:
                self.failed.emit(str(e))

    def _hook(self, d: dict) -> None:
        if self._cancelled:
            raise _CancelledError()
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
        opts = build_format_opts(
            audio_only=self.audio_only,
            height=self.height,
            container=self.container,
            bitrate=self.bitrate,
            embed_metadata=self.embed_metadata,
            embed_thumbnail=self.embed_thumbnail,
            outdir=self.outdir,
            archive_path=self.archive_path,
            playlist=self.playlist,
        )
        opts["progress_hooks"] = [self._hook]
        opts.update(build_cookie_opts(self.cookie_path,
                                      self.cookies_from_browser))

        # Download the thumbnail file so EmbedThumbnail has something to embed.
        if self.embed_thumbnail and _thumbnail_supported(self.audio_only,
                                                         self.container):
            opts["writethumbnail"] = True

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
    return set(AUDIO_CONTAINERS)


def video_extensions() -> set[str]:
    return set(VIDEO_CONTAINERS)


class PlaylistInspectWorker(CancellableWorker):
    """Inspect playlist URLs off the GUI thread to get their entry counts.

    Emits:
        progress(str)           — status text for the status label
        done(object)            — list[tuple[url, n, est_str, title]] for
                                  playlists that exceed *threshold* entries
        error(str, str)         — (url, error_message) on first failure
    """

    progress = Signal(str)
    done     = Signal(object)   # list[tuple[str, int, str, str]]
    error    = Signal(str, str)

    def __init__(self, playlist_urls: list[str], audio_only: bool,
                 threshold: int, cookie_path: str | None = None,
                 cookies_from_browser: bool = False):
        super().__init__()
        self.playlist_urls = playlist_urls
        self.audio_only    = audio_only
        self.threshold     = threshold
        self.cookie_path = cookie_path
        self.cookies_from_browser = cookies_from_browser

    def run(self) -> None:
        dry_opts = {
            "quiet": True, "no_warnings": True,
            "skip_download": True, "extract_flat": True,
        }
        dry_opts.update(build_cookie_opts(self.cookie_path,
                                          self.cookies_from_browser))

        total = len(self.playlist_urls)
        big: list[tuple[str, int, str, str]] = []
        for i, p_url in enumerate(self.playlist_urls, 1):
            if self._cancelled:
                return
            self.progress.emit(f"Inspecting playlist {i}/{total}...")
            try:
                with YoutubeDL(dry_opts) as ydl:
                    info = ydl.extract_info(p_url, download=False)
            except Exception as exc:
                if not self._cancelled:
                    self.error.emit(p_url, str(exc))
                return
            if self._cancelled:
                return
            entries = (info or {}).get("entries") or []
            n = (info or {}).get("playlist_count") or len(entries)
            if n >= self.threshold:
                per_mb  = 3 if self.audio_only else 15
                est_mb  = n * per_mb
                est_str = f"{est_mb / 1000:.1f} GB" if est_mb > 500 else f"{est_mb} MB"
                big.append((p_url, n, est_str, (info or {}).get("title", "?")))
        if not self._cancelled:
            self.done.emit(big)


class FileSizeWorker(CancellableWorker):
    """Fetch video metadata (title, duration, estimated file size) from a single URL.

    Emits:
        result(str, float|None, float|None, str, bool, str)
            — title, length_sec, filesize_mb, format_note, audio_only, resolution
        error(str)  — error message
    """

    result = Signal(str, object, object, str, bool, str)  # title, duration, size, note, audio, res
    error  = Signal(str)

    def __init__(self, url: str, audio_only: bool, height: int | None, fmt: str,
                 cookie_path: str | None = None, cookies_from_browser: bool = False):
        super().__init__()
        self.url = url
        self.audio_only = audio_only
        self.height = height
        self.fmt = fmt
        self.cookie_path = cookie_path
        self.cookies_from_browser = cookies_from_browser

    def run(self) -> None:
        try:
            opts = build_dry_opts(self.audio_only, self.cookie_path,
                                  self.cookies_from_browser)

            if self.height and not self.audio_only:
                opts["format"] = f"bv*[height<={self.height}]+ba/b[height<={self.height}]/b"

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if isinstance(info, dict) and "entries" in info:
                    info = info["entries"][0] if info["entries"] else info

            title = (info.get("title") or "?").strip()
            duration = info.get("duration")
            filesize = info.get("filesize") or info.get("filesize_approx")
            fmt_note = info.get("format_note", "")

            # Determine resolution label
            if self.audio_only:
                resolution = "audio only"
            elif self.height:
                resolution = f"up to {self.height}p"
            else:
                resolution = "best available"

            filesize_mb = None
            if filesize:
                filesize_mb = round(filesize / (1024 * 1024), 1)

            if filesize_mb is None and duration:
                # Rough estimate based on format
                kbps = 128 if self.audio_only else 2500
                filesize_mb = round(duration * kbps * 1000 / 8 / (1024 * 1024), 1)

            if self._cancelled:
                return
            self.result.emit(title, duration, filesize_mb, fmt_note or self.fmt,
                             self.audio_only, resolution)

        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
