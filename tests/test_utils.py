"""Tests for app.utils - bounded folder scanning and open_in_explorer."""

from pathlib import Path
from types import SimpleNamespace

from app.utils import (
    BATCH_BUSY_HINT,
    clip_text,
    open_in_explorer,
    open_result,
    scan_media_files,
    set_controls_busy,
    strip_ansi,
)


class TestOpenInExplorer:
    """open_in_explorer() must hand a real directory to QDesktopServices and
    do nothing at all for anything else (a stale folder, an empty field)."""

    @staticmethod
    def _capture(monkeypatch) -> list:
        calls: list = []
        fake = SimpleNamespace(openUrl=lambda url: calls.append(url))
        monkeypatch.setattr("app.utils.QDesktopServices", fake)
        return calls

    def test_opens_directory_as_local_file_url(self, tmp_path, monkeypatch):
        calls = self._capture(monkeypatch)
        open_in_explorer(str(tmp_path))
        assert len(calls) == 1
        assert Path(calls[0].toLocalFile()) == tmp_path

    def test_ignores_missing_path_and_non_directory(self, tmp_path, monkeypatch):
        calls = self._capture(monkeypatch)
        file_path = tmp_path / "a-file"
        file_path.write_text("x")
        open_in_explorer(str(tmp_path / "does-not-exist"))  # vanished folder
        open_in_explorer(str(file_path))                    # a file, not a dir
        open_in_explorer("")                                # cleared field
        assert calls == []


class TestScanMediaFiles:
    """scan_media_files() replaces Path.rglob() on the GUI thread: it must
    recurse, filter extensions case-insensitively, skip hidden entries, and
    stay bounded so a huge tree cannot freeze the window."""

    def _tree(self, root: Path) -> Path:
        (root / "a.mp3").write_text("x")
        (root / "b.MP3").write_text("x")          # case-insensitive match
        (root / "c.txt").write_text("x")          # wrong extension
        (root / "noext").write_text("x")          # no extension at all
        (root / ".hidden.mp3").write_text("x")    # hidden file → skipped
        (root / "sub").mkdir()
        (root / "sub" / "d.m4a").write_text("x")
        (root / "sub" / "deeper").mkdir()
        (root / "sub" / "deeper" / "e.mp3").write_text("x")
        (root / ".git").mkdir()
        (root / ".git" / "f.mp3").write_text("x")  # hidden dir → pruned
        return root

    def test_collects_media_files_recursively(self, tmp_path: Path):
        files, truncated = scan_media_files(self._tree(tmp_path), {"mp3", "m4a"})
        assert sorted(p.name for p in files) == ["a.mp3", "b.MP3", "d.m4a", "e.mp3"]
        assert truncated is False

    def test_skips_hidden_entries(self, tmp_path: Path):
        files, _ = scan_media_files(self._tree(tmp_path), {"mp3"})
        assert not any(".git" in p.parts for p in files)
        assert not any(p.name.startswith(".") for p in files)

    def test_stops_at_max_files(self, tmp_path: Path):
        for i in range(5):
            (tmp_path / f"x{i}.mp3").write_text("x")
        files, truncated = scan_media_files(tmp_path, {"mp3"}, max_files=2)
        assert len(files) == 2
        assert truncated is True

    def test_stops_at_max_entries(self, tmp_path: Path):
        for i in range(5):
            (tmp_path / f"x{i}.mp3").write_text("x")
        files, truncated = scan_media_files(tmp_path, {"mp3"}, max_entries=3)
        assert truncated is True
        assert len(files) < 5

    def test_empty_extension_never_matches_files(self, tmp_path: Path):
        (tmp_path / "noext").write_text("x")
        files, _ = scan_media_files(tmp_path, {""})
        assert files == []

    def test_unreadable_folder_returns_empty(self, tmp_path: Path):
        # No exception: a vanished/unplugged/unreadable folder must not
        # crash the GUI thread that called this.
        assert scan_media_files(tmp_path / "ghost", {"mp3"}) == ([], False)


class TestClipText:
    """Queue labels are previews — clipping must announce the cut (P1).

    The old raw slices (``identifier[:20]``, ``url[:40]``) hid that anything
    was missing: no ellipsis, and the full value only on hover (which the
    rows never had until now).
    """

    def test_short_text_passes_through_unchanged(self):
        assert clip_text("[abc123]", 20) == "[abc123]"

    def test_exact_limit_is_not_clipped(self):
        assert clip_text("a" * 20, 20) == "a" * 20

    def test_long_text_is_clipped_to_the_limit_including_ellipsis(self):
        out = clip_text("a" * 40, 20)
        assert out == "a" * 19 + "…"
        assert len(out) == 20

    def test_unicode_ellipsis_marks_the_cut(self):
        out = clip_text("https://example.com/very/long/url", 12)
        assert out.endswith("…") and len(out) == 12
        assert out.startswith("https://exa")

    def test_tiny_limits_degrade_to_the_ellipsis_only(self):
        assert clip_text("abcdef", 1) == "…"


class _StubWidget:
    """Duck-typed QWidget for set_controls_busy(): only the four methods the
    helper touches, so the freeze contract is unit-testable without a
    QApplication (pytest must not create one — see tests/test_main_excepthook)."""

    def __init__(self, tooltip: str = "", enabled: bool = True) -> None:
        self._tip = tooltip
        self._enabled = enabled

    def toolTip(self) -> str:
        return self._tip

    def setToolTip(self, text: str) -> None:
        self._tip = text

    def isEnabled(self) -> bool:
        return self._enabled

    def setEnabled(self, on: bool) -> None:
        self._enabled = on


class TestSetControlsBusy:
    """A batch freezes the Downloader's *settings* too (P2), and thawing must
    restore whatever state each control was in — not blindly re-enable it."""

    def test_freeze_disables_and_self_explains(self):
        w = _StubWidget(tooltip="Pick a resolution")
        set_controls_busy([w], True)
        assert w.isEnabled() is False
        assert w.toolTip() == BATCH_BUSY_HINT

    def test_thaw_restores_tooltip_and_enabled_state(self):
        w = _StubWidget(tooltip="Pick a resolution")
        set_controls_busy([w], True)
        set_controls_busy([w], False)
        assert w.isEnabled() is True
        assert w.toolTip() == "Pick a resolution"

    def test_thaw_keeps_a_control_that_was_already_off(self):
        # bitrate in video mode / the cleanup-tag field with Clean title off
        w = _StubWidget(tooltip="Bitrate", enabled=False)
        set_controls_busy([w], True)
        assert w.isEnabled() is False
        set_controls_busy([w], False)
        assert w.isEnabled() is False, "thaw must not switch a control on"
        assert w.toolTip() == "Bitrate"

    def test_double_freeze_keeps_the_original_state(self):
        # The second freeze must not capture the frozen state as "original".
        w = _StubWidget(tooltip="Browse")
        set_controls_busy([w], True)
        w.setEnabled(True)  # something re-enabled it behind our back
        set_controls_busy([w], True)
        set_controls_busy([w], False)
        set_controls_busy([w], False)
        assert w.isEnabled() is True
        assert w.toolTip() == "Browse"

    def test_thaw_without_a_prior_freeze_is_a_noop(self):
        w = _StubWidget(tooltip="Skip duplicates")
        set_controls_busy([w], False)
        assert w.isEnabled() is True
        assert w.toolTip() == "Skip duplicates"


class TestOpenResult:
    """'Open last result' (P2) — files open with the default app, folders in
    the file manager, and a vanished/empty path opens nothing at all."""

    @staticmethod
    def _capture(monkeypatch) -> list:
        calls: list = []
        fake = SimpleNamespace(openUrl=lambda url: calls.append(url) or True)
        monkeypatch.setattr("app.utils.QDesktopServices", fake)
        return calls

    def test_opens_a_finished_file_and_its_folder(self, tmp_path, monkeypatch):
        calls = self._capture(monkeypatch)
        out = tmp_path / "converted.mp3"
        out.write_bytes(b"x")
        assert open_result(out) is True
        assert open_result(tmp_path) is True
        assert [Path(c.toLocalFile()) for c in calls] == [out, tmp_path]

    def test_ignores_missing_and_empty_paths(self, tmp_path, monkeypatch):
        calls = self._capture(monkeypatch)
        assert open_result(tmp_path / "vanished.mp3") is False
        assert open_result("") is False
        assert calls == []

class TestStripAnsi:
    """Error strings from yt-dlp keep their tty color codes unless stripped;
    the History row/tooltip displays what the model stored, and legacy rows
    hold raw escapes already — both must render cleanly."""

    def test_strips_color_and_weight_codes(self):
        raw = "\x1b[1m\x1b[31mERROR:\x1b[0m\x1b[10m unable to download video data"
        assert strip_ansi(raw) == "ERROR: unable to download video data"

    def test_strips_cursor_and_misc_sequences(self):
        raw = "\x1b[2K\x1b[31m[download] Destination: x.mp3\x1b[0m"
        assert strip_ansi(raw) == "[download] Destination: x.mp3"

    def test_plain_text_with_brackets_is_untouched(self):
        # A failed thumbnail slot shows like "[ 20%]" in the wild — without
        # the ESC prefix it must NOT be eaten by a naive "[...]" pattern.
        assert strip_ansi("format [1080p] failed at [42]") == "format [1080p] failed at [42]"

    def test_empty_and_none_safe(self):
        assert strip_ansi("") == ""
        assert strip_ansi(None) is None
