# Download History — Spec

## Context

New 4th tab "History" in the tab bar, next to Downloader / Audio Converter / Video Converter. Records every completed or failed download with file info, timestamp, and action buttons. Persisted to a JSON file between app sessions.

## Layout

**Tab 4 — History**, accessible from any tab. Contains:

- **Header row**: "Download History" title, total count + total size badge, "Clear All" button on the right.
- **Search/filter row**: text input (search by filename/URL) and a dropdown filter (All / Audio / Video / Playlist).
- **Table columns**: File | Size | Date | Status | Action
  - **File**: filename truncated with ellipsis, prefixed with icon (🎵 audio / 🎬 video / 📋 playlist)
  - **Size**: human-readable filesize (KB/MB/GB)
  - **Date**: relative time ("just now", "5 min ago", "2h ago"), with absolute on hover via tooltip
  - **Status**: "Completed" (blue) or "Failed" (red)
  - **Action**: 📂 Open folder (Completed only) + ↻ Re-download (both)
- **Legend row** below the table explaining icon meanings.

Rows are sorted newest-first. Max height of the table area is scrollable (no fixed limit, grows with window).

## Persistence (JSON)

File location: `~/.config/chrisnov-media-toolkit/download-history.json`

Schema:

```json
{
  "version": 1,
  "items": [
    {
      "url": "https://www.youtube.com/watch?v=...",
      "filepath": "/home/user/Videos/video.mp4",
      "filename": "video.mp4",
      "filesize_bytes": 45000000,
      "type": "video",
      "container": "mp4",
      "audio_only": false,
      "timestamp": 1742751234,
      "status": "completed"
    },
    {
      "url": "https://www.youtube.com/watch?v=...",
      "filepath": "/home/user/Music/song.mp3",
      "filename": "song.mp3",
      "filesize_bytes": 3200000,
      "type": "audio",
      "container": "mp3",
      "audio_only": true,
      "timestamp": 1742751000,
      "status": "failed",
      "error": "HTTP Error 403: Forbidden"
    }
  ]
}
```

- `type`: `"audio"`, `"video"`, or `"playlist"`
- `audio_only`: `bool`
- `status`: `"completed"` or `"failed"`
- `timestamp`: Unix epoch seconds (UTC)
- `error`: only present when `status === "failed"`
- For playlists: `filepath` points to the output directory, `filename` stores the playlist title, `filesize_bytes` is the total across all entries.

Loading: read on app startup (`__init__`), parse JSON, validate `version` field. If file missing or corrupt, start with empty list.

Writing: append each new entry on every `_on_item_ok` or `_on_item_fail`. Also write on `_on_info_error`? No — Info is not a download, only actual download attempts.

Clear All: re-initialize to empty list + overwrite file.

## State

`MainWindow.__init__`:
```python
self._history: list[dict] = []
self._history_path: Path = Path.home() / ".config" / "chrisnov-media-toolkit" / "download-history.json"
```

Loaded before `_build_ui()`.

## Files touched

- `app/window.py` — tab 4 UI, history loading/saving, append on download result, Clear All + Re-download action.
- `app/constants.py` — if needed for HISTORY_DIR or similar path constants.
- No new files — JSON persistence logic lives in `MainWindow` as private methods.
- No new dependencies — JSON is stdlib.

## Implementation scope

**In scope (Phase 1):**
- Tab 4 UI: header, table with File/Size/Date/Status/Action columns, legend, scrollable list.
- JSON persistence: load on startup, append on each download result, Clear All.
- Open Folder action button.
- Re-download action button (add URL back to queue, does not auto-start).

**In scope but low-effort (bundled with Phase 1):**
- Search/filter — simple in-memory Python filter on the `_history` list, re-render on keystroke or filter dropdown change.

**Not in scope:**
- Re-download with full settings restore (audio_only, format, bitrate).
  Single URL re-queue is sufficient for now.
- Export / share history.
- Dark mode styling for the new tab.
