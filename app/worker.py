"""Download worker threaded for the GUI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import Signal
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled, remove_terminal_sequences

from .base_worker import CancellableWorker
from .constants import AUDIO_CONTAINERS, VIDEO_CONTAINERS
from .yt_dlp_opts import (
    JS_RUNTIME_OPTS,
    _thumbnail_supported,
    build_cookie_opts,
    build_dry_opts,
    build_format_opts,
)

# ---------------------------------------------------------------------------
# yt-dlp update hint
# ---------------------------------------------------------------------------

# Lowercase fragments that mark an error as a yt-dlp extractor problem
# rather than a network/filesystem one. YouTube A/B-tests its pages and
# players; videos in a new cohort fail with these messages until yt-dlp
# ships a fix while every other URL keeps working — which is exactly why
# it looks so random ("only this one video fails").
_YTDLP_UPDATE_MARKERS = (
    "not a bot",             # "Sign in to confirm you're not a bot"
    "unable to extract",     # ExtractorError: unable to extract ...
    "signature extraction",  # player signature changed
    "nsig",                  # nsig extraction failed / could not decipher
)


def ytdlp_update_hint(error: str) -> str | None:
    """Mode-aware "update yt-dlp" hint for extractor-type download errors.

    Returns None when the error doesn't look like an outdated-yt-dlp
    problem (timeout, missing file, bad URL, ...) so callers only show
    the hint when it can actually help. Frozen builds get a "download the
    latest app release" hint (their yt-dlp is baked into the exe); source
    installs get the pip command from the README.
    """
    if not error:
        return None
    if not any(marker in error.lower() for marker in _YTDLP_UPDATE_MARKERS):
        return None
    if getattr(sys, "frozen", False):
        return (
            "This is usually fixed in a newer app release — "
            "please download the latest version."
        )
    return (
        "This is usually fixed by updating yt-dlp — run "
        "pip install -U yt-dlp curl_cffi, then restart the app."
    )


class _CancelledError(DownloadCancelled):
    """Raised from the yt-dlp progress hook to abort a download cleanly.

    Deliberately subclasses yt-dlp's ``DownloadCancelled``: playlist runs
    set ``ignoreerrors``, and with that on yt-dlp swallows any plain
    exception per playlist entry and moves on to the next video - a cancel
    would merely *skip* the rest of the playlist instead of stopping it.
    ``_handle_extraction_exceptions`` re-raises ``DownloadCancelled``
    unconditionally (regardless of ``ignoreerrors``), so the cancel still
    propagates out of ``extract_info()`` and aborts the run.
    """


class _PlaylistLogger:
    """yt-dlp logger for playlist runs (installed together with
    ``ignoreerrors``).

    With ``ignoreerrors`` on, yt-dlp reports failures through the logger
    instead of raising them, so these lines are the only record of *why*
    playlist items failed - they distinguish "everything failed" (emit
    ``failed``) from partial success (emit the saved files plus counts).

    ``error`` mirrors the line to stderr exactly like yt-dlp would write it
    without a logger, so the console output the user watches is unchanged.
    ``debug``/``info``/``warning`` are no-ops: the opts set
    quiet/no_warnings, which already suppress those messages when no
    logger is installed.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        # Store display-ready text (ANSI colors stripped) for the UI, but
        # forward the original line so console output stays as before.
        self.errors.append(remove_terminal_sequences(message))
        print(message, file=sys.stderr)


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
        self._logger: _PlaylistLogger | None = None

    def run(self) -> None:
        try:
            ytdl_opts = self._build_opts()
            self.status.emit(f"{self.idx_label} Resolving info...")
            with YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if self._cancelled:
                    return
                entries = info.get("entries") if isinstance(info, dict) else None
                if entries or (self.playlist and isinstance(entries, (list, tuple))):
                    # Truthy entries (old behavior) or an empty playlist run:
                    # both are playlist-shaped results.
                    self._finish_playlist(info, ydl, ytdl_opts)
                    return
                if info is None:
                    # Playlist runs use ignoreerrors, so a failed fetch is
                    # reported through the logger rather than raised.
                    self.failed.emit(self._first_error() or "Could not fetch video info")
                    return
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
        except Exception as e:  # noqa: BLE001 — run() boundary: report any failure
            if not self._cancelled:
                # DownloadError messages carry ANSI color codes when yt-dlp's
                # stderr was a tty — history/status display must stay clean.
                self.failed.emit(remove_terminal_sequences(str(e)))

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

        if self.playlist:
            # A playlist must survive individual bad items: 'only_download'
            # makes yt-dlp report a failed entry (mid-playlist 403/503, a
            # private/unavailable video, ...) and continue with the rest
            # instead of raising out of extract_info() and abandoning every
            # item after the first failure. With ignoreerrors on, those
            # errors no longer reach the console either - install a
            # capturing logger so the run can still tell the user why
            # items failed.
            opts["ignoreerrors"] = "only_download"
            self._logger = _PlaylistLogger()
            opts["logger"] = self._logger
            # Pace the entries a little: hammering item after item is what
            # triggers YouTube's mid-run rate limiting (403/503) in the
            # first place - a uniform 1-2s before each stream download.
            opts["sleep_interval"] = 1
            opts["max_sleep_interval"] = 2

        # Download the thumbnail file so EmbedThumbnail has something to embed.
        if self.embed_thumbnail and _thumbnail_supported(self.audio_only,
                                                         self.container):
            opts["writethumbnail"] = True

        return opts

    def _finish_playlist(self, info: dict, ydl: YoutubeDL, opts: dict) -> None:
        """Handle a playlist result that yt-dlp returned without raising.

        Playlist runs use ``ignoreerrors``, so a mid-playlist failure is
        reported through the logger and skipped instead of aborting the
        run. Entries that ended up with no file on disk are retried once
        with a fresh single-video extraction (the media URL for such
        failures is usually expired or throttled - re-extracting fetches a
        new one), then the outcome is reported honestly:

        - saved files  -> ``playlist_files:`` payload carrying the paths
          plus failed/total counts (partial success is visible to the
          caller instead of silently looking like a full run);
        - nothing saved -> ``failed`` with the first captured error, or
          the legacy ``playlist:N:title`` discovery payload when no error
          was captured at all (yt-dlp succeeded but we could not resolve
          the paths - let the caller discover what is on disk).
        """
        entries = list(info.get("entries") or [])
        total = len(entries)
        saved: list[str] = []
        seen: set[str] = set()
        retryable: list[dict] = []
        failed = 0
        for entry in entries:
            path = self._saved_path_for_entry(entry, ydl)
            if path and Path(path).exists():
                if path not in seen:
                    saved.append(path)
                    seen.add(path)
                continue
            failed += 1
            if isinstance(entry, dict):
                retryable.append(entry)

        if retryable and not self._cancelled:
            failed -= self._retry_failed_entries(retryable, opts, saved, seen)

        if self._cancelled:
            return

        if saved:
            payload = {"files": saved, "failed": failed, "total": total}
            self.finished_ok.emit("playlist_files:" + json.dumps(payload))
            return

        # Nothing reached the disk: report why instead of a fake success.
        first_error = self._first_error()
        if first_error:
            reason = f"All {total} item(s) failed — {first_error}" if total else first_error
            self.failed.emit(reason)
        elif total == 0:
            self.failed.emit("Playlist contains no downloadable items")
        else:
            self.finished_ok.emit(f"playlist:{total}:{info.get('title', '?')}")

    def _retry_failed_entries(self, entries: list[dict], opts: dict,
                              saved: list[str], seen: set[str]) -> int:
        """Retry each failed playlist entry once with a fresh extraction.

        Returns how many entries produced a file (added to *saved*).
        Re-extracting the URL is the point: a mid-download 403/503 usually
        means the streaming URL expired or was throttled, and a fresh
        extraction gets a new one. Each retry reuses the batch opts with
        noplaylist forced on, so the entry URL is fetched as a single
        video and progress/cancel keep working through the same hook.
        """
        urls: list[str] = []
        for entry in entries:
            # webpage_url first (yt-dlp's "the page this entry came from" —
            # the watch page for YouTube entries), but never retry the
            # playlist URL itself: container-derived entries (XSPF, generic
            # multi-video pages, ...) report it as their webpage_url, and
            # re-extracting it would re-run every entry in the list. For
            # those entries entry["url"] is the entry's own location.
            for key in ("webpage_url", "original_url", "url"):
                url = entry.get(key)
                if (isinstance(url, str)
                        and url.startswith(("http://", "https://"))
                        and url != self.url):
                    urls.append(url)
                    break
        if not urls:
            return 0

        recovered = 0
        retry_opts = {**opts, "noplaylist": True}
        with YoutubeDL(retry_opts) as ydl:
            for i, url in enumerate(urls, 1):
                if self._cancelled:
                    break
                self.status.emit(f"{self.idx_label} Retrying failed item {i}/{len(urls)}...")
                try:
                    fresh = ydl.extract_info(url, download=True)
                except DownloadCancelled:
                    raise  # user cancel must stop the whole run
                except Exception:  # noqa: BLE001 — per-item failure, already logged
                    continue
                path = self._saved_path_for_entry(fresh, ydl)
                if path and Path(path).exists():
                    recovered += 1
                    if path not in seen:
                        saved.append(path)
                        seen.add(path)
        return recovered

    def _first_error(self) -> str | None:
        """First error line yt-dlp reported during this run, display-ready
        (ANSI colors and the redundant "ERROR: " prefix stripped), or None."""
        if self._logger is None or not self._logger.errors:
            return None
        return self._logger.errors[0].removeprefix("ERROR: ")

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
        except Exception:  # noqa: BLE001 — best-effort extra candidate only
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
        dry_opts.update(JS_RUNTIME_OPTS)
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
            except Exception as exc:  # noqa: BLE001 — report fetch failure per URL
                if not self._cancelled:
                    self.error.emit(p_url, remove_terminal_sequences(str(exc)))
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

        except Exception as exc:  # noqa: BLE001 — run() boundary: report any failure
            if not self._cancelled:
                self.error.emit(remove_terminal_sequences(str(exc)))
