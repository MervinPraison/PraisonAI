#!/usr/bin/env python3
"""C8 repatriation helper — move impl from praisonai-code to praisonai wrapper."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODE = REPO / "src/praisonai-code/praisonai_code"
WRAP = REPO / "src/praisonai/praisonai"


def repatriate_file(code_rel: str, wrap_rel: str | None = None) -> None:
    """Copy code file to wrapper and delete code copy."""
    wrap_rel = wrap_rel or code_rel
    src = CODE / code_rel
    dst = WRAP / wrap_rel
    if not src.exists():
        print(f"SKIP missing: {src}", file=sys.stderr)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    src.unlink()
    print(f"repatriated {code_rel} -> {wrap_rel}")


def repatriate_command(name: str) -> None:
    repatriate_file(f"cli/commands/{name}.py")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("items", nargs="+", help="command names or code-relative paths")
    parser.add_argument("--feature", action="store_true", help="path under cli/features/")
    args = parser.parse_args()
    for item in args.items:
        if args.feature:
            repatriate_file(f"cli/features/{item}")
        elif "/" in item:
            repatriate_file(item)
        else:
            repatriate_command(item)


if __name__ == "__main__":
    main()
