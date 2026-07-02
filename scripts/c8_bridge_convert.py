#!/usr/bin/env python3
"""Convert direct ``from praisonai`` imports to bridge calls in a file."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Match: from praisonai.foo.bar import A, B
FROM_IMPORT = re.compile(
    r"^(\s*)from praisonai(\.[\w.]+)? import (.+)$"
)
# Match: from praisonai import foo
FROM_ROOT = re.compile(
    r"^(\s*)from praisonai import (.+)$"
)


def _convert_from_line(line: str) -> str | None:
    m = FROM_ROOT.match(line)
    if m:
        indent, names = m.groups()
        mod = "praisonai"
        return (
            f"{indent}from praisonai_code._wrapper_bridge import import_wrapper_module\n"
            f"{indent}_mod = import_wrapper_module({mod!r})\n"
            f"{indent}({names}) = tuple(getattr(_mod, n.strip()) for n in {names!r}.split(','))"
        )
    m = FROM_IMPORT.match(line)
    if not m:
        return None
    indent, suffix, names = m.groups()
    mod = f"praisonai{suffix or ''}"
    # Handle ``import x as y``
    parts = [p.strip() for p in names.split(",")]
    assigns = []
    for part in parts:
        if " as " in part:
            orig, alias = part.split(" as ", 1)
            orig, alias = orig.strip(), alias.strip()
            assigns.append(f"{alias} = getattr(_mod, {orig!r})")
        else:
            assigns.append(f"{part} = getattr(_mod, {part!r})")
    body = "\n".join(f"{indent}{a}" for a in assigns)
    return (
        f"{indent}from praisonai_code._wrapper_bridge import import_wrapper_module\n"
        f"{indent}_mod = import_wrapper_module({mod!r})\n"
        f"{body}"
    )


def convert_file(path: Path) -> int:
    text = path.read_text()
    lines = text.splitlines()
    out: list[str] = []
    changed = 0
    for line in lines:
        if line.strip().startswith("#") and "from praisonai" in line:
            out.append(line)
            continue
        if "from praisonai" in line and "praisonai_code" not in line and "praisonaiagents" not in line:
            new = _convert_from_line(line)
            if new:
                out.append(new)
                changed += 1
                continue
        out.append(line)
    if changed:
        path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""))
    return changed


if __name__ == "__main__":
    total = 0
    for p in sys.argv[1:]:
        n = convert_file(Path(p))
        print(f"{p}: {n} lines converted")
        total += n
    print(f"total: {total}")
