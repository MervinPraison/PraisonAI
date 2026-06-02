"""Hooks query protocol for UI/API consumers."""

from __future__ import annotations

from typing import Dict, List, Protocol, runtime_checkable


@runtime_checkable
class HooksQueryProtocol(Protocol):
    """Read path for registered hooks."""

    def list_hooks_for_api(self) -> List[Dict]:
        ...
