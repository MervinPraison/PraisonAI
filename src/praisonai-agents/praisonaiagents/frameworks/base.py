"""Shared base helpers for framework adapters (no third-party imports)."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Callable, Dict, List, Optional

from .protocols import FrameworkAdapterProtocol


class BaseFrameworkAdapter:
    """Base class for framework adapters providing common functionality."""

    name: str = ""
    install_hint: str = ""
    requires_tools_extra: bool = False
    is_router: bool = False

    DEFAULT_MODEL = "openai/gpt-4o-mini"

    def __init__(self) -> None:
        pass

    def _resolve_llm(self, spec: Any, llm_config: Optional[List[Dict]]) -> str:
        """Resolve a model name from per-agent spec and shared llm_config."""
        base = None
        key = None
        if llm_config and len(llm_config) > 0:
            base = llm_config[0].get("base_url")
            key = llm_config[0].get("api_key")

        if isinstance(spec, str) and spec.strip():
            model = spec.strip()
        elif isinstance(spec, dict) and spec.get("model"):
            model = spec["model"]
        else:
            model = os.environ.get("MODEL_NAME") or self.DEFAULT_MODEL

        # Return model string; wrapper subclasses may upgrade to provider objects.
        _ = (base, key)
        return model

    def _format_template(self, template: str, **kwargs: Any) -> str:
        """Safely format template string, preserving JSON-like braces."""
        if not isinstance(template, str):
            return template

        def _sub(match: re.Match) -> str:
            name = match.group(1)
            return str(kwargs[name]) if name in kwargs else match.group(0)

        return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", _sub, template)

    def resolve(
        self, *, config: Optional[Dict[str, Any]] = None
    ) -> FrameworkAdapterProtocol:
        return self

    def setup(self, *, framework_tag: str) -> None:
        pass

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
        return await asyncio.to_thread(
            self.run,
            config,
            llm_config,
            topic,
            tools_dict=tools_dict,
            agent_callback=agent_callback,
            task_callback=task_callback,
            cli_config=cli_config,
        )

    def cleanup(self) -> None:
        pass

    def resolve_alias(self) -> str:
        return self.name
