"""Download worker threaded for the GUI."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from yt_dlp import YoutubeDL

from .constants import VIDEO_CONTAINERS, AUDIO_CONTAINERS


class _CancelledError(Exception):
    """Raised from the yt-dlp progress hook to abort a download cleanly."""


class DownloadWorker(QThread):
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
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation. The progress hook will raise on the next
        yt-dlp callback, aborting the download without killing the thread."""
        self._cancelled = True

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

    def _thumbnail_supported(self) -> bool:
        """Return True if the target container reliably supports embedded cover art."""
        if self.audio_only:
            return self.container in {"mp3", "m4a"}
        return self.container in {"mp4", "mkv"}

    def _extra_postprocessors(self) -> list[dict]:
        """Build metadata/thumbnail postprocessors shared by audio and video paths.

        Order matters: FFmpegMetadata must run before EmbedThumbnail so the
        cover art survives the metadata rewrite.
        """
        pps: list[dict] = []
        if self.embed_metadata:
            # FFmpegMetadata already prefers YouTube's music fields when present:
            # it maps %(track)s -> title and %(artist)s -> artist automatically,
            # falling back to the raw video title only when no music metadata
            # exists. We deliberately avoid MetadataParser/INTERPRET here because
            # it overwrites the infodict title with "NA" when %(track)s is empty,
            # which corrupts both the output filename and the title tag.
            pps.append({"key": "FFmpegMetadata", "add_metadata": True})
        if self.embed_thumbnail and self._thumbnail_supported():
            pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
        return pps

    def _build_opts(self) -> dict:
        opts: dict = {
            "noplaylist": not self.playlist,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._hook],
        }
        # Add browser impersonation for platforms that require it (Dailymotion, Vimeo, Instagram, etc.)
        # Try to use ImpersonateTarget for newer yt-dlp versions, fall back to string for older versions
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            try:
                # Try with a commonly available target
                opts["impersonate"] = ImpersonateTarget.from_str("chrome")
            except Exception:
                # Fall back to string for older yt-dlp
                opts["impersonate"] = "chrome"
        except ImportError:
            # Older yt-dlp without impersonate module
            opts["impersonate"] = "chrome"
        if self.archive_path:
            opts["download_archive"] = self.archive_path

        # Add cookie support for platforms that require authentication (Instagram, Vimeo private, etc.)
        if self.cookies_from_browser:
            opts["cookies_from_browser"] = ("chrome",)
        elif self.cookie_path and Path(self.cookie_path).exists():
            opts["cookies"] = self.cookie_path

        # Download the thumbnail file so EmbedThumbnail has something to embed.
        if self.embed_thumbnail and self._thumbnail_supported():
            opts["writethumbnail"] = True

        extra_pps = self._extra_postprocessors()

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
                }] + extra_pps,
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
        if extra_pps:
            opts["postprocessors"] = extra_pps
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


class PlaylistInspectWorker(QThread):
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
        self._cancelled    = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        dry_opts = {
            "quiet": True, "no_warnings": True,
            "skip_download": True, "extract_flat": True,
        }
        # Add browser impersonation
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            try:
                dry_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
            except Exception:
                dry_opts["impersonate"] = "chrome"
        except ImportError:
            dry_opts["impersonate"] = "chrome"
        
        # Add cookie support for playlist inspection
        if self.cookies_from_browser:
            dry_opts["cookies_from_browser"] = ("chrome",)
        elif self.cookie_path and Path(self.cookie_path).exists():
            dry_opts["cookies"] = self.cookie_path
        
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


class FileSizeWorker(QThread):
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
            opts: dict = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
            }
            # Add browser impersonation
            try:
                from yt_dlp.networking.impersonate import ImpersonateTarget
                try:
                    opts["impersonate"] = ImpersonateTarget.from_str("chrome")
                except Exception:
                    opts["impersonate"] = "chrome"
            except ImportError:
                opts["impersonate"] = "chrome"
            
            # Add cookie support for metadata fetching
            if self.cookies_from_browser:
                opts["cookies_from_browser"] = ("chrome",)
            elif self.cookie_path and Path(self.cookie_path).exists():
                opts["cookies"] = self.cookie_path
            
            if self.audio_only:
                opts["format"] = "ba/b"
            elif self.height:
                opts["format"] = f"bv*[height<={self.height}]+ba/b[height<={self.height}]/b"
            else:
                opts["format"] = "bv*+ba/b"

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

            self.result.emit(title, duration, filesize_mb, fmt_note or self.fmt,
                             self.audio_only, resolution)

        except Exception as exc:
            self.error.emit(str(exc))
