"""Tests for http_.py: _safe_join, request handler, auth, auto-rename, base64, logging, one-shot."""

import base64
import os
import threading
import urllib.request
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from exchanger.http_ import (
    _safe_join,
    _auto_rename,
    _parse_multipart,
    ExchangeHTTPServer,
    ExchangeHTTPRequestHandler,
    serve_http,
)


def _handler_with_dir(directory):
    def handler(*args, **kwargs):
        return ExchangeHTTPRequestHandler(*args, directory=directory, **kwargs)
    return handler


@pytest.fixture
def _http_server(tmp_path):
    """Fixture that yields (server, port, tmp_path) and handles cleanup."""
    server = ExchangeHTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    yield server, port, tmp_path
    server.shutdown()
    server.server_close()


@pytest.fixture
def _auth_server(tmp_path):
    """Server with basic auth enabled."""
    server = ExchangeHTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    server.auth_credentials = "admin:secret"
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    yield server, port, tmp_path
    server.shutdown()
    server.server_close()


@pytest.fixture
def _b64_server(tmp_path):
    """Server with base64 decode enabled."""
    server = ExchangeHTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    server.decode_uploads = "base64"
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    yield server, port, tmp_path
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------
# _safe_join tests
# ---------------------------------------------------------------------------

def test_safe_join_under_base():
    base = "/tmp/root"
    full = _safe_join(base, "a/b.txt")
    assert full is not None
    assert full.endswith("a/b.txt") or "b.txt" in full
    assert full.startswith(os.path.realpath(base))


def test_safe_join_escape_returns_none():
    assert _safe_join("/tmp/root", "../../etc/passwd") is None


def test_safe_join_leading_slash_stripped():
    full = _safe_join("/tmp/root", "/a/b")
    assert full is not None
    assert "a" in full and "b" in full


def test_safe_join_symlink_escape_returns_none(tmp_path):
    base = tmp_path / "root"
    base.mkdir()
    (base / "legit.txt").write_text("ok")
    (base / "escape").symlink_to("/etc")
    assert _safe_join(str(base), "escape/passwd") is None


def test_safe_join_base_itself():
    assert _safe_join("/tmp", "/") is not None


# ---------------------------------------------------------------------------
# _auto_rename tests
# ---------------------------------------------------------------------------

def test_auto_rename_no_collision(tmp_path):
    path = str(tmp_path / "newfile.txt")
    assert _auto_rename(path) == path


def test_auto_rename_with_collision(tmp_path):
    f = tmp_path / "exists.txt"
    f.write_text("x")
    result = _auto_rename(str(f))
    assert result == str(f) + ".1"


def test_auto_rename_multiple_collisions(tmp_path):
    f = tmp_path / "exists.txt"
    f.write_text("x")
    (tmp_path / "exists.txt.1").write_text("x")
    (tmp_path / "exists.txt.2").write_text("x")
    result = _auto_rename(str(f))
    assert result == str(f) + ".3"


# ---------------------------------------------------------------------------
# _parse_multipart tests
# ---------------------------------------------------------------------------

def test_parse_multipart_single_file():
    boundary = b"----bound"
    body = (
        b"------bound\r\n"
        b'Content-Disposition: form-data; name="file"; filename="x.txt"\r\n\r\n'
        b"filecontent\r\n"
        b"------bound--\r\n"
    )
    out = _parse_multipart(body, boundary)
    assert out["file"] == b"filecontent"


def test_parse_multipart_empty():
    out = _parse_multipart(b"--b--\r\n", b"b")
    assert isinstance(out, dict)


# ---------------------------------------------------------------------------
# Basic GET/POST tests
# ---------------------------------------------------------------------------

def test_handler_get_root_returns_200(_http_server):
    _, port, _ = _http_server
    req = urllib.request.Request(f"http://127.0.0.1:{port}/")
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 200
        assert "exchanger" in r.read().decode()


def test_handler_get_missing_file_returns_404(_http_server):
    _, port, _ = _http_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/nonexistent", timeout=2)
    assert exc.value.code == 404


def test_handler_get_existing_file_returns_200(_http_server):
    _, port, tmp_path = _http_server
    (tmp_path / "hello.txt").write_text("hello world")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/hello.txt", timeout=2) as r:
        assert r.status == 200
        assert r.read() == b"hello world"


def test_handler_get_path_traversal_returns_403(_http_server):
    _, port, _ = _http_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/../etc/passwd", timeout=2)
    assert exc.value.code == 403


def test_handler_get_with_query_string(_http_server):
    _, port, tmp_path = _http_server
    (tmp_path / "qfile.txt").write_text("query test")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/qfile.txt?v=1&cache=no", timeout=2) as r:
        assert r.status == 200
        assert r.read() == b"query test"


def test_handler_post_raw_body_returns_201(_http_server):
    _, port, tmp_path = _http_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/uploaded.bin",
        data=b"binary content",
        method="POST",
        headers={"Content-Length": "14"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201
    assert (tmp_path / "uploaded.bin").read_bytes() == b"binary content"


def test_handler_post_empty_file_returns_201(_http_server):
    _, port, tmp_path = _http_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/empty.bin",
        data=b"",
        method="POST",
        headers={"Content-Length": "0"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201
    assert (tmp_path / "empty.bin").read_bytes() == b""


def test_handler_post_unicode_filename_returns_201(_http_server):
    _, port, tmp_path = _http_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/%E4%B8%AD%E6%96%87.txt",
        data=b"unicode test",
        method="POST",
        headers={"Content-Length": "12"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201
    assert (tmp_path / "\u4e2d\u6587.txt").read_bytes() == b"unicode test"


def test_handler_post_multipart_upload(_http_server):
    _, port, tmp_path = _http_server
    boundary = "----TestBoundary123"
    body = (
        f"------TestBoundary123\r\n"
        f'Content-Disposition: form-data; name="file"; filename="multi.txt"\r\n\r\n'
        f"multipart content\r\n"
        f"------TestBoundary123--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/multi.txt",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201


def test_handler_post_no_content_length_returns_411(_http_server):
    _, port, _ = _http_server
    import socket
    sock = socket.create_connection(("127.0.0.1", port), timeout=2)
    sock.sendall(b"POST /test.bin HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    resp = sock.recv(4096).decode()
    sock.close()
    assert "411" in resp


# ---------------------------------------------------------------------------
# Auto-rename on collision
# ---------------------------------------------------------------------------

def test_handler_post_auto_renames_on_collision(_http_server):
    _, port, tmp_path = _http_server
    (tmp_path / "dup.bin").write_text("original")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/dup.bin",
        data=b"new content",
        method="POST",
        headers={"Content-Length": "11"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201
        body = r.read().decode()
        assert "dup.bin.1" in body
    # Original untouched
    assert (tmp_path / "dup.bin").read_text() == "original"
    assert (tmp_path / "dup.bin.1").read_bytes() == b"new content"


# ---------------------------------------------------------------------------
# Basic auth tests
# ---------------------------------------------------------------------------

def test_auth_server_rejects_no_credentials(_auth_server):
    _, port, _ = _auth_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
    assert exc.value.code == 401


def test_auth_server_rejects_wrong_credentials(_auth_server):
    _, port, _ = _auth_server
    creds = base64.b64encode(b"wrong:creds").decode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        headers={"Authorization": f"Basic {creds}"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2)
    assert exc.value.code == 401


def test_auth_server_accepts_correct_credentials(_auth_server):
    _, port, _ = _auth_server
    creds = base64.b64encode(b"admin:secret").decode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        headers={"Authorization": f"Basic {creds}"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 200


def test_auth_server_post_with_credentials(_auth_server):
    _, port, tmp_path = _auth_server
    creds = base64.b64encode(b"admin:secret").decode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/authfile.txt",
        data=b"authenticated upload",
        method="POST",
        headers={"Authorization": f"Basic {creds}", "Content-Length": "20"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201
    assert (tmp_path / "authfile.txt").read_bytes() == b"authenticated upload"


# ---------------------------------------------------------------------------
# Base64 decode on upload
# ---------------------------------------------------------------------------

def test_b64_server_decodes_upload(_b64_server):
    _, port, tmp_path = _b64_server
    payload = base64.b64encode(b"decoded content")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/b64file.bin",
        data=payload,
        method="POST",
        headers={"Content-Length": str(len(payload))},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201
    assert (tmp_path / "b64file.bin").read_bytes() == b"decoded content"


def test_b64_server_rejects_invalid_base64(_b64_server):
    _, port, _ = _b64_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/bad.bin",
        data=b"not-valid-base64!!!",
        method="POST",
        headers={"Content-Length": "19"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2)
    assert exc.value.code == 400


# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------

def test_logging_to_file(tmp_path):
    log_file = str(tmp_path / "requests.log")
    server = ExchangeHTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    server.log_file = log_file
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
        with open(log_file) as f:
            log_content = f.read()
        assert "GET" in log_content
        assert "127.0.0.1" in log_content
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# One-shot mode
# ---------------------------------------------------------------------------

def test_one_shot_server_exits_after_post(tmp_path):
    server = ExchangeHTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    server.one_shot = True
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/oneshot.bin",
        data=b"oneshot data",
        method="POST",
        headers={"Content-Length": "12"},
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        assert r.status == 201
    # Server should have shut down — wait briefly then verify thread exits
    t.join(timeout=3)
    assert not t.is_alive()


# ---------------------------------------------------------------------------
# serve_http exits
# ---------------------------------------------------------------------------

def test_serve_http_nonexistent_dir_exits():
    from argparse import Namespace
    args = Namespace(dir="/nonexistent_dir_xyz_12345", port=0, bind="127.0.0.1", protocol="http")
    with pytest.raises(SystemExit) as exc:
        serve_http(args)
    assert exc.value.code != 0


def test_serve_http_unreadable_dir_exits(tmp_path):
    unreadable = tmp_path / "noperm"
    unreadable.mkdir()
    unreadable.chmod(0o000)
    from argparse import Namespace
    args = Namespace(dir=str(unreadable), port=0, bind="127.0.0.1", protocol="http")
    try:
        with pytest.raises(SystemExit) as exc:
            serve_http(args)
        assert exc.value.code != 0
    finally:
        unreadable.chmod(0o755)


def test_serve_http_port_443_no_certs_exits(tmp_path):
    from argparse import Namespace
    args = Namespace(dir=str(tmp_path), port=443, bind="127.0.0.1", protocol="http",
                     one_shot=False, auth=None, encode=None, log=None,
                     obfuscate=False, proxy=None, clipboard=False, qr=False)
    mock_server = MagicMock()
    mock_server.socket = MagicMock()
    with patch("exchanger.http_.ExchangeHTTPServer", return_value=mock_server):
        with patch("exchanger.http_.ssl.SSLContext") as mock_ctx:
            mock_ctx.return_value.load_cert_chain.side_effect = FileNotFoundError
            with pytest.raises(SystemExit) as exc:
                serve_http(args)
    assert exc.value.code == 1
