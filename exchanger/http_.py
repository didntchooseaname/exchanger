"""HTTP server and client for file exchange."""

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


def _read_with_progress(rfile, length: int, name: str) -> bytes:
    """Read length bytes from rfile in chunks; show progress bar for large transfers."""
    show_bar = length >= _MIN_SIZE_FOR_PROGRESS and sys.stderr.isatty()
    chunks = []
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
    """Resolve path under base; return None if path escapes base."""
    base = os.path.abspath(base)
    full = os.path.abspath(os.path.join(base, path.lstrip("/")))
    if not full.startswith(base):
        return None
    return full


class ExchangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves directory (GET) and accepts file uploads (POST)."""

    def __init__(self, *args, directory=None, **kwargs):
        self.directory = directory or os.getcwd()
        super().__init__(*args, directory=self.directory, **kwargs)

    def do_GET(self):
        path = urllib.parse.unquote(self.path)
        if path == "/" or path == "":
            path = "/"
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
        size = os.path.getsize(local)
        ctype, _ = mimetypes.guess_type(local)
        ctype = ctype or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        name = os.path.basename(local)
        show_bar = size >= _MIN_SIZE_FOR_PROGRESS and sys.stderr.isatty()
        request_path_normalized = path.strip("/") or path
        serve_path = getattr(self.server, "serve_path", None)
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
                        self.wfile.write(chunk)
                        pbar.update(len(chunk))
        if serve_path is not None and request_path_normalized == serve_path:
            self.server.shutdown()

    def do_POST(self):
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
        length = self.headers.get("Content-Length")
        if length is None:
            self.send_error(411, "Content-Length required")
            return
        try:
            length = int(length)
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if "multipart/form-data" in content_type:
            boundary = None
            for part in content_type.split(";"):
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part[9:].strip().strip('"')
                    break
            if not boundary:
                self.send_error(400, "Missing boundary")
                return
            data = _read_with_progress(self.rfile, length, "upload")
            try:
                body = _parse_multipart(data, boundary)
            except ValueError:
                self.send_error(400, "Invalid multipart")
                return
            if "file" in body:
                payload = body["file"]
            else:
                keys = [k for k in body if k != "path"]
                payload = body[keys[0]] if keys else b""
            out_path = local if local != self.directory else os.path.join(self.directory, "upload")
            if os.path.isdir(out_path):
                out_path = os.path.join(out_path, "upload")
        else:
            payload = _read_with_progress(self.rfile, length, "upload")
            if path == "/" or path == "" or (local and os.path.isdir(local)):
                x_fn = self.headers.get("X-Filename", "").strip()
                if x_fn:
                    safe = os.path.basename(x_fn.replace("\\", "/"))
                    if safe and "/" not in safe and ".." not in safe:
                        out_path = os.path.join(self.directory, safe)
                    else:
                        out_path = os.path.join(self.directory, "upload")
                else:
                    out_path = os.path.join(self.directory, "upload")
            else:
                out_path = local
                if os.path.isdir(out_path):
                    out_path = os.path.join(out_path, "upload")
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


def _parse_multipart(data: bytes, boundary: bytes) -> dict:
    if isinstance(boundary, str):
        boundary = boundary.encode()
    parts = data.split(b"--" + boundary)
    out = {}
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


def serve_http(args, receive_only: bool = False):
    dir_abs = os.path.abspath(args.dir)
    if not os.path.isdir(dir_abs):
        sys.exit(f"exchanger: not a directory: {args.dir}")
    os.chdir(args.dir)
    handler = lambda *a, **k: ExchangeHTTPRequestHandler(*a, directory=dir_abs, **k)
    server = http.server.HTTPServer((args.bind, args.port), handler)
    server.serve_path = None
    if args.port == 443:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(
                os.path.expanduser("~/.exchanger/cert.pem"),
                os.path.expanduser("~/.exchanger/key.pem"),
            )
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
        except FileNotFoundError:
            print("exchanger: port 443 requires TLS; no cert at ~/.exchanger/cert.pem", file=sys.stderr)
            print("exchanger: use --port 8443 for plain HTTP or provide certs.", file=sys.stderr)
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
        )
    else:
        from .net_ import BOLD, GREEN, RESET, get_serve_base, print_commands_serve, pick_file_to_serve
        if sys.stderr.isatty():
            print(f"{GREEN}{BOLD}🔄 exchanger: serving {dir_abs} on {args.bind}:{args.port} (http){RESET}", file=sys.stderr)
        else:
            print(f"exchanger: serving {dir_abs} on {args.bind}:{args.port} (protocol http)", file=sys.stderr)
        base, platform = get_serve_base(args.port, getattr(args, "protocol", "http"))
        serve_path = pick_file_to_serve(dir_abs)
        if base is not None:
            print_commands_serve(
                args.port,
                getattr(args, "protocol", "http"),
                serve_path=serve_path,
                _base=base,
                _platform=platform,
                obfuscate=getattr(args, "obfuscate", False),
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


