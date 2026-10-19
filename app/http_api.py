"""Optional localhost helper API for browser extensions.

A tiny HTTP server that runs in a background QThread and exposes two
endpoints:

    GET /health            -> {"ok": true}
    GET /queue?url=...&token=...  -> queues the URL in the downloader

The token is per-installation (stored in QSettings) and must be supplied by
the caller, so a random web page cannot silently push URLs into the queue.
Everything binds to 127.0.0.1 only.
"""

from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QThread, Signal


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

    def run(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._reply(200, {"ok": True})
                    return
                if parsed.path == "/queue":
                    qs = parse_qs(parsed.query)
                    token = (qs.get("token") or [""])[0]
                    url = (qs.get("url") or [""])[0]
                    if token != server.token:
                        self._reply(403, {"ok": False, "error": "bad token"})
                        return
                    if not url.startswith(("http://", "https://")):
                        self._reply(400, {"ok": False, "error": "bad url"})
                        return
                    server.url_received.emit(url)
                    self._reply(200, {"ok": True, "queued": url})
                    return
                self._reply(404, {"ok": False, "error": "not found"})

            def _reply(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # silence
                pass

        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as exc:
            self.status_changed.emit(f"Failed to bind port {self.port}: {exc}")
            return
        httpd.api_server = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self.status_changed.emit(f"Listening on 127.0.0.1:{self.port}")
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()

    def stop(self) -> None:
        httpd = self._httpd
        if httpd is not None:
            httpd.shutdown()


def make_token() -> str:
    return secrets.token_urlsafe(24)