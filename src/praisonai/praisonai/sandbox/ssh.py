"""
SSH Sandbox implementation for PraisonAI.

Provides remote code execution via SSH connections.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from praisonaiagents.sandbox import (
    SandboxResult,
    SandboxStatus,
    ResourceLimits,
)

logger = logging.getLogger(__name__)


class SSHSandbox:
    """SSH-based sandbox for remote code execution.
    
    Executes code on remote servers via SSH connections with resource limits
    and security policies.
    
    Example:
        from praisonai.sandbox import SSHSandbox
        
        sandbox = SSHSandbox(
            host="gpu-server.example.com",
            user="ubuntu",
            key_file="~/.ssh/id_rsa",
        )
        result = await sandbox.execute("python train.py")
        print(result.stdout)
    
    Requires: asyncssh package (install with pip install praisonai[ssh])
    """
    
    def __init__(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        key_file: Optional[str] = None,
        password: Optional[str] = None,
        working_dir: str = "/tmp/praisonai",
        timeout: int = 300,
    ):
        """Initialize the SSH sandbox.
        
        Args:
            host: Remote host to connect to
            user: SSH username
            port: SSH port
            key_file: Path to private key file
            password: SSH password (if not using key)
            working_dir: Working directory on remote host
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.user = user
        self.port = port
        self.key_file = os.path.expanduser(key_file) if key_file else None
        self.password = password
        self.working_dir = working_dir
        self.timeout = timeout
        
        self._connection = None
        self._is_running = False
    
    @property
    def is_available(self) -> bool:
        """Check if SSH backend is available."""
        try:
            import asyncssh
            return True
        except ImportError:
            return False
    
    @property
    def sandbox_type(self) -> str:
        return "ssh"
    
    async def start(self) -> None:
        """Start/initialize the SSH connection."""
        if self._is_running:
            return
        
        if not self.is_available:
            raise RuntimeError(
                "SSH backend not available. Install with: pip install praisonai[ssh]"
            )
        
        try:
            import asyncssh
            
            # Prepare connection kwargs
            connect_kwargs = {
                "host": self.host,
                "port": self.port,
                "username": self.user,
                "connect_timeout": self.timeout,
            }
            
            if self.key_file:
                connect_kwargs["client_keys"] = [self.key_file]
            elif self.password:
                connect_kwargs["password"] = self.password
            else:
                # Try default key files
                connect_kwargs["client_keys"] = ["~/.ssh/id_rsa", "~/.ssh/id_ed25519"]
            
            self._connection = await asyncssh.connect(**connect_kwargs)
            
            # Create working directory
            await self._connection.run(f"mkdir -p {self.working_dir}")
            
            self._is_running = True
            logger.info(f"SSH sandbox connected to {self.user}@{self.host}:{self.port}")
            
        except Exception as e:
            raise RuntimeError(f"Failed to connect via SSH: {e}")
    
    async def stop(self) -> None:
        """Stop/cleanup the SSH connection."""
        if self._connection:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None
        
        self._is_running = False
        logger.info(f"SSH sandbox disconnected from {self.host}")
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Execute code on the remote server.
        
        Args:
            code: Code to execute
            language: Programming language (python, bash, etc.)
            limits: Resource limits for execution
            env: Environment variables
            working_dir: Working directory for execution
            
        Returns:
            Execution result
        """
        if not self._is_running:
            await self.start()
        
        execution_id = str(uuid.uuid4())
        started_at = time.time()
        
        try:
            # Create temporary file for code
            remote_file = f"{self.working_dir}/exec_{execution_id}.{self._get_file_extension(language)}"
            
            # Write code to remote file
            await self.write_file(remote_file, code)
            
            # Build command
            command = self._build_command(language, remote_file, limits, env)
            
            # Execute command
            result = await self._run_command_with_limits(
                command, 
                limits, 
                working_dir or self.working_dir
            )
            
            # Cleanup temp file
            await self._connection.run(f"rm -f {remote_file}")
            
            completed_at = time.time()
            duration = completed_at - started_at
            
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.COMPLETED if result.exit_status == 0 else SandboxStatus.FAILED,
                exit_code=result.exit_status,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                metadata={"host": self.host, "language": language}
            )
            
        except asyncio.TimeoutError:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.TIMEOUT,
                error="Execution timed out",
                started_at=started_at,
                completed_at=time.time(),
                duration_seconds=time.time() - started_at,
                metadata={"host": self.host, "language": language}
            )
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=time.time(),
                duration_seconds=time.time() - started_at,
                metadata={"host": self.host, "language": language}
            )
    
    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a file on the remote server."""
        if not self._is_running:
            await self.start()
        
        execution_id = str(uuid.uuid4())
        started_at = time.time()
        
        try:
            # Build command
            command_parts = [file_path]
            if args:
                command_parts.extend(args)
            command = " ".join(command_parts)
            
            # Execute command
            result = await self._run_command_with_limits(command, limits, self.working_dir)
            
            completed_at = time.time()
            duration = completed_at - started_at
            
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.COMPLETED if result.exit_status == 0 else SandboxStatus.FAILED,
                exit_code=result.exit_status,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                metadata={"host": self.host, "file": file_path}
            )
            
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=time.time(),
                duration_seconds=time.time() - started_at,
                metadata={"host": self.host, "file": file_path}
            )
    
    async def run_command(
        self,
        command: Union[str, List[str]],
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Run a shell command on the remote server."""
        if not self._is_running:
            await self.start()
        
        execution_id = str(uuid.uuid4())
        started_at = time.time()
        
        try:
            # Convert command to string if needed
            if isinstance(command, list):
                command = " ".join(command)
            
            # Execute command
            result = await self._run_command_with_limits(
                command, 
                limits, 
                working_dir or self.working_dir
            )
            
            completed_at = time.time()
            duration = completed_at - started_at
            
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.COMPLETED if result.exit_status == 0 else SandboxStatus.FAILED,
                exit_code=result.exit_status,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                metadata={"host": self.host, "command": command}
            )
            
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=time.time(),
                duration_seconds=time.time() - started_at,
                metadata={"host": self.host, "command": command}
            )
    
    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file to the remote server."""
        if not self._is_running:
            await self.start()
        
        try:
            # Create directory if needed
            directory = os.path.dirname(path)
            if directory:
                await self._connection.run(f"mkdir -p {directory}")
            
            # Write content
            async with self._connection.start_sftp_client() as sftp:
                if isinstance(content, str):
                    content = content.encode('utf-8')
                
                async with sftp.open(path, 'wb') as f:
                    await f.write(content)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to write file {path}: {e}")
            return False
    
    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file from the remote server."""
        if not self._is_running:
            await self.start()
        
        try:
            async with self._connection.start_sftp_client() as sftp:
                async with sftp.open(path, 'rb') as f:
                    content = await f.read()
                    
                # Try to decode as UTF-8, return bytes if it fails
                try:
                    return content.decode('utf-8')
                except UnicodeDecodeError:
                    return content
            
        except Exception as e:
            logger.error(f"Failed to read file {path}: {e}")
            return None
    
    async def list_files(
        self,
        path: str = "/",
    ) -> List[str]:
        """List files in a remote directory."""
        if not self._is_running:
            await self.start()
        
        try:
            result = await self._connection.run(f"find {path} -type f")
            if result.exit_status == 0:
                return result.stdout.strip().split('\n') if result.stdout.strip() else []
            return []
            
        except Exception as e:
            logger.error(f"Failed to list files in {path}: {e}")
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get SSH sandbox status information."""
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "host": self.host,
            "user": self.user,
            "port": self.port,
            "working_dir": self.working_dir,
        }
    
    async def cleanup(self) -> None:
        """Clean up remote sandbox resources."""
        if not self._is_running:
            return
        
        try:
            # Clean working directory
            await self._connection.run(f"rm -rf {self.working_dir}/*")
        except Exception as e:
            logger.warning(f"Failed to cleanup working directory: {e}")
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        await self.cleanup()
        if self._is_running:
            # Recreate working directory
            await self._connection.run(f"mkdir -p {self.working_dir}")
    
    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": "py",
            "bash": "sh", 
            "shell": "sh",
            "javascript": "js",
            "typescript": "ts",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "go": "go",
            "rust": "rs",
        }
        return extensions.get(language.lower(), "txt")
    
    def _build_command(
        self, 
        language: str, 
        file_path: str, 
        limits: Optional[ResourceLimits],
        env: Optional[Dict[str, str]]
    ) -> str:
        """Build execution command for language."""
        interpreters = {
            "python": f"python3 {file_path}",
            "bash": f"bash {file_path}",
            "shell": f"bash {file_path}",
            "javascript": f"node {file_path}",
            "typescript": f"npx ts-node {file_path}",
            "java": f"javac {file_path} && java {os.path.splitext(os.path.basename(file_path))[0]}",
        }
        
        base_command = interpreters.get(language.lower(), f"cat {file_path}")
        
        # Add environment variables
        if env:
            env_vars = " ".join(f"{k}={v}" for k, v in env.items())
            base_command = f"env {env_vars} {base_command}"
        
        # Add resource limits using timeout and ulimit
        if limits:
            if limits.timeout_seconds > 0:
                base_command = f"timeout {limits.timeout_seconds} {base_command}"
            
            if limits.memory_mb > 0:
                # ulimit -v sets virtual memory limit in KB
                memory_kb = limits.memory_mb * 1024
                base_command = f"ulimit -v {memory_kb} && {base_command}"
        
        return base_command
    
    async def _run_command_with_limits(
        self,
        command: str,
        limits: Optional[ResourceLimits],
        working_dir: str
    ):
        """Run command with resource limits."""
        # Change to working directory
        full_command = f"cd {working_dir} && {command}"
        
        # Set timeout
        timeout = None
        if limits and limits.timeout_seconds > 0:
            timeout = limits.timeout_seconds
        
        # Execute with timeout
        if timeout:
            result = await asyncio.wait_for(
                self._connection.run(full_command),
                timeout=timeout
            )
        else:
            result = await self._connection.run(full_command)
        
        return result