"""Tests for the Qt-free download-history model (app/history.py)."""

import json

import app.history as history_mod
from app.history import DownloadHistory


def make_history(tmp_path):
    return DownloadHistory(tmp_path / "download-history.json")


def test_load_missing_file_starts_empty(tmp_path):
    h = make_history(tmp_path)
    h.load()
    assert h.entries == []


def test_load_corrupt_file_starts_empty(tmp_path):
    p = tmp_path / "download-history.json"
    p.write_text("{not json", encoding="utf-8")
    h = DownloadHistory(p)
    h.load()
    assert h.entries == []


def test_load_wrong_version_rejected(tmp_path):
    p = tmp_path / "download-history.json"
    p.write_text(
        json.dumps({"version": 99, "items": [{"url": "x"}]}), encoding="utf-8",
    )
    h = DownloadHistory(p)
    h.load()
    assert h.entries == []


def test_load_valid(tmp_path):
    p = tmp_path / "download-history.json"
    items = [{"url": "u", "filename": "f", "status": "completed"}]
    p.write_text(json.dumps({"version": 1, "items": items}), encoding="utf-8")
    h = DownloadHistory(p)
    h.load()
    assert h.entries == items


def test_load_legacy_playlist_payload_sanitized(tmp_path):
    p = tmp_path / "download-history.json"
    items = [
        {"url": "u", "filename": 'playlist_files:["/a/b.mp3"]', "status": "completed"},
        {"url": "u2", "filename": "playlist:12:My List", "status": "completed"},
    ]
    p.write_text(json.dumps({"version": 1, "items": items}), encoding="utf-8")
    h = DownloadHistory(p)
    h.load()
    assert [e["filename"] for e in h.entries] == ["Playlist", "Playlist"]


def test_load_drops_non_dict_entries(tmp_path):
    """A truncated/hand-edited file must not crash load() (or the app start)."""
    p = tmp_path / "download-history.json"
    p.write_text(
        json.dumps({"version": 1, "items": ["oops", 42, None, {"url": "u"}]}),
        encoding="utf-8",
    )
    h = DownloadHistory(p)
    h.load()
    assert h.entries == [{"url": "u"}]


def test_load_coerces_bad_numeric_fields(tmp_path):
    """filesize_bytes/timestamp are summed and int()-cast by the History tab,
    so wrong types must be normalised at load time."""
    p = tmp_path / "download-history.json"
    p.write_text(
        json.dumps({
            "version": 1,
            "items": [{
                "url": "u", "filename": "f", "status": "completed",
                "filesize_bytes": "big", "timestamp": "soon",
            }],
        }),
        encoding="utf-8",
    )
    h = DownloadHistory(p)
    h.load()
    assert h.entries[0]["filesize_bytes"] == 0
    assert h.entries[0]["timestamp"] == 0
    # Values that are already correct stay untouched
    assert h.entries[0]["filename"] == "f"


def test_load_keeps_valid_numeric_fields(tmp_path):
    p = tmp_path / "download-history.json"
    p.write_text(
        json.dumps({
            "version": 1,
            "items": [{"url": "u", "filesize_bytes": 2048, "timestamp": 1234}],
        }),
        encoding="utf-8",
    )
    h = DownloadHistory(p)
    h.load()
    assert h.entries[0]["filesize_bytes"] == 2048
    assert h.entries[0]["timestamp"] == 1234


def test_append_newest_first_and_persists(tmp_path):
    h = make_history(tmp_path)
    h.append(url="https://a", filepath="/x/a.mp3", filename="a.mp3",
             filesize=10, type_="audio", container="mp3",
             audio_only=True, status="completed")
    h.append(url="https://b", filepath="", filename="b",
             filesize=0, type_="video", container="mp4",
             audio_only=False, status="failed", error="boom")
    assert h.entries[0]["url"] == "https://b"
    assert h.entries[1]["url"] == "https://a"

    data = json.loads(
        (tmp_path / "download-history.json").read_text(encoding="utf-8"),
    )
    assert data["version"] == 1
    assert [e["url"] for e in data["items"]] == ["https://b", "https://a"]
    assert data["items"][0]["error"] == "boom"
    assert "error" not in data["items"][1]


def test_append_creates_nested_parent_dirs(tmp_path):
    h = DownloadHistory(tmp_path / "deep" / "nested" / "download-history.json")
    h.append(url="u", filepath="f", filename="n", filesize=1,
             type_="audio", container="mp3", audio_only=True,
             status="completed")
    assert (tmp_path / "deep" / "nested" / "download-history.json").exists()


def test_append_caps_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "MAX_HISTORY_ENTRIES", 5)
    h = make_history(tmp_path)
    for i in range(8):
        h.append(url=f"https://x/{i}", filepath="f", filename=f"n{i}",
                 filesize=1, type_="audio", container="mp3",
                 audio_only=True, status="completed")
    assert len(h.entries) == 5
    # Oldest entries dropped — the newest remain, newest first
    assert h.entries[0]["filename"] == "n7"
    assert h.entries[-1]["filename"] == "n3"


def test_clear_persists_empty(tmp_path):
    h = make_history(tmp_path)
    h.append(url="u", filepath="f", filename="n", filesize=1,
             type_="audio", container="mp3", audio_only=True,
             status="completed")
    h.clear()
    assert h.entries == []
    data = json.loads(
        (tmp_path / "download-history.json").read_text(encoding="utf-8"),
    )
    assert data["items"] == []


def test_remove_at_drops_one_entry_and_persists(tmp_path):
    """The History tab could only Clear *All*; removing a single row needs a
    model-side counterpart that is safe to call from a Qt slot."""
    h = make_history(tmp_path)
    for name in ("a", "b", "c"):
        h.append(url=f"https://x/{name}", filepath="f", filename=name,
                 filesize=1, type_="audio", container="mp3",
                 audio_only=True, status="completed")
    assert h.remove_at(1) is True
    assert [e["filename"] for e in h.entries] == ["c", "a"]
    # …and the removal survives a reload (persisted, not just in memory).
    h2 = make_history(tmp_path)
    h2.load()
    assert [e["filename"] for e in h2.entries] == ["c", "a"]


def test_remove_at_is_bounds_checked(tmp_path):
    """A row index comes from a *filtered* view: a stale index must be a
    no-op, never an IndexError escaping into a Qt slot."""
    h = make_history(tmp_path)
    h.append(url="u", filepath="f", filename="n", filesize=1,
             type_="audio", container="mp3", audio_only=True,
             status="completed")
    for bad in (-1, 1, 999):
        assert h.remove_at(bad) is False, f"remove_at({bad}) must be a no-op"
    assert len(h.entries) == 1


def test_remove_at_on_empty_history_is_a_noop(tmp_path):
    h = make_history(tmp_path)
    h.load()
    assert h.remove_at(0) is False
    assert h.entries == []


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    """The payload goes to a sibling .tmp and is moved into place, so a crash
    mid-write can never truncate the file the next load() reads."""
    h = make_history(tmp_path)
    h.append(url="u", filepath="f", filename="n", filesize=1,
             type_="audio", container="mp3", audio_only=True,
             status="completed")
    assert (tmp_path / "download-history.json").exists()
    assert not (tmp_path / "download-history.json.tmp").exists()


def test_save_keeps_previous_copy_as_backup(tmp_path):
    h = make_history(tmp_path)
    h.append(url="first", filepath="f", filename="n", filesize=1,
             type_="audio", container="mp3", audio_only=True,
             status="completed")
    # Nothing to back up yet — the main file did not exist before this save.
    assert not (tmp_path / "download-history.json.bak").exists()

    h.append(url="second", filepath="f", filename="n", filesize=1,
             type_="audio", container="mp3", audio_only=True,
             status="completed")
    bak = tmp_path / "download-history.json.bak"
    assert bak.exists()
    assert [e["url"] for e in json.loads(bak.read_text(encoding="utf-8"))["items"]] \
        == ["first"]


def test_load_falls_back_to_backup_when_main_is_corrupt(tmp_path):
    """A truncated main file must not wipe the history (the old code reset
    to [] and the next append overwrote everything)."""
    p = tmp_path / "download-history.json"
    p.write_text('{"version": 1, "items": [{"url": "lost"', encoding="utf-8")
    (tmp_path / "download-history.json.bak").write_text(
        json.dumps({"version": 1, "items": [{"url": "kept", "filename": "f"}]}),
        encoding="utf-8",
    )
    h = DownloadHistory(p)
    h.load()
    assert [e["url"] for e in h.entries] == ["kept"]


def test_load_caps_entries(tmp_path, monkeypatch):
    """append() only caps what it adds; a hand-edited oversized file must be
    capped at load time too."""
    monkeypatch.setattr(history_mod, "MAX_HISTORY_ENTRIES", 3)
    p = tmp_path / "download-history.json"
    p.write_text(
        json.dumps({"version": 1, "items": [{"url": f"u{i}"} for i in range(10)]}),
        encoding="utf-8",
    )
    h = DownloadHistory(p)
    h.load()
    assert [e["url"] for e in h.entries] == ["u0", "u1", "u2"]


def test_save_reports_failure_instead_of_swallowing_it(tmp_path):
    """A failed write returns False (and logs) so callers can react."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    h = DownloadHistory(blocker / "download-history.json")
    assert h.save() is False
