"""Console entry: ``praisonai-browser``."""

from __future__ import annotations

import sys


def _configure_stdio() -> None:
    """Force UTF-8 on stdout/stderr so banners never crash on cp1252 consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    from praisonai_browser.cli.app import app

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        args = ["--help"]
    app(args=args, prog_name="praisonai-browser")


if __name__ == "__main__":
    main()
