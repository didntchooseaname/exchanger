# exchanger

Serve files or listen to receive (target POSTs file to host). Default port 8080.

## Installation

```bash
pipx install exchangertool
```

## Usage

```bash
exchanger
```

## Help menu

```bash
___________             .__                                        
\_   _____/__  ___ ____ |  |__ _____    ____    ____   ___________ 
 |    __)_\  \/  // ___\|  |  \\__  \  /    \  / ___\_/ __ \_  __ \
 |        \>    <\  \___|   Y  \/ __ \|   |  \/ /_/  >  ___/|  | \/
/_______  /__/\_ \\___  >___|  (____  /___|  /\___  / \___  >__|   
        \/      \/    \/     \/     \/     \//_____/      \/       

Serve files or listen to receive (target POSTs to host). Default port 8080.

positional arguments:
  {serve,receive}
                 command (default:
                 serve)
    serve        serve current
                 directory; others
                 can send/receive
                 (default)
    receive      listen for target to
                 POST file to you

options:
  -h, --help     show this help
                 message and exit

examples:
  exchanger                    (same as serve)
  exchanger serve              (target can GET or POST)
  exchanger receive            (host listens; target POSTs file to you)
  exchanger receive --dir /tmp --port 8080
```
