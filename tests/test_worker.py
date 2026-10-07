"""Tests for app.worker — FileSizeWorker cancellation, yt-dlp update hint,
and DownloadWorker playlist resilience.

Regression: MainWindow._start_download() calls FileSizeWorker.cancel() when
the user presses Start while an Info fetch is still in flight. Before the fix,
FileSizeWorker had no cancel() and the call raised AttributeError, aborting
the download start.
"""

import json
import sys

import pytest
from yt_dlp.utils import DownloadCancelled

from app.worker import (
    DownloadWorker,
    FileSizeWorker,
    _CancelledError,
    _PlaylistLogger,
    ytdlp_update_hint,
)


class _FakeYoutubeDL:
    """Stand-in for yt_dlp.YoutubeDL returning canned metadata."""

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return {
            "title": "Test Video",
            "duration": 120,
            "filesize": 10 * 1024 * 1024,
            "format_note": "1080p",
        }


class _RaisingYoutubeDL(_FakeYoutubeDL):
    def extract_info(self, url, download=False):
        raise RuntimeError("network down")


def _make_worker() -> FileSizeWorker:
    return FileSizeWorker("https://example.com/watch", False, None, "mp4")


class TestFileSizeWorkerCancel:
    def test_cancel_sets_flag(self):
        w = _make_worker()
        assert w._cancelled is False
        w.cancel()
        assert w._cancelled is True

    def test_uncancelled_run_emits_result(self, monkeypatch):
        """Sanity: without cancel, run() emits exactly one result, no error."""
        monkeypatch.setattr("app.worker.YoutubeDL", _FakeYoutubeDL)
        w = _make_worker()
        results, errors = [], []
        w.result.connect(lambda *a: results.append(a))
        w.error.connect(errors.append)

        w.run()  # synchronous — no event loop needed

        assert errors == []
        assert len(results) == 1
        title, duration, filesize_mb, _fmt_note, audio_only, _resolution = results[0]
        assert title == "Test Video"
        assert duration == 120
        assert filesize_mb == 10.0
        assert audio_only is False

    def test_cancelled_run_emits_nothing(self, monkeypatch):
        """After cancel(), a completing fetch must not emit result or error."""
        monkeypatch.setattr("app.worker.YoutubeDL", _FakeYoutubeDL)
        w = _make_worker()
        results, errors = [], []
        w.result.connect(lambda *a: results.append(a))
        w.error.connect(errors.append)

        w.cancel()
        w.run()

        assert results == []
        assert errors == []

    def test_cancelled_run_swallows_errors(self, monkeypatch):
        """After cancel(), a failing fetch must not emit error either."""
        monkeypatch.setattr("app.worker.YoutubeDL", _RaisingYoutubeDL)
        w = _make_worker()
        results, errors = [], []
        w.result.connect(lambda *a: results.append(a))
        w.error.connect(errors.append)

        w.cancel()
        w.run()

        assert results == []
        assert errors == []

    def test_uncancelled_failure_emits_error(self, monkeypatch):
        monkeypatch.setattr("app.worker.YoutubeDL", _RaisingYoutubeDL)
        w = _make_worker()
        results, errors = [], []
        w.result.connect(lambda *a: results.append(a))
        w.error.connect(errors.append)

        w.run()

        assert results == []
        assert errors == ["network down"]


class TestYtdlpUpdateHint:
    """The hint must fire only for extractor-type errors and adapt the
    advice to how the app runs (frozen exe vs source checkout)."""

    def test_hits_extractor_errors(self):
        for err in (
            "ERROR: [youtube] dQw4: Sign in to confirm you're not a bot",
            "ERROR: unable to extract initial data",
            "nsig extraction failed: could not decipher",
            "Signature extraction failed: player JS changed",
        ):
            assert ytdlp_update_hint(err) is not None, err

    def test_ignores_non_extractor_errors(self):
        for err in ("connection timeout", "File not found: /tmp/x.mp3", ""):
            assert ytdlp_update_hint(err) is None

    def test_match_is_case_insensitive(self):
        assert ytdlp_update_hint("UNABLE TO EXTRACT IX02") is not None

    def test_source_mode_hints_pip(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        hint = ytdlp_update_hint("Unable to extract video info")
        assert hint is not None
        assert "pip install -U yt-dlp" in hint

    def test_frozen_mode_hints_app_release(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        hint = ytdlp_update_hint("Unable to extract video info")
        assert hint is not None
        assert "latest" in hint
        assert "pip" not in hint


# ---------------------------------------------------------------------------
# DownloadWorker playlist resilience
# ---------------------------------------------------------------------------

class _FakeEntryYDL:
    """Minimal YoutubeDL stand-in for _handle_extraction_exceptions."""

    def __init__(self, ignoreerrors="only_download"):
        self.params = {"ignoreerrors": ignoreerrors}
        self.reported: list = []

    def report_error(self, *args, **kwargs):
        self.reported.append(args)


def _fake_ydl(main, retry=None):
    """Build a fake yt_dlp.YoutubeDL class for DownloadWorker runs.

    *main* is the result of the primary extract_info() call, *retry* the
    one for the single-video retry pass (opts with noplaylist=True);
    retry=None reuses *main*. Values may be dicts, None, Exceptions, or
    callables receiving (url, opts) — that is how tests inject captured
    yt-dlp error lines through opts["logger"]. Records every constructed
    opts dict (``created``) and every retry URL (``retried``).
    """
    created: list[dict] = []
    retried: list[str] = []

    class _FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts
            created.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def prepare_filename(self, info):
            return (info or {}).get("filepath") or ""

        def extract_info(self, url, download=False):
            is_retry = bool(self.opts.get("noplaylist"))
            if is_retry:
                retried.append(url)
            result = retry if (is_retry and retry is not None) else main
            if callable(result):
                result = result(url, self.opts)
            if isinstance(result, Exception):
                raise result
            return result

    _FakeYoutubeDL.created = created
    _FakeYoutubeDL.retried = retried
    return _FakeYoutubeDL


def _download_worker(tmp_path, *, playlist: bool) -> DownloadWorker:
    return DownloadWorker(
        url=("https://www.youtube.com/playlist?list=PL1" if playlist
             else "https://youtu.be/abc"),
        height=None, container="mp4", bitrate=128, outdir=str(tmp_path),
        audio_only=False, playlist=playlist,
    )


class TestCancelPropagation:
    """Playlist runs set ignoreerrors, which makes yt-dlp report and skip
    plain exceptions per entry instead of raising them — the cancel error
    must never be one of them, or Cancel would only skip to the next item."""

    def test_cancel_error_is_download_cancelled(self):
        assert issubclass(_CancelledError, DownloadCancelled)

    def test_yt_dlp_reraises_cancelled_despite_ignoreerrors(self):
        from yt_dlp.YoutubeDL import YoutubeDL

        @YoutubeDL._handle_extraction_exceptions
        def _entry(_self):
            raise _CancelledError()

        with pytest.raises(_CancelledError):
            _entry(_FakeEntryYDL())

    def test_yt_dlp_swallows_plain_errors_when_ignoring(self):
        """Documents the flip side: a plain per-entry error (the 403 case)
        is reported instead of raised, which is exactly what makes a
        playlist continue after a mid-run failure."""
        from yt_dlp.YoutubeDL import YoutubeDL

        @YoutubeDL._handle_extraction_exceptions
        def _entry(_self):
            raise RuntimeError("HTTP Error 403: Forbidden")

        fake = _FakeEntryYDL()
        assert _entry(fake) is None
        assert fake.reported


class TestPlaylistOpts:
    def test_playlist_opts_enable_resilience(self, tmp_path):
        opts = _download_worker(tmp_path, playlist=True)._build_opts()
        assert opts["ignoreerrors"] == "only_download"
        assert isinstance(opts["logger"], _PlaylistLogger)
        assert opts["noplaylist"] is False
        assert opts["sleep_interval"] == 1
        assert opts["max_sleep_interval"] == 2

    def test_single_video_opts_untouched(self, tmp_path):
        opts = _download_worker(tmp_path, playlist=False)._build_opts()
        assert "ignoreerrors" not in opts
        assert "logger" not in opts
        assert "sleep_interval" not in opts
        assert opts["noplaylist"] is True


class TestPlaylistRun:
    def _run(self, monkeypatch, tmp_path, fake):
        monkeypatch.setattr("app.worker.YoutubeDL", fake)
        w = _download_worker(tmp_path, playlist=True)
        oks: list[str] = []
        fails: list[str] = []
        w.finished_ok.connect(oks.append)
        w.failed.connect(fails.append)
        w.run()
        return w, oks, fails

    def test_partial_failure_retries_and_reports(self, monkeypatch, tmp_path):
        """One item 403s mid-run: it must be retried with a fresh
        extraction, and every saved file reported (with counts)."""
        ok = tmp_path / "one.mp4"
        ok.write_bytes(b"one")
        missing = tmp_path / "two.mp4"  # failed during the main run

        def main(_url, opts):
            opts["logger"].error(
                "ERROR: unable to download video data: HTTP Error 403: Forbidden"
            )
            return {
                "title": "My List",
                "entries": [
                    {"filepath": str(ok), "webpage_url": "https://ex/1"},
                    {"filepath": str(missing), "webpage_url": "https://ex/2"},
                ],
            }

        def retry(_url, _opts):
            missing.write_bytes(b"two")  # fresh extraction succeeds
            return {"filepath": str(missing)}

        fake = _fake_ydl(main, retry)
        _, oks, fails = self._run(monkeypatch, tmp_path, fake)

        assert fails == []
        assert fake.retried == ["https://ex/2"]
        payload = json.loads(oks[0].removeprefix("playlist_files:"))
        assert payload == {
            "files": [str(ok), str(missing)],
            "failed": 0,
            "total": 2,
        }

    def test_retry_failure_reports_partial_counts(self, monkeypatch, tmp_path):
        ok = tmp_path / "one.mp4"
        ok.write_bytes(b"one")
        missing = tmp_path / "two.mp4"

        def main(_url, opts):
            opts["logger"].error(
                "ERROR: unable to download video data: HTTP Error 503: Service Unavailable"
            )
            return {
                "title": "L",
                "entries": [
                    {"filepath": str(ok), "webpage_url": "https://ex/1"},
                    {"filepath": str(missing), "webpage_url": "https://ex/2"},
                ],
            }

        fake = _fake_ydl(main, lambda _url, _opts: None)
        _, oks, fails = self._run(monkeypatch, tmp_path, fake)

        assert fails == []
        payload = json.loads(oks[0].removeprefix("playlist_files:"))
        assert payload == {"files": [str(ok)], "failed": 1, "total": 2}

    def test_total_failure_emits_captured_error(self, monkeypatch, tmp_path):
        a = tmp_path / "a.mp4"
        b = tmp_path / "b.mp4"  # neither ever written

        def main(_url, opts):
            opts["logger"].error(
                "ERROR: unable to download video data: HTTP Error 403: Forbidden"
            )
            return {
                "title": "L",
                "entries": [
                    {"filepath": str(a), "webpage_url": "https://ex/1"},
                    {"filepath": str(b), "webpage_url": "https://ex/2"},
                ],
            }

        fake = _fake_ydl(main, lambda _url, _opts: None)
        _, oks, fails = self._run(monkeypatch, tmp_path, fake)

        assert oks == []
        assert fails == [
            "All 2 item(s) failed — unable to download video data: "
            "HTTP Error 403: Forbidden"
        ]

    def test_failed_fetch_emits_captured_error(self, monkeypatch, tmp_path):
        def main(_url, opts):
            opts["logger"].error("ERROR: Unable to extract video data")
            return None

        fake = _fake_ydl(main)
        _, oks, fails = self._run(monkeypatch, tmp_path, fake)

        assert oks == []
        assert fails == ["Unable to extract video data"]

    def test_empty_playlist_fails_cleanly(self, monkeypatch, tmp_path):
        fake = _fake_ydl({"title": "Empty", "entries": []})
        _, oks, fails = self._run(monkeypatch, tmp_path, fake)

        assert oks == []
        assert fails == ["Playlist contains no downloadable items"]

    def test_unresolvable_paths_fall_back_to_discovery(self, monkeypatch, tmp_path):
        """No captured error but nothing found on disk: keep the legacy
        playlist:N:title payload so the caller can discover the files."""
        a = tmp_path / "a.mp4"  # missing, and yt-dlp reported no error
        fake = _fake_ydl(
            {"title": "L", "entries": [{"filepath": str(a), "webpage_url": "https://ex/1"}]},
            lambda _url, _opts: None,
        )
        _, oks, fails = self._run(monkeypatch, tmp_path, fake)

        assert fails == []
        assert oks == ["playlist:1:L"]
        assert fake.retried == ["https://ex/1"]

    def test_retry_never_reuses_the_playlist_url(self, monkeypatch, tmp_path):
        """Container-derived entries (XSPF, generic multi-video pages)
        report the playlist URL as their webpage_url. Retrying it would
        re-run the whole list (real yt-dlp did exactly that in the local
        lab), so the retry must fall back to the entry's own URL — and
        skip entries that only know the playlist URL."""
        got_a = tmp_path / "a.mp4"
        got_b = tmp_path / "b.mp4"
        playlist_url = "http://pl/list.xml"
        entries = [
            {"filepath": str(got_a), "webpage_url": playlist_url,
             "url": "http://pl/a.mp4"},
            {"filepath": str(got_b), "webpage_url": playlist_url},
        ]

        def retry(url, _opts):
            assert url == "http://pl/a.mp4"  # entry's own URL, not the list
            got_a.write_bytes(b"a")
            return {"filepath": str(got_a)}

        fake = _fake_ydl({"title": "L", "entries": entries}, retry)
        monkeypatch.setattr("app.worker.YoutubeDL", fake)
        w = DownloadWorker(
            url=playlist_url, height=None, container="mp4", bitrate=128,
            outdir=str(tmp_path), audio_only=False, playlist=True,
        )
        oks: list[str] = []
        fails: list[str] = []
        w.finished_ok.connect(oks.append)
        w.failed.connect(fails.append)

        w.run()

        assert fails == []
        assert fake.retried == ["http://pl/a.mp4"]  # entry B not retried
        payload = json.loads(oks[0].removeprefix("playlist_files:"))
        assert payload == {"files": [str(got_a)], "failed": 1, "total": 2}

    def test_cancelled_run_is_silent(self, monkeypatch, tmp_path):
        fake = _fake_ydl({"title": "L", "entries": []})
        monkeypatch.setattr("app.worker.YoutubeDL", fake)
        w = _download_worker(tmp_path, playlist=True)
        oks: list[str] = []
        fails: list[str] = []
        w.finished_ok.connect(oks.append)
        w.failed.connect(fails.append)

        w.cancel()
        w.run()

        assert oks == [] and fails == []

    def test_cancel_during_run_stops_before_retry(self, monkeypatch, tmp_path):
        """Cancel pressed while the playlist is downloading: no retry pass,
        no result signals — same contract as the single-video path."""
        missing = tmp_path / "two.mp4"
        w = _download_worker(tmp_path, playlist=True)
        oks: list[str] = []
        fails: list[str] = []
        w.finished_ok.connect(oks.append)
        w.failed.connect(fails.append)

        def main(_url, _opts):
            w.cancel()  # user presses Cancel while yt-dlp works
            return {
                "title": "L",
                "entries": [{"filepath": str(missing), "webpage_url": "https://ex/1"}],
            }

        monkeypatch.setattr(
            "app.worker.YoutubeDL",
            _fake_ydl(main, lambda _url, _opts: pytest.fail("retry after cancel")),
        )
        w.run()

        assert oks == [] and fails == []


class TestSingleVideoRun:
    """The non-playlist path must stay strict: failures still raise and
    surface as the exception message (no ignoreerrors, no retry)."""

    def test_success_emits_prepared_path(self, monkeypatch, tmp_path):
        p = tmp_path / "clip.mp4"
        p.write_bytes(b"x")
        monkeypatch.setattr("app.worker.YoutubeDL", _fake_ydl({"filepath": str(p)}))
        w = _download_worker(tmp_path, playlist=False)
        oks: list[str] = []
        fails: list[str] = []
        w.finished_ok.connect(oks.append)
        w.failed.connect(fails.append)

        w.run()

        assert oks == [str(p)]
        assert fails == []

    def test_failure_still_emits_exception(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.worker.YoutubeDL", _fake_ydl(RuntimeError("network down"))
        )
        w = _download_worker(tmp_path, playlist=False)
        oks: list[str] = []
        fails: list[str] = []
        w.finished_ok.connect(oks.append)
        w.failed.connect(fails.append)

        w.run()

        assert oks == []
        assert fails == ["network down"]
