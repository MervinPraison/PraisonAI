"""Shared base helpers for framework adapters (no third-party imports)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .protocols import FrameworkAdapterProtocol

logger = logging.getLogger(__name__)


class BaseFrameworkAdapter:
    """Base class for framework adapters providing common functionality."""

    name: str = ""
    install_hint: str = ""
    requires_tools_extra: bool = False
    is_router: bool = False

    # Adapters with a native async ``run`` path set this True and override
    # ``arun``. When False (default), ``arun`` offloads the sync ``run`` to a
    # bounded, per-adapter thread pool so one slow run cannot starve the
    # process-wide default executor used by ``asyncio.to_thread``.
    SUPPORTS_ASYNC: bool = False

    # Bounded per-adapter offload pool. Kept small on purpose: framework runs
    # are long-lived, so a large pool provides no benefit and just hides the
    # lack of a native async path. Overridable per subclass / instance.
    _THREAD_OFFLOAD_MAX_WORKERS: int = 4

    DEFAULT_MODEL = "openai/gpt-4o-mini"

    def __init__(self) -> None:
        self._thread_pool: Optional[ThreadPoolExecutor] = None

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

    def _get_thread_pool(self) -> ThreadPoolExecutor:
        """Lazily create the bounded, per-adapter offload executor."""
        # Defensive: tolerate subclasses that don't call super().__init__().
        if getattr(self, "_thread_pool", None) is None:
            self._thread_pool = ThreadPoolExecutor(
                max_workers=self._THREAD_OFFLOAD_MAX_WORKERS,
                thread_name_prefix=f"{self.name or 'framework'}-arun",
            )
        return self._thread_pool

    async def _thread_offload_run(self, *args: Any, **kwargs: Any) -> str:
        """Run the sync ``run`` on this adapter's bounded thread pool.

        Unlike ``asyncio.to_thread`` (which shares the process-wide default
        executor), this isolates the offload so one slow framework run cannot
        starve every other async caller in the process.
        """
        loop = asyncio.get_running_loop()
        pool = self._get_thread_pool()
        return await loop.run_in_executor(
            pool, lambda: self.run(*args, **kwargs)
        )

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
        if not self.SUPPORTS_ASYNC:
            logger.warning(
                "Adapter %r has no native async path; delegating to a bounded "
                "thread pool (max_workers=%d). Concurrent async callers will "
                "contend for this pool.",
                self.name or type(self).__name__,
                self._THREAD_OFFLOAD_MAX_WORKERS,
            )
        return await self._thread_offload_run(
            config,
            llm_config,
            topic,
            tools_dict=tools_dict,
            agent_callback=agent_callback,
            task_callback=task_callback,
            cli_config=cli_config,
        )

    def cleanup(self) -> None:
        pool = getattr(self, "_thread_pool", None)
        if pool is not None:
            pool.shutdown(wait=False)
            self._thread_pool = None

    def __del__(self) -> None:
        # Best-effort: shut down the offload pool when the adapter is garbage
        # collected so idle worker threads do not outlive the adapter in
        # long-lived services that forget to call cleanup(). Guarded because
        # __del__ can run during interpreter shutdown when globals are gone.
        try:
            self.cleanup()
        except Exception:
            pass

    def resolve_alias(self) -> str:
        return self.name
