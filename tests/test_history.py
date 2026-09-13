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
