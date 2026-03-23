"""SMB file server using impacket (optional dependency)."""

import os
import sys


def serve_smb(args) -> None:  # type: ignore[type-arg]
    """Serve a directory over SMB using impacket's smbserver."""
    try:
        from impacket.smbserver import SimpleSMBServer  # type: ignore[import-untyped]
    except ImportError:
        sys.exit(
            "exchanger: SMB requires impacket.\n"
            "  Install with: pip install exchangertool[smb]"
        )

    dir_abs = os.path.abspath(args.dir)
    if not os.path.isdir(dir_abs):
        sys.exit(f"exchanger: not a directory: {args.dir}")

    share_name = "share"
    bind = getattr(args, "bind", "0.0.0.0")
    port = getattr(args, "port", 445)

    server = SimpleSMBServer(listenAddress=bind, listenPort=port)
    server.addShare(share_name, dir_abs, comment="exchanger share")

    auth = getattr(args, "auth", None)
    if auth:
        user, _, password = auth.partition(":")
        server.setSMB2Support(True)
        server.addCredential(user, 0, "", password)
    else:
        server.setSMB2Support(True)

    sys.stderr.write(f"exchanger: SMB share '{share_name}' on {bind}:{port} -> {dir_abs}\n")
    sys.stderr.write(f"  target: net use Z: \\\\YOUR_IP\\{share_name}\n")
    if auth:
        user, _, _ = auth.partition(":")
        sys.stderr.write(f"  target: net use Z: \\\\YOUR_IP\\{share_name} /user:{user}\n")
    sys.stderr.write("\n")

    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
