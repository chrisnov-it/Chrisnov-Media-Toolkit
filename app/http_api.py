"""Optional localhost helper API for browser extensions.

A tiny HTTP server that runs in a background QThread and exposes two
endpoints:

    GET /health   -> {"ok": true}
    POST /queue   -> queues {"url": "..."} with Authorization: Bearer <token>

The token is per-installation (stored in QSettings) and must be supplied by
the caller, so a random web page cannot silently push URLs into the queue.
Everything binds to 127.0.0.1 only, with no wildcard CORS headers.
"""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal

_MAX_BODY_BYTES = 64 * 1024


class _LocalThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LocalApiServer(QThread):
    """Background HTTP server that emits queued URLs on the GUI thread."""

    url_received = Signal(str)
    status_changed = Signal(str)

    def __init__(self, token: str, port: int = 8765,
                 parent=None) -> None:
        super().__init__(parent)
        self.token = token
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._stop_requested = threading.Event()

    def _extract_bearer_token(self, auth_header: str) -> str:
        scheme, _, value = auth_header.partition(" ")
        if scheme.lower() == "bearer":
            return value.strip()
        return ""

    def run(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._reply(200, {"ok": True})
                    return
                if parsed.path == "/queue":
                    self._reply(405, {"ok": False, "error": "use POST"})
                    return
                self._reply(404, {"ok": False, "error": "not found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/queue":
                    self._reply(404, {"ok": False, "error": "not found"})
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._reply(400, {"ok": False, "error": "bad content-length"})
                    return
                if length <= 0 or length > _MAX_BODY_BYTES:
                    self._reply(400, {"ok": False, "error": "bad payload size"})
                    return

                raw = self.rfile.read(length)
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._reply(400, {"ok": False, "error": "invalid json"})
                    return
                if not isinstance(data, dict):
                    self._reply(400, {"ok": False, "error": "invalid json"})
                    return

                token = server._extract_bearer_token(
                    self.headers.get("Authorization", "")
                )
                if not token and isinstance(data.get("token"), str):
                    token = data["token"]

                if not server.token or not secrets.compare_digest(token, server.token):
                    self._reply(403, {"ok": False, "error": "bad token"})
                    return

                url = data.get("url")
                if not isinstance(url, str):
                    self._reply(400, {"ok": False, "error": "bad url"})
                    return
                url = url.strip()
                if not url.startswith(("http://", "https://")):
                    self._reply(400, {"ok": False, "error": "bad url"})
                    return

                server.url_received.emit(url)
                self._reply(200, {"ok": True, "queued": url})

            def _reply(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # silence
                pass

        try:
            httpd = _LocalThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as exc:
            self.status_changed.emit(f"Failed to bind port {self.port}: {exc}")
            return
        httpd.api_server = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self.status_changed.emit(f"Listening on 127.0.0.1:{self.port}")
        try:
            if not self._stop_requested.is_set():
                httpd.serve_forever()
        finally:
            self._httpd = None
            httpd.server_close()

    def stop(self) -> None:
        self._stop_requested.set()
        httpd = self._httpd
        if httpd is not None:
            httpd.shutdown()


def make_token() -> str:
    return secrets.token_urlsafe(24)