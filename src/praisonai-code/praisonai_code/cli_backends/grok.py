"""xAI Grok CLI backend."""

from __future__ import annotations

import asyncio
import copy
import os
import subprocess
from typing import AsyncIterator, List, Optional

try:
    from praisonaiagents import (
        CliBackendConfig,
        CliBackendDelta,
        CliBackendProtocol,
        CliBackendResult,
        CliSessionBinding,
    )
except ImportError:
    from praisonaiagents.cli_backend.protocols import (
        CliBackendConfig,
        CliBackendDelta,
        CliBackendProtocol,
        CliBackendResult,
        CliSessionBinding,
    )

DEFAULT_CONFIG = CliBackendConfig(
    command="grok",
    args=["--always-approve", "--output-format", "plain"],
    output="text",
    input="single",
    timeout_ms=300_000,
)


class GrokBackend:
    """Grok CLI backend — delegates agent turns to ``grok --single``."""

    def __init__(self, config: Optional[CliBackendConfig] = None):
        self.config = copy.deepcopy(config if config is not None else DEFAULT_CONFIG)

    async def execute(
        self,
        prompt: str,
        *,
        session: Optional[CliSessionBinding] = None,
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> CliBackendResult:
        cmd = self._build_command(
            prompt,
            session=session,
            images=images,
            system_prompt=system_prompt,
            **kwargs,
        )
        try:
            content = await self._execute_subprocess(cmd)
            return CliBackendResult(
                content=content.strip(),
                session_id=session.session_id if session else None,
                metadata={"command": cmd},
            )
        except subprocess.CalledProcessError as exc:
            return CliBackendResult(
                content="",
                error=f"Grok CLI failed: {exc}",
                metadata={"command": cmd, "return_code": getattr(exc, "returncode", -1)},
            )

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[CliBackendDelta]:
        result = await self.execute(prompt, **kwargs)
        if result.error:
            yield CliBackendDelta(type="error", content=result.error)
            return
        yield CliBackendDelta(type="text", content=result.content)

    def _build_command(
        self,
        prompt: str,
        *,
        session: Optional[CliSessionBinding] = None,
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> List[str]:
        cmd = [self.config.command, *self.config.args, "--cwd", os.getcwd()]

        if session and session.session_id:
            cmd.extend(["--resume", session.session_id])

        if system_prompt:
            cmd.extend(["--system-prompt-override", system_prompt])

        if images:
            for image_path in images:
                cmd.extend(["--image", image_path])

        cmd.extend(["-p", prompt])
        return cmd

    async def _execute_subprocess(self, cmd: List[str]) -> str:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._get_env(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout_ms / 1000,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise TimeoutError(f"Grok CLI timed out after {self.config.timeout_ms}ms") from exc

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else f"Exit code {process.returncode}"
            raise subprocess.CalledProcessError(process.returncode, cmd, stderr=error_msg)

        return stdout.decode()

    def _get_env(self) -> dict[str, str]:
        env = dict(os.environ)
        for var in self.config.clear_env:
            env.pop(var, None)
        env.update(self.config.env)
        return env
