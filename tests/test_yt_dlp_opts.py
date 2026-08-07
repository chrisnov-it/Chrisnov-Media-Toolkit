"""Tests for app.yt_dlp_opts — cookie/impersonation option builders, format
opts, dry-run opts, and thumbnail/postprocessor helpers.

These cover the logic extracted out of worker.py during the workers refactor,
including the corrected yt-dlp option keys (cookiefile / cookiesfrombrowser).
"""

import sys

from app.yt_dlp_opts import (
    build_cookie_opts,
    build_dry_opts,
    build_format_opts,
    _extra_postprocessors,
    _thumbnail_supported,
)


# -- build_cookie_opts -------------------------------------------------------

class TestBuildCookieOpts:
    def test_browser_cookies(self):
        opts = build_cookie_opts(None, True)
        assert opts["cookiesfrombrowser"] == ("chrome",)
        assert opts["impersonate"] == "chrome"

    def test_cookie_file_when_exists(self, tmp_path):
        f = tmp_path / "cookies.txt"
        f.write_text("x")
        opts = build_cookie_opts(str(f), False)
        assert opts["cookiefile"] == str(f)
        assert opts["impersonate"] == "chrome"

    def test_missing_cookie_file_ignored(self, tmp_path):
        ghost = str(tmp_path / "nope.txt")
        assert build_cookie_opts(ghost, False) == {}

    def test_nothing_configured_yields_empty(self):
        assert build_cookie_opts(None, False) == {}

    def test_no_impersonation_without_curl_cffi(self, tmp_path, monkeypatch):
        f = tmp_path / "cookies.txt"
        f.write_text("x")
        # Force the optional curl_cffi import to fail → no impersonate key.
        monkeypatch.setitem(sys.modules, "curl_cffi.requests", None)
        opts = build_cookie_opts(str(f), False)
        assert "impersonate" not in opts
        assert opts["cookiefile"] == str(f)


# -- _thumbnail_supported ----------------------------------------------------

class TestThumbnailSupported:
    def test_audio_containers(self):
        assert _thumbnail_supported(True, "mp3") is True
        assert _thumbnail_supported(True, "m4a") is True
        assert _thumbnail_supported(True, "opus") is False

    def test_video_containers(self):
        assert _thumbnail_supported(False, "mp4") is True
        assert _thumbnail_supported(False, "mkv") is True
        assert _thumbnail_supported(False, "webm") is False


# -- _extra_postprocessors ----------------------------------------------------

class TestExtraPostprocessors:
    def test_metadata_only(self):
        pps = _extra_postprocessors(True, False, True, "mp3")
        assert [p["key"] for p in pps] == ["FFmpegMetadata"]

    def test_metadata_runs_before_thumbnail(self):
        pps = _extra_postprocessors(True, True, True, "mp3")
        assert [p["key"] for p in pps] == ["FFmpegMetadata", "EmbedThumbnail"]

    def test_thumbnail_skipped_for_unsupported_container(self):
        assert _extra_postprocessors(False, True, True, "opus") == []

    def test_nothing_when_all_disabled(self):
        assert _extra_postprocessors(False, False, False, "mp4") == []

# -- build_format_opts -------------------------------------------------------

def _audio_opts(**kw):
    base = dict(
        audio_only=True, height=None, container="mp3", bitrate=192,
        embed_metadata=False, embed_thumbnail=False, outdir="/out",
        archive_path=None, playlist=False,
    )
    base.update(kw)
    return build_format_opts(**base)


class TestBuildFormatOpts:
    def test_noplaylist_default(self):
        assert _audio_opts()["noplaylist"] is True

    def test_playlist_sets_noplaylist_false(self):
        assert _audio_opts(playlist=True)["noplaylist"] is False

    def test_audio_format_and_outtmpl(self):
        opts = _audio_opts()
        assert opts["format"] == "ba/b"
        assert opts["outtmpl"].endswith("%(title)s.%(ext)s")

    def test_audio_codec_by_container(self):
        assert _audio_opts(container="m4a")["postprocessors"][0]["preferredcodec"] == "aac"
        assert _audio_opts(container="opus")["postprocessors"][0]["preferredcodec"] == "opus"
        assert _audio_opts(container="mp3")["postprocessors"][0]["preferredcodec"] == "mp3"

    def test_audio_bitrate(self):
        pp = _audio_opts(bitrate=320)["postprocessors"][0]
        assert pp["preferredquality"] == "320"
        assert pp["key"] == "FFmpegExtractAudio"

    def test_archive_path(self):
        opts = _audio_opts(archive_path="/x/arch.txt")
        assert opts["download_archive"] == "/x/arch.txt"

    def test_video_format_with_height(self):
        opts = build_format_opts(
            audio_only=False, height=720, container="mp4", bitrate=0,
            embed_metadata=False, embed_thumbnail=False, outdir="/out",
            archive_path=None, playlist=False,
        )
        assert opts["format"] == "bv*[height<=720]+ba/b[height<=720]/b"
        assert opts["merge_output_format"] == "mp4"
        assert "[%(height)sp]" in opts["outtmpl"]

    def test_video_format_without_height(self):
        opts = build_format_opts(
            audio_only=False, height=None, container="mp4", bitrate=0,
            embed_metadata=False, embed_thumbnail=False, outdir="/out",
            archive_path=None, playlist=False,
        )
        assert opts["format"] == "bv*+ba/b"

    def test_writethumbnail_when_supported(self):
        opts = _audio_opts(embed_thumbnail=True, container="mp3")
        assert opts["writethumbnail"] is True

    def test_writethumbnail_skipped_for_unsupported_container(self):
        opts = _audio_opts(embed_thumbnail=True, container="opus")
        assert "writethumbnail" not in opts


# -- build_dry_opts ----------------------------------------------------------

class TestBuildDryOpts:
    def test_audio_only_format(self):
        opts = build_dry_opts(True, None, False)
        assert opts["skip_download"] is True
        assert opts["format"] == "ba/b"
        assert opts["quiet"] is True and opts["no_warnings"] is True

    def test_video_format(self):
        opts = build_dry_opts(False, None, False)
        assert opts["format"] == "bv*+ba/b"

    def test_merges_cookie_opts(self, tmp_path):
        f = tmp_path / "cookies.txt"
        f.write_text("x")
        opts = build_dry_opts(False, str(f), False)
        assert opts["cookiefile"] == str(f)

