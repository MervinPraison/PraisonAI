"""Check the environment before the GPU time is spent.

The floors were pip metadata only. `pyproject.toml` declares `torch>=2.6.0`,
`transformers>=4.51.3`, `trl>=0.18.2` and so on, but nothing checked them at
runtime — and pip is routinely bypassed. `pip install --no-deps`, a conda
environment assembled by hand, `setup_conda_env.sh` pinning its own torch: all
produce an environment whose versions were never enforced.

praisonai-train does inherit unsloth's own import-time checks, but only once
`from unsloth import FastLanguageModel` runs, deep inside a lazy helper. By
then the CLI has parsed arguments and the user sees a raw traceback rather than
a CLI-shaped error naming the package to upgrade.
"""

from __future__ import annotations

# Kept in step with pyproject.toml's [project.optional-dependencies] llm extra.
# A test asserts they match, so the two cannot drift.
FLOORS = {
    "torch": "2.6.0",
    "transformers": "4.51.3",
    "unsloth": "2025.9.1",
    "trl": "0.18.2",
    "peft": "0.13.0",
    "bitsandbytes": "0.45.0",
}


def _parse(version: str) -> tuple:
    """Compare release segments only.

    A dev or rc suffix on a matching release counts as satisfying the floor:
    refusing `2.6.0rc1` when the floor is `2.6.0` blocks people testing
    upstream, and unsloth's own checks are release-level too.
    """
    out = []
    for part in str(version).split(".")[:4]:
        digits = ""
        for ch in part:
            if not ch.isdigit():
                break
            digits += ch
        out.append(int(digits) if digits else 0)
    return tuple(out)


def satisfies(installed: str, floor: str) -> bool:
    if not installed:
        return False
    return _parse(installed) >= _parse(floor)


def installed_version(package: str) -> "str | None":
    try:
        from importlib.metadata import version
        return version(package)
    except Exception:
        return None


def check(floors=None) -> list:
    """Packages that are missing or too old, as (name, installed, floor).

    `installed` is None when the package is absent, which needs a different
    remedy from a version that is merely behind.
    """
    problems = []
    for package, floor in (floors or FLOORS).items():
        found = installed_version(package)
        if found is None:
            problems.append((package, None, floor))
        elif not satisfies(found, floor):
            problems.append((package, found, floor))
    return problems


def describe(problems) -> str:
    """One actionable message naming exactly what to install."""
    missing = [p for p in problems if p[1] is None]
    stale = [p for p in problems if p[1] is not None]
    lines = []
    if missing:
        lines.append("Missing: " + ", ".join(p[0] for p in missing))
    for package, found, floor in stale:
        lines.append(f"{package} {found} is older than the required {floor}")
    specs = " ".join(f'"{p[0]}>={p[2]}"' for p in problems)
    lines.append(f"Install with: pip install -U {specs}")
    return "\n".join(lines)
