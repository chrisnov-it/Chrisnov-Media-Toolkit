#!/usr/bin/env python
"""Offscreen GUI smoke test for Chrisnov Media Toolkit.

Formalizes the ad-hoc offscreen checks run during the audit fixes (#4-#9)
and the window.py refactor (#10). Exercises tab construction, URL queue
handling, history rendering/search/clear, converter file-list handling,
worker tracking, and idle cancel/start guards - without any network access.

Designed to work both BEFORE and AFTER the window.py refactor through
getattr proxies and fallbacks:

  - tabs:        w.download_tab / w.audio_tab / w.video_tab / w.history_tab
                 (post-refactor) falling back to the MainWindow itself
  - add url:     tab.add_url (public) or ._add_url (pre-refactor private)
  - history:     w.history.append (model) or w._history_append (method)
  - rendering:   tab.refresh() or w._history_render()
  - tracking:    tab._tracker (WorkerTracker) or w._track_worker/_tracked_workers

Exit code 0 with "SMOKE OK" on success; prints "FAIL: <what>" and exits 1
on the first failed check.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import ClassVar

# --- Environment isolation - MUST happen before any Qt import ----------
# Redirect HOME/XDG_CONFIG_HOME so QSettings, download history, and the
# skip-duplicates archive never touch the developer's real ~/.config.
_TMP_HOME = tempfile.mkdtemp(prefix="cmt-smoke-")
os.environ["HOME"] = _TMP_HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP_HOME, ".config")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication


def check(cond: bool, what: str) -> None:
    if not cond:
        print(f"FAIL: {what}")
        sys.exit(1)


def pump(rounds: int = 3) -> None:
    """Process queued events, including deferred deletes.

    finished -> deleteLater is a queued connection: the delete event only
    runs after one event-loop round, and the actual deletion happens in the
    DeferredDelete pass after that. Two-plus rounds keeps that observable.
    """
    for _ in range(rounds):
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class _StubMessageBox:
    """Records modal calls instead of blocking an offscreen dialog."""

    calls: ClassVar[list[tuple[str, str, str]]] = []
    # Real enum values so code doing `QMessageBox.Yes | QMessageBox.No`,
    # `QMessageBox.StandardButton.Yes`, and flag comparisons keeps working
    # against the stub.
    from PySide6.QtWidgets import QMessageBox as _RealMB
    StandardButton = _RealMB.StandardButton
    Yes = _RealMB.StandardButton.Yes
    No = _RealMB.StandardButton.No
    del _RealMB

    @classmethod
    def warning(cls, parent, title, text, *args, **kwargs):
        cls.calls.append(("warning", title, text))

    @classmethod
    def question(cls, parent, title, text, *args, **kwargs):
        cls.calls.append(("question", title, text))
        return cls.Yes

    @classmethod
    def information(cls, parent, title, text, *args, **kwargs):
        cls.calls.append(("information", title, text))

    @classmethod
    def find_warnings(cls, title: str) -> list[str]:
        return [t for (kind, t, _) in cls.calls if kind == "warning" and t == title]


def patch_message_boxes() -> None:
    """Replace QMessageBox in every app module that uses it (pre and post)."""
    import importlib

    for mod_name in (
        "app.window",
        "app.download_tab",
        "app.convert_tab",
        "app.video_convert_tab",
        "app.history_tab",
    ):
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        if hasattr(mod, "QMessageBox"):
            mod.QMessageBox = _StubMessageBox


def add_url(tab, url: str) -> bool:
    fn = getattr(tab, "add_url", None) or tab._add_url
    return fn(url)


def history_append(win, **kw) -> None:
    model = getattr(win, "history", None)
    if model is not None:
        model.append(**kw)
    else:
        win._history_append(**kw)


def history_render(hist, win) -> None:
    refresh = getattr(hist, "refresh", None)
    if refresh is not None:
        refresh()
    else:
        win._history_render()


def track_api(obj):
    """Return (track, tracked_count) for a tab or the pre-refactor window."""
    tracker = getattr(obj, "_tracker", None)
    if tracker is not None:
        return tracker.track, lambda: len(tracker._tracked)
    return obj._track_worker, lambda: len(obj._tracked_workers)


def find_warning(title: str) -> bool:
    return bool(_StubMessageBox.find_warnings(title))


def main() -> None:
    if QApplication.instance() is None:
        QApplication(sys.argv)
    patch_message_boxes()

    import app.window as win_mod

    w = win_mod.MainWindow()
    pump()

    # --- Tab structure ----------------------------------------------------
    check(w._tabs.count() == 4, "expected 4 tabs")
    labels = [w._tabs.tabText(i) for i in range(w._tabs.count())]
    for needle in ("Downloader", "Audio Converter", "Video Converter", "History"):
        check(any(needle in t for t in labels), f"missing tab label: {needle}")

    # Tab icons must render (regression net for the tofu-box glyph era —
    # glyphs depended on the user's fonts, e.g. ▣ showed as a plain box
    # on Linux Mint; icons are now bundled SVGs)
    missing_icons = [
        i for i in range(w._tabs.count()) if w._tabs.tabIcon(i).isNull()
    ]
    check(not missing_icons, f"tabs without a rendered icon: {missing_icons}")

    dl = getattr(w, "download_tab", None) or w
    conv = getattr(w, "audio_tab", None) or w
    vid = getattr(w, "video_tab", None) or w
    hist = getattr(w, "history_tab", None) or w

    # --- Downloader queue --------------------------------------------------
    n0 = dl.queue_list.count()
    ok = add_url(dl, "https://www.youtube.com/watch?v=abc123")
    check(ok is True, "add_url(watch?v=) should return True")
    check(dl.queue_list.count() == n0 + 1, "watch URL should be queued")
    check(dl.queue_list.item(n0).text() == "[abc123]",
          f"watch label should be [abc123], got {dl.queue_list.item(n0).text()!r}")
    check("Playlist detected" not in dl.status_label.text(),
          "watch?v= URL must NOT be flagged as playlist")

    ok = add_url(dl, "https://www.youtube.com/playlist?list=PLsmoke123")
    check(ok is True, "add_url(playlist) should return True")
    check(dl.queue_list.count() == n0 + 2, "playlist URL should be queued")
    check(dl.queue_list.item(n0 + 1).text().startswith("\U0001f4cb"),
          "playlist label should start with clipboard icon")
    check("Playlist detected" in dl.status_label.text(),
          "playlist URL should flag 'Playlist detected'")

    ok = add_url(dl, "https://www.youtube.com/watch?v=abc123")
    check(ok is True, "duplicate add should still return True")
    check(dl.queue_list.count() == n0 + 2, "duplicate URL must be deduped")

    # Remove the first queued row
    dl.queue_list.item(n0).setSelected(True)
    dl._remove_selected()
    check(dl.queue_list.count() == n0 + 1, "remove should drop one row")

    dl._clear_queue()
    check(dl.queue_list.count() == 0, "clear should empty the queue")

    # --- History model + rendering ----------------------------------------
    history_append(
        w, url="https://example.com/a", filepath="/tmp/a.mp3",
        filename="a.mp3", filesize=2048, type_="audio", container="mp3",
        audio_only=True, status="completed",
    )
    history_append(
        w, url="https://example.com/b", filepath="",
        filename="b", filesize=0, type_="video", container="mp4",
        audio_only=False, status="failed", error="boom",
    )
    history_render(hist, w)
    check(hist._history_list.count() == 2, "history should render 2 entries")

    # Search narrows to zero and shows the placeholder
    hist._history_search.setText("zzznomatch")
    pump()
    check(hist._history_list.count() == 0, "no-match search should hide all rows")
    check(not hist._history_empty.isHidden(), "empty placeholder should be visible")
    hist._history_search.setText("")
    pump()
    check(hist._history_list.count() == 2, "cleared search should restore rows")
    check(hist._history_empty.isHidden(), "empty placeholder should hide again")

    # --- Converter file lists ----------------------------------------------
    conv._conv_add_file(Path("/cmt-smoke/notes.txt"))
    check(conv.conv_file_list.count() == 0, "unsupported .txt must be skipped")
    check("Skipped" in conv.conv_status_label.text(),
          "unsupported file should set Skipped status")

    conv._conv_add_file(Path("/cmt-smoke/song.mp3"))
    conv._conv_add_file(Path("/cmt-smoke/song.mp3"))
    check(conv.conv_file_list.count() == 1, "converter should dedup identical paths")

    folder = Path(_TMP_HOME) / "smoke-audio"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "one.mp3").write_text("x", encoding="utf-8")
    (folder / "two.m4a").write_text("x", encoding="utf-8")
    (folder / "three.txt").write_text("x", encoding="utf-8")
    added = conv._conv_add_folder(folder)
    check(added == 2, f"folder add should return 2 supported files, got {added}")
    check(conv.conv_file_list.count() == 3, "folder add should leave 3 files queued")

    conv._conv_clear_files()
    check(conv.conv_file_list.count() == 0, "clear should empty converter list")

    # --- Video converter file lists -----------------------------------------
    vid._video_conv_add_file(Path("/cmt-smoke/clip.mp4"))
    vid._video_conv_add_file(Path("/cmt-smoke/song.mp3"))
    check(vid.video_conv_file_list.count() == 1, "video list should keep only .mp4")
    vid._video_conv_clear_files()
    check(vid.video_conv_file_list.count() == 0, "clear should empty video list")

    # --- Worker tracking ----------------------------------------------------
    class _Quick(QThread):
        def run(self):
            pass

    track, tracked_count = track_api(dl)
    t = _Quick()
    track(t)
    check(tracked_count() >= 1, "tracked set should pin the worker")
    t.start()
    t.wait()
    pump(5)
    check(tracked_count() == 0, "worker should be released after deferred delete")

    track2, tracked2 = track_api(conv)
    t2 = _Quick()
    track2(t2)
    t2.start()
    t2.wait()
    pump(5)
    check(tracked2() == 0, "converter tracker should release its worker")

    # --- Idle cancel guards --------------------------------------------------
    dl._cancel_download()
    check(dl.download_btn.isEnabled(), "idle cancel should leave Start enabled")
    check(not dl.cancel_btn.isEnabled(), "idle cancel should leave Cancel disabled")

    conv._conv_cancel()
    check(conv.conv_start_btn.isEnabled(), "idle conv cancel should leave Convert enabled")
    vid._video_conv_cancel()
    check(vid.video_conv_start_btn.isEnabled(), "idle video cancel should leave Convert enabled")

    # --- Start guards ---------------------------------------------------------
    _StubMessageBox.calls.clear()
    dl._start_download()
    check(find_warning("No URLs"), "empty queue should warn 'No URLs'")
    check(dl.download_btn.isEnabled(), "empty-queue guard should not start a batch")

    add_url(dl, "https://example.com/x")
    dl.dir_input.setText("/nonexistent-cmt-smoke")
    dl._start_download()
    check(find_warning("Bad folder"), "bad folder should warn")
    check(dl.download_btn.isEnabled(), "bad-folder guard should not start a batch")

    # Clean-title guard: enabled with empty tag list (needs valid queue+dir so
    # the earlier guards pass first)
    if getattr(dl, "clean_chk", None) is not None:
        dl.clean_chk.setChecked(True)
        dl.clean_tags_input.setText("")
        dl.dir_input.setText(_TMP_HOME)
        dl._start_download()
        check(find_warning("No cleanup tags"), "empty clean tags should warn")
        check(dl.download_btn.isEnabled(), "clean-tags guard should not start a batch")

    dl._clear_queue()

    # --- History re-queue action ----------------------------------------------
    history_render(hist, w)
    item = hist._history_list.item(0)
    check(item is not None, "history row should exist for re-queue test")
    hist._on_history_item_action(item)
    check(w._tabs.currentIndex() == 0, "re-queue should switch to Downloader tab")
    check(dl.url_input.text() == "https://example.com/b",
          f"url_input should hold re-queued url, got {dl.url_input.text()!r}")
    check(dl.queue_list.count() == 1, "re-queued URL should land in the queue")

    # --- History clear ---------------------------------------------------------
    hist._on_history_clear()
    check(any(
        kind in ("question", "warning") and title == "Clear history"
        for (kind, title, _) in _StubMessageBox.calls
    ), "history clear should confirm first")
    check(hist._history_list.count() == 0, "history should be empty after clear")

    pump()
    print("SMOKE OK")


if __name__ == "__main__":
    main()
