"""Path helpers for dynamic-context storage (no traversal in run/agent ids)."""

from __future__ import annotations


def safe_storage_id(value: str, label: str = "id") -> str:
    """Reject path separators and parent-directory segments in storage keys."""
    if not value or value in (".", ".."):
        raise ValueError(f"Invalid {label}")
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"Invalid {label}: path separators not allowed")
    return value
