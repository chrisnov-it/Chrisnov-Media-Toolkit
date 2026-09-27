#!/usr/bin/env python
"""Offscreen GUI smoke test for Chrisnov Media Toolkit.

Formalizes the ad-hoc offscreen checks run during the audit fixes (#4-#9)
and the window.py refactor (#10). Exercises tab construction, URL queue
handling, history rendering/search/clear, converter file-list handling,
worker tracking, and idle cancel/start guards - without any network access.
Later audit passes added the shutdown regressions: completion handlers must
stay fenced when bookkeeping raises, Cancel must neither block the GUI nor
terminate() the thread, a non-UTF-8 file drop must be ignored, and
MainWindow.closeEvent must defer while a tracked worker is still running.

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

import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import ClassVar

# --- Environment isolation - MUST happen before any Qt import ----------
# Redirect the home directory so the download history (and the
# skip-duplicates archive) never touch the developer's real ~/.config.
_TMP_HOME = tempfile.mkdtemp(prefix="cmt-smoke-")
os.environ["HOME"] = _TMP_HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP_HOME, ".config")
# Windows: ntpath.expanduser() reads USERPROFILE first and ignores HOME, so
# without this the smoke test reads, appends to — and (at the end of the run)
# clears! — the developer's real download history.
os.environ["USERPROFILE"] = _TMP_HOME
os.environ["HOMEDRIVE"], os.environ["HOMEPATH"] = os.path.splitdrive(_TMP_HOME)
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
    #: Override for question(); None = the default Yes.
    answer = None
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
        # Tests flip `answer` to No to exercise the "decline" branch.
        return cls.answer if cls.answer is not None else cls.Yes

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

    # --- Clipped rows keep the full target on hover (P1) ---------------------
    # The old code sliced identifiers mid-word with no ellipsis and threw the
    # full URL away — a row that hid what it was about to download.
    from PySide6.QtCore import Qt

    long_plain = "https://example.com/" + "very-long-path-segment/" * 6
    ok = add_url(dl, long_plain)
    check(ok is True, "long plain URL should be queued")
    row = dl.queue_list.item(0)
    check("…" in row.text(),
          f"a clipped label must show an ellipsis, got {row.text()!r}")
    check(row.toolTip() == long_plain,
          "a clipped row must keep the full URL as its tooltip")

    long_pl = ("https://www.youtube.com/watch?v=abc123def456&list="
               + "PL" + "x" * 40)
    ok = add_url(dl, long_pl)
    check(ok is True, "long playlist URL should be queued")
    row = dl.queue_list.item(1)
    check("…" in row.text(),
          f"a long playlist id must be ellipsised, got {row.text()!r}")
    check(row.toolTip() == long_pl,
          "the playlist row must keep the full URL as its tooltip")
    dl._clear_queue()

    # Status labels: long errors must wrap and be selectable/copyable (P1).
    sel = Qt.TextInteractionFlag.TextSelectableByMouse
    for label, name in (
        (dl.status_label, "dl.status_label"),
        (dl.info_box, "dl.info_box"),
        (conv.conv_status_label, "conv.conv_status_label"),
        (vid.video_conv_status_label, "vid.video_conv_status_label"),
    ):
        check(label.wordWrap(), f"{name} should word-wrap long messages")
        check(bool(label.textInteractionFlags() & sel),
              f"{name} should let the user select its text")

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

    # A bare refresh() (what history_changed → refresh() does when a download
    # finishes) must keep the user's search instead of resetting it to "".
    hist._history_search.setText("a.mp3")
    pump()
    check(hist._history_list.count() == 1, "filter should narrow to 1 row")
    history_render(hist, w)
    check(hist._history_list.count() == 1,
          "refresh() must keep the active search filter")
    hist._history_search.setText("")
    pump()
    check(hist._history_list.count() == 2, "cleared search should restore rows")
    check(hist._history_empty.isHidden(), "empty placeholder should hide again")

    # --- Converter file lists ----------------------------------------------
    # Empty-state placeholder: visible while the list is empty, hidden
    # once files are queued, back again after Clear.
    check(not conv._conv_empty.isHidden(),
          "conv empty placeholder should start visible")

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
    # Recursion must work, and hidden entries (.git, dotfiles) are pruned
    # by the bounded scan that replaced rglob on the GUI thread.
    (folder / "sub").mkdir(exist_ok=True)
    (folder / "sub" / "four.mp3").write_text("x", encoding="utf-8")
    (folder / ".cache").mkdir(exist_ok=True)
    (folder / ".cache" / "hidden.mp3").write_text("x", encoding="utf-8")
    added = conv._conv_add_folder(folder)
    check(added == 3, f"folder add should return 3 supported files, got {added}")
    check(conv.conv_file_list.count() == 4, "folder add should leave 4 files queued")
    check(conv._conv_empty.isHidden(),
          "conv empty placeholder should hide while files are queued")

    conv._conv_clear_files()
    check(conv.conv_file_list.count() == 0, "clear should empty converter list")
    check(not conv._conv_empty.isHidden(),
          "conv empty placeholder should return after clear")

    # --- Video converter file lists -----------------------------------------
    check(not vid._video_conv_empty.isHidden(),
          "video empty placeholder should start visible")
    vid._video_conv_add_file(Path("/cmt-smoke/clip.mp4"))
    vid._video_conv_add_file(Path("/cmt-smoke/song.mp3"))
    check(vid.video_conv_file_list.count() == 1, "video list should keep only .mp4")
    check(vid._video_conv_empty.isHidden(),
          "video empty placeholder should hide while videos are queued")
    vid._video_conv_clear_files()
    check(vid.video_conv_file_list.count() == 0, "clear should empty video list")
    check(not vid._video_conv_empty.isHidden(),
          "video empty placeholder should return after clear")

    # --- Batch settings freeze (MEDIUM) --------------------------------------
    # _conv_start() must freeze every widget _conv_kick_next() reads (and
    # snapshot the shared cleanup-tag list), _conv_reset() must thaw them.
    # The kick is patched out so no real worker/ffmpeg gets spawned here.
    conv._conv_add_file(Path("/cmt-smoke/freeze.mp3"))
    conv.conv_dir_input.setText(_TMP_HOME)
    orig_kick = conv._conv_kick_next
    conv._conv_kick_next = lambda: None
    from app.utils import BATCH_BUSY_HINT, set_controls_busy

    orig_conv_tip = conv.conv_start_btn.toolTip()
    orig_fmt_tip = conv.conv_fmt_combo.toolTip()
    try:
        conv._conv_start()
        check(conv._conv_active, "audio batch should be active after start")
        for wdg_name in ("conv_fmt_combo", "conv_bitrate_combo", "conv_sr_combo",
                         "conv_cbr_radio", "conv_norm_ebu", "conv_lufs_spin",
                         "conv_trim_chk", "conv_clean_chk", "conv_dir_input"):
            check(not getattr(conv, wdg_name).isEnabled(),
                  f"{wdg_name} must be frozen while the batch runs")
        check(conv._conv_clean_tags is not None,
              "cleanup tags should be snapshotted at start")
        # Frozen controls must explain *why* they are off (P1): tooltips
        # still fire on disabled widgets, so this is the one place to answer
        # "why can't I click this?".
        check(conv.conv_start_btn.toolTip() == BATCH_BUSY_HINT,
              f"frozen Convert should carry the busy tooltip, got "
              f"{conv.conv_start_btn.toolTip()!r}")
        check(conv.conv_fmt_combo.toolTip() == BATCH_BUSY_HINT,
              "frozen settings should carry the busy tooltip too")
    finally:
        conv._conv_kick_next = orig_kick
        conv._conv_reset()
    check(conv.conv_fmt_combo.isEnabled(), "audio settings must thaw after the batch")
    check(conv.conv_dir_input.isEnabled(), "audio output folder must thaw too")
    check(conv._conv_clean_tags is None, "tag snapshot must be dropped at reset")
    check(conv.conv_start_btn.toolTip() == orig_conv_tip,
          "the busy tooltip must be restored when the batch ends")
    check(conv.conv_fmt_combo.toolTip() == orig_fmt_tip,
          "the settings' original tooltips must come back as well")

    # The same helper, exercised directly on the Downloader's Start button.
    orig_dl_tip = dl.download_btn.toolTip()
    set_controls_busy((dl.download_btn,), True)
    check(not dl.download_btn.isEnabled()
          and dl.download_btn.toolTip() == BATCH_BUSY_HINT,
          "busy Start should be disabled and self-explaining")
    set_controls_busy((dl.download_btn,), False)
    check(dl.download_btn.isEnabled()
          and dl.download_btn.toolTip() == orig_dl_tip,
          "unfreezing Start must restore its tooltip and enabled state")

    vid._video_conv_add_file(Path("/cmt-smoke/freeze.mp4"))
    vid.video_conv_dir_input.setText(_TMP_HOME)
    orig_vkick = vid._video_conv_kick_next
    vid._video_conv_kick_next = lambda: None
    orig_vstart_tip = vid.video_conv_start_btn.toolTip()
    try:
        vid._video_conv_start()
        check(vid._video_conv_active, "video batch should be active after start")
        for wdg_name in ("video_conv_fmt_combo", "video_conv_quality_combo",
                         "video_conv_audio_copy_chk", "video_conv_clean_chk",
                         "video_conv_dir_input"):
            check(not getattr(vid, wdg_name).isEnabled(),
                  f"{wdg_name} must be frozen while the batch runs")
        check(vid._video_conv_clean_tags is not None,
              "video cleanup tags should be snapshotted at start")
        check(vid.video_conv_start_btn.toolTip() == BATCH_BUSY_HINT,
              "frozen video Convert should carry the busy tooltip")
    finally:
        vid._video_conv_kick_next = orig_vkick
        vid._video_conv_reset()
    check(vid.video_conv_fmt_combo.isEnabled(),
          "video settings must thaw after the batch")
    check(vid._video_conv_clean_tags is None, "video tag snapshot must be dropped")
    check(vid.video_conv_start_btn.toolTip() == orig_vstart_tip,
          "the video busy tooltip must be restored when the batch ends")

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

    # --- Conversion outcomes must land in the shared history (P1) ------------
    # Conversions never called history.append before: a failed run left no
    # trace beyond a transient status line that vanished with the batch.
    # The handlers are driven by hand with manual queue state — never
    # _conv_start(), which would spawn a real ffmpeg worker.
    out_file = Path(_TMP_HOME) / "converted.mp3"
    out_file.write_bytes(b"x" * 64)
    conv._conv_queue = [Path(_TMP_HOME) / "source.wav"]
    conv._conv_files = [conv._conv_queue[0]]
    conv._conv_idx = 0
    conv._conv_total = 1
    conv._conv_active = True
    conv._on_conv_ok(str(out_file))
    entry = w.history.entries[0]
    check(entry.get("status") == "completed",
          f"a finished conversion must be recorded as completed, "
          f"got {entry.get('status')!r}")
    check(entry.get("filepath") == str(out_file),
          "the completed entry should point at the output file")
    check(entry.get("type") == "audio",
          f"the conversion entry should be typed audio, got {entry.get('type')!r}")

    conv._conv_queue = [Path(_TMP_HOME) / "broken.wav"]
    conv._conv_files = [conv._conv_queue[0]]
    conv._conv_idx = 0
    conv._conv_total = 1
    conv._conv_active = True
    conv._on_conv_fail("ffmpeg exploded: exit code 1")
    entry = w.history.entries[0]
    check(entry.get("status") == "failed",
          f"a failed conversion must be recorded as failed, "
          f"got {entry.get('status')!r}")
    check("ffmpeg exploded" in (entry.get("error") or ""),
          "the failed entry must keep its error message")
    check(not entry.get("filepath"),
          "a failed conversion must not claim an output file")
    check(str(entry.get("url", "")).endswith("broken.wav"),
          "url should hold the source path (searchable, never requeued)")

    vout = Path(_TMP_HOME) / "converted.mp4"
    vout.write_bytes(b"x" * 32)
    vid._video_conv_queue = [Path(_TMP_HOME) / "clip.mkv"]
    vid._video_conv_files = [vid._video_conv_queue[0]]
    vid._video_conv_idx = 0
    vid._video_conv_total = 1
    vid._video_conv_active = True
    vid._on_video_conv_ok(str(vout))
    entry = w.history.entries[0]
    check(entry.get("type") == "video" and entry.get("status") == "completed",
          f"video conversion should record as completed/video, got "
          f"{entry.get('type')!r}/{entry.get('status')!r}")

    history_render(hist, w)
    check(hist._history_list.count() == 3,
          f"three conversion entries should render, got "
          f"{hist._history_list.count()}")
    fail_row = next(
        (hist._history_list.item(i)
         for i in range(hist._history_list.count())
         if "ffmpeg exploded" in hist._history_list.item(i).text()),
        None,
    )
    check(fail_row is not None,
          "the failed conversion row should be rendered somewhere")
    check("ffmpeg exploded" in fail_row.toolTip(),
          "the failed history row must carry the error in its tooltip too")

    # Double-click on a conversion entry must not requeue its local source
    # path as a URL — the guard is scheme-based, not merely "url is set".
    tab_before = w._tabs.currentIndex()
    dl_rows = dl.queue_list.count()
    hist._on_history_item_action(fail_row)
    check(w._tabs.currentIndex() == tab_before,
          "double-click on a conversion entry must not jump to the Downloader")
    check(dl.queue_list.count() == dl_rows,
          "a local source path must never be queued as a URL")

    # The conversion bookkeeping is fenced like the Downloader's: a failed
    # history write must not raise out of the slot, must still emit
    # history_changed (that is what keeps the History tab honest), and must
    # let the batch finish instead of stranding it.
    conv_failed_writes: list[str] = []
    conv_fired: list[int] = []
    conv.history_changed.connect(lambda: conv_fired.append(1))

    class _ConvLogCapture(logging.Handler):
        def emit(self, record):
            conv_failed_writes.append(record.getMessage())

    def _conv_boom(**kw):
        raise OSError("disk on fire")

    conv_capture = _ConvLogCapture()
    logging.getLogger("app.convert_tab").addHandler(conv_capture)
    real_conv_append = conv._history.append
    conv._history.append = _conv_boom
    try:
        conv._conv_queue = [Path(_TMP_HOME) / "will-fail.wav"]
        conv._conv_files = [conv._conv_queue[0]]
        conv._conv_idx = 0
        conv._conv_total = 1
        conv._conv_active = True
        conv._on_conv_fail("boom")
    finally:
        conv._history.append = real_conv_append
        logging.getLogger("app.convert_tab").removeHandler(conv_capture)
    check(any("disk on fire" in m for m in conv_failed_writes),
          "the conversion history failure should be logged for diagnosis")
    check(conv_fired, "history_changed must fire even when the history write fails")
    check(not conv._conv_active,
          "the conversion batch must finish even when bookkeeping fails")
    history_render(hist, w)
    check(hist._history_list.count() == 3,
          "a failed history write must not corrupt the rendered history")

    # --- About dialog + background yt-dlp update check -----------------------
    # The check must never hit the network during a smoke run and must never
    # block the dialog; the PyPI lookup is faked and the worker is driven by
    # hand. Regression: it used to run urlopen() on the GUI thread and compare
    # versions with "!=" (advertising downgrades).
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel

    from app import update_check

    class _FakePypiResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"info": {"version": "99.9.9"}}'

    real_urlopen = update_check.urllib.request.urlopen
    update_check.urllib.request.urlopen = lambda url, timeout=None: _FakePypiResponse()
    try:
        notice = QLabel("")
        notice.hide()
        w._start_update_check(notice, "1.0")
        for _ in range(60):  # the worker delivers on the GUI thread
            pump()
            if notice.text():
                break
            time.sleep(0.05)
        check("99.9.9" in notice.text(),
              f"update notice should show the newer version, got {notice.text()!r}")
        check(not notice.isHidden(), "update notice should become visible")

        # The dialog itself must open (and start the check) without blocking
        QTimer.singleShot(300, lambda: (QApplication.activeModalWidget() or w).close())
        w._show_about()
        check(w._about_update_target is None,
              "About dialog should drop its update target when it closes")
        check(w._about_ffmpeg_label is None,
              "About dialog should drop its FFmpeg probe target when it closes")
    finally:
        update_check.urllib.request.urlopen = real_urlopen

    # A late worker answer after the dialog closed must be ignored, not crash
    w._show_update_notice("99.9.9")
    w._show_ffmpeg_version("6.1.1")  # same contract for the FFmpeg row

    # --- Completion handler fencing (HIGH) ------------------------------------
    # A history/IO failure inside _on_item_ok must never strand the batch: the
    # old code let the exception escape the Qt slot, skipping idx += 1 and
    # _kick_next(), which froze the queue until the user found Cancel.
    from PySide6.QtCore import QMimeData, QPointF, QUrl, Signal
    from PySide6.QtCore import Qt as QtCoreQt
    from PySide6.QtGui import QCloseEvent, QDropEvent

    from app.download_tab import BatchState

    dl._clear_queue()
    add_url(dl, "https://example.com/fencing")
    single = BatchState(
        urls=["https://example.com/fencing"], outdir=_TMP_HOME, audio_only=True,
        height=None, container="mp3", bitrate=192, clean_tags=None,
        embed_metadata=False, embed_thumbnail=False, archive_path=None,
    )
    dl._batch = single
    real_append = dl._history.append
    exploding = []
    logged: list[str] = []

    def _boom(**kw):
        exploding.append(kw)
        raise OSError("disk on fire")

    class _LogCapture(logging.Handler):
        def emit(self, record):
            logged.append(record.getMessage())

    capture = _LogCapture()
    logging.getLogger("app.download_tab").addHandler(capture)
    dl._history.append = _boom
    try:
        dl._on_item_ok(str(Path(_TMP_HOME) / "ghost.mp3"))
    finally:
        dl._history.append = real_append
        logging.getLogger("app.download_tab").removeHandler(capture)
    check(single.idx == 1, "a history failure must still advance the batch")
    check(exploding, "the history append should really have been attempted")
    check(any("disk on fire" in m for m in logged),
          "the history failure should be logged for diagnosis")
    check(dl._batch is None, "single-item batch should reset after the failure")
    check(dl.download_btn.isEnabled(),
          "the queue must not be left stranded with Start disabled")
    dl._clear_queue()

    # --- A vanished file must not be recorded as completed (MEDIUM) ----------
    # yt-dlp can report success for a file we cannot find on disk. Writing
    # status="completed" put a dead entry in the history: zero size, a folder
    # that cannot be opened, and a requeue that hides what happened.
    dl._clear_queue()
    add_url(dl, "https://example.com/vanished")
    vanished = BatchState(
        urls=["https://example.com/vanished"], outdir=_TMP_HOME, audio_only=True,
        height=None, container="mp3", bitrate=192, clean_tags=None,
        embed_metadata=False, embed_thumbnail=False, archive_path=None,
    )
    dl._batch = vanished
    dl._on_item_ok(str(Path(_TMP_HOME) / "vanished.mp3"))
    entry = dl._history.entries[0]
    check(entry.get("status") == "failed",
          f"a vanished file must be recorded as failed, got {entry.get('status')!r}")
    check(bool(entry.get("error")), "the failed entry should say what went wrong")
    check(vanished.done == 0, "a missing file must not count as completed")
    check(vanished.idx == 1, "the batch must still advance past the missing file")
    check(dl._batch is None, "single-item batch should reset after the miss")
    # The per-item message is intentionally replaced by the batch summary —
    # which itself proves the miss was not counted as a completion.
    check("Queue finished: 0/1" in dl.status_label.text(),
          f"summary must not count the miss, got {dl.status_label.text()!r}")
    dl._clear_queue()

    # --- Playlist inspect must keep the queue (MEDIUM) ------------------------
    # Declining the large-playlist confirm (or hitting an inspect error) runs
    # before any download starts, so it must not wipe the user's queue — the
    # old code called _reset_after_batch() and lost every queued URL.
    def _queued_batch() -> BatchState:
        return BatchState(
            urls=list(dl.current_batch), outdir=_TMP_HOME, audio_only=True,
            height=None, container="mp3", bitrate=192, clean_tags=None,
            embed_metadata=False, embed_thumbnail=False, archive_path=None,
        )

    dl._clear_queue()
    add_url(dl, "https://example.com/big-playlist")
    dl._batch = _queued_batch()
    _StubMessageBox.answer = _StubMessageBox.No
    try:
        dl._on_inspect_done(
            [("https://example.com/big-playlist", 999, "3 h", "Big List")],
        )
    finally:
        _StubMessageBox.answer = None
    check(any(t == "Confirm large playlist download"
              for _, t, _ in _StubMessageBox.calls),
          "the large-playlist confirm should really be shown")
    check(dl._batch is None, "declining the confirm should end the batch")
    check(dl.queue_list.count() == 1,
          f"declining must keep the queued URLs, got {dl.queue_list.count()}")
    check(dl.download_btn.isEnabled(), "declining should re-enable Start")

    dl._batch = _queued_batch()
    dl._on_inspect_error("https://example.com/big-playlist", "boom")
    check(dl.queue_list.count() == 1,
          "an inspect error must keep the queued URLs too")
    dl._clear_queue()

    # Dropping several items at once must queue every one of them.
    drop_urls = []
    for name, url in (("drop-a.txt", "https://example.com/drop-a"),
                      ("drop-b.txt", "https://example.com/drop-b")):
        p = Path(_TMP_HOME) / name
        p.write_text(url + "\n", encoding="utf-8")
        drop_urls.append(QUrl.fromLocalFile(str(p)))
    multi = QMimeData()
    multi.setUrls(drop_urls)
    w.dropEvent(QDropEvent(QPointF(12, 12), QtCoreQt.DropAction.CopyAction,
                           multi, QtCoreQt.MouseButton.LeftButton,
                           QtCoreQt.KeyboardModifier.NoModifier))
    check(dl.queue_list.count() == 2,
          f"both dropped files must be queued, got {dl.queue_list.count()}")
    dl._clear_queue()

    # --- Cancel must not block the GUI or terminate the thread (HIGH) ---------
    class _StubWorker(QThread):
        """Stands in for DownloadWorker/ConvertWorker: same signals, and a
        sleep instead of yt-dlp/ffmpeg so the contract can be measured."""

        progress = Signal(int)
        status = Signal(str)
        finished_ok = Signal(str)
        failed = Signal(str)

        def __init__(self):
            super().__init__()
            self.cancelled = False

        def run(self):
            time.sleep(0.6)

        def cancel(self):
            self.cancelled = True

    def _wire(worker: QThread) -> None:
        """Mirror _kick_next(): connect the signals the cancel path disconnects,
        otherwise disconnecting them logs 'Failed to disconnect' warnings."""
        for name in ("progress", "status", "finished_ok", "failed"):
            getattr(worker, name).connect(lambda *a: None)

    # Downloader: cancel a live worker and return immediately.
    dl.worker = _StubWorker()
    dl._tracker.track(dl.worker)
    dl._batch = BatchState(
        urls=["https://example.com/slow"], outdir=_TMP_HOME, audio_only=True,
        height=None, container="mp3", bitrate=192, clean_tags=None,
        embed_metadata=False, embed_thumbnail=False, archive_path=None,
    )
    _wire(dl.worker)
    dl.worker.start()
    worker_ref = dl.worker
    started = time.monotonic()
    dl._cancel_download()
    cancel_elapsed = time.monotonic() - started
    check(cancel_elapsed < 0.4,
          f"download cancel blocked the GUI for {cancel_elapsed:.2f}s")
    check(worker_ref.cancelled,
          "cancel must set the worker's cancel flag")
    check(worker_ref.isRunning(),
          "cancel must not terminate() the thread (it is still winding down)")
    check(dl._batch is None and dl.download_btn.isEnabled(),
          "cancel should reset the batch state and re-enable Start")
    worker_ref.wait()

    # Audio converter: same guarantees.
    conv._conv_worker = _StubWorker()
    conv._tracker.track(conv._conv_worker)
    conv._conv_active = True
    conv_worker = conv._conv_worker
    _wire(conv_worker)
    conv_worker.start()
    started = time.monotonic()
    conv._conv_cancel()
    conv_elapsed = time.monotonic() - started
    check(conv_elapsed < 0.4, f"convert cancel blocked the GUI for {conv_elapsed:.2f}s")
    check(conv_worker.cancelled, "convert cancel must set the cancel flag")
    check(conv_worker.isRunning(), "convert cancel must not terminate() the thread")
    check(conv.conv_start_btn.isEnabled(),
          "convert cancel should re-enable the Convert button")
    conv_worker.wait()

    # --- Dropping a binary file must not raise (HIGH) -------------------------
    binary = Path(_TMP_HOME) / "not-really-a-playlist.mp3"
    binary.write_bytes(b"\xff\xfb\x90" + bytes(range(256)))  # not valid UTF-8
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(binary))])
    drop = QDropEvent(QPointF(12, 12), QtCoreQt.DropAction.CopyAction, md,
                      QtCoreQt.MouseButton.LeftButton,
                      QtCoreQt.KeyboardModifier.NoModifier)
    rows_before = dl.queue_list.count()
    w.dropEvent(drop)  # used to raise UnicodeDecodeError out of the handler
    check(dl.queue_list.count() == rows_before,
          "dropping a binary file must be ignored, not queued")
    dl._clear_queue()

    # --- Shutdown: close waits for running workers (HIGH) ---------------------
    sleeper = _StubWorker()
    dl._tracker.track(sleeper)
    sleeper.start()
    deferred = QCloseEvent()
    w.closeEvent(deferred)
    check(not deferred.isAccepted(),
          "closeEvent must defer while a tracked worker is still running")
    check("stopping…" in w.windowTitle(),
          "a deferred close should show the 'stopping' title")
    w.shutdown()
    w.shutdown()  # idempotent — repeated shutdowns must not cancel twice
    sleeper.wait()
    pump(5)
    final_close = QCloseEvent()
    w.closeEvent(final_close)
    check(final_close.isAccepted(),
          "closeEvent should accept once the workers have exited")

    pump()
    # Drop the throwaway home dir (history + archive written above).
    shutil.rmtree(_TMP_HOME, ignore_errors=True)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
