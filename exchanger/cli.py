"""CLI argument parsing and dispatch."""

import argparse
import os
import sys


_BANNER = r"""
___________             .__
\_   _____/__  ___ ____ |  |__ _____    ____    ____   ___________
 |    __)_\  \/  // ___\|  |  \\__  \  /    \  / ___\_/ __ \_  __ \
 |        \>    <\  \___|   Y  \/ __ \|   |  \/ /_/  >  ___/|  | \/
/_______  /__/\_ \\___  >___|  (____  /___|  /\___  / \___  >__|
        \/      \/    \/     \/     \/     \//_____/      \/
"""


def _add_common_opts(sp: argparse.ArgumentParser) -> None:
    """Add options shared by serve and receive subcommands."""
    sp.add_argument(
        "--protocol",
        choices=("http", "smb"),
        default="http",
        help="protocol (default: http)",
    )
    sp.add_argument(
        "-p", "--port",
        type=int,
        default=80,
        help="port (default: 80)",
    )
    sp.add_argument(
        "-d", "--dir",
        default=".",
        metavar="DIR",
        help="directory to serve/save (default: current directory)",
    )
    sp.add_argument(
        "--bind",
        default="0.0.0.0",
        metavar="ADDR",
        help="address to bind (default: 0.0.0.0)",
    )
    sp.add_argument(
        "-o", "--obfuscate",
        action="store_true",
        help="output only obfuscated commands to stdout",
    )
    sp.add_argument(
        "--one-shot",
        action="store_true",
        help="exit after first completed transfer",
    )
    sp.add_argument(
        "--auth",
        metavar="USER:PASS",
        default=None,
        help="require HTTP Basic auth (e.g. --auth admin:secret)",
    )
    sp.add_argument(
        "--log",
        metavar="FILE",
        default=None,
        help="log requests to FILE (timestamp, IP, method, path, user-agent)",
    )
    sp.add_argument(
        "--proxy",
        metavar="PROXY_URL",
        default=None,
        help="include proxy in generated target commands (e.g. socks5://127.0.0.1:1080)",
    )
    sp.add_argument(
        "-c", "--clipboard",
        action="store_true",
        help="copy first target command to clipboard",
    )
    sp.add_argument(
        "-q", "--qr",
        action="store_true",
        help="print QR code of download URL to stderr",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exchanger",
        description=_BANNER + "\nServe files or listen to receive (target POSTs to host). Default port 80.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s                              (same as serve)
  %(prog)s serve                        (target can GET or POST)
  %(prog)s serve -o                     obfuscated one-liners to stdout
  %(prog)s serve --auth admin:s3cret    require basic auth
  %(prog)s serve --one-shot             exit after first download
  %(prog)s serve -c                     copy first command to clipboard
  %(prog)s serve -q                     show QR code of download URL
  %(prog)s receive                      (host listens; target POSTs file to you)
  %(prog)s receive --encode base64      auto-decode base64 uploads
  %(prog)s receive --one-shot           exit after first upload
  %(prog)s push file.bin 10.0.0.1:8080  push a file to a listening target
        """,
    )

    sub = parser.add_subparsers(dest="command", help="command (default: serve)")

    # serve
    serve_p = sub.add_parser("serve", help="serve current directory; others can send/receive (default)")
    _add_common_opts(serve_p)
    serve_p.set_defaults(func=_cmd_serve)

    # receive
    recv_p = sub.add_parser("receive", help="listen for target to POST file to you")
    _add_common_opts(recv_p)
    recv_p.add_argument(
        "--encode",
        choices=("base64",),
        default=None,
        help="decode uploads (e.g. --encode base64)",
    )
    recv_p.set_defaults(func=_cmd_receive)

    # push
    push_p = sub.add_parser("push", help="push a file to a listening target")
    push_p.add_argument("file", help="file to push")
    push_p.add_argument("target", help="target address (host:port or URL)")
    push_p.add_argument(
        "--encode",
        choices=("base64",),
        default=None,
        help="encode payload before sending (e.g. --encode base64)",
    )
    push_p.set_defaults(func=_cmd_push)

    return parser


def _cmd_serve(args: argparse.Namespace) -> None:
    if args.protocol == "smb":
        from .smb_ import serve_smb
        serve_smb(args)
    else:
        from .http_ import serve_http
        serve_http(args)


def _cmd_receive(args: argparse.Namespace) -> None:
    if args.protocol == "smb":
        sys.exit("exchanger: receive is listen-only; use --protocol http.")
    from .http_ import serve_http
    serve_http(args, receive_only=True)


def _cmd_push(args: argparse.Namespace) -> None:
    from .push_ import push_file
    push_file(args)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        args = parser.parse_args(["serve"] + [a for a in sys.argv[1:] if a not in ("-h", "--help")])
    args.func(args)
