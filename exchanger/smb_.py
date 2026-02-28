"""SMB: serve not supported; receive is listen-only (HTTP)."""

import sys


def serve_smb(args):
    sys.exit("exchanger: SMB serve not supported on this platform; use --protocol http to serve.")
