"""Shared yt-dlp option builders — cookie handling, impersonation, and
format/dry-run option construction.

Extracted from worker.py to eliminate the 3x duplicated cookie/impersonation
block previously copy-pasted across DownloadWorker, PlaylistInspectWorker,
and FileSizeWorker, plus the duplicated format-opts and thumbnail-support
logic in DownloadWorker._build_opts / _thumbnail_supported /
_extra_postprocessors.
"""

from __future__ import annotations

from pathlib import Path


def build_cookie_opts(
    cookie_path: str | None,
    cookies_from_browser: bool,
) -> dict:
    """Return a dict of cookie + impersonation options for a yt-dlp opts dict.

    Callers do: ``opts.update(build_cookie_opts(cookie_path, cookies_from_browser))``

    Behavior matches the previous inline code:
      - cookies_from_browser=True → use browser cookies
      - cookie_path exists → use cookies file
      - impersonate=chrome is only added when cookies are in use
        (YouTube works fine without it; only Instagram/Vimeo need it)
    """
    opts: dict = {}
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = ("chrome",)
    elif cookie_path and Path(cookie_path).exists():
        opts["cookiefile"] = cookie_path

    needs_impersonation = cookies_from_browser or bool(
        cookie_path and Path(cookie_path).exists()
    )
    if needs_impersonation:
        try:
            from curl_cffi.requests import Session as _CurlSession  # noqa: F401

            opts["impersonate"] = "chrome"
        except ImportError:
            pass

    return opts


# ---------------------------------------------------------------------------
# Thumbnail support
# ---------------------------------------------------------------------------

def _thumbnail_supported(audio_only: bool, container: str) -> bool:
    """Return True if the target container reliably supports embedded cover art.

    Mirrors the original DownloadWorker._thumbnail_supported() method.
    Uses the canonical container lists from constants.py; opus (audio) and
    webm (video) are excluded since they do not reliably support thumbnail
    embedding.
    """
    if audio_only:
        return container in {"mp3", "m4a"}
    return container in {"mp4", "mkv"}


# ---------------------------------------------------------------------------
# Extra postprocessors (metadata + thumbnail)
# ---------------------------------------------------------------------------

def _extra_postprocessors(
    embed_metadata: bool,
    embed_thumbnail: bool,
    audio_only: bool,
    container: str,
) -> list[dict]:
    """Build metadata/thumbnail postprocessors shared by audio and video paths.

    Order matters: FFmpegMetadata must run before EmbedThumbnail so the
    cover art survives the metadata rewrite.

    Mirrors the original DownloadWorker._extra_postprocessors() method.
    """
    pps: list[dict] = []
    if embed_metadata:
        # FFmpegMetadata already prefers YouTube's music fields when present:
        # it maps %(track)s -> title and %(artist)s -> artist automatically,
        # falling back to the raw video title only when no music metadata
        # exists. We deliberately avoid MetadataParser/INTERPRET here because
        # it overwrites the infodict title with "NA" when %(track)s is empty,
        # which corrupts both the output filename and the title tag.
        pps.append({"key": "FFmpegMetadata", "add_metadata": True})
    if embed_thumbnail and _thumbnail_supported(audio_only, container):
        pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    return pps


# ---------------------------------------------------------------------------
# Format / full opts construction for DownloadWorker
# ---------------------------------------------------------------------------

_CODEC_BY_CONTAINER: dict[str, str] = {"mp3": "mp3", "m4a": "aac", "opus": "opus"}


def build_format_opts(
    *,
    audio_only: bool,
    height: int | None,
    container: str,
    bitrate: int,
    embed_metadata: bool,
    embed_thumbnail: bool,
    outdir: str,
    archive_path: str | None,
    playlist: bool,
) -> dict:
    """Construct the base yt-dlp opts dict for a download.

    Handles the audio-only vs video branch logic that was previously inlined
    in DownloadWorker._build_opts(), including format selection, outtmpl,
    postprocessors, download_archive, and noplaylist.
    """
    opts: dict = {
        "noplaylist": not playlist,
        "quiet": True,
        "no_warnings": True,
    }
    if archive_path:
        opts["download_archive"] = archive_path

    extra_pps = _extra_postprocessors(embed_metadata, embed_thumbnail, audio_only, container)

    # Download the thumbnail file so EmbedThumbnail has something to embed.
    if embed_thumbnail and _thumbnail_supported(audio_only, container):
        opts["writethumbnail"] = True

    if audio_only:
        codec = _CODEC_BY_CONTAINER.get(container, "mp3")
        opts.update({
            "format": "ba/b",
            # Use %(ext)s — FFmpegExtractAudio rewrites the extension after
            # conversion, so hardcoding it here causes a double extension
            # (e.g. "title.m4a.m4a").
            "outtmpl": str(Path(outdir) / "%(title)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": str(bitrate),
            }] + extra_pps,
        })
        return opts

    # Video path
    if height:
        fmt = f"bv*[height<={height}]+ba/b[height<={height}]/b"
    else:
        fmt = "bv*+ba/b"
    opts.update({
        "format": fmt,
        "merge_output_format": container,
        "outtmpl": str(Path(outdir) / "%(title)s [%(height)sp].%(ext)s"),
    })
    if extra_pps:
        opts["postprocessors"] = extra_pps
    return opts


# ---------------------------------------------------------------------------
# Dry-run opts for metadata inspection (FileSizeWorker)
# ---------------------------------------------------------------------------

def build_dry_opts(
    audio_only: bool,
    cookie_path: str | None,
    cookies_from_browser: bool,
) -> dict:
    """Construct yt-dlp opts for a metadata-only extraction (skip_download=True).

    Recovered from the original FileSizeWorker.run() inline logic: builds a
    quiet dry-run opts dict with cookie/impersonation support and the
    appropriate format selection.
    """
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    opts.update(build_cookie_opts(cookie_path, cookies_from_browser))

    if audio_only:
        opts["format"] = "ba/b"
    else:
        opts["format"] = "bv*+ba/b"
    return opts