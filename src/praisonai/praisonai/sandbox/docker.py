"""
Docker Sandbox implementation for PraisonAI.

Provides isolated code execution in Docker containers.
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


class DockerSandbox:
    """Docker-based sandbox for safe code execution.
    
    Executes code in isolated Docker containers with resource limits
    and security policies.
    
    Example:
        from praisonai.sandbox import DockerSandbox
        
        sandbox = DockerSandbox(image="python:3.11-slim")
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    
    Requires: Docker installed and running
    """
    
    def __init__(
        self,
        image: str = "python:3.11-slim",
        config: Optional[SandboxConfig] = None,
    ):
        """Initialize the Docker sandbox.
        
        Args:
            image: Docker image to use
            config: Optional sandbox configuration
        """
        self.config = config or SandboxConfig.docker(image)
        self._image = image
        self._container_id: Optional[str] = None
        self._is_running = False
        self._temp_dir: Optional[str] = None
    
    @property
    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @property
    def sandbox_type(self) -> str:
        return "docker"
    
    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        if self._is_running:
            return
        
        if not self.is_available:
            raise RuntimeError("Docker is not available")
        
        self._temp_dir = tempfile.mkdtemp(prefix="praisonai_sandbox_")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "pull", self._image,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        except Exception as e:
            logger.warning(f"Failed to pull image: {e}")
        
        self._is_running = True
        logger.info(f"Docker sandbox initialized with image: {self._image}")
    
    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        if not self._is_running:
            return
        
        if self._container_id:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", self._container_id,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            except Exception as e:
                logger.warning(f"Failed to remove container: {e}")
            self._container_id = None
        
        if self._temp_dir and os.path.exists(self._temp_dir):
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        
        self._is_running = False
        logger.info("Docker sandbox stopped")
    
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
        
        docker_cmd = self._build_docker_command(
            code_file=code_file,
            language=language,
            limits=limits,
            env=env,
            working_dir=working_dir,
        )
        
        started_at = time.time()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
        
        if isinstance(command, list):
            cmd_str = " ".join(command)
        else:
            cmd_str = command
        
        docker_cmd = [
            "docker", "run", "--rm",
            "--memory", f"{limits.memory_mb}m",
            "--cpus", str(limits.cpu_percent / 100),
        ]
        
        if not limits.network_enabled:
            docker_cmd.extend(["--network", "none"])
        
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        if working_dir:
            docker_cmd.extend(["-w", working_dir])
        
        docker_cmd.extend([self._image, "sh", "-c", cmd_str])
        
        started_at = time.time()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
            "image": self._image,
            "container_id": self._container_id,
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
    
    def _build_docker_command(
        self,
        code_file: str,
        language: str,
        limits: ResourceLimits,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> List[str]:
        """Build the Docker run command."""
        docker_cmd = [
            "docker", "run", "--rm",
            "--memory", f"{limits.memory_mb}m",
            "--cpus", str(limits.cpu_percent / 100),
            "--pids-limit", str(limits.max_processes),
        ]
        
        if not limits.network_enabled:
            docker_cmd.extend(["--network", "none"])
        
        docker_cmd.extend(["-v", f"{code_file}:/code/script.py:ro"])
        
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        docker_cmd.extend(["-w", working_dir or "/code"])
        
        docker_cmd.append(self._image)
        
        if language == "python":
            docker_cmd.extend(["python", "/code/script.py"])
        elif language == "bash":
            docker_cmd.extend(["bash", "/code/script.py"])
        else:
            docker_cmd.extend(["python", "/code/script.py"])
        
        return docker_cmd
