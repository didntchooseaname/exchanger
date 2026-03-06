"""Tests for net_.py: URL building, target commands, print_commands_serve."""

import io
import sys
from unittest.mock import patch

import pytest

from exchanger import net_


def test_base_url_port_80():
    assert net_._base_url("192.168.1.1", 80) == "http://192.168.1.1"


def test_base_url_port_443():
    assert net_._base_url("10.0.0.1", 443) == "https://10.0.0.1"


def test_base_url_custom_port():
    assert net_._base_url("192.168.1.1", 8080) == "http://192.168.1.1:8080"


def test_port_proto():
    port_opt, proto_opt = net_._port_proto(80, "http")
    assert port_opt == ""
    assert proto_opt == ""
    port_opt, proto_opt = net_._port_proto(8080, "http")
    assert "8080" in port_opt
    assert proto_opt == ""


def test_target_receive_linux():
    base = "http://192.168.1.1:80"
    out = net_._target_receive_linux(base, "/script.sh", "/tmp/script.sh")
    assert "curl -o /tmp/script.sh" in out
    assert "wget -O /tmp/script.sh" in out
    assert "/dev/tcp/" in out
    assert base in out or "192.168.1.1" in out


def test_target_receive_win():
    base = "http://192.168.1.1:80"
    out = net_._target_receive_win(base, "/x", "out")
    assert "curl -o out" in out
    assert "wget -O out" in out
    assert "certutil" in out
    assert "iwr" in out or "Invoke-WebRequest" in out
    assert "bitsadmin" in out
    assert "192.168.1.1" in out


def test_target_send_linux():
    base = "http://10.0.0.1:8080"
    out = net_._target_send_linux(base, "./f", "f")
    assert "curl -X POST" in out
    assert "--data-binary" in out
    assert "10.0.0.1" in out


def test_target_send_win():
    base = "http://10.0.0.1"
    out = net_._target_send_win(base, "file", "file")
    assert "curl -X POST" in out
    assert "10.0.0.1" in out


def test_target_inmemory_linux():
    base = "http://192.168.1.1/path"
    lines = net_._target_inmemory_linux(base, "/script.sh")
    assert len(lines) >= 1
    assert any("curl" in l and "bash" in l for l in lines)
    assert any("wget" in l and "bash" in l for l in lines)
    assert "192.168.1.1" in lines[0]


def test_target_inmemory_win():
    base = "http://192.168.1.1"
    lines = net_._target_inmemory_win(base, "/x.ps1")
    assert len(lines) >= 1
    assert any("iex" in l or "Invoke-Expression" in l for l in lines)
    assert any("WebClient" in l or "iwr" in l for l in lines)


def test_get_serve_base_returns_none_when_protocol_not_http():
    with patch.object(net_, "pick_platform", return_value="windows"):
        with patch.object(net_, "pick_interface", return_value="127.0.0.1"):
            base, platform = net_.get_serve_base(80, protocol="smb")
    assert base is None
    assert platform is None


def test_print_commands_serve_none_base_returns_none_none():
    result = net_.print_commands_serve(80, _base=None, _platform="linux")
    assert result == (None, None)


def test_print_commands_serve_linux_prints_sections(capsys):
    base = "http://192.168.1.1:80"
    net_.print_commands_serve(
        80,
        _base=base,
        _platform="linux",
        serve_path=None,
        obfuscate=False,
    )
    captured = capsys.readouterr()
    assert "GNU/Linux" in captured.err
    assert "curl" in captured.err or "wget" in captured.err
    assert "192.168.1.1" in captured.err


def test_print_commands_serve_windows_prints_sections(capsys):
    base = "http://192.168.1.1:80"
    net_.print_commands_serve(
        80,
        _base=base,
        _platform="windows",
        serve_path=None,
        obfuscate=False,
    )
    captured = capsys.readouterr()
    assert "Windows" in captured.err
    assert "iwr" in captured.err or "certutil" in captured.err


def test_print_commands_serve_obfuscate_writes_to_stdout(capsys):
    base = "http://192.168.1.1:80"
    net_.print_commands_serve(
        80,
        _base=base,
        _platform="linux",
        serve_path=None,
        obfuscate=True,
    )
    captured = capsys.readouterr()
    assert "curl" in captured.out or "wget" in captured.out or "bash" in captured.out
    assert "GNU/Linux" in captured.err


def test_print_commands_serve_with_serve_path(capsys):
    base = "http://10.0.0.1"
    net_.print_commands_serve(
        80,
        _base=base,
        _platform="linux",
        serve_path="dir/payload.bin",
        obfuscate=False,
    )
    captured = capsys.readouterr()
    assert "payload.bin" in captured.err or "dir" in captured.err


def test_pick_interface_menu_returns_selected():
    choices = [("eth0", "192.168.1.1"), ("eth1", "10.0.0.1")]
    with patch("builtins.input", return_value="2"):
        result = net_._pick_interface_menu(choices)
    assert result == "10.0.0.1"


def test_pick_interface_menu_invalid_returns_none():
    choices = [("eth0", "192.168.1.1")]
    with patch("builtins.input", return_value="99"):
        result = net_._pick_interface_menu(choices)
    assert result is None


def test_get_local_ip_empty_interfaces():
    with patch.object(net_, "get_all_interfaces", return_value=[]):
        assert net_.get_local_ip() is None


def test_get_local_ip_prefers_tun0():
    with patch.object(
        net_, "get_all_interfaces", return_value=[("eth0", "192.168.1.1"), ("tun0", "10.8.0.1")]
    ):
        assert net_.get_local_ip() == "10.8.0.1"


def test_get_local_ip_first_otherwise():
    with patch.object(
        net_, "get_all_interfaces", return_value=[("eth0", "192.168.1.1")]
    ):
        assert net_.get_local_ip() == "192.168.1.1"


def test_pick_file_to_serve_empty_dir(tmp_path):
    assert net_.pick_file_to_serve(str(tmp_path)) is None


def test_pick_file_to_serve_returns_file_when_single(tmp_path):
    (tmp_path / "only.txt").write_text("x")
    with patch("exchanger.net_.subprocess.run") as run:
        run.return_value = type("R", (), {"returncode": 0, "stdout": "only.txt\n"})()
        result = net_.pick_file_to_serve(str(tmp_path))
    assert result == "only.txt"
