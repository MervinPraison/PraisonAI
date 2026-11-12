"""
boxd Sandbox implementation for PraisonAI.

Provides code execution in boxd cloud machines via the boxd SDK.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import threading
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

_INSTALL_HINT = "pip install praisonai-sandbox[boxd]"
_NAME_PREFIX = "praisonai-"
_DEFAULT_MAX_LIFETIME = 24 * 60 * 60


class BoxdSandbox:
    """boxd cloud sandbox for isolated code execution.

    Each sandbox is one boxd machine (a full Ubuntu VM). ``start()`` creates
    it with ``isolated=True``, so it joins no private network and holds no
    credentials. ``stop()`` deletes it. If ``stop()`` never runs, boxd deletes
    the machine itself once it is ``max_lifetime`` seconds old.

    Example:
        import os
        from praisonai_sandbox import BoxdSandbox

        os.environ["BOXD_API_KEY"] = "your-api-key"
        sandbox = BoxdSandbox()
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!

    Requires:
        - pip install praisonai-sandbox[boxd]
        - BOXD_API_KEY environment variable (BOXD_ORG and BOXD_REGION optional)
    """

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        api_key: Optional[str] = None,
        org: Optional[str] = None,
        region: Optional[str] = None,
        vcpu: Optional[int] = None,
        memory: Optional[str] = None,
        from_snapshot: Optional[str] = None,
        max_lifetime: Optional[int] = _DEFAULT_MAX_LIFETIME,
    ):
        """Initialize the boxd sandbox.

        Args:
            config: Optional sandbox configuration
            api_key: boxd API key (defaults to BOXD_API_KEY)
            org: boxd organization (defaults to BOXD_ORG, else the key's org)
            region: "fra" or "nyc" (defaults to BOXD_REGION, else your home region)
            vcpu: vCPUs, paired with memory: 1/"4G", 2/"8G", 4/"16G", 8/"32G"
                (defaults to your org's machine size)
            memory: memory, paired with vcpu
            from_snapshot: start from a saved boxd snapshot instead of the base image
            max_lifetime: seconds after which boxd deletes the machine, whatever
                it is doing, so a process that dies before ``stop()`` leaves
                nothing behind (default 24 hours; None or 0 for no limit)
        """
        self.config = config or SandboxConfig(sandbox_type="boxd")
        self._api_key = api_key or os.environ.get("BOXD_API_KEY", "")
        self.org = org or os.environ.get("BOXD_ORG") or None
        self.region = region or os.environ.get("BOXD_REGION") or None
        self.vcpu = vcpu
        self.memory = memory
        self.from_snapshot = from_snapshot
        self.max_lifetime = max_lifetime
        self.machine_id: Optional[str] = None
        self._client = None
        self._is_running = False
        # A threading lock, not an asyncio one: a sync Agent runs each tool
        # call on its own event loop, and callers may be on different threads.
        self._start_lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        """Check if boxd is available."""
        if not self._api_key.strip():
            return False
        try:
            import importlib
            importlib.import_module("boxd")
            return True
        except ImportError:
            return False

    @property
    def sandbox_type(self) -> str:
        return "boxd"

    def _get_client(self):
        if self._client is None:
            from boxd import Boxd

            self._client = Boxd(api_key=self._api_key, region=self.region)
        return self._client

    async def start(self) -> None:
        """Create the machine and wait until it accepts commands."""
        if self._is_running:
            return

        if not self.is_available:
            raise RuntimeError(
                f"boxd is not available. Install the boxd SDK and set BOXD_API_KEY. {_INSTALL_HINT}"
            )

        while not self._start_lock.acquire(blocking=False):
            await asyncio.sleep(0.05)
        try:
            # Another caller may have started the machine while this one waited.
            if not self._is_running:
                await self._create_and_wait()
        finally:
            self._start_lock.release()

    async def _create_and_wait(self) -> None:
        client = self._get_client()
        options: Dict[str, Any] = {"isolated": True}
        if self.org:
            options["org"] = self.org
        if self.vcpu is not None:
            options["vcpu"] = self.vcpu
        if self.memory is not None:
            options["memory"] = self.memory
        if self.from_snapshot:
            options["from_snapshot"] = self.from_snapshot
        if self.max_lifetime:
            options["delete_after"] = int(self.max_lifetime)

        name = f"{_NAME_PREFIX}{uuid.uuid4().hex[:8]}"
        machine = await self._create_machine(client, name, options)
        self.machine_id = machine.id
        try:
            await asyncio.to_thread(client.machines.wait_until_ready, machine.id)
        except BaseException:
            # Also on cancel or Ctrl-C: the machine exists, so delete it.
            await self._delete_machine()
            raise
        self._is_running = True
        logger.info("boxd sandbox started: %s (%s)", name, machine.id)

    async def _create_machine(self, client, name: str, options: Dict[str, Any]):
        """Create the machine without losing it to a cancel.

        The create call runs in a worker thread, and a cancel cannot stop a
        thread. So on cancel, wait for the call to finish and delete the
        machine it made before passing the cancel on.
        """
        pending = asyncio.ensure_future(
            asyncio.to_thread(client.machines.create, name, **options)
        )
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not pending.cancelled() and pending.exception() is None:
                self.machine_id = pending.result().id
                await self._delete_machine()
            raise

    async def _delete_machine(self) -> None:
        machine_id = self.machine_id
        self.machine_id = None
        if machine_id is None:
            return
        delete = self._get_client().machines.delete
        try:
            try:
                await asyncio.to_thread(delete, machine_id)
            except RuntimeError as exc:
                # No worker threads left, e.g. a cleanup that runs while the
                # interpreter shuts down: delete on this thread instead.
                if "interpreter shutdown" not in str(exc):
                    raise
                delete(machine_id)
        except Exception as exc:
            logger.warning("boxd machine delete failed for %s: %s", machine_id, exc)

    async def stop(self) -> None:
        """Delete the machine."""
        if not self._is_running and self.machine_id is None:
            return
        self._is_running = False
        await self._delete_machine()
        logger.info("boxd sandbox stopped")

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
        if language == "bash":
            command = code
        else:
            command = f"python3 -c {shlex.quote(code)}"

        return await self._run_command(
            command,
            limits=limits,
            env=env,
            working_dir=working_dir,
            execution_id=str(uuid.uuid4()),
            started_at=time.time(),
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
        merged_env = {**self.config.env, **(env or {})}
        try:
            # bash -c, so pipes, redirects and $VAR expansion see the env
            # passed to this call.
            result = await asyncio.to_thread(
                self._get_client().machines.exec,
                self.machine_id,
                ["bash", "-c", command],
                env=merged_env or None,
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
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
        except Exception as exc:
            error = str(exc)
            status = SandboxStatus.TIMEOUT if "timed out" in error.lower() else SandboxStatus.FAILED
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
        """Execute a local file in the sandbox."""
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
            try:
                return await self.run_command(parts, limits=limits, env=env)
            finally:
                await self._remove_file(remote_path)

        return await self.execute(code, language=language, limits=limits, env=env)

    async def _remove_file(self, path: str) -> None:
        if self.machine_id is None:
            return
        try:
            await asyncio.to_thread(
                self._get_client().machines.files.delete, self.machine_id, path
            )
        except Exception as exc:
            logger.debug("boxd could not remove %s: %s", path, exc)

    async def write_file(self, path: str, content: Union[str, bytes]) -> bool:
        """Write a file to the sandbox. Parent directories are created."""
        if not self._is_running:
            await self.start()
        try:
            await asyncio.to_thread(
                self._get_client().machines.files.upload, self.machine_id, path, content
            )
            return True
        except Exception as exc:
            logger.error("boxd write_file failed for %s: %s", path, exc)
            return False

    async def read_file(self, path: str) -> Optional[Union[str, bytes]]:
        """Read a file from the sandbox as text."""
        if not self._is_running:
            await self.start()
        try:
            content = await asyncio.to_thread(
                self._get_client().machines.files.download, self.machine_id, path
            )
            return content.decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("boxd read_file failed for %s: %s", path, exc)
            return None

    async def list_files(self, path: str = "/") -> List[str]:
        """List the files in a sandbox directory (not recursive)."""
        if not self._is_running:
            await self.start()
        try:
            listing = await asyncio.to_thread(
                self._get_client().machines.files.list_dir, self.machine_id, path
            )
        except Exception:
            return []
        base = path.rstrip("/")
        return [f"{base}/{entry.name}" for entry in listing.entries if not entry.is_dir]

    def get_status(self) -> Dict[str, Any]:
        """Get sandbox status information."""
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "machine_id": self.machine_id,
            "region": self.region,
            "api_key_set": bool(self._api_key),
        }

    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        await self.stop()

    async def reset(self) -> None:
        """Reset sandbox to a fresh machine."""
        await self.stop()
        await self.start()
