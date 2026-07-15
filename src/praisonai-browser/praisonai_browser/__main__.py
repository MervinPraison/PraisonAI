"""Console entry: ``praisonai-browser``."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    from praisonai_browser.cli.app import app

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        args = ["--help"]
    app(args=args, prog_name="praisonai-browser")


if __name__ == "__main__":
    main()
