"""Tests for app.utils - bounded folder scanning and open_in_explorer."""

from pathlib import Path
from types import SimpleNamespace

from app.utils import open_in_explorer, scan_media_files


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
