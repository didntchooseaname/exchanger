"""Tests for net_.py: URL building, target commands, auth, proxy, checksum, DNS, chunked, WebDAV, clipboard."""

import io
import sys
from unittest.mock import patch

import pytest

from exchanger import net_


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

def test_base_url_port_80():
    assert net_._base_url("192.168.1.1", 80) == "http://192.168.1.1"


def test_base_url_port_443():
    assert net_._base_url("10.0.0.1", 443) == "https://10.0.0.1"


def test_base_url_custom_port():
    assert net_._base_url("192.168.1.1", 8080) == "http://192.168.1.1:8080"


def test_base_url_ipv6():
    assert net_._base_url("::1", 80) == "http://[::1]"


def test_base_url_ipv6_custom_port():
    assert net_._base_url("fd00::1", 8080) == "http://[fd00::1]:8080"


def test_port_proto():
    port_opt, proto_opt = net_._port_proto(80, "http")
    assert port_opt == ""
    assert proto_opt == ""
    port_opt, proto_opt = net_._port_proto(8080, "http")
    assert "8080" in port_opt
    assert proto_opt == ""


# ---------------------------------------------------------------------------
# Target receive commands
# ---------------------------------------------------------------------------

def test_target_receive_linux():
    base = "http://192.168.1.1:80"
    out = net_._target_receive_linux(base, "/script.sh", "/tmp/script.sh")
    assert "curl -o /tmp/script.sh" in out
    assert "wget -O /tmp/script.sh" in out
    assert "/dev/tcp/" in out


def test_target_receive_linux_with_auth():
    out = net_._target_receive_linux("http://10.0.0.1", "/x", "/tmp/x", auth="user:pass")
    assert "-u user:pass" in out
    assert "--user=user" in out


def test_target_receive_linux_with_proxy():
    out = net_._target_receive_linux("http://10.0.0.1", "/x", "/tmp/x", proxy="socks5://127.0.0.1:1080")
    assert "--proxy socks5://127.0.0.1:1080" in out


def test_target_receive_win():
    base = "http://192.168.1.1:80"
    out = net_._target_receive_win(base, "/x", "out")
    assert "curl -o out" in out
    assert "certutil" in out
    assert "iwr" in out
    assert "bitsadmin" in out


def test_target_receive_win_with_auth():
    out = net_._target_receive_win("http://10.0.0.1", "/x", "out", auth="admin:secret")
    assert "-u admin:secret" in out
    assert "Authorization" in out  # PS headers


def test_target_receive_win_with_proxy():
    out = net_._target_receive_win("http://10.0.0.1", "/x", "out", proxy="http://proxy:8080")
    assert "--proxy http://proxy:8080" in out
    assert '-Proxy "http://proxy:8080"' in out


# ---------------------------------------------------------------------------
# LOLBAS/GTFOBins receive
# ---------------------------------------------------------------------------

def test_target_receive_linux_lolbins():
    cmds = net_._target_receive_linux_lolbins("http://10.0.0.1", "/x", "/tmp/x")
    texts = "\n".join(cmds)
    assert "python3" in texts
    assert "perl" in texts
    assert "ruby" in texts
    assert "php" in texts
    assert "lwp-download" in texts
    assert "socat" in texts
    assert "tftp" in texts
    assert len(cmds) >= 8


def test_target_receive_win_lolbas():
    cmds = net_._target_receive_win_lolbas("http://10.0.0.1", "/x", "out")
    texts = "\n".join(cmds)
    assert "DownloadFile" in texts
    assert "Start-BitsTransfer" in texts
    assert "mshta" in texts
    assert "regsvr32" in texts
    assert "msiexec" in texts
    assert "hh.exe" in texts
    assert "esentutl" in texts
    assert "findstr" in texts
    assert "replace" in texts
    assert "cscript" in texts
    assert len(cmds) >= 10


# ---------------------------------------------------------------------------
# Target send commands
# ---------------------------------------------------------------------------

def test_target_send_linux():
    out = net_._target_send_linux("http://10.0.0.1:8080", "./f", "f")
    assert "curl -X POST" in out
    assert "--data-binary" in out


def test_target_send_linux_with_auth_proxy():
    out = net_._target_send_linux("http://10.0.0.1", auth="u:p", proxy="socks5://x:1080")
    assert "-u u:p" in out
    assert "--proxy socks5://x:1080" in out


def test_target_send_win():
    out = net_._target_send_win("http://10.0.0.1", "file", "file")
    assert "curl -X POST" in out


# ---------------------------------------------------------------------------
# LOLBAS/GTFOBins send
# ---------------------------------------------------------------------------

def test_target_send_linux_lolbins():
    cmds = net_._target_send_linux_lolbins("http://10.0.0.1", "./f", "f")
    texts = "\n".join(cmds)
    assert "nc" in texts
    assert "python3" in texts
    assert "socat" in texts
    assert len(cmds) >= 3


def test_target_send_win_lolbas():
    cmds = net_._target_send_win_lolbas("http://10.0.0.1", "f", "f")
    texts = "\n".join(cmds)
    assert "UploadFile" in texts
    assert "UploadData" in texts
    assert "iwr" in texts and "POST" in texts
    assert len(cmds) >= 3


# ---------------------------------------------------------------------------
# In-memory execution
# ---------------------------------------------------------------------------

def test_target_inmemory_linux():
    lines = net_._target_inmemory_linux("http://192.168.1.1/path", "/script.sh")
    assert any("curl" in l and "bash" in l for l in lines)
    assert any("wget" in l and "bash" in l for l in lines)


def test_target_inmemory_linux_auth():
    lines = net_._target_inmemory_linux("http://10.0.0.1", "/x", auth="a:b")
    assert any("-u a:b" in l for l in lines)


def test_target_inmemory_win():
    lines = net_._target_inmemory_win("http://192.168.1.1", "/x.ps1")
    assert any("iex" in l for l in lines)
    assert any("WebClient" in l for l in lines)


def test_target_inmemory_win_auth_proxy():
    lines = net_._target_inmemory_win("http://10.0.0.1", "/x.ps1", auth="u:p", proxy="http://px:80")
    assert any("Authorization" in l for l in lines)
    assert any("Proxy" in l for l in lines)


# ---------------------------------------------------------------------------
# LOLBAS/GTFOBins in-memory
# ---------------------------------------------------------------------------

def test_target_inmemory_linux_lolbins():
    cmds = net_._target_inmemory_linux_lolbins("http://10.0.0.1", "/x.sh")
    texts = "\n".join(cmds)
    assert "python3" in texts and "exec" in texts
    assert "perl" in texts and "eval" in texts
    assert "ruby" in texts and "eval" in texts
    assert "php" in texts and "eval" in texts
    assert len(cmds) >= 4


def test_target_inmemory_win_lolbas():
    cmds = net_._target_inmemory_win_lolbas("http://10.0.0.1", "/x.ps1")
    texts = "\n".join(cmds)
    assert "mshta" in texts
    assert "rundll32" in texts
    assert "-enc" in texts
    assert "Reflection.Assembly" in texts
    assert len(cmds) >= 4


# ---------------------------------------------------------------------------
# Checksum commands
# ---------------------------------------------------------------------------

def test_checksum_commands_linux_with_hash():
    cmds = net_._checksum_commands_linux("/tmp/file", sha256="abc123")
    assert any("abc123" in c and "sha256sum" in c for c in cmds)


def test_checksum_commands_linux_without_hash():
    cmds = net_._checksum_commands_linux("/tmp/file")
    assert any("sha256sum" in c for c in cmds)


def test_checksum_commands_win_with_hash():
    cmds = net_._checksum_commands_win("file.bin", sha256="abc123")
    assert any("ABC123" in c and "Get-FileHash" in c for c in cmds)


def test_checksum_commands_win_without_hash():
    cmds = net_._checksum_commands_win("file.bin")
    assert any("Get-FileHash" in c for c in cmds)


def test_compute_sha256(tmp_path):
    f = tmp_path / "hashme.txt"
    f.write_text("hello")
    h = net_._compute_sha256(str(f))
    assert h is not None
    assert len(h) == 64  # hex sha256


def test_compute_sha256_missing_file():
    assert net_._compute_sha256("/nonexistent/path/xyz") is None


# ---------------------------------------------------------------------------
# DNS exfil commands
# ---------------------------------------------------------------------------

def test_dns_exfil_linux():
    cmds = net_._dns_exfil_linux("attacker.com", "./secret.txt")
    assert any("nslookup" in c and "attacker.com" in c for c in cmds)
    assert any("dig" in c and "attacker.com" in c for c in cmds)


def test_dns_exfil_win():
    cmds = net_._dns_exfil_win("attacker.com", "secret.txt")
    assert any("nslookup" in c and "attacker.com" in c for c in cmds)


# ---------------------------------------------------------------------------
# Chunked transfer commands
# ---------------------------------------------------------------------------

def test_chunked_send_linux():
    cmds = net_._chunked_send_linux("http://10.0.0.1", "./big.bin", chunk_size=4096)
    assert any("split" in c and "4096" in c for c in cmds)


def test_chunked_send_linux_with_auth():
    cmds = net_._chunked_send_linux("http://10.0.0.1", auth="u:p")
    assert any("-u u:p" in c for c in cmds)


def test_chunked_send_win():
    cmds = net_._chunked_send_win("http://10.0.0.1", "big.bin", chunk_size=8192)
    assert any("8192" in c for c in cmds)


# ---------------------------------------------------------------------------
# WebDAV commands
# ---------------------------------------------------------------------------

def test_webdav_commands_win():
    cmds = net_._webdav_commands_win("http://10.0.0.1:8080", "/payload.exe", "payload.exe")
    assert any("net use" in c for c in cmds)
    assert any("10.0.0.1" in c for c in cmds)
    assert any("DavWWWRoot" in c for c in cmds)


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def test_copy_to_clipboard_no_tool_available():
    with patch("exchanger.net_.subprocess.run", side_effect=FileNotFoundError):
        assert net_.copy_to_clipboard("test") is False


def test_copy_to_clipboard_success():
    with patch("exchanger.net_.subprocess.run") as mock_run:
        mock_run.return_value = None
        assert net_.copy_to_clipboard("test text") is True
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# print_commands_serve
# ---------------------------------------------------------------------------

def test_get_serve_base_returns_none_when_protocol_not_http():
    with patch.object(net_, "pick_platform", return_value="windows"):
        with patch.object(net_, "pick_interface", return_value="127.0.0.1"):
            base, platform = net_.get_serve_base(80, protocol="smb")
    assert base is None


def test_print_commands_serve_none_base_returns_none_none():
    result = net_.print_commands_serve(80, _base=None, _platform="linux")
    assert result == (None, None)


def test_print_commands_serve_linux_prints_sections(capsys):
    net_.print_commands_serve(80, _base="http://192.168.1.1:80", _platform="linux")
    captured = capsys.readouterr()
    assert "GNU/Linux" in captured.err
    assert "curl" in captured.err or "wget" in captured.err
    # New sections
    assert "DNS exfil" in captured.err
    assert "chunked" in captured.err


def test_print_commands_serve_windows_prints_sections(capsys):
    net_.print_commands_serve(80, _base="http://192.168.1.1:80", _platform="windows")
    captured = capsys.readouterr()
    assert "Windows" in captured.err
    assert "WebDAV" in captured.err
    assert "DNS exfil" in captured.err
    assert "chunked" in captured.err


def test_print_commands_serve_with_auth(capsys):
    net_.print_commands_serve(80, _base="http://10.0.0.1", _platform="linux", auth="u:p")
    captured = capsys.readouterr()
    assert "u:p" in captured.err


def test_print_commands_serve_obfuscate_writes_to_stdout(capsys):
    net_.print_commands_serve(80, _base="http://192.168.1.1:80", _platform="linux", obfuscate=True)
    captured = capsys.readouterr()
    assert "curl" in captured.out or "wget" in captured.out or "bash" in captured.out


def test_print_commands_serve_with_serve_path(capsys):
    net_.print_commands_serve(80, _base="http://10.0.0.1", _platform="linux", serve_path="dir/payload.bin")
    captured = capsys.readouterr()
    assert "payload.bin" in captured.err


# ---------------------------------------------------------------------------
# Interface/platform picking
# ---------------------------------------------------------------------------

def test_pick_interface_menu_returns_selected():
    choices = [("eth0", "192.168.1.1"), ("eth1", "10.0.0.1")]
    with patch("builtins.input", return_value="2"):
        assert net_._pick_interface_menu(choices) == "10.0.0.1"


def test_pick_interface_menu_invalid_returns_none():
    with patch("builtins.input", return_value="99"):
        assert net_._pick_interface_menu([("eth0", "192.168.1.1")]) is None


def test_get_local_ip_empty_interfaces():
    with patch.object(net_, "get_all_interfaces", return_value=[]):
        assert net_.get_local_ip() is None


def test_get_local_ip_prefers_tun0():
    with patch.object(net_, "get_all_interfaces", return_value=[("eth0", "192.168.1.1"), ("tun0", "10.8.0.1")]):
        assert net_.get_local_ip() == "10.8.0.1"


def test_get_local_ip_first_otherwise():
    with patch.object(net_, "get_all_interfaces", return_value=[("eth0", "192.168.1.1")]):
        assert net_.get_local_ip() == "192.168.1.1"


# ---------------------------------------------------------------------------
# File picker
# ---------------------------------------------------------------------------

def test_pick_file_to_serve_empty_dir(tmp_path):
    assert net_.pick_file_to_serve(str(tmp_path)) is None


def test_pick_file_to_serve_returns_file_when_single(tmp_path):
    (tmp_path / "only.txt").write_text("x")
    with patch("exchanger.net_.subprocess.run") as run:
        run.return_value = type("R", (), {"returncode": 0, "stdout": "only.txt\n"})()
        assert net_.pick_file_to_serve(str(tmp_path)) == "only.txt"


def test_pick_file_to_serve_respects_depth_limit(tmp_path):
    deep = tmp_path
    for i in range(net_._MAX_WALK_DEPTH + 2):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_text("deep")
    (tmp_path / "shallow.txt").write_text("shallow")
    with patch("exchanger.net_.subprocess.run") as run:
        run.return_value = type("R", (), {"returncode": 0, "stdout": "shallow.txt\n"})()
        net_.pick_file_to_serve(str(tmp_path))
        call_input = run.call_args.kwargs.get("input", "") or (run.call_args[1].get("input", "") if len(run.call_args) > 1 else "")
        assert "deep.txt" not in call_input


def test_get_all_interfaces_handles_missing_ip_command():
    with patch("exchanger.net_.subprocess.run", side_effect=FileNotFoundError):
        assert net_.get_all_interfaces() == []
