"""Protocol for optional third-party agent framework adapters."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class FrameworkAdapterProtocol(Protocol):
    """Contract for YAML-driven multi-framework execution backends."""

    name: str
    install_hint: str
    requires_tools_extra: bool
    is_router: bool

    def is_available(self) -> bool:
        """Return True when this framework's optional dependencies are installed."""
        ...

    def resolve(
        self, *, config: Optional[Dict[str, Any]] = None
    ) -> "FrameworkAdapterProtocol":
        """Pick a concrete adapter variant (e.g. autogen v0.2 vs v0.4)."""
        ...

    def setup(self, *, framework_tag: str) -> None:
        """Framework-specific pre-run hooks (observability, SDK init, etc.)."""
        ...

    def run(
        self,
        config: Dict[str, Any],
        llm_config: List[Dict],
        topic: str,
        *,
        tools_dict: Optional[Dict[str, Any]] = None,
        agent_callback: Optional[Callable] = None,
        task_callback: Optional[Callable] = None,
        cli_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Execute the framework with shared agents.yaml configuration."""
        ...

    async def arun(
        self,
        config: Dict[str, Any],
        llm_config: List[Dict],
        topic: str,
        *,
        tools_dict: Optional[Dict[str, Any]] = None,
        agent_callback: Optional[Callable] = None,
        task_callback: Optional[Callable] = None,
        cli_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Async execution; default implementations may offload sync run()."""
        ...

    def cleanup(self) -> None:
        """Release resources after execution."""
        ...

    def resolve_alias(self) -> str:
        """Return the concrete adapter name to dispatch to."""
        ...
