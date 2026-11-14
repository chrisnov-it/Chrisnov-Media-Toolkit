"""Tests for app.http_api — localhost helper API security and routing."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
from PySide6.QtCore import Qt

from app.http_api import LocalApiServer, make_token


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture()
def api_server():
    token = make_token()
    port = _free_port()
    server = LocalApiServer(token=token, port=port)
    ready = threading.Event()
    server.status_changed.connect(
        lambda _msg: ready.set(), Qt.ConnectionType.DirectConnection
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    assert ready.wait(timeout=3.0), "LocalApiServer did not start in time"
    # Give serve_forever() a brief moment to enter its loop after status_changed.
    time.sleep(0.05)
    try:
        yield server, f"http://127.0.0.1:{port}", token
    finally:
        server.stop()
        thread.join(timeout=2.0)


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict | bytes | None = None,
) -> tuple[int, dict[str, str], dict]:
    data = None
    req_headers = dict(headers or {})
    if isinstance(body, dict):
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, bytes):
        data = body
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, dict(resp.headers.items()), json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers.items()), json.loads(err.read())


def test_health_has_no_wildcard_cors(api_server):
    _server, base, _token = api_server
    code, headers, body = _request(f"{base}/health")
    assert code == 200
    assert body == {"ok": True}
    lower_headers = {k.lower(): v for k, v in headers.items()}
    assert "access-control-allow-origin" not in lower_headers


def test_get_queue_is_rejected(api_server):
    _server, base, token = api_server
    code, _headers, body = _request(
        f"{base}/queue?url=https://example.com&token={token}"
    )
    assert code == 405
    assert body["ok"] is False


def test_post_queue_accepts_bearer_token(api_server):
    server, base, token = api_server
    received: list[str] = []
    server.url_received.connect(
        received.append, Qt.ConnectionType.DirectConnection
    )

    code, _headers, body = _request(
        f"{base}/queue",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        body={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert code == 200
    assert body == {
        "ok": True,
        "queued": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }
    assert received == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]


def test_post_queue_rejects_bad_token(api_server):
    server, base, _token = api_server
    received: list[str] = []
    server.url_received.connect(
        received.append, Qt.ConnectionType.DirectConnection
    )

    code, _headers, body = _request(
        f"{base}/queue",
        method="POST",
        headers={"Authorization": "Bearer wrong-token"},
        body={"url": "https://example.com"},
    )
    assert code == 403
    assert body["ok"] is False
    assert received == []


def test_post_queue_rejects_non_http_url(api_server):
    server, base, token = api_server
    received: list[str] = []
    server.url_received.connect(
        received.append, Qt.ConnectionType.DirectConnection
    )

    code, _headers, body = _request(
        f"{base}/queue",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        body={"url": "file:///etc/passwd"},
    )
    assert code == 400
    assert body["ok"] is False
    assert received == []


def test_post_queue_rejects_invalid_json(api_server):
    _server, base, token = api_server
    code, _headers, body = _request(
        f"{base}/queue",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        body=b"{not-json",
    )
    assert code == 400
    assert body["ok"] is False
