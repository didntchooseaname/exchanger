"""exchanger - minimal file send/receive over HTTP or SMB."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("exchangertool")
except PackageNotFoundError:
    __version__ = "0.0.0"  # fallback for editable installs without metadata
