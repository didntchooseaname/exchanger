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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="exchanger",
        description=_BANNER + "\nServe files or listen to receive (target POSTs to host). Default port 80.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s                    (same as serve)
  %(prog)s serve              (target can GET or POST)
  %(prog)s receive            (host listens; target POSTs file to you)
  %(prog)s receive --dir /tmp --port 80
        """,
    )
    def add_protocol_port(sp):
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

    sub = parser.add_subparsers(dest="command", help="command (default: serve)")

    # serve (default when no command)
    serve_p = sub.add_parser("serve", help="serve current directory; others can send/receive (default)")
    add_protocol_port(serve_p)
    serve_p.add_argument(
        "-d", "--dir",
        default=".",
        metavar="DIR",
        help="directory to serve (default: current directory)",
    )
    serve_p.add_argument(
        "--bind",
        default="0.0.0.0",
        metavar="ADDR",
        help="address to bind (default: 0.0.0.0)",
    )
    serve_p.set_defaults(func=_cmd_serve)

    # receive (host listens; target POSTs to host)
    recv_p = sub.add_parser("receive", help="listen for target to POST file to you")
    add_protocol_port(recv_p)
    recv_p.add_argument(
        "-d", "--dir",
        default=".",
        metavar="DIR",
        help="directory to save received files (default: current directory)",
    )
    recv_p.add_argument(
        "--bind",
        default="0.0.0.0",
        metavar="ADDR",
        help="address to bind (default: 0.0.0.0)",
    )
    recv_p.set_defaults(func=_cmd_receive)

    return parser


def _cmd_serve(args):
    if args.protocol == "smb":
        from .smb_ import serve_smb
        serve_smb(args)
    else:
        from .http_ import serve_http
        serve_http(args)


def _cmd_receive(args):
    if args.protocol == "smb":
        sys.exit("exchanger: receive is listen-only; use --protocol http.")
    from .http_ import serve_http
    serve_http(args, receive_only=True)


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        args = parser.parse_args(["serve"] + [a for a in sys.argv[1:] if a not in ("-h", "--help")])
    args.func(args)
