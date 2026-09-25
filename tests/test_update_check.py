"""Tests for app.update_check — version comparison + the PyPI check worker.

Regression: the About dialog compared versions with ``!=`` (an installed build
newer than PyPI's latest was told to "update" downwards) and called urlopen()
from the GUI thread, freezing the dialog for the whole request.
"""

import json

from app import update_check
from app.update_check import UpdateCheckWorker, is_newer_version, version_key


class _FakeResponse:
    """Minimal stand-in for the urlopen() context manager."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


def _patch_urlopen(monkeypatch, version: str, calls: list | None = None):
    def fake_urlopen(url, timeout=None):
        if calls is not None:
            calls.append((url, timeout))
        return _FakeResponse(
            json.dumps({"info": {"version": version}}).encode("utf-8")
        )

    monkeypatch.setattr(update_check.urllib.request, "urlopen", fake_urlopen)


class TestVersionKey:
    def test_parses_numeric_segments(self):
        assert version_key("2026.8.19") == (2026, 8, 19)

    def test_ignores_prerelease_suffix(self):
        assert version_key("2026.8.19.dev0") == (2026, 8, 19)

    def test_strips_leading_v(self):
        assert version_key("v1.2") == (1, 2)

    def test_unparsable_returns_empty(self):
        assert version_key("n/a") == ()
        assert version_key("") == ()


class TestIsNewerVersion:
    def test_detects_newer(self):
        assert is_newer_version("2026.8.19", "2026.8.9") is True
        assert is_newer_version("2026.9.1", "2026.8.19") is True

    def test_equal_is_not_newer(self):
        assert is_newer_version("2026.8.19", "2026.8.19") is False

    def test_older_is_not_newer(self):
        # This is what the old `!=` comparison got wrong.
        assert is_newer_version("2026.8.19", "2026.9.1") is False

    def test_unparsable_never_newer(self):
        assert is_newer_version("n/a", "2026.8.19") is False
        assert is_newer_version("2026.8.19", "n/a") is False


class TestUpdateCheckWorker:
    def _run(self, monkeypatch, latest: str, current: str = "2026.8.19",
             calls: list | None = None):
        _patch_urlopen(monkeypatch, latest, calls)
        w = UpdateCheckWorker(current)
        emitted: list[str] = []
        w.update_available.connect(emitted.append)
        w.run()  # synchronous — no event loop needed
        return w, emitted

    def test_emits_when_newer(self, monkeypatch):
        _w, emitted = self._run(monkeypatch, "2026.9.1")
        assert emitted == ["2026.9.1"]

    def test_silent_when_installed_is_newer(self, monkeypatch):
        _w, emitted = self._run(monkeypatch, "2026.8.9")
        assert emitted == []

    def test_silent_when_equal(self, monkeypatch):
        _w, emitted = self._run(monkeypatch, "2026.8.19")
        assert emitted == []

    def test_silent_on_network_error(self, monkeypatch):
        def boom(url, timeout=None):
            raise OSError("offline")

        monkeypatch.setattr(update_check.urllib.request, "urlopen", boom)
        w = UpdateCheckWorker("2026.8.19")
        emitted: list[str] = []
        w.update_available.connect(emitted.append)

        w.run()  # must not raise

        assert emitted == []

    def test_silent_on_unexpected_payload(self, monkeypatch):
        monkeypatch.setattr(
            update_check.urllib.request, "urlopen",
            lambda url, timeout=None: _FakeResponse(b"{}"),
        )
        w = UpdateCheckWorker("2026.8.19")
        emitted: list[str] = []
        w.update_available.connect(emitted.append)

        w.run()

        assert emitted == []

    def test_cancelled_run_emits_nothing(self, monkeypatch):
        _patch_urlopen(monkeypatch, "2026.9.1")
        w = UpdateCheckWorker("2026.8.19")
        emitted: list[str] = []
        w.update_available.connect(emitted.append)

        w.cancel()
        w.run()

        assert emitted == []

    def test_request_is_bounded_and_uses_pypi_json(self, monkeypatch):
        calls: list = []
        self._run(monkeypatch, "2026.9.1", calls=calls)

        url, timeout = calls[0]
        assert url == update_check.PYPI_YTDLP_URL
        assert url.startswith("https://")
        assert timeout == update_check._TIMEOUT_SECONDS
