"""Push a file to a listening target via HTTP POST."""

import base64
import os
import sys
import urllib.parse
import urllib.request
from tqdm import tqdm


def push_file(args) -> None:  # type: ignore[type-arg]
    """Push a local file to a remote target via HTTP POST."""
    filepath = args.file
    target = args.target
    encode = getattr(args, "encode", None)

    if not os.path.isfile(filepath):
        sys.exit(f"exchanger: file not found: {filepath}")

    # Build URL
    if not target.startswith(("http://", "https://")):
        target = f"http://{target}"
    filename = os.path.basename(filepath)
    url = target.rstrip("/") + "/" + urllib.parse.quote(filename)

    # Read file
    with open(filepath, "rb") as f:
        data = f.read()

    if encode == "base64":
        data = base64.b64encode(data)

    # Send
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Length": str(len(data)),
            "Content-Type": "application/octet-stream",
            "X-Filename": filename,
        },
    )

    sys.stderr.write(f"exchanger: pushing {filepath} ({len(data)} bytes) to {url}\n")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
            sys.stderr.write(f"exchanger: {resp.status} — {body.strip()}\n")
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"exchanger: HTTP {e.code} — {e.reason}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"exchanger: connection failed — {e.reason}\n")
        sys.exit(1)
