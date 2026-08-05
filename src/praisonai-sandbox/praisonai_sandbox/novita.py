"""
Novita Sandbox implementation for PraisonAI.

Provides code execution in Novita cloud sandboxes via novita-sandbox.
"""

from __future__ import annotations

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

_INSTALL_HINT = "pip install praisonai-sandbox[novita]"


class NovitaSandbox:
    """Novita cloud sandbox for isolated code execution.

    Example:
        import os
        from praisonai_sandbox import NovitaSandbox

        os.environ["NOVITA_API_KEY"] = "your-api-key"
        sandbox = NovitaSandbox()
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!

    Requires:
        - pip install novita-sandbox
        - NOVITA_API_KEY environment variable
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        """Initialize the Novita sandbox.

        Args:
            config: Optional sandbox configuration
        """
        self.config = config or SandboxConfig(sandbox_type="novita")
        self._sandbox = None
        self._is_running = False

    @property
    def is_available(self) -> bool:
        """Check if Novita is available."""
        try:
            import importlib
            importlib.import_module("novita_sandbox")
            api_key = os.getenv("NOVITA_API_KEY")
            return api_key is not None and api_key.strip() != ""
        except ImportError:
            return False

    @property
    def sandbox_type(self) -> str:
        return "novita"

    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        if self._is_running:
            return

        if not self.is_available:
            raise RuntimeError(
                f"Novita is not available. Please install novita-sandbox and set NOVITA_API_KEY. {_INSTALL_HINT}"
            )

        try:
            from novita_sandbox.core import AsyncSandbox
        except ImportError:
            raise ImportError(
                "novita-sandbox not installed. "
                "Install with: pip install novita-sandbox"
            )

        self._sandbox = await AsyncSandbox.create(
            timeout=self.config.resource_limits.timeout_seconds,
        )
        self._is_running = True
        logger.info("Novita sandbox initialized")

    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        if not self._is_running:
            return

        if self._sandbox:
            try:
                await self._sandbox.kill()
            except Exception as e:
                logger.warning(f"Failed to kill Novita sandbox: {e}")
            self._sandbox = None

        self._is_running = False
        logger.info("Novita sandbox stopped")

    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Execute code in the sandbox."""
        if not self._is_running:
            await self.start()

        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())
        started_at = time.time()

        if language == "python":
            command = f"python3 -c {shlex.quote(code)}"
        elif language == "bash":
            command = code
        else:
            command = f"python3 -c {shlex.quote(code)}"

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
        """Run a shell command in the sandbox."""
        if not self._is_running:
            await self.start()

        if isinstance(command, list):
            command = shlex.join(command)

        limits = limits or self.config.resource_limits
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
            result = await self._sandbox.commands.run(
                command,
                envs=env,
                cwd=working_dir,
                timeout=limits.timeout_seconds,
            )
            status = SandboxStatus.COMPLETED if result.exit_code == 0 else SandboxStatus.FAILED
            return SandboxResult(
                execution_id=execution_id,
                status=status,
                exit_code=result.exit_code,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                error=result.error,
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
        """Execute a file in the sandbox."""
        try:
            with open(file_path, "r") as f:
                code = f.read()
        except OSError as exc:
            return SandboxResult(
                execution_id=str(uuid.uuid4()),
                status=SandboxStatus.FAILED,
                error=f"Could not read {file_path}: {exc}",
            )

        language = "bash" if file_path.endswith((".sh", ".bash")) else "python"
        if args:
            remote_path = f"/tmp/{uuid.uuid4().hex}_{os.path.basename(file_path)}"
            if not await self.write_file(remote_path, code):
                return SandboxResult(
                    execution_id=str(uuid.uuid4()),
                    status=SandboxStatus.FAILED,
                    error=f"Could not upload {file_path} to sandbox",
                )
            interpreter = "bash" if language == "bash" else "python3"
            parts = [interpreter, remote_path] + list(args)
            return await self.run_command(parts, limits=limits, env=env)

        return await self.execute(code, language=language, limits=limits, env=env)

    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file to the sandbox."""
        if not self._is_running:
            await self.start()

        try:
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            await self._sandbox.files.write(path, content)
            return True
        except Exception as e:
            logger.error(f"Failed to write file {path}: {e}")
            return False

    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file from the sandbox."""
        if not self._is_running:
            await self.start()

        try:
            content = await self._sandbox.files.read(path)
            return content
        except Exception as e:
            logger.warning(f"Failed to read file {path}: {e}")
            return None

    async def list_files(
        self,
        path: str = "/",
    ) -> List[str]:
        """List files in a sandbox directory."""
        if not self._is_running:
            await self.start()

        try:
            entries = await self._sandbox.files.list(path)
            return [entry.path for entry in entries]
        except Exception:
            return []

    def get_status(self) -> Dict[str, Any]:
        """Get sandbox status information."""
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "api_key_set": bool(os.getenv("NOVITA_API_KEY")),
        }

    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        await self.stop()

    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        await self.stop()
        await self.start()
