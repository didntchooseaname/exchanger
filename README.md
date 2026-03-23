# 🔄 Exchanger (exchangertool)

[![PyPI version](https://img.shields.io/pypi/v/exchangertool.svg)](https://pypi.org/project/exchangertool/)
[![CI](https://github.com/didntchooseaname/exchanger/actions/workflows/ci.yml/badge.svg)](https://github.com/didntchooseaname/exchanger/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Exchanger** is a fast, lightweight, and flexible Python CLI utility designed to streamline file transfers, payload delivery, and data exchange between machines.

Whether you are a system administrator moving files or a security professional leveraging LOLBAS/GTFOBins during an engagement, `exchangertool` provides a seamless way to host, transfer, and exfiltrate your data.

## ✨ Features

* **Quick Setup:** Spin up a file exchange server in seconds.
* **Cross-Platform Target Support:** Serves files to Windows (`certutil`, `curl`, `PowerShell`, `iwr`, `bitsadmin`, `net use`) and GNU/Linux (`wget`, `curl`, `bash`) targets.
* **Obfuscation (`-o`):** PowerShell-Obfuscation-Bible–style and Bashfuscator-style command obfuscation for authorized testing.
* **Basic Auth (`--auth`):** Protect downloads/uploads with HTTP Basic authentication.
* **One-Shot Mode (`--one-shot`):** Server exits after completing a single transfer.
* **Push Mode (`push`):** Actively push a file to a listening target.
* **Base64 Encoding (`--encode base64`):** Auto-encode on push, auto-decode on receive.
* **Clipboard Copy (`-c`):** Auto-copy first target command to clipboard.
* **QR Code (`-q`):** Display download URL as a QR code for air-gapped transfers.
* **Checksum Verification:** SHA256 verification commands printed alongside downloads.
* **DNS Exfil Commands:** Ready-to-use DNS exfiltration stagers for Linux and Windows.
* **Chunked Transfer Commands:** Split large files into chunks for size-limit evasion.
* **WebDAV Commands:** Windows `net use` / `copy` commands via WebDAV.
* **Proxy Support (`--proxy`):** Generate proxy-aware target commands (SOCKS5/HTTP).
* **Request Logging (`--log`):** Log all requests to a file (timestamp, IP, method, path, user-agent).
* **Auto-Rename:** Uploads never overwrite — collisions auto-rename to `file.1`, `file.2`, etc.
* **SMB Serve (`--protocol smb`):** Serve files over SMB using impacket (optional).
* **Standalone CLI:** Runs smoothly from any terminal.
* **Isolated Installation:** Compatible with `pipx`.

## 📦 Installation

```bash
pipx install exchangertool
```

### Optional extras

```bash
# QR code support
pipx install exchangertool[qr]

# SMB support (requires impacket)
pipx install exchangertool[smb]

# Everything
pipx install exchangertool[all]
```

### Using with sudo

`pipx` installs to your user directory (e.g. `~/.local/bin`). For root:

```bash
# Option 1: Full path
sudo "$(which exchanger)" serve --port 80

# Option 2: System-wide install
sudo pip install exchangertool

# Option 3: Allow low ports without sudo (Linux)
sudo setcap 'cap_net_bind_service=+ep' "$(which exchanger)"
```

## 🚀 Usage

### Serve (default)

```bash
exchanger                              # serve current directory on port 80
exchanger serve -d /payloads -p 8080   # serve specific dir on custom port
exchanger serve --auth admin:s3cret    # require authentication
exchanger serve --one-shot             # exit after first download
exchanger serve -o                     # obfuscated commands to stdout
exchanger serve -c                     # copy first command to clipboard
exchanger serve -q                     # show QR code of download URL
exchanger serve --proxy socks5://127.0.0.1:1080  # proxy-aware commands
exchanger serve --log requests.log     # log all requests
```

### Receive (listen for uploads)

```bash
exchanger receive                      # listen for target to POST files
exchanger receive --encode base64      # auto-decode base64 uploads
exchanger receive --one-shot           # exit after first upload
exchanger receive --auth user:pass     # require auth for uploads
```

### Push (send to target)

```bash
exchanger push payload.bin 10.0.0.1:8080           # push file to target
exchanger push payload.bin 10.0.0.1:8080 --encode base64  # base64-encode
```

### SMB (optional)

```bash
exchanger serve --protocol smb -d /share -p 445
exchanger serve --protocol smb --auth admin:pass
```

## 🛠️ Help menu

```
usage: exchanger [-h] {serve,receive,push} ...

Serve files or listen to receive (target POSTs to host). Default port 80.

positional arguments:
  {serve,receive,push}  command (default: serve)
    serve               serve current directory; others can send/receive
    receive             listen for target to POST file to you
    push                push a file to a listening target

common options (serve/receive):
  --protocol {http,smb}  protocol (default: http)
  -p, --port PORT        port (default: 80)
  -d, --dir DIR          directory to serve/save (default: .)
  --bind ADDR            address to bind (default: 0.0.0.0)
  -o, --obfuscate        obfuscated commands to stdout
  --one-shot             exit after first transfer
  --auth USER:PASS       HTTP Basic auth
  --log FILE             log requests to file
  --proxy PROXY_URL      proxy for target commands
  -c, --clipboard        copy first command to clipboard
  -q, --qr              show QR code of download URL

receive-only:
  --encode base64        decode uploads on the server

push:
  exchanger push FILE TARGET [--encode base64]
```

## 📋 Generated Target Commands

When you start the server, exchanger prints ready-to-paste commands organized by platform:

| Category | Linux (GTFOBins) | Windows (LOLBAS) |
|----------|------------------|------------------|
| **Download** | `curl`, `wget`, `/dev/tcp` | `curl`, `wget`, `certutil`, `iwr`, `bitsadmin` |
| **Download LOLBins** | `python3`, `perl`, `ruby`, `php`, `nc`, `socat`, `openssl`, `lwp-download`, `tftp` | `DownloadFile`, `Start-BitsTransfer`, `mshta`, `regsvr32`, `msiexec`, `hh.exe`, `esentutl`, `expand`, `findstr`, `replace`, `cscript` |
| **In-Memory** | `curl \| bash`, `wget \| bash` | `iwr \| iex`, `WebClient.DownloadString` |
| **In-Memory LOLBins** | `python exec()`, `perl eval()`, `ruby eval()`, `php eval()` | `mshta vbscript`, `rundll32 javascript`, `powershell -enc`, `cscript //e:jscript`, `Reflection.Assembly.Load` |
| **Upload** | `curl -X POST` | `curl -X POST` |
| **Upload LOLBins** | `nc`, `python requests`, `openssl s_client`, `socat`, `bash /dev/tcp` | `WebClient.UploadFile`, `WebClient.UploadData`, `iwr -Method POST` |
| **Checksum** | `sha256sum` | `Get-FileHash` |
| **DNS Exfil** | `xxd \| nslookup`, `base64 \| dig` | PowerShell + `nslookup` |
| **Chunked** | `split` + `curl` loop | PowerShell byte chunking |
| **WebDAV** | — | `net use`, `copy` |

All commands respect `--auth`, `--proxy`, and `-o` (obfuscation) flags.

## 🔒 Obfuscation Techniques (`-o`)

When `-o` is passed, all target commands are obfuscated and written to stdout (for piping/redirection).

**PowerShell obfuscation:**
- Quote interruption (`i''ex`, `i""wr`)
- Random case (`iNvOkE-wEbReQuEsT`)
- Backtick insertion (`` i`e`x ``)
- Format string iex (`("{0}{1}{2}" -f 'i','e','x')`)
- Get-Command wildcard (`& (gcm i*e*-E*n)`)
- `-EncodedCommand` (base64 UTF-16LE full command wrap)
- `[scriptblock]::Create()` wrapping
- `Set-Alias` for cmdlet renaming
- URL string concatenation and base64 encoding
- `$True`/`$False` boolean substitution
- WebClient variable name randomization

**Bash obfuscation:**
- Base64 wrap (`echo ... | base64 -d | bash`, `eval $(...)`, `source <(...)`)
- Variable expansion (`_var=curl; $_var ...`)
- Double variable indirection (`a=curl; b=a; ${!b} ...`)
- Hex command names (`$'\x63\x75\x72\x6c'`)
- Printf command names (`$(printf '\x63\x75\x72\x6c')`)
- Reverse pipe (`echo '...reversed...' | rev | bash`)
- IFS substitution (`curl${IFS}-s${IFS}http://...`)
- Quote tricks (`cu''rl`, `wg''et`)

## 🧪 Testing

CI runs the test suite on Python 3.10–3.13 with mypy type checking on every push/PR.

```bash
pip install -e ".[dev]"
pytest tests/ -v
mypy exchanger/ --ignore-missing-imports
```

Coverage report: `pytest tests/ --cov=exchanger --cov-report=term-missing`

## 🤝 Contributing

Contributions, bug reports, and feature requests are always welcome! Feel free to check out the issues page.

## 📝 License

This project is licensed under the MIT License.
