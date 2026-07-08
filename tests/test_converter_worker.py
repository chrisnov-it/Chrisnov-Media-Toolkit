"""Tests for app.converter_worker — codec args, sample rate, ffmpeg discovery."""

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
    PATH, otherwise raise FileNotFoundError. Both outcomes are valid; we
    only assert that the function doesn't return garbage."""

    def test_find_ffmpeg_handles_missing(self):
        # On a CI Ubuntu runner without ffmpeg, this raises FileNotFoundError;
        # with the binary available (developer machines) it returns a string.
        try:
            ff = find_ffmpeg()
            assert ff is None or isinstance(ff, str)
        except FileNotFoundError:
            pass

    def test_find_ffprobe_handles_missing(self):
        try:
            fp = find_ffprobe()
            assert fp is None or isinstance(fp, str)
        except FileNotFoundError:
            pass


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
        ffmpeg = find_ffmpeg()
        ffprobe = find_ffprobe()

        if not ffmpeg or not ffprobe:
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


class TestInputExtensions:
    _audio_ext = {"mp3", "m4a", "opus", "wav", "flac", "aac", "ogg"}
    _video_ext = {"mp4", "mkv", "webm", "mov", "avi", "m4v"}

    def test_audio_extensions_superset(self):
        assert SUPPORTED_INPUT_EXTENSIONS >= self._audio_ext

    def test_video_extensions_superset(self):
        assert VIDEO_INPUT_EXTENSIONS >= self._video_ext