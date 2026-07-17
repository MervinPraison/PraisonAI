"""Console entry: ``praisonai-sandbox``."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        args = ["--help"]
    print("praisonai-sandbox: use praisonaiagents SandboxManager or import praisonai_sandbox backends.")
    print("Install extras: pip install praisonai-sandbox[docker,e2b,sandlock,ssh,modal]")
    if args[0] in ("--help", "-h"):
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
