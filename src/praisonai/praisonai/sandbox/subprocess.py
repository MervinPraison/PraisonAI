"""
Subprocess Sandbox implementation for PraisonAI.

Provides isolated code execution using subprocess with resource limits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
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


class SubprocessSandbox:
    """Subprocess-based sandbox for code execution.
    
    Executes code in isolated subprocesses with timeout limits.
    Less secure than Docker but works without Docker installation.
    
    Example:
        from praisonai.sandbox import SubprocessSandbox
        
        sandbox = SubprocessSandbox()
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    """
    
    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the subprocess sandbox.
        
        Args:
            config: Optional sandbox configuration
        """
        self.config = config or SandboxConfig.subprocess()
        self._is_running = False
        self._temp_dir: Optional[str] = None
    
    @property
    def is_available(self) -> bool:
        """Subprocess sandbox is always available."""
        return True
    
    @property
    def sandbox_type(self) -> str:
        return "subprocess"
    
    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        if self._is_running:
            return
        
        self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandbox_")
        self._is_running = True
        logger.info("Subprocess sandbox initialized")
    
    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        if not self._is_running:
            return
        
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        
        self._is_running = False
        logger.info("Subprocess sandbox stopped")
    
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
        
        code_file = os.path.join(self._temp_dir, f"code_{execution_id}.py")
        with open(code_file, "w") as f:
            f.write(code)
        
        if language == "python":
            cmd = ["python", code_file]
        elif language == "bash":
            cmd = ["bash", code_file]
        else:
            cmd = ["python", code_file]
        
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        
        started_at = time.time()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir or self._temp_dir,
                env=process_env,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds,
                )
                
                completed_at = time.time()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.COMPLETED,
                    exit_code=proc.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_seconds=completed_at - started_at,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.TIMEOUT,
                    error=f"Execution timed out after {limits.timeout_seconds}s",
                    duration_seconds=limits.timeout_seconds,
                    started_at=started_at,
                    completed_at=time.time(),
                )
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
        finally:
            if os.path.exists(code_file):
                os.remove(code_file)
    
    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a file in the sandbox."""
        if not os.path.exists(file_path):
            return SandboxResult(
                status=SandboxStatus.FAILED,
                error=f"File not found: {file_path}",
            )
        
        with open(file_path, "r") as f:
            code = f.read()
        
        return await self.execute(code, limits=limits, env=env)
    
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
        
        limits = limits or self.config.resource_limits
        execution_id = str(uuid.uuid4())
        
        if isinstance(command, str):
            cmd = ["sh", "-c", command]
        else:
            cmd = command
        
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        
        started_at = time.time()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir or self._temp_dir,
                env=process_env,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds,
                )
                
                completed_at = time.time()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.COMPLETED,
                    exit_code=proc.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_seconds=completed_at - started_at,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                
                return SandboxResult(
                    execution_id=execution_id,
                    status=SandboxStatus.TIMEOUT,
                    error=f"Command timed out after {limits.timeout_seconds}s",
                    duration_seconds=limits.timeout_seconds,
                    started_at=started_at,
                    completed_at=time.time(),
                )
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
    
    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file to the sandbox."""
        if not self._temp_dir:
            return False
        
        full_path = os.path.join(self._temp_dir, path.lstrip("/"))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        try:
            mode = "wb" if isinstance(content, bytes) else "w"
            with open(full_path, mode) as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            return False
    
    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file from the sandbox."""
        if not self._temp_dir:
            return None
        
        full_path = os.path.join(self._temp_dir, path.lstrip("/"))
        
        if not os.path.exists(full_path):
            return None
        
        try:
            with open(full_path, "r") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(full_path, "rb") as f:
                return f.read()
        except Exception:
            return None
    
    async def list_files(
        self,
        path: str = "/",
    ) -> List[str]:
        """List files in a sandbox directory."""
        if not self._temp_dir:
            return []
        
        full_path = os.path.join(self._temp_dir, path.lstrip("/"))
        
        if not os.path.exists(full_path):
            return []
        
        try:
            files = []
            for root, dirs, filenames in os.walk(full_path):
                for filename in filenames:
                    rel_path = os.path.relpath(
                        os.path.join(root, filename),
                        self._temp_dir,
                    )
                    files.append("/" + rel_path)
            return files
        except Exception:
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get sandbox status information."""
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "temp_dir": self._temp_dir,
        }
    
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandbox_")
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        await self.stop()
        await self.start()
