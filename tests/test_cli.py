"""CLI argument parsing and command dispatch."""

import sys
from io import StringIO
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
    assert getattr(args, "obfuscate", False) is False


def test_parser_serve_full_options():
    parser = build_parser()
    args = parser.parse_args(
        ["serve", "-p", "8080", "-d", "/tmp", "--bind", "127.0.0.1", "-o"]
    )
    assert args.port == 8080
    assert args.dir == "/tmp"
    assert args.bind == "127.0.0.1"
    assert args.obfuscate is True


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
    # Message is printed to stderr
    assert "receive" in str(exc.value).lower() or "http" in str(exc.value).lower()


def test_serve_protocol_smb_exits_with_message():
    parser = build_parser()
    args = parser.parse_args(["serve", "--protocol", "smb"])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    assert exc.value.code != 0


def test_cli_entry_point_help():
    """Ensure the CLI entry point runs and --help exits 0."""
    with pytest.raises(SystemExit) as exc:
        with patch.object(sys, "argv", ["exchanger", "--help"]):
            main()
    assert exc.value.code == 0
