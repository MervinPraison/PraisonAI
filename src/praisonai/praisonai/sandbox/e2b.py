"""
E2B Sandbox implementation for PraisonAI.

Provides isolated code execution using E2B cloud VMs.
"""

from __future__ import annotations

import asyncio
import logging
import os
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


class E2BSandbox:
    """E2B cloud sandbox for safe code execution.
    
    Executes code in isolated E2B cloud VMs with full filesystem access.
    
    Example:
        import os
        from praisonai.sandbox import E2BSandbox
        
        os.environ["E2B_API_KEY"] = "your-api-key"
        sandbox = E2BSandbox()
        result = await sandbox.execute("print('Hello, World!')")
        print(result.stdout)  # Hello, World!
    
    Requires: 
        - pip install e2b-code-interpreter  
        - E2B_API_KEY environment variable
    """
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        """Initialize the E2B sandbox.
        
        Args:
            config: Optional sandbox configuration
        """
        self.config = config or SandboxConfig.e2b()
        self._sandbox = None
        self._is_running = False
        
    @property
    def is_available(self) -> bool:
        """Check if E2B is available."""
        try:
            import e2b_code_interpreter
            api_key = os.getenv("E2B_API_KEY")
            return api_key is not None and api_key.strip() != ""
        except ImportError:
            return False
    
    @property
    def sandbox_type(self) -> str:
        return "e2b"
    
    async def start(self) -> None:
        """Start/initialize the sandbox environment."""
        if self._is_running:
            return
        
        if not self.is_available:
            raise RuntimeError(
                "E2B is not available. Please install e2b-code-interpreter and set E2B_API_KEY"
            )
        
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError:
            raise ImportError(
                "e2b-code-interpreter not installed. "
                "Install with: pip install e2b-code-interpreter"
            )
        
        api_key = os.getenv("E2B_API_KEY")
        if not api_key:
            raise ValueError("E2B_API_KEY environment variable not set")
        
        # Create E2B sandbox (this starts a cloud VM)
        self._sandbox = Sandbox(api_key=api_key)
        self._is_running = True
        logger.info("E2B sandbox initialized")
    
    async def stop(self) -> None:
        """Stop/cleanup the sandbox environment."""
        if not self._is_running:
            return
        
        if self._sandbox:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._sandbox.kill
                )
            except Exception as e:
                logger.warning(f"Failed to kill E2B sandbox: {e}")
            self._sandbox = None
        
        self._is_running = False
        logger.info("E2B sandbox stopped")
    
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
        
        try:
            if language == "python":
                result = await self._execute_python_code(code, limits, env)
            elif language == "bash":
                result = await self._execute_bash_command(code, limits, env, working_dir)
            else:
                # Default to Python for other languages
                result = await self._execute_python_code(code, limits, env)
            
            result.execution_id = execution_id
            result.started_at = started_at
            result.completed_at = time.time()
            result.duration_seconds = result.completed_at - started_at
            
            return result
            
        except Exception as e:
            return SandboxResult(
                execution_id=execution_id,
                status=SandboxStatus.FAILED,
                error=str(e),
                duration_seconds=time.time() - started_at,
                started_at=started_at,
                completed_at=time.time(),
            )
    
    async def _execute_python_code(
        self,
        code: str,
        limits: ResourceLimits,
        env: Optional[Dict[str, str]],
    ) -> SandboxResult:
        """Execute Python code using E2B code interpreter."""
        try:
            # Run in executor to avoid blocking the event loop
            execution = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self._sandbox.run_code(code, timeout=limits.timeout_seconds)
            )
            
            # Extract results from E2B execution
            stdout_parts = []
            stderr_parts = []
            
            for result in execution.results:
                if hasattr(result, 'text') and result.text:
                    stdout_parts.append(str(result.text))
                elif hasattr(result, 'logs'):
                    # Handle different result types from E2B
                    for log in result.logs:
                        if hasattr(log, 'line'):
                            stdout_parts.append(str(log.line))
            
            if execution.error:
                stderr_parts.append(execution.error.traceback if execution.error.traceback else str(execution.error))
                exit_code = 1
                status = SandboxStatus.FAILED
            else:
                exit_code = 0
                status = SandboxStatus.COMPLETED
            
            return SandboxResult(
                status=status,
                exit_code=exit_code,
                stdout="\n".join(stdout_parts) if stdout_parts else "",
                stderr="\n".join(stderr_parts) if stderr_parts else "",
            )
            
        except Exception as e:
            if "timeout" in str(e).lower():
                return SandboxResult(
                    status=SandboxStatus.TIMEOUT,
                    error=f"Execution timed out after {limits.timeout_seconds}s",
                )
            else:
                return SandboxResult(
                    status=SandboxStatus.FAILED,
                    error=str(e),
                )
    
    async def _execute_bash_command(
        self,
        command: str,
        limits: ResourceLimits,
        env: Optional[Dict[str, str]],
        working_dir: Optional[str],
    ) -> SandboxResult:
        """Execute bash command using E2B terminal."""
        try:
            # Set environment variables
            if env:
                import shlex
                for key, value in env.items():
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda k=key, v=value: self._sandbox.commands.run(f"export {shlex.quote(k)}={shlex.quote(v)}", timeout=5)
                    )
            
            # Change directory if needed
            if working_dir:
                import shlex
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._sandbox.commands.run(f"cd {shlex.quote(working_dir)}", timeout=5)
                )
            
            # Execute the command
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._sandbox.commands.run(command, timeout=limits.timeout_seconds)
            )
            
            return SandboxResult(
                status=SandboxStatus.COMPLETED if result.exit_code == 0 else SandboxStatus.FAILED,
                exit_code=result.exit_code,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
            
        except Exception as e:
            if "timeout" in str(e).lower():
                return SandboxResult(
                    status=SandboxStatus.TIMEOUT,
                    error=f"Command timed out after {limits.timeout_seconds}s",
                )
            else:
                return SandboxResult(
                    status=SandboxStatus.FAILED,
                    error=str(e),
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
            # Read file content and execute
            with open(file_path, "r") as f:
                code = f.read()
            
            if file_path.endswith(".py"):
                return await self.execute(code, language="python", limits=limits, env=env)
            elif file_path.endswith((".sh", ".bash")):
                return await self.execute(code, language="bash", limits=limits, env=env)
            else:
                # Try to execute as Python
                return await self.execute(code, language="python", limits=limits, env=env)
                
        except FileNotFoundError:
            return SandboxResult(
                status=SandboxStatus.FAILED,
                error=f"File not found: {file_path}",
            )
        except Exception as e:
            return SandboxResult(
                status=SandboxStatus.FAILED,
                error=str(e),
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
            command = " ".join(command)
        
        return await self._execute_bash_command(command, limits or self.config.resource_limits, env, working_dir)
    
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
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._sandbox.files.write(path, content)
            )
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
            content = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._sandbox.files.read(path)
            )
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
            # Use ls command to list files
            result = await self.run_command(f"find {path} -type f")
            if result.success:
                files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
                return files
            return []
        except Exception:
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get sandbox status information."""
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "api_key_set": bool(os.getenv("E2B_API_KEY")),
        }
    
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        if self._sandbox:
            try:
                # E2B sandbox cleanup is handled by the platform
                # We can optionally clear files or reset state here
                pass
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        await self.stop()
        await self.start()