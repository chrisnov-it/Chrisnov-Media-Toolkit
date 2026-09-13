"""Typed QSettings wrapper for persistent app options.

QSettings.value() is typed as returning `object` by the PySide6 stubs,
and INI backends can hand booleans back as strings, so every read goes
through isinstance-checked accessors instead of the untyped
`value(..., type=...)` form that also produced noisy diagnostics.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

ORG_NAME = "Chrisnov IT Solutions"
APP_NAME = "Chrisnov Media Toolkit"


class AppSettings:
    """Thin wrapper around QSettings with typed read accessors."""

    def __init__(self) -> None:
        self._qs = QSettings(ORG_NAME, APP_NAME)

    # -- generic values ---------------------------------------------------

    def get_str(self, key: str, default: str = "") -> str:
        value = self._qs.value(key, default)
        if isinstance(value, str):
            return value
        return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._qs.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        if isinstance(value, int):
            return value != 0
        return default

    def set_value(self, key: str, value: object) -> None:
        self._qs.setValue(key, value)

    # -- output folder persistence ------------------------------------------

    def saved_dir(self, key: str, default: Path) -> str:
        """Return the saved folder for *key*, falling back to *default* if the
        saved value is missing or no longer exists on disk."""
        value = self.get_str(f"dirs/{key}")
        if value and Path(value).is_dir():
            return value
        return str(default)

    def save_dir(self, key: str, path: str) -> None:
        """Persist a folder path for *key* if it points at a real directory."""
        if path and Path(path).is_dir():
            self._qs.setValue(f"dirs/{key}", path)
