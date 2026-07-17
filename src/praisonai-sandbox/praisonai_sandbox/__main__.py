"""Console entry: ``praisonai-sandbox``."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print("praisonai-sandbox — isolated agent code execution backends")
        print("Use: praisonai sandbox run | praisonaiagents SandboxManager | import praisonai_sandbox")
        print("Extras: pip install praisonai-sandbox[docker,e2b,daytona,modal,sandlock,ssh]")
        raise SystemExit(0)

    if args[0] == "backends":
        try:
            from praisonaiagents.sandbox import SandboxConfig, SandboxManager

            manager = SandboxManager(SandboxConfig.subprocess())
            for name, info in sorted(manager.get_available_types().items()):
                flag = "available" if info.get("available") else "unavailable"
                print(f"{name}: {flag}")
            raise SystemExit(0)
        except ImportError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    print("Unknown command. Try: praisonai-sandbox --help")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
