"""Tests for push_.py: push file to listening target."""

import base64
import os
import threading
import urllib.request
from argparse import Namespace
from http.server import HTTPServer

import pytest

from exchanger.http_ import ExchangeHTTPServer, ExchangeHTTPRequestHandler
from exchanger.push_ import push_file


def _handler_with_dir(directory):
    def handler(*args, **kwargs):
        return ExchangeHTTPRequestHandler(*args, directory=directory, **kwargs)
    return handler


@pytest.fixture
def _target_server(tmp_path):
    server = ExchangeHTTPServer(("127.0.0.1", 0), _handler_with_dir(str(tmp_path)))
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    yield server, port, tmp_path
    server.shutdown()
    server.server_close()


def test_push_file_success(tmp_path, _target_server):
    _, port, target_dir = _target_server
    src = tmp_path / "payload.bin"
    src.write_bytes(b"push content")
    args = Namespace(file=str(src), target=f"127.0.0.1:{port}", encode=None)
    push_file(args)
    assert (target_dir / "payload.bin").read_bytes() == b"push content"


def test_push_file_with_base64_encode(tmp_path, _target_server):
    _, port, target_dir = _target_server
    # Use a separate dir for the source so it doesn't collide with target
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "b64push.bin"
    src.write_bytes(b"raw data")
    args = Namespace(file=str(src), target=f"127.0.0.1:{port}", encode="base64")
    push_file(args)
    # Server receives base64, doesn't decode (no decode_uploads set)
    received = (target_dir / "b64push.bin").read_bytes()
    assert base64.b64decode(received) == b"raw data"


def test_push_file_not_found(tmp_path):
    args = Namespace(file="/nonexistent/file.bin", target="127.0.0.1:9999", encode=None)
    with pytest.raises(SystemExit):
        push_file(args)


def test_push_file_connection_refused(tmp_path):
    src = tmp_path / "test.bin"
    src.write_bytes(b"data")
    args = Namespace(file=str(src), target="127.0.0.1:1", encode=None)
    with pytest.raises(SystemExit):
        push_file(args)
