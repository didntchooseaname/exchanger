"""QR code output for URLs (requires optional 'qrcode' package)."""

import sys


def print_qr(url: str) -> None:
    """Print a QR code of the URL to stderr. Requires 'qrcode' package."""
    try:
        import qrcode  # type: ignore[import-untyped]
    except ImportError:
        sys.stderr.write("  (install 'qrcode' for QR output: pip install exchangertool[qr])\n")
        return

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Render as Unicode block characters to stderr
    matrix = qr.get_matrix()
    sys.stderr.write("\n")
    for row in matrix:
        line = "  "
        for cell in row:
            line += "██" if cell else "  "
        sys.stderr.write(line + "\n")
    sys.stderr.write(f"  {url}\n\n")
