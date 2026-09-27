"""Tests for the unhandled-exception hook installed by main().

The Windows build is a windowed (no-console) exe, so without this hook an
uncaught exception — including one raised inside a Qt slot, which PySide6
routes through sys.excepthook — is written to stderr nobody can see.
"""

import sys
from typing import ClassVar

import main as main_mod


class _StubMessageBox:
    calls: ClassVar[list] = []

    @classmethod
    def critical(cls, *args, **kwargs):
        cls.calls.append((args, kwargs))


class _GuiUp:
    """Pretend a QApplication exists (pytest itself must not create one:
    headless CI has no display and no QT_QPA_PLATFORM set)."""

    @staticmethod
    def instance():
        return object()


class _GuiDown:
    @staticmethod
    def instance():
        return None


def _install(monkeypatch, *, gui: bool):
    """Install the hook with a stubbed dialog and a recording previous hook."""
    monkeypatch.setattr(main_mod, "QMessageBox", _StubMessageBox)
    monkeypatch.setattr(main_mod, "QApplication", _GuiUp if gui else _GuiDown)
    chained: list = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: chained.append(a))
    _StubMessageBox.calls.clear()
    main_mod._install_excepthook()
    assert chained == [], "the hook only fires once something actually fails"
    assert callable(sys.excepthook)
    return chained


class TestExcepthook:
    def test_writes_crash_log_and_chains(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.constants.CONFIG_DIR", tmp_path)
        chained = _install(monkeypatch, gui=True)

        sys.excepthook(ValueError, ValueError("boom"), None)

        log = (tmp_path / "crash.log").read_text(encoding="utf-8")
        assert "ValueError: boom" in log
        assert chained and chained[0][0] is ValueError  # previous hook still ran

    def test_shows_dialog_with_the_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.constants.CONFIG_DIR", tmp_path)
        _install(monkeypatch, gui=True)

        sys.excepthook(ValueError, ValueError("boom"), None)

        assert _StubMessageBox.calls, "a running GUI must show the error dialog"
        args, _ = _StubMessageBox.calls[0]
        assert "ValueError: boom" in " ".join(str(part) for part in args)

    def test_no_dialog_before_the_gui_exists(self, monkeypatch, tmp_path):
        """Import-time failures fire the hook before QApplication exists —
        calling Qt then would raise again and hide the original error."""
        monkeypatch.setattr("app.constants.CONFIG_DIR", tmp_path)
        chained = _install(monkeypatch, gui=False)

        sys.excepthook(RuntimeError, RuntimeError("too early"), None)

        assert not _StubMessageBox.calls
        assert (tmp_path / "crash.log").exists()
        assert chained, "the previous hook must still run"

    def test_survives_an_unwritable_config_dir(self, monkeypatch, tmp_path):
        blocker = tmp_path / "blocker.txt"
        blocker.write_text("x", encoding="utf-8")
        # CONFIG_DIR sits *under* a regular file → mkdir raises OSError.
        monkeypatch.setattr("app.constants.CONFIG_DIR", blocker / "sub")
        chained = _install(monkeypatch, gui=True)

        sys.excepthook(OSError, OSError("disk gone"), None)  # must not raise

        assert chained, "a failing log write must not break the hook"
