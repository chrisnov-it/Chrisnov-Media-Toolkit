"""Tests for app.worker — FileSizeWorker cancellation + yt-dlp update hint.

Regression: MainWindow._start_download() calls FileSizeWorker.cancel() when
the user presses Start while an Info fetch is still in flight. Before the fix,
FileSizeWorker had no cancel() and the call raised AttributeError, aborting
the download start.
"""

import sys

from app.worker import FileSizeWorker, ytdlp_update_hint


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
