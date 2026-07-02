"""Standalone-safe legacy entry helpers (C8.4)."""

from __future__ import annotations


def dispatch_version_only() -> int:
    """Print version and exit — no wrapper import."""
    from praisonai_code._version import get_package_version
    print(get_package_version())
    return 0
