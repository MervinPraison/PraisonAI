"""Async-over-sync plumbing, written once instead of once per vendor.

Every cloud SDK here is synchronous, and ``ComputeProviderProtocol`` is async.
So each provider grew the same five methods, whose entire body is "hand the
matching ``_*_sync`` call to a thread":

    async def provision(self, config):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._provision_sync, config)

Those five were byte-identical across e2b, daytona, modal, tenki and flyio --
about 210 lines of the same four statements. That was the largest genuinely
duplicated block in the project, larger than all four cross-stack vendor pairs
combined, and it was invisible because it sat *within* one stack rather than
between two.

A vendor now implements only the ``_*_sync`` half it actually differs in.
Anything a vendor genuinely needs to do differently it simply overrides, since
these are ordinary methods.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional


class SyncComputeProvider:
    """Bridges synchronous vendor SDKs to the async compute protocol.

    Subclasses implement the ``_*_sync`` methods. Each is optional: a provider
    that cannot do something raises ``NotImplementedError`` from the base
    rather than silently returning a wrong answer.
    """

    async def _offload(self, fn, *args):
        """Run a blocking SDK call without stalling the event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, *args)

    # ── the protocol, in terms of the sync half ──────────────────────────────
    async def provision(self, config) -> Any:
        return await self._offload(self._provision_sync, config)

    async def execute(
        self, instance_id: str, command: str, timeout: int = 300
    ) -> Dict[str, Any]:
        return await self._offload(self._execute_sync, instance_id, command, timeout)

    async def shutdown(self, instance_id: str) -> None:
        return await self._offload(self._shutdown_sync, instance_id)

    async def upload_file(
        self, instance_id: str, local_path: str, remote_path: str
    ) -> bool:
        return await self._offload(self._upload_sync, instance_id, local_path, remote_path)

    async def download_file(
        self, instance_id: str, remote_path: str, local_path: str
    ) -> bool:
        return await self._offload(self._download_sync, instance_id, remote_path, local_path)

    # ── the half each vendor actually writes ─────────────────────────────────
    def _provision_sync(self, config) -> Any:
        raise NotImplementedError(
            f"{type(self).__name__} cannot provision an instance"
        )

    def _execute_sync(self, instance_id: str, command: str, timeout: int) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{type(self).__name__} cannot execute a command"
        )

    def _shutdown_sync(self, instance_id: str) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} cannot shut an instance down"
        )

    def _upload_sync(self, instance_id: str, local_path: str, remote_path: str) -> bool:
        raise NotImplementedError(
            f"{type(self).__name__} does not support uploading files"
        )

    def _download_sync(self, instance_id: str, remote_path: str, local_path: str) -> bool:
        raise NotImplementedError(
            f"{type(self).__name__} does not support downloading files"
        )
