"""
Resolve a caller-supplied name to a file directly inside a base directory.

Used wherever a store builds ``base / f"{name}{suffix}"`` from a session,
checkpoint, rule, doc or config name, so the name cannot climb out of the
store via ``..`` or path separators.
"""

from pathlib import Path

__all__ = ["safe_child"]


def safe_child(base: Path, name: str, suffix: str = "") -> Path:
    """Return ``base / f"{name}{suffix}"``, refusing names that escape ``base``."""
    if (
        not isinstance(name, str)
        or not name.strip()
        or name in (".", "..")
        or any(sep in name for sep in ("/", "\\", "\0"))
    ):
        raise ValueError(f"invalid name: {name!r}")
    path = Path(base) / f"{name}{suffix}"
    if path.resolve().parent != Path(base).resolve():
        raise ValueError(f"name escapes {base}: {name!r}")
    return path
