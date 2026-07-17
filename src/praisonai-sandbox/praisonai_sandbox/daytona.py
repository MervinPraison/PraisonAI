"""
Daytona Sandbox implementation for PraisonAI.

Provides code execution in Daytona cloud sandboxes via daytona-sdk.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from praisonaiagents.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxStatus,
    ResourceLimits,
)

logger = logging.getLogger(__name__)

_INSTALL_HINT = "pip install praisonai-sandbox[daytona]"


class DaytonaSandbox:
    """Daytona cloud sandbox for isolated code execution."""

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        image: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        target: Optional[str] = None,
        timeout: Optional[int] = None,
        cpu: Optional[int] = None,
        memory_mb: Optional[int] = None,
    ):
        self.config = config or SandboxConfig(sandbox_type="daytona")
        limits = self.config.resource_limits

        if image is not None:
            self.image = image
        elif config is not None and config.image:
            self.image = config.image
        else:
            self.image = "python:3.12-slim"
        self._api_key = api_key or os.environ.get("DAYTONA_API_KEY", "")
        self._api_url = api_url or os.environ.get(
            "DAYTONA_API_URL", "https://app.daytona.io/api"
        )
        self._target = target or os.environ.get("DAYTONA_TARGET", "us")
        if timeout is not None:
            self.timeout = timeout
        elif config is not None:
            self.timeout = limits.timeout_seconds
        else:
            self.timeout = 300
        self.cpu = cpu if cpu is not None else max(1, limits.cpu_percent // 100)
        self.memory_mb = memory_mb if memory_mb is not None else limits.memory_mb
        self._sandbox = None
        self._client = None
        self._is_running = False

    @property
    def is_available(self) -> bool:
        if not self._api_key.strip():
            return False
        try:
            import daytona_sdk  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def sandbox_type(self) -> str:
        return "daytona"

    def _get_client(self):
        if self._client is None:
            from daytona_sdk import Daytona, DaytonaConfig

            self._client = Daytona(
                DaytonaConfig(
                    api_key=self._api_key,
                    api_url=self._api_url,
                    target=self._target,
                )
            )
        return self._client

    async def start(self) -> None:
        if self._is_running:
            return
        if not self.is_available:
            raise RuntimeError(
                f"Daytona not available. Install daytona-sdk and set DAYTONA_API_KEY. {_INSTALL_HINT}"
            )
        self._sandbox = await asyncio.to_thread(self._create_sandbox_sync)
        self._is_running = True
        logger.info("Daytona sandbox started")

    def _create_sandbox_sync(self):
        from daytona_sdk import CreateSandboxFromImageParams, Resources

        client = self._get_client()
        params = CreateSandboxFromImageParams(
            image=self.image,
            resources=Resources(cpu=self.cpu, memory=self.memory_mb),
        )
        return client.create(params, timeout=max(self.timeout, 60))

    async def stop(self) -> None:
        if not self._is_running:
            return
        sandbox = self._sandbox
        self._sandbox = None
        self._is_running = False
        if sandbox is not None:
            try:
                await asyncio.to_thread(sandbox.delete)
            except Exception as exc:
                logger.warning("Daytona sandbox delete failed: %s", exc)
        logger.info("Daytona sandbox stopped")

    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        if not self._is_running:
            await self.start()
        limits = limits or ResourceLimits(timeout_seconds=self.timeout)
        execution_id = str(uuid.uuid4())
        started_at = time.time()
        if language == "python":
            command = f"python -c {shlex.quote(code)}"
        elif language == "bash":
            command = code
        else:
            command = f"python -c {shlex.quote(code)}"
        return await self._run_command(
            command,
            limits=limits,
            env=env,
            working_dir=working_dir,
            execution_id=execution_id,
            started_at=started_at,
        )

    async def run_command(
        self,
        command: Union[str, List[str]],
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        if not self._is_running:
            await self.start()
        if isinstance(command, list):
            command = shlex.join(command)
        limits = limits or ResourceLimits(timeout_seconds=self.timeout)
        return await self._run_command(
            command,
            limits=limits,
            env=env,
            working_dir=working_dir,
            execution_id=str(uuid.uuid4()),
            started_at=time.time(),
        )

    async def _run_command(
        self,
        command: str,
        *,
        limits: ResourceLimits,
        env: Optional[Dict[str, str]],
        working_dir: Optional[str],
        execution_id: str,
        started_at: float,
    ) -> SandboxResult:
        try:
            cmd_parts: List[str] = []
            if working_dir:
                cmd_parts.append(f"cd {shlex.quote(working_dir)}")
            if env:
                for key, value in env.items():
                    cmd_parts.append(
                        f"export {shlex.quote(key)}={shlex.quote(value)}"
                    )
            cmd_parts.append(command)
            full_command = " && ".join(cmd_parts)
            response = await asyncio.to_thread(
                self._sandbox.process.exec,
                full_command,
                timeout=limits.timeout_seconds,
            )
            stdout = getattr(response, "result", "") or ""
            exit_code = getattr(response, "exit_code", 0)
            status = SandboxStatus.COMPLETED if exit_code == 0 else SandboxStatus.FAILED
            return SandboxResult(
                execution_id=execution_id,
                status=status,
                exit_code=exit_code,
                stdout=stdout,
                stderr="",
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
        except Exception as exc:
            error = str(exc)
            status = SandboxStatus.TIMEOUT if "timeout" in error.lower() else SandboxStatus.FAILED
            return SandboxResult(
                execution_id=execution_id,
                status=status,
                error=error,
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )

    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    code = handle.read()
            except OSError as exc:
                return SandboxResult(
                    execution_id=str(uuid.uuid4()),
                    status=SandboxStatus.FAILED,
                    error=f"Could not read {file_path}: {exc}",
                )
            language = "bash" if file_path.endswith((".sh", ".bash")) else "python"
            return await self.execute(code, language=language, limits=limits, env=env)

        parts = [file_path] + (args or [])
        return await self.run_command(
            " ".join(shlex.quote(p) for p in parts), limits=limits, env=env
        )

    async def write_file(self, path: str, content: Union[str, bytes]) -> bool:
        if not self._is_running:
            await self.start()
        try:
            payload = content if isinstance(content, bytes) else content.encode("utf-8")
            await asyncio.to_thread(self._sandbox.fs.upload_file, path, payload)
            return True
        except Exception as exc:
            logger.error("Daytona write_file failed: %s", exc)
            return False

    async def read_file(self, path: str) -> Optional[Union[str, bytes]]:
        if not self._is_running:
            await self.start()
        try:
            content = await asyncio.to_thread(self._sandbox.fs.download_file, path)
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return content
        except Exception as exc:
            logger.warning("Daytona read_file failed: %s", exc)
            return None

    async def list_files(self, path: str = "/") -> List[str]:
        result = await self.run_command(f"find {shlex.quote(path)} -type f 2>/dev/null | head -100")
        if not result.success:
            return []
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    def get_status(self) -> Dict[str, Any]:
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "image": self.image,
            "api_key_set": bool(self._api_key),
        }

    async def cleanup(self) -> None:
        await self.stop()

    async def reset(self) -> None:
        await self.stop()
        await self.start()
