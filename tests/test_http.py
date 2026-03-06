"""Tests for http_.py: _safe_join, request handler behavior, serve_http exit."""

import os
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest

from exchanger.http_ import (
    _safe_join,
    _parse_multipart,
    ExchangeHTTPRequestHandler,
    serve_http,
)


def test_safe_join_under_base():
    base = "/tmp/root"
    path = "a/b.txt"
    full = _safe_join(base, path)
    assert full is not None
    assert full.endswith("a/b.txt") or "b.txt" in full
    assert full.startswith(os.path.abspath(base))


def test_safe_join_escape_returns_none():
    base = "/tmp/root"
    path = "../../etc/passwd"
    full = _safe_join(base, path)
    assert full is None


def test_safe_join_leading_slash_stripped():
    base = "/tmp/root"
    path = "/a/b"
    full = _safe_join(base, path)
    assert full is not None
    assert "a" in full and "b" in full


def test_parse_multipart_single_file():
    boundary = b"----bound"
    body = (
        b"------bound\r\n"
        b'Content-Disposition: form-data; name="file"; filename="x.txt"\r\n\r\n'
        b"filecontent\r\n"
        b"------bound--\r\n"
    )
    out = _parse_multipart(body, boundary)
    assert "file" in out
    assert out["file"] == b"filecontent"


def test_parse_multipart_empty():
    out = _parse_multipart(b"--b--\r\n", b"b")
    assert isinstance(out, dict)


def _handler_with_dir(directory):
    def handler(*args, **kwargs):
        return ExchangeHTTPRequestHandler(*args, directory=directory, **kwargs)
    return handler


def test_handler_get_root_returns_200(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    port = server.server_address[1]
    try:
        t = threading.Thread(target=server.serve_forever)
        t.daemon = True
        t.start()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req, timeout=2) as r:
            assert r.status == 200
            body = r.read().decode()
            assert "exchanger" in body or "GET" in body
    finally:
        server.shutdown()
        server.server_close()


def test_handler_get_missing_file_returns_404(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    port = server.server_address[1]
    try:
        t = threading.Thread(target=server.serve_forever)
        t.daemon = True
        t.start()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/nonexistent")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=2)
        assert exc.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_handler_get_existing_file_returns_200(tmp_path):
    (tmp_path / "hello.txt").write_text("hello world")
    server = HTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    port = server.server_address[1]
    try:
        t = threading.Thread(target=server.serve_forever)
        t.daemon = True
        t.start()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/hello.txt")
        with urllib.request.urlopen(req, timeout=2) as r:
            assert r.status == 200
            assert r.read() == b"hello world"
    finally:
        server.shutdown()
        server.server_close()


def test_handler_get_path_traversal_returns_403(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    port = server.server_address[1]
    try:
        t = threading.Thread(target=server.serve_forever)
        t.daemon = True
        t.start()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/../etc/passwd")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=2)
        assert exc.value.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_serve_http_nonexistent_dir_exits():
    from argparse import Namespace
    args = Namespace(dir="/nonexistent_dir_xyz_12345", port=0, bind="127.0.0.1", protocol="http")
    with pytest.raises(SystemExit) as exc:
        serve_http(args)
    assert exc.value.code != 0


def test_serve_http_port_443_no_certs_exits(tmp_path):
    from argparse import Namespace
    args = Namespace(dir=str(tmp_path), port=443, bind="127.0.0.1", protocol="http")
    mock_server = MagicMock()
    mock_server.socket = MagicMock()
    with patch("exchanger.http_.http.server.HTTPServer", return_value=mock_server):
        with patch("exchanger.http_.ssl.SSLContext") as mock_ctx:
            mock_ctx.return_value.load_cert_chain.side_effect = FileNotFoundError
            with pytest.raises(SystemExit) as exc:
                serve_http(args)
    assert exc.value.code == 1


def test_handler_post_raw_body_returns_201(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    port = server.server_address[1]
    try:
        t = threading.Thread(target=server.serve_forever)
        t.daemon = True
        t.start()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/uploaded.bin",
            data=b"binary content",
            method="POST",
            headers={"Content-Length": "14"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            assert r.status == 201
        assert (tmp_path / "uploaded.bin").read_bytes() == b"binary content"
    finally:
        server.shutdown()
        server.server_close()
