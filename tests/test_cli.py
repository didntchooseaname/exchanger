"""CLI argument parsing and command dispatch."""

import sys
from unittest.mock import patch

import pytest

from exchanger.cli import build_parser, main


def test_parser_serve_has_obfuscate():
    parser = build_parser()
    args = parser.parse_args(["serve", "-o"])
    assert args.command == "serve"
    assert args.obfuscate is True


def test_parser_serve_defaults():
    parser = build_parser()
    args = parser.parse_args(["serve"])
    assert args.command == "serve"
    assert args.port == 80
    assert args.dir == "."
    assert args.bind == "0.0.0.0"
    assert args.protocol == "http"
    assert args.obfuscate is False
    assert args.one_shot is False
    assert args.auth is None
    assert args.log is None
    assert args.proxy is None
    assert args.clipboard is False
    assert args.qr is False


def test_parser_serve_full_options():
    parser = build_parser()
    args = parser.parse_args(
        ["serve", "-p", "8080", "-d", "/tmp", "--bind", "127.0.0.1", "-o",
         "--one-shot", "--auth", "admin:pass", "--log", "/tmp/req.log",
         "--proxy", "socks5://127.0.0.1:1080", "-c", "-q"]
    )
    assert args.port == 8080
    assert args.dir == "/tmp"
    assert args.bind == "127.0.0.1"
    assert args.obfuscate is True
    assert args.one_shot is True
    assert args.auth == "admin:pass"
    assert args.log == "/tmp/req.log"
    assert args.proxy == "socks5://127.0.0.1:1080"
    assert args.clipboard is True
    assert args.qr is True


def test_parser_receive_has_obfuscate():
    parser = build_parser()
    args = parser.parse_args(["receive", "-o"])
    assert args.command == "receive"
    assert args.obfuscate is True


def test_parser_receive_defaults():
    parser = build_parser()
    args = parser.parse_args(["receive"])
    assert args.command == "receive"
    assert args.port == 80
    assert args.dir == "."


def test_parser_receive_encode():
    parser = build_parser()
    args = parser.parse_args(["receive", "--encode", "base64"])
    assert args.encode == "base64"


def test_parser_push():
    parser = build_parser()
    args = parser.parse_args(["push", "myfile.bin", "10.0.0.1:8080"])
    assert args.command == "push"
    assert args.file == "myfile.bin"
    assert args.target == "10.0.0.1:8080"


def test_parser_push_with_encode():
    parser = build_parser()
    args = parser.parse_args(["push", "myfile.bin", "10.0.0.1:8080", "--encode", "base64"])
    assert args.encode == "base64"


def test_parser_help_exits_zero():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_receive_protocol_smb_exits_with_message():
    parser = build_parser()
    args = parser.parse_args(["receive", "--protocol", "smb"])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    assert exc.value.code != 0
    assert "receive" in str(exc.value).lower() or "http" in str(exc.value).lower()


def test_serve_protocol_smb_exits_with_message():
    parser = build_parser()
    args = parser.parse_args(["serve", "--protocol", "smb"])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    assert exc.value.code != 0


def test_cli_entry_point_help():
    with pytest.raises(SystemExit) as exc:
        with patch.object(sys, "argv", ["exchanger", "--help"]):
            main()
    assert exc.value.code == 0
