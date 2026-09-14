"""Tests for app.ffmpeg_utils — binary discovery, probing, output-path
resolution, and progress-aware ffmpeg execution.

These cover the logic extracted out of converter_worker.py during the
workers refactor.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from app import ffmpeg_utils
from app.ffmpeg_utils import (
    find_binary,
    find_ffmpeg,
    find_ffprobe,
    probe_duration,
    probe_loudness,
    probe_version,
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
        monkeypatch.delattr("sys.frozen", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
        assert find_binary("ffmpeg") == "/usr/bin/ffmpeg"

    def test_frozen_app_finds_bin_next_to_exe(self, tmp_path, monkeypatch):
        exe_dir = tmp_path / "install"
        (exe_dir / "bin").mkdir(parents=True)
        beside_exe = exe_dir / "bin" / "ffmpeg.exe"
        beside_exe.write_text("binary")
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys.executable", str(exe_dir / "app.exe"))
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("shutil.which", lambda name: None)

        assert find_binary("ffmpeg") == str(beside_exe)

    def test_bundled_beats_bin_next_to_exe(self, tmp_path, monkeypatch):
        bundled_dir = tmp_path / "bundle"
        (bundled_dir / "bin").mkdir(parents=True)
        bundled = bundled_dir / "bin" / "ffmpeg.exe"
        bundled.write_text("bundled")
        exe_dir = tmp_path / "install"
        (exe_dir / "bin").mkdir(parents=True)
        beside_exe = exe_dir / "bin" / "ffmpeg.exe"
        beside_exe.write_text("beside")
        monkeypatch.setattr("sys._MEIPASS", str(bundled_dir), raising=False)
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys.executable", str(exe_dir / "app.exe"))
        monkeypatch.setattr("sys.platform", "win32")

        assert find_binary("ffmpeg") == str(bundled)

    def test_raises_when_nowhere_to_be_found(self, monkeypatch):
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        monkeypatch.delattr("sys.frozen", raising=False)
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


# -- probe_version ------------------------------------------------------------

class TestProbeVersion:
    def test_reads_banner_from_stdout(self, monkeypatch):
        # The banner goes to stdout — this is exactly the bug the old About
        # dialog had (it read stderr and always showed "n/a").
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(
                returncode=0,
                stdout=("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023\n"
                        "built with gcc 13\n"),
                stderr="",
            ),
        )
        assert probe_version("/usr/bin/ffmpeg") == "6.1.1-3ubuntu5"

    def test_returns_none_when_binary_missing(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError("no such binary")

        monkeypatch.setattr("subprocess.run", boom)
        assert probe_version("/nope/ffmpeg") is None

    def test_returns_none_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""),
        )
        assert probe_version("/usr/bin/ffmpeg") is None

    def test_returns_none_when_no_banner(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(
                returncode=0, stdout="unrelated text\n", stderr="",
            ),
        )
        assert probe_version("/usr/bin/ffmpeg") is None

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


# -- probe_loudness -----------------------------------------------------------


class _FakeScanPopen:
    """Stand-in for the loudness-scan Popen.

    poll() returns None until *exit_after_polls* polls have happened, then
    the class-level exit_code. The stderr handle passed via kwargs receives
    the canned loudnorm JSON, mirroring the real ffmpeg behavior.
    """

    exit_code = 0
    exit_after_polls = 0
    stderr_text = ""
    records: ClassVar[list] = []

    def __init__(self, cmd, **kwargs):
        type(self).records.append((cmd, kwargs))
        self.cmd = cmd
        self._polls = 0
        self.returncode = None
        self.terminated = False
        self.killed = False
        if self.stderr_text:
            kwargs["stderr"].write(self.stderr_text)
            kwargs["stderr"].flush()

    def poll(self):
        if self._polls >= type(self).exit_after_polls:
            self.returncode = type(self).exit_code
        self._polls += 1
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = type(self).exit_code
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class TestProbeLoudness:
    _JSON = (
        '{"input_i":"-13.4","input_tp":"-1.2","input_lra":"6.3",'
        '"input_thresh":"-23.1","target_offset":"0.4"}'
    )

    def _patch(self, monkeypatch, *, exit_code=0, exit_after_polls=0,
               stderr_text=""):
        _FakeScanPopen.exit_code = exit_code
        _FakeScanPopen.exit_after_polls = exit_after_polls
        _FakeScanPopen.stderr_text = stderr_text
        _FakeScanPopen.records.clear()
        monkeypatch.setattr("subprocess.Popen", _FakeScanPopen, raising=False)
        return _FakeScanPopen

    def test_parses_measured_json_and_skips_video(self, monkeypatch):
        self._patch(
            monkeypatch,
            stderr_text=f"noise above\n{self._JSON}\nnoise below\n",
        )
        processes = []

        result = probe_loudness(
            "/bin/ffmpeg", Path("song.mp3"), -14.0, -1.0, 11.0,
            set_process=processes.append,
        )

        assert result == {
            "input_i": "-13.4", "input_tp": "-1.2", "input_lra": "6.3",
            "input_thresh": "-23.1", "target_offset": "0.4",
        }
        assert processes[0] is not None and processes[1] is None
        cmd = _FakeScanPopen.records[0][0]
        # -vn keeps the scan from decoding the video stream
        assert "-vn" in cmd
        assert "print_format=json" in cmd[cmd.index("-af") + 1]

    def test_cancel_terminates_scan_and_raises(self, monkeypatch):
        # A huge poll budget means the scan never finishes on its own
        self._patch(monkeypatch, exit_after_polls=10**9)
        processes = []

        with pytest.raises(RuntimeError, match="Cancelled"):
            probe_loudness(
                "/bin/ffmpeg", Path("song.mp3"), -14.0, -1.0, 11.0,
                cancelled=lambda: True,
                set_process=processes.append,
            )

        assert processes[0].terminated is True
        assert processes[1] is None  # tracking cleared even on cancel

    def test_timeout_kills_scan_and_raises(self, monkeypatch):
        self._patch(monkeypatch, exit_after_polls=10**9)
        processes = []

        with pytest.raises(RuntimeError, match="timed out"):
            probe_loudness(
                "/bin/ffmpeg", Path("song.mp3"), -14.0, -1.0, 11.0,
                timeout=1,
                set_process=processes.append,
            )

        assert processes[0].killed is True
        assert processes[1] is None

    def test_nonzero_exit_raises_readable_error(self, monkeypatch):
        self._patch(monkeypatch, exit_code=1, stderr_text="boom\n")

        with pytest.raises(RuntimeError, match="loudnorm scan failed"):
            probe_loudness(
                "/bin/ffmpeg", Path("song.mp3"), -14.0, -1.0, 11.0,
            )

    def test_raises_when_no_json_in_output(self, monkeypatch):
        self._patch(monkeypatch, stderr_text="nothing here\n")

        with pytest.raises(RuntimeError, match="no JSON"):
            probe_loudness(
                "/bin/ffmpeg", Path("song.mp3"), -14.0, -1.0, 11.0,
            )


# -- run_ffmpeg_with_progress ------------------------------------------------

class _FakePopen:
    """Stand-in for subprocess.Popen that yields canned -progress output."""

    exit_code = 0
    lines: ClassVar[list[str]] = []
    records: ClassVar[list] = []

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
        self._patch_popen(monkeypatch, ["out_time_ms=50000000\n"])
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

