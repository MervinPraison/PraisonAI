"""CLI extension protocols for wrapper ↔ code boundaries (C8.5)."""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class TemplateStoreProtocol(Protocol):
    """Template persistence accessed from repatriated CLI features."""

    def list_templates(self, *, category: Optional[str] = None) -> list[Any]:
        ...

    def get_template(self, name: str) -> Any:
        ...


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Optional session backend for interactive TUI paths."""

    def load(self, session_id: str) -> Optional[Any]:
        ...

    def save(self, session_id: str, data: Any) -> None:
        ...


@runtime_checkable
class ServeHandlerProtocol(Protocol):
    """Dispatch serve subcommands without direct wrapper imports in code."""

    def handle(self, args: list[str]) -> int:
        ...


@runtime_checkable
class BotGatewayFacadeProtocol(Protocol):
    """Future praisonai-bot package entry for gateway/bot CLI (C8.4 Phase 9)."""

    def handle_gateway(self, args: list[str]) -> int:
        ...

    def handle_bot(self, args: list[str]) -> int:
        ...
