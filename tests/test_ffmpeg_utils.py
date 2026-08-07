"""Tests for app.ffmpeg_utils — binary discovery, probing, output-path
resolution, and progress-aware ffmpeg execution.

These cover the logic extracted out of converter_worker.py during the
workers refactor.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import ffmpeg_utils
from app.ffmpeg_utils import (
    find_binary,
    find_ffmpeg,
    find_ffprobe,
    probe_duration,
    probe_loudness,
    resolve_output_path,
    run_ffmpeg_with_progress,
)


# -- find_binary / find_ffmpeg / find_ffprobe --------------------------------

class TestFindBinary:
    def test_uses_pyinstaller_bundled_binary(self, tmp_path, monkeypatch):
        bundled_dir = tmp_path / "bundle"
        (bundled_dir / "bin").mkdir(parents=True)
        bundled = bundled_dir / "bin" / "ffmpeg"
        bundled.write_text("binary")
        monkeypatch.setattr("sys._MEIPASS", str(bundled_dir), raising=False)

        assert find_binary("ffmpeg") == str(bundled)

    def test_windows_uses_exe_extension_in_bundle(self, tmp_path, monkeypatch):
        bundled_dir = tmp_path / "bundle"
        (bundled_dir / "bin").mkdir(parents=True)
        bundled = bundled_dir / "bin" / "ffprobe.exe"
        bundled.write_text("binary")
        monkeypatch.setattr("sys._MEIPASS", str(bundled_dir), raising=False)
        monkeypatch.setattr("sys.platform", "win32")

        assert find_binary("ffprobe") == str(bundled)

    def test_falls_back_to_system_path(self, monkeypatch):
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
        assert find_binary("ffmpeg") == "/usr/bin/ffmpeg"

    def test_raises_when_nowhere_to_be_found(self, monkeypatch):
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: None)
        with pytest.raises(FileNotFoundError):
            find_binary("ffmpeg")

    def test_find_ffmpeg_delegates_to_find_binary(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_utils, "find_binary",
                            lambda name: f"/opt/bin/{name}")
        assert find_ffmpeg() == "/opt/bin/ffmpeg"

    def test_find_ffprobe_delegates_to_find_binary(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_utils, "find_binary",
                            lambda name: f"/opt/bin/{name}")
        assert find_ffprobe() == "/opt/bin/ffprobe"


# -- probe_duration ----------------------------------------------------------

class TestProbeDuration:
    def test_returns_duration_on_success(self, monkeypatch):
        calls = {}

        def fake_run(cmd, **kw):
            calls["cmd"] = cmd
            return SimpleNamespace(returncode=0, stdout="120.5\n")

        monkeypatch.setattr("subprocess.run", fake_run)
        assert probe_duration("/bin/ffprobe", Path("/tmp/x.mp3")) == 120.5
        assert calls["cmd"][0] == "/bin/ffprobe"

    def test_returns_none_on_nonzero_rc(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout=""),
        )
        assert probe_duration("/bin/ffprobe", Path("/tmp/x.mp3")) is None

    def test_returns_none_on_invalid_float(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="abc\n"),
        )
        assert probe_duration("/bin/ffprobe", Path("/tmp/x.mp3")) is None

    def test_returns_none_for_zero_duration(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="0\n"),
        )
        assert probe_duration("/bin/ffprobe", Path("/tmp/x.mp3")) is None

# -- probe_loudness ----------------------------------------------------------

class TestProbeLoudness:
    _JSON = (
        '{"input_i":"-13.4","input_tp":"-1.2","input_lra":"6.3",'
        '"input_thresh":"-23.1","target_offset":"0.4"}'
    )

    def test_parses_json_from_stderr(self, monkeypatch):
        def fake_run(cmd, **kw):
            return SimpleNamespace(stderr=f"noise above\n{self._JSON}\nnoise below")

        monkeypatch.setattr("subprocess.run", fake_run)
        out = probe_loudness("/bin/ffmpeg", Path("/tmp/x.wav"), -14.0, -1.0, 11.0)
        assert out["input_i"] == "-13.4"
        assert out["target_offset"] == "0.4"

    def test_raises_when_no_json_in_output(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(stderr="nothing here"),
        )
        with pytest.raises(RuntimeError):
            probe_loudness("/bin/ffmpeg", Path("/tmp/x.wav"), -14.0, -1.0, 11.0)


# -- resolve_output_path ------------------------------------------------------

class TestResolveOutputPath:
    def test_no_collision(self, tmp_path):
        src = tmp_path / "Song.mp3"
        assert resolve_output_path(src, tmp_path, "wav", None) == tmp_path / "Song.wav"

    def test_collision_appends_counter(self, tmp_path):
        (tmp_path / "Song.wav").write_text("x")
        out = resolve_output_path(tmp_path / "Song.mp3", tmp_path, "wav", None)
        assert out == tmp_path / "Song (1).wav"

    def test_multiple_collisions_increment(self, tmp_path):
        for name in ("Song.wav", "Song (1).wav", "Song (2).wav"):
            (tmp_path / name).write_text("x")
        out = resolve_output_path(tmp_path / "Song.mp3", tmp_path, "wav", None)
        assert out == tmp_path / "Song (3).wav"

    def test_cleans_tags_when_requested(self, tmp_path):
        src = tmp_path / "Song (Official Music Video).mp3"
        out = resolve_output_path(src, tmp_path, "mp3", ["Official Music Video"])
        assert out == tmp_path / "Song.mp3"

    def test_none_tags_leave_stem_untouched(self, tmp_path):
        src = tmp_path / "Song (Official Music Video).mp3"
        out = resolve_output_path(src, tmp_path, "mp3", None)
        assert out == tmp_path / "Song (Official Music Video).mp3"


# -- run_ffmpeg_with_progress ------------------------------------------------

class _FakePopen:
    """Stand-in for subprocess.Popen that yields canned -progress output."""

    exit_code = 0
    lines: list[str] = []
    records: list = []

    def __init__(self, cmd, **kwargs):
        type(self).records.append((cmd, kwargs))
        self.cmd = cmd
        self.terminated = False
        self.killed = False

    @property
    def stdout(self):
        return iter(type(self).lines)

    def wait(self, timeout=None):
        return type(self).exit_code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class TestRunFfmpegWithProgress:
    def _patch_popen(self, monkeypatch, lines, exit_code=0):
        _FakePopen.exit_code = exit_code
        _FakePopen.lines = list(lines)
        _FakePopen.records.clear()
        monkeypatch.setattr("subprocess.Popen", _FakePopen, raising=False)
        return _FakePopen

    @staticmethod
    def _cmd():
        return ["/bin/ffmpeg", "-i", "in.mp3", "out.mp3"]

    def test_success_emits_progress_bounded_and_tracks_process(self, monkeypatch):
        fake = self._patch_popen(monkeypatch, ["out_time_ms=50000000\n"])
        progress, processes = [], []

        run_ffmpeg_with_progress(
            self._cmd(),
            duration=100.0,
            cancelled=lambda: False,
            on_progress=progress.append,
            set_process=processes.append,
        )

        assert progress == [50]  # 50s elapsed / 100s → 50%
        assert processes[0] is not None and processes[1] is None
        # -progress flags inserted just before the output path op
        inserted = fake.records[0][0]
        assert inserted[-1] == "out.mp3"
        assert "-progress" in inserted and "pipe:1" in inserted

    def test_maps_progress_onto_floor_ceiling_range(self, monkeypatch):
        self._patch_popen(monkeypatch, ["out_time_ms=50000000\n"])
        progress = []

        run_ffmpeg_with_progress(
            self._cmd(),
            duration=100.0,
            cancelled=lambda: False,
            on_progress=progress.append,
            progress_floor=10,
            progress_ceiling=90,
        )

        # 50/100 → 40 of the 80-wide band, then offset by floor → 50
        assert progress == [50]

    def test_throttles_rapid_progress_updates(self, monkeypatch):
        self._patch_popen(monkeypatch, [
            "out_time_ms=50000000\n",
            "out_time_ms=60000000\n",
        ])
        progress = []

        run_ffmpeg_with_progress(
            self._cmd(),
            duration=100.0,
            cancelled=lambda: False,
            on_progress=progress.append,
        )

        # Both lines arrive within the 0.2s throttle window → only first emits
        assert progress == [50]

    def test_no_progress_when_duration_unknown(self, monkeypatch):
        self._patch_popen(monkeypatch, ["out_time_ms=50000000\n"])
        progress = []

        run_ffmpeg_with_progress(
            self._cmd(),
            duration=None,
            cancelled=lambda: False,
            on_progress=progress.append,
        )

        assert progress == []

    def test_cancel_terminates_process_and_raises(self, monkeypatch):
        fake = self._patch_popen(monkeypatch, ["out_time_ms=50000000\n"])
        progress, processes = [], []

        with pytest.raises(RuntimeError, match="Cancelled"):
            run_ffmpeg_with_progress(
                self._cmd(),
                duration=100.0,
                cancelled=lambda: True,
                on_progress=progress.append,
                set_process=processes.append,
            )

        assert processes[0].terminated is True
        assert processes[1] is None
        assert progress == []

    def test_nonzero_exit_raises_error(self, monkeypatch):
        self._patch_popen(monkeypatch, ["out_time_ms=50000000\n"], exit_code=1)
        progress = []

        with pytest.raises(RuntimeError, match="ffmpeg error"):
            run_ffmpeg_with_progress(
                self._cmd(),
                duration=100.0,
                cancelled=lambda: False,
                on_progress=progress.append,
            )

