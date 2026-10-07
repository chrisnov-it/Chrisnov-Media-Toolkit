"""Playlist result payloads — DownloadTab._collect_playlist_files.

A resilient playlist run sends ``playlist_files:{"files": [...],
"failed": n, "total": n}`` so partial success stays visible in the history
label; a plain JSON list (what older workers produced) must keep working.
The helpers are stateless (self is unused), so they are exercised without
instantiating the widget.
"""

import json

from app.download_tab import BatchState, DownloadTab


def _batch(tmp_path):
    return BatchState(
        urls=["https://example.com/playlist"],
        outdir=str(tmp_path),
        audio_only=False,
        height=None,
        container="mp4",
        bitrate=128,
        clean_tags=[],
        embed_metadata=False,
        embed_thumbnail=False,
        archive_path=None,
    )


class TestCollectPlaylistFiles:
    def test_partial_payload_reports_failed_count(self, tmp_path):
        payload = "playlist_files:" + json.dumps({
            "files": [str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4")],
            "failed": 3,
            "total": 5,
        })
        files, label, renamed, failed = DownloadTab._collect_playlist_files(
            None, payload, _batch(tmp_path)
        )

        assert [f.name for f in files] == ["a.mp4", "b.mp4"]
        assert label == "Playlist — 2 file(s), 3 failed"
        assert failed == 3
        assert renamed == []

    def test_full_success_label_has_no_failure_note(self, tmp_path):
        payload = "playlist_files:" + json.dumps({
            "files": [str(tmp_path / "a.mp4")],
            "failed": 0,
            "total": 1,
        })
        files, label, _renamed, failed = DownloadTab._collect_playlist_files(
            None, payload, _batch(tmp_path)
        )

        assert len(files) == 1
        assert label == "Playlist — 1 file(s)"
        assert failed == 0

    def test_legacy_list_payload_still_works(self, tmp_path):
        payload = "playlist_files:" + json.dumps([str(tmp_path / "a.mp4")])
        files, label, _renamed, failed = DownloadTab._collect_playlist_files(
            None, payload, _batch(tmp_path)
        )

        assert [f.name for f in files] == ["a.mp4"]
        assert label == "Playlist — 1 file(s)"
        assert failed == 0

    def test_invalid_payload_is_empty_not_an_error(self, tmp_path):
        files, label, renamed, failed = DownloadTab._collect_playlist_files(
            None, "playlist_files:not-json", _batch(tmp_path)
        )

        assert files == []
        assert label == "Playlist — 0 file(s)"
        assert renamed == []
        assert failed == 0

    def test_garbage_failed_field_degrades_to_zero(self, tmp_path):
        payload = "playlist_files:" + json.dumps({
            "files": [str(tmp_path / "a.mp4")],
            "failed": "many",
        })
        _files, _label, _renamed, failed = DownloadTab._collect_playlist_files(
            None, payload, _batch(tmp_path)
        )

        assert failed == 0


class TestDiscoverPlaylistFiles:
    def test_discovery_never_claims_failures(self, tmp_path):
        files, label, renamed, failed = DownloadTab._discover_playlist_files(
            None, "playlist:7:My List", _batch(tmp_path)
        )

        assert files == []
        assert label == "Playlist: My List — 7 item(s)"
        assert renamed == []
        assert failed == 0
