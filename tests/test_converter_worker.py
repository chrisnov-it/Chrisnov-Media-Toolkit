"""Tests for app.converter_worker — codec args, sample rate, ffmpeg discovery."""

from typing import ClassVar

import pytest

from app.converter_worker import (
    SUPPORTED_INPUT_EXTENSIONS,
    VIDEO_INPUT_EXTENSIONS,
    find_ffmpeg,
    find_ffprobe,
    probe_duration,
)


class TestFFmpegDiscovery:
    """find_ffmpeg() / find_ffprobe() return a path when the binary is on
    PATH, otherwise raise FileNotFoundError. Both outcomes are valid; a
    successful return must be a non-empty path (find_binary() never
    yields None), while the raise path is itself the contract."""

    def test_find_ffmpeg_handles_missing(self):
        # On a CI Ubuntu runner without ffmpeg, this raises FileNotFoundError;
        # with the binary available (developer machines) it returns a string.
        try:
            ff = find_ffmpeg()
        except FileNotFoundError:
            pass  # absent here — raising is the expected behavior
        else:
            assert isinstance(ff, str) and ff, f"garbage return: {ff!r}"

    def test_find_ffprobe_handles_missing(self):
        try:
            fp = find_ffprobe()
        except FileNotFoundError:
            pass  # absent here — raising is the expected behavior
        else:
            assert isinstance(fp, str) and fp, f"garbage return: {fp!r}"


class TestCodecArgs:
    """_codec_args() and _sample_rate_args() logic tests using the raw
    worker classes instantiated without QThread.__init__."""

    def test_audio_codec_args_no_hardcoded_ar_for_mp3(self):
        """_codec_args for mp3 must not emit -ar (fixed in 0.1.0-beta.2)."""
        from app.converter_worker import ConvertWorker
        w = ConvertWorker.__new__(ConvertWorker)
        w.fmt = "mp3"
        w.cbr = True
        w.bitrate = 192
        w.sample_rate = 44100
        args = w._codec_args()
        assert "-ar" not in args, f"_codec_args for mp3 CBR must not contain -ar: {args}"

        w.cbr = False
        w.bitrate = 256
        args = w._codec_args()
        assert "-ar" not in args, f"_codec_args for mp3 VBR must not contain -ar: {args}"

    def test_audio_codec_args_other_formats_unaffected(self):
        """_codec_args for m4a/opus still works (they delegate -ar to _sample_rate_args)."""
        from app.converter_worker import ConvertWorker
        for fmt in ("m4a", "opus"):
            w = ConvertWorker.__new__(ConvertWorker)
            w.fmt = fmt
            w.cbr = True
            w.bitrate = 128
            w.sample_rate = 48000
            args = w._codec_args()
            assert "-ar" not in args, f"_codec_args for {fmt} must not contain -ar: {args}"

    def test_sample_rate_args_emits_ar_when_set(self):
        from app.converter_worker import ConvertWorker
        w = ConvertWorker.__new__(ConvertWorker)
        w.fmt = "mp3"
        w.sample_rate = 44100
        sr_args = w._sample_rate_args()
        assert sr_args == ["-ar", "44100"]

    def test_sample_rate_args_returns_empty_when_none(self):
        from app.converter_worker import ConvertWorker
        w = ConvertWorker.__new__(ConvertWorker)
        w.fmt = "mp3"
        w.sample_rate = None
        sr_args = w._sample_rate_args()
        assert sr_args == []

    def test_no_duplicate_ar_when_explicit_rate_chosen(self):
        """When sample_rate is explicitly set, -ar must appear exactly once
        in the combined command line (from _sample_rate_args, not _codec_args)."""
        from app.converter_worker import ConvertWorker
        w = ConvertWorker.__new__(ConvertWorker)
        w.fmt = "mp3"
        w.cbr = True
        w.bitrate = 192
        w.sample_rate = 48000

        codec_args = w._codec_args()
        sr_args = w._sample_rate_args()
        full = codec_args + sr_args

        ar_count = full.count("-ar")
        assert ar_count == 1, f"-ar appears {ar_count} times in full args: {full}"


class TestBuildCmdAndPartialCleanup:
    """-nostdin on every ffmpeg invocation, plus partial-output cleanup."""

    def test_audio_build_cmd_has_nostdin_before_input(self):
        from app.converter_worker import ConvertWorker
        w = ConvertWorker.__new__(ConvertWorker)
        w.src = "in.mp3"
        w.fmt = "mp3"
        w.cbr = True
        w.bitrate = 192
        w.sample_rate = None
        cmd = w._build_cmd("/bin/ffmpeg", "out.mp3", [], None)
        assert "-nostdin" in cmd, f"audio cmd must disable stdin: {cmd}"
        assert cmd.index("-nostdin") < cmd.index("-i")

    def test_video_build_cmd_has_nostdin_before_input(self):
        from app.converter_worker import VideoConvertWorker
        w = VideoConvertWorker.__new__(VideoConvertWorker)
        w.src = "in.mp4"
        w.fmt = "mp4"
        w.quality = "balanced"
        w.copy_audio = True
        cmd = w._build_cmd("/bin/ffmpeg", "out.mp4")
        assert "-nostdin" in cmd, f"video cmd must disable stdin: {cmd}"
        assert cmd.index("-nostdin") < cmd.index("-i")

    def test_remove_partial_deletes_file(self, tmp_path):
        from app.converter_worker import _remove_partial
        partial = tmp_path / "partial.mp3"
        partial.write_text("half a file")
        _remove_partial(partial)
        assert not partial.exists()

    def test_remove_partial_tolerates_missing_file(self, tmp_path):
        from app.converter_worker import _remove_partial
        _remove_partial(tmp_path / "never-existed.mp3")  # must not raise


class TestProbeDuration:
    def test_probe_duration_returns_none_for_missing_file(self, tmp_path):
        # If ffprobe isn't available on this runner (e.g. CI Ubuntu image),
        # skip — otherwise we cannot even verify the missing-file branch
        # without an existing binary to invoke.
        try:
            ffprobe = find_ffprobe()
        except FileNotFoundError:
            pytest.skip("ffprobe not available on this system")

        dur = probe_duration(ffprobe, tmp_path / "nonexistent.mp3")
        assert dur is None

    def test_probe_duration_works_on_real_file(self, tmp_path):
        import subprocess
        try:
            ffmpeg = find_ffmpeg()
            ffprobe = find_ffprobe()
        except FileNotFoundError:
            # find_* raise rather than return a falsy value, so the missing
            # case must be caught here or the test errors instead of skipping.
            pytest.skip("ffmpeg/ffprobe not available on this system")

        wav = tmp_path / "tone.wav"
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             str(wav)],
            capture_output=True, check=True
        )

        dur = probe_duration(ffprobe, wav)
        assert dur is not None
        assert 1.9 <= dur <= 2.1, f"expected ~2.0s, got {dur}"


class TestCancelDuringProbe:
    """Cancelling while ffprobe runs must stop the worker before it spawns
    ffmpeg. probe_duration() now takes a cancel hook and exposes its child,
    which is what lets the GUI's Cancel return immediately instead of falling
    back to QThread.terminate()."""

    @staticmethod
    def _patch(monkeypatch, cw, worker, tmp_path):
        """Fake the binary lookups; simulate a cancel arriving mid-probe."""
        monkeypatch.setattr(cw, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
        monkeypatch.setattr(cw, "find_ffprobe", lambda: "/usr/bin/ffprobe")
        resolved = []

        def fake_probe(ffprobe, src, **kwargs):
            assert kwargs.get("cancelled") is not None, \
                "probe_duration() must receive a cancel hook"
            assert kwargs.get("set_process") is not None, \
                "probe_duration() must expose its child process to cancel()"
            worker.cancel()  # the user presses Cancel while ffprobe runs
            return None

        monkeypatch.setattr(cw, "probe_duration", fake_probe)
        monkeypatch.setattr(
            cw, "resolve_output_path",
            lambda *a, **k: resolved.append(a) or tmp_path / "out",
        )
        return resolved

    @staticmethod
    def _observe(worker):
        seen = {"status": [], "failed": [], "ok": []}
        worker.status.connect(seen["status"].append)
        worker.failed.connect(seen["failed"].append)
        worker.finished_ok.connect(seen["ok"].append)
        return seen

    def test_audio_worker_stops_after_cancelled_probe(self, monkeypatch, tmp_path):
        from app import converter_worker as cw

        src = tmp_path / "in.mp3"
        src.write_text("x", encoding="utf-8")
        worker = cw.ConvertWorker(src=src, outdir=tmp_path, fmt="mp3")
        resolved = self._patch(monkeypatch, cw, worker, tmp_path)
        seen = self._observe(worker)

        worker.run()

        assert seen["status"] == ["Cancelled."]
        assert seen["failed"] == []
        assert seen["ok"] == []
        assert resolved == [], "a cancelled worker must not resolve an output path"

    def test_video_worker_stops_after_cancelled_probe(self, monkeypatch, tmp_path):
        from app import converter_worker as cw

        src = tmp_path / "in.mp4"
        src.write_text("x", encoding="utf-8")
        worker = cw.VideoConvertWorker(src=src, outdir=tmp_path, fmt="mp4")
        resolved = self._patch(monkeypatch, cw, worker, tmp_path)
        seen = self._observe(worker)

        worker.run()

        assert seen["status"] == ["Cancelled."]
        assert seen["failed"] == []
        assert seen["ok"] == []
        assert resolved == [], "a cancelled worker must not resolve an output path"


class TestInputExtensions:
    _audio_ext: ClassVar[set[str]] = {"mp3", "m4a", "opus", "wav", "flac", "aac", "ogg"}
    _video_ext: ClassVar[set[str]] = {"mp4", "mkv", "webm", "mov", "avi", "m4v"}

    def test_audio_extensions_superset(self):
        assert SUPPORTED_INPUT_EXTENSIONS >= self._audio_ext

    def test_video_extensions_superset(self):
        assert VIDEO_INPUT_EXTENSIONS >= self._video_ext