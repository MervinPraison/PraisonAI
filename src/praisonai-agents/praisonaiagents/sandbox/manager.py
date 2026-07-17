"""
SandboxManager for PraisonAI Agents.

Factory and context manager for sandbox backends.
Core SDK component that routes to appropriate sandbox implementations
via lazy bridge to praisonai-sandbox.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

from .config import SandboxConfig
from .protocols import SandboxProtocol, SandboxResult

if TYPE_CHECKING:
    from typing import AsyncContextManager

logger = logging.getLogger(__name__)


class SandboxManager:
    """Factory and context manager for all sandbox backends.

    Routes to appropriate sandbox implementations based on configuration.
    Lightweight manager in core SDK — heavy implementations in praisonai-sandbox.

    Example:
        from praisonaiagents.sandbox import SandboxManager, SandboxConfig

        config = SandboxConfig.docker("python:3.11-slim")
        manager = SandboxManager(config)
        result = await manager.run_code("print('Hello, World!')")
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig.subprocess()
        self._sandbox: Optional[SandboxProtocol] = None

    async def __aenter__(self) -> SandboxProtocol:
        self._sandbox = await self._create_sandbox()
        return self._sandbox

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._sandbox:
            try:
                await self._sandbox.stop()
                await self._sandbox.cleanup()
            except Exception as e:
                logger.warning(f"Error during sandbox cleanup: {e}")
            finally:
                self._sandbox = None

    async def run_code(
        self,
        code: str,
        language: str = "python",
        **kwargs
    ) -> SandboxResult:
        async with self as sandbox:
            return await sandbox.execute(code, language=language, **kwargs)

    async def _create_sandbox(self) -> SandboxProtocol:
        from ._sandbox_bridge import resolve_sandbox_class, sandbox_install_hint

        sandbox_type = self.config.sandbox_type.lower()
        if sandbox_type == "local":
            sandbox_type = "subprocess"
        if sandbox_type == "native":
            sandbox_type = "sandlock"

        try:
            sandbox_cls = resolve_sandbox_class(sandbox_type)
        except ImportError as e:
            raise ImportError(sandbox_install_hint(sandbox_type)) from e
        except ValueError as e:
            raise ValueError(
                f"Unknown sandbox type: {sandbox_type!r}. {e}"
            ) from e

        kwargs: Dict[str, Any] = {"config": self.config}
        if sandbox_type == "docker":
            kwargs["image"] = self.config.image

        sandbox = sandbox_cls(**kwargs)

        is_available = getattr(sandbox, "is_available", True)
        if callable(is_available):
            is_available = is_available()
        if not is_available:
            raise RuntimeError(
                f"Sandbox {sandbox_type!r} is not available. "
                f"{sandbox_install_hint(sandbox_type)}"
            )

        await sandbox.start()
        return sandbox

    def get_available_types(self) -> Dict[str, Dict[str, Any]]:
        from ._sandbox_bridge import get_sandbox_registry, sandbox_install_hint

        types: Dict[str, Dict[str, Any]] = {}
        try:
            registry_cls = get_sandbox_registry()
            registry = registry_cls.default()
            for name in registry.list_names():
                available = False
                try:
                    cls = registry.resolve(name)
                    is_available = getattr(cls(), "is_available", False)
                    available = bool(
                        is_available() if callable(is_available) else is_available
                    )
                except Exception:
                    available = False
                types[name] = {
                    "available": available,
                    "description": f"Sandbox backend: {name}",
                    "requires": [] if available else [sandbox_install_hint(name)],
                }
        except ImportError:
            types.setdefault("subprocess", {
                "available": False,
                "description": "Local subprocess (limited isolation)",
                "requires": [sandbox_install_hint("subprocess")],
            })

        types.setdefault("subprocess", {
            "available": True,
            "description": "Local subprocess (limited isolation)",
            "requires": [],
        })
        return types
