# 🔄 Exchanger (exchangertool)

[![PyPI version](https://img.shields.io/pypi/v/exchangertool.svg)](https://pypi.org/project/exchangertool/)
[![Python versions](https://img.shields.io/pypi/pyversions/exchangertool.svg)](https://pypi.org/project/exchangertool/)
[![GitHub Repo stars](https://img.shields.io/github/stars/didntchooseaname/exchanger?style=social)](https://github.com/didntchooseaname/exchanger)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Exchanger** is a fast, lightweight, and flexible Python Command Line Interface (CLI) utility designed to streamline file transfers, payload delivery, and data exchange between machines.

Whether you are a system administrator moving files or a security professional leveraging LOLBAS/GTFOBins during an engagement, `exchangertool` provides a seamless way to host and transfer your data.

## ✨ Features

* **Quick Setup:** Spin up a file exchange server in seconds.
* **Cross-Platform Target Support:** Easily serves files to Windows (`certutil`, `curl`, `PowerShell`, `iwr`, `bitsadmin`) and Linux (`wget`, `curl`, `bash`) targets.
* **Standalone CLI:** Runs smoothly from any terminal.
* **Isolated Installation:** Perfectly compatible with `pipx` to avoid polluting your system Python environment.

## 📦 Installation

The recommended way to install `exchangertool` is using [`pipx`](https://pypa.github.io/pipx/). This installs the tool globally in an isolated virtual environment.

```bash
pipx install exchangertool
```

### Using with sudo

`pipx` installs the tool in your user directory (e.g. `~/.local/bin`). When you run `sudo exchanger`, the root user does not see that path, so the command may not be found or may run a different binary.

**Options:**

- **Use the full path** so root runs your installed binary:
  ```bash
  sudo "$(which exchanger)" serve --port 80
  ```
- **Install system-wide** when you need to run as root often:
  ```bash
  sudo pip install exchangertool
  ```
- **Bind to port 80 without sudo** (Linux) by giving the binary permission to bind to low ports:
  ```bash
  sudo setcap 'cap_net_bind_service=+ep' "$(which exchanger)"
  ```
  Then run `exchanger serve --port 80` as your normal user.

## 🚀 Usage

Once installed, you can trigger the tool directly from your command line.

```bash
exchanger
```

## 🛠️ Help menu

```bash
usage: exchanger [-h] {serve,receive} ...

___________             .__                                        
\_   _____/__  ___ ____ |  |__ _____    ____    ____   ___________ 
 |    __)_\  \/  // ___\|  |  \\__  \  /    \  / ___\_/ __ \_  __ \
 |        \>    <\  \___|   Y  \/ __ \|   |  \/ /_/  >  ___/|  | \/
/_______  /__/\_ \\___  >___|  (____  /___|  /\___  / \___  >__|   
        \/      \/    \/     \/     \/     \//_____/      \/       

Serve files or listen to receive (target POSTs to host). Default port 80.

positional arguments:
  {serve,receive}  command (default: serve)
    serve          serve current directory; others can send/receive (default)
    receive        listen for target to POST file to you

options:
  -h, --help       show this help message and exit

examples:
  exchanger                    (same as serve)
  exchanger serve              (target can GET or POST)
  exchanger receive            (host listens; target POSTs file to you)
  exchanger receive --dir /tmp --port 80
```

## 🤝 Contributing

Contributions, bug reports, and feature requests are always welcome! Feel free to check out the issues page if you have ideas for new features or find a bug.

## 📝 License

This project is licensed under the MIT License.
