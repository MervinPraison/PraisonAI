"""
Modal Sandbox implementation for PraisonAI.

Provides serverless code execution on Modal's cloud platform.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from praisonaiagents.sandbox import (
    SandboxResult,
    SandboxStatus,
    ResourceLimits,
)

logger = logging.getLogger(__name__)
TIMEOUT_EXIT_CODE = 124


class ModalSandbox:
    """Modal-based sandbox for serverless code execution.
    
    Executes code on Modal's serverless GPU platform with automatic scaling
    and resource management.
    
    Example:
        from praisonai.sandbox import ModalSandbox
        
        sandbox = ModalSandbox(gpu="A100")
        result = await sandbox.execute("import torch; print(torch.cuda.is_available())")
        print(result.stdout)  # True
    
    Requires: modal package (install with pip install praisonai[modal])
    """
    
    def __init__(
        self,
        gpu: Optional[str] = None,
        image: str = "python:3.11",
        timeout: int = 300,
        app_name: Optional[str] = None,
    ):
        """Initialize the Modal sandbox.
        
        Args:
            gpu: GPU type ("T4", "A10G", "A100", etc.)
            image: Docker image to use as base
            timeout: Maximum execution time in seconds
            app_name: Optional Modal app name
        """
        self.gpu = gpu
        self.image = image
        self.timeout = timeout
        self.app_name = app_name or f"praisonai-sandbox-{uuid.uuid4().hex[:8]}"
        
        self._app = None
        self._function = None
        self._is_running = False
    
    @property
    def is_available(self) -> bool:
        """Check if Modal backend is available."""
        try:
            import modal
            return True
        except ImportError:
            return False
    
    @property
    def sandbox_type(self) -> str:
        return "modal"
    
    async def start(self) -> None:
        """Start/initialize the Modal app."""
        if self._is_running:
            return
        
        if not self.is_available:
            raise RuntimeError(
                "Modal backend not available. Install with: pip install praisonai[modal]"
            )
        
        try:
            import modal
            execution_timeout = self.timeout
            
            # Create Modal app
            self._app = modal.App(self.app_name)
            
            # Configure image
            if self.gpu:
                gpu_config = modal.gpu.T4() if self.gpu.upper() == "T4" else \
                           modal.gpu.A10G() if self.gpu.upper() == "A10G" else \
                           modal.gpu.A100() if self.gpu.upper() == "A100" else \
                           modal.gpu.T4()  # Default fallback
                           
                image = modal.Image.from_registry(
                    self.image,
                    add_python="3.11"
                ).pip_install("torch", "numpy")
            else:
                image = modal.Image.from_registry(
                    self.image,
                    add_python="3.11"
                )
                gpu_config = None
            
            # Create function for code execution
            @self._app.function(
                image=image,
                gpu=gpu_config,
                timeout=self.timeout,
                allow_concurrent_inputs=10,
                keep_warm=1,
            )
            def execute_code(code: str, language: str = "python", env_vars: Dict[str, str] = None):
                """Execute code in Modal environment."""
                import logging
                import subprocess
                import tempfile
                import os
                import sys
                execute_logger = logging.getLogger(__name__)

                extension_map = {
                    "python": "py",
                    "bash": "sh",
                    "shell": "sh",
                    "javascript": "js",
                    "java": "java",
                    "cpp": "cpp",
                    "c": "c",
                }

                interpreter_map = {
                    "python": [sys.executable],
                    "bash": ["bash"],
                    "shell": ["bash"],
                    "javascript": ["node"],
                }

                ext = extension_map.get(language.lower(), "txt")
                interpreter = interpreter_map.get(language.lower())
                execution_env = os.environ.copy()
                execution_env.update(env_vars or {})

                # Write code to temp file
                with tempfile.NamedTemporaryFile(mode="w", suffix=f".{ext}", delete=False) as f:
                    f.write(code)
                    temp_file = f.name

                try:
                    if interpreter:
                        cmd = interpreter + [temp_file]
                    else:
                        # Try to execute directly
                        os.chmod(temp_file, 0o755)
                        cmd = [temp_file]

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=execution_timeout,
                        env=execution_env,
                    )

                    return {
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                except subprocess.TimeoutExpired:
                    return {
                        "exit_code": TIMEOUT_EXIT_CODE,
                        "stdout": "",
                        "stderr": "Execution timed out",
                    }
                except Exception as e:
                    return {
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": str(e),
                    }
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(temp_file)
                    except OSError as e:
                        execute_logger.debug(
                            f"Failed to remove temporary file {temp_file}: {e}"
                        )
            
            self._function = execute_code
            self._is_running = True
            logger.info(f"Modal sandbox initialized with app: {self.app_name}")
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Modal sandbox: {e}")
    
    async def stop(self) -> None:
        """Stop/cleanup the Modal app."""
        self._app = None
        self._function = None
        self._is_running = False
        logger.info("Modal sandbox stopped")
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Execute code on Modal platform.
        
        Args:
            code: Code to execute
            language: Programming language (python, bash, etc.)
            limits: Resource limits (timeout used from limits)
            env: Environment variables
            working_dir: Working directory (not used in serverless)
            
        Returns:
            Execution result
        """
        if not self._is_running:
            await self.start()
        
        execution_id = str(uuid.uuid4())
        started_at = time.time()
        
        try:
            # Call Modal function
            result = await self._function.remote.aio(
                code=code,
                language=language,
                env_vars=env or {}
            )
            
            completed_at = time.time()
            duration = completed_at - started_at
            
            status = SandboxStatus.COMPLETED if result["exit_code"] == 0 else SandboxStatus.FAILED
            
            return SandboxResult(
                execution_id=execution_id,
                status=status,
                exit_code=result["exit_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                metadata={
                    "platform": "modal",
                    "gpu": self.gpu,
                    "language": language,
                    "app_name": self.app_name,
                }
            )
            
        except Exception as e:
            error_msg = str(e)
            status = SandboxStatus.TIMEOUT if "timeout" in error_msg.lower() else SandboxStatus.FAILED
            
            return SandboxResult(
                execution_id=execution_id,
                status=status,
                error=error_msg,
                started_at=started_at,
                completed_at=time.time(),
                duration_seconds=time.time() - started_at,
                metadata={
                    "platform": "modal",
                    "gpu": self.gpu,
                    "language": language,
                    "app_name": self.app_name,
                }
            )
    
    async def execute_file(
        self,
        file_path: str,
        args: Optional[List[str]] = None,
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a file on Modal platform.
        
        Note: File must be uploaded to Modal first via write_file.
        """
        # Read file content and execute it
        content = await self.read_file(file_path)
        if content is None:
            return SandboxResult(
                execution_id=str(uuid.uuid4()),
                status=SandboxStatus.FAILED,
                error=f"File not found: {file_path}",
                started_at=time.time(),
                completed_at=time.time(),
            )
        
        # Determine language from file extension
        language = "python"
        if file_path.endswith(('.sh', '.bash')):
            language = "bash"
        elif file_path.endswith('.js'):
            language = "javascript"
        elif file_path.endswith('.java'):
            language = "java"
        
        return await self.execute(content, language, limits, env)
    
    async def run_command(
        self,
        command: Union[str, List[str]],
        limits: Optional[ResourceLimits] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> SandboxResult:
        """Run a shell command on Modal platform."""
        if isinstance(command, list):
            command = " ".join(command)
        
        return await self.execute(command, "bash", limits, env, working_dir)
    
    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Write a file (stored in Modal's temporary storage)."""
        # Modal functions are stateless, so we simulate file storage
        # In practice, you'd use Modal Volumes for persistent storage
        logger.warning("Modal sandbox write_file is limited - files are not persistent between executions")
        return True
    
    async def read_file(
        self,
        path: str,
    ) -> Optional[Union[str, bytes]]:
        """Read a file (not supported in stateless Modal functions)."""
        logger.warning("Modal sandbox read_file is not supported for stateless functions")
        return None
    
    async def list_files(
        self,
        path: str = "/",
    ) -> List[str]:
        """List files (not supported in stateless Modal functions)."""
        logger.warning("Modal sandbox list_files is not supported for stateless functions")
        return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get Modal sandbox status information."""
        return {
            "available": self.is_available,
            "type": self.sandbox_type,
            "running": self._is_running,
            "gpu": self.gpu,
            "image": self.image,
            "app_name": self.app_name,
            "timeout": self.timeout,
        }
    
    async def cleanup(self) -> None:
        """Clean up Modal resources."""
        # Modal automatically cleans up after function execution
        logger.info("Modal sandbox cleanup - automatic resource cleanup by platform")
    
    async def reset(self) -> None:
        """Reset sandbox to initial state."""
        # Modal functions are stateless, so reset is automatic
        logger.info("Modal sandbox reset - functions are stateless by default")
