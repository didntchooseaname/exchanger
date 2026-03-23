"""HTTP server and client for file exchange."""

import base64
import datetime
import http.server
import mimetypes
import os
import threading
import urllib.parse
import urllib.request
import ssl
import sys
from tqdm import tqdm

_SPINNER = (".", "\\", "/", "-")
_SPINNER_INTERVAL = 0.12
_PROGRESS_LOCK = threading.Lock()
_CHUNK = 65536
_MIN_SIZE_FOR_PROGRESS = 65536  # only show bar for transfers >= 64KiB


def _spinner_loop(stop: threading.Event) -> None:
    i = 0
    while not stop.is_set():
        sys.stderr.write(f"\r  {_SPINNER[i % len(_SPINNER)]} ")
        sys.stderr.flush()
        i += 1
        stop.wait(_SPINNER_INTERVAL)
    sys.stderr.write("\r   \r")
    sys.stderr.flush()


def _read_with_progress(rfile, length: int, name: str) -> bytes:  # type: ignore[type-arg]
    """Read length bytes from rfile in chunks; show progress bar for large transfers."""
    show_bar = length >= _MIN_SIZE_FOR_PROGRESS and sys.stderr.isatty()
    chunks: list[bytes] = []
    remaining = length
    with _PROGRESS_LOCK:
        with tqdm(
            total=length,
            desc=name[:20],
            unit="B",
            unit_scale=True,
            file=sys.stderr,
            mininterval=0.1,
            disable=not show_bar,
        ) as pbar:
            while remaining > 0:
                chunk_size = min(_CHUNK, remaining)
                chunk = rfile.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
                pbar.update(len(chunk))
    return b"".join(chunks)


def _safe_join(base: str, path: str) -> str | None:
    """Resolve path under base; return None if path escapes base (including via symlinks)."""
    base = os.path.realpath(base)
    full = os.path.realpath(os.path.join(base, path.lstrip("/")))
    if not (full == base or full.startswith(base + os.sep)):
        return None
    return full


def _auto_rename(path: str) -> str:
    """If path already exists, append .1, .2, etc. until a free name is found."""
    if not os.path.exists(path):
        return path
    i = 1
    while True:
        candidate = f"{path}.{i}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _send_file(handler: "ExchangeHTTPRequestHandler", local: str, path: str) -> None:
    """Serve a local file over HTTP with progress tracking."""
    size = os.path.getsize(local)
    ctype, _ = mimetypes.guess_type(local)
    ctype = ctype or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-type", ctype)
    handler.send_header("Content-Length", str(size))
    handler.end_headers()
    name = os.path.basename(local)
    show_bar = size >= _MIN_SIZE_FOR_PROGRESS and sys.stderr.isatty()
    with _PROGRESS_LOCK:
        with open(local, "rb") as f:
            with tqdm(
                total=size,
                desc=name[:20],
                unit="B",
                unit_scale=True,
                file=sys.stderr,
                mininterval=0.1,
                disable=not show_bar,
            ) as pbar:
                while True:
                    chunk = f.read(_CHUNK)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    pbar.update(len(chunk))
    request_path_normalized = path.strip("/") or path
    serve_path = handler.server.serve_path
    if serve_path is not None and request_path_normalized == serve_path:
        threading.Thread(target=handler.server.shutdown, daemon=True).start()
    elif handler.server.one_shot:
        threading.Thread(target=handler.server.shutdown, daemon=True).start()


def _resolve_upload_path(handler: "ExchangeHTTPRequestHandler", path: str, local: str, content_type: str) -> tuple[bytes, str] | None:
    """Read upload payload and determine output path. Returns (payload, out_path) or None on error."""
    length_hdr = handler.headers.get("Content-Length")
    if length_hdr is None:
        handler.send_error(411, "Content-Length required")
        return None
    try:
        length = int(length_hdr)
    except ValueError:
        handler.send_error(400, "Invalid Content-Length")
        return None

    if "multipart/form-data" in content_type:
        return _handle_multipart_upload(handler, path, local, length, content_type)
    return _handle_raw_upload(handler, path, local, length)


def _handle_multipart_upload(
    handler: "ExchangeHTTPRequestHandler", path: str, local: str, length: int, content_type: str
) -> tuple[bytes, str] | None:
    """Parse multipart upload and return (payload, out_path)."""
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[9:].strip().strip('"')
            break
    if not boundary:
        handler.send_error(400, "Missing boundary")
        return None
    data = _read_with_progress(handler.rfile, length, "upload")
    try:
        body = _parse_multipart(data, boundary)
    except ValueError:
        handler.send_error(400, "Invalid multipart")
        return None
    if "file" in body:
        payload = body["file"]
    else:
        keys = [k for k in body if k != "path"]
        payload = body[keys[0]] if keys else b""
    out_path = local if local != handler.directory else os.path.join(handler.directory, "upload")
    if os.path.isdir(out_path):
        out_path = os.path.join(out_path, "upload")
    return payload, out_path


def _handle_raw_upload(handler: "ExchangeHTTPRequestHandler", path: str, local: str, length: int) -> tuple[bytes, str]:
    """Read raw body upload and return (payload, out_path)."""
    payload = _read_with_progress(handler.rfile, length, "upload")
    if path == "/" or path == "" or (local and os.path.isdir(local)):
        x_fn = handler.headers.get("X-Filename", "").strip()
        if x_fn:
            safe = os.path.basename(x_fn.replace("\\", "/"))
            if safe and "/" not in safe and ".." not in safe:
                out_path = os.path.join(handler.directory, safe)
            else:
                out_path = os.path.join(handler.directory, "upload")
        else:
            out_path = os.path.join(handler.directory, "upload")
    else:
        out_path = local
        if os.path.isdir(out_path):
            out_path = os.path.join(out_path, "upload")
    return payload, out_path


class ExchangeHTTPServer(http.server.HTTPServer):
    """HTTPServer subclass with exchange-specific attributes."""

    serve_path: str | None = None
    one_shot: bool = False
    auth_credentials: str | None = None  # "user:pass"
    decode_uploads: str | None = None    # "base64" or None
    log_file: str | None = None


class ExchangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves directory (GET) and accepts file uploads (POST)."""

    server: ExchangeHTTPServer  # type: ignore[assignment]

    def __init__(self, *args, directory: str | None = None, **kwargs):  # type: ignore[no-untyped-def]
        self.directory = directory or os.getcwd()
        super().__init__(*args, directory=self.directory, **kwargs)

    def _check_auth(self) -> bool:
        """Return True if auth passes (or no auth required)."""
        creds = self.server.auth_credentials
        if creds is None:
            return True
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            self._send_auth_required()
            return False
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        except Exception:
            self._send_auth_required()
            return False
        if decoded != creds:
            self._send_auth_required()
            return False
        return True

    def _send_auth_required(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="exchanger"')
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"401 Unauthorized\n")

    def _log_request(self, method: str) -> None:
        log_file = self.server.log_file
        if not log_file:
            return
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        client_ip = self.client_address[0]
        ua = self.headers.get("User-Agent", "-")
        line = f"{ts}\t{client_ip}\t{method}\t{self.path}\t{ua}\n"
        try:
            with open(log_file, "a") as f:
                f.write(line)
        except OSError:
            pass

    def do_GET(self) -> None:
        self._log_request("GET")
        if not self._check_auth():
            return
        path = urllib.parse.unquote(self.path)
        if path == "/" or path == "":
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"exchanger: GET /path/to/file to download, POST to upload\n")
            return
        if "?" in path:
            path = path.split("?")[0]
        local = _safe_join(self.directory, path)
        if local is None:
            self.send_error(403, "Forbidden")
            return
        if not os.path.isfile(local):
            self.send_error(404, "Not Found")
            return
        _send_file(self, local, path)

    def do_POST(self) -> None:
        self._log_request("POST")
        if not self._check_auth():
            return
        path = urllib.parse.unquote(self.path)
        if path == "/" or path == "":
            path = "/"
        if "?" in path:
            path = path.split("?")[0]
        local = _safe_join(self.directory, path)
        if local is None:
            self.send_error(403, "Forbidden")
            return
        dirpath = os.path.dirname(local)
        if dirpath and not os.path.isdir(dirpath):
            try:
                os.makedirs(dirpath, exist_ok=True)
            except OSError:
                self.send_error(500, "Cannot create directory")
                return
        content_type = self.headers.get("Content-Type", "")
        result = _resolve_upload_path(self, path, local, content_type)
        if result is None:
            return
        payload, out_path = result

        # Decode if --encode was specified
        if self.server.decode_uploads == "base64":
            try:
                payload = base64.b64decode(payload)
            except Exception:
                self.send_error(400, "Invalid base64 payload")
                return

        # Auto-rename to avoid overwriting
        out_path = _auto_rename(out_path)

        try:
            with open(out_path, "wb") as f:
                f.write(payload)
        except OSError as e:
            self.send_error(500, str(e))
            return
        self.send_response(201)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"created {out_path}\n".encode())

        if self.server.one_shot:
            threading.Thread(target=self.server.shutdown, daemon=True).start()


def _parse_multipart(data: bytes, boundary: str | bytes) -> dict[str, bytes]:
    if isinstance(boundary, str):
        boundary = boundary.encode()
    parts = data.split(b"--" + boundary)
    out: dict[str, bytes] = {}
    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        head, body = part.split(b"\r\n\r\n", 1)
        if body.endswith(b"\r\n"):
            body = body[:-2]
        name = None
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition:"):
                for token in line.split(b";")[1:]:
                    token = token.strip()
                    if token.lower().startswith(b"name="):
                        name = token[5:].strip(b'"').decode("utf-8", "replace")
                        break
                break
        if name is not None:
            out[name] = body
    return out


def serve_http(args, receive_only: bool = False) -> None:  # type: ignore[type-arg]
    dir_abs = os.path.abspath(args.dir)
    if not os.path.isdir(dir_abs):
        sys.exit(f"exchanger: not a directory: {args.dir}")
    if not os.access(dir_abs, os.R_OK):
        sys.exit(f"exchanger: directory not readable: {args.dir}")
    os.chdir(args.dir)
    handler = lambda *a, **k: ExchangeHTTPRequestHandler(*a, directory=dir_abs, **k)  # type: ignore[misc]
    server = ExchangeHTTPServer((args.bind, args.port), handler)
    server.serve_path = None
    server.one_shot = getattr(args, "one_shot", False)
    server.auth_credentials = getattr(args, "auth", None)
    server.decode_uploads = getattr(args, "encode", None)
    server.log_file = getattr(args, "log", None)

    if args.port == 443:
        cert_path = os.path.expanduser("~/.exchanger/cert.pem")
        key_path = os.path.expanduser("~/.exchanger/key.pem")
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert_path, key_path)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
        except FileNotFoundError:
            print(
                "exchanger: port 443 requires TLS; no cert found.\n"
                f"  expected: {cert_path}\n"
                f"           {key_path}\n"
                "  generate with:\n"
                '    mkdir -p ~/.exchanger && openssl req -x509 -newkey rsa:2048 -nodes \\\n'
                '      -keyout ~/.exchanger/key.pem -out ~/.exchanger/cert.pem -days 365 \\\n'
                '      -subj "/CN=exchanger"',
                file=sys.stderr,
            )
            sys.exit(1)
    if receive_only:
        from .net_ import BOLD, GREEN, RESET, print_commands_receive_listen
        if sys.stderr.isatty():
            print(f"{GREEN}{BOLD}🔄 exchanger: listening to receive (target POSTs to you) on {args.bind}:{args.port}{RESET}", file=sys.stderr)
        else:
            print(f"exchanger: listening to receive (target POSTs to you) on {args.bind}:{args.port}", file=sys.stderr)
        print_commands_receive_listen(
            args.port,
            getattr(args, "protocol", "http"),
            obfuscate=getattr(args, "obfuscate", False),
            auth=server.auth_credentials,
            proxy=getattr(args, "proxy", None),
            clipboard=getattr(args, "clipboard", False),
        )
    else:
        from .net_ import BOLD, GREEN, RESET, get_serve_base, print_commands_serve, pick_file_to_serve
        if sys.stderr.isatty():
            print(f"{GREEN}{BOLD}🔄 exchanger: serving {dir_abs} on {args.bind}:{args.port} (http){RESET}", file=sys.stderr)
        else:
            print(f"exchanger: serving {dir_abs} on {args.bind}:{args.port} (protocol http)", file=sys.stderr)
        base, platform = get_serve_base(args.port, getattr(args, "protocol", "http"))
        serve_path = pick_file_to_serve(dir_abs)

        # QR code
        if getattr(args, "qr", False) and base and serve_path:
            from .qr_ import print_qr
            url = base + "/" + serve_path
            print_qr(url)

        if base is not None:
            print_commands_serve(
                args.port,
                getattr(args, "protocol", "http"),
                serve_path=serve_path,
                _base=base,
                _platform=platform,
                obfuscate=getattr(args, "obfuscate", False),
                auth=server.auth_credentials,
                proxy=getattr(args, "proxy", None),
                clipboard=getattr(args, "clipboard", False),
            )
        server.serve_path = serve_path
    stop = threading.Event()
    spinner = threading.Thread(target=_spinner_loop, args=(stop,), daemon=True)
    spinner.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        spinner.join(timeout=0.5)
        sys.stderr.write("\r   \r")
        sys.stderr.flush()
